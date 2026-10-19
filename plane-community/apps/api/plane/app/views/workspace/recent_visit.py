# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import status
from rest_framework.response import Response

from plane.db.models import UserRecentVisit
from plane.app.serializers import WorkspaceRecentVisitSerializer

# Modules imports
from ..base import BaseViewSet
from plane.app.permissions import allow_permission, ROLE
from plane.sharing.visibility import hidden_issue_ids, hidden_page_ids


class UserRecentVisitViewSet(BaseViewSet):
    model = UserRecentVisit
    use_read_replica = True

    def get_serializer_class(self):
        return WorkspaceRecentVisitSerializer

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def list(self, request, slug):
        user_recent_visits = UserRecentVisit.objects.filter(workspace__slug=slug, user=request.user)

        entity_name = request.query_params.get("entity_name")

        if entity_name:
            user_recent_visits = user_recent_visits.filter(entity_name=entity_name)

        user_recent_visits = user_recent_visits.filter(entity_name__in=["issue", "page", "project"])
        user_recent_visits = user_recent_visits.exclude(
            entity_name="issue", entity_identifier__in=hidden_issue_ids(request.user)
        ).exclude(entity_name="page", entity_identifier__in=hidden_page_ids(request.user))

        serializer = WorkspaceRecentVisitSerializer(user_recent_visits[:20], many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
