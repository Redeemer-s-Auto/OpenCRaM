# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os
from pathlib import Path

from django.db import connection
from django.http import JsonResponse
from django.views import View


class GardenWorkHealthView(View):
    """Minimal readiness endpoint for the self-hosted Garden Work stack."""

    http_method_names = ["get", "head"]

    def get(self, request, *args, **kwargs):
        credential_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        checks = {
            "gardenAuth": os.environ.get("GARDEN_AUTH_ENABLED", "0") == "1",
            "firebaseProject": bool(os.environ.get("GARDEN_FIREBASE_PROJECT_ID", "").strip()),
            "firebaseCredentials": bool(credential_path) and Path(credential_path).is_file(),
            "workspaceSlug": bool(os.environ.get("GARDEN_WORKSPACE_SLUG", "").strip()),
        }

        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                checks["database"] = cursor.fetchone() == (1,)
        except Exception:
            checks["database"] = False

        ready = all(checks.values())
        return JsonResponse(
            {
                "ok": ready,
                "service": "garden-work",
                "checks": checks,
            },
            status=200 if ready else 503,
        )

    def head(self, request, *args, **kwargs):
        response = self.get(request, *args, **kwargs)
        response.content = b""
        return response
