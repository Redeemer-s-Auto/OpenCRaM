# SPDX-License-Identifier: AGPL-3.0-only

from types import SimpleNamespace

import pytest
from django.utils import timezone

from plane.app.permissions import ROLE, allow_permission
from plane.db.models import User, WorkspaceMember
from plane.garden.models import GardenExternalIdentity
from plane.garden.services.firebase_identity import GardenFirebasePrincipal, GardenIdentityError, _identity_fields
from plane.garden.services.provisioning import (
    PLANE_ROLE_ADMIN,
    PLANE_ROLE_MEMBER,
    reconcile_principal,
    sync_linked_identity,
)
from plane.license.models import Instance


def principal(
    uid="firebase-1",
    email="staff@example.com",
    capabilities=("work.read", "work.manage", "work.admin"),
    organization_role=None,
    work_projection=None,
    display_name="Garden Staff",
    first_name="Garden",
    last_name="Staff",
    photo_url="",
    person_id="person-1",
    preferred_name="",
):
    return GardenFirebasePrincipal(
        uid=uid,
        email=email,
        email_verified=True,
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        photo_url=photo_url,
        roles=("staff",),
        capabilities=tuple(capabilities),
        organization_role=organization_role,
        work_projection=work_projection,
        person_id=person_id,
        preferred_name=preferred_name,
    )


@pytest.mark.django_db
@pytest.mark.unit
def test_first_admin_login_bootstraps_workspace_identity_and_instance(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    monkeypatch.setenv("GARDEN_WORKSPACE_SLUG", "the-garden")
    monkeypatch.setenv("GARDEN_WORKSPACE_NAME", "The Garden")
    monkeypatch.setenv("GARDEN_WORK_URL", "https://work.aphrisoft.com")
    instance = Instance.objects.create(
        instance_name="Plane Community Edition",
        instance_id="garden-test-instance",
        current_version="v1-test",
        latest_version="v1-test",
        last_checked_at=timezone.now(),
    )

    user, workspace, membership = reconcile_principal(principal())

    instance.refresh_from_db()
    assert workspace.slug == "the-garden"
    assert workspace.owner_id == user.id
    assert membership.role == PLANE_ROLE_ADMIN
    assert membership.is_active is True
    assert GardenExternalIdentity.objects.get(external_id="firebase-1").user_id == user.id
    assert user.profile.is_onboarded is True
    assert user.is_managed is True
    assert instance.is_setup_done is True
    assert instance.is_signup_screen_visited is True
    assert instance.instance_name == "The Garden"
    assert instance.domain == "https://work.aphrisoft.com"
    assert instance.is_telemetry_enabled is False
    assert instance.is_support_required is False


@pytest.mark.django_db
@pytest.mark.unit
def test_repeat_login_is_idempotent(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")

    first_user, _, first_membership = reconcile_principal(principal())
    second_user, _, second_membership = reconcile_principal(principal())

    assert first_user.id == second_user.id
    assert first_membership.id == second_membership.id
    assert GardenExternalIdentity.objects.filter(external_id="firebase-1").count() == 1


@pytest.mark.django_db
@pytest.mark.unit
def test_repeat_login_refreshes_plane_identity_from_garden(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    user, _, _ = reconcile_principal(principal())
    assert user.display_name == "Garden Staff"

    user, _, _ = reconcile_principal(
        principal(
            display_name="TJ Asaday",
            first_name="TJ",
            last_name="Asaday",
            photo_url="https://example.test/tj.jpg",
        )
    )
    user.refresh_from_db()
    assert user.display_name == "TJ Asaday"
    assert user.first_name == "TJ"
    assert user.last_name == "Asaday"
    assert user.avatar == "https://example.test/tj.jpg"
    assert "firebase-" not in user.display_name.lower()


@pytest.mark.django_db
@pytest.mark.unit
def test_linked_identity_push_updates_existing_user_without_provisioning(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    user, _, _ = reconcile_principal(principal())
    user.display_name = "Old Work Name"
    user.save(update_fields=["display_name", "updated_at"])

    refreshed = principal(
        capabilities=(),
        display_name="Garden Canonical Name",
        first_name="Garden",
        last_name="Canonical",
        preferred_name="Garden",
    )
    monkeypatch.setattr("plane.garden.services.provisioning.load_firebase_profile", lambda uid: refreshed)

    synced_user, synced_principal = sync_linked_identity("firebase-1")
    assert synced_user.id == user.id
    assert synced_principal.person_id == "person-1"
    assert synced_user.display_name == "Garden Canonical Name"
    assert User.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.unit
def test_linked_identity_push_refuses_unknown_firebase_uid(monkeypatch):
    monkeypatch.setattr(
        "plane.garden.services.provisioning.load_firebase_profile",
        lambda uid: pytest.fail("unlinked identities must fail before Firebase lookup"),
    )
    with pytest.raises(GardenIdentityError, match="has not been provisioned"):
        sync_linked_identity("not-linked")


def test_people_identity_fields_win_over_auth_fallback():
    record = SimpleNamespace(
        email="staff@example.com",
        email_verified=True,
        display_name="Firebase Auth Name",
        photo_url="https://example.test/auth.jpg",
    )
    fields = _identity_fields(
        "firebase-1",
        record,
        {
            "personId": "person-1",
            "firstName": "Keith",
            "lastName": "Asaday",
            "preferredName": "TJ",
            "displayName": "TJ Asaday",
            "photoURL": "https://example.test/people.jpg",
        },
        {"name": "Token Name", "given_name": "Token", "family_name": "User"},
    )
    assert fields["person_id"] == "person-1"
    assert fields["display_name"] == "TJ Asaday"
    assert fields["first_name"] == "Keith"
    assert fields["last_name"] == "Asaday"
    assert fields["preferred_name"] == "TJ"
    assert fields["photo_url"] == "https://example.test/people.jpg"
    assert fields["email"] == "staff@example.com"


@pytest.mark.django_db
@pytest.mark.unit
def test_role_reconciles_from_admin_to_member(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")

    user, _, membership = reconcile_principal(principal())
    assert membership.role == PLANE_ROLE_ADMIN

    _, _, membership = reconcile_principal(
        principal(capabilities=("work.read", "work.manage"))
    )
    membership.refresh_from_db()

    assert membership.role == PLANE_ROLE_MEMBER
    assert membership.member_id == user.id


@pytest.mark.django_db
@pytest.mark.unit
def test_canonical_superuser_repairs_stale_member_projection(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    stale_projection = {
        "accessVersion": 0,
        "workspaceRole": PLANE_ROLE_MEMBER,
        "projectionHash": "a" * 64,
        "managedProjectIds": [],
        "projects": [],
    }

    _, _, membership = reconcile_principal(
        principal(
            capabilities=(),
            organization_role="superuser",
            work_projection=stale_projection,
        )
    )

    membership.refresh_from_db()
    assert membership.role == PLANE_ROLE_ADMIN
    assert membership.is_active is True


@pytest.mark.django_db
@pytest.mark.unit
def test_workspace_owner_is_not_blocked_by_stale_guest_membership(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    user, workspace, membership = reconcile_principal(principal())
    membership.role = ROLE.GUEST.value
    membership.save(update_fields=["role", "updated_at"])

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def protected_workspace_action(_instance, _request, slug):
        return slug

    result = protected_workspace_action(object(), SimpleNamespace(user=user), slug=workspace.slug)
    assert result == workspace.slug


@pytest.mark.django_db
@pytest.mark.unit
def test_existing_deactivated_plane_user_is_not_reactivated(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")

    user = User(email="staff@example.com", username="deactivated")
    user.set_unusable_password()
    user.is_active = False
    user.last_logout_time = timezone.now()
    user.save()

    with pytest.raises(GardenIdentityError):
        reconcile_principal(principal())

    user.refresh_from_db()
    assert user.is_active is False


@pytest.mark.django_db
@pytest.mark.unit
def test_user_without_work_read_is_denied_before_provisioning(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")

    with pytest.raises(GardenIdentityError):
        reconcile_principal(principal(capabilities=()))

    assert WorkspaceMember.objects.count() == 0
    assert GardenExternalIdentity.objects.count() == 0
