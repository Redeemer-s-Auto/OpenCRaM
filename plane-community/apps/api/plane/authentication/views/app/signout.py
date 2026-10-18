# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import os

# Django imports
from django.views import View
from django.contrib.auth import logout
from django.http import HttpResponseRedirect
from django.utils import timezone

# Module imports
from plane.authentication.utils.host import user_ip, base_host
from plane.db.models import User


def _post_logout_destination(request):
    if os.environ.get("GARDEN_AUTH_ENABLED", "0") == "1":
        garden_admin_url = os.environ.get("GARDEN_ADMIN_URL", "").strip().rstrip("/")
        if garden_admin_url:
            return f"{garden_admin_url}/work"
    return base_host(request=request, is_app=True)


class SignOutAuthEndpoint(View):
    def post(self, request):
        destination = _post_logout_destination(request)
        try:
            user = User.objects.get(pk=request.user.id)
            user.last_logout_ip = user_ip(request=request)
            user.last_logout_time = timezone.now()
            user.save()
            # End only the Plane session. The Garden Firebase session intentionally remains active.
            logout(request)
            return HttpResponseRedirect(destination)
        except Exception:
            return HttpResponseRedirect(destination)
