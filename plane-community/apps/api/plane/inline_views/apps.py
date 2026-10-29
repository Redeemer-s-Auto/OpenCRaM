# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class InlineViewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plane.inline_views"
    verbose_name = "Inline views"
