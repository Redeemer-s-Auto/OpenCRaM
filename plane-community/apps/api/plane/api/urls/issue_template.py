# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views.issue_template import IssueTemplateDetailAPIEndpoint, IssueTemplateListCreateAPIEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-templates/",
        IssueTemplateListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="api-work-item-templates",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-templates/<uuid:pk>/",
        IssueTemplateDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="api-work-item-template",
    ),
]
