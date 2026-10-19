# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

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
]
