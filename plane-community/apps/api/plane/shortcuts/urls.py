# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import (
    CardBacklinksEndpoint,
    CardLinkResolveEndpoint,
    CardLinkSearchEndpoint,
    CardShortcutInfoEndpoint,
    ProjectShortcutsEndpoint,
)

urlpatterns = [
    path("workspaces/<str:slug>/card-links/resolve/", CardLinkResolveEndpoint.as_view(), name="card-links-resolve"),
    path("workspaces/<str:slug>/card-links/search/", CardLinkSearchEndpoint.as_view(), name="card-links-search"),
    path(
        "workspaces/<str:slug>/cards/<uuid:issue_id>/backlinks/",
        CardBacklinksEndpoint.as_view(),
        name="card-backlinks",
    ),
    path(
        "workspaces/<str:slug>/cards/<uuid:issue_id>/shortcut/",
        CardShortcutInfoEndpoint.as_view(),
        name="card-shortcut-info",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/shortcuts/",
        ProjectShortcutsEndpoint.as_view(),
        name="project-shortcuts",
    ),
]
