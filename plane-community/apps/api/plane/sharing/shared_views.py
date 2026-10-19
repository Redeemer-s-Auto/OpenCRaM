# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""The "Shared with me" endpoints: reach restricted items shared with you from outside their project.

Plane's normal screens require project membership. These endpoints let a
person on an item's share list open that one item (and nothing else in its
project) at the level the share grants. Pages are view-only here: page text is
edited through the live collaboration server, which still requires project
membership.
"""

import json

import nh3
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Max
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import IssueCommentSerializer, IssueCreateSerializer, IssueDetailSerializer
from plane.app.views.base import BaseAPIView
from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import Issue, IssueComment, Page, ProjectMember
from plane.sharing.models import AccessLevel, ItemShare
from plane.sharing.visibility import (
    issue_access_level,
    page_access_level,
    share_matches_user,
    visible_issues,
    visible_pages,
)
from plane.utils.host import base_host

NOT_FOUND = {"error": "The required object does not exist."}
EDITABLE_ISSUE_FIELDS = ("name", "description_html")


def _member_project_ids(user):
    return set(
        ProjectMember.objects.filter(member=user, is_active=True, deleted_at__isnull=True).values_list(
            "project_id", flat=True
        )
    )


def _shared_level(level):
    """Only a share grants access here; an unrestricted item (None) is not "shared"."""
    return level if level else 0


def _clean(html):
    """The read view shows HTML as-is in the browser, so strip anything that can run."""
    return nh3.clean(html or "")


def _person(user):
    if user is None:
        return None
    return {"id": str(user.id), "name": user.display_name or user.first_name or user.email}


class SharedWithMeListEndpoint(BaseAPIView):
    """Every restricted work item and page shared with the signed-in user."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        user = request.user
        shares = ItemShare.objects.filter(share_matches_user(user), workspace__slug=slug)
        member_projects = _member_project_ids(user)
        rows = []

        issue_levels = dict(
            shares.filter(issue__isnull=False).values("issue_id").annotate(level=Max("level")).values_list("issue_id", "level")
        )
        # visible_issues applies every other rule (private projects included) on top of the share.
        issues = (
            visible_issues(Issue.issue_objects.filter(id__in=issue_levels.keys(), workspace__slug=slug), user)
            .exclude(created_by=user)
            .select_related("project", "state", "created_by")
        )
        for issue in issues:
            rows.append(
                {
                    "kind": "issue",
                    "id": str(issue.id),
                    "name": issue.name,
                    "identifier": f"{issue.project.identifier}-{issue.sequence_id}",
                    "project_id": str(issue.project_id),
                    "project_name": issue.project.name,
                    "state": issue.state.name if issue.state else None,
                    "level": issue_levels[issue.id],
                    "in_project": issue.project_id in member_projects,
                    "shared_by": _person(issue.created_by),
                    "updated_at": issue.updated_at,
                }
            )

        page_levels = dict(
            shares.filter(page__isnull=False).values("page_id").annotate(level=Max("level")).values_list("page_id", "level")
        )
        pages = (
            visible_pages(Page.objects.filter(id__in=page_levels.keys(), workspace__slug=slug, archived_at__isnull=True), user)
            .exclude(owned_by=user)
            .select_related("owned_by")
            .prefetch_related("project_pages__project")
        )
        for page in pages:
            project = next((pp.project for pp in page.project_pages.all() if pp.deleted_at is None), None)
            rows.append(
                {
                    "kind": "page",
                    "id": str(page.id),
                    "name": page.name,
                    "identifier": None,
                    "project_id": str(project.id) if project else None,
                    "project_name": project.name if project else None,
                    "state": None,
                    "level": page_levels[page.id],
                    "in_project": bool(project and project.id in member_projects),
                    "shared_by": _person(page.owned_by),
                    "updated_at": page.updated_at,
                }
            )

        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        return Response(rows)


class SharedIssueEndpoint(BaseAPIView):
    """Read (and with Can edit, rename or rewrite) one work item shared with you."""

    def _issue(self, slug, issue_id):
        return Issue.issue_objects.filter(workspace__slug=slug, pk=issue_id).select_related(
            "project", "state", "created_by"
        ).first()

    def _payload(self, issue, level):
        return {
            "id": str(issue.id),
            "identifier": f"{issue.project.identifier}-{issue.sequence_id}",
            "name": issue.name,
            "description_html": _clean(issue.description_html),
            "project_id": str(issue.project_id),
            "project_name": issue.project.name,
            "state": {"name": issue.state.name, "group": issue.state.group, "color": issue.state.color}
            if issue.state
            else None,
            "priority": issue.priority,
            "start_date": issue.start_date,
            "target_date": issue.target_date,
            "assignees": [_person(user) for user in issue.assignees.all()],
            "labels": [{"name": label.name, "color": label.color} for label in issue.labels.all()],
            "created_by": _person(issue.created_by),
            "created_at": issue.created_at,
            "updated_at": issue.updated_at,
            "level": level,
        }

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, issue_id):
        issue = self._issue(slug, issue_id)
        level = _shared_level(issue_access_level(request.user, issue_id)) if issue else 0
        if not level:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(self._payload(issue, level))

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def patch(self, request, slug, issue_id):
        issue = self._issue(slug, issue_id)
        level = _shared_level(issue_access_level(request.user, issue_id)) if issue else 0
        if not level:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        if level < AccessLevel.EDIT:
            return Response({"error": "You don't have the required permissions."}, status=status.HTTP_403_FORBIDDEN)
        data = {key: request.data[key] for key in EDITABLE_ISSUE_FIELDS if key in request.data}
        if not data:
            return Response({"error": "Only name and description can be changed here."}, status=status.HTTP_400_BAD_REQUEST)
        current_instance = json.dumps(IssueDetailSerializer(issue).data, cls=DjangoJSONEncoder)
        serializer = IssueCreateSerializer(issue, data=data, partial=True, context={"project_id": issue.project_id})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        issue_activity.delay(
            type="issue.activity.updated",
            requested_data=json.dumps(data, cls=DjangoJSONEncoder),
            actor_id=str(request.user.id),
            issue_id=str(issue.id),
            project_id=str(issue.project_id),
            current_instance=current_instance,
            epoch=int(timezone.now().timestamp()),
            notification=True,
            origin=base_host(request=request, is_app=True),
        )
        issue.refresh_from_db()
        return Response(self._payload(issue, level))


class SharedIssueCommentEndpoint(BaseAPIView):
    """Comments on one work item shared with you. Posting needs Can comment."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, issue_id):
        issue = Issue.issue_objects.filter(workspace__slug=slug, pk=issue_id).first()
        if not issue or not _shared_level(issue_access_level(request.user, issue_id)):
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        comments = IssueComment.objects.filter(issue=issue).select_related("actor").order_by("created_at")
        return Response(
            [
                {
                    "id": str(comment.id),
                    "comment_html": _clean(comment.comment_html),
                    "actor": _person(comment.actor),
                    "created_at": comment.created_at,
                }
                for comment in comments
            ]
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug, issue_id):
        issue = Issue.issue_objects.filter(workspace__slug=slug, pk=issue_id).first()
        level = _shared_level(issue_access_level(request.user, issue_id)) if issue else 0
        if not level:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        if level < AccessLevel.COMMENT:
            return Response({"error": "You don't have the required permissions."}, status=status.HTTP_403_FORBIDDEN)
        serializer = IssueCommentSerializer(data={"comment_html": request.data.get("comment_html", "")})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(project_id=issue.project_id, issue_id=issue.id, actor=request.user)
        issue_activity.delay(
            type="comment.activity.created",
            requested_data=json.dumps(serializer.data, cls=DjangoJSONEncoder),
            actor_id=str(request.user.id),
            issue_id=str(issue.id),
            project_id=str(issue.project_id),
            current_instance=None,
            epoch=int(timezone.now().timestamp()),
            notification=True,
            origin=base_host(request=request, is_app=True),
        )
        return Response(
            {"id": serializer.data["id"], "comment_html": _clean(serializer.data["comment_html"])},
            status=status.HTTP_201_CREATED,
        )


class SharedPageEndpoint(BaseAPIView):
    """Read one page shared with you (view only)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, page_id):
        page = Page.objects.filter(workspace__slug=slug, pk=page_id, archived_at__isnull=True).select_related("owned_by").first()
        level = _shared_level(page_access_level(request.user, page_id)) if page else 0
        if not level:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        project = page.project_pages.filter(deleted_at__isnull=True).select_related("project").first()
        return Response(
            {
                "id": str(page.id),
                "name": page.name,
                "description_html": _clean(page.description_html),
                "project_name": project.project.name if project else None,
                "owned_by": _person(page.owned_by),
                "updated_at": page.updated_at,
                "level": level,
            }
        )
