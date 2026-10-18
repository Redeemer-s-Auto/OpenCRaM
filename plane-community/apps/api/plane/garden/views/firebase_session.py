# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os
from urllib.parse import urlsplit

from django.http import HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from plane.authentication.utils.login import user_login
from plane.garden.services.firebase_identity import GardenIdentityError, verify_firebase_id_token
from plane.garden.services.provisioning import deactivate_work_membership, reconcile_principal, revoke_work_sessions
from plane.utils.ip_address import get_client_ip


def _allowed_origins() -> set[str]:
    # Prefer a Garden-specific override when an operator needs one, otherwise use
    # Plane's CORS origin list so there is one production source of truth.
    raw = os.environ.get("GARDEN_AUTH_ALLOWED_ORIGINS") or os.environ.get("CORS_ALLOWED_ORIGINS", "")
    return {origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()}


def _request_origin(request) -> str:
    origin = request.headers.get("Origin", "").strip().rstrip("/")
    if origin:
        return origin

    # Top-level form navigations normally include Origin on POST. Referer is a
    # conservative fallback for browsers that omit Origin on navigational POSTs.
    referer = request.headers.get("Referer", "").strip()
    if not referer:
        return ""
    try:
        parsed = urlsplit(referer)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _bearer_token(request) -> str:
    value = request.headers.get("Authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def _request_guard(request):
    if os.environ.get("GARDEN_AUTH_ENABLED", "0") != "1":
        return JsonResponse({"ok": False, "error": "garden_auth_disabled"}, status=404)

    allowed_origins = _allowed_origins()
    if not allowed_origins:
        return JsonResponse({"ok": False, "error": "garden_auth_not_configured"}, status=503)

    if _request_origin(request) not in allowed_origins:
        return JsonResponse({"ok": False, "error": "origin_not_allowed"}, status=403)

    return None


def _establish_session(request, token: str, *, missing_token_error: str):
    if not token:
        return None, JsonResponse({"ok": False, "error": missing_token_error}, status=401)

    try:
        principal = verify_firebase_id_token(token)
        if not principal.can_read_work:
            deactivate_work_membership(principal.uid)
            return None, JsonResponse({"ok": False, "error": "work_access_denied"}, status=403)

        user, workspace, membership = reconcile_principal(principal)
    except GardenIdentityError as exc:
        return None, JsonResponse({"ok": False, "error": "firebase_auth_failed", "detail": str(exc)}, status=401)

    now = timezone.now()
    user.last_login_medium = "firebase"
    user.last_login_time = now
    user.last_active = now
    user.last_login_ip = get_client_ip(request=request)
    user.last_login_uagent = request.META.get("HTTP_USER_AGENT", "")
    user.save(
        update_fields=[
            "last_login_medium",
            "last_login_time",
            "last_active",
            "last_login_ip",
            "last_login_uagent",
            "updated_at",
        ]
    )

    user_login(request=request, user=user, is_app=True)

    # Keep the trusted Garden authorization result with the Plane session.
    # This is not sourced from the browser: it is written only after the
    # Firebase token, canonical access profile, and projection are verified
    # server-side above. It lets managed-workspace authorization recover from
    # stale Plane membership rows without weakening non-Garden workspaces.
    request.session["garden_work_firebase_uid"] = principal.uid
    request.session["garden_work_workspace_slug"] = workspace.slug
    request.session["garden_work_workspace_role"] = int(membership.role)
    request.session["garden_work_access_version"] = int(principal.access_version)
    request.session.save()

    return (principal, user, workspace, membership), None


@method_decorator(csrf_exempt, name="dispatch")
class FirebaseSessionExchangeView(View):
    http_method_names = ["post", "options"]

    def options(self, request, *args, **kwargs):
        return JsonResponse({"ok": True})

    def post(self, request, *args, **kwargs):
        guard_error = _request_guard(request)
        if guard_error is not None:
            return guard_error

        result, auth_error = _establish_session(
            request,
            _bearer_token(request),
            missing_token_error="missing_bearer_token",
        )
        if auth_error is not None:
            return auth_error

        _, _, workspace, membership = result
        response = JsonResponse(
            {
                "ok": True,
                "workspaceSlug": workspace.slug,
                "role": membership.role,
                "destination": f"/{workspace.slug}/",
            }
        )
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(csrf_exempt, name="dispatch")
class FirebaseSessionRevokeView(View):
    """Revoke every Work session for the currently authenticated Garden user.

    Garden calls this immediately before Firebase sign-out. Because revocation
    is keyed by the verified Firebase UID rather than a browser cookie, it logs
    the person out of Work on every desktop/mobile session at once.
    """

    http_method_names = ["post", "options"]

    def options(self, request, *args, **kwargs):
        return JsonResponse({"ok": True})

    def post(self, request, *args, **kwargs):
        guard_error = _request_guard(request)
        if guard_error is not None:
            return guard_error

        token = _bearer_token(request)
        if not token:
            return JsonResponse({"ok": False, "error": "missing_bearer_token"}, status=401)

        try:
            principal = verify_firebase_id_token(token)
        except GardenIdentityError as exc:
            return JsonResponse({"ok": False, "error": "firebase_auth_failed", "detail": str(exc)}, status=401)

        revoked = revoke_work_sessions(principal.uid)
        response = JsonResponse({"ok": True, "revokedSessions": revoked})
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(csrf_exempt, name="dispatch")
class FirebaseMobileLaunchView(View):
    """Create the Work session in a top-level browser context.

    Mobile Safari blocks the cross-site iframe session used by the desktop Admin
    shell. Garden Admin therefore submits a Firebase ID token in a top-level POST
    to this endpoint. The token never appears in the URL; after verification the
    response sets the normal Work session cookie as first-party state and
    redirects directly into the managed workspace.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        guard_error = _request_guard(request)
        if guard_error is not None:
            return guard_error

        result, auth_error = _establish_session(
            request,
            str(request.POST.get("firebase_token", "")).strip(),
            missing_token_error="missing_firebase_token",
        )
        if auth_error is not None:
            return auth_error

        _, _, workspace, _ = result
        response = HttpResponseRedirect(f"/{workspace.slug}/")
        response["Cache-Control"] = "no-store"
        return response
