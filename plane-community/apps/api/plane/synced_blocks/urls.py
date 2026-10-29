# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import SyncedBlockEndpoint, SyncedBlockListEndpoint

urlpatterns = [
    path("workspaces/<str:slug>/synced-blocks/", SyncedBlockListEndpoint.as_view(), name="synced-blocks"),
    path("workspaces/<str:slug>/synced-blocks/<uuid:block_id>/", SyncedBlockEndpoint.as_view(), name="synced-block"),
]
