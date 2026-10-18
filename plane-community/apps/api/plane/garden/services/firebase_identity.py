# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

from dataclasses import dataclass
import logging
import os
from typing import Any

import firebase_admin
from firebase_admin import auth, firestore


logger = logging.getLogger("plane.garden.firebase")
_FIREBASE_APP_NAME = "garden-firebase"


class GardenIdentityError(Exception):
    """Raised when a Firebase principal cannot be trusted for Garden Work."""


@dataclass(frozen=True)
class GardenFirebasePrincipal:
    uid: str
    email: str | None
    email_verified: bool
    display_name: str
    first_name: str
    last_name: str
    photo_url: str
    roles: tuple[str, ...]
    capabilities: tuple[str, ...]
    organization_role: str | None = None
    access_version: int = 0
    work_projection: dict[str, Any] | None = None
    denied_permissions: tuple[str, ...] = ()
    person_id: str | None = None
    preferred_name: str = ""

    @property
    def can_read_work(self) -> bool:
        # accessProfiles/{uid} is canonical for organizational role. A Garden
        # superuser receives every capability unless that capability is denied,
        # so a missing/stale projection must not deadlock first-time Work bootstrap.
        if self.organization_role == "superuser" and "work.read" not in self.denied_permissions:
            return True
        if self.work_projection is not None:
            workspace_role = self.work_projection.get("workspaceRole")
            if workspace_role in (15, 20):
                return True
            projects = self.work_projection.get("projects")
            return isinstance(projects, list) and any(isinstance(project, dict) and project.get("readable") is True for project in projects)
        return "work.read" in self.capabilities

    @property
    def can_admin_work(self) -> bool:
        if self.organization_role == "superuser" and "work.admin" not in self.denied_permissions:
            return True
        if self.work_projection is not None:
            return self.work_projection.get("workspaceRole") == 20
        return "work.admin" in self.capabilities


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _denied_permissions(access_profile: dict[str, Any]) -> tuple[str, ...]:
    denies = access_profile.get("denies")
    if not isinstance(denies, list):
        return ()
    permissions: list[str] = []
    for deny in denies:
        if not isinstance(deny, dict):
            continue
        permission = deny.get("permission")
        if isinstance(permission, str) and permission:
            permissions.append(permission)
    return tuple(dict.fromkeys(permissions))


def _firebase_app():
    try:
        return firebase_admin.get_app(_FIREBASE_APP_NAME)
    except ValueError:
        project_id = os.environ.get("GARDEN_FIREBASE_PROJECT_ID", "").strip()
        if not project_id:
            raise GardenIdentityError("GARDEN_FIREBASE_PROJECT_ID is not configured")
        return firebase_admin.initialize_app(options={"projectId": project_id}, name=_FIREBASE_APP_NAME)


def _firestore_document(collection: str, uid: str, app, *, fail_closed: bool = False) -> dict[str, Any]:
    try:
        snapshot = firestore.client(app=app).collection(collection).document(uid).get()
        if snapshot.exists:
            data = snapshot.to_dict()
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Unable to read Garden Firestore %s for %s: %s", collection, uid, type(exc).__name__)
        if fail_closed:
            raise GardenIdentityError(f"Unable to verify Garden {collection} state") from exc
    return {}


def _firestore_profile(uid: str, app) -> dict[str, Any]:
    """Resolve the canonical Garden person behind a Firebase account.

    `users/{uid}` is the auth/account projection. `people/{personId}` is the CRM
    source of truth for a human's name. Work used to read only the user projection,
    which meant accounts whose Firebase Auth record had no display name appeared as
    `firebase-<uid>`. Resolve the account -> person link first, then let People win
    for human-facing identity fields while keeping Firebase Auth authoritative for
    sign-in email.
    """
    if os.environ.get("GARDEN_FIRESTORE_PROFILE_SYNC", "1") != "1":
        return {}

    user_profile = _firestore_document("users", uid, app)
    person_id = _clean_string(user_profile.get("personId")) or uid
    person_profile = _firestore_document("people", person_id, app)

    first_name = _clean_string(person_profile.get("firstName")) or _clean_string(user_profile.get("firstName"))
    last_name = _clean_string(person_profile.get("lastName")) or _clean_string(user_profile.get("lastName"))
    preferred_name = _clean_string(person_profile.get("preferredName")) or _clean_string(user_profile.get("preferredName"))
    person_display_name = " ".join(part for part in (preferred_name or first_name, last_name) if part).strip()
    display_name = person_display_name or _clean_string(user_profile.get("displayName"))

    photo_url = (
        _clean_string(person_profile.get("photoURL"))
        or _clean_string(person_profile.get("profileImg"))
        or _clean_string(person_profile.get("avatarUrl"))
        or _clean_string(user_profile.get("photoURL"))
        or _clean_string(user_profile.get("profileImg"))
    )

    # Return a deliberately small merged identity projection instead of leaking
    # arbitrary People CRM fields into the Work identity bridge.
    return {
        "personId": person_id,
        "firstName": first_name,
        "lastName": last_name,
        "preferredName": preferred_name,
        "displayName": display_name,
        "photoURL": photo_url,
    }


def _firestore_work_projection(uid: str, app) -> dict[str, Any] | None:
    data = _firestore_document("workAccessProjections", uid, app, fail_closed=True)
    return data or None


def _access_version(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


def _identity_fields(uid: str, user_record, profile: dict[str, Any], decoded: dict[str, Any] | None = None) -> dict[str, Any]:
    decoded = decoded or {}
    email = getattr(user_record, "email", None) or decoded.get("email")
    email = email.strip().lower() if isinstance(email, str) and email.strip() else None

    first_name = _clean_string(profile.get("firstName")) or _clean_string(decoded.get("given_name"))
    last_name = _clean_string(profile.get("lastName")) or _clean_string(decoded.get("family_name"))
    preferred_name = _clean_string(profile.get("preferredName"))
    display_name = _clean_string(profile.get("displayName"))
    if not display_name:
        display_name = _clean_string(getattr(user_record, "display_name", None)) or _clean_string(decoded.get("name"))
    if not display_name:
        display_name = " ".join(part for part in (preferred_name or first_name, last_name) if part).strip()

    photo_url = (
        _clean_string(profile.get("photoURL"))
        or _clean_string(getattr(user_record, "photo_url", None))
        or _clean_string(decoded.get("picture"))
    )
    person_id = _clean_string(profile.get("personId")) or uid

    return {
        "uid": uid,
        "email": email,
        "email_verified": bool(decoded.get("email_verified") or getattr(user_record, "email_verified", False)),
        "display_name": display_name,
        "first_name": first_name,
        "last_name": last_name,
        "preferred_name": preferred_name,
        "photo_url": photo_url,
        "person_id": person_id,
    }


def load_firebase_profile(uid: str) -> GardenFirebasePrincipal:
    """Load trusted Garden identity fields for an already-linked Work account.

    This server-to-server path is used by the Work integration API when a Garden
    People profile changes. It intentionally does not grant access or provision a
    new Work user; authorization still comes from the access projection/session
    bridge. It only refreshes identity for an existing Firebase<->Plane link.
    """
    if not uid:
        raise GardenIdentityError("Firebase UID is required")
    app = _firebase_app()
    try:
        user_record = auth.get_user(uid, app=app)
        if user_record.disabled:
            raise GardenIdentityError("Firebase user is disabled")
    except GardenIdentityError:
        raise
    except Exception as exc:
        logger.warning("Firebase profile lookup failed for %s: %s", uid, type(exc).__name__)
        raise GardenIdentityError("Firebase profile lookup failed") from exc

    profile = _firestore_profile(uid, app)
    fields = _identity_fields(uid, user_record, profile)
    return GardenFirebasePrincipal(
        uid=uid,
        email=fields["email"],
        email_verified=fields["email_verified"],
        display_name=fields["display_name"],
        first_name=fields["first_name"],
        last_name=fields["last_name"],
        photo_url=fields["photo_url"],
        roles=(),
        capabilities=(),
        person_id=fields["person_id"],
        preferred_name=fields["preferred_name"],
    )


def verify_firebase_id_token(raw_token: str) -> GardenFirebasePrincipal:
    if not raw_token:
        raise GardenIdentityError("Firebase ID token is required")

    app = _firebase_app()
    project_id = os.environ.get("GARDEN_FIREBASE_PROJECT_ID", "").strip()
    try:
        decoded = auth.verify_id_token(raw_token, app=app, check_revoked=True)
        uid = decoded.get("uid") or decoded.get("sub")
        if not isinstance(uid, str) or not uid:
            raise GardenIdentityError("Firebase token has no UID")
        if decoded.get("aud") != project_id:
            raise GardenIdentityError("Firebase token audience does not match Garden project")
        user_record = auth.get_user(uid, app=app)
        if user_record.disabled:
            raise GardenIdentityError("Firebase user is disabled")
    except GardenIdentityError:
        raise
    except Exception as exc:
        logger.warning("Firebase token verification failed: %s", type(exc).__name__)
        raise GardenIdentityError("Firebase token verification failed") from exc

    roles = _string_tuple(decoded.get("roles"))
    capabilities = _string_tuple(decoded.get("capabilities"))
    profile = _firestore_profile(uid, app)
    access_profile = _firestore_document("accessProfiles", uid, app, fail_closed=True)
    work_projection = _firestore_work_projection(uid, app)
    fields = _identity_fields(uid, user_record, profile, decoded)
    organization_role = decoded.get("organizationRole") if isinstance(decoded.get("organizationRole"), str) else None
    access_version = _access_version(decoded.get("accessVersion"))
    denied_permissions: tuple[str, ...] = ()
    if access_profile:
        # The live Admin resolver and Work federation must agree on the same
        # canonical record instead of relying on potentially lagging token claims.
        profile_role = access_profile.get("organizationRole")
        if isinstance(profile_role, str) and profile_role:
            organization_role = profile_role
        denied_permissions = _denied_permissions(access_profile)
        current_access_version = _access_version(access_profile.get("accessVersion"))
        if access_version != current_access_version:
            raise GardenIdentityError("Firebase token access version is stale")
        if work_projection is not None and _access_version(work_projection.get("accessVersion")) != current_access_version:
            raise GardenIdentityError("Garden Work access projection is stale")

    return GardenFirebasePrincipal(
        uid=uid,
        email=fields["email"],
        email_verified=fields["email_verified"],
        display_name=fields["display_name"],
        first_name=fields["first_name"],
        last_name=fields["last_name"],
        photo_url=fields["photo_url"],
        roles=roles,
        capabilities=capabilities,
        organization_role=organization_role,
        access_version=access_version,
        work_projection=work_projection,
        denied_permissions=denied_permissions,
        person_id=fields["person_id"],
        preferred_name=fields["preferred_name"],
    )
