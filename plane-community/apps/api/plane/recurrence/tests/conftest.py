# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Repeat-rule tests reuse the sharing-rule cast (workspace, Alpha/Beta, author/insider/friend/outsider)."""

import datetime as dt

import pytest

from plane.recurrence.models import RepeatRule
from plane.sharing.tests.conftest import (  # noqa: F401  (fixtures and helpers)
    cast,
    client_for,
    eager_celery,
    make_issue,
    make_user,
    restrict,
)

UTC = dt.timezone.utc

# The moment the repeat tests pretend it is. Code under test reads the clock through
# ``django.utils.timezone.now``; tests that let it read the clock must use ``frozen_clock``
# so they do not start failing once the real date passes the dates written in them.
NOW = dt.datetime(2026, 10, 19, 6, 2, tzinfo=UTC)


@pytest.fixture
def frozen_clock(monkeypatch):
    """Pin ``django.utils.timezone.now`` (used by tasks and services) to ``NOW``."""
    from django.utils import timezone

    monkeypatch.setattr(timezone, "now", lambda: NOW)
    return NOW


def make_rule(cast, issue, actor=None, **fields):
    values = dict(
        workspace=cast.workspace,
        project=issue.project,
        issue=issue,
        frequency="daily",
        interval=1,
        time_of_day=dt.time(6, 0),
        timezone="UTC",
        start_date=dt.date(2026, 10, 1),
        next_run_at=dt.datetime(2026, 10, 19, 6, 0, tzinfo=UTC),
        created_by=actor or cast.author,
    )
    values.update(fields)
    return RepeatRule.objects.create(**values)


@pytest.fixture
def template(cast):
    return make_issue(cast, "Weekly numbers", priority="high", description_html="<p>Fill in the numbers</p>")
