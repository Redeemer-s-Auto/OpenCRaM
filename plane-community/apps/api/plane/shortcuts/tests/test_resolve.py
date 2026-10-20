# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The "Link to card" block: resolve ids for one viewer, and the card picker."""

import uuid

import pytest

from plane.db.models import Issue, ProjectMember, Workspace
from plane.utils.content_validator import validate_html_content

from .conftest import SECRET, block, card, resolve, url


def statuses(response):
    return {key: value["status"] for key, value in response.data["results"].items()}


@pytest.mark.django_db
class TestResolve:
    def test_member_of_both_boards(self, links):
        response = resolve(links, links.both_client, [links.beta_open.id, links.beta_secret.id, links.gamma_card.id])
        assert statuses(response) == {
            str(links.beta_open.id): "visible",
            str(links.beta_secret.id): "hidden",
            str(links.gamma_card.id): "hidden",
        }
        shown = response.data["results"][str(links.beta_open.id)]["card"]
        assert shown["name"] == "Beta open target"
        assert shown["project_identifier"] == "BET" and shown["project_name"] == "Beta"
        assert shown["state_group"] == "unstarted"
        assert SECRET.encode() not in response.content

    def test_hidden_entries_say_nothing_else(self, links):
        response = resolve(links, links.both_client, [links.beta_secret.id, links.gamma_card.id])
        for value in response.data["results"].values():
            assert value == {"status": "hidden"}
        assert b"Beta" not in response.content and b"GAM" not in response.content

    def test_admin_and_private_board_member_see_all(self, links):
        response = resolve(links, links.owner_client, [links.beta_open.id, links.beta_secret.id, links.gamma_card.id])
        assert set(statuses(response).values()) == {"visible"}

    def test_not_a_member_of_the_board(self, links):
        response = resolve(links, links.insider_client, [links.beta_open.id])
        assert statuses(response) == {str(links.beta_open.id): "hidden"}
        assert b"Beta open target" not in response.content

    def test_workspace_admin_off_the_private_board_sees_hidden(self, links):
        ProjectMember.objects.filter(project=links.gamma, member=links.owner).update(is_active=False)
        response = resolve(links, links.owner_client, [links.gamma_card.id])
        assert statuses(response) == {str(links.gamma_card.id): "hidden"}

    def test_guest_sees_only_own_cards(self, links):
        ProjectMember.objects.filter(project=links.beta, member=links.both).update(role=5)
        own = card(links, "Guest made", project=links.beta, author=links.both)
        response = resolve(links, links.both_client, [links.beta_open.id, own.id])
        assert statuses(response) == {str(links.beta_open.id): "hidden", str(own.id): "visible"}

    def test_deleted_card_is_removed_only_for_people_who_could_see_it(self, links):
        links.beta_open.delete()
        assert statuses(resolve(links, links.both_client, [links.beta_open.id])) == {
            str(links.beta_open.id): "removed"
        }
        assert statuses(resolve(links, links.insider_client, [links.beta_open.id])) == {
            str(links.beta_open.id): "hidden"
        }

    def test_unknown_and_garbage_ids(self, links):
        missing = str(uuid.uuid4())
        response = resolve(links, links.both_client, [missing, "not-an-id", 42, None])
        assert statuses(response) == {missing: "removed"}

    def test_card_in_another_workspace_is_hidden(self, links):
        other = Workspace.objects.create(name="Other", owner=links.owner, slug=f"other-{uuid.uuid4().hex[:6]}")
        project = links.alpha.__class__.objects.create(
            name="Elsewhere", identifier="ELS", workspace=other, created_by=links.owner
        )
        ProjectMember.objects.create(project=project, member=links.owner, workspace=other, role=20)
        far = Issue(name=f"Far {SECRET}", project=project, workspace=other)
        far.save(created_by_id=links.owner.id)
        response = resolve(links, links.owner_client, [far.id])
        assert statuses(response) == {str(far.id): "hidden"}

    def test_limit_and_bad_payload(self, links):
        response = resolve(links, links.both_client, [uuid.uuid4() for _ in range(150)])
        assert len(response.data["results"]) == 100
        bad = links.both_client.post(url(links, "card-links/resolve/"), {"ids": "x"}, format="json")
        assert bad.status_code == 400

    def test_not_in_the_workspace(self, links):
        from plane.sharing.tests.conftest import client_for, make_user

        stranger = client_for(make_user("stranger"))
        response = stranger.post(url(links, "card-links/resolve/"), {"ids": [str(links.beta_open.id)]}, format="json")
        assert response.status_code in (403, 404)


@pytest.mark.django_db
class TestSearch:
    def search(self, links, client, text):
        response = client.get(url(links, "card-links/search/"), {"search": text})
        assert response.status_code == 200, response.content
        return response

    def test_only_visible_cards(self, links):
        found = {row["id"] for row in self.search(links, links.both_client, "").data["results"]}
        assert str(links.beta_open.id) in found and str(links.source.id) in found
        assert str(links.beta_secret.id) not in found and str(links.gamma_card.id) not in found
        assert self.search(links, links.both_client, SECRET).data["results"] == []
        assert len(self.search(links, links.owner_client, SECRET).data["results"]) == 2

    def test_by_identifier(self, links):
        rows = self.search(links, links.both_client, f"BET-{links.beta_open.sequence_id}").data["results"]
        assert [r["id"] for r in rows] == [str(links.beta_open.id)]
        rows = self.search(links, links.insider_client, f"BET-{links.beta_open.sequence_id}").data["results"]
        assert rows == []


@pytest.mark.unit
def test_block_survives_the_html_clean_up():
    card_id = str(uuid.uuid4())
    html = f"<p>x</p>{block(card_id)}"
    ok, error, cleaned = validate_html_content(html)
    assert ok, error
    result = cleaned if cleaned is not None else html
    assert "<card-link-component" in result and f'data-card-id="{card_id}"' in result
