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


# ---- roles mode through the hub access endpoint (no credential file) ----------------------------

HUB_URL = "https://hub.example/notesAccess"
HUB_SECRET = "x" * 40


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.fixture
def hub_env(monkeypatch):
    monkeypatch.setenv("GARDEN_ACCESS_MODE", "roles")
    monkeypatch.setenv("GARDEN_FIREBASE_PROJECT_ID", "hub-project")
    monkeypatch.setenv("GARDEN_HUB_ACCESS_URL", HUB_URL)
    monkeypatch.setenv("GARDEN_HUB_ACCESS_SECRET", HUB_SECRET)

    def no_admin_sdk(*a, **k):
        raise AssertionError("the Admin SDK / a credential must not be used in hub mode")

    monkeypatch.setattr(firebase_identity, "_firebase_app", no_admin_sdk)
    monkeypatch.setattr(firebase_identity, "_firestore_document", no_admin_sdk)
    monkeypatch.setattr(
        firebase_identity,
        "_verify_token_with_public_certs",
        lambda token, project: {"user_id": "hub-uid", "sub": "hub-uid", "aud": project},
    )


def _hub_reply(monkeypatch, status=200, body=None, seen=None):
    import requests

    def post(url, headers=None, timeout=None):
        if seen is not None:
            seen.append((url, headers, timeout))
        return _Resp(status, body)

    monkeypatch.setattr(requests, "post", post)


def _body(**overrides):
    body = {
        "ok": True,
        "uid": "hub-uid",
        "email": "Pat@Example.com",
        "emailVerified": True,
        "displayName": "Pat Doe",
        "firstName": "Pat",
        "lastName": "Doe",
        "photoURL": "https://lh3.example/p",
        "active": True,
        "access": "member",
    }
    body.update(overrides)
    return body


@pytest.mark.unit
def test_hub_mode_sends_token_and_secret_and_maps_member(hub_env, monkeypatch):
    seen = []
    _hub_reply(monkeypatch, body=_body(), seen=seen)
    principal = verify_firebase_id_token("raw-token")
    url, headers, timeout = seen[0]
    assert url == HUB_URL
    assert headers == {"Authorization": "Bearer raw-token", "X-Notes-Access-Secret": HUB_SECRET}
    assert timeout and timeout <= 10
    assert principal.uid == "hub-uid"
    assert principal.email == "pat@example.com"
    assert principal.display_name == "Pat Doe"
    assert principal.can_read_work is True
    assert principal.can_admin_work is False


@pytest.mark.unit
def test_hub_mode_admin_and_none(hub_env, monkeypatch):
    _hub_reply(monkeypatch, body=_body(access="admin"))
    assert verify_firebase_id_token("t").can_admin_work is True
    _hub_reply(monkeypatch, body=_body(access="none"))
    assert verify_firebase_id_token("t").can_read_work is False
    _hub_reply(monkeypatch, body=_body(access="admin", active=False))
    assert verify_firebase_id_token("t").can_read_work is False
    _hub_reply(monkeypatch, body=_body(access="superuser"))
    assert verify_firebase_id_token("t").can_read_work is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "status,body",
    [
        (401, {"ok": False, "error": "token_invalid"}),
        (401, {"ok": False, "error": "bad_secret"}),
        (500, ValueError("html")),
        (200, {"ok": False}),
    ],
)
def test_hub_mode_refusal_or_outage_fails_closed(hub_env, monkeypatch, status, body):
    _hub_reply(monkeypatch, status=status, body=body)
    with pytest.raises(GardenIdentityError):
        verify_firebase_id_token("t")


@pytest.mark.unit
def test_hub_mode_network_error_fails_closed(hub_env, monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(GardenIdentityError, match="unavailable"):
        verify_firebase_id_token("t")


@pytest.mark.unit
def test_hub_mode_answer_for_another_uid_is_refused(hub_env, monkeypatch):
    _hub_reply(monkeypatch, body=_body(uid="someone-else"))
    with pytest.raises(GardenIdentityError, match="different account"):
        verify_firebase_id_token("t")


@pytest.mark.unit
def test_hub_mode_bad_local_token_never_calls_hub(hub_env, monkeypatch):
    def bad(token, project):
        raise ValueError("Token expired")

    monkeypatch.setattr(firebase_identity, "_verify_token_with_public_certs", bad)
    called = []
    _hub_reply(monkeypatch, body=_body(), seen=called)
    with pytest.raises(GardenIdentityError, match="verification failed"):
        verify_firebase_id_token("t")
    assert called == []


@pytest.mark.unit
def test_hub_mode_needs_https_url_and_long_secret(monkeypatch):
    monkeypatch.setenv("GARDEN_ACCESS_MODE", "roles")
    monkeypatch.setenv("GARDEN_HUB_ACCESS_URL", "http://hub.example/x")
    monkeypatch.setenv("GARDEN_HUB_ACCESS_SECRET", HUB_SECRET)
    assert firebase_identity.hub_access_configured() is False
    monkeypatch.setenv("GARDEN_HUB_ACCESS_URL", HUB_URL)
    monkeypatch.setenv("GARDEN_HUB_ACCESS_SECRET", "short")
    assert firebase_identity.hub_access_configured() is False
    monkeypatch.setenv("GARDEN_HUB_ACCESS_SECRET", HUB_SECRET)
    assert firebase_identity.hub_access_configured() is True
    monkeypatch.setenv("GARDEN_ACCESS_MODE", "projection")
    assert firebase_identity.hub_access_configured() is False


@pytest.mark.django_db
@pytest.mark.contract
def test_health_needs_no_credential_file_in_hub_mode(hub_env, monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_WORKSPACE_SLUG", "the-garden")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/nonexistent.json")
    response = Client().get("/auth/firebase/health/")
    assert response.status_code == 200
    assert response.json()["checks"]["hubAccess"] is True
    assert "firebaseCredentials" not in response.json()["checks"]


@pytest.mark.django_db
@pytest.mark.contract
def test_health_still_needs_credentials_by_default(monkeypatch):
    monkeypatch.delenv("GARDEN_ACCESS_MODE", raising=False)
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_FIREBASE_PROJECT_ID", "p")
    monkeypatch.setenv("GARDEN_WORKSPACE_SLUG", "the-garden")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/nonexistent.json")
    response = Client().get("/auth/firebase/health/")
    assert response.status_code == 503
    assert response.json()["checks"]["firebaseCredentials"] is False


@pytest.mark.django_db
@pytest.mark.contract
def test_session_exchange_through_hub_links_existing_user_by_email(hub_env, monkeypatch):
    from plane.db.models import User, WorkspaceMember
    from plane.garden.models import GardenExternalIdentity

    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://hub.example")
    monkeypatch.setenv("GARDEN_WORKSPACE_SLUG", "the-garden")
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    existing = User.objects.create(email="pat@example.com", username="pat-native", is_active=True)
    existing.set_password("native-password")
    existing.save()

    _hub_reply(monkeypatch, body=_body(access="admin"))
    response = Client().post("/auth/firebase/mobile/", {"firebase_token": "t"}, HTTP_ORIGIN="https://hub.example")

    assert response.status_code == 302
    assert User.objects.filter(email="pat@example.com").count() == 1
    link = GardenExternalIdentity.objects.get(external_id="hub-uid")
    assert link.user_id == existing.id
    assert WorkspaceMember.objects.get(member=existing, workspace__slug="the-garden").role == 20
