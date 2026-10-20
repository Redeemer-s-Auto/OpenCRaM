# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""The blueprint document: capture a board's design, check a document, swap ids.

A blueprint document is portable: it never holds an id from the workspace it
came from. Everything the board owns (states, labels, custom fields, dropdown
options) is written as a token like ``@@state:s1@@``. When a board is made, each
token is swapped for the id of the thing just made. Any other id (people, cycles,
modules, cards on other boards) cannot travel, so it is dropped: a list item or a
dict entry that names it is left out, a plain value becomes empty.

Shape (``schema_version`` 1)::

    {
      "format": "opencram.board-blueprint", "schema_version": 1,
      "name", "description", "logo_props",
      "board": {"description", "logo_props", "settings": {...}},
      "states": [{"key", "name", "color", "group", "sequence", "default", "description"}],
      "default_state": "<state key>" | null,
      "labels": [{"key", "name", "color", "description", "sort_order", "parent": "<label key>" | null}],
      "fields": [{"key", "name", "description", "field_type", "options": [{"key", "name", "color"}],
                  "settings": {...}, "sort_order"}],
      "views": [{"name", "description", "filters", "display_filters", "display_properties",
                 "rich_filters", "logo_props", "access"}],
      "layout": {"filters", "display_filters", "display_properties", "rich_filters"} | null,
      "templates": [{"name", "description", "data", "sort_order"}],
      "sample_cards": [<template data node> + optional "repeat": {...}],
      "notes": ["what was left out and why"]
    }
"""

import re

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from plane.db.models import (
    CustomField,
    Issue,
    IssueTemplate,
    IssueView,
    Label,
    Project,
    ProjectMember,
    ProjectUserProperty,
    State,
)

FORMAT = "opencram.board-blueprint"
SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_SAMPLE_CARDS = 50
MAX_VIEWS = 100
MAX_FIELDS = 200
MAX_STATES = 100
MAX_LABELS = 500
MAX_TEMPLATES = 100

# Board settings a blueprint carries (features on/off and the private flag).
BOARD_SETTINGS = {
    "is_private": bool,
    "network": int,
    "module_view": bool,
    "cycle_view": bool,
    "issue_views_view": bool,
    "page_view": bool,
    "intake_view": bool,
    "is_time_tracking_enabled": bool,
    "guest_view_all_features": bool,
    "archive_in": int,
    "close_in": int,
    "timezone": str,
}

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
TOKEN_RE = re.compile(r"@@(?P<kind>[a-z]+):(?P<key>[A-Za-z0-9_]+)@@")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Pieces of a card body that point at things in the source workspace.
_BODY_DROP_RES = [
    re.compile(r"<mention-component\b[^>]*?(?:/>|>.*?</mention-component>)", re.S | re.I),
    re.compile(r"<image-component\b[^>]*?(?:/>|>.*?</image-component>)", re.S | re.I),
    re.compile(r"<issue-embed-component\b[^>]*?(?:/>|>.*?</issue-embed-component>)", re.S | re.I),
    re.compile(r"<img\b[^>]*>", re.I),
]


class _Drop:
    """Marker: this value named something that cannot travel."""


DROP = _Drop()


def token(kind, key):
    return f"@@{kind}:{key}@@"


# ---------------------------------------------------------------------------
# Swapping ids for tokens and back
# ---------------------------------------------------------------------------


def _swap(value, replace_string):
    """Walk a JSON value; ``replace_string`` returns the new string or DROP."""
    if isinstance(value, str):
        return replace_string(value)
    if isinstance(value, list):
        out = []
        for item in value:
            new = _swap(item, replace_string)
            if new is not DROP:
                out.append(new)
        return out
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            new_key = replace_string(str(key))
            if new_key is DROP:
                continue
            new = _swap(item, replace_string)
            out[new_key] = None if new is DROP else new
        return out
    return value


def tokenize(value, idmap):
    """Ids in ``idmap`` (id -> token) become tokens; any other id drops its value."""

    def replace(text):
        if not UUID_RE.search(text):
            return text
        dropped = []

        def sub(match):
            found = idmap.get(match.group(0).lower())
            if found is None:
                dropped.append(match.group(0))
                return match.group(0)
            return found

        new = UUID_RE.sub(sub, text)
        return DROP if dropped else new

    return _swap(value, replace)


def detokenize(value, newmap):
    """Tokens become the new ids in ``newmap`` (token -> id); an unknown token drops its value.

    Raw ids are dropped too, so a hand-made document cannot point at things in this workspace.
    """

    def replace(text):
        if UUID_RE.search(text):
            return DROP
        if "@@" not in text:
            return text
        missing = []

        def sub(match):
            found = newmap.get(match.group(0))
            if found is None:
                missing.append(match.group(0))
                return ""
            return str(found)

        new = TOKEN_RE.sub(sub, text)
        return DROP if missing else new

    result = _swap(value, replace)
    return None if result is DROP else result


def clean_body(html):
    """A card body that can travel: no mentions, images, embeds or stray ids."""
    html = html or ""
    for pattern in _BODY_DROP_RES:
        html = pattern.sub("", html)
    return UUID_RE.sub("", html)


# ---------------------------------------------------------------------------
# Capture: board -> document
# ---------------------------------------------------------------------------


def _visible_card_filter(user):
    """Cards a blueprint may copy: ones the saver can see that no sharing rule hides from anyone."""
    try:
        from plane.sharing.visibility import restricted_issue_ids, visible_issues
    except ImportError:  # pragma: no cover - branches without sharing rules
        return lambda queryset: queryset
    return lambda queryset: visible_issues(queryset, user).exclude(pk__in=restricted_issue_ids())


def _board_name_for(user, project_id):
    """The other board's name, unless it is private and the saver is not on it."""
    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return None
    if project.is_private and not ProjectMember.objects.filter(
        project_id=project_id, member_id=user.id, is_active=True
    ).exists():
        return None
    return project.name


def capture(project, user, include_samples=False, include_repeat_rules=False):
    """The design of ``project`` as a portable document (without name/description/logo)."""
    notes = []
    idmap = {}

    # States (the hidden triage state is made fresh on every board, so it is not copied).
    states = []
    for n, state in enumerate(State.objects.filter(project=project).order_by("sequence"), 1):
        key = f"s{n}"
        idmap[str(state.id)] = token("state", key)
        states.append(
            {
                "key": key,
                "name": state.name,
                "color": state.color,
                "group": state.group,
                "sequence": state.sequence,
                "default": bool(state.default),
                "description": state.description or "",
            }
        )
    default_state = idmap.get(str(project.default_state_id)) if project.default_state_id else None

    # Labels
    labels = []
    label_rows = list(Label.objects.filter(project=project).order_by("sort_order", "name"))
    for n, label in enumerate(label_rows, 1):
        idmap[str(label.id)] = token("label", f"l{n}")
    for n, label in enumerate(label_rows, 1):
        parent = idmap.get(str(label.parent_id)) if label.parent_id else None
        labels.append(
            {
                "key": f"l{n}",
                "name": label.name,
                "color": label.color or "",
                "description": label.description or "",
                "sort_order": label.sort_order,
                "parent": TOKEN_RE.match(parent).group("key") if parent else None,
            }
        )

    # Custom fields: give every field and option a key first, so settings can point at each other.
    field_rows = list(CustomField.objects.filter(project=project, archived_at__isnull=True).order_by("sort_order"))
    by_id = {str(f.id): f for f in field_rows}
    keys = {}
    for n, field in enumerate(field_rows, 1):
        keys[str(field.id)] = f"f{n}"
        idmap[str(field.id)] = token("field", f"f{n}")
        for m, option in enumerate(field.options or [], 1):
            if isinstance(option, dict) and option.get("id"):
                idmap[str(option["id"]).lower()] = token("option", f"f{n}o{m}")

    fields = []
    skipped = set()
    for field in field_rows:
        settings = dict(field.settings or {})
        out_settings = {}
        if field.field_type == CustomField.RELATION:
            target_id = str(settings.get("target_project_id") or "")
            if settings.get("is_mirror"):
                primary = by_id.get(str(settings.get("mirror_field_id") or ""))
                if primary is None:
                    # The other side of a two-way relation made on another board: that board owns it.
                    notes.append(
                        f'Left out "{field.name}": it is the other side of a two-way relation made on another board.'
                    )
                    skipped.add(str(field.id))
                # Same-board two-way: the mirror is remade from its primary (see below).
                continue
            if target_id == str(project.id):
                out_settings = {"target": "self"}
            else:
                out_settings = {"target": "pick", "board_name": _board_name_for(user, target_id)}
            out_settings["two_way"] = bool(settings.get("two_way"))
            mirror = by_id.get(str(settings.get("mirror_field_id") or ""))
            if mirror is not None:
                out_settings["mirror_key"] = keys[str(mirror.id)]
                out_settings["mirror_name"] = mirror.name
                out_settings["mirror_sort_order"] = mirror.sort_order
        elif field.field_type == CustomField.ROLLUP:
            relation_id = str(settings.get("relation_field_id") or "")
            relation = by_id.get(relation_id)
            if relation is None or relation_id in skipped:
                notes.append(f'Left out "{field.name}": its relation field is not part of this board.')
                skipped.add(str(field.id))
                continue
            out_settings = {"relation": keys[relation_id], "function": settings.get("function")}
            target_key = settings.get("target_field_id")
            if isinstance(target_key, str) and target_key.startswith("@"):
                out_settings["target_builtin"] = target_key
            elif target_key:
                if str(target_key) in by_id:
                    out_settings["target_field"] = keys[str(target_key)]
                else:
                    target = CustomField.objects.filter(pk=target_key).first()
                    out_settings["target_field_name"] = target.name if target else None
        else:
            out_settings = tokenize(settings, idmap)
        fields.append(
            {
                "key": keys[str(field.id)],
                "name": field.name,
                "description": field.description or "",
                "field_type": field.field_type,
                "options": [
                    {"key": f"{keys[str(field.id)]}o{m}", "name": o.get("name", ""), "color": o.get("color", "")}
                    for m, o in enumerate(field.options or [], 1)
                    if isinstance(o, dict)
                ],
                "settings": out_settings,
                "sort_order": field.sort_order,
            }
        )
    for field_id in skipped:
        idmap.pop(field_id, None)

    # Saved views on the board (private views stay with their owner).
    views = []
    view_rows = IssueView.objects.filter(project=project, archived_at__isnull=True).filter(
        Q(access=1) | Q(owned_by=user)
    )
    for view in view_rows.order_by("sort_order"):
        views.append(
            {
                "name": view.name,
                "description": view.description or "",
                "filters": tokenize(view.filters or {}, idmap),
                "display_filters": tokenize(view.display_filters or {}, idmap),
                "display_properties": tokenize(view.display_properties or {}, idmap),
                "rich_filters": tokenize(view.rich_filters or {}, idmap),
                "logo_props": tokenize(view.logo_props or {}, idmap),
                "access": view.access,
            }
        )

    # The saver's own layout of the board (layout type, group, sort, shown properties, card faces).
    layout = None
    prop = ProjectUserProperty.objects.filter(project=project, user=user).first()
    if prop is not None:
        layout = {
            "filters": tokenize(prop.filters or {}, idmap),
            "display_filters": tokenize(prop.display_filters or {}, idmap),
            "display_properties": tokenize(prop.display_properties or {}, idmap),
            "rich_filters": tokenize(prop.rich_filters or {}, idmap),
        }

    templates = [
        {
            "name": t.name,
            "description": t.description or "",
            "data": tokenize(_travel_card(t.data or {}), idmap),
            "sort_order": t.sort_order,
        }
        for t in IssueTemplate.objects.filter(project=project).order_by("sort_order", "name")
    ]

    sample_cards = []
    if include_samples:
        sample_cards = _capture_samples(project, user, idmap, include_repeat_rules, notes)

    settings = {key: getattr(project, key) for key in BOARD_SETTINGS if hasattr(project, key)}
    doc = {
        "format": FORMAT,
        "schema_version": SCHEMA_VERSION,
        "board": {
            "description": project.description or "",
            "logo_props": tokenize(project.logo_props or {}, idmap),
            "settings": settings,
        },
        "states": states,
        "default_state": TOKEN_RE.match(default_state).group("key") if default_state else None,
        "labels": labels,
        "fields": fields,
        "views": views,
        "layout": layout,
        "templates": templates,
        "sample_cards": [],
        "notes": notes,
    }
    # Email addresses are people's data: only sample cards (ticked on purpose) may keep them.
    scrubbed = []

    def scrub(text):
        if EMAIL_RE.search(text):
            scrubbed.append(text)
            return EMAIL_RE.sub("", text)
        return text

    doc = _swap(doc, scrub)
    if scrubbed:
        doc["notes"].append("Email addresses were removed from the design.")
    doc["sample_cards"] = sample_cards
    return doc


def _travel_card(node):
    """A template / sample card node made safe to travel: clean body, sub-cards too."""
    if not isinstance(node, dict):
        return {}
    node = dict(node)
    node["description_html"] = clean_body(node.get("description_html"))
    node["sub_items"] = [_travel_card(child) for child in node.get("sub_items") or [] if isinstance(child, dict)]
    return node


def _capture_samples(project, user, idmap, include_repeat_rules, notes):
    from plane.utils.issue_templates import snapshot_issue

    visible = _visible_card_filter(user)
    cards = visible(Issue.issue_objects.filter(project=project, parent__isnull=True)).order_by("sequence_id")
    total = cards.count()
    out = []
    for card in cards[:MAX_SAMPLE_CARDS]:
        # Clean the body first: a mention names a person, which would drop the whole body.
        node = tokenize(_travel_card(snapshot_issue(card, include_sub_items=True, visible=visible)), idmap)
        if include_repeat_rules:
            repeat = _capture_repeat(card)
            if repeat:
                node["repeat"] = repeat
        out.append(node)
    if total > MAX_SAMPLE_CARDS:
        notes.append(f"Only the first {MAX_SAMPLE_CARDS} cards were kept as sample cards.")
    return out


def _capture_repeat(card):
    try:
        from plane.recurrence.models import RepeatRule
    except ImportError:  # pragma: no cover
        return None
    rule = RepeatRule.objects.filter(issue=card, is_active=True).first()
    if rule is None:
        return None
    return {
        "frequency": rule.frequency,
        "interval": rule.interval,
        "weekdays": list(rule.weekdays or []),
        "month_day": rule.month_day,
        "time_of_day": rule.time_of_day.strftime("%H:%M") if rule.time_of_day else None,
        "timezone": rule.timezone,
        "max_count": rule.max_count,
    }


# ---------------------------------------------------------------------------
# Checking a document (imports, and every save)
# ---------------------------------------------------------------------------


def _err(message):
    return ValidationError({"error": message})


def _list(doc, key, limit):
    value = doc.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise _err(f'"{key}" must be a list.')
    if len(value) > limit:
        raise _err(f'"{key}" can hold at most {limit} items.')
    for item in value:
        if not isinstance(item, dict):
            raise _err(f'Every item in "{key}" must be an object.')
    return value


def find_ids(value, path="$"):
    """Paths in a JSON value that hold something looking like an id."""
    found = []
    if isinstance(value, str):
        if UUID_RE.search(value):
            found.append(path)
    elif isinstance(value, list):
        for n, item in enumerate(value):
            found += find_ids(item, f"{path}[{n}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if UUID_RE.search(str(key)):
                found.append(f"{path}.{key}")
            found += find_ids(item, f"{path}.{key}")
    return found


def find_emails(value, path="$"):
    found = []
    if isinstance(value, str):
        if EMAIL_RE.search(value):
            found.append(path)
    elif isinstance(value, list):
        for n, item in enumerate(value):
            found += find_emails(item, f"{path}[{n}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if EMAIL_RE.search(str(key)):
                found.append(f"{path}.{key}")
            found += find_emails(item, f"{path}.{key}")
    return found


def validate_document(doc):
    """Check a blueprint document. Returns it (normalised). Raises ValidationError."""
    import json

    if not isinstance(doc, dict):
        raise _err("A blueprint file must hold one JSON object.")
    if doc.get("format") != FORMAT:
        raise _err("This is not a board blueprint file.")
    version = doc.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise _err("The blueprint file has no schema version.")
    if version > SCHEMA_VERSION:
        raise _err(
            f"This blueprint was made by a newer version of the app (schema {version}). "
            f"This app reads schema {SCHEMA_VERSION}."
        )
    if len(json.dumps(doc)) > MAX_DOCUMENT_BYTES:
        raise _err("The blueprint file is too big (2 MB at most).")

    states = _list(doc, "states", MAX_STATES)
    labels = _list(doc, "labels", MAX_LABELS)
    fields = _list(doc, "fields", MAX_FIELDS)
    _list(doc, "views", MAX_VIEWS)
    _list(doc, "templates", MAX_TEMPLATES)
    _list(doc, "sample_cards", MAX_SAMPLE_CARDS)
    for name, items in (("states", states), ("labels", labels), ("fields", fields)):
        seen, names = set(), set()
        for item in items:
            key = item.get("key")
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", key) or key in seen:
                raise _err(f'Every item in "{name}" needs its own short "key".')
            seen.add(key)
            label = " ".join(str(item.get("name") or "").split()).lower()
            if not label:
                raise _err(f'Every item in "{name}" needs a name.')
            if label in names:
                raise _err(f'Two items in "{name}" have the same name ("{item.get("name")}").')
            names.add(label)
    for field in fields:
        if field.get("field_type") not in {c[0] for c in CustomField.ALL_TYPE_CHOICES}:
            raise _err(f'Field "{field.get("name")}" has an unknown type.')
    board = doc.get("board") or {}
    if not isinstance(board, dict) or not isinstance(board.get("settings") or {}, dict):
        raise _err('"board" must be an object.')

    ids = find_ids(doc)
    if ids:
        raise _err(f"The blueprint file holds ids from another workspace (at {ids[0]}). It cannot be used.")
    outside_samples = {k: v for k, v in doc.items() if k != "sample_cards"}
    emails = find_emails(outside_samples)
    if emails:
        raise _err(f"The blueprint file holds an email address (at {emails[0]}). Remove it and try again.")
    return doc


def summary(doc):
    """Counts for the library list and the picker."""
    doc = doc or {}
    return {
        "states": len(doc.get("states") or []),
        "labels": len(doc.get("labels") or []),
        "fields": len(doc.get("fields") or []),
        "views": len(doc.get("views") or []),
        "templates": len(doc.get("templates") or []),
        "sample_cards": len(doc.get("sample_cards") or []),
        "is_private": bool(((doc.get("board") or {}).get("settings") or {}).get("is_private")),
        "pick_boards": [
            {"key": f["key"], "name": f["name"], "board_name": (f.get("settings") or {}).get("board_name")}
            for f in doc.get("fields") or []
            if f.get("field_type") == CustomField.RELATION and (f.get("settings") or {}).get("target") == "pick"
        ],
        "notes": list(doc.get("notes") or []),
    }
