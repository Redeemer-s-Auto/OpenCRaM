# SPDX-License-Identifier: AGPL-3.0-only

import pytest
from django.conf import settings
from django.test import Client

from plane.garden.services.firebase_identity import GardenFirebasePrincipal


def _principal(capabilities=("work.read", "work.manage", "work.admin")):
    return GardenFirebasePrincipal(
        uid="firebase-session-user",
        email="session@example.com",
        email_verified=True,
        display_name="Session User",
        first_name="Session",
        last_name="User",
        photo_url="",
        roles=("admin",),
        capabilities=tuple(capabilities),
    )


@pytest.mark.django_db
@pytest.mark.contract
def test_session_exchange_is_unavailable_when_garden_auth_is_disabled(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "0")

    response = Client().post(
        "/auth/firebase/session/",
        HTTP_ORIGIN="https://admin.thegarden.example",
        HTTP_AUTHORIZATION="Bearer fake",
    )

    assert response.status_code == 404
    assert response.json()["error"] == "garden_auth_disabled"


@pytest.mark.django_db
@pytest.mark.contract
def test_session_exchange_rejects_unlisted_origin(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    response = Client().post(
        "/auth/firebase/session/",
        HTTP_ORIGIN="https://evil.example",
        HTTP_AUTHORIZATION="Bearer fake",
    )

    assert response.status_code == 403
    assert response.json()["error"] == "origin_not_allowed"


@pytest.mark.django_db
@pytest.mark.contract
def test_session_exchange_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    response = Client().post(
        "/auth/firebase/session/",
        HTTP_ORIGIN="https://admin.thegarden.example",
    )

    assert response.status_code == 401
    assert response.json()["error"] == "missing_bearer_token"


@pytest.mark.django_db
@pytest.mark.contract
def test_session_exchange_rejects_principal_without_work_read(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    from plane.garden.views import firebase_session as view_module

    monkeypatch.setattr(view_module, "verify_firebase_id_token", lambda _: _principal(capabilities=()))
    deactivated = []
    monkeypatch.setattr(view_module, "deactivate_work_membership", lambda uid: deactivated.append(uid))

    response = Client().post(
        "/auth/firebase/session/",
        HTTP_ORIGIN="https://admin.thegarden.example",
        HTTP_AUTHORIZATION="Bearer verified-by-test-double",
    )

    assert response.status_code == 403
    assert response.json()["error"] == "work_access_denied"
    assert deactivated == ["firebase-session-user"]


@pytest.mark.django_db
@pytest.mark.contract
def test_session_exchange_requires_work_read_even_with_other_work_capabilities(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    from plane.garden.views import firebase_session as view_module

    monkeypatch.setattr(
        view_module,
        "verify_firebase_id_token",
        lambda _: _principal(capabilities=("work.manage", "work.admin")),
    )
    deactivated = []
    monkeypatch.setattr(view_module, "deactivate_work_membership", lambda uid: deactivated.append(uid))

    response = Client().post(
        "/auth/firebase/session/",
        HTTP_ORIGIN="https://admin.thegarden.example",
        HTTP_AUTHORIZATION="Bearer verified-by-test-double",
    )

    assert response.status_code == 403
    assert response.json()["error"] == "work_access_denied"
    assert deactivated == ["firebase-session-user"]


@pytest.mark.django_db
@pytest.mark.contract
def test_session_exchange_creates_plane_session(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")

    from plane.garden.views import firebase_session as view_module

    monkeypatch.setattr(view_module, "verify_firebase_id_token", lambda _: _principal())

    client = Client()
    response = client.post(
        "/auth/firebase/session/",
        HTTP_ORIGIN="https://admin.thegarden.example",
        HTTP_AUTHORIZATION="Bearer verified-by-test-double",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["workspaceSlug"] == "the-garden"
    assert payload["role"] == 20
    assert payload["destination"] == "/the-garden/"
    assert response["Cache-Control"] == "no-store"
    assert settings.SESSION_COOKIE_NAME in response.cookies
    assert response.cookies[settings.SESSION_COOKIE_NAME]["httponly"] is True
    session = client.session
    assert session["garden_work_firebase_uid"] == "firebase-session-user"
    assert session["garden_work_workspace_slug"] == "the-garden"
    assert session["garden_work_workspace_role"] == 20
    assert session["garden_work_access_version"] == 0


@pytest.mark.django_db
@pytest.mark.contract
def test_session_revoke_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    response = Client().post(
        "/auth/firebase/logout/",
        HTTP_ORIGIN="https://admin.thegarden.example",
    )

    assert response.status_code == 401
    assert response.json()["error"] == "missing_bearer_token"


@pytest.mark.django_db
@pytest.mark.contract
def test_session_revoke_invalidates_all_linked_work_sessions(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    from plane.garden.views import firebase_session as view_module

    monkeypatch.setattr(view_module, "verify_firebase_id_token", lambda _: _principal())
    revoked = []
    monkeypatch.setattr(view_module, "revoke_work_sessions", lambda uid: revoked.append(uid) or 3)

    response = Client().post(
        "/auth/firebase/logout/",
        HTTP_ORIGIN="https://admin.thegarden.example",
        HTTP_AUTHORIZATION="Bearer verified-by-test-double",
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "revokedSessions": 3}
    assert response["Cache-Control"] == "no-store"
    assert revoked == ["firebase-session-user"]


@pytest.mark.django_db
@pytest.mark.contract
def test_mobile_launch_rejects_unlisted_origin(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    response = Client().post(
        "/auth/firebase/mobile/",
        {"firebase_token": "fake"},
        HTTP_ORIGIN="https://evil.example",
    )

    assert response.status_code == 403
    assert response.json()["error"] == "origin_not_allowed"


@pytest.mark.django_db
@pytest.mark.contract
def test_mobile_launch_requires_form_token(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")

    response = Client().post(
        "/auth/firebase/mobile/",
        HTTP_ORIGIN="https://admin.thegarden.example",
    )

    assert response.status_code == 401
    assert response.json()["error"] == "missing_firebase_token"


@pytest.mark.django_db
@pytest.mark.contract
def test_mobile_launch_creates_first_party_session_and_redirects(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_AUTH_ALLOWED_ORIGINS", "https://admin.thegarden.example")
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")

    from plane.garden.views import firebase_session as view_module

    monkeypatch.setattr(view_module, "verify_firebase_id_token", lambda _: _principal())

    client = Client()
    response = client.post(
        "/auth/firebase/mobile/",
        {"firebase_token": "verified-by-test-double"},
        HTTP_ORIGIN="https://admin.thegarden.example",
    )

    assert response.status_code == 302
    assert response["Location"] == "/the-garden/"
    assert response["Cache-Control"] == "no-store"
    assert settings.SESSION_COOKIE_NAME in response.cookies
    session = client.session
    assert session["garden_work_firebase_uid"] == "firebase-session-user"
    assert session["garden_work_workspace_slug"] == "the-garden"
    assert session["garden_work_workspace_role"] == 20
