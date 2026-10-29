# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The reminder job. Celery beat runs ``send_due_reminders`` every minute.

Safe to run twice, in parallel, or after a restart: each batch is taken under row locks
(``SKIP LOCKED``) and a row is marked sent in the same transaction as its notification, so a
reminder is sent once. A reminder is dropped (not sent) when it can no longer be honoured:
the person lost access, the card or the mention is gone, or it is too late to matter.
"""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from plane.db.models import Issue, Notification, WorkspaceMember
from plane.relations.visibility import viewable_issues
from plane.utils.exception_logger import log_exception

from .models import DateReminder
from .service import MAX_LATE

logger = logging.getLogger("plane.reminders")

BATCH = 200
SENDER = "in_app:issue_activities:reminder"


def _when_text(row):
    day = f"{row.event_date:%a, %b} {row.event_date.day}, {row.event_date.year}"
    if row.event_time:
        hour = row.event_time.hour % 12 or 12
        return f"{day} at {hour}:{row.event_time.minute:02d} {'AM' if row.event_time.hour < 12 else 'PM'}"
    return day


def _blocker(row, issue):
    """Why this reminder cannot be sent, or None."""
    if issue is None:
        return "The card is gone or hidden from this person."
    if f'data-mention-id="{row.mention_id}"' not in (issue.description_html or ""):
        return "The date was removed from the card."
    if not WorkspaceMember.objects.filter(
        workspace_id=row.workspace_id, member_id=row.user_id, is_active=True
    ).exists():
        return "The person is no longer in the workspace."
    return None


def _notification(row, issue):
    return Notification(
        workspace_id=row.workspace_id,
        project_id=issue.project_id,
        sender=SENDER,
        triggered_by=None,
        receiver_id=row.user_id,
        entity_identifier=issue.id,
        entity_name="issue",
        title=f"Reminder: {issue.name}",
        data={
            "issue": {
                "id": str(issue.id),
                "name": str(issue.name),
                "identifier": str(issue.project.identifier),
                "sequence_id": issue.sequence_id,
                "state_name": issue.state.name if issue.state_id else "",
                "state_group": issue.state.group if issue.state_id else "",
            },
            "issue_activity": {
                "id": str(row.id),
                "verb": "updated",
                "field": "reminder",
                "actor": "",
                "new_value": _when_text(row),
                "old_value": "",
                "old_identifier": None,
                "new_identifier": None,
            },
        },
    )


def _handle(row):
    issue = (
        viewable_issues(row.user, Issue.issue_objects.filter(pk=row.issue_id)).select_related("project", "state").first()
    )
    reason = _blocker(row, issue)
    now = timezone.now()
    if reason is None and row.remind_at < now - MAX_LATE:
        reason = "It was too late to send by the time the job ran."
    if reason:
        row.stopped_at, row.stop_reason = now, reason
        row.save(update_fields=["stopped_at", "stop_reason", "updated_at"])
        return False
    _notification(row, issue).save()
    row.sent_at = now
    row.save(update_fields=["sent_at", "updated_at"])
    return True


@shared_task
def send_due_reminders():
    """Send every reminder that is due. Returns how many were sent."""
    sent = 0
    try:
        while True:
            with transaction.atomic():
                due = list(
                    DateReminder.objects.select_for_update(skip_locked=True, of=("self",))
                    .filter(remind_at__lte=timezone.now(), sent_at__isnull=True, stopped_at__isnull=True)
                    .select_related("user")
                    .order_by("remind_at")[:BATCH]
                )
                for row in due:
                    try:
                        with transaction.atomic():
                            sent += _handle(row)
                    except Exception as error:  # one bad row must not hold up the rest
                        log_exception(error)
                        row.stopped_at, row.stop_reason = timezone.now(), "Error while sending."
                        row.save(update_fields=["stopped_at", "stop_reason", "updated_at"])
            if len(due) < BATCH:
                break
    except Exception as error:
        log_exception(error)
    return sent
