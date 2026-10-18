# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.api.views.garden import GardenAccessProjectionSyncEndpoint, GardenIdentitySyncEndpoint


urlpatterns = [
    path(
        "garden/identities/<str:firebase_uid>/sync/",
        GardenIdentitySyncEndpoint.as_view(http_method_names=["post"]),
        name="garden-identity-sync",
    ),
    path(
        "garden/access-projections/<str:firebase_uid>/sync/",
        GardenAccessProjectionSyncEndpoint.as_view(http_method_names=["post"]),
        name="garden-access-projection-sync",
    ),
]
