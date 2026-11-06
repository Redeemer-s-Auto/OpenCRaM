# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A cheap "did anything change?" probe, so open browsers can show each other's edits without a reload.

The page asks every few seconds. Each stamp is an opaque string made from how many rows exist and when the
newest one changed (soft-deleted rows count too, so a delete moves the stamp). When a stamp differs from the
last one the page saw, it refetches that part (cards, boards, pages). No stamp carries any content.
"""

import hashlib

from django.db.models import Count, Max
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, Page, Project

from . import service


def _stamp(queryset) -> str:
    row = queryset.aggregate(n=Count("id"), newest=Max("updated_at"), deleted=Max("deleted_at"))
    raw = f"{row['n']}|{row['newest']}|{row['deleted']}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]  # noqa: S324 - a change marker, not a secret


class LiveStampEndpoint(BaseAPIView):
    """GET ``?project_id=`` (optional) -> ``{"projects": s, "pages": s, "issues": s | null}``."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        project_id = service.as_uuid(request.query_params.get("project_id"))
        if request.query_params.get("project_id") and project_id is None:
            return Response({"error": "project_id must be a uuid"}, status=status.HTTP_400_BAD_REQUEST)
        projects = Project.all_objects.filter(workspace__slug=slug)
        pages = Page.all_objects.filter(workspace__slug=slug)
        issues = Issue.all_objects.filter(workspace__slug=slug, project_id=project_id) if project_id else None
        return Response(
            {
                "projects": _stamp(projects),
                "pages": _stamp(pages),
                "issues": _stamp(issues) if issues is not None else None,
            },
            status=status.HTTP_200_OK,
        )
