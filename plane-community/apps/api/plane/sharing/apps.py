# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.apps import AppConfig


class SharingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plane.sharing"
    verbose_name = "Item sharing rules"
