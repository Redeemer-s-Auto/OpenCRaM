# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.recurrence.views import IssueRepeatEndpoint, ProjectRepeatRulesEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/repeat/",
        IssueRepeatEndpoint.as_view(),
        name="issue-repeat",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/repeat-rules/",
        ProjectRepeatRulesEndpoint.as_view(),
        name="project-repeat-rules",
    ),
]
