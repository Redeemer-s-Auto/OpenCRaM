# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class RelationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plane.relations"
    verbose_name = "Card relations and rollups"
