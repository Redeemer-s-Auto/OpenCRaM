# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.sharing.shared_views import (
    SharedIssueCommentEndpoint,
    SharedIssueEndpoint,
    SharedPageEndpoint,
    SharedWithMeListEndpoint,
)
from plane.sharing.views import AccessGroupEndpoint, IssueSharingEndpoint, PageSharingEndpoint, ShareTargetSearchEndpoint

urlpatterns = [
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
