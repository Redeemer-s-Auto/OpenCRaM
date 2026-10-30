# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""One-click "Add task list views" for a board: the Seen checkbox plus Active / Completed / Checked."""

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import CustomFieldSerializer, IssueViewSerializer
from plane.db.models import Project
from plane.utils.task_list_views import ensure_task_list_views

from ..base import BaseAPIView


class TaskListViewsEndpoint(BaseAPIView):
    """POST creates (or refreshes) the task-list views on a board. Board admins only. Idempotent."""

    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        result = ensure_task_list_views(project, request.user)
        views = [result["views"][name] for name in ("Active", "Completed", "Checked")]
        return Response(
            {
                "field": CustomFieldSerializer(result["field"]).data,
                "views": IssueViewSerializer(views, many=True).data,
                "created": result["created"],
                "updated": result["updated"],
                "field_created": result["field_created"],
            },
            status=status.HTTP_201_CREATED if result["created"] or result["field_created"] else status.HTTP_200_OK,
        )
