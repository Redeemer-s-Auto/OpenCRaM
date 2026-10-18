# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os

from rest_framework import status
from rest_framework.response import Response

from plane.api.views.base import BaseAPIView
from plane.db.models import Workspace
from plane.garden.models import GardenExternalIdentity
from plane.garden.services.access_projection import apply_work_projection, load_work_projection, projection_allows_work
from plane.garden.services.firebase_identity import GardenIdentityError
from plane.garden.services.project_policy import garden_workspace_slug
from plane.garden.services.provisioning import revoke_work_sessions, sync_linked_identity


def _garden_integration_allowed(request) -> bool:
    expected_email = os.environ.get(
        "GARDEN_INTEGRATION_USER_EMAIL",
        "garden-work-integration@garden.invalid",
    ).strip().lower()
    actual_email = str(getattr(request.user, "email", "") or "").strip().lower()
    return bool(expected_email and actual_email == expected_email)


class GardenIdentitySyncEndpoint(BaseAPIView):
    """Refresh one already-provisioned Plane user from Garden People/Firebase.

    The Garden integration API key authenticates the caller. The endpoint never
    creates an account and never grants access; it only refreshes the identity
    behind an existing GardenExternalIdentity link.
    """

    def post(self, request, firebase_uid):
        if os.environ.get("GARDEN_AUTH_ENABLED", "0") != "1":
            return Response({"error": "Garden mode is disabled"}, status=status.HTTP_404_NOT_FOUND)
        if not _garden_integration_allowed(request):
            return Response({"error": "Garden integration principal required"}, status=status.HTTP_403_FORBIDDEN)
        try:
            user, principal = sync_linked_identity(firebase_uid)
        except GardenIdentityError as exc:
            message = str(exc)
            code = status.HTTP_404_NOT_FOUND if "has not been provisioned" in message else status.HTTP_409_CONFLICT
            return Response({"error": message}, status=code)

        return Response(
            {
                "ok": True,
                "firebaseUid": firebase_uid,
                "personId": principal.person_id,
                "planeUserId": str(user.id),
                "displayName": user.display_name,
                "firstName": user.first_name,
                "lastName": user.last_name,
                "avatarUrl": user.avatar or None,
            },
            status=status.HTTP_200_OK,
        )


class GardenAccessProjectionSyncEndpoint(BaseAPIView):
    """Apply one Firebase-owned access projection using the Garden integration API key."""

    def post(self, request, firebase_uid):
        if os.environ.get("GARDEN_AUTH_ENABLED", "0") != "1":
            return Response({"error": "Garden mode is disabled"}, status=status.HTTP_404_NOT_FOUND)
        if not _garden_integration_allowed(request):
            return Response({"error": "Garden integration principal required"}, status=status.HTTP_403_FORBIDDEN)

        identity = GardenExternalIdentity.objects.select_related("user").filter(
            provider="firebase",
            external_id=firebase_uid,
        ).first()
        if identity is None:
            return Response(
                {"error": "Firebase identity has not been provisioned in Garden Work"},
                status=status.HTTP_404_NOT_FOUND,
            )
        workspace = Workspace.objects.filter(slug=garden_workspace_slug()).first()
        if workspace is None:
            return Response({"error": "Garden workspace is missing"}, status=status.HTTP_409_CONFLICT)
        projection = load_work_projection(firebase_uid)
        if projection is None:
            return Response({"error": "Garden access projection is missing"}, status=status.HTTP_409_CONFLICT)

        previous_access_version = int(identity.access_version or 0)

        # Access sync is also an identity reconciliation point. This makes manual
        # and scheduled projection retries repair stale names/avatars in the same
        # server-to-server operation instead of maintaining two divergent users.
        try:
            user, principal = sync_linked_identity(firebase_uid)
        except GardenIdentityError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        result = apply_work_projection(firebase_uid, user, workspace, projection)

        # A browser session must never outlive the Garden permission state that
        # created it. Revoke every existing Work session whenever accessVersion
        # changes, or immediately when the projection removes Work entirely.
        # The next legitimate visit simply performs a fresh Firebase exchange.
        current_access_version = int(result.get("accessVersion") or 0)
        should_revoke_sessions = (
            current_access_version != previous_access_version
            or not projection_allows_work(projection)
        )
        revoked_sessions = revoke_work_sessions(firebase_uid) if should_revoke_sessions else 0

        return Response(
            {
                "ok": True,
                **result,
                "revokedSessions": revoked_sessions,
                "identity": {
                    "personId": principal.person_id,
                    "planeUserId": str(user.id),
                    "displayName": user.display_name,
                },
            },
            status=status.HTTP_200_OK,
        )
