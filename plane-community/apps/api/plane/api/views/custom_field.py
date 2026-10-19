# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Public API (/api/v1/) for custom field definitions.

Same rules as the app endpoints (plane.app.views.custom_field): any project
member can read; project admins can change. Values are read and written on the
work item itself through its ``custom_fields`` object.
"""

from plane.app.views.custom_field import (
    CustomFieldArchiveEndpoint,
    CustomFieldDetailEndpoint,
    CustomFieldEndpoint,
    CustomFieldReorderEndpoint,
)

from .base import BaseAPIView


class CustomFieldListCreateAPIEndpoint(BaseAPIView):
    get = CustomFieldEndpoint.get
    post = CustomFieldEndpoint.post


class CustomFieldDetailAPIEndpoint(BaseAPIView):
    get = CustomFieldDetailEndpoint.get
    patch = CustomFieldDetailEndpoint.patch
    delete = CustomFieldDetailEndpoint.delete


class CustomFieldArchiveAPIEndpoint(BaseAPIView):
    post = CustomFieldArchiveEndpoint.post
    delete = CustomFieldArchiveEndpoint.delete


class CustomFieldReorderAPIEndpoint(BaseAPIView):
    post = CustomFieldReorderEndpoint.post
