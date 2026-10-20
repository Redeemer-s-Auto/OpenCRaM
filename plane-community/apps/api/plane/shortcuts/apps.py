# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class ShortcutsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plane.shortcuts"
    verbose_name = "Card shortcuts and backlinks"

    def ready(self):
        # Keeps the backlink index in step with every saved card body.
        from . import signals  # noqa: F401
