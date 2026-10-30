# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Public API (/api/v1/, X-Api-Key) for groups and board shares: what scripts need.

Same handlers and rules as the app endpoints (``plane.sharing.views``); the key
acts as the person who made it, so writes need a workspace admin's key.
"""

from plane.api.views.base import BaseAPIView
from plane.sharing.views import (
    AccessGroupIncludeViews,
    AccessGroupViews,
    ProjectGroupExclusionViews,
    ProjectGroupShareViews,
    TeamspaceViews,
)


class TeamspaceAPIEndpoint(TeamspaceViews, BaseAPIView):
    pass


class AccessGroupAPIEndpoint(AccessGroupViews, BaseAPIView):
    pass


class AccessGroupIncludeAPIEndpoint(AccessGroupIncludeViews, BaseAPIView):
    pass


class ProjectGroupShareAPIEndpoint(ProjectGroupShareViews, BaseAPIView):
    pass


class ProjectGroupExclusionAPIEndpoint(ProjectGroupExclusionViews, BaseAPIView):
    pass
