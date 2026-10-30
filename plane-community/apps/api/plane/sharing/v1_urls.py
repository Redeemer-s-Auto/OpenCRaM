# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.sharing import v1_views

urlpatterns = [
    path(
        "workspaces/<str:slug>/access-groups/",
        v1_views.AccessGroupAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="api-access-groups",
    ),
    path(
        "workspaces/<str:slug>/access-groups/<uuid:group_id>/",
        v1_views.AccessGroupAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="api-access-group",
    ),
    path(
        "workspaces/<str:slug>/access-groups/<uuid:group_id>/includes/",
        v1_views.AccessGroupIncludeAPIEndpoint.as_view(http_method_names=["post"]),
        name="api-access-group-includes",
    ),
    path(
        "workspaces/<str:slug>/access-groups/<uuid:group_id>/includes/<uuid:included_group_id>/",
        v1_views.AccessGroupIncludeAPIEndpoint.as_view(http_method_names=["delete"]),
        name="api-access-group-include",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-shares/",
        v1_views.ProjectGroupShareAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="api-project-group-shares",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-shares/<uuid:group_id>/",
        v1_views.ProjectGroupShareAPIEndpoint.as_view(http_method_names=["delete"]),
        name="api-project-group-share",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-exclusions/",
        v1_views.ProjectGroupExclusionAPIEndpoint.as_view(http_method_names=["post"]),
        name="api-project-group-exclusions",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/group-exclusions/<uuid:group_id>/",
        v1_views.ProjectGroupExclusionAPIEndpoint.as_view(http_method_names=["delete"]),
        name="api-project-group-exclusion",
    ),
]
