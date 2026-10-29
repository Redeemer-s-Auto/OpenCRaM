# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Live view blocks: what a block may show, and what it must never show."""

import pytest

from plane.db.models import Project, ProjectMember, State, Workspace, WorkspaceMember
from plane.relations.models import CardLink
from plane.sharing.models import ItemRestriction

from .conftest import FIELDS_URL, client_for, make_user

URL = "/api/workspaces/{slug}/inline-views/query/"
SECRET = "TOPSECRET"


def query(cast, client, **body):
    return client.post(URL.format(slug=cast.workspace.slug), body, format="json")


def names(response):
    assert response.status_code == 200, getattr(response, "data", None)
    return sorted(card["name"] for card in response.data["results"])


def board(cast, project):
    return {"type": "project", "project_id": str(project.id)}


@pytest.fixture
def cards(cast):
    one = cast.card(cast.alpha, "One", priority="high")
    two = cast.card(cast.alpha, "Two", priority="low")
    secret = cast.card(cast.alpha, f"Secret {SECRET}")
    ItemRestriction.objects.create(workspace=cast.workspace, issue=secret)
    other = cast.card(cast.beta, "Beta card")
    return one, two, secret, other


def test_block_shows_one_board(cast, cards):
    response = query(cast, cast.member_client, source=board(cast, cast.alpha))
    assert names(response) == ["One", "Two"]
    assert response.data["count"] == 2
    assert query(cast, cast.member_client, source=board(cast, cast.beta)).data["results"][0]["name"] == "Beta card"


def test_two_blocks_each_with_own_filter(cast, cards):
    high = query(cast, cast.member_client, source=board(cast, cast.alpha), filters={"priority": ["high"]})
    low = query(cast, cast.member_client, source=board(cast, cast.alpha), filters={"priority": ["low"]})
    assert names(high) == ["One"]
    assert names(low) == ["Two"]


def test_restricted_card_is_hidden_and_not_counted(cast, cards):
    response = query(cast, cast.member_client, source=board(cast, cast.alpha))
    assert SECRET not in str(response.data)
    assert response.data["count"] == 2
    # The author-side view (workspace admin) still sees it.
    admin = query(cast, cast.admin_client, source=board(cast, cast.alpha))
    assert response.status_code == 200 and admin.data["count"] == 3


def test_search_cannot_find_a_hidden_card(cast, cards):
    response = query(cast, cast.member_client, source=board(cast, cast.alpha), search=SECRET)
    assert response.data["count"] == 0 and response.data["results"] == []


def test_a_board_the_viewer_is_not_in_gives_nothing(cast, cards):
    # alpha_only is a workspace admin of Alpha and never joined Beta.
    response = query(cast, cast.alpha_only_client, source=board(cast, cast.beta))
    assert response.status_code == 200
    assert response.data["results"] == [] and response.data["projects"] == {}


def test_outsider_gets_nothing(cast, cards):
    outsider = make_user("outsider")
    response = query(cast, client_for(outsider), source=board(cast, cast.alpha))
    assert response.status_code == 403


def test_other_workspace_board_gives_nothing(cast, cards):
    other_owner = make_user("owner2")
    other_ws = Workspace.objects.create(name="Other", owner=other_owner, slug="other-" + cast.workspace.slug[-6:])
    WorkspaceMember.objects.create(workspace=other_ws, member=other_owner, role=20)
    foreign = Project.objects.create(name="Far", identifier="FAR", workspace=other_ws, created_by=other_owner)
    ProjectMember.objects.create(project=foreign, member=other_owner, workspace=other_ws, role=20)
    State.objects.create(name="Todo", project=foreign, workspace=other_ws, group="unstarted", default=True)
    response = query(cast, cast.member_client, source={"type": "project", "project_id": str(foreign.id)})
    assert response.data["results"] == []


def test_children_source_hides_restricted_children(cast, cards):
    one, _, _, _ = cards
    visible = cast.card(cast.alpha, "Child ok", parent=one)
    hidden = cast.card(cast.alpha, f"Child {SECRET}", parent=one)
    ItemRestriction.objects.create(workspace=cast.workspace, issue=hidden)
    response = query(cast, cast.member_client, source={"type": "children", "parent_id": str(one.id)})
    assert names(response) == ["Child ok"]
    assert str(visible.id) == response.data["results"][0]["id"]


def test_children_of_a_hidden_parent_is_empty(cast, cards):
    _, _, secret, _ = cards
    cast.card(cast.alpha, "Under secret", parent=secret)
    response = query(cast, cast.member_client, source={"type": "children", "parent_id": str(secret.id)})
    assert response.status_code == 200 and response.data["results"] == []


def test_linked_source_reads_forward_and_back(cast, cards):
    one, _, secret, other = cards
    rel = cast.relation(two_way=True)
    cast.patch(one, {str(rel["id"]): [str(other.id)]})
    forward = query(cast, cast.member_client, source={"type": "linked", "issue_id": str(one.id), "field_id": rel["id"]})
    assert names(forward) == ["Beta card"]
    mirror = cast.mirror_of(rel)
    back = query(
        cast, cast.member_client, source={"type": "linked", "issue_id": str(other.id), "field_id": str(mirror.id)}
    )
    assert names(back) == ["One"]


def test_linked_source_drops_hidden_targets(cast):
    rel = cast.relation()
    target = cast.card(cast.beta, f"Hidden {SECRET}")
    start = cast.card(cast.alpha, "Start")
    CardLink.objects.create(workspace=cast.workspace, field_id=rel["id"], from_issue=start, to_issue=target)
    ItemRestriction.objects.create(workspace=cast.workspace, issue=target)
    response = query(cast, cast.member_client, source={"type": "linked", "issue_id": str(start.id), "field_id": rel["id"]})
    assert response.status_code == 200 and response.data["results"] == []


def test_custom_field_values_filter_and_sort(cast, cards):
    one, two, _, _ = cards
    amount = cast.field(cast.alpha, name="Amount", field_type="number")
    key = str(amount["id"])
    cast.patch(one, {key: 5})
    cast.patch(two, {key: 50})
    big = query(
        cast,
        cast.member_client,
        source=board(cast, cast.alpha),
        custom_field_filters={f"customfield_{key}__gt": 10},
    )
    assert names(big) == ["Two"]
    assert big.data["results"][0]["custom_fields"][key] == 50
    ordered = query(cast, cast.member_client, source=board(cast, cast.alpha), order_by=f"-custom_field__{key}")
    assert [c["name"] for c in ordered.data["results"]] == ["Two", "One"]
    assert [f["name"] for f in ordered.data["projects"][str(cast.alpha.id)]["fields"]] == ["Amount"]


def test_custom_field_filters_need_one_board(cast, cards):
    one, _, _, _ = cards
    response = query(
        cast,
        cast.member_client,
        source={"type": "children", "parent_id": str(one.id)},
        custom_field_filters={"customfield_x__exact": 1},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"source": {"type": "everything"}},
        {"source": {"type": "project", "project_id": "nope"}},
        {"source": {"type": "project", "project_id": "00000000-0000-0000-0000-000000000000"}, "filters": {"name": "x"}},
        {"source": {"type": "project", "project_id": "00000000-0000-0000-0000-000000000000"}, "order_by": "secret"},
        {"source": {"type": "project", "project_id": "00000000-0000-0000-0000-000000000000"}, "limit": "many"},
    ],
)
def test_bad_settings_are_refused(cast, body):
    assert query(cast, cast.member_client, **body).status_code == 400


def test_limit_caps_rows_but_count_stays_true(cast):
    for i in range(3):
        cast.card(cast.alpha, f"Card {i}")
    response = query(cast, cast.member_client, source=board(cast, cast.alpha), limit=2)
    assert len(response.data["results"]) == 2 and response.data["count"] == 3


def test_states_and_people_come_back_for_drawing_columns(cast, cards):
    one, _, _, _ = cards
    from plane.db.models import IssueAssignee

    IssueAssignee.objects.create(issue=one, assignee=cast.member, project=cast.alpha, workspace=cast.workspace)
    response = query(cast, cast.member_client, source=board(cast, cast.alpha))
    project = response.data["projects"][str(cast.alpha.id)]
    assert [s["name"] for s in project["states"]] == ["Todo"]
    assert str(cast.member.id) in response.data["people"]
    assert FIELDS_URL  # imported for parity with the relation tests
