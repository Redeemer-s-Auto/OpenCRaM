# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Date math for repeat rules. Pure functions: no database.

A rule is anything with these attributes: ``frequency``, ``interval``,
``weekdays``, ``month_day``, ``time_of_day``, ``timezone``, ``start_date``,
``end_date``, ``max_count`` (see ``RepeatRule``).

Dates are worked out in the rule's own time zone, then turned into UTC. A run
time that does not exist on a spring-forward day (e.g. 02:30) runs one hour
later; a run time that happens twice on a fall-back day runs the first time.
"""

import calendar
import datetime
from zoneinfo import ZoneInfo

UTC = datetime.timezone.utc
ONE_DAY = datetime.timedelta(days=1)

DAILY, WEEKLY, MONTHLY = "daily", "weekly", "monthly"
LAST_DAY = -1


def _interval(rule):
    return max(int(rule.interval or 1), 1)


def _weekdays(rule):
    return sorted(set(rule.weekdays or [])) or [rule.start_date.weekday()]


def _monday(day):
    return day - datetime.timedelta(days=day.weekday())


def _month_index(day):
    return day.year * 12 + day.month - 1


def month_target_day(rule, year, month):
    """The day number a monthly rule lands on in ``year``/``month``."""
    wanted = rule.month_day if rule.month_day else rule.start_date.day
    last = calendar.monthrange(year, month)[1]
    if wanted == LAST_DAY or wanted > last:
        return last
    return wanted


def matches(rule, day):
    """True when ``day`` (a local date) is one of the rule's run days."""
    if day < rule.start_date or (rule.end_date and day > rule.end_date):
        return False
    n = _interval(rule)
    if rule.frequency == DAILY:
        return (day - rule.start_date).days % n == 0
    if rule.frequency == WEEKLY:
        weeks = (_monday(day) - _monday(rule.start_date)).days // 7
        return weeks % n == 0 and day.weekday() in _weekdays(rule)
    if rule.frequency == MONTHLY:
        months = _month_index(day) - _month_index(rule.start_date)
        return months % n == 0 and day.day == month_target_day(rule, day.year, day.month)
    raise ValueError(f"Unknown frequency {rule.frequency!r}")


def next_date(rule, on_or_after):
    """First run day on or after ``on_or_after`` (a local date), or None past the end date."""
    day = max(on_or_after, rule.start_date)
    if rule.end_date and day > rule.end_date:
        return None
    n = _interval(rule)
    found = None
    if rule.frequency == DAILY:
        offset = (day - rule.start_date).days
        found = day + datetime.timedelta(days=(-offset) % n)
    elif rule.frequency == WEEKLY:
        for step in range(7 * (n + 1)):
            candidate = day + datetime.timedelta(days=step)
            if matches(rule, candidate):
                found = candidate
                break
    elif rule.frequency == MONTHLY:
        index = _month_index(day)
        start_index = _month_index(rule.start_date)
        for step in range(2 * n + 2):
            month = index + step
            if (month - start_index) % n:
                continue
            year, month0 = divmod(month, 12)
            candidate = datetime.date(year, month0 + 1, month_target_day(rule, year, month0 + 1))
            if candidate >= day:
                found = candidate
                break
    else:
        raise ValueError(f"Unknown frequency {rule.frequency!r}")
    if found is None or (rule.end_date and found > rule.end_date):
        return None
    return found


def zone(rule):
    try:
        return ZoneInfo(rule.timezone or "UTC")
    except Exception:
        return UTC


def run_at(rule, day):
    """UTC moment the rule runs on local date ``day``."""
    local = datetime.datetime.combine(day, rule.time_of_day, tzinfo=zone(rule))
    # Round-trip through UTC so a time skipped by spring-forward lands after the jump.
    return local.astimezone(UTC)


def local_date(rule, moment):
    return moment.astimezone(zone(rule)).date()


def next_run_after(rule, after, created_count=0):
    """First run moment strictly after ``after`` (aware datetime), or None when the rule is finished."""
    if rule.max_count and created_count >= rule.max_count:
        return None
    day = next_date(rule, local_date(rule, after))
    while day is not None:
        moment = run_at(rule, day)
        if moment > after:
            return moment
        day = next_date(rule, day + ONE_DAY)
    return None


def latest_due(rule, first_due, now):
    """The last run moment at or before ``now``, starting from ``first_due`` (itself due).

    Used to catch up once after downtime: missed slots are skipped, only the
    newest one makes a copy.
    """
    latest = first_due
    while True:
        following = next_run_after(rule, latest)
        if following is None or following > now:
            return latest
        latest = following
