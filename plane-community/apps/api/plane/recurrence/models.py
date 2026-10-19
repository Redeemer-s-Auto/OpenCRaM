# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Repeat rules for work items.

A ``RepeatRule`` turns one work item (the template) into a schedule. Each time
the schedule comes due, a background job makes a new work item copied from the
template and records it as a ``RepeatOccurrence``. The (rule, scheduled_for)
pair is unique, so one slot can never make two copies.
"""

import datetime
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Frequency(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"


LAST_DAY = -1  # month_day value meaning "last day of the month"


class RepeatRule(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # The person the copies are made as. Set when the rule is first turned on.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="repeat_rules")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="repeat_rules")
    issue = models.OneToOneField("db.Issue", on_delete=models.CASCADE, related_name="repeat_rule")

    frequency = models.CharField(max_length=16, choices=Frequency.choices)
    interval = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(365)]
    )
    # 0 = Monday ... 6 = Sunday. Weekly rules only.
    weekdays = models.JSONField(default=list, blank=True)
    # 1..31, or -1 for the last day. Monthly rules only.
    month_day = models.SmallIntegerField(null=True, blank=True)
    time_of_day = models.TimeField(default=datetime.time(6, 0))
    timezone = models.CharField(max_length=64, default="UTC")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    max_count = models.PositiveIntegerField(null=True, blank=True)

    created_count = models.PositiveIntegerField(default=0)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    stop_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "recurrence_rules"
        indexes = [models.Index(fields=["is_active", "next_run_at"], name="recurrence_rule_due_idx")]

    def __str__(self):
        return f"{self.frequency} repeat of {self.issue_id}"


class RepeatOccurrence(models.Model):
    """One slot of a rule that has been handled (normally: one copy made)."""

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    rule = models.ForeignKey(RepeatRule, on_delete=models.CASCADE, related_name="occurrences")
    scheduled_for = models.DateTimeField()
    issue = models.OneToOneField(
        "db.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="repeat_occurrence"
    )

    class Meta:
        db_table = "recurrence_occurrences"
        ordering = ("-scheduled_for",)
        constraints = [
            models.UniqueConstraint(fields=["rule", "scheduled_for"], name="recurrence_occurrence_rule_slot_unique"),
        ]
