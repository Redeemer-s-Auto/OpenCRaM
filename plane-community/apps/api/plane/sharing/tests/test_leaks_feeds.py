# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Leak tests for feeds: saved views, profiles, dashboards, activity, notifications,
favorites, recent visits and webhooks."""

import json
from datetime import timedelta
from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone

from plane.db.models import (
    EmailNotificationLog,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueComment,
    IssueSubscriber,
    Notification,
    UserFavorite,
    UserRecentVisit,
    Webhook,
)
from plane.sharing.tests.conftest import make_issue

MARK = b"TOPSECRET"


def hidden_from(response, item):
    """Nothing about ``item`` in the body: no id, no marker."""
    assert response.status_code == 200, response.content
    return MARK not in response.content and str(item.id).encode() not in response.content


def shown_to(response, item):
    assert response.status_code == 200, response.content
    return str(item.id).encode() in response.content


def assign(cast, issue, *users):
    for user in users:
        IssueAssignee.objects.create(issue=issue, assignee=user, project=cast.alpha, workspace=cast.workspace)


def activity(cast, issue, actor, **fields):
    return IssueActivity.objects.create(
        issue=issue,
        actor=actor,
        project=cast.alpha,
        workspace=cast.workspace,
        verb="updated",
        **fields,
    )


@pytest.mark.django_db
class TestSavedViewsAndProfiles:
    def test_global_view_issues(self, cast, secret_issue):
        url = f"/api/workspaces/{cast.workspace.slug}/issues/"
        assert hidden_from(cast.insider_client.get(url), secret_issue)
        assert shown_to(cast.friend_client.get(url), secret_issue)

    def test_global_view_sub_issue_count(self, cast, open_issue, secret_issue):
        Issue.objects.filter(pk=secret_issue.pk).update(parent=open_issue)
        url = f"/api/workspaces/{cast.workspace.slug}/issues/"

        def count(client):
            rows = client.get(url).json()["results"]
            return next(r["sub_issues_count"] for r in rows if r["id"] == str(open_issue.id))

        assert count(cast.insider_client) == 0
        assert count(cast.author_client) == 1

    def test_user_profile_issues(self, cast, secret_issue):
        url = f"/api/workspaces/{cast.workspace.slug}/user-issues/{cast.author.id}/"
        assert hidden_from(cast.insider_client.get(url), secret_issue)
        assert shown_to(cast.friend_client.get(url), secret_issue)

    def test_user_profile_stats(self, cast, secret_issue):
        assign(cast, secret_issue, cast.author)
        IssueSubscriber.objects.create(
            issue=secret_issue, subscriber=cast.author, project=cast.alpha, workspace=cast.workspace
        )
        url = f"/api/workspaces/{cast.workspace.slug}/user-stats/{cast.author.id}/"
        hidden = cast.insider_client.get(url).json()
        shown = cast.friend_client.get(url).json()
        for key in ("created_issues", "assigned_issues", "pending_issues", "subscribed_issues"):
            assert hidden[key] == 0, key
            assert shown[key] == 1, key
        assert hidden["state_distribution"] == [] and hidden["priority_distribution"] == []

    def test_user_profile_project_counts(self, cast, secret_issue):
        assign(cast, secret_issue, cast.author)
        url = f"/api/workspaces/{cast.workspace.slug}/user-profile/{cast.author.id}/"

        def counts(client):
            rows = client.get(url).json()["project_data"]
            row = next(r for r in rows if r["id"] == str(cast.alpha.id))
            return row["created_issues"], row["assigned_issues"], row["pending_issues"]

        assert counts(cast.insider_client) == (0, 0, 0)
        assert counts(cast.friend_client) == (1, 1, 1)


@pytest.mark.django_db
class TestActivity:
    @pytest.fixture
    def rows(self, cast, open_issue, secret_issue):
        on_secret = activity(cast, secret_issue, cast.author, field="name", new_value="TOPSECRET renamed")
        # Activity on a visible item that names the hidden one (parent change).
        points_at_secret = activity(
            cast, open_issue, cast.author, field="parent", new_value="ALP-9", new_identifier=secret_issue.id
        )
        plain = activity(cast, open_issue, cast.author, field="priority", new_value="high")
        return on_secret, points_at_secret, plain

    def ids(self, response):
        assert response.status_code == 200, response.content
        return {row["id"] for row in response.json()["results"]}

    def test_workspace_user_activity(self, cast, rows):
        on_secret, points_at_secret, plain = rows
        url = f"/api/workspaces/{cast.workspace.slug}/user-activity/{cast.author.id}/"
        response = cast.insider_client.get(url)
        assert self.ids(response) == {str(plain.id)}
        assert MARK not in response.content
        assert self.ids(cast.friend_client.get(url)) == {str(r.id) for r in rows}

    def test_export_user_activity(self, cast, rows):
        url = f"/api/workspaces/{cast.workspace.slug}/user-activity/{cast.author.id}/export/"
        body = {"date": str(timezone.now().date())}
        hidden = cast.insider_client.post(url, body, format="json")
        assert hidden.status_code == 200
        assert MARK not in hidden.content and b"ALP-9" not in hidden.content
        shown = cast.friend_client.post(url, body, format="json")
        assert MARK in shown.content

    def test_my_activities(self, cast, open_issue, secret_issue):
        # The insider touched the item before it was restricted.
        activity(cast, secret_issue, cast.insider, field="name", new_value="TOPSECRET by me")
        plain = activity(cast, open_issue, cast.insider, field="priority", new_value="low")
        response = cast.insider_client.get("/api/users/me/activities/")
        assert self.ids(response) == {str(plain.id)}
        assert MARK not in response.content
        by_author = activity(cast, secret_issue, cast.author, field="name", new_value="TOPSECRET")
        assert str(by_author.id) in self.ids(cast.author_client.get("/api/users/me/activities/"))

    def test_activity_graph(self, cast, secret_issue):
        activity(cast, secret_issue, cast.insider, field="name", new_value="x")
        url = f"/api/users/me/workspaces/{cast.workspace.slug}/activity-graph/"
        assert cast.insider_client.get(url).json() == []
        activity(cast, secret_issue, cast.friend, field="name", new_value="x")
        assert cast.friend_client.get(url).json() != []


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard_counts_and_lists(self, cast, secret_issue):
        Issue.objects.filter(pk=secret_issue.pk).update(
            target_date=(timezone.now() - timedelta(days=2)).date(),
            start_date=(timezone.now() + timedelta(days=2)).date(),
        )
        assign(cast, secret_issue, cast.insider, cast.friend)
        activity(cast, secret_issue, cast.insider, field="name", new_value="x")
        url = f"/api/users/me/workspaces/{cast.workspace.slug}/dashboard/"
        hidden = cast.insider_client.get(url)
        assert hidden.status_code == 200
        data = hidden.json()
        assert MARK not in hidden.content
        assert data["assigned_issues_count"] == 0 and data["pending_issues_count"] == 0
        assert data["issue_activities"] == [] and data["state_distribution"] == []
        shown = cast.friend_client.get(url)
        assert shown.json()["assigned_issues_count"] == 1
        assert MARK in shown.content

    def test_completed_graph(self, cast, secret_issue):
        Issue.objects.filter(pk=secret_issue.pk).update(completed_at=timezone.now())
        assign(cast, secret_issue, cast.insider, cast.friend)
        url = f"/api/users/me/workspaces/{cast.workspace.slug}/issues-completed-graph/?month={timezone.now().month}"
        assert cast.insider_client.get(url).json() == []
        assert cast.friend_client.get(url).json() != []


def notify(cast, receiver, issue, sender="in_app:issue_activities:subscribed"):
    return Notification.objects.create(
        workspace=cast.workspace,
        project=cast.alpha,
        receiver=receiver,
        triggered_by=cast.author,
        entity_identifier=issue.id,
        entity_name="issue",
        sender=sender,
        title="updated",
        data={"issue": {"id": str(issue.id), "name": issue.name}},
    )


@pytest.mark.django_db
class TestNotificationEndpoints:
    def base(self, cast):
        return f"/api/workspaces/{cast.workspace.slug}/users/notifications/"

    def test_list(self, cast, secret_issue):
        notify(cast, cast.insider, secret_issue)
        notify(cast, cast.insider, secret_issue, sender="in_app:issue_activities:mentioned")
        notify(cast, cast.friend, secret_issue)
        for query in ("", "?mentioned=true"):
            assert hidden_from(cast.insider_client.get(self.base(cast) + query), secret_issue)
        assert shown_to(cast.friend_client.get(self.base(cast)), secret_issue)

    def test_unread_counts(self, cast, secret_issue):
        notify(cast, cast.insider, secret_issue)
        notify(cast, cast.insider, secret_issue, sender="in_app:issue_activities:mentioned")
        notify(cast, cast.friend, secret_issue)
        hidden = cast.insider_client.get(self.base(cast) + "unread/").json()
        assert hidden == {"total_unread_notifications_count": 0, "mention_unread_notifications_count": 0}
        shown = cast.friend_client.get(self.base(cast) + "unread/").json()
        assert shown["total_unread_notifications_count"] == 1

    def test_single_notification_actions(self, cast, secret_issue):
        row = notify(cast, cast.insider, secret_issue)
        for path in (f"{row.id}/read/", f"{row.id}/archive/"):
            response = cast.insider_client.post(self.base(cast) + path)
            assert response.status_code == 404 and MARK not in response.content
        assert cast.insider_client.patch(self.base(cast) + f"{row.id}/", {}, format="json").status_code == 404
        friend_row = notify(cast, cast.friend, secret_issue)
        assert cast.friend_client.post(self.base(cast) + f"{friend_row.id}/read/").status_code == 200

    def test_mark_all_read_skips_hidden(self, cast, secret_issue, open_issue):
        hidden = notify(cast, cast.insider, secret_issue)
        visible = notify(cast, cast.insider, open_issue)
        assert cast.insider_client.post(self.base(cast) + "mark-all-read/", {}, format="json").status_code == 200
        hidden.refresh_from_db()
        visible.refresh_from_db()
        assert hidden.read_at is None and visible.read_at is not None


def run_notifications(cast, issue, activities, subscribers=()):
    from plane.bgtasks.notification_task import notifications

    for user in subscribers:
        IssueSubscriber.objects.create(issue=issue, subscriber=user, project=cast.alpha, workspace=cast.workspace)
    notifications(
        type="issue.activity.updated",
        issue_id=str(issue.id),
        project_id=str(cast.alpha.id),
        actor_id=str(cast.author.id),
        subscriber=False,
        issue_activities_created=json.dumps(activities),
        requested_data=json.dumps({}),
        current_instance=json.dumps({}),
    )


def state_activity(issue, **extra):
    return {
        "id": str(issue.id),
        "issue_detail": {"id": str(issue.id)},
        "field": "state",
        "verb": "updated",
        "comment": "updated the state",
        "actor_id": None,
        "old_value": "Todo",
        "new_value": "Done",
        "created_at": timezone.now().isoformat(),
        **extra,
    }


def received(user, issue):
    return (
        Notification.objects.filter(receiver=user, entity_identifier=issue.id).count(),
        EmailNotificationLog.objects.filter(receiver=user, entity_identifier=issue.id).count(),
    )


@pytest.mark.django_db
class TestNotificationTask:
    def test_subscribers_who_cannot_view_get_nothing(self, cast, secret_issue):
        run_notifications(cast, secret_issue, [state_activity(secret_issue)], [cast.insider, cast.friend])
        assert received(cast.insider, secret_issue) == (0, 0)
        assert received(cast.friend, secret_issue) == (1, 1)

    def test_comment_mentions(self, cast, secret_issue):
        mention = '<mention-component entity_name="user_mention" entity_identifier="{}"></mention-component>'
        html = mention.format(cast.insider.id) + mention.format(cast.friend.id)
        comment_activity = state_activity(
            secret_issue, field="comment", issue_comment=str(secret_issue.id), new_value=html, old_value=None
        )
        run_notifications(cast, secret_issue, [comment_activity])
        assert received(cast.insider, secret_issue)[0] == 0
        assert received(cast.friend, secret_issue)[0] == 1

    def test_activity_naming_hidden_item(self, cast, open_issue, secret_issue):
        parent_change = state_activity(
            open_issue, field="parent", old_value="", new_value="ALP-9", new_identifier=str(secret_issue.id)
        )
        run_notifications(cast, open_issue, [parent_change], [cast.insider, cast.friend])
        assert received(cast.insider, open_issue) == (0, 0)
        assert received(cast.friend, open_issue)[0] == 1


@pytest.mark.django_db
class TestEmailRecheck:
    def send(self, cast, issue, receiver, change=None):
        from plane.bgtasks import email_notification_task as task

        change = change or {
            "issue_activity": {
                "field": "state",
                "old_value": "Todo",
                "new_value": "Done",
                "activity_time": timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }
        }
        redis = mock.MagicMock()
        redis.get.return_value = b"http://plane.test"
        with (
            mock.patch.object(task, "redis_instance", return_value=redis),
            mock.patch.object(task, "acquire_lock", return_value=True),
            mock.patch.object(task, "release_lock"),
            mock.patch.object(task, "get_connection"),
            mock.patch.object(task, "get_email_configuration", return_value=("h", "u", "p", "25", "0", "0", "f@x")),
            mock.patch.object(task, "EmailMultiAlternatives") as email,
        ):
            task.send_email_notification(
                issue_id=str(issue.id),
                notification_data={str(cast.author.id): [change]},
                receiver_id=str(receiver.id),
                email_notification_ids=[],
            )
        return email.return_value.send.called

    def test_hidden_receiver_gets_no_email(self, cast, secret_issue):
        assert self.send(cast, secret_issue, cast.insider) is False
        assert self.send(cast, secret_issue, cast.friend) is True

    def test_change_naming_hidden_item_dropped(self, cast, open_issue, secret_issue):
        change = {
            "issue_activity": {
                "field": "parent",
                "old_value": "",
                "new_value": "ALP-9",
                "new_identifier": str(secret_issue.id),
                "activity_time": timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }
        }
        assert self.send(cast, open_issue, cast.insider, change) is False
        assert self.send(cast, open_issue, cast.friend, change) is True


@pytest.mark.django_db
class TestFavoritesAndRecent:
    def test_favorites_list(self, cast, secret_issue, secret_page):
        for user in (cast.insider, cast.friend):
            UserFavorite.objects.create(
                user=user, workspace=cast.workspace, entity_type="issue", entity_identifier=secret_issue.id
            )
            UserFavorite.objects.create(
                user=user,
                workspace=cast.workspace,
                project=cast.alpha,
                entity_type="page",
                entity_identifier=secret_page.id,
            )
        url = f"/api/workspaces/{cast.workspace.slug}/user-favorites/"
        response = cast.insider_client.get(url)
        assert hidden_from(response, secret_issue) and hidden_from(response, secret_page)
        shown = cast.friend_client.get(url)
        assert shown_to(shown, secret_page) and MARK in shown.content

    def test_cannot_favorite_hidden_page(self, cast, secret_page):
        url = f"/api/workspaces/{cast.workspace.slug}/user-favorites/"
        body = {"entity_type": "page", "entity_identifier": str(secret_page.id), "project_id": str(cast.alpha.id)}
        response = cast.insider_client.post(url, body, format="json")
        assert response.status_code == 404 and MARK not in response.content
        assert not UserFavorite.objects.filter(user=cast.insider).exists()
        shown = cast.friend_client.post(url, body, format="json")
        assert shown.status_code == 200 and MARK in shown.content

    def test_recent_visits(self, cast, secret_issue, secret_page):
        for user in (cast.insider, cast.friend):
            for name, item in (("issue", secret_issue), ("page", secret_page)):
                UserRecentVisit.objects.create(
                    user=user, workspace=cast.workspace, entity_name=name, entity_identifier=item.id
                )
        url = f"/api/workspaces/{cast.workspace.slug}/recent-visits/"
        response = cast.insider_client.get(url)
        assert hidden_from(response, secret_issue) and hidden_from(response, secret_page)
        shown = cast.friend_client.get(url)
        assert shown_to(shown, secret_issue) and MARK in shown.content


@pytest.mark.django_db
class TestWebhooks:
    @pytest.fixture
    def fetch(self, cast):
        Webhook.objects.create(
            workspace=cast.workspace, url="https://hooks.example.com/plane", issue=True, issue_comment=True
        )
        response = mock.MagicMock(status_code=200, headers={}, text="ok")
        with mock.patch("plane.bgtasks.webhook_task.pinned_fetch", return_value=response) as fetch:
            yield fetch

    def fire(self, cast, event, event_id, **fields):
        from plane.bgtasks.webhook_task import webhook_activity

        webhook_activity(
            event=event,
            verb=fields.pop("verb", "updated"),
            field=fields.pop("field", "name"),
            old_value=fields.pop("old_value", None),
            new_value=fields.pop("new_value", None),
            actor_id=str(cast.author.id),
            slug=cast.workspace.slug,
            current_site="http://plane.test",
            event_id=str(event_id),
            old_identifier=None,
            new_identifier=None,
        )

    def comment(self, cast, issue):
        return IssueComment.objects.create(
            issue=issue,
            project=cast.alpha,
            workspace=cast.workspace,
            actor=cast.author,
            comment_html="<p>TOPSECRET note</p>",
        )

    def test_off_by_default(self, cast, fetch, open_issue, secret_issue):
        from django.conf import settings

        assert settings.SHARING_WEBHOOK_INCLUDE_RESTRICTED is False
        self.fire(cast, "issue", secret_issue.id, new_value="TOPSECRET")
        self.fire(cast, "issue_comment", self.comment(cast, secret_issue).id)
        self.fire(cast, "issue", open_issue.id, field="parent", new_value=str(secret_issue.id))
        assert fetch.call_count == 0
        self.fire(cast, "issue", open_issue.id, new_value="renamed")
        assert fetch.call_count == 1
        assert "sharing" not in fetch.call_args.kwargs["json"]

    def test_on_sends_with_sharing(self, cast, fetch, secret_issue):
        with override_settings(SHARING_WEBHOOK_INCLUDE_RESTRICTED=True):
            self.fire(cast, "issue", secret_issue.id, new_value="TOPSECRET")
            self.fire(cast, "issue_comment", self.comment(cast, secret_issue).id)
        assert fetch.call_count == 2
        for call in fetch.call_args_list:
            sharing = call.kwargs["json"]["sharing"]
            assert sharing["restricted"] is True
            assert [s["target_id"] for s in sharing["shares"]] == [str(cast.friend.id)]
