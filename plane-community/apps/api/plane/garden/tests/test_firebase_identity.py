# SPDX-License-Identifier: AGPL-3.0-only

from types import SimpleNamespace

import pytest

from plane.garden.services import firebase_identity
from plane.garden.services.firebase_identity import GardenIdentityError, verify_firebase_id_token


def _user(**overrides):
    values = {
        "disabled": False,
        "email": "staff@thegarden.church",
        "email_verified": True,
        "display_name": "Garden Staff",
        "photo_url": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _decoded(**overrides):
    values = {
        "uid": "firebase-qa-user",
        "aud": "church-2612f",
        "email": "token@thegarden.church",
        "email_verified": True,
        "roles": ["staff"],
        "capabilities": ["work.read", "work.manage"],
        "given_name": "Garden",
        "family_name": "Staff",
    }
    values.update(overrides)
    return values


def _prepare(monkeypatch, decoded=None, user=None):
    monkeypatch.setenv("GARDEN_FIREBASE_PROJECT_ID", "church-2612f")
    monkeypatch.setattr(firebase_identity, "_firebase_app", lambda: object())
    monkeypatch.setattr(firebase_identity.auth, "verify_id_token", lambda *args, **kwargs: decoded or _decoded())
    monkeypatch.setattr(firebase_identity.auth, "get_user", lambda *args, **kwargs: user or _user())
    monkeypatch.setattr(firebase_identity, "_firestore_profile", lambda *args, **kwargs: {})


@pytest.mark.unit
def test_verified_auth_record_email_is_identity_authority(monkeypatch):
    _prepare(monkeypatch)
    monkeypatch.setattr(
        firebase_identity,
        "_firestore_profile",
        lambda *args, **kwargs: {"email": "different@profile.example", "displayName": "Canonical Display"},
    )

    principal = verify_firebase_id_token("valid")

    assert principal.email == "staff@thegarden.church"
    assert principal.display_name == "Canonical Display"


@pytest.mark.unit
def test_wrong_firebase_project_audience_is_rejected(monkeypatch):
    _prepare(monkeypatch, decoded=_decoded(aud="other-project"))

    with pytest.raises(GardenIdentityError, match="audience"):
        verify_firebase_id_token("wrong-audience")


@pytest.mark.unit
def test_disabled_firebase_user_is_rejected(monkeypatch):
    _prepare(monkeypatch, user=_user(disabled=True))

    with pytest.raises(GardenIdentityError, match="disabled"):
        verify_firebase_id_token("disabled-user")


@pytest.mark.unit
@pytest.mark.parametrize("failure", [ValueError("malformed"), RuntimeError("expired"), RuntimeError("revoked")])
def test_invalid_expired_or_revoked_tokens_fail_closed(monkeypatch, failure):
    monkeypatch.setenv("GARDEN_FIREBASE_PROJECT_ID", "church-2612f")
    monkeypatch.setattr(firebase_identity, "_firebase_app", lambda: object())

    def fail_verify(*args, **kwargs):
        raise failure

    monkeypatch.setattr(firebase_identity.auth, "verify_id_token", fail_verify)

    with pytest.raises(GardenIdentityError, match="verification failed"):
        verify_firebase_id_token("bad-token")


@pytest.mark.unit
def test_missing_uid_is_rejected(monkeypatch):
    _prepare(monkeypatch, decoded=_decoded(uid="", sub=""))

    with pytest.raises(GardenIdentityError, match="no UID"):
        verify_firebase_id_token("missing-uid")


@pytest.mark.unit
def test_claim_arrays_ignore_non_string_values(monkeypatch):
    _prepare(
        monkeypatch,
        decoded=_decoded(roles=["staff", 123], capabilities=["work.read", None, "work.manage"]),
    )

    principal = verify_firebase_id_token("valid")

    assert principal.roles == ("staff",)
    assert principal.capabilities == ("work.read", "work.manage")


@pytest.mark.unit
def test_canonical_superuser_profile_can_bootstrap_before_work_projection_exists(monkeypatch):
    _prepare(
        monkeypatch,
        decoded=_decoded(capabilities=[], organizationRole="user", accessVersion=0),
    )

    def firestore_document(collection, uid, app, **kwargs):
        if collection == "accessProfiles":
            return {
                "uid": uid,
                "principalType": "human",
                "organizationRole": "superuser",
                "grants": [],
                "denies": [],
                "accessVersion": 0,
            }
        return {}

    monkeypatch.setattr(firebase_identity, "_firestore_document", firestore_document)
    monkeypatch.setattr(firebase_identity, "_firestore_work_projection", lambda *args, **kwargs: None)

    principal = verify_firebase_id_token("valid")

    assert principal.organization_role == "superuser"
    assert principal.can_read_work is True
    assert principal.can_admin_work is True


@pytest.mark.unit
def test_firestore_enrichment_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GARDEN_FIRESTORE_PROFILE_SYNC", "0")

    def should_not_run(*args, **kwargs):
        raise AssertionError("Firestore client should not be called")

    monkeypatch.setattr(firebase_identity.firestore, "client", should_not_run)

    assert firebase_identity._firestore_profile("uid", object()) == {}
