# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import PageLinkResolveEndpoint, PageLinkSearchEndpoint, PageTreeEndpoint

urlpatterns = [
    path("workspaces/<str:slug>/page-tree/", PageTreeEndpoint.as_view(), name="page-tree"),
    path("workspaces/<str:slug>/page-links/resolve/", PageLinkResolveEndpoint.as_view(), name="page-links-resolve"),
    path("workspaces/<str:slug>/page-links/search/", PageLinkSearchEndpoint.as_view(), name="page-links-search"),
]
