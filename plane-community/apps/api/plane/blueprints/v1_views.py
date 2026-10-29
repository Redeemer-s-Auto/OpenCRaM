# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Public API (/api/v1/, API key) for blueprints: list them, make a board from one.

Same rules as the app endpoints; the key acts as the person who made it.
"""

from plane.api.views.base import BaseAPIView
from plane.blueprints.views import BlueprintDetailEndpoint, BlueprintListEndpoint, BlueprintUseEndpoint


class BlueprintListAPIEndpoint(BaseAPIView):
    get = BlueprintListEndpoint.get


class BlueprintDetailAPIEndpoint(BaseAPIView):
    get = BlueprintDetailEndpoint.get


class BlueprintCreateBoardAPIEndpoint(BaseAPIView):
    post = BlueprintUseEndpoint.post
