# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Run the query behind a live view block.

A live view block stores only its settings (source, filter, sort). Cards are read
here, each time the block is shown. The only cards that can come back are those
``plane.relations.visibility.viewable_issues`` allows: board membership plus the
sharing rules. Hidden cards are not sent and not counted.
"""

import uuid

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from plane.db.models import CustomField, IssueAssignee, IssueLabel, Label, Project, ProjectMember, State, User
from plane.relations.models import CardLink
from plane.relations.service import _storage
from plane.relations.visibility import viewable_issues
from plane.utils.custom_fields import build_flat_filters, is_order_key, order_queryset, values_for_issues
from plane.utils.issue_filters import issue_filters

SOURCE_TYPES = ("project", "children", "linked")
DEFAULT_LIMIT = 100
MAX_LIMIT = 200
# Filter keys a block may use. Same names and value shapes as a saved view's ``filters``.
FILTER_KEYS = {"state", "state_group", "priority", "labels", "assignees", "created_by", "start_date", "target_date"}
SORT_KEYS = {"sort_order", "sequence_id", "created_at", "updated_at", "name", "start_date", "target_date"}
CARD_FIELDS = (
    "id",
    "sequence_id",
    "project_id",
    "project__identifier",
    "name",
    "priority",
    "state_id",
    "parent_id",
    "start_date",
    "target_date",
    "created_at",
    "updated_at",
)


def _uuid(value, name):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise ValidationError({"source": f"'{name}' must be an id."})


def _filters(raw):
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ValidationError({"filters": "Must be an object."})
    unknown = set(raw) - FILTER_KEYS
    if unknown:
        raise ValidationError({"filters": f"Not allowed: {', '.join(sorted(unknown))}."})
    clean = {}
    for key, value in raw.items():
        value = value if isinstance(value, list) else [value]
        clean[key] = [str(v) for v in value]
    return issue_filters(clean, "POST") if clean else {}


def viewable_projects(user, slug):
    """Boards ``user`` is an active member of, in this workspace."""
    member_of = ProjectMember.objects.filter(member_id=user.id, is_active=True, deleted_at__isnull=True)
    return Project.objects.filter(workspace__slug=slug, pk__in=member_of.values("project_id"))


def _source_cards(source, user, slug):
    """``(queryset, project_id_or_None)``. An unseen parent or board gives an empty queryset."""
    if not isinstance(source, dict) or source.get("type") not in SOURCE_TYPES:
        raise ValidationError({"source": f"'type' must be one of {', '.join(SOURCE_TYPES)}."})
    kind = source["type"]
    cards = viewable_issues(user).filter(workspace__slug=slug)
    if kind == "project":
        project_id = _uuid(source.get("project_id"), "project_id")
        return cards.filter(project_id=project_id), project_id
    parent_id = _uuid(source.get("issue_id" if kind == "linked" else "parent_id"), "parent_id")
    parent = cards.filter(pk=parent_id).values("id", "project_id").first()
    if parent is None:
        return cards.none(), None
    if kind == "children":
        return cards.filter(parent_id=parent["id"]), None
    field_id = _uuid(source.get("field_id"), "field_id")
    field = CustomField.objects.filter(
        pk=field_id,
        workspace__slug=slug,
        project_id=parent["project_id"],
        field_type=CustomField.RELATION,
        archived_at__isnull=True,
    ).first()
    if field is None:
        return cards.none(), None
    primary_id, forward = _storage(field)
    if primary_id is None:
        return cards.none(), None
    links = CardLink.objects.filter(field_id=primary_id)
    if forward:
        ids = links.filter(from_issue_id=parent["id"]).values("to_issue_id")
    else:
        ids = links.filter(to_issue_id=parent["id"]).values("from_issue_id")
    return cards.filter(pk__in=ids), None


def _order(cards, order_by):
    order_by = str(order_by or "sort_order")
    if is_order_key(order_by):
        ordered, _ = order_queryset(cards, order_by)
        return ordered if ordered is not None else cards.order_by("sort_order", "-created_at")
    if order_by.lstrip("-") not in SORT_KEYS:
        raise ValidationError({"order_by": f"Sort by one of {', '.join(sorted(SORT_KEYS))} or a custom field."})
    return cards.order_by(order_by, "-created_at")


def _grouped(pairs):
    out = {}
    for card_id, other in pairs:
        out.setdefault(card_id, []).append(str(other))
    return out


def run_query(user, slug, body):
    cards, project_id = _source_cards(body.get("source"), user, slug)
    cards = cards.filter(**_filters(body.get("filters")))

    flat = body.get("custom_field_filters")
    if flat:
        if project_id is None:
            raise ValidationError({"custom_field_filters": "Only for a block that shows one board."})
        cards = cards.filter(build_flat_filters(flat, project_id))
    search = str(body.get("search") or "").strip()
    if search:
        cards = cards.filter(Q(name__icontains=search))

    try:
        limit = min(max(int(body.get("limit") or DEFAULT_LIMIT), 1), MAX_LIMIT)
    except (TypeError, ValueError):
        raise ValidationError({"limit": "Must be a number."})
    cards = _order(cards, body.get("order_by"))
    count = cards.count()
    rows = list(cards.values(*CARD_FIELDS)[:limit])
    ids = [row["id"] for row in rows]

    assignees = _grouped(
        IssueAssignee.objects.filter(issue_id__in=ids, deleted_at__isnull=True).values_list("issue_id", "assignee_id")
    )
    labels = _grouped(
        IssueLabel.objects.filter(issue_id__in=ids, deleted_at__isnull=True).values_list("issue_id", "label_id")
    )
    values = values_for_issues(ids, user)

    results = [
        {
            "id": str(row["id"]),
            "sequence_id": row["sequence_id"],
            "project_id": str(row["project_id"]),
            "project_identifier": row["project__identifier"],
            "name": row["name"],
            "priority": row["priority"],
            "state_id": str(row["state_id"]) if row["state_id"] else None,
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "start_date": row["start_date"],
            "target_date": row["target_date"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "assignee_ids": assignees.get(row["id"], []),
            "label_ids": labels.get(row["id"], []),
            "custom_fields": values.get(str(row["id"]), {}),
        }
        for row in rows
    ]

    # What the block needs to draw columns: board states and fields, names for people and labels.
    wanted = {r["project_id"] for r in results}
    if project_id is not None:
        wanted.add(str(project_id))
    projects = {}
    for project in viewable_projects(user, slug).filter(pk__in=list(wanted)):
        projects[str(project.id)] = {
            "id": str(project.id),
            "name": project.name,
            "identifier": project.identifier,
            "states": [],
            "fields": [],
        }
    for state in State.objects.filter(project_id__in=list(projects)).order_by("sequence"):
        projects[str(state.project_id)]["states"].append(
            {"id": str(state.id), "name": state.name, "color": state.color, "group": state.group}
        )
    fields = CustomField.objects.filter(project_id__in=list(projects), archived_at__isnull=True).order_by("sort_order")
    for field in fields:
        projects[str(field.project_id)]["fields"].append(
            {
                "id": str(field.id),
                "name": field.name,
                "field_type": field.field_type,
                "options": field.options,
                "settings": field.settings,
                "description": field.description,
                "sort_order": field.sort_order,
                "archived_at": None,
                "project": str(field.project_id),
                "workspace": str(field.workspace_id),
                "created_at": field.created_at,
                "updated_at": field.updated_at,
            }
        )
    people = {
        str(u.id): u.display_name or u.email
        for u in User.objects.filter(pk__in={uid for lst in assignees.values() for uid in lst})
    }
    label_rows = {
        str(label.id): {"id": str(label.id), "name": label.name, "color": label.color}
        for label in Label.objects.filter(pk__in={lid for lst in labels.values() for lid in lst})
    }
    return {"count": count, "results": results, "projects": projects, "people": people, "labels": label_rows}
