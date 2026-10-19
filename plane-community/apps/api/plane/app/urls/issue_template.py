# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views.issue_template import (
    IssueSaveAsTemplateEndpoint,
    IssueTemplateDetailEndpoint,
    IssueTemplateEndpoint,
    IssueTemplateUseEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-templates/",
        IssueTemplateEndpoint.as_view(),
        name="work-item-templates",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-templates/<uuid:pk>/",
        IssueTemplateDetailEndpoint.as_view(),
        name="work-item-template",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-item-templates/<uuid:pk>/use/",
        IssueTemplateUseEndpoint.as_view(),
        name="work-item-template-use",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/save-as-template/",
        IssueSaveAsTemplateEndpoint.as_view(),
        name="work-item-save-as-template",
    ),
]
