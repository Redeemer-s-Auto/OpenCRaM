# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import CustomField

from .service import link_candidates


class LinkCandidatesEndpoint(BaseAPIView):
    """GET ``?search=`` - cards the caller could link in this relation field.

    Only cards on the field's target board that the caller may see (or edit, for a
    two-way relation) are returned, the same rule the save uses.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, field_id):
        field = CustomField.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            pk=field_id,
            field_type=CustomField.RELATION,
            archived_at__isnull=True,
        ).first()
        if field is None:
            return Response({"error": "Field not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            limit = int(request.GET.get("limit", 20))
        except ValueError:
            limit = 20
        return Response(link_candidates(field, request.user, request.GET.get("search", ""), limit))
