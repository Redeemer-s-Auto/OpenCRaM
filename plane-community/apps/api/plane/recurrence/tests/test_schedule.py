# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Rule math: no database."""

import datetime as dt
from types import SimpleNamespace

import pytest

from plane.recurrence import schedule

UTC = dt.timezone.utc
CHI = "America/Chicago"


def rule(frequency="daily", start=dt.date(2026, 10, 19), **kw):
    values = dict(
        frequency=frequency,
        interval=1,
        weekdays=[],
        month_day=None,
        time_of_day=dt.time(6, 0),
        timezone=CHI,
        start_date=start,
        end_date=None,
        max_count=None,
    )
    values.update(kw)
    return SimpleNamespace(**values)


def utc(*args):
    return dt.datetime(*args, tzinfo=UTC)


def run_days(r, after, n):
    """The next ``n`` local run dates after ``after``."""
    out, moment = [], after
    for _ in range(n):
        moment = schedule.next_run_after(r, moment)
        if moment is None:
            break
        out.append(schedule.local_date(r, moment))
    return out


@pytest.mark.unit
class TestDaylightSaving:
    def test_spring_forward_keeps_local_time(self):
        r = rule(start=dt.date(2027, 3, 12))
        assert schedule.run_at(r, dt.date(2027, 3, 13)) == utc(2027, 3, 13, 12, 0)  # CST, UTC-6
        assert schedule.run_at(r, dt.date(2027, 3, 14)) == utc(2027, 3, 14, 11, 0)  # CDT, UTC-5

    def test_fall_back_keeps_local_time(self):
        r = rule(start=dt.date(2026, 10, 30))
        assert schedule.run_at(r, dt.date(2026, 10, 31)) == utc(2026, 10, 31, 11, 0)
        assert schedule.run_at(r, dt.date(2026, 11, 1)) == utc(2026, 11, 1, 12, 0)

    def test_skipped_time_runs_after_the_jump(self):
        r = rule(start=dt.date(2027, 3, 14), time_of_day=dt.time(2, 30))
        moment = schedule.run_at(r, dt.date(2027, 3, 14))
        assert moment == utc(2027, 3, 14, 8, 30)
        assert moment.astimezone(schedule.zone(r)).strftime("%H:%M") == "03:30"

    def test_repeated_time_runs_once_first_time(self):
        r = rule(start=dt.date(2026, 11, 1), time_of_day=dt.time(1, 30))
        assert schedule.run_at(r, dt.date(2026, 11, 1)) == utc(2026, 11, 1, 6, 30)  # 01:30 CDT
        # Exactly one run that day, then the next day's.
        first = schedule.next_run_after(r, utc(2026, 11, 1, 0, 0))
        second = schedule.next_run_after(r, first)
        assert first == utc(2026, 11, 1, 6, 30)
        assert second == utc(2026, 11, 2, 7, 30)  # 01:30 CST

    def test_daily_sequence_across_dst_has_no_gaps_or_doubles(self):
        r = rule(start=dt.date(2027, 3, 12))
        days = run_days(r, utc(2027, 3, 12, 0, 0), 5)
        assert days == [dt.date(2027, 3, d) for d in (12, 13, 14, 15, 16)]


@pytest.mark.unit
class TestMonthly:
    def test_31st_lands_on_last_day_of_short_months(self):
        r = rule("monthly", start=dt.date(2027, 1, 31), month_day=31)
        assert run_days(r, utc(2027, 1, 1), 4) == [
            dt.date(2027, 1, 31),
            dt.date(2027, 2, 28),
            dt.date(2027, 3, 31),
            dt.date(2027, 4, 30),
        ]

    def test_last_day_in_leap_and_common_years(self):
        r = rule("monthly", start=dt.date(2027, 1, 1), month_day=schedule.LAST_DAY)
        days = run_days(r, utc(2027, 1, 1), 14)
        assert dt.date(2027, 2, 28) in days
        assert dt.date(2028, 2, 29) in days
        assert all(d.month != (d + dt.timedelta(days=1)).month for d in days)

    def test_29th_in_february(self):
        r = rule("monthly", start=dt.date(2027, 1, 29), month_day=29)
        days = run_days(r, utc(2027, 1, 1), 14)
        assert dt.date(2027, 2, 28) in days
        assert dt.date(2028, 2, 29) in days

    def test_every_three_months(self):
        r = rule("monthly", start=dt.date(2026, 1, 15), interval=3, month_day=15)
        assert run_days(r, utc(2026, 1, 1), 4) == [
            dt.date(2026, 1, 15),
            dt.date(2026, 4, 15),
            dt.date(2026, 7, 15),
            dt.date(2026, 10, 15),
        ]

    def test_first_of_month(self):
        r = rule("monthly", start=dt.date(2026, 10, 19), month_day=1)
        assert run_days(r, utc(2026, 10, 19), 3) == [dt.date(2026, 11, 1), dt.date(2026, 12, 1), dt.date(2027, 1, 1)]


@pytest.mark.unit
class TestWeeklyAndDaily:
    def test_weekday_set_every_other_week(self):
        # 2026-10-19 is a Monday.
        r = rule("weekly", start=dt.date(2026, 10, 19), weekdays=[0, 2, 4], interval=2)
        assert run_days(r, utc(2026, 10, 19), 6) == [
            dt.date(2026, 10, 19),
            dt.date(2026, 10, 21),
            dt.date(2026, 10, 23),
            dt.date(2026, 11, 2),
            dt.date(2026, 11, 4),
            dt.date(2026, 11, 6),
        ]

    def test_weekly_defaults_to_start_weekday(self):
        r = rule("weekly", start=dt.date(2026, 10, 21))  # Wednesday
        assert run_days(r, utc(2026, 10, 1), 2) == [dt.date(2026, 10, 21), dt.date(2026, 10, 28)]

    def test_weekly_across_year_end(self):
        r = rule("weekly", start=dt.date(2026, 12, 28), weekdays=[0], interval=2)
        assert run_days(r, utc(2026, 12, 1), 3) == [dt.date(2026, 12, 28), dt.date(2027, 1, 11), dt.date(2027, 1, 25)]

    def test_every_three_days(self):
        r = rule(start=dt.date(2026, 10, 19), interval=3)
        assert run_days(r, utc(2026, 10, 20, 12), 3) == [dt.date(2026, 10, 22), dt.date(2026, 10, 25), dt.date(2026, 10, 28)]

    def test_strictly_after(self):
        r = rule(start=dt.date(2026, 10, 19))
        at = schedule.run_at(r, dt.date(2026, 10, 19))
        assert schedule.next_run_after(r, at) == schedule.run_at(r, dt.date(2026, 10, 20))
        assert schedule.next_run_after(r, at - dt.timedelta(seconds=1)) == at


@pytest.mark.unit
class TestEnds:
    def test_end_date_is_inclusive_then_finished(self):
        r = rule(start=dt.date(2026, 10, 19), end_date=dt.date(2026, 10, 21))
        assert run_days(r, utc(2026, 10, 1), 10) == [dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21)]

    def test_max_count(self):
        r = rule(start=dt.date(2026, 10, 19), max_count=2)
        assert schedule.next_run_after(r, utc(2026, 10, 1), created_count=1) is not None
        assert schedule.next_run_after(r, utc(2026, 10, 1), created_count=2) is None

    def test_monthly_end_date_before_next_month(self):
        r = rule("monthly", start=dt.date(2026, 10, 31), month_day=31, end_date=dt.date(2026, 11, 29))
        assert run_days(r, utc(2026, 10, 1), 5) == [dt.date(2026, 10, 31)]


@pytest.mark.unit
class TestCatchUp:
    def test_latest_due_skips_to_newest_missed_slot(self):
        r = rule(start=dt.date(2026, 10, 1))
        first = schedule.run_at(r, dt.date(2026, 10, 15))
        now = utc(2026, 10, 19, 15, 0)  # 10:00 CDT, after the 06:00 run
        assert schedule.latest_due(r, first, now) == schedule.run_at(r, dt.date(2026, 10, 19))

    def test_latest_due_before_todays_time(self):
        r = rule(start=dt.date(2026, 10, 1))
        first = schedule.run_at(r, dt.date(2026, 10, 15))
        now = utc(2026, 10, 19, 10, 0)  # 05:00 CDT, before the 06:00 run
        assert schedule.latest_due(r, first, now) == schedule.run_at(r, dt.date(2026, 10, 18))

    def test_latest_due_respects_end_date(self):
        r = rule(start=dt.date(2026, 10, 1), end_date=dt.date(2026, 10, 16))
        first = schedule.run_at(r, dt.date(2026, 10, 15))
        assert schedule.latest_due(r, first, utc(2026, 10, 30)) == schedule.run_at(r, dt.date(2026, 10, 16))
