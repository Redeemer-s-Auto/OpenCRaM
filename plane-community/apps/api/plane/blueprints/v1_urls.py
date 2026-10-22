# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.blueprints import v1_views

urlpatterns = [
    path(
        "workspaces/<str:slug>/blueprints/",
        v1_views.BlueprintListAPIEndpoint.as_view(http_method_names=["get"]),
        name="api-blueprints",
    ),
    path(
        "workspaces/<str:slug>/blueprints/<uuid:pk>/",
        v1_views.BlueprintDetailAPIEndpoint.as_view(http_method_names=["get"]),
        name="api-blueprint",
    ),
    path(
        "workspaces/<str:slug>/blueprints/<uuid:pk>/create-board/",
        v1_views.BlueprintCreateBoardAPIEndpoint.as_view(http_method_names=["post"]),
        name="api-blueprint-create-board",
    ),
]
