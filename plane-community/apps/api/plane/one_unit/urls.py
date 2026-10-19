# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.one_unit.views import CardBreadcrumbEndpoint, CardTreeEndpoint, ProjectPageListEndpoint

urlpatterns = [
    path("workspaces/<str:slug>/card-tree/", CardTreeEndpoint.as_view(), name="card-tree"),
    path(
        "workspaces/<str:slug>/cards/<uuid:issue_id>/breadcrumb/",
        CardBreadcrumbEndpoint.as_view(),
        name="card-breadcrumb",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/page-list/",
        ProjectPageListEndpoint.as_view(),
        name="project-page-list",
    ),
]
