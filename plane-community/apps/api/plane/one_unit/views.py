# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Card tree (sidebar), page list (project layout) and breadcrumb endpoints.

Every row goes through ``plane.one_unit.reach.reachable_issues``: project
membership, guest limits, sharing rules and private projects.
"""

import uuid

from django.db.models import Count, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Concat
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue
from plane.one_unit.reach import ancestor_ids, reach_q, reachable_issues
from plane.sharing.visibility import hidden_issue_ids

TREE_LIMIT, TREE_MAX = 50, 200
LIST_LIMIT, LIST_MAX = 500, 1000

ROW_FIELDS = (
    "id",
    "name",
    "project_id",
    "project_identifier",
    "sequence_id",
    "parent_id",
    "state_color",
    "state_group",
    "updated_at",
    "child_count",
)


def _paging(request, default, maximum):
    def number(key, fallback):
        try:
            return max(0, int(request.query_params.get(key, fallback)))
        except (TypeError, ValueError):
            return fallback

    return number("offset", 0), min(number("limit", default) or default, maximum)


def _uuid_or_none(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _child_count(user):
    """Subquery: how many reachable, live children a card has."""
    children = reachable_issues(Issue.issue_objects.filter(parent_id=OuterRef("id")), user)
    return Coalesce(
        Subquery(children.order_by().values("parent_id").annotate(n=Count("id")).values("n")[:1]),
        Value(0),
    )


def _annotate(queryset, user):
    return queryset.annotate(
        project_identifier=F("project__identifier"),
        state_color=F("state__color"),
        state_group=F("state__group"),
        child_count=_child_count(user),
    )


def _page(queryset, offset, limit, fields):
    total = queryset.count()
    rows = list(queryset.values(*fields)[offset : offset + limit])
    next_offset = offset + limit if offset + limit < total else None
    return {"results": rows, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}


def _mask_parents(rows, user):
    """``parent_id`` becomes null when the parent is out of reach (no hint that it exists)."""
    parent_ids = {str(row["parent_id"]) for row in rows if row.get("parent_id")}
    if not parent_ids:
        return rows
    visible = {
        str(i)
        for i in reachable_issues(Issue.all_objects.filter(pk__in=parent_ids), user).values_list("id", flat=True)
    }
    for row in rows:
        if row.get("parent_id") and str(row["parent_id"]) not in visible:
            row["parent_id"] = None
    return rows


class CardTreeEndpoint(BaseAPIView):
    """Sidebar tree. ``?project_id=`` gives a project's top cards; ``?parent_id=`` a card's children."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        user = request.user
        project_id = request.query_params.get("project_id")
        parent_id = request.query_params.get("parent_id")
        if (project_id and not _uuid_or_none(project_id)) or (parent_id and not _uuid_or_none(parent_id)):
            return Response({"error": "Invalid id"}, status=status.HTTP_400_BAD_REQUEST)
        offset, limit = _paging(request, TREE_LIMIT, TREE_MAX)
        base = Issue.issue_objects.filter(workspace__slug=slug)

        if parent_id:
            parent = reachable_issues(Issue.all_objects.filter(workspace__slug=slug, pk=parent_id), user)
            if not parent.exists():
                return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
            cards = reachable_issues(base.filter(parent_id=parent_id), user)
        elif project_id:
            cards = reachable_issues(base.filter(project_id=project_id), user)
            # Top of the project: no parent, a parent in another project, or a parent out of reach.
            reachable_parents = Issue.all_objects.filter(reach_q(user)).exclude(pk__in=hidden_issue_ids(user))
            cards = cards.filter(
                Q(parent__isnull=True)
                | ~Q(parent__project_id=project_id)
                | ~Q(parent_id__in=reachable_parents.values("id"))
            )
        else:
            return Response({"error": "project_id or parent_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        cards = _annotate(cards, user).order_by("sort_order", "created_at")
        data = _page(cards, offset, limit, ROW_FIELDS)
        _mask_parents(data["results"], user)
        return Response(data, status=status.HTTP_200_OK)


class CardBreadcrumbEndpoint(BaseAPIView):
    """The chain of cards above one card, root first, cut at the first one out of reach."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, issue_id):
        user = request.user
        if not reachable_issues(Issue.all_objects.filter(workspace__slug=slug, pk=issue_id), user).exists():
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        chain = ancestor_ids(issue_id)
        if not chain:
            return Response({"ancestors": []}, status=status.HTTP_200_OK)
        reachable = {
            str(row["id"]): row
            for row in reachable_issues(Issue.all_objects.filter(workspace__slug=slug, pk__in=chain), user)
            .annotate(project_identifier=F("project__identifier"), state_color=F("state__color"))
            .values("id", "name", "project_id", "project_identifier", "sequence_id", "state_color")
        }
        ancestors = []
        for ancestor_id in chain:
            if ancestor_id not in reachable:
                break
            ancestors.append(reachable[ancestor_id])
        ancestors.reverse()
        return Response({"ancestors": ancestors}, status=status.HTTP_200_OK)


class ProjectPageListEndpoint(BaseAPIView):
    """Every card of a project the user may reach, newest edit first, for the "Page list" layout."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        user = request.user
        offset, limit = _paging(request, LIST_LIMIT, LIST_MAX)
        cards = reachable_issues(Issue.issue_objects.filter(workspace__slug=slug, project_id=project_id), user)
        cards = _annotate(cards, user).annotate(
            updated_by_name=Concat(
                Coalesce(F("updated_by__first_name"), Value("")),
                Value(" "),
                Coalesce(F("updated_by__last_name"), Value("")),
            )
        )
        cards = cards.order_by("-updated_at")
        data = _page(cards, offset, limit, (*ROW_FIELDS, "updated_by_name"))
        for row in data["results"]:
            row["updated_by_name"] = (row.get("updated_by_name") or "").strip()
        _mask_parents(data["results"], user)
        return Response(data, status=status.HTTP_200_OK)
