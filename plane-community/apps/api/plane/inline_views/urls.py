# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import InlineViewQueryEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/inline-views/query/",
        InlineViewQueryEndpoint.as_view(),
        name="inline-view-query",
    ),
]
