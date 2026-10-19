# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Card templates must not leak restricted cards.

A template is visible to everyone on the board, so a restricted card - or a
restricted sub-card - must never be copied into one, even by someone who can see it.
"""

import pytest

from plane.db.models import IssueTemplate
from plane.sharing.models import AccessLevel, ShareTarget

from .conftest import make_issue, restrict


def _save_url(cast, issue):
    return f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/issues/{issue.id}/save-as-template/"


def _templates_url(cast):
    return f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/work-item-templates/"


@pytest.mark.django_db
class TestTemplateLeaks:
    def test_restricted_card_cannot_become_a_template(self, cast, secret_issue):
        # The friend only has Can view: saving needs Can edit, so the sharing guard refuses.
        response = cast.friend_client.post(_save_url(cast, secret_issue), {"name": "Copy"}, format="json")
        assert response.status_code == 403
        # The author can edit the card, but the template would reach the whole board: refused too.
        response = cast.author_client.post(_save_url(cast, secret_issue), {"name": "Copy"}, format="json")
        assert response.status_code == 400
        assert response.data["code"] == "restricted_card"
        assert not IssueTemplate.objects.exists()

    def test_insider_cannot_save_a_card_they_cannot_see(self, cast, secret_issue):
        response = cast.insider_client.post(_save_url(cast, secret_issue), {"name": "Copy"}, format="json")
        assert response.status_code in (400, 403, 404)
        assert not IssueTemplate.objects.exists()

    def test_restricted_sub_cards_are_left_out(self, cast):
        parent = make_issue(cast, "Open parent")
        make_issue(cast, "Open child", parent=parent)
        hidden = make_issue(cast, "Hidden child TOPSECRET", parent=parent)
        # Shared with the author's friend only; the author created it, so the author can see it.
        restrict(cast, issue=hidden, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])

        response = cast.author_client.post(
            _save_url(cast, parent), {"name": "From parent", "include_sub_items": True}, format="json"
        )
        assert response.status_code == 201, response.data
        assert [s["name"] for s in response.data["data"]["sub_items"]] == ["Open child"]

        # The insider (not on the hidden card's share list) reads the templates: no trace of it.
        listing = cast.insider_client.get(_templates_url(cast))
        assert listing.status_code == 200
        assert "TOPSECRET" not in str(listing.data)
        detail = cast.insider_client.get(f"{_templates_url(cast)}{response.data['id']}/")
        assert "TOPSECRET" not in str(detail.data)
