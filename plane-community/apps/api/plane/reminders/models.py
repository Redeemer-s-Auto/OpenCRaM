# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A reminder a person set on a date mention in a card body.

The date mention itself lives in the card body (its id, date and time). The reminder is
personal: one row per person per mention, so each person sets their own and nobody sees
anyone else's. The scheduled job (``plane.reminders.tasks``) turns due rows into
notifications.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class DateReminder(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    # The id stored in the date mention in the card body.
    mention_id = models.UUIDField()
    # What the mention says: a date, and a time if it has one. A date alone means 9:00 AM in ``tz``.
    event_date = models.DateField()
    event_time = models.TimeField(null=True, blank=True)
    tz = models.CharField(max_length=64, default="UTC")
    # How long before the event to remind, in minutes (0 = at the event).
    offset_minutes = models.PositiveIntegerField(default=0)
    # When to remind, in UTC. Worked out from the fields above.
    remind_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    # Set when the reminder was dropped without being sent, with the reason.
    stopped_at = models.DateTimeField(null=True, blank=True)
    stop_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "date_reminders"
        ordering = ("remind_at",)
        constraints = [
            models.UniqueConstraint(fields=["mention_id", "user"], name="date_reminder_unique_mention_user"),
        ]
        indexes = [
            models.Index(
                fields=["remind_at"],
                condition=Q(sent_at__isnull=True, stopped_at__isnull=True),
                name="date_reminder_due_idx",
            ),
            models.Index(fields=["issue", "user"], name="date_reminder_issue_user_idx"),
        ]

    def __str__(self):
        return f"reminder {self.id} for {self.user_id} at {self.remind_at}"
