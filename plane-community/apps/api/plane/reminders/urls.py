# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import ReminderEndpoint, ReminderListEndpoint, ReminderMoveEndpoint

urlpatterns = [
    path("workspaces/<str:slug>/date-reminders/", ReminderListEndpoint.as_view(), name="date-reminders"),
    path(
        "workspaces/<str:slug>/date-reminders/<uuid:mention_id>/",
        ReminderEndpoint.as_view(),
        name="date-reminder",
    ),
    path(
        "workspaces/<str:slug>/date-reminders/<uuid:mention_id>/move/",
        ReminderMoveEndpoint.as_view(),
        name="date-reminder-move",
    ),
]
