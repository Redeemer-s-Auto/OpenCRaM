# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views.custom_field import (
    CustomFieldArchiveEndpoint,
    CustomFieldDetailEndpoint,
    CustomFieldEndpoint,
    CustomFieldReorderEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/",
        CustomFieldEndpoint.as_view(),
        name="project-custom-fields",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/reorder/",
        CustomFieldReorderEndpoint.as_view(),
        name="project-custom-fields-reorder",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/<uuid:pk>/",
        CustomFieldDetailEndpoint.as_view(),
        name="project-custom-field",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/<uuid:pk>/archive/",
        CustomFieldArchiveEndpoint.as_view(),
        name="project-custom-field-archive",
    ),
]
