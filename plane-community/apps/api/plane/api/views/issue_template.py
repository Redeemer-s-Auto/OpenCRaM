# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Public API (/api/v1/) for card templates.

Same rules as the app endpoints (plane.app.views.issue_template): any admin or
member of the board can list, add, change and delete its templates. Used by
importers (e.g. Notion database templates) that work with an API key.
"""

from plane.app.views.issue_template import IssueTemplateDetailEndpoint, IssueTemplateEndpoint

from .base import BaseAPIView


class IssueTemplateListCreateAPIEndpoint(BaseAPIView):
    get = IssueTemplateEndpoint.get
    post = IssueTemplateEndpoint.post


class IssueTemplateDetailAPIEndpoint(BaseAPIView):
    get = IssueTemplateDetailEndpoint.get
    patch = IssueTemplateDetailEndpoint.patch
    delete = IssueTemplateDetailEndpoint.delete
