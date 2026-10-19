# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""The card door: hub apps make and read cards (work items) and sub-cards through the public API."""

import pytest
from rest_framework.test import APIClient

from plane.db.models import Issue
from plane.db.models.api import APIToken
from plane.sharing.models import AccessLevel, ShareTarget
from plane.sharing.tests.conftest import make_issue, restrict


def api_client(cast, user):
    token = APIToken.objects.create(user=user, workspace=cast.workspace)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


def url(cast, path=""):
    return f"/api/v1/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/work-items/{path}"


def ids(rows):
    return {str(row["id"]) for row in rows}


@pytest.mark.django_db
class TestCardDoor:
    def test_card_and_sub_cards_round_trip(self, cast):
        api = api_client(cast, cast.author)
        card = api.post(
            url(cast),
            {
                "name": "Client call",
                "description_html": "<p>Asked about <strong>brakes</strong>.</p>",
                "external_source": "hub",
                "external_id": "call-1",
            },
            format="json",
        )
        assert card.status_code == 201, card.content
        card_id = card.data["id"]

        again = api.post(url(cast), {"name": "dup", "external_source": "hub", "external_id": "call-1"}, format="json")
        assert again.status_code == 409
        assert again.data["id"] == card_id

        read = api.get(url(cast, f"{card_id}/"))
        assert read.status_code == 200
        assert "<strong>brakes</strong>" in read.data["description_html"]

        updated = api.patch(url(cast, f"{card_id}/"), {"description_html": "<p>Booked Thursday.</p>"}, format="json")
        assert updated.status_code == 200, updated.content
        # The web editor for work items loads description_html, so this is what it shows.
        assert Issue.objects.get(pk=card_id).description_html == "<p>Booked Thursday.</p>"

        sub = api.post(url(cast), {"name": "Order pads", "parent": card_id}, format="json")
        assert sub.status_code == 201, sub.content
        assert str(sub.data["parent"]) == card_id
        other = make_issue(cast, "Unrelated")

        children = api.get(url(cast) + f"?parent={card_id}")
        assert children.status_code == 200
        assert ids(children.data["results"]) == {sub.data["id"]}
        assert children.data["total_count"] == 1

        top = api.get(url(cast) + "?parent=null")
        assert ids(top.data["results"]) == {card_id, str(other.id)}

        assert api.get(url(cast) + "?parent=not-a-uuid").status_code == 400

    def test_hidden_sub_card_not_listed(self, cast):
        parent = make_issue(cast, "Parent")
        shown = make_issue(cast, "Shown child", parent=parent)
        hidden = make_issue(cast, "Hidden child", parent=parent)
        restrict(cast, issue=hidden, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])

        insider = api_client(cast, cast.insider).get(url(cast) + f"?parent={parent.id}")
        assert insider.status_code == 200
        assert ids(insider.data["results"]) == {str(shown.id)}
        assert insider.data["total_count"] == 1

        friend = api_client(cast, cast.friend).get(url(cast) + f"?parent={parent.id}")
        assert ids(friend.data["results"]) == {str(shown.id), str(hidden.id)}

    def test_outsider_cannot_list_sub_cards(self, cast):
        parent = make_issue(cast, "Parent")
        make_issue(cast, "Child", parent=parent)
        response = api_client(cast, cast.outsider).get(url(cast) + f"?parent={parent.id}")
        assert response.status_code in (403, 404)
