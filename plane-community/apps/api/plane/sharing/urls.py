# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.sharing.shared_views import (
    SharedIssueCommentEndpoint,
    SharedIssueEndpoint,
    SharedPageEndpoint,
    SharedWithMeListEndpoint,
)
from plane.sharing.views import (
    AccessGroupEndpoint,
    AccessGroupIncludeEndpoint,
    IssueSharingEndpoint,
    PageSharingEndpoint,
    ProjectGroupExclusionEndpoint,
    ProjectGroupShareEndpoint,
    ShareTargetSearchEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-shares/",
        ProjectGroupShareEndpoint.as_view(http_method_names=["get", "post"]),
        name="project-group-shares",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-shares/<uuid:group_id>/",
        ProjectGroupShareEndpoint.as_view(http_method_names=["delete"]),
        name="project-group-share",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-exclusions/",
        ProjectGroupExclusionEndpoint.as_view(http_method_names=["post"]),
        name="project-group-exclusions",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-exclusions/<uuid:group_id>/",
        ProjectGroupExclusionEndpoint.as_view(http_method_names=["delete"]),
        name="project-group-exclusion",
    ),
    path(
        "workspaces/<str:slug>/access-groups/<uuid:group_id>/includes/",
        AccessGroupIncludeEndpoint.as_view(http_method_names=["post"]),
        name="access-group-includes",
    ),
    path(
        "workspaces/<str:slug>/access-groups/<uuid:group_id>/includes/<uuid:included_group_id>/",
        AccessGroupIncludeEndpoint.as_view(http_method_names=["delete"]),
        name="access-group-include",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/permissions/",
        IssueSharingEndpoint.as_view(),
        name="issue-sharing",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/pages/<uuid:page_id>/permissions/",
        PageSharingEndpoint.as_view(),
        name="page-sharing",
    ),
    path("workspaces/<str:slug>/access-groups/", AccessGroupEndpoint.as_view(), name="access-groups"),
    path("workspaces/<str:slug>/access-groups/<uuid:group_id>/", AccessGroupEndpoint.as_view(), name="access-group"),
    path("workspaces/<str:slug>/share-targets/", ShareTargetSearchEndpoint.as_view(), name="share-targets"),
    path("workspaces/<str:slug>/shared-with-me/", SharedWithMeListEndpoint.as_view(), name="shared-with-me"),
    path(
        "workspaces/<str:slug>/shared-with-me/issues/<uuid:issue_id>/",
        SharedIssueEndpoint.as_view(),
        name="shared-with-me-issue",
    ),
    path(
        "workspaces/<str:slug>/shared-with-me/issues/<uuid:issue_id>/comments/",
        SharedIssueCommentEndpoint.as_view(),
        name="shared-with-me-issue-comments",
    ),
    path(
        "workspaces/<str:slug>/shared-with-me/pages/<uuid:page_id>/",
        SharedPageEndpoint.as_view(),
        name="shared-with-me-page",
    ),
]
