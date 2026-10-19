# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A viewer must never learn anything about a linked card they cannot see.

Hidden linked cards are left out of the relation list AND out of rollup math for
that viewer, on every read path: card detail, card lists, the v1 API, the link
picker, and the activity log. Background jobs (no viewer) get no linked values.
"""

import pytest
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember
from plane.db.models.api import APIToken
from plane.relations.models import CardLink
from plane.sharing.models import ItemRestriction
from plane.utils.custom_fields import values_for_issues

from .conftest import FIELDS_URL

SECRET = "TOPSECRET"


def fid(field):
    return str(field["id"])


def _rows(data):
    if isinstance(data, list):
        return data
    results = data.get("results", data)
    if isinstance(results, list):
        return results
    rows = []
    for group in results.values():
        rows.extend(group.get("results", []) if isinstance(group, dict) else group)
    return rows


@pytest.fixture
def linked(cast):
    """a1 links an open Beta card (100 cents) and a restricted one (9900 cents, only admin sees it)."""
    amount = cast.field(cast.beta, name="Amount", field_type="money")
    done = cast.field(cast.beta, name="Done", field_type="checkbox")
    rel = cast.relation(name="Linked", two_way=True)
    open_card = cast.card(cast.beta, "Open card")
    secret = cast.card(cast.beta, f"Secret {SECRET}")
    cast.patch(open_card, {fid(amount): 100, fid(done): False})
    cast.patch(secret, {fid(amount): 9900, fid(done): True})
    ItemRestriction.objects.create(workspace=cast.workspace, issue=secret)
    a1 = cast.card(cast.alpha, "A1")
    cast.patch(a1, {fid(rel): [str(open_card.id), str(secret.id)]})
    rollups = {
        name: cast.rollup(rel, function, target)
        for name, function, target in (
            ("count", "count", None),
            ("sum", "sum", fid(amount)),
            ("max", "max", fid(amount)),
            ("pct", "percent_checked", fid(done)),
            ("names", "unique", "@title"),
        )
    }

    class Linked:
        pass

    x = Linked()
    x.amount, x.rel, x.a1, x.open, x.secret, x.rollups = amount, rel, a1, open_card, secret, rollups
    x.mirror = cast.mirror_of(rel)
    return x


def _assert_member_view(values, linked):
    assert [c["id"] for c in values[fid(linked.rel)]] == [str(linked.open.id)]
    r = linked.rollups
    assert values[fid(r["count"])] == 1
    assert values[fid(r["sum"])] == 100
    assert values[fid(r["max"])] == 100
    assert values[fid(r["pct"])] == 0
    assert values[fid(r["names"])] == ["Open card"]
    assert SECRET not in str(values) and str(linked.secret.id) not in str(values)


@pytest.mark.django_db
class TestHiddenLinkedCards:
    def test_admin_sees_both(self, cast, linked):
        values = cast.values(linked.a1)
        assert len(values[fid(linked.rel)]) == 2
        assert values[fid(linked.rollups["count"])] == 2
        assert values[fid(linked.rollups["sum"])] == 10000
        assert values[fid(linked.rollups["pct"])] == 50

    def test_restricted_card_not_listed_or_counted_on_detail(self, cast, linked):
        _assert_member_view(cast.values(linked.a1, cast.member_client), linked)

    def test_restricted_card_not_in_the_list_endpoint(self, cast, linked):
        url = f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/issues/"
        response = cast.member_client.get(url)
        assert response.status_code == 200
        rows = {str(r["id"]): r for r in _rows(response.data)}
        _assert_member_view(rows[str(linked.a1.id)]["custom_fields"], linked)

    def test_mirror_side_hides_too(self, cast, linked):
        # A restricted Alpha card linking to the open Beta card is invisible on the Beta side.
        hidden_a = cast.card(cast.alpha, f"Hidden {SECRET}")
        ItemRestriction.objects.create(workspace=cast.workspace, issue=hidden_a)
        cast.patch(hidden_a, {fid(linked.rel): [str(linked.open.id)]})
        values = cast.values(linked.open, cast.member_client)
        assert [c["id"] for c in values[str(linked.mirror.id)]] == [str(linked.a1.id)]
        assert SECRET not in str(values)

    def test_not_a_member_of_the_target_board(self, cast, linked):
        # alpha_only: workspace admin and Alpha admin, but not on Beta. Beta is also private.
        Project.objects.filter(pk=cast.beta.pk).update(is_private=True)
        values = cast.values(linked.a1, cast.alpha_only_client)
        assert fid(linked.rel) not in values
        assert values[fid(linked.rollups["count"])] == 0
        assert fid(linked.rollups["sum"]) not in values
        assert "Open card" not in str(values)

    def test_guest_sees_only_own_cards(self, cast, linked):
        ProjectMember.objects.filter(project=cast.beta, member=cast.member).update(role=5)
        values = cast.values(linked.a1, cast.member_client)
        assert fid(linked.rel) not in values
        assert values[fid(linked.rollups["count"])] == 0

    def test_cannot_link_a_hidden_card_and_error_says_nothing(self, cast, linked):
        a2 = cast.card(cast.alpha, "A2", author=cast.member)
        hidden = cast.patch(a2, {fid(linked.rel): [str(linked.secret.id)]}, client=cast.member_client, expect=400)
        missing = cast.patch(
            a2, {fid(linked.rel): ["00000000-0000-0000-0000-000000000000"]}, client=cast.member_client, expect=400
        )
        assert str(hidden.data) == str(missing.data)

    def test_writer_cannot_remove_links_they_cannot_see(self, cast, linked):
        cast.patch(linked.a1, {fid(linked.rel): None}, client=cast.member_client)
        assert CardLink.objects.filter(to_issue_id=linked.secret.id).exists()
        assert not CardLink.objects.filter(to_issue_id=linked.open.id).exists()
        assert [c["id"] for c in cast.values(linked.a1)[fid(linked.rel)]] == [str(linked.secret.id)]

    def test_picker_leaves_hidden_cards_out(self, cast, linked):
        url = (
            FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id)
            + f"{fid(linked.rel)}/link-candidates/"
        )
        member = cast.member_client.get(url, {"search": ""})
        assert member.status_code == 200
        assert {c["id"] for c in member.data} == {str(linked.open.id)}
        assert cast.member_client.get(url, {"search": SECRET}).data == []
        assert {c["id"] for c in cast.admin_client.get(url).data} == {str(linked.open.id), str(linked.secret.id)}
        assert [c["name"] for c in cast.admin_client.get(url, {"search": "open"}).data] == ["Open card"]

    def test_private_source_board_404s_the_picker(self, cast, linked):
        Project.objects.filter(pk=cast.alpha.pk).update(is_private=True)
        outsider_url = (
            FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id)
            + f"{fid(linked.rel)}/link-candidates/"
        )
        ProjectMember.objects.filter(project=cast.alpha, member=cast.member).update(is_active=False)
        assert cast.member_client.get(outsider_url).status_code in (403, 404)

    def test_background_jobs_get_no_linked_values(self, cast, linked):
        values = values_for_issues([linked.a1.id]).get(str(linked.a1.id), {})
        assert fid(linked.rel) not in values
        assert fid(linked.rollups["count"]) not in values


@pytest.mark.django_db
class TestPublicAPI:
    @pytest.fixture
    def member_key(self, cast):
        api_client = APIClient()
        token = APIToken.objects.create(user=cast.member, label="member key", token="member-links-key-1")
        api_client.credentials(HTTP_X_API_KEY=token.token)
        return api_client

    def test_round_trip_and_no_leak(self, cast, linked, member_key):
        base = f"/api/v1/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/issues/"
        detail = member_key.get(f"{base}{linked.a1.id}/")
        assert detail.status_code == 200, detail.data
        _assert_member_view(detail.data["custom_fields"], linked)

        listing = member_key.get(base)
        assert listing.status_code == 200
        rows = {str(r["id"]): r for r in _rows(listing.data)}
        _assert_member_view(rows[str(linked.a1.id)]["custom_fields"], linked)

        # Write through the card door: link a new card, keep the open one.
        extra = cast.card(cast.beta, "Extra")
        response = member_key.patch(
            f"{base}{linked.a1.id}/",
            {"custom_fields": {fid(linked.rel): [str(linked.open.id), str(extra.id)]}},
            format="json",
        )
        assert response.status_code == 200, response.data
        got = member_key.get(f"{base}{linked.a1.id}/").data["custom_fields"]
        assert [c["id"] for c in got[fid(linked.rel)]] == [str(linked.open.id), str(extra.id)]
        assert got[fid(linked.rollups["count"])] == 2
        # The hidden link is still there for the admin.
        assert len(cast.values(linked.a1)[fid(linked.rel)]) == 3

        # Create a card with links in one call.
        created = member_key.post(
            base, {"name": "Made by API", "custom_fields": {fid(linked.rel): [str(extra.id)]}}, format="json"
        )
        assert created.status_code == 201, created.data
        assert [c["id"] for c in created.data["custom_fields"][fid(linked.rel)]] == [str(extra.id)]

    def test_picker_through_v1(self, cast, linked, member_key):
        url = (
            f"/api/v1/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/custom-fields/"
            f"{fid(linked.rel)}/link-candidates/"
        )
        response = member_key.get(url)
        assert response.status_code == 200, response.data
        assert {c["id"] for c in response.data} == {str(linked.open.id)}
