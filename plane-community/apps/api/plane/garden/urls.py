# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from plane.garden.views.firebase_session import (
    FirebaseMobileLaunchView,
    FirebaseSessionExchangeView,
    FirebaseSessionRevokeView,
)
from plane.garden.views.health import GardenWorkHealthView


urlpatterns = [
    path("health/", GardenWorkHealthView.as_view(), name="garden-work-health"),
    path("session/", FirebaseSessionExchangeView.as_view(), name="garden-firebase-session"),
    path("logout/", FirebaseSessionRevokeView.as_view(), name="garden-firebase-session-revoke"),
    path("mobile/", FirebaseMobileLaunchView.as_view(), name="garden-firebase-mobile-launch"),
]
