# SPDX-License-Identifier: AGPL-3.0-only
"""GARDEN_ACCESS_MODE=roles: Work access from a sign-in hub's role and app lists."""

import json
from types import SimpleNamespace

import pytest
from django.http import HttpResponse
from django.test import Client, RequestFactory

from plane.db.models import Project, ProjectNetwork
from plane.garden.middleware import GardenAuthorizationMiddleware
from plane.garden.services import firebase_identity
from plane.garden.services.firebase_identity import (
    GardenFirebasePrincipal,
    GardenIdentityError,
    roles_mode_capabilities,
    verify_firebase_id_token,
)
from plane.garden.services.provisioning import reconcile_principal


@pytest.fixture
def roles_env(monkeypatch):
    monkeypatch.setenv("GARDEN_ACCESS_MODE", "roles")
    monkeypatch.setenv("GARDEN_ROLES_APP_ID", "notes")
    monkeypatch.setenv("GARDEN_ROLES_ADMIN_ROLES", "owner, upperManagement")
    monkeypatch.delenv("GARDEN_ROLES_MEMBER_ROLES", raising=False)


# ---- the pure rule ------------------------------------------------------------------------------


@pytest.mark.unit
def test_app_on_list_opens_work_as_member(roles_env):
    roles, caps = roles_mode_capabilities({"roles": ["hr"], "apps": ["hr", "notes"], "active": True}, {})
    assert roles == ("hr",)
    assert caps == ("work.read",)


@pytest.mark.unit
def test_admin_role_opens_work_as_admin_without_the_app(roles_env):
    _, caps = roles_mode_capabilities({"roles": ["upperManagement"], "apps": [], "active": True}, {})
    assert caps == ("work.read", "work.admin")


@pytest.mark.unit
def test_no_app_and_no_admin_role_gets_nothing(roles_env):
    _, caps = roles_mode_capabilities({"roles": ["member"], "apps": ["hr"], "active": True}, {})
    assert caps == ()


@pytest.mark.unit
def test_inactive_record_gets_nothing_even_for_owner(roles_env):
    _, caps = roles_mode_capabilities({"roles": ["owner"], "apps": ["notes"], "active": False}, {})
    assert caps == ()


@pytest.mark.unit
def test_live_record_wins_over_stale_token_claims(roles_env):
    # The hub removed the app; the old token still carries it.
    record = {"roles": ["member"], "apps": [], "active": True}
    decoded = {"roles": ["member"], "apps": ["notes"]}
    assert roles_mode_capabilities(record, decoded)[1] == ()


@pytest.mark.unit
def test_missing_record_falls_back_to_token_claims(roles_env):
    _, caps = roles_mode_capabilities({}, {"roles": ["member"], "apps": ["notes"]})
    assert caps == ("work.read",)


@pytest.mark.unit
def test_single_legacy_role_string_is_read(roles_env):
    _, caps = roles_mode_capabilities({"role": "owner", "apps": []}, {})
    assert caps == ("work.read", "work.admin")


@pytest.mark.unit
def test_member_roles_open_work_without_the_app(roles_env, monkeypatch):
    monkeypatch.setenv("GARDEN_ROLES_MEMBER_ROLES", "hr")
    _, caps = roles_mode_capabilities({"roles": ["hr"], "apps": []}, {})
    assert caps == ("work.read",)


@pytest.mark.unit
def test_nothing_configured_grants_nothing(monkeypatch):
    monkeypatch.setenv("GARDEN_ACCESS_MODE", "roles")
    for name in ("GARDEN_ROLES_APP_ID", "GARDEN_ROLES_ADMIN_ROLES", "GARDEN_ROLES_MEMBER_ROLES"):
        monkeypatch.delenv(name, raising=False)
    assert roles_mode_capabilities({"roles": ["owner"], "apps": ["notes"]}, {})[1] == ()


@pytest.mark.unit
def test_non_string_entries_are_ignored(roles_env):
    roles, caps = roles_mode_capabilities({"roles": ["hr", 7, None], "apps": [None, "notes"]}, {})
    assert roles == ("hr",)
    assert caps == ("work.read",)


# ---- token verification in roles mode -----------------------------------------------------------


def _prepare(monkeypatch, record, decoded_extra=None):
    monkeypatch.setenv("GARDEN_FIREBASE_PROJECT_ID", "hub-project")
    decoded = {"uid": "hub-user", "aud": "hub-project", "email": "t@example.com", "email_verified": True}
    decoded.update(decoded_extra or {})
    user = SimpleNamespace(disabled=False, email="t@example.com", email_verified=True, display_name="Team Member", photo_url="")
    monkeypatch.setattr(firebase_identity, "_firebase_app", lambda: object())
    monkeypatch.setattr(firebase_identity.auth, "verify_id_token", lambda *a, **k: decoded)
    monkeypatch.setattr(firebase_identity.auth, "get_user", lambda *a, **k: user)
    monkeypatch.setattr(firebase_identity, "_firestore_profile", lambda *a, **k: {})
    reads = []

    def firestore_document(collection, uid, app, **kwargs):
        reads.append((collection, kwargs.get("fail_closed", False)))
        return record if collection == "users" else {}

    monkeypatch.setattr(firebase_identity, "_firestore_document", firestore_document)
    return reads


@pytest.mark.unit
def test_roles_mode_ignores_token_capabilities_and_skips_projection(roles_env, monkeypatch):
    reads = _prepare(
        monkeypatch,
        {"roles": ["member"], "apps": [], "active": True},
        {"capabilities": ["work.read", "work.admin"], "accessVersion": 99},
    )

    principal = verify_firebase_id_token("valid")

    assert principal.capabilities == ()
    assert principal.can_read_work is False
    assert principal.work_projection is None
    # Only the live record is read, and a read failure there must fail closed.
    assert reads == [("users", True)]


@pytest.mark.unit
def test_roles_mode_admin(roles_env, monkeypatch):
    _prepare(monkeypatch, {"roles": ["owner"], "apps": [], "active": True})

    principal = verify_firebase_id_token("valid")

    assert principal.can_read_work is True
    assert principal.can_admin_work is True
    assert principal.roles == ("owner",)


@pytest.mark.unit
def test_roles_mode_record_collection_is_configurable(roles_env, monkeypatch):
    monkeypatch.setenv("GARDEN_ROLES_PROFILE_COLLECTION", "staff")
    reads = _prepare(monkeypatch, {})
    verify_firebase_id_token("valid")
    assert reads == [("staff", True)]


@pytest.mark.unit
def test_roles_mode_record_read_failure_fails_closed(roles_env, monkeypatch):
    _prepare(monkeypatch, {})

    def broken(collection, uid, app, **kwargs):
        raise GardenIdentityError("Unable to verify Garden users state")

    monkeypatch.setattr(firebase_identity, "_firestore_document", broken)
    with pytest.raises(GardenIdentityError):
        verify_firebase_id_token("valid")


@pytest.mark.unit
def test_default_mode_is_unchanged(monkeypatch):
    monkeypatch.delenv("GARDEN_ACCESS_MODE", raising=False)
    _prepare(monkeypatch, {}, {"capabilities": ["work.read"]})
    principal = verify_firebase_id_token("valid")
    assert principal.capabilities == ("work.read",)
    assert principal.can_read_work is True


# ---- board membership managed inside Work -------------------------------------------------------


def _principal(uid, email, capabilities):
    return GardenFirebasePrincipal(
        uid=uid,
        email=email,
        email_verified=True,
        display_name=email.split("@")[0],
        first_name="Team",
        last_name="Member",
        photo_url="",
        roles=(),
        capabilities=tuple(capabilities),
    )


def _workspace(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    monkeypatch.setenv("GARDEN_WORKSPACE_SLUG", "the-garden")
    admin_user, workspace, _ = reconcile_principal(_principal("admin", "admin@example.com", ("work.read", "work.admin")))
    member_user, _, _ = reconcile_principal(_principal("member", "member@example.com", ("work.read",)))
    project = Project.objects.create(
        name="Board", identifier="BOARD", workspace=workspace, network=ProjectNetwork.SECRET.value, created_by=admin_user
    )
    return admin_user, member_user, project


def _member_change(user, project):
    request = RequestFactory().post(
        f"/api/workspaces/the-garden/projects/{project.id}/members/",
        data=json.dumps({"members": []}),
        content_type="application/json",
    )
    request.user = user
    return request


@pytest.mark.django_db
@pytest.mark.unit
def test_roles_mode_lets_work_admins_manage_board_members(roles_env, monkeypatch):
    admin_user, member_user, project = _workspace(monkeypatch)
    middleware = GardenAuthorizationMiddleware(lambda request: HttpResponse(status=204))

    assert middleware(_member_change(admin_user, project)).status_code == 204
    assert middleware(_member_change(member_user, project)).status_code == 403

    # Who may sign in at all still comes only from Firebase.
    workspace_role = RequestFactory().patch(
        f"/api/workspaces/the-garden/members/{member_user.id}/",
        data=json.dumps({"role": 20}),
        content_type="application/json",
    )
    workspace_role.user = admin_user
    assert middleware(workspace_role).status_code == 403


@pytest.mark.django_db
@pytest.mark.unit
def test_projection_mode_still_blocks_board_member_changes(monkeypatch):
    monkeypatch.delenv("GARDEN_ACCESS_MODE", raising=False)
    admin_user, _, project = _workspace(monkeypatch)
    middleware = GardenAuthorizationMiddleware(lambda request: HttpResponse(status=204))
    assert middleware(_member_change(admin_user, project)).status_code == 403


# ---- top-level launch errors go back to the launch page -----------------------------------------


@pytest.mark.django_db
@pytest.mark.contract
def test_launch_failure_redirects_to_launch_url_with_code_only(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://hub.example")
    monkeypatch.setenv("GARDEN_LAUNCH_URL", "https://hub.example/notes")

    from plane.garden.views import firebase_session as view_module

    def reject(_):
        raise GardenIdentityError("secret detail that must not travel")

    monkeypatch.setattr(view_module, "verify_firebase_id_token", reject)

    response = Client().post("/auth/firebase/mobile/", {"firebase_token": "x"}, HTTP_ORIGIN="https://hub.example")

    assert response.status_code == 303
    assert response["Location"] == "https://hub.example/notes?error=firebase_auth_failed"
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
@pytest.mark.contract
def test_launch_denied_redirects_with_access_denied(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://hub.example")
    monkeypatch.setenv("GARDEN_LAUNCH_URL", "https://hub.example/notes")

    from plane.garden.views import firebase_session as view_module

    monkeypatch.setattr(view_module, "verify_firebase_id_token", lambda _: _principal("u", "u@example.com", ()))
    monkeypatch.setattr(view_module, "deactivate_work_membership", lambda uid: None)

    response = Client().post("/auth/firebase/mobile/", {"firebase_token": "x"}, HTTP_ORIGIN="https://hub.example")

    assert response.status_code == 303
    assert response["Location"] == "https://hub.example/notes?error=work_access_denied"


@pytest.mark.django_db
@pytest.mark.contract
@pytest.mark.parametrize("launch_url", ["", "http://hub.example/notes", "https://hub.example/notes?x=1", "javascript:alert(1)"])
def test_launch_failure_without_safe_launch_url_returns_json(monkeypatch, launch_url):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://hub.example")
    monkeypatch.setenv("GARDEN_LAUNCH_URL", launch_url)

    response = Client().post("/auth/firebase/mobile/", HTTP_ORIGIN="https://hub.example")

    assert response.status_code == 401
    assert response.json()["error"] == "missing_firebase_token"


@pytest.mark.django_db
@pytest.mark.contract
def test_wrong_origin_is_never_redirected(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://hub.example")
    monkeypatch.setenv("GARDEN_LAUNCH_URL", "https://hub.example/notes")

    response = Client().post("/auth/firebase/mobile/", {"firebase_token": "x"}, HTTP_ORIGIN="https://evil.example")

    assert response.status_code == 403
    assert response.json()["error"] == "origin_not_allowed"
