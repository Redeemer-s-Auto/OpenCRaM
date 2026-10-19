# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Card templates: check template data, snapshot a card, create cards from a template.

Cards are always created through IssueCreateSerializer, the same path as the
"new card" screen, followed by the same background tasks (activity, webhooks,
description versions). Anything that no longer exists on the board - a state, a
label, a custom field, a dropdown option - is skipped instead of failing.
"""

# Python imports
import json
import uuid

# Django imports
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

# Third party imports
from rest_framework.exceptions import ValidationError

# Module imports
from plane.db.models import CustomField, Issue, IssueLabel, Label, State
from plane.utils.custom_fields import clean_value

MAX_DEPTH = 3  # the card, its sub-cards, and their sub-cards
MAX_ITEMS = 50  # cards per template, the top card included
NAME_MAX = 255
BODY_MAX = 500_000
PRIORITIES = {"urgent", "high", "medium", "low", "none"}
# Field types a template never stores: formulas are worked out by the server, and
# linked-card fields (relation, rollup) point at specific cards, which a template
# must not copy. Matched by name so this works with or without the linked-cards code.
NOT_COPIED_TYPES = ["formula", "relation", "rollup"]


# ---------------------------------------------------------------------------
# Checking template data
# ---------------------------------------------------------------------------


class _Board:
    """What exists on a project right now, loaded once per operation."""

    def __init__(self, project_id):
        self.project_id = project_id
        self.state_ids = {str(i) for i in State.objects.filter(project_id=project_id).values_list("id", flat=True)}
        self.label_ids = {str(i) for i in Label.objects.filter(project_id=project_id).values_list("id", flat=True)}
        self.fields = {
            str(f.id): f
            for f in CustomField.objects.filter(project_id=project_id, archived_at__isnull=True).exclude(
                field_type__in=NOT_COPIED_TYPES
            )
        }

    def clean_custom_fields(self, raw):
        """Keep values for live fields that still pass their checks. Drop the rest quietly."""
        if not isinstance(raw, dict):
            return {}
        kept = {}
        for key, value in raw.items():
            field = self.fields.get(str(key))
            if field is None or value in (None, "", []):
                continue
            try:
                cleaned, _ = clean_value(field, value)
            except ValidationError:
                continue
            if cleaned is not None:
                kept[str(field.id)] = cleaned
        return kept


def _clean_node(board, node, depth, counter, require_name):
    if not isinstance(node, dict):
        raise ValidationError({"data": "Each card in a template must be an object."})
    counter[0] += 1
    if counter[0] > MAX_ITEMS:
        raise ValidationError({"data": f"A template can hold at most {MAX_ITEMS} cards."})

    name = " ".join(str(node.get("name") or "").split())[:NAME_MAX]
    if require_name and not name:
        raise ValidationError({"data": "Each sub-card in a template needs a title."})

    body = node.get("description_html") or ""
    if not isinstance(body, str):
        raise ValidationError({"data": "description_html must be text."})
    if len(body) > BODY_MAX:
        raise ValidationError({"data": "The page body is too long for a template."})

    priority = node.get("priority") or "none"
    state_id = str(node.get("state_id")) if node.get("state_id") else None
    label_ids = [str(i) for i in (node.get("label_ids") or []) if str(i) in board.label_ids]

    sub_items = node.get("sub_items") or []
    if not isinstance(sub_items, list):
        raise ValidationError({"data": "sub_items must be a list."})
    if sub_items and depth >= MAX_DEPTH:
        raise ValidationError({"data": f"Templates can nest sub-cards {MAX_DEPTH - 1} levels deep."})

    return {
        "name": name,
        "description_html": body,
        "priority": priority if priority in PRIORITIES else "none",
        "state_id": state_id if state_id in board.state_ids else None,
        "label_ids": list(dict.fromkeys(label_ids)),
        "custom_fields": board.clean_custom_fields(node.get("custom_fields")),
        "sub_items": [_clean_node(board, child, depth + 1, counter, True) for child in sub_items],
    }


def clean_template_data(project_id, data):
    """Check and normalise template data for a project. Raises ValidationError."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValidationError({"data": "Template data must be an object."})
    return _clean_node(_Board(project_id), data, 1, [0], False)


# ---------------------------------------------------------------------------
# Snapshot: card -> template data
# ---------------------------------------------------------------------------


def snapshot_issue(issue, include_sub_items=True, visible=None):
    """Template data from a card (and, if asked, its sub-cards).

    ``visible`` is an optional function ``(queryset) -> queryset`` that limits sub-cards
    to the ones the person saving can see, so a template never copies hidden cards.
    """
    from plane.utils.custom_fields import values_for_issues

    counter = [0]

    def node_for(card, depth):
        counter[0] += 1
        values = values_for_issues([card.id]).get(str(card.id), {})
        node = {
            "name": card.name,
            "description_html": card.description_html or "",
            "priority": card.priority or "none",
            "state_id": str(card.state_id) if card.state_id else None,
            "label_ids": [
                str(i)
                for i in IssueLabel.objects.filter(issue_id=card.id, deleted_at__isnull=True).values_list(
                    "label_id", flat=True
                )
            ],
            "custom_fields": values,
            "sub_items": [],
        }
        if include_sub_items and depth < MAX_DEPTH:
            children = Issue.issue_objects.filter(parent_id=card.id).order_by("sequence_id")
            if visible is not None:
                children = visible(children)
            for child in children:
                if counter[0] >= MAX_ITEMS:
                    break
                node["sub_items"].append(node_for(child, depth + 1))
        return node

    return node_for(issue, 1)


# ---------------------------------------------------------------------------
# Use: template data -> cards
# ---------------------------------------------------------------------------


def create_from_template(request, project, template, name_override=None):
    """Create the template's card and sub-cards. Returns (top card, number of cards made)."""
    # Imported here: these modules import serializers, which import this package's siblings.
    from plane.app.serializers import IssueCreateSerializer
    from plane.bgtasks.issue_activities_task import issue_activity
    from plane.bgtasks.issue_description_version_task import issue_description_version_task
    from plane.bgtasks.webhook_task import model_activity
    from plane.utils.host import base_host

    data = clean_template_data(project.id, template.data)
    if name_override:
        data["name"] = " ".join(str(name_override).split())[:NAME_MAX]
    if not data["name"]:
        data["name"] = template.name

    created = []

    def make(node, parent_id):
        payload = {
            "name": node["name"],
            "description_html": node["description_html"] or "<p></p>",
            "priority": node["priority"],
            "label_ids": node["label_ids"],
            "custom_fields": node["custom_fields"],
        }
        if node["state_id"]:
            payload["state_id"] = node["state_id"]
        if parent_id:
            payload["parent_id"] = str(parent_id)
        serializer = IssueCreateSerializer(
            data=payload,
            context={
                "project_id": project.id,
                "workspace_id": project.workspace_id,
                "default_assignee_id": project.default_assignee_id,
            },
        )
        serializer.is_valid(raise_exception=True)
        issue = serializer.save()
        created.append((issue, payload))
        for child in node["sub_items"]:
            make(child, issue.id)
        return issue

    with transaction.atomic():
        top = make(data, None)

    # Same background work as the "new card" screen, after the rows are committed.
    origin = base_host(request=request, is_app=True)
    for issue, payload in created:
        requested = json.dumps(payload, cls=DjangoJSONEncoder)
        issue_activity.delay(
            type="issue.activity.created",
            requested_data=requested,
            actor_id=str(request.user.id),
            issue_id=str(issue.id),
            project_id=str(project.id),
            current_instance=None,
            epoch=int(timezone.now().timestamp()),
            notification=True,
            origin=origin,
        )
        model_activity.delay(
            model_name="issue",
            model_id=str(issue.id),
            requested_data=payload,
            current_instance=None,
            actor_id=request.user.id,
            slug=project.workspace.slug,
            origin=origin,
        )
        issue_description_version_task.delay(
            updated_issue=requested,
            issue_id=str(issue.id),
            user_id=request.user.id,
            is_creating=True,
        )
    return top, len(created)


def new_template_name(project_id, base):
    """A free template name on the project: base, base (2), base (3), ..."""
    from plane.db.models import IssueTemplate

    base = " ".join(str(base or "Template").split())[: NAME_MAX - 6] or "Template"
    taken = set(
        IssueTemplate.objects.filter(project_id=project_id, name__istartswith=base).values_list("name", flat=True)
    )
    taken = {t.lower() for t in taken}
    if base.lower() not in taken:
        return base
    for n in range(2, 1000):
        candidate = f"{base} ({n})"
        if candidate.lower() not in taken:
            return candidate
    return f"{base} ({uuid.uuid4().hex[:6]})"
