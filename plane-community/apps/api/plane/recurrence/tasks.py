# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""The repeat job. Celery beat runs ``run_due_repeats`` every few minutes.

Safe to run twice, in parallel, or after a restart:
- each rule is handled under a row lock (``SKIP LOCKED``: a second worker skips it);
- each slot is recorded in ``RepeatOccurrence`` (unique per rule and slot) in the
  same transaction as the copy, so a slot that already made its copy never
  makes another, and a crash mid-copy leaves nothing behind;
- after downtime only the newest missed slot makes a copy; the rule then moves
  on to its first future slot.
"""

import datetime
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from plane.db.models import ProjectMember
from plane.recurrence import schedule
from plane.recurrence.copier import make_copy
from plane.recurrence.models import RepeatOccurrence, RepeatRule
from plane.sharing.models import AccessLevel
from plane.sharing.visibility import can_reach, issue_access_level
from plane.utils.exception_logger import log_exception

logger = logging.getLogger("plane.recurrence")

BATCH = 200
RETRY_AFTER = datetime.timedelta(hours=1)  # a run that failed is tried again this much later


def _stop(rule, reason):
    rule.is_active = False
    rule.next_run_at = None
    rule.stop_reason = reason
    rule.save(update_fields=["is_active", "next_run_at", "stop_reason", "updated_at"])


def _blocker(rule):
    """Why the rule cannot run any more, or None."""
    template = rule.issue
    if template.deleted_at is not None:
        return "The card was deleted."
    if template.archived_at is not None:
        return "The card was archived."
    if template.project.archived_at is not None:
        return "The project was archived."
    actor = rule.created_by
    if actor is None or not actor.is_active:
        return "The person who set the repeat is no longer here."
    if not ProjectMember.objects.filter(
        project_id=rule.project_id, member=actor, role__gte=15, is_active=True, deleted_at__isnull=True
    ).exists():
        return "The person who set the repeat is no longer a member of this project."
    if not can_reach(issue_access_level(actor, template.id), AccessLevel.EDIT):
        return "The person who set the repeat can no longer edit the card."
    return None


def run_rule(rule_id, now=None):
    """Handle one due rule. Returns the new work item, or None."""
    now = now or timezone.now()
    with transaction.atomic():
        rule = (
            RepeatRule.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(pk=rule_id, is_active=True, next_run_at__isnull=False, next_run_at__lte=now)
            .select_related("issue", "issue__project", "issue__project__workspace", "created_by")
            .first()
        )
        if rule is None:
            return None  # not due, stopped, or another worker has it
        reason = _blocker(rule)
        if reason:
            _stop(rule, reason)
            return None

        slot = schedule.latest_due(rule, rule.next_run_at, now)
        occurrence, created = RepeatOccurrence.objects.get_or_create(rule=rule, scheduled_for=slot)
        copy = None
        if created:
            delta = schedule.local_date(rule, slot) - rule.start_date
            copy = make_copy(rule.issue, delta, rule.created_by)
            occurrence.issue = copy
            occurrence.save(update_fields=["issue"])
            rule.created_count += 1
            rule.last_run_at = now

        rule.next_run_at = schedule.next_run_after(rule, max(slot, now), rule.created_count)
        if rule.next_run_at is None:
            rule.is_active = False
            rule.stop_reason = "Finished: no run dates left."
        rule.save(update_fields=["created_count", "last_run_at", "next_run_at", "is_active", "stop_reason", "updated_at"])
        return copy


@shared_task
def run_due_repeats():
    now = timezone.now()
    due = list(
        RepeatRule.objects.filter(is_active=True, next_run_at__isnull=False, next_run_at__lte=now)
        .order_by("next_run_at")
        .values_list("id", flat=True)[:BATCH]
    )
    made = 0
    for rule_id in due:
        try:
            if run_rule(rule_id, now) is not None:
                made += 1
        except Exception as e:  # one broken rule must not stop the others
            log_exception(e)
            # Nothing was saved for this slot (the transaction rolled back). Try again
            # later rather than every few minutes; the catch-up rule still makes one copy.
            RepeatRule.objects.filter(pk=rule_id, is_active=True).update(next_run_at=now + RETRY_AFTER)
    if due:
        logger.info("repeat job: %s due rules, %s copies made", len(due), made)
    return made
