# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Who may read, set and stop a repeat rule, and what the endpoints return."""

import datetime as dt
from types import SimpleNamespace

import pytest
from rest_framework import status

from plane.db.models import ProjectMember, WorkspaceMember
from plane.recurrence import tasks
from plane.recurrence.models import RepeatRule
from plane.recurrence.services import pick_timezone
from plane.sharing.models import AccessLevel, ShareTarget

from .conftest import client_for, make_issue, make_rule, make_user, restrict

WEEKLY = {"frequency": "weekly", "weekdays": [0], "time_of_day": "07:30", "timezone": "America/Chicago"}


def repeat_url(cast, issue):
    return f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/issues/{issue.id}/repeat/"


def list_url(cast):
    return f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/repeat-rules/"


@pytest.mark.contract
class TestPermissions:
    def test_member_sets_reads_and_stops(self, cast, template):
        response = cast.author_client.put(repeat_url(cast, template), WEEKLY, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        rule = response.data["rule"]
        assert rule["frequency"] == "weekly" and rule["weekdays"] == [0]
        assert rule["timezone"] == "America/Chicago" and rule["time_of_day"] == "07:30"
        assert rule["is_active"] is True and rule["next_run_at"]
        assert rule["owner"]["id"] == str(cast.author.id)

        response = cast.insider_client.get(repeat_url(cast, template))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["rule"]["id"] == rule["id"]

        response = cast.insider_client.delete(repeat_url(cast, template))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["rule"]["is_active"] is False
        assert response.data["rule"]["next_run_at"] is None

    def test_any_member_who_can_edit_may_change_it(self, cast, template):
        cast.author_client.put(repeat_url(cast, template), WEEKLY, format="json")
        response = cast.insider_client.put(repeat_url(cast, template), {**WEEKLY, "weekdays": [0, 3]}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["rule"]["weekdays"] == [0, 3]
        assert response.data["rule"]["owner"]["id"] == str(cast.author.id)  # copies still made as the first owner

    def test_turning_a_stopped_rule_back_on_hands_it_over(self, cast, template):
        cast.author_client.put(repeat_url(cast, template), WEEKLY, format="json")
        cast.author_client.delete(repeat_url(cast, template))
        response = cast.insider_client.put(repeat_url(cast, template), WEEKLY, format="json")
        assert response.data["rule"]["owner"]["id"] == str(cast.insider.id)

    def test_non_member_of_the_project_cannot(self, cast, template):
        response = cast.outsider_client.put(repeat_url(cast, template), WEEKLY, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert cast.outsider_client.get(repeat_url(cast, template)).status_code == status.HTTP_403_FORBIDDEN
        assert not RepeatRule.objects.filter(issue=template).exists()

    def test_stranger_cannot(self, cast, template):
        stranger = client_for(make_user("stranger"))
        assert stranger.put(repeat_url(cast, template), WEEKLY, format="json").status_code in (403, 404)

    def test_guest_can_neither_read_nor_set(self, cast, template):
        guest = make_user("guest")
        WorkspaceMember.objects.create(workspace=cast.workspace, member=guest, role=5)
        ProjectMember.objects.create(project=cast.alpha, member=guest, workspace=cast.workspace, role=5)
        client = client_for(guest)
        assert client.put(repeat_url(cast, template), WEEKLY, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert client.get(repeat_url(cast, template)).status_code == status.HTTP_403_FORBIDDEN
        assert client.get(list_url(cast)).status_code == status.HTTP_403_FORBIDDEN

    def test_hidden_card_answers_404(self, cast, template):
        restrict(cast, issue=template, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
        assert cast.insider_client.put(repeat_url(cast, template), WEEKLY, format="json").status_code == 404
        assert cast.insider_client.get(repeat_url(cast, template)).status_code == 404

    def test_view_only_share_cannot_set(self, cast, template):
        restrict(cast, issue=template, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
        assert cast.friend_client.get(repeat_url(cast, template)).status_code == 200
        assert cast.friend_client.put(repeat_url(cast, template), WEEKLY, format="json").status_code == 403

    def test_edit_share_can_set(self, cast, template):
        restrict(cast, issue=template, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.EDIT)])
        assert cast.friend_client.put(repeat_url(cast, template), WEEKLY, format="json").status_code == 200


@pytest.mark.contract
class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"frequency": "yearly"},
            {"frequency": "daily", "interval": 0},
            {"frequency": "daily", "interval": "x"},
            {"frequency": "weekly", "weekdays": [7]},
            {"frequency": "monthly", "month_day": 0},
            {"frequency": "monthly", "month_day": 32},
            {"frequency": "daily", "start_date": "2026-10-10", "end_date": "2026-10-01"},
            {"frequency": "daily", "time_of_day": "25:00"},
            {"frequency": "daily", "timezone": "Mars/Base"},
            {"frequency": "daily", "max_count": 0},
        ],
    )
    def test_bad_rules_are_refused(self, cast, template, body):
        response = cast.author_client.put(repeat_url(cast, template), body, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not RepeatRule.objects.filter(issue=template).exists()

    def test_monthly_last_day(self, cast, template):
        body = {"frequency": "monthly", "month_day": -1, "start_date": "2027-02-01", "timezone": "UTC"}
        response = cast.author_client.put(repeat_url(cast, template), body, format="json")
        assert response.status_code == 200
        assert response.data["rule"]["next_run_at"].startswith("2027-02-28T06:00")

    def test_rule_with_no_dates_left_is_saved_stopped(self, cast, template):
        body = {"frequency": "daily", "start_date": "2020-01-01", "end_date": "2020-01-02", "timezone": "UTC"}
        response = cast.author_client.put(repeat_url(cast, template), body, format="json")
        assert response.status_code == 200
        assert response.data["rule"]["is_active"] is False


@pytest.mark.unit
class TestTimezone:
    def test_workspace_zone_wins_over_unset_utc(self):
        ws = SimpleNamespace(timezone="America/Chicago")
        assert pick_timezone(None, ws, SimpleNamespace(user_timezone="UTC")) == "America/Chicago"

    def test_person_zone_when_workspace_is_utc(self):
        ws = SimpleNamespace(timezone="UTC")
        assert pick_timezone(None, ws, SimpleNamespace(user_timezone="America/Denver")) == "America/Denver"

    def test_browser_zone_is_the_last_choice(self):
        ws = SimpleNamespace(timezone="UTC")
        assert pick_timezone(None, ws, SimpleNamespace(user_timezone="UTC"), "America/Chicago") == "America/Chicago"
        assert pick_timezone(None, ws, SimpleNamespace(user_timezone="UTC"), "Not/AZone") == "UTC"

    def test_new_rule_uses_browser_zone_when_nothing_is_set(self, cast, template):
        body = {"frequency": "daily", "fallback_timezone": "America/Chicago"}
        response = cast.author_client.put(repeat_url(cast, template), body, format="json")
        assert response.data["rule"]["timezone"] == "America/Chicago"

    def test_asked_for_zone_wins(self):
        ws = SimpleNamespace(timezone="America/Chicago")
        assert pick_timezone("Europe/London", ws, None) == "Europe/London"


@pytest.mark.contract
class TestListsAndLinks:
    def test_project_list_hides_rules_on_hidden_cards(self, cast, template):
        secret = make_issue(cast, "Secret repeat")
        restrict(cast, issue=secret)
        make_rule(cast, template)
        make_rule(cast, secret)
        ids = {row["issue_id"] for row in cast.insider_client.get(list_url(cast)).data}
        assert ids == {str(template.id)}
        ids = {row["issue_id"] for row in cast.author_client.get(list_url(cast)).data}
        assert ids == {str(template.id), str(secret.id)}
        assert cast.outsider_client.get(list_url(cast)).status_code == status.HTTP_403_FORBIDDEN

    def test_copy_links_back_to_its_template(self, cast, template):
        rule = make_rule(cast, template)
        copy = tasks.run_rule(rule.id, dt.datetime(2026, 10, 19, 7, 0, tzinfo=dt.timezone.utc))
        data = cast.insider_client.get(repeat_url(cast, copy)).data
        assert data["rule"] is None
        assert data["copy_of"]["template"]["id"] == str(template.id)
        recent = cast.insider_client.get(repeat_url(cast, template)).data["rule"]["recent_copies"]
        assert [row["id"] for row in recent] == [str(copy.id)]
