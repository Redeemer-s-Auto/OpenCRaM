# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView

from .service import run_query


class InlineViewQueryEndpoint(BaseAPIView):
    """POST - the cards one live view block shows.

    Body: ``source`` (``{type: "project", project_id}``, ``{type: "children", parent_id}`` or
    ``{type: "linked", issue_id, field_id}``), optional ``filters`` (saved-view filter shape),
    ``custom_field_filters``, ``search``, ``order_by``, ``limit``. A POST so the settings can be
    sent as JSON; it changes nothing.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug):
        return Response(run_query(request.user, slug, request.data or {}))
