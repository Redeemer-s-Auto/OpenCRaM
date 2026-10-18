# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os

from django.apps import AppConfig
from django.conf import settings


class GardenConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plane.garden"
    verbose_name = "Garden Integration"

    def ready(self):
        # Import signal handlers only after Django's app registry is ready.
        from plane.garden import signals  # noqa: F401

        if os.environ.get("GARDEN_AUTH_ENABLED", "0") == "1":
            middleware_path = "plane.garden.middleware.GardenAuthorizationMiddleware"
            middleware = list(settings.MIDDLEWARE)
            if middleware_path not in middleware:
                auth_path = "django.contrib.auth.middleware.AuthenticationMiddleware"
                insert_at = middleware.index(auth_path) + 1 if auth_path in middleware else 0
                middleware.insert(insert_at, middleware_path)
                settings.MIDDLEWARE = middleware
