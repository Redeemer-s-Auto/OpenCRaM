# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import LinkCandidatesEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/<uuid:field_id>/link-candidates/",
        LinkCandidatesEndpoint.as_view(),
        name="custom-field-link-candidates",
    ),
]
