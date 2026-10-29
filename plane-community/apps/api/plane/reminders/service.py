# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Setting, moving and reading date reminders.

Rules:
- A person may set a reminder only on a card they can see (board membership plus sharing rules).
- A reminder is personal. Nobody reads or changes another person's reminder.
- The time is worked out here from the mention (date, optional time, time zone) and the offset,
  so a moved date moves every reminder on that mention.
"""

import datetime
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue
from plane.relations.visibility import viewable_issues

from .models import DateReminder

# A date alone means this time of day.
DEFAULT_HOUR = 9
MAX_OFFSET_MINUTES = 60 * 24 * 30
# A reminder can be set at most this far ahead.
MAX_AHEAD = datetime.timedelta(days=366 * 5)
# A reminder that is already this late when the job finds it is dropped, not sent.
MAX_LATE = datetime.timedelta(days=7)
# Setting a reminder for "right now" is fine; this much slack covers clock drift and a slow click.
PAST_SLACK = datetime.timedelta(minutes=2)


def visible_issue(user, slug, issue_id):
    """The card, if ``user`` may see it; else None."""
    try:
        issue_id = uuid.UUID(str(issue_id))
    except (ValueError, TypeError):
        return None
    return viewable_issues(user, Issue.issue_objects.filter(workspace__slug=slug, pk=issue_id)).first()


def _zone(name):
    try:
        return ZoneInfo(str(name))
    except (ZoneInfoNotFoundError, ValueError, TypeError, OSError):
        raise ValidationError({"tz": "Not a time zone name, like America/Chicago."})


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError({"date": "Must be a date (YYYY-MM-DD)."})


def _time(value):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.time.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError({"time": "Must be a time (HH:MM)."})
    return parsed.replace(second=0, microsecond=0, tzinfo=None)


def _offset(value):
    if isinstance(value, bool):
        raise ValidationError({"offset_minutes": "Must be a whole number of minutes."})
    try:
        minutes = int(value)
    except (ValueError, TypeError):
        raise ValidationError({"offset_minutes": "Must be a whole number of minutes."})
    if not 0 <= minutes <= MAX_OFFSET_MINUTES:
        raise ValidationError({"offset_minutes": f"Must be between 0 and {MAX_OFFSET_MINUTES} minutes."})
    return minutes


def compute_remind_at(event_date, event_time, tz, offset_minutes):
    """UTC time to remind: the event (9:00 AM when it has no time) in ``tz``, minus the offset."""
    local = datetime.datetime.combine(event_date, event_time or datetime.time(DEFAULT_HOUR, 0), tzinfo=_zone(tz))
    return local.astimezone(datetime.timezone.utc) - datetime.timedelta(minutes=offset_minutes)


def editable_issue(user, slug, issue_id):
    """The card, if ``user`` may edit it; else None."""
    from plane.relations.visibility import editable_issues

    try:
        issue_id = uuid.UUID(str(issue_id))
    except (ValueError, TypeError):
        return None
    return editable_issues(user, Issue.issue_objects.filter(workspace__slug=slug, pk=issue_id)).first()


def move_mention(issue, mention_id, data):
    """The date or time in a mention changed: move every pending reminder on it. Returns how many moved."""
    event_date = _date(data.get("date"))
    event_time = _time(data.get("time"))
    tz = data.get("tz") or "UTC"
    _zone(tz)
    return move_event(issue, mention_id, event_date, event_time, tz)


def own_reminder(user, mention_id):
    return DateReminder.objects.filter(user=user, mention_id=mention_id).first()


@transaction.atomic
def set_reminder(user, issue, mention_id, data):
    """Create or change ``user``'s reminder on one mention. Moves everyone's on the same mention."""
    event_date = _date(data.get("date"))
    event_time = _time(data.get("time"))
    tz = data.get("tz") or "UTC"
    _zone(tz)
    offset = _offset(data.get("offset_minutes"))
    remind_at = compute_remind_at(event_date, event_time, tz, offset)
    now = timezone.now()
    if remind_at < now - PAST_SLACK:
        raise ValidationError({"offset_minutes": "That time has already passed."})
    if remind_at > now + MAX_AHEAD:
        raise ValidationError({"date": "That is too far ahead."})

    row, _ = DateReminder.objects.update_or_create(
        mention_id=mention_id,
        user=user,
        defaults={
            "workspace_id": issue.workspace_id,
            "issue": issue,
            "event_date": event_date,
            "event_time": event_time,
            "tz": tz,
            "offset_minutes": offset,
            "remind_at": remind_at,
            "sent_at": None,
            "stopped_at": None,
            "stop_reason": "",
        },
    )
    move_event(issue, mention_id, event_date, event_time, tz, skip=row.pk)
    return row


def move_event(issue, mention_id, event_date, event_time, tz, skip=None):
    """The mention changed: move the reminders other people set on it, if not sent yet."""
    others = DateReminder.objects.filter(
        mention_id=mention_id, issue=issue, sent_at__isnull=True, stopped_at__isnull=True
    ).exclude(pk=skip)
    for other in others:
        other.event_date, other.event_time, other.tz = event_date, event_time, tz
        other.remind_at = compute_remind_at(event_date, event_time, tz, other.offset_minutes)
        other.save(update_fields=["event_date", "event_time", "tz", "remind_at", "updated_at"])
    return others.count()


def reminders_for(user, issue):
    """``user``'s own reminders on one card."""
    return DateReminder.objects.filter(user=user, issue=issue)


def payload(row):
    return {
        "mention_id": str(row.mention_id),
        "issue_id": str(row.issue_id),
        "date": row.event_date.isoformat(),
        "time": row.event_time.strftime("%H:%M") if row.event_time else None,
        "tz": row.tz,
        "offset_minutes": row.offset_minutes,
        "remind_at": row.remind_at,
        "sent_at": row.sent_at,
        "stopped": bool(row.stopped_at),
        "stop_reason": row.stop_reason,
    }
