# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Date reminders: who may set one, how the time is worked out, and when the job sends or drops one."""

import datetime
import uuid
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from plane.db.models import Notification
from plane.reminders.models import DateReminder
from plane.reminders.tasks import send_due_reminders
from plane.sharing.models import ItemRestriction

from .conftest import client_for, make_user

LIST_URL = "/api/workspaces/{slug}/date-reminders/"
ONE_URL = "/api/workspaces/{slug}/date-reminders/{mention}/"
CHICAGO = ZoneInfo("America/Chicago")


def mention_html(mention_id):
    return f'<p>Call <span data-type="date-mention" data-date="2030-01-01" data-mention-id="{mention_id}">Jan 1</span></p>'


def soon(days=10):
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def put(cast, client, mention, card, **body):
    body.setdefault("date", soon())
    body.setdefault("tz", "America/Chicago")
    body.setdefault("offset_minutes", 0)
    return client.put(
        ONE_URL.format(slug=cast.workspace.slug, mention=mention), {"issue_id": str(card.id), **body}, format="json"
    )


@pytest.fixture
def card(cast):
    return cast.card(cast.alpha, "Call Mr. Lee", description_html=mention_html("placeholder"))


def due_row(cast, card, user, mention=None, **extra):
    mention = mention or uuid.uuid4()
    card.description_html = mention_html(mention)
    card.save()
    now = timezone.now()
    return DateReminder.objects.create(
        workspace=cast.workspace,
        issue=card,
        user=user,
        mention_id=mention,
        event_date=(now + datetime.timedelta(hours=1)).date(),
        event_time=datetime.time(9, 30),
        tz="UTC",
        offset_minutes=0,
        remind_at=extra.pop("remind_at", now - datetime.timedelta(minutes=1)),
        **extra,
    )


# ---------------------------------------------------------------- setting a reminder


def test_a_date_alone_means_nine_in_the_morning_in_the_zone(cast, card):
    mention = uuid.uuid4()
    response = put(cast, cast.member_client, mention, card, offset_minutes=1440)
    assert response.status_code == 200, response.data
    day = datetime.date.fromisoformat(soon()) - datetime.timedelta(days=1)
    expected = datetime.datetime.combine(day, datetime.time(9, 0), tzinfo=CHICAGO).astimezone(datetime.timezone.utc)
    assert DateReminder.objects.get(mention_id=mention, user=cast.member).remind_at == expected
    assert response.data["time"] is None and response.data["offset_minutes"] == 1440


def test_a_date_with_a_time_uses_that_time(cast, card):
    mention = uuid.uuid4()
    response = put(cast, cast.member_client, mention, card, time="14:30", offset_minutes=60)
    assert response.status_code == 200, response.data
    event = datetime.datetime.combine(
        datetime.date.fromisoformat(soon()), datetime.time(14, 30), tzinfo=CHICAGO
    ).astimezone(datetime.timezone.utc)
    assert DateReminder.objects.get(mention_id=mention, user=cast.member).remind_at == event - datetime.timedelta(
        minutes=60
    )
    assert response.data["time"] == "14:30"


def test_setting_it_again_changes_the_same_reminder(cast, card):
    mention = uuid.uuid4()
    put(cast, cast.member_client, mention, card, offset_minutes=0)
    put(cast, cast.member_client, mention, card, offset_minutes=60)
    assert DateReminder.objects.filter(mention_id=mention, user=cast.member).count() == 1
    assert DateReminder.objects.get(mention_id=mention, user=cast.member).offset_minutes == 60


@pytest.mark.parametrize(
    "body",
    [
        {"date": "yesterday"},
        {"date": "2001-01-01"},
        {"date": "2999-01-01"},
        {"time": "25:99"},
        {"tz": "Mars/Base"},
        {"offset_minutes": -5},
        {"offset_minutes": "soon"},
        {"offset_minutes": 10**7},
        {"offset_minutes": True},
        {"offset_minutes": None},
    ],
)
def test_bad_reminders_are_refused(cast, card, body):
    assert put(cast, cast.member_client, uuid.uuid4(), card, **body).status_code == 400
    assert not DateReminder.objects.exists()


def test_cannot_set_a_reminder_on_a_card_you_cannot_see(cast):
    secret = cast.card(cast.alpha, "Secret")
    ItemRestriction.objects.create(workspace=cast.workspace, issue=secret)
    response = put(cast, cast.member_client, uuid.uuid4(), secret)
    assert response.status_code == 403 and response.data == {"error": "no_access"}
    assert cast.member_client.get(LIST_URL.format(slug=cast.workspace.slug), {"issue_id": str(secret.id)}).status_code == 403
    assert not DateReminder.objects.exists()


def test_unknown_or_foreign_card_is_the_same_as_hidden(cast):
    beta_card = cast.card(cast.beta, "Beta")
    # alpha_only is not in Beta.
    assert put(cast, cast.alpha_only_client, uuid.uuid4(), beta_card).status_code == 403
    response = cast.member_client.put(
        ONE_URL.format(slug=cast.workspace.slug, mention=uuid.uuid4()),
        {"issue_id": "00000000-0000-0000-0000-000000000000", "date": soon(), "offset_minutes": 0},
        format="json",
    )
    assert response.status_code == 403


def test_outsider_and_anonymous_are_refused(cast, card):
    outsider = client_for(make_user("outsider"))
    assert put(cast, outsider, uuid.uuid4(), card).status_code == 403
    from rest_framework.test import APIClient

    assert put(cast, APIClient(), uuid.uuid4(), card).status_code in (401, 403)


def test_a_mention_id_stays_with_its_card(cast, card):
    other = cast.card(cast.alpha, "Other card")
    mention = uuid.uuid4()
    put(cast, cast.member_client, mention, card)
    assert put(cast, cast.member_client, mention, other).status_code == 400


# ---------------------------------------------------------------- reminders are personal


def test_people_see_and_remove_only_their_own(cast, card):
    mention = uuid.uuid4()
    put(cast, cast.member_client, mention, card)
    mine = cast.member_client.get(LIST_URL.format(slug=cast.workspace.slug), {"issue_id": str(card.id)})
    assert [r["mention_id"] for r in mine.data] == [str(mention)]
    theirs = cast.admin_client.get(LIST_URL.format(slug=cast.workspace.slug), {"issue_id": str(card.id)})
    assert theirs.data == []
    assert cast.admin_client.delete(ONE_URL.format(slug=cast.workspace.slug, mention=mention)).status_code == 204
    assert DateReminder.objects.filter(mention_id=mention, user=cast.member).exists()
    assert cast.member_client.delete(ONE_URL.format(slug=cast.workspace.slug, mention=mention)).status_code == 204
    assert not DateReminder.objects.filter(mention_id=mention).exists()


def test_moving_the_date_moves_everyone_elses_pending_reminder(cast, card):
    mention = uuid.uuid4()
    put(cast, cast.member_client, mention, card, offset_minutes=60)
    put(cast, cast.admin_client, mention, card, offset_minutes=0)
    later = soon(20)
    put(cast, cast.admin_client, mention, card, date=later, offset_minutes=0)
    moved = DateReminder.objects.get(mention_id=mention, user=cast.member)
    assert moved.event_date.isoformat() == later and moved.offset_minutes == 60
    event = datetime.datetime.combine(datetime.date.fromisoformat(later), datetime.time(9, 0), tzinfo=CHICAGO)
    assert moved.remind_at == event.astimezone(datetime.timezone.utc) - datetime.timedelta(minutes=60)


def test_moving_the_date_leaves_a_sent_reminder_alone(cast, card):
    mention = uuid.uuid4()
    put(cast, cast.member_client, mention, card)
    DateReminder.objects.filter(mention_id=mention, user=cast.member).update(sent_at=timezone.now())
    before = DateReminder.objects.get(mention_id=mention, user=cast.member).remind_at
    put(cast, cast.admin_client, mention, card, date=soon(30))
    assert DateReminder.objects.get(mention_id=mention, user=cast.member).remind_at == before


# ---------------------------------------------------------------- the job


def test_a_due_reminder_becomes_one_notification(cast, card):
    row = due_row(cast, card, cast.member)
    assert send_due_reminders() == 1
    row.refresh_from_db()
    assert row.sent_at is not None and row.stopped_at is None
    note = Notification.objects.get(receiver=cast.member)
    assert note.sender == "in_app:issue_activities:reminder" and note.triggered_by is None
    assert note.entity_identifier == card.id and note.entity_name == "issue"
    assert note.title == "Reminder: Call Mr. Lee"
    assert note.data["issue_activity"]["field"] == "reminder"
    assert note.data["issue_activity"]["new_value"].endswith("at 9:30 AM")
    assert note.data["issue"]["identifier"] == "ALP"
    # Again: nothing more is sent.
    assert send_due_reminders() == 0
    assert Notification.objects.filter(receiver=cast.member).count() == 1


def test_a_reminder_that_is_not_due_waits(cast, card):
    row = due_row(cast, card, cast.member, remind_at=timezone.now() + datetime.timedelta(hours=2))
    assert send_due_reminders() == 0
    row.refresh_from_db()
    assert row.sent_at is None and row.stopped_at is None and not Notification.objects.exists()


def test_each_person_gets_their_own(cast, card):
    mention = uuid.uuid4()
    due_row(cast, card, cast.member, mention=mention)
    due_row(cast, card, cast.admin, mention=mention)
    assert send_due_reminders() == 2
    assert Notification.objects.filter(receiver=cast.member).count() == 1
    assert Notification.objects.filter(receiver=cast.admin).count() == 1


def test_a_removed_date_stops_the_reminder(cast, card):
    row = due_row(cast, card, cast.member)
    card.description_html = "<p>No date here any more</p>"
    card.save()
    assert send_due_reminders() == 0
    row.refresh_from_db()
    assert row.sent_at is None and row.stopped_at is not None and "removed" in row.stop_reason
    assert not Notification.objects.exists()


def test_losing_access_stops_the_reminder(cast, card):
    row = due_row(cast, card, cast.member)
    ItemRestriction.objects.create(workspace=cast.workspace, issue=card)
    assert send_due_reminders() == 0
    row.refresh_from_db()
    assert row.stopped_at is not None and not Notification.objects.exists()


def test_a_deleted_card_stops_the_reminder(cast, card):
    row = due_row(cast, card, cast.member)
    card.delete()
    assert send_due_reminders() == 0
    row.refresh_from_db()
    assert row.stopped_at is not None and not Notification.objects.exists()


def test_an_archived_card_stops_the_reminder(cast, card):
    row = due_row(cast, card, cast.member)
    card.archived_at = timezone.now().date()
    card.save()
    assert send_due_reminders() == 0
    row.refresh_from_db()
    assert row.stopped_at is not None


def test_a_reminder_found_far_too_late_is_dropped(cast, card):
    row = due_row(cast, card, cast.member, remind_at=timezone.now() - datetime.timedelta(days=8))
    assert send_due_reminders() == 0
    row.refresh_from_db()
    assert row.stopped_at is not None and "too late" in row.stop_reason and not Notification.objects.exists()


def test_a_reminder_late_by_a_few_hours_is_still_sent(cast, card):
    due_row(cast, card, cast.member, remind_at=timezone.now() - datetime.timedelta(hours=5))
    assert send_due_reminders() == 1


def test_a_person_who_left_the_workspace_gets_nothing(cast, card):
    row = due_row(cast, card, cast.member)
    from plane.db.models import WorkspaceMember

    WorkspaceMember.objects.filter(workspace=cast.workspace, member=cast.member).update(is_active=False)
    assert send_due_reminders() == 0
    row.refresh_from_db()
    assert row.stopped_at is not None and not Notification.objects.exists()


def test_a_stopped_reminder_comes_back_when_set_again(cast, card):
    mention = uuid.uuid4()
    row = due_row(cast, card, cast.member, mention=mention)
    card.description_html = "<p>gone</p>"
    card.save()
    send_due_reminders()
    card.description_html = mention_html(mention)
    card.save()
    assert put(cast, cast.member_client, mention, card).status_code == 200
    row.refresh_from_db()
    assert row.stopped_at is None and row.stop_reason == "" and row.sent_at is None


# ---------------------------------------------------------------- moving a mention


def move(cast, client, mention, card, **body):
    body.setdefault("date", soon(20))
    body.setdefault("tz", "America/Chicago")
    return client.post(
        ONE_URL.format(slug=cast.workspace.slug, mention=mention) + "move/",
        {"issue_id": str(card.id), **body},
        format="json",
    )


def test_an_editor_moves_every_pending_reminder_on_a_mention(cast, card):
    mention = uuid.uuid4()
    put(cast, cast.admin_client, mention, card, offset_minutes=0)
    put(cast, cast.member_client, mention, card, offset_minutes=60)
    DateReminder.objects.filter(mention_id=mention, user=cast.admin).update(sent_at=timezone.now())
    sent_at = DateReminder.objects.get(mention_id=mention, user=cast.admin).remind_at
    response = move(cast, cast.member_client, mention, card, date=soon(20), time="08:00")
    assert response.status_code == 200 and response.data == {"moved": 1}
    moved = DateReminder.objects.get(mention_id=mention, user=cast.member)
    event = datetime.datetime.combine(datetime.date.fromisoformat(soon(20)), datetime.time(8, 0), tzinfo=CHICAGO)
    assert moved.remind_at == event.astimezone(datetime.timezone.utc) - datetime.timedelta(minutes=60)
    assert DateReminder.objects.get(mention_id=mention, user=cast.admin).remind_at == sent_at


def test_a_reader_cannot_move_reminders(cast, card):
    from plane.db.models import ProjectMember, WorkspaceMember

    cast.alpha.guest_view_all_features = True
    cast.alpha.save()
    guest = make_user("guest")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=guest, role=5)
    ProjectMember.objects.create(project=cast.alpha, member=guest, workspace=cast.workspace, role=5)
    mention = uuid.uuid4()
    put(cast, cast.member_client, mention, card)
    before = DateReminder.objects.get(mention_id=mention).remind_at
    assert move(cast, client_for(guest), mention, card).status_code == 403
    assert DateReminder.objects.get(mention_id=mention).remind_at == before


def test_cannot_move_reminders_on_a_hidden_card(cast, card):
    mention = uuid.uuid4()
    put(cast, cast.admin_client, mention, card)
    ItemRestriction.objects.create(workspace=cast.workspace, issue=card)
    assert move(cast, cast.member_client, mention, card).status_code == 403


@pytest.mark.parametrize("body", [{"date": "nope"}, {"time": "99:99"}, {"tz": "Mars/Base"}])
def test_bad_move_is_refused(cast, card, body):
    assert move(cast, cast.member_client, uuid.uuid4(), card, **body).status_code == 400


def test_a_move_on_a_card_does_not_touch_the_same_id_on_another_card(cast, card):
    other = cast.card(cast.alpha, "Other")
    mention = uuid.uuid4()
    put(cast, cast.admin_client, mention, card)
    before = DateReminder.objects.get(mention_id=mention).remind_at
    assert move(cast, cast.member_client, mention, other).data == {"moved": 0}
    assert DateReminder.objects.get(mention_id=mention).remind_at == before
