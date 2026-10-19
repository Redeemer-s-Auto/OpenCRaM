# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Check, save and describe repeat rules."""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone as dj_timezone
from rest_framework.exceptions import ValidationError

from plane.recurrence import schedule
from plane.recurrence.models import LAST_DAY, Frequency, RepeatOccurrence, RepeatRule

MAX_INTERVAL = 365
MAX_COUNT = 10000
RECENT_COPIES = 5


def _valid_zone(name):
    if not name or not isinstance(name, str):
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def pick_timezone(requested, workspace, user, fallback=None):
    """Rule time zone: what was asked for, else the workspace's, else the person's profile,
    else ``fallback`` (the browser's zone, sent by the app), else UTC."""
    if _valid_zone(requested):
        return requested
    # "UTC" is Plane's unset default, so a real choice further down wins over it.
    for name in (getattr(workspace, "timezone", None), getattr(user, "user_timezone", None), fallback):
        if name and name != "UTC" and _valid_zone(name):
            return name
    return "UTC"


def _parse_date(value, field):
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError({field: "Use a date like 2026-01-31."})


def _parse_time(value):
    if value in (None, ""):
        return datetime.time(6, 0)
    try:
        parsed = datetime.time.fromisoformat(str(value))
    except ValueError:
        raise ValidationError({"time_of_day": "Use a time like 06:00."})
    return parsed.replace(second=0, microsecond=0, tzinfo=None)


def _int(value, field, low, high, allow_none=False):
    if value in (None, "") and allow_none:
        return None
    if isinstance(value, bool):
        raise ValidationError({field: "Must be a whole number."})
    if isinstance(value, float) and not value.is_integer():
        raise ValidationError({field: "Must be a whole number."})
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "Must be a whole number."})
    if number < low or number > high:
        raise ValidationError({field: f"Must be between {low} and {high}."})
    return number


def clean_rule(data, workspace, user):
    """Turn a request body into rule field values. Raises ValidationError."""
    if not isinstance(data, dict):
        raise ValidationError({"error": "Send an object."})
    frequency = data.get("frequency")
    if frequency not in Frequency.values:
        raise ValidationError({"frequency": "Pick daily, weekly or monthly."})
    tz = pick_timezone(data.get("timezone"), workspace, user, data.get("fallback_timezone"))
    if data.get("timezone") and not _valid_zone(data.get("timezone")):
        raise ValidationError({"timezone": "Unknown time zone."})

    today = dj_timezone.now().astimezone(ZoneInfo(tz)).date()
    start_date = _parse_date(data.get("start_date"), "start_date") or today
    end_date = _parse_date(data.get("end_date"), "end_date")
    if end_date and end_date < start_date:
        raise ValidationError({"end_date": "The end date is before the start date."})

    weekdays = []
    month_day = None
    if frequency == Frequency.WEEKLY:
        raw = data.get("weekdays") or []
        if not isinstance(raw, list):
            raise ValidationError({"weekdays": "Must be a list of day numbers (0 = Monday)."})
        weekdays = sorted({_int(d, "weekdays", 0, 6) for d in raw}) or [start_date.weekday()]
    elif frequency == Frequency.MONTHLY:
        raw = data.get("month_day")
        month_day = start_date.day if raw in (None, "") else _int(raw, "month_day", LAST_DAY, 31)
        if month_day == 0:
            raise ValidationError({"month_day": "Pick a day from 1 to 31, or the last day."})

    return {
        "frequency": frequency,
        "interval": _int(1 if data.get("interval") in (None, "") else data.get("interval"), "interval", 1, MAX_INTERVAL),
        "weekdays": weekdays,
        "month_day": month_day,
        "time_of_day": _parse_time(data.get("time_of_day")),
        "timezone": tz,
        "start_date": start_date,
        "end_date": end_date,
        "max_count": _int(data.get("max_count"), "max_count", 1, MAX_COUNT, allow_none=True),
    }


def save_rule(issue, data, user):
    """Create or replace the rule on ``issue``. Returns the rule.

    The person who turns a rule on is the one the copies are made as. Editing a
    running rule keeps that person; turning a stopped rule back on hands it to
    whoever does it.
    """
    rule = RepeatRule.objects.filter(issue=issue).first()
    if rule is not None and isinstance(data, dict) and not data.get("timezone"):
        data = {**data, "timezone": rule.timezone}  # editing keeps the rule's time zone
    values = clean_rule(data, issue.workspace, user)
    if rule is None:
        rule = RepeatRule(issue=issue, workspace_id=issue.workspace_id, project_id=issue.project_id, created_by=user)
    elif not rule.is_active:
        rule.created_by = user
        rule.created_count = 0
    if rule.created_by_id is None:
        rule.created_by = user
    for key, value in values.items():
        setattr(rule, key, value)
    rule.updated_by = user
    rule.is_active = True
    rule.stop_reason = ""
    rule.next_run_at = schedule.next_run_after(rule, dj_timezone.now(), rule.created_count)
    if rule.next_run_at is None:
        rule.is_active = False
        rule.stop_reason = "The rule has no run dates left."
    rule.save()
    return rule


def stop_rule(rule, user, reason="Stopped"):
    rule.is_active = False
    rule.next_run_at = None
    rule.stop_reason = reason
    rule.updated_by = user
    rule.save(update_fields=["is_active", "next_run_at", "stop_reason", "updated_by", "updated_at"])
    return rule


def _person(user):
    if user is None:
        return None
    return {"id": str(user.id), "name": user.display_name or user.first_name or ""}


def _issue_ref(issue):
    if issue is None:
        return None
    return {
        "id": str(issue.id),
        "name": issue.name,
        "sequence_id": issue.sequence_id,
        "project_id": str(issue.project_id),
    }


def describe_rule(rule, visible_issue_ids=None):
    copies = (
        RepeatOccurrence.objects.filter(rule=rule, issue__isnull=False, issue__deleted_at__isnull=True)
        .select_related("issue")
        .order_by("-scheduled_for")
    )
    if visible_issue_ids is not None:
        copies = copies.filter(issue_id__in=visible_issue_ids)
    return {
        "id": str(rule.id),
        "issue_id": str(rule.issue_id),
        "frequency": rule.frequency,
        "interval": rule.interval,
        "weekdays": rule.weekdays,
        "month_day": rule.month_day,
        "time_of_day": rule.time_of_day.strftime("%H:%M"),
        "timezone": rule.timezone,
        "start_date": rule.start_date.isoformat(),
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "max_count": rule.max_count,
        "created_count": rule.created_count,
        "next_run_at": rule.next_run_at.isoformat() if rule.next_run_at else None,
        "last_run_at": rule.last_run_at.isoformat() if rule.last_run_at else None,
        "is_active": rule.is_active,
        "stop_reason": rule.stop_reason,
        "owner": _person(rule.created_by),
        "recent_copies": [
            {"scheduled_for": occ.scheduled_for.isoformat(), **_issue_ref(occ.issue)} for occ in copies[:RECENT_COPIES]
        ],
    }


def describe_copy_of(issue, visible):
    """For a copy: the template card it was made from (if the viewer may see it)."""
    occurrence = RepeatOccurrence.objects.filter(issue=issue).select_related("rule__issue").first()
    if occurrence is None:
        return None
    template = occurrence.rule.issue
    if template is None or template.deleted_at is not None or not visible(template.id):
        return {"scheduled_for": occurrence.scheduled_for.isoformat(), "template": None}
    return {"scheduled_for": occurrence.scheduled_for.isoformat(), "template": _issue_ref(template)}
