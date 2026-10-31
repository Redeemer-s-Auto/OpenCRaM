# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for task-list views: the Seen checkbox and the Active / Completed / Checked views.

Covers: the one-click endpoint (admin only, idempotent), the exact filters each view
stores and what they return, who may tick Seen, and who may hide a view from the tabs.
"""

import json
from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import CustomField, IssueView, Issue, Project, ProjectMember, State, User, WorkspaceMember
from plane.utils.task_list_views import ensure_task_list_views, seen_filter_key, view_definitions

TASK_LIST_URL = "/api/workspaces/{slug}/projects/{project_id}/views/task-list/"
VIEW_URL = "/api/workspaces/{slug}/projects/{project_id}/views/{pk}/"
ISSUES_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/"
ISSUE_URL = ISSUES_URL + "{pk}/"
# A card patch answers 204 (no body), like the other custom field tests expect.
OK = status.HTTP_204_NO_CONTENT


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Task List", identifier="TL", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def states(db, workspace, project):
    return {
        "todo": State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True),
        "doing": State.objects.create(name="Doing", project=project, workspace=workspace, group="started"),
        "done": State.objects.create(name="Done", project=project, workspace=workspace, group="completed"),
        "dropped": State.objects.create(name="Dropped", project=project, workspace=workspace, group="cancelled"),
    }


def _user(workspace, project, role, prefix):
    unique_id = uuid4().hex[:8]
    user = User.objects.create(
        email=f"{prefix}-{unique_id}@example.com",
        username=f"{prefix}_{unique_id}",
        first_name=prefix.title(),
        last_name="User",
        display_name=f"{prefix}{unique_id}",
    )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=role)
    return user


@pytest.fixture
def member(db, workspace, project):
    return _user(workspace, project, 15, "member")


@pytest.fixture
def guest(db, workspace, project):
    return _user(workspace, project, 5, "guest")


@pytest.fixture
def other_admin(db, workspace, project):
    return _user(workspace, project, 20, "admin")


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_issue(name, project, state, author):
    issue = Issue(name=name, project=project, workspace=project.workspace, state=state)
    issue.save(created_by_id=author.id)
    return issue


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


def _names(client, workspace, project, rich_filters):
    url = ISSUES_URL.format(slug=workspace.slug, project_id=project.id)
    response = client.get(url, {"filters": json.dumps(rich_filters)})
    assert response.status_code == status.HTTP_200_OK, response.data
    return {row["name"] for row in _rows(response.data)}


def _tick_seen(client, workspace, project, issue, field, checked):
    return client.patch(
        ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=issue.id),
        {"custom_fields": {str(field.id): checked}},
        format="json",
    )


@pytest.mark.contract
@pytest.mark.django_db
class TestTaskListViewsEndpoint:
    def test_admin_adds_the_field_and_three_views_once(self, session_client, workspace, project):
        url = TASK_LIST_URL.format(slug=workspace.slug, project_id=project.id)
        first = session_client.post(url)
        assert first.status_code == status.HTTP_201_CREATED, first.data
        assert first.data["field"]["name"] == "Seen"
        assert first.data["field"]["field_type"] == "checkbox"
        assert [v["name"] for v in first.data["views"]] == ["Active", "Completed", "Checked"]
        assert [v["is_hidden"] for v in first.data["views"]] == [False, False, False]
        assert first.data["created"] == ["Active", "Completed", "Checked"]

        second = session_client.post(url)
        assert second.status_code == status.HTTP_200_OK, second.data
        assert second.data["created"] == [] and second.data["updated"] == []
        assert [v["id"] for v in second.data["views"]] == [v["id"] for v in first.data["views"]]
        assert second.data["field"]["id"] == first.data["field"]["id"]
        assert CustomField.objects.filter(project=project, deleted_at__isnull=True).count() == 1
        assert IssueView.objects.filter(project=project, deleted_at__isnull=True).count() == 3

    def test_views_store_the_exact_filters(self, session_client, workspace, project):
        url = TASK_LIST_URL.format(slug=workspace.slug, project_id=project.id)
        data = session_client.post(url).data
        seen = seen_filter_key(data["field"]["id"])
        by_name = {v["name"]: v for v in data["views"]}
        assert by_name["Active"]["rich_filters"] == {
            "and": [{"state_group__in": ["backlog", "unstarted", "started", "cancelled"]}, {seen: False}]
        }
        assert by_name["Completed"]["rich_filters"] == {"and": [{"state_group__in": ["completed"]}, {seen: False}]}
        assert by_name["Checked"]["rich_filters"] == {"and": [{seen: True}]}
        # The Seen checkbox shows on the cards of every tab.
        for name in ("Active", "Completed", "Checked"):
            assert by_name[name]["display_properties"][f"cardfield_{data['field']['id']}"] is True
        assert view_definitions(data["field"]["id"]).keys() == {"Active", "Completed", "Checked"}

    def test_members_and_guests_cannot_add_them(self, workspace, project, member, guest):
        url = TASK_LIST_URL.format(slug=workspace.slug, project_id=project.id)
        for user in (member, guest):
            assert _client(user).post(url).status_code == status.HTTP_403_FORBIDDEN
        assert not IssueView.objects.filter(project=project).exists()

    def test_rerun_restores_a_changed_view_and_keeps_cards(self, workspace, project, create_user, states):
        card = _make_issue("Oil change", project, states["todo"], create_user)
        first = ensure_task_list_views(project, create_user)
        checked = first["views"]["Checked"]
        checked.is_hidden = True
        checked.rich_filters = {}
        checked.save()
        again = ensure_task_list_views(project, create_user)
        assert again["updated"] == ["Checked"] and again["created"] == []
        checked.refresh_from_db()
        assert checked.is_hidden is False
        assert checked.rich_filters == view_definitions(str(first["field"].id))["Checked"]["rich_filters"]
        card.refresh_from_db()
        assert card.state_id == states["todo"].id


@pytest.mark.contract
@pytest.mark.django_db
class TestTaskListFilters:
    @pytest.fixture
    def setup(self, workspace, project, create_user, states, session_client):
        result = ensure_task_list_views(project, create_user)
        field = result["field"]
        cards = {
            "todo": _make_issue("todo", project, states["todo"], create_user),
            "doing": _make_issue("doing", project, states["doing"], create_user),
            "done": _make_issue("done", project, states["done"], create_user),
            "done-seen": _make_issue("done-seen", project, states["done"], create_user),
            "dropped": _make_issue("dropped", project, states["dropped"], create_user),
            "todo-seen": _make_issue("todo-seen", project, states["todo"], create_user),
        }
        for key in ("done-seen", "todo-seen"):
            assert _tick_seen(session_client, workspace, project, cards[key], field, True).status_code == OK
        # An explicit "not seen" value must count the same as no value at all.
        assert _tick_seen(session_client, workspace, project, cards["done"], field, False).status_code == OK
        return {"field": field, "views": result["views"], "cards": cards}

    def _view_names(self, client, workspace, project, view):
        return _names(client, workspace, project, view.rich_filters)

    def test_active_is_not_completed_and_not_checked(self, session_client, workspace, project, setup):
        names = self._view_names(session_client, workspace, project, setup["views"]["Active"])
        assert names == {"todo", "doing", "dropped"}

    def test_all_shows_every_card(self, session_client, workspace, project, setup):
        assert _names(session_client, workspace, project, {}) == set(setup["cards"])

    def test_marking_completed_leaves_active_and_ticking_check_leaves_completed(
        self, session_client, workspace, project, setup, states
    ):
        views, field, card = setup["views"], setup["field"], setup["cards"]["todo"]
        active, completed, checked = (self._view_names(session_client, workspace, project, views[n]) for n in ("Active", "Completed", "Checked"))
        assert "todo" in active and "todo" not in completed and "todo" not in checked
        url = ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=card.id)
        assert session_client.patch(url, {"state_id": str(states["done"].id)}, format="json").status_code == OK
        assert "todo" not in self._view_names(session_client, workspace, project, views["Active"])
        assert "todo" in self._view_names(session_client, workspace, project, views["Completed"])
        assert _tick_seen(session_client, workspace, project, card, field, True).status_code == OK
        assert "todo" not in self._view_names(session_client, workspace, project, views["Active"])
        assert "todo" not in self._view_names(session_client, workspace, project, views["Completed"])
        assert "todo" in self._view_names(session_client, workspace, project, views["Checked"])
        assert "todo" in _names(session_client, workspace, project, {})

    def test_ticking_check_on_an_open_task_removes_it_from_active(self, session_client, workspace, project, setup):
        assert _tick_seen(session_client, workspace, project, setup["cards"]["doing"], setup["field"], True).status_code == OK
        assert "doing" not in self._view_names(session_client, workspace, project, setup["views"]["Active"])
        assert "doing" in self._view_names(session_client, workspace, project, setup["views"]["Checked"])

    def test_completed_is_done_and_not_seen(self, session_client, workspace, project, setup):
        names = self._view_names(session_client, workspace, project, setup["views"]["Completed"])
        assert names == {"done"}

    def test_checked_is_seen(self, session_client, workspace, project, setup):
        names = self._view_names(session_client, workspace, project, setup["views"]["Checked"])
        assert names == {"done-seen", "todo-seen"}

    def test_ticking_seen_moves_a_card_from_completed_to_checked(self, session_client, workspace, project, setup):
        completed, checked = setup["views"]["Completed"], setup["views"]["Checked"]
        card, field = setup["cards"]["done"], setup["field"]
        assert "done" in self._view_names(session_client, workspace, project, completed)
        assert _tick_seen(session_client, workspace, project, card, field, True).status_code == OK
        assert "done" not in self._view_names(session_client, workspace, project, completed)
        assert "done" in self._view_names(session_client, workspace, project, checked)
        # Unticking sends it back.
        assert _tick_seen(session_client, workspace, project, card, field, False).status_code == OK
        assert "done" in self._view_names(session_client, workspace, project, completed)
        assert "done" not in self._view_names(session_client, workspace, project, checked)

    def test_seen_true_and_false_filters(self, session_client, workspace, project, setup):
        seen = seen_filter_key(setup["field"].id)
        assert _names(session_client, workspace, project, {seen: True}) == {"done-seen", "todo-seen"}
        assert _names(session_client, workspace, project, {seen: "true"}) == {"done-seen", "todo-seen"}
        assert _names(session_client, workspace, project, {seen: False}) == {"todo", "doing", "done", "dropped"}
        assert _names(session_client, workspace, project, {seen: "false"}) == {"todo", "doing", "done", "dropped"}


@pytest.mark.contract
@pytest.mark.django_db
class TestWhoMayTickSeen:
    def test_member_can_tick_and_guest_cannot(self, workspace, project, create_user, states, member, guest):
        field = ensure_task_list_views(project, create_user)["field"]
        card = _make_issue("done", project, states["done"], create_user)
        assert _tick_seen(_client(guest), workspace, project, card, field, True).status_code == status.HTTP_403_FORBIDDEN
        assert not card.custom_field_values.filter(field=field, value_bool=True).exists()
        assert _tick_seen(_client(member), workspace, project, card, field, True).status_code == OK
        assert card.custom_field_values.filter(field=field, value_bool=True).exists()


@pytest.mark.contract
@pytest.mark.django_db
class TestHiddenViews:
    def test_hidden_flag_round_trips_and_admins_may_toggle_it(
        self, session_client, workspace, project, create_user, other_admin, member
    ):
        views = ensure_task_list_views(project, create_user)["views"]
        checked = views["Checked"]
        assert checked.is_hidden is False  # shown by default
        IssueView.objects.filter(pk=checked.id).update(is_hidden=True)
        url = VIEW_URL.format(slug=workspace.slug, project_id=project.id, pk=checked.id)
        assert session_client.get(url).data["is_hidden"] is True
        # Another admin may toggle is_hidden alone, nothing else.
        admin = _client(other_admin)
        assert admin.patch(url, {"is_hidden": False}, format="json").status_code == status.HTTP_200_OK
        assert IssueView.objects.get(pk=checked.id).is_hidden is False
        assert admin.patch(url, {"is_hidden": True, "name": "Renamed"}, format="json").status_code == 400
        assert IssueView.objects.get(pk=checked.id).name == "Checked"
        # A member who does not own the view may not.
        assert _client(member).patch(url, {"is_hidden": True}, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert IssueView.objects.get(pk=checked.id).is_hidden is False
        # The owner may.
        assert session_client.patch(url, {"is_hidden": True}, format="json").status_code == status.HTTP_200_OK
        assert IssueView.objects.get(pk=checked.id).is_hidden is True


@pytest.mark.contract
@pytest.mark.django_db
class TestPlusButtonChain:
    """The + at the left of a row makes a card at once, between the row and its neighbour.

    The web app sends the payload below (a blank name with blank_line, the row's state, sort_order
    midway to the neighbour). Five clicks in a row, each on the newest row, must give five blank
    lines in order. A blank name is refused without blank_line, except for a divider.
    """

    def _add_next_to(self, client, workspace, project, row, neighbour, below=True):
        gap = 65535
        if neighbour is not None:
            order = (row.sort_order + neighbour.sort_order) / 2
        else:
            order = row.sort_order + gap if below else row.sort_order - gap
        response = client.post(
            ISSUES_URL.format(slug=workspace.slug, project_id=project.id),
            {
                "name": "",
                "blank_line": True,
                "state_id": str(row.state_id),
                "priority": "none",
                "sort_order": order,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        return Issue.objects.get(pk=response.data["id"])

    def test_five_plus_clicks_in_a_row_make_five_normal_cards_in_order(
        self, session_client, workspace, project, create_user, states
    ):
        first = _make_issue("first", project, states["todo"], create_user)
        last = _make_issue("last", project, states["todo"], create_user)
        ensure_task_list_views(project, create_user)
        row, made = first, []
        for _ in range(5):
            row = self._add_next_to(session_client, workspace, project, row, None if row is last else last)
            made.append(row)
        assert [c.name for c in made] == [""] * 5
        assert {c.state_id for c in made} == {states["todo"].id}
        assert all(c.parent_id is None for c in made)
        orders = [first.sort_order] + [c.sort_order for c in made] + [last.sort_order]
        assert orders == sorted(orders) and len(set(orders)) == len(orders)
        listing = session_client.get(ISSUES_URL.format(slug=workspace.slug, project_id=project.id), {"order_by": "sort_order"})
        assert listing.status_code == status.HTTP_200_OK
        names = [r["name"] for r in _rows(listing.data)]
        assert names == ["first"] + [""] * 5 + ["last"]
        assert all(r["is_divider"] is False for r in _rows(listing.data))

    def test_five_clicks_on_the_last_row_keep_adding_below(self, session_client, workspace, project, create_user, states):
        row = _make_issue("only", project, states["todo"], create_user)
        count = 0
        for _ in range(5):
            row = self._add_next_to(session_client, workspace, project, row, None)
            count += 1
        assert Issue.objects.filter(project=project, name="").count() == count == 5

    def test_blank_name_without_blank_line_is_still_refused(self, session_client, workspace, project, states):
        url = ISSUES_URL.format(slug=workspace.slug, project_id=project.id)
        for name in ["", "   "]:
            response = session_client.post(url, {"name": name, "state_id": str(states["todo"].id)}, format="json")
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "name" in response.data
        assert not Issue.objects.filter(project=project).exists()

    def test_a_named_card_cannot_be_blanked_but_a_blank_line_can_be_named(
        self, session_client, workspace, project, create_user, states
    ):
        named = _make_issue("named", project, states["todo"], create_user)
        url = ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=named.id)
        assert session_client.patch(url, {"name": ""}, format="json").status_code == status.HTTP_400_BAD_REQUEST
        assert Issue.objects.get(pk=named.id).name == "named"
        blank = self._add_next_to(session_client, workspace, project, named, None)
        url = ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=blank.id)
        assert session_client.patch(url, {"name": "Sat 9/12-"}, format="json").status_code == OK
        assert Issue.objects.get(pk=blank.id).name == "Sat 9/12-"

    def test_dividers_may_be_blank_and_show_in_the_listing(self, session_client, workspace, project, states):
        url = ISSUES_URL.format(slug=workspace.slug, project_id=project.id)
        for name in ["Mon 9/14-", ""]:
            response = session_client.post(
                url, {"name": name, "is_divider": True, "state_id": str(states["todo"].id)}, format="json"
            )
            assert response.status_code == status.HTTP_201_CREATED, response.data
        assert Issue.objects.filter(project=project, is_divider=True).count() == 2
        rows = _rows(session_client.get(url).data)
        assert sorted(r["name"] for r in rows if r["is_divider"]) == ["", "Mon 9/14-"]
        # A named card turned into a divider and back.
        card = Issue.objects.filter(project=project, name="Mon 9/14-").first()
        card_url = ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=card.id)
        assert session_client.patch(card_url, {"is_divider": False}, format="json").status_code == OK
        assert Issue.objects.get(pk=card.id).is_divider is False
