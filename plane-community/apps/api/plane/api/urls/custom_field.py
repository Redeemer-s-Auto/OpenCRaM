# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views.custom_field import (
    CustomFieldArchiveAPIEndpoint,
    CustomFieldDetailAPIEndpoint,
    CustomFieldListCreateAPIEndpoint,
    CustomFieldReorderAPIEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/",
        CustomFieldListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="custom-fields",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/reorder/",
        CustomFieldReorderAPIEndpoint.as_view(http_method_names=["post"]),
        name="custom-fields-reorder",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/<uuid:pk>/",
        CustomFieldDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="custom-field",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/custom-fields/<uuid:pk>/archive/",
        CustomFieldArchiveAPIEndpoint.as_view(http_method_names=["post", "delete"]),
        name="custom-field-archive",
    ),
]
