# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from plane.db.models import Profile, User, Workspace, WorkspaceMember
from plane.db.models.session import Session
from plane.garden.models import GardenExternalIdentity
from plane.garden.services.access_projection import apply_work_projection
from plane.garden.services.firebase_identity import (
    GardenFirebasePrincipal,
    GardenIdentityError,
    load_firebase_profile,
)
from plane.garden.services.project_policy import harden_garden_workspace_projects
from plane.license.models import Instance
from plane.utils.cache import invalidate_cache_directly


FIREBASE_PROVIDER = "firebase"
PLANE_ROLE_ADMIN = 20
PLANE_ROLE_MEMBER = 15


def _internal_email(uid: str) -> str:
    return f"firebase-{uid}@garden.invalid".lower()


def _safe_email(principal: GardenFirebasePrincipal) -> str:
    return principal.email or _internal_email(principal.uid)


def _safe_display_name(principal: GardenFirebasePrincipal) -> str:
    if principal.display_name.strip():
        return principal.display_name.strip()
    full_name = " ".join(part.strip() for part in (principal.first_name, principal.last_name) if part and part.strip()).strip()
    if full_name:
        return full_name
    if principal.email and "@" in principal.email:
        local = principal.email.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ").strip()
        if local:
            return " ".join(part.capitalize() for part in local.split())
    # Never expose `firebase-<uid>` as a human-facing fallback.
    return "Garden User"


def _assert_user_can_be_federated(user: User) -> None:
    if user.is_bot:
        raise GardenIdentityError("Internal Plane bot accounts cannot be linked to Firebase identities")
    if not user.is_active and user.last_logout_time is not None:
        raise GardenIdentityError("Deactivated Plane account cannot be reactivated by Firebase sign-in")


def revoke_work_sessions(firebase_uid: str) -> int:
    """Delete every Plane session belonging to one linked Firebase identity.

    Plane stores the authenticated user id alongside each database-backed
    session. That lets Garden invalidate desktop and mobile Work sessions at
    once without knowing or transporting browser cookie values.
    """
    identity = GardenExternalIdentity.objects.select_related("user").filter(
        provider=FIREBASE_PROVIDER,
        external_id=firebase_uid,
    ).first()
    if identity is None:
        return 0
    deleted, _ = Session.objects.filter(user_id=str(identity.user_id)).delete()
    return int(deleted)


def _sync_user(user: User, principal: GardenFirebasePrincipal) -> User:
    _assert_user_can_be_federated(user)
    desired_email = _safe_email(principal)
    changed_fields: list[str] = []

    if desired_email != user.email and not User.objects.exclude(pk=user.pk).filter(email=desired_email).exists():
        user.email = desired_email
        changed_fields.append("email")

    # Garden People is authoritative for human-facing identity. Only replace a
    # name component when Garden has a value so a temporary missing profile does
    # not erase a previously synchronized identity.
    if principal.first_name and principal.first_name != user.first_name:
        user.first_name = principal.first_name
        changed_fields.append("first_name")
    if principal.last_name and principal.last_name != user.last_name:
        user.last_name = principal.last_name
        changed_fields.append("last_name")
    desired_display_name = _safe_display_name(principal)
    if desired_display_name != user.display_name:
        user.display_name = desired_display_name
        changed_fields.append("display_name")
    if principal.photo_url and principal.photo_url != user.avatar:
        user.avatar = principal.photo_url
        changed_fields.append("avatar")
    if user.is_email_verified != principal.email_verified:
        user.is_email_verified = principal.email_verified
        changed_fields.append("is_email_verified")
    if not user.is_password_autoset:
        user.is_password_autoset = True
        changed_fields.append("is_password_autoset")
    if not user.is_managed:
        user.is_managed = True
        changed_fields.append("is_managed")
    if not user.is_active:
        user.is_active = True
        changed_fields.append("is_active")
    if user.last_login_medium != FIREBASE_PROVIDER:
        user.last_login_medium = FIREBASE_PROVIDER
        changed_fields.append("last_login_medium")
    user.last_active = timezone.now()
    changed_fields.append("last_active")
    user.save(update_fields=[*dict.fromkeys(changed_fields), "updated_at"])

    profile, _ = Profile.objects.get_or_create(user=user)
    profile_changed = []
    if not profile.is_onboarded:
        profile.is_onboarded = True
        profile_changed.append("is_onboarded")
    if not profile.is_tour_completed:
        profile.is_tour_completed = True
        profile_changed.append("is_tour_completed")
    if not profile.is_navigation_tour_completed:
        profile.is_navigation_tour_completed = True
        profile_changed.append("is_navigation_tour_completed")
    if profile_changed:
        profile.save(update_fields=[*profile_changed, "updated_at"])
    return user


def _create_user(principal: GardenFirebasePrincipal) -> User:
    user = User(
        email=_safe_email(principal),
        username=uuid.uuid4().hex,
        first_name=principal.first_name,
        last_name=principal.last_name,
        display_name=_safe_display_name(principal),
        avatar=principal.photo_url,
        is_email_verified=principal.email_verified,
        is_password_autoset=True,
        is_managed=True,
        is_active=True,
        last_login_medium=FIREBASE_PROVIDER,
    )
    user.set_unusable_password()
    user.save()
    Profile.objects.get_or_create(user=user)
    return user


def _resolve_user(principal: GardenFirebasePrincipal) -> User:
    identity = (
        GardenExternalIdentity.objects.select_for_update()
        .select_related("user")
        .filter(provider=FIREBASE_PROVIDER, external_id=principal.uid)
        .first()
    )
    if identity:
        identity.last_synced_at = timezone.now()
        identity.save(update_fields=["last_synced_at", "updated_at"])
        return _sync_user(identity.user, principal)

    user = User.objects.filter(email=principal.email).first() if principal.email else None
    if user:
        _assert_user_can_be_federated(user)
        if GardenExternalIdentity.objects.filter(provider=FIREBASE_PROVIDER, user=user).exclude(external_id=principal.uid).exists():
            raise GardenIdentityError("Plane user is already linked to a different Firebase identity")
    else:
        user = _create_user(principal)
    try:
        GardenExternalIdentity.objects.create(
            provider=FIREBASE_PROVIDER,
            external_id=principal.uid,
            user=user,
            last_synced_at=timezone.now(),
        )
    except IntegrityError as exc:
        raise GardenIdentityError("Concurrent Firebase identity provisioning conflict") from exc
    return _sync_user(user, principal)


@transaction.atomic
def sync_linked_identity(firebase_uid: str) -> tuple[User, GardenFirebasePrincipal]:
    """Refresh an existing Plane user from canonical Firebase + People identity.

    This never creates a new Plane account and never grants Work access. It is
    safe for profile-change webhooks because the Firebase UID must already be
    linked through `GardenExternalIdentity` by the normal authenticated login
    flow.
    """
    identity = (
        GardenExternalIdentity.objects.select_for_update()
        .select_related("user")
        .filter(provider=FIREBASE_PROVIDER, external_id=firebase_uid)
        .first()
    )
    if identity is None:
        raise GardenIdentityError("Firebase identity has not been provisioned in Garden Work")
    principal = load_firebase_profile(firebase_uid)
    user = _sync_user(identity.user, principal)
    identity.last_synced_at = timezone.now()
    identity.save(update_fields=["last_synced_at", "updated_at"])
    return user, principal


def _get_or_create_workspace(user: User, principal: GardenFirebasePrincipal) -> Workspace:
    slug = os.environ.get("GARDEN_WORKSPACE_SLUG", "the-garden").strip() or "the-garden"
    workspace = Workspace.objects.filter(slug=slug).first()
    if workspace:
        return workspace
    if os.environ.get("GARDEN_WORKSPACE_BOOTSTRAP", "0") != "1":
        raise GardenIdentityError("Managed Garden workspace has not been bootstrapped")
    if not principal.can_admin_work:
        raise GardenIdentityError("Only a Garden Work administrator can bootstrap the workspace")
    return Workspace.objects.create(
        name=os.environ.get("GARDEN_WORKSPACE_NAME", "The Garden").strip() or "The Garden",
        slug=slug,
        owner=user,
        timezone=os.environ.get("GARDEN_WORKSPACE_TIMEZONE", "America/Chicago").strip() or "America/Chicago",
    )


def _ensure_garden_instance_ready(principal: GardenFirebasePrincipal) -> None:
    """Finish Plane's instance bootstrap without exposing Plane god-mode.

    Garden owns identity and administration, so the first approved Garden Work
    administrator replaces Plane's native instance-setup flow. This is also
    intentionally idempotent so an already-created Garden workspace can repair
    an instance that is still advertising `is_setup_done = false`.
    """
    if os.environ.get("GARDEN_WORKSPACE_BOOTSTRAP", "0") != "1" or not principal.can_admin_work:
        return
    instance = Instance.objects.select_for_update().first()
    if instance is None:
        return

    changed_fields: list[str] = []
    desired_name = os.environ.get("GARDEN_WORKSPACE_NAME", "The Garden").strip() or "The Garden"
    desired_domain = os.environ.get("GARDEN_WORK_URL", "").strip()

    if not instance.is_setup_done:
        instance.is_setup_done = True
        changed_fields.append("is_setup_done")
    if not instance.is_signup_screen_visited:
        instance.is_signup_screen_visited = True
        changed_fields.append("is_signup_screen_visited")
    if instance.instance_name != desired_name:
        instance.instance_name = desired_name
        changed_fields.append("instance_name")
    if desired_domain and instance.domain != desired_domain:
        instance.domain = desired_domain
        changed_fields.append("domain")
    if instance.is_telemetry_enabled:
        instance.is_telemetry_enabled = False
        changed_fields.append("is_telemetry_enabled")
    if instance.is_support_required:
        instance.is_support_required = False
        changed_fields.append("is_support_required")
    if changed_fields:
        instance.save(update_fields=[*changed_fields, "updated_at"])
        # /api/instances/ is cached globally for two hours. Without explicit
        # invalidation, the browser can keep seeing is_setup_done=false even
        # after Garden has finalized the row in Postgres.
        transaction.on_commit(lambda: invalidate_cache_directly(path="/api/instances/", user=False))


@transaction.atomic
def reconcile_principal(principal: GardenFirebasePrincipal) -> tuple[User, Workspace, WorkspaceMember]:
    if not principal.can_read_work:
        raise GardenIdentityError("Garden user does not have projected Work access")
    user = _resolve_user(principal)
    workspace = _get_or_create_workspace(user, principal)
    _ensure_garden_instance_ready(principal)
    harden_garden_workspace_projects(workspace)
    if principal.work_projection is not None:
        apply_work_projection(principal.uid, user, workspace, principal.work_projection)
        membership = WorkspaceMember.objects.filter(
            workspace=workspace,
            member=user,
            deleted_at__isnull=True,
            is_active=True,
        ).first()
        if membership is None:
            raise GardenIdentityError("Garden projection does not grant an interactive Work session")
        # accessProfiles/{uid} is the canonical Garden authorization record. A
        # stale or manually-created projection must never demote a canonical
        # Garden superuser to a lower Plane workspace role. Reconcile that role
        # on every Firebase session exchange so existing sessions self-heal.
        if principal.can_admin_work and membership.role != PLANE_ROLE_ADMIN:
            membership.role = PLANE_ROLE_ADMIN
            membership.save(update_fields=["role", "updated_at"])
    else:
        desired_role = PLANE_ROLE_ADMIN if principal.can_admin_work else PLANE_ROLE_MEMBER
        membership = WorkspaceMember.objects.filter(
            workspace=workspace,
            member=user,
            deleted_at__isnull=True,
        ).first()
        if membership is None:
            membership = WorkspaceMember.objects.create(
                workspace=workspace,
                member=user,
                role=desired_role,
                is_active=True,
            )
        else:
            changed_fields = []
            if membership.role != desired_role:
                membership.role = desired_role
                changed_fields.append("role")
            if not membership.is_active:
                membership.is_active = True
                changed_fields.append("is_active")
            if changed_fields:
                membership.save(update_fields=[*changed_fields, "updated_at"])
    profile = user.profile
    if profile.last_workspace_id != workspace.id:
        profile.last_workspace_id = workspace.id
        profile.save(update_fields=["last_workspace_id", "updated_at"])
    return user, workspace, membership


@transaction.atomic
def deactivate_work_membership(firebase_uid: str) -> None:
    identity = GardenExternalIdentity.objects.select_related("user").filter(
        provider=FIREBASE_PROVIDER,
        external_id=firebase_uid,
    ).first()
    if not identity:
        return
    slug = os.environ.get("GARDEN_WORKSPACE_SLUG", "the-garden").strip() or "the-garden"
    membership = WorkspaceMember.objects.filter(
        workspace__slug=slug,
        member=identity.user,
        deleted_at__isnull=True,
        is_active=True,
    ).first()
    if membership:
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
    revoke_work_sessions(firebase_uid)
