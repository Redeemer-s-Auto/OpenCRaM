# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.blueprints import views

urlpatterns = [
    path("workspaces/<str:slug>/blueprints/", views.BlueprintListEndpoint.as_view(), name="blueprints"),
    path("workspaces/<str:slug>/blueprints/import/", views.BlueprintImportEndpoint.as_view(), name="blueprint-import"),
    path("workspaces/<str:slug>/blueprints/<uuid:pk>/", views.BlueprintDetailEndpoint.as_view(), name="blueprint"),
    path(
        "workspaces/<str:slug>/blueprints/<uuid:pk>/recapture/",
        views.BlueprintRecaptureEndpoint.as_view(),
        name="blueprint-recapture",
    ),
    path(
        "workspaces/<str:slug>/blueprints/<uuid:pk>/versions/",
        views.BlueprintVersionsEndpoint.as_view(),
        name="blueprint-versions",
    ),
    path(
        "workspaces/<str:slug>/blueprints/<uuid:pk>/export/",
        views.BlueprintExportEndpoint.as_view(),
        name="blueprint-export",
    ),
    path("workspaces/<str:slug>/blueprints/<uuid:pk>/use/", views.BlueprintUseEndpoint.as_view(), name="blueprint-use"),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/blueprint-origin/",
        views.BoardOriginEndpoint.as_view(),
        name="board-blueprint-origin",
    ),
]
