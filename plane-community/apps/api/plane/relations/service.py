# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Relation and rollup fields.

Relation: a custom field whose value is a list of linked cards on one target
board. Rollup: a read-only custom field that sums up the cards linked through a
relation field on the same board.

Safety rule: relation lists and rollup results are worked out at read time FOR
ONE VIEWER, from only the linked cards that viewer may see
(``plane.relations.visibility``). Nothing here is stored per card, so a hidden
card can never be shown or counted, and there is nothing to go stale: every
read reflects the linked cards as they are now. With no viewer (background
jobs, webhooks, exports) relation and rollup values are left out entirely.
"""

# Python imports
import datetime
import uuid
from decimal import ROUND_HALF_UP, Decimal

# Django imports
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date, parse_datetime

# Third party imports
from crum import get_current_user
from rest_framework.exceptions import ValidationError

# Module imports
from plane.db.models import CustomField, CustomFieldValue, Issue, Project, ProjectMember

from .models import CardLink
from .visibility import _real_user, editable_issues, viewable_issues

FT = CustomField.FieldType

MAX_LINKS = 500
MAX_UNIQUE = 100
ADMIN = 20
MEMBER = 15

ANY = "any"
NUMERIC = "numeric"
DATE = "date"
CHECKBOX = "checkbox"

# function -> what the target must be (None: no target needed)
ROLLUP_FUNCTIONS = {
    "count": None,
    "count_empty": ANY,
    "count_not_empty": ANY,
    "sum": NUMERIC,
    "avg": NUMERIC,
    "min": NUMERIC,
    "max": NUMERIC,
    "earliest": DATE,
    "latest": DATE,
    "unique": ANY,
    "percent_checked": CHECKBOX,
}

# Built-in card properties a rollup can read: key -> (kind, getter on a values() row)
BUILTIN_TARGETS = {
    "@title": ("text", lambda row: row["name"]),
    "@state": ("text", lambda row: row["state__name"]),
    "@priority": ("text", lambda row: None if row["priority"] in (None, "", "none") else row["priority"]),
    "@start_date": ("date", lambda row: row["start_date"]),
    "@due_date": ("date", lambda row: row["target_date"]),
}


def viewer(user=None):
    """The user a read or write acts for: the one given, else the request's user, else nobody."""
    return _real_user(user if user is not None else get_current_user())


def _err(field, message):
    return ValidationError({str(field.id) if field is not None else "settings": message})


def _settings_error(message):
    return ValidationError({"settings": message})


def _uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _is_member(user, project_id, min_role=MEMBER):
    if user is None:
        return False
    return ProjectMember.objects.filter(
        project_id=project_id, member_id=user.id, is_active=True, deleted_at__isnull=True, role__gte=min_role
    ).exists()


# ---------------------------------------------------------------------------
# Field settings
# ---------------------------------------------------------------------------


def _target_kind(target_field):
    """What a rollup target behaves as: numeric, date, checkbox or any."""
    from plane.utils.custom_fields import effective_type

    t = effective_type(target_field)
    if t in (FT.NUMBER, FT.MONEY):
        return NUMERIC
    if t == FT.DATE:
        return DATE
    if t == FT.CHECKBOX:
        return CHECKBOX
    return ANY


def rollup_result_type(function, target):
    """How a rollup result shows: number, money, date, list or percent."""
    from plane.utils.custom_fields import effective_type

    if function in ("count", "count_empty", "count_not_empty"):
        return "number"
    if function == "percent_checked":
        return "percent"
    if function == "unique":
        return "list"
    if function in ("earliest", "latest"):
        return "date"
    if isinstance(target, CustomField) and effective_type(target) == FT.MONEY:
        return "money"
    return "number"


def clean_relation_settings(project_id, settings, instance=None, user=None):
    """Validate a relation field's settings. Server-owned keys are kept from ``instance``.

    Returns ``(settings, mirror_name)``; ``mirror_name`` is only used when two-way is
    switched on and is not stored.
    """
    settings = settings or {}
    if not isinstance(settings, dict):
        raise _settings_error("Settings must be an object.")
    user = viewer(user)
    project = Project.objects.filter(pk=project_id).first()
    old = (instance.settings or {}) if instance is not None else {}

    if instance is not None:
        target_id = old.get("target_project_id")
        sent = settings.get("target_project_id")
        if sent is not None and _uuid(sent) != target_id:
            raise _settings_error("The target board of a relation cannot change. Make a new field instead.")
    else:
        target_id = _uuid(settings.get("target_project_id"))
        if target_id is None:
            raise _settings_error("Pick the board this relation links to (target_project_id).")
        if project is None or not Project.objects.filter(pk=target_id, workspace_id=project.workspace_id).exists():
            raise _settings_error("The target board must be a board in this workspace.")
        if not _is_member(user, target_id):
            raise _settings_error("You must be a member of the target board to link to it.")

    is_mirror = bool(old.get("is_mirror", False))
    mirror_field_id = old.get("mirror_field_id")
    two_way = bool(settings.get("two_way", old.get("two_way", False)))
    if is_mirror:
        if not two_way:
            raise _settings_error(
                "This field is the other side of a two-way relation. Turn two-way off on the board where it was "
                "made, or delete this field."
            )
        two_way = True
    elif two_way and not mirror_field_id:
        if not _is_member(user, target_id, ADMIN):
            raise _settings_error("Two-way needs you to be an admin of the target board (it adds a field there).")

    mirror_name = settings.get("mirror_name")
    if mirror_name is not None:
        mirror_name = " ".join(str(mirror_name).split())[:255] or None
    cleaned = {
        "target_project_id": target_id,
        "two_way": two_way,
        "mirror_field_id": mirror_field_id,
        "is_mirror": is_mirror,
    }
    return cleaned, mirror_name


def clean_rollup_settings(project_id, settings, user=None):
    settings = settings or {}
    if not isinstance(settings, dict):
        raise _settings_error("Settings must be an object.")
    user = viewer(user)
    relation_id = _uuid(settings.get("relation_field_id"))
    relation = (
        CustomField.objects.filter(
            pk=relation_id, project_id=project_id, field_type=CustomField.RELATION, archived_at__isnull=True
        ).first()
        if relation_id
        else None
    )
    if relation is None:
        raise _settings_error("Pick a relation field on this board (relation_field_id).")
    function = settings.get("function")
    if function not in ROLLUP_FUNCTIONS:
        raise _settings_error(f"function must be one of: {', '.join(ROLLUP_FUNCTIONS)}.")
    needs = ROLLUP_FUNCTIONS[function]
    target_project_id = (relation.settings or {}).get("target_project_id")

    target_key = settings.get("target_field_id")
    target = None
    if needs is None:
        target_key = None
    elif isinstance(target_key, str) and target_key in BUILTIN_TARGETS:
        kind = BUILTIN_TARGETS[target_key][0]
        if needs not in (ANY, DATE if kind == "date" else None):
            raise _settings_error("That property cannot be used with this calculation.")
    else:
        target_key = _uuid(target_key)
        if not _is_member(user, target_project_id, 5):
            raise _settings_error("You must be a member of the linked board to roll up its fields.")
        target = (
            CustomField.objects.filter(pk=target_key, project_id=target_project_id, archived_at__isnull=True).first()
            if target_key
            else None
        )
        if target is None:
            raise _settings_error("Pick a field on the linked board to roll up (target_field_id).")
        if target.field_type in CustomField.LINKED_TYPES:
            raise _settings_error("A rollup cannot use a relation or another rollup.")
        if needs != ANY and _target_kind(target) != needs:
            raise _settings_error("That field's type does not fit this calculation.")
    return {
        "relation_field_id": str(relation.id),
        "target_field_id": target_key,
        "function": function,
        "result_type": rollup_result_type(function, target),
    }


def _unique_name(project_id, base):
    base = (base or "Related")[:240]
    taken = {n.lower() for n in CustomField.objects.filter(project_id=project_id).values_list("name", flat=True)}
    name, n = base, 2
    while name.lower() in taken:
        name = f"{base} ({n})"
        n += 1
    return name


@transaction.atomic
def sync_mirror(field, mirror_name=None):
    """After a relation field is saved: add or remove its mirror to match ``two_way``."""
    settings = dict(field.settings or {})
    if field.field_type != CustomField.RELATION or settings.get("is_mirror"):
        return
    mirror_id = settings.get("mirror_field_id")
    if settings.get("two_way") and not mirror_id:
        source = Project.objects.get(pk=field.project_id)
        mirror = CustomField.objects.create(
            project_id=settings["target_project_id"],
            workspace_id=field.workspace_id,
            name=_unique_name(settings["target_project_id"], mirror_name or source.name),
            field_type=CustomField.RELATION,
            settings={
                "target_project_id": str(field.project_id),
                "two_way": True,
                "mirror_field_id": str(field.id),
                "is_mirror": True,
            },
        )
        settings["mirror_field_id"] = str(mirror.id)
        field.settings = settings
        field.save(update_fields=["settings", "updated_at"])
    elif not settings.get("two_way") and mirror_id:
        # Links belong to this (primary) field, so removing the mirror loses nothing.
        CustomFieldValue.all_objects.filter(field_id=mirror_id).delete()
        CustomField.all_objects.filter(pk=mirror_id).delete()
        settings["mirror_field_id"] = None
        field.settings = settings
        field.save(update_fields=["settings", "updated_at"])


@transaction.atomic
def before_field_delete(field):
    """Keep the other side of a two-way pair working when one side is deleted."""
    if field.field_type != CustomField.RELATION:
        return
    settings = field.settings or {}
    other_id = settings.get("mirror_field_id")
    other = CustomField.all_objects.filter(pk=other_id).first() if other_id else None
    if other is None:
        return
    if settings.get("is_mirror"):
        # The primary keeps its links and becomes one-way.
        other.settings = {**(other.settings or {}), "two_way": False, "mirror_field_id": None}
        other.save(update_fields=["settings", "updated_at"])
        return
    # Deleting the primary: hand the links to the mirror, flipped, and make it one-way.
    links = list(CardLink.objects.filter(field_id=field.id).values("workspace_id", "from_issue_id", "to_issue_id"))
    CardLink.objects.bulk_create(
        [
            CardLink(
                workspace_id=link["workspace_id"],
                field_id=other.id,
                from_issue_id=link["to_issue_id"],
                to_issue_id=link["from_issue_id"],
            )
            for link in links
        ],
        batch_size=500,
        ignore_conflicts=True,
    )
    CardLink.objects.filter(field_id=field.id).delete()
    other.settings = {**(other.settings or {}), "two_way": False, "mirror_field_id": None, "is_mirror": False}
    other.save(update_fields=["settings", "updated_at"])


# ---------------------------------------------------------------------------
# Writing relation values
# ---------------------------------------------------------------------------


def _storage(field):
    """``(primary_field_id, forward)`` for reading and writing this field's links, or (None, True)."""
    settings = field.settings or {}
    if settings.get("is_mirror"):
        primary = settings.get("mirror_field_id")
        if not primary or not CustomField.objects.filter(pk=primary).exists():
            return None, False
        return primary, False
    return str(field.id), True


def _ids_from(raw):
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    ids = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("id")
        card_id = _uuid(item)
        if card_id is None:
            return None
        if card_id not in ids:
            ids.append(card_id)
    return ids


def clean_relation_value(field, raw, user=None):
    """Check a relation value: a list of card ids (or ``{"id": ...}`` objects).

    Every id must be a live card on the target board that the writer can see; for a
    two-way relation the writer must also be able to change it (its other side
    changes; checked in ``set_links`` for the cards being added). Returns the list
    of ids, or None to clear the writer's visible links.
    """
    user = viewer(user)
    if user is None:
        raise _err(field, "Sign in to change linked cards.")
    if raw is None or raw == "" or raw == []:
        return None
    ids = _ids_from(raw)
    if ids is None:
        raise _err(field, "Each linked card must be a card id.")
    if len(ids) > MAX_LINKS:
        raise _err(field, f"A card can link to at most {MAX_LINKS} cards in one field.")
    primary_id, _ = _storage(field)
    if primary_id is None:
        raise _err(field, "This relation lost its other side and cannot change. Ask an admin.")
    settings = field.settings or {}
    candidates = Issue.issue_objects.filter(pk__in=ids, project_id=settings.get("target_project_id"))
    allowed_ids = {str(i) for i in viewable_issues(user, candidates).values_list("id", flat=True)}
    if any(i not in allowed_ids for i in ids):
        # Same message whether the card is missing, on another board or hidden: say nothing about it.
        raise _err(field, "One or more cards cannot be linked here.")
    return ids


@transaction.atomic
def set_links(issue, field, ids, user=None):
    """Make the writer's visible links on ``issue`` equal ``ids``.

    Links to cards the writer cannot see are kept as they are. Returns
    ``(old_visible_ids, new_visible_ids)``.
    """
    user = viewer(user)
    primary_id, forward = _storage(field)
    if primary_id is None or user is None:
        return [], []
    ids = ids or []
    links = CardLink.objects.select_for_update().filter(
        field_id=primary_id, **({"from_issue_id": issue.id} if forward else {"to_issue_id": issue.id})
    )
    other_col = "to_issue_id" if forward else "from_issue_id"
    existing = {str(getattr(link, other_col)): link for link in links}
    # Same rule as reading: archived, draft and deleted cards are not shown, so they are kept here.
    shown = viewable_issues(user, Issue.issue_objects.filter(pk__in=list(existing)))
    visible = {str(i) for i in shown.values_list("id", flat=True)}
    old_visible = [i for i in existing if i in visible]

    remove = [existing[i].pk for i in old_visible if i not in ids]
    if remove:
        CardLink.objects.filter(pk__in=remove).delete()
    add = [i for i in ids if i not in existing]
    if add and (field.settings or {}).get("two_way"):
        # Adding a two-way link changes the other card too, so the writer must be able to edit it.
        editable = {str(i) for i in editable_issues(user, Issue.issue_objects.filter(pk__in=add)).values_list("id", flat=True)}
        if any(i not in editable for i in add):
            raise _err(field, "One or more cards cannot be linked here.")
    CardLink.objects.bulk_create(
        [
            CardLink(
                workspace_id=issue.workspace_id,
                field_id=primary_id,
                from_issue_id=issue.id if forward else other,
                to_issue_id=other if forward else issue.id,
                created_by_id=user.id,
            )
            for other in add
        ],
        ignore_conflicts=True,
    )
    return old_visible, [i for i in ids]


# ---------------------------------------------------------------------------
# Reading relation and rollup values, per viewer
# ---------------------------------------------------------------------------


def _number_out(number):
    number = round(Decimal(number), 6)
    return int(number) if number == number.to_integral_value() else float(number)


def _date_key(value):
    """Sort key for a stored date or date-time value (dates count as midnight UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time(), tzinfo=datetime.timezone.utc)
    text = str(value)
    if "T" in text:
        parsed = parse_datetime(text.replace("Z", "+00:00"))
        return _date_key(parsed)
    return _date_key(parse_date(text[:10]))


def _unique_texts(field, value):
    """The separate display texts inside one stored value (multi values split)."""
    from plane.utils.custom_fields import display_value

    if value is None or value == "" or value == []:
        return []
    if isinstance(value, list) and field is not None:
        return [t for t in (display_value(field, [v]) for v in value) if t]
    text = display_value(field, value) if field is not None else str(value)
    return [text] if text else []


def compute_rollup(function, cards, values, target, money):
    """Work out one rollup.

    ``cards``: linked card ids the viewer can see. ``values``: card id -> raw value
    of the target (None when empty). ``target``: the CustomField, or None for a
    built-in or no target. ``money``: the target holds whole cents.
    """
    if function == "count":
        return len(cards)
    present = [values.get(c) for c in cards]

    def empty(v):
        return v is None or v == "" or v == []

    if function == "count_empty":
        return sum(1 for v in present if empty(v))
    if function == "count_not_empty":
        return sum(1 for v in present if not empty(v))
    if function in ("sum", "avg", "min", "max"):
        if not cards:
            return None
        numbers = [Decimal(str(v)) for v in present if not empty(v)]
        if function == "sum":
            result = sum(numbers, Decimal(0))
        elif not numbers:
            return None
        elif function == "avg":
            result = sum(numbers, Decimal(0)) / len(numbers)
        else:
            result = min(numbers) if function == "min" else max(numbers)
        if money:
            return int(result.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return _number_out(result)
    if function in ("earliest", "latest"):
        dated = [(k, v) for v in present if not empty(v) for k in [_date_key(v)] if k is not None]
        if not dated:
            return None
        pick = min(dated, key=lambda kv: kv[0]) if function == "earliest" else max(dated, key=lambda kv: kv[0])
        value = pick[1]
        if isinstance(value, datetime.datetime):
            return value.isoformat().replace("+00:00", "Z")
        if isinstance(value, datetime.date):
            return value.isoformat()
        return value
    if function == "unique":
        seen = []
        for v in present:
            for text in _unique_texts(target, v):
                if text not in seen:
                    seen.append(text)
        return seen[:MAX_UNIQUE] or None
    if function == "percent_checked":
        if not cards:
            return None
        checked = sum(1 for v in present if v is True)
        return _number_out(Decimal(checked * 100) / len(cards))
    return None


def linked_values(issue_ids, user=None):
    """``{issue_id: {field_id: value}}`` for relation and rollup fields, as ``user`` may see them."""
    user = viewer(user)
    issue_ids = [str(i) for i in issue_ids if i]
    if user is None or not issue_ids:
        return {}
    issue_projects = {str(i): str(p) for i, p in Issue.all_objects.filter(pk__in=issue_ids).values_list("id", "project_id")}
    fields = list(
        CustomField.objects.filter(
            project_id__in=set(issue_projects.values()),
            field_type__in=list(CustomField.LINKED_TYPES),
            archived_at__isnull=True,
        )
    )
    if not fields:
        return {}
    relations = {str(f.id): f for f in fields if f.field_type == CustomField.RELATION}
    rollups = [f for f in fields if f.field_type == CustomField.ROLLUP]

    # 1. Raw links for every relation field on these boards.
    storage = {fid: _storage(f) for fid, f in relations.items()}
    forward_ids = [p for p, fwd in storage.values() if p and fwd]
    backward_ids = [p for p, fwd in storage.values() if p and not fwd]
    raw = CardLink.objects.filter(
        Q(field_id__in=forward_ids, from_issue_id__in=issue_ids) | Q(field_id__in=backward_ids, to_issue_id__in=issue_ids)
    ).values_list("field_id", "from_issue_id", "to_issue_id")
    # (primary_id, forward, this card) -> [other card ids in link order]
    by_key = {}
    for field_id, from_id, to_id in raw:
        field_id, from_id, to_id = str(field_id), str(from_id), str(to_id)
        if field_id in forward_ids and from_id in issue_projects:
            by_key.setdefault((field_id, True, from_id), []).append(to_id)
        if field_id in backward_ids and to_id in issue_projects:
            by_key.setdefault((field_id, False, to_id), []).append(from_id)

    # 2. Keep only linked cards the viewer may see.
    all_linked = {i for ids in by_key.values() for i in ids}
    cards = {}
    if all_linked:
        rows = viewable_issues(user, Issue.issue_objects.filter(pk__in=all_linked)).values(
            "id", "name", "sequence_id", "project_id", "project__identifier", "state__name", "priority",
            "start_date", "target_date",
        )
        cards = {str(r["id"]): r for r in rows}

    result = {}
    linked_by_field = {}  # (relation field id, issue id) -> visible linked ids
    for issue_id, project_id in issue_projects.items():
        for fid, field in relations.items():
            if str(field.project_id) != project_id:
                continue
            primary_id, forward = storage[fid]
            target = (field.settings or {}).get("target_project_id")
            others = by_key.get((str(primary_id), forward, issue_id), []) if primary_id else []
            visible = [o for o in others if o in cards and str(cards[o]["project_id"]) == str(target)]
            linked_by_field[(fid, issue_id)] = visible
            if visible:
                result.setdefault(issue_id, {})[fid] = [
                    {
                        "id": o,
                        "name": cards[o]["name"],
                        "sequence_id": cards[o]["sequence_id"],
                        "project_id": str(cards[o]["project_id"]),
                        "project_identifier": cards[o]["project__identifier"],
                    }
                    for o in visible
                ]

    if not rollups:
        return result

    # 3. Rollups: read target values for the visible linked cards only.
    target_ids = {
        (r.settings or {}).get("target_field_id")
        for r in rollups
        if _uuid((r.settings or {}).get("target_field_id"))
    }
    targets = {str(f.id): f for f in CustomField.objects.filter(pk__in=target_ids, archived_at__isnull=True)}
    stored = {}
    if targets and cards:
        for field_id, issue_id, value in CustomFieldValue.objects.filter(
            field_id__in=list(targets), issue_id__in=list(cards)
        ).values_list("field_id", "issue_id", "value"):
            stored.setdefault(str(field_id), {})[str(issue_id)] = value

    for rollup in rollups:
        settings = rollup.settings or {}
        relation = relations.get(str(settings.get("relation_field_id")))
        function = settings.get("function")
        if relation is None or function not in ROLLUP_FUNCTIONS or relation.project_id != rollup.project_id:
            continue
        key = settings.get("target_field_id")
        target, values_of, money = None, None, False
        if ROLLUP_FUNCTIONS[function] is not None:
            if key in BUILTIN_TARGETS:
                getter = BUILTIN_TARGETS[key][1]
                values_of = lambda ids, g=getter: {c: g(cards[c]) for c in ids}  # noqa: E731
            else:
                target = targets.get(str(key))
                if target is None or str(target.project_id) != str((relation.settings or {}).get("target_project_id")):
                    continue
                from plane.utils.custom_fields import effective_type

                money = effective_type(target) == FT.MONEY
                column = stored.get(str(target.id), {})
                values_of = lambda ids, col=column: {c: col.get(c) for c in ids}  # noqa: E731
        for issue_id, project_id in issue_projects.items():
            if str(rollup.project_id) != project_id:
                continue
            linked = linked_by_field.get((str(relation.id), issue_id), [])
            values = values_of(linked) if values_of else {}
            value = compute_rollup(function, linked, values, target, money)
            if value is not None:
                result.setdefault(issue_id, {})[str(rollup.id)] = value
    return result


def link_candidates(field, user, search="", limit=20):
    """Cards on the relation's target board that ``user`` could link, newest first."""
    user = viewer(user)
    settings = field.settings or {}
    queryset = Issue.issue_objects.filter(project_id=settings.get("target_project_id"))
    queryset = editable_issues(user, queryset) if settings.get("two_way") else viewable_issues(user, queryset)
    search = (search or "").strip()
    if search:
        q = Q(name__icontains=search)
        if search.isdigit():
            q |= Q(sequence_id=int(search))
        queryset = queryset.filter(q)
    rows = queryset.order_by("-created_at").values("id", "name", "sequence_id", "project_id", "project__identifier")[
        : max(1, min(int(limit or 20), 50))
    ]
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "sequence_id": r["sequence_id"],
            "project_id": str(r["project_id"]),
            "project_identifier": r["project__identifier"],
        }
        for r in rows
    ]
