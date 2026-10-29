# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Created time, last edited time, created by, last edited by: read from the card, never written."""

import datetime

import pytest
from django.utils import timezone

from plane.db.models import CustomFieldValue
from plane.relations.tests.conftest import *  # noqa: F401,F403  (the cast of users and boards)

QUERY_URL = "/api/workspaces/{slug}/inline-views/query/"
ISSUE_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/"
TYPES = ("created_time", "last_edited_time", "created_by", "last_edited_by")


@pytest.fixture
def audit(cast):
    fields = {t: cast.field(cast.alpha, name=t.replace("_", " ").title(), field_type=t) for t in TYPES}
    # Ids come back as UUID objects; values are keyed by the id as text.
    return {t: {**f, "id": str(f["id"])} for t, f in fields.items()}


def card_values(cast, client, card):
    return cast.values(card, client)


def test_audit_fields_can_be_made_with_no_settings(cast, audit):
    for field in audit.values():
        assert field["settings"] == {} and field["options"] == []


def test_card_shows_who_made_it_and_when(cast, audit):
    card = cast.card(cast.alpha, "A card", author=cast.member)
    values = card_values(cast, cast.member_client, card)
    assert values[audit["created_by"]["id"]] == [str(cast.member.id)]
    made = datetime.datetime.fromisoformat(values[audit["created_time"]["id"]])
    assert abs((timezone.now() - made).total_seconds()) < 300
    assert datetime.datetime.fromisoformat(values[audit["last_edited_time"]["id"]]) >= made


def test_last_edited_time_moves_when_a_field_value_changes(cast, audit):
    amount = cast.field(cast.alpha, name="Amount", field_type="number")
    card = cast.card(cast.alpha, "A card", author=cast.admin)
    before = card_values(cast, cast.member_client, card)[audit["last_edited_time"]["id"]]
    cast.patch(card, {str(amount["id"]): 5}, client=cast.member_client)
    after = card_values(cast, cast.member_client, card)[audit["last_edited_time"]["id"]]
    assert datetime.datetime.fromisoformat(after) > datetime.datetime.fromisoformat(before)


def test_last_edited_time_moves_when_the_body_changes(cast, audit):
    card = cast.card(cast.alpha, "A card", author=cast.admin)
    before = card_values(cast, cast.admin_client, card)[audit["last_edited_time"]["id"]]
    url = ISSUE_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id, issue_id=card.id)
    response = cast.admin_client.patch(url, {"description_html": "<p>New body</p>"}, format="json")
    assert response.status_code == 204, getattr(response, "data", None)
    after = card_values(cast, cast.admin_client, card)[audit["last_edited_time"]["id"]]
    assert datetime.datetime.fromisoformat(after) > datetime.datetime.fromisoformat(before)


def test_a_client_cannot_write_an_audit_field(cast, audit):
    card = cast.card(cast.alpha, "A card", author=cast.member)
    cast.patch(card, {audit["created_by"]["id"]: [str(cast.admin.id)], audit["created_time"]["id"]: "2001-01-01"})
    values = card_values(cast, cast.member_client, card)
    assert values[audit["created_by"]["id"]] == [str(cast.member.id)]
    assert not values[audit["created_time"]["id"]].startswith("2001")
    assert not CustomFieldValue.objects.filter(issue=card, field_id__in=[f["id"] for f in audit.values()]).exists()


def query(cast, client, **body):
    body.setdefault("source", {"type": "project", "project_id": str(cast.alpha.id)})
    response = client.post(QUERY_URL.format(slug=cast.workspace.slug), body, format="json")
    return response


def test_filter_by_created_by(cast, audit):
    mine = cast.card(cast.alpha, "Mine", author=cast.member)
    cast.card(cast.alpha, "Theirs", author=cast.admin)
    key = f"customfield_{audit['created_by']['id']}__in"
    response = query(cast, cast.admin_client, custom_field_filters={key: str(cast.member.id)})
    assert response.status_code == 200, response.data
    assert [c["id"] for c in response.data["results"]] == [str(mine.id)]
    bad = query(cast, cast.admin_client, custom_field_filters={key: "not-an-id"})
    assert bad.status_code == 400


def test_filter_by_created_time(cast, audit):
    cast.card(cast.alpha, "New", author=cast.admin)
    field = audit["created_time"]["id"]
    today = query(cast, cast.admin_client, custom_field_filters={f"customfield_{field}__gte": "@today"})
    assert len(today.data["results"]) == 1
    exact = query(cast, cast.admin_client, custom_field_filters={f"customfield_{field}__exact": "@today"})
    assert len(exact.data["results"]) == 1
    tomorrow = query(cast, cast.admin_client, custom_field_filters={f"customfield_{field}__gte": "@today+2"})
    assert tomorrow.data["results"] == []
    ranged = query(cast, cast.admin_client, custom_field_filters={f"customfield_{field}__range": "@today-1,@today+1"})
    assert len(ranged.data["results"]) == 1
    bad = query(cast, cast.admin_client, custom_field_filters={f"customfield_{field}__icontains": "x"})
    assert bad.status_code == 400


def test_sort_by_created_time_and_created_by(cast, audit):
    first = cast.card(cast.alpha, "First", author=cast.member)
    second = cast.card(cast.alpha, "Second", author=cast.admin)
    by_time = query(cast, cast.admin_client, order_by=f"-custom_field__{audit['created_time']['id']}")
    assert [c["id"] for c in by_time.data["results"]] == [str(second.id), str(first.id)]
    by_name = query(cast, cast.admin_client, order_by=f"custom_field__{audit['created_by']['id']}")
    assert by_name.status_code == 200 and len(by_name.data["results"]) == 2
    names = {str(cast.admin.id): cast.admin.display_name, str(cast.member.id): cast.member.display_name}
    order = [names[c["custom_fields"][audit["created_by"]["id"]][0]] for c in by_name.data["results"]]
    assert order == sorted(order, key=str.lower) or order == sorted(order)


def test_hidden_card_shows_no_audit_values(cast, audit):
    from plane.sharing.models import ItemRestriction

    secret = cast.card(cast.alpha, "Secret", author=cast.admin)
    ItemRestriction.objects.create(workspace=cast.workspace, issue=secret)
    response = query(cast, cast.member_client)
    assert response.data["results"] == [] and response.data["count"] == 0


def test_audit_field_is_empty_when_card_has_no_author(cast, audit):
    card = cast.card(cast.alpha, "Imported")
    from plane.db.models import Issue

    Issue.objects.filter(pk=card.pk).update(created_by=None, updated_by=None)
    values = card_values(cast, cast.admin_client, card)
    assert values[audit["created_by"]["id"]] is None and values[audit["last_edited_by"]["id"]] is None
