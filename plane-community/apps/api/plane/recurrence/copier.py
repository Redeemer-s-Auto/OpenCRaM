# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Make one copy of a template work item, the same way the app creates work items.

Each copy goes through ``IssueCreateSerializer`` (validation, custom fields,
formulas, default assignee, default state), runs as the rule's owner (so
``created_by`` and activity name that person), and queues the same activity,
webhook and description-history jobs as the create endpoint, after commit.
The template's sharing restriction is copied too, so a private card never
spawns cards everyone can see. Sub-items are copied under the new item.
"""

import json
import logging

from crum import impersonate
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from plane.app.serializers import IssueCreateSerializer
from plane.db.models import CustomField, Issue, IssueAssignee, IssueLabel
from plane.sharing.models import ItemRestriction, ItemShare
from plane.sharing.visibility import hidden_issue_ids
from plane.utils.custom_fields import validate_values, values_for_issues

logger = logging.getLogger("plane.recurrence")

MAX_SUB_ITEMS = 200  # safety cap on how many sub-items one run copies
MAX_DEPTH = 5
# Same rule as card templates (plane/utils/issue_templates.py), matched by type name.
NOT_COPIED_TYPES = ["formula", "relation", "rollup"]


class CopyBudget:
    def __init__(self, limit=MAX_SUB_ITEMS):
        self.left = limit


def _origin():
    return getattr(settings, "WEB_URL", None) or getattr(settings, "APP_BASE_URL", None) or None


def _shift(value, delta):
    return (value + delta).isoformat() if value and delta is not None else (value.isoformat() if value else None)


def _clean_custom_fields(source):
    """The template's custom field values that still pass validation (one bad field never blocks the copy).

    Like card templates, linked-card fields (relation, rollup) are not copied: they
    point at specific cards. Formulas are worked out again by the server.
    """
    stored = values_for_issues([source.id]).get(str(source.id), {})
    skipped = {
        str(i)
        for i in CustomField.objects.filter(id__in=list(stored), field_type__in=NOT_COPIED_TYPES).values_list(
            "id", flat=True
        )
    }
    kept = {}
    for field_id, value in stored.items():
        if field_id in skipped:
            continue
        try:
            validate_values(source.project_id, {field_id: value})
        except ValidationError:
            logger.info("repeat copy skipped custom field %s of %s: value no longer valid", field_id, source.id)
            continue
        kept[field_id] = value
    return kept


def _payload(source, parent_id, delta):
    label_ids = list(
        IssueLabel.objects.filter(issue_id=source.id, deleted_at__isnull=True, label__deleted_at__isnull=True)
        .values_list("label_id", flat=True)
        .distinct()
    )
    assignee_ids = list(
        IssueAssignee.objects.filter(issue_id=source.id, deleted_at__isnull=True)
        .values_list("assignee_id", flat=True)
        .distinct()
    )
    data = {
        "name": source.name,
        "description_html": source.description_html or "<p></p>",
        "priority": source.priority,
        "label_ids": [str(i) for i in label_ids],
        "assignee_ids": [str(i) for i in assignee_ids],
        "parent_id": str(parent_id) if parent_id else None,
        "start_date": _shift(source.start_date, delta),
        "target_date": _shift(source.target_date, delta),
    }
    if source.estimate_point_id:
        data["estimate_point"] = str(source.estimate_point_id)
    if getattr(source, "type_id", None):
        data["type"] = str(source.type_id)
    custom_fields = _clean_custom_fields(source)
    if custom_fields:
        data["custom_fields"] = custom_fields
    return data


def _copy_sharing(source, copy):
    restriction = ItemRestriction.objects.filter(issue_id=source.id).first()
    if restriction is None:
        return
    ItemRestriction.objects.create(workspace_id=restriction.workspace_id, issue=copy)
    ItemShare.objects.bulk_create(
        ItemShare(
            workspace_id=share.workspace_id,
            issue=copy,
            target_type=share.target_type,
            member_id=share.member_id,
            project_id=share.project_id,
            group_id=share.group_id,
            level=share.level,
        )
        for share in ItemShare.objects.filter(issue_id=source.id)
    )


def _queue_jobs(copy_id, project, data, actor_id):
    from plane.bgtasks.issue_activities_task import issue_activity
    from plane.bgtasks.issue_description_version_task import issue_description_version_task
    from plane.bgtasks.webhook_task import model_activity

    requested = json.dumps(data, cls=DjangoJSONEncoder)
    origin = _origin()

    def send():
        issue_activity.delay(
            type="issue.activity.created",
            requested_data=requested,
            actor_id=str(actor_id),
            issue_id=str(copy_id),
            project_id=str(project.id),
            current_instance=None,
            epoch=int(timezone.now().timestamp()),
            notification=True,
            origin=origin,
        )
        model_activity.delay(
            model_name="issue",
            model_id=str(copy_id),
            requested_data=data,
            current_instance=None,
            actor_id=str(actor_id),
            slug=project.workspace.slug,
            origin=origin,
        )
        issue_description_version_task.delay(
            updated_issue=requested,
            issue_id=str(copy_id),
            user_id=str(actor_id),
            is_creating=True,
        )

    transaction.on_commit(send)


def _create(source, parent_id, delta, actor):
    project = source.project
    data = _payload(source, parent_id, delta)
    serializer = IssueCreateSerializer(
        data=data,
        context={
            "project_id": project.id,
            "workspace_id": project.workspace_id,
            "default_assignee_id": project.default_assignee_id,
        },
    )
    if not serializer.is_valid():
        # Retry without the optional extras that can go stale (estimate, type, custom fields).
        for key in ("estimate_point", "type", "custom_fields"):
            data.pop(key, None)
        serializer = IssueCreateSerializer(data=data, context=serializer.context)
        serializer.is_valid(raise_exception=True)
    copy = serializer.save()
    _copy_sharing(source, copy)
    _queue_jobs(copy.id, project, data, actor.id)
    return copy


def _copy_tree(source, copy, delta, actor, hidden, depth, budget):
    if depth >= MAX_DEPTH:
        return
    children = (
        Issue.issue_objects.filter(parent_id=source.id, project_id=source.project_id)
        .exclude(id__in=hidden)
        .select_related("project", "project__workspace")
        .order_by("sequence_id")
    )
    for child in children:
        if budget.left <= 0:
            logger.warning("repeat copy of %s stopped at the sub-item limit", source.id)
            return
        budget.left -= 1
        child_copy = _create(child, copy.id, delta, actor)
        _copy_tree(child, child_copy, delta, actor, hidden, depth + 1, budget)


def make_copy(template, delta, actor):
    """Copy ``template`` and its sub-items as ``actor``; dates move by ``delta``. Returns the new item.

    Call inside a transaction. Sub-items ``actor`` cannot see are left out.
    """
    hidden = set(hidden_issue_ids(actor).values_list("issue_id", flat=True))
    parent_id = template.parent_id
    if parent_id and (
        parent_id in hidden or not Issue.issue_objects.filter(pk=parent_id, project_id=template.project_id).exists()
    ):
        parent_id = None
    with impersonate(actor):
        copy = _create(template, parent_id, delta, actor)
        _copy_tree(template, copy, delta, actor, hidden, 0, CopyBudget())
    return copy
