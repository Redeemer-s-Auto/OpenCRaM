# SPDX-License-Identifier: AGPL-3.0-only

import pytest

from plane.authentication.urls import build_auth_urlpatterns


def _names(patterns):
    return {pattern.name for pattern in patterns if getattr(pattern, "name", None)}


@pytest.mark.unit
def test_garden_mode_keeps_only_session_maintenance_auth_routes():
    names = _names(build_auth_urlpatterns(True))

    assert names == {"sign-out", "space-sign-out", "get_csrf_token"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "blocked_name",
    [
        "sign-in",
        "sign-up",
        "magic-generate",
        "magic-sign-in",
        "magic-sign-up",
        "google-initiate",
        "github-initiate",
        "gitlab-initiate",
        "gitea-initiate",
        "forgot-password",
        "reset-password",
        "change-password",
        "set-password",
        "space-sign-in",
        "space-sign-up",
    ],
)
def test_garden_mode_excludes_native_auth_entry_points(blocked_name):
    assert blocked_name not in _names(build_auth_urlpatterns(True))


@pytest.mark.unit
def test_non_garden_mode_preserves_upstream_native_auth_routes():
    names = _names(build_auth_urlpatterns(False))

    assert "sign-in" in names
    assert "sign-up" in names
    assert "google-initiate" in names
    assert "forgot-password" in names
    assert "sign-out" in names
