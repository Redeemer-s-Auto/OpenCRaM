# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Custom field logic shared by the app API, the public API and webhooks.

Visibility rule: a value is only ever read through the work items it belongs
to. Callers pass work items (or their ids) that have already passed the
caller's visibility checks; nothing in this module lists values on its own.
"""

# Python imports
import datetime
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Django imports
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Case, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

# Third party imports
from rest_framework.exceptions import ValidationError

# Module imports
from plane.db.models import CustomField, CustomFieldValue, WorkspaceMember
from plane.utils import formula

FT = CustomField.FieldType

TEXT_MAX = 1000
LONG_TEXT_MAX = 20000
URL_MAX = 2048
OPTION_NAME_MAX = 255
MAX_OPTIONS = 500
# Money is whole cents. Cap at one trillion dollars.
MONEY_MAX_CENTS = 100_000_000_000_000
NUMBER_MAX = Decimal("1e17")

FILTER_KEY_PREFIX = "customfield_"
ORDER_KEY_PREFIX = "custom_field__"
ORDER_ANNOTATION = "custom_field_sort"

_FILTER_KEY_RE = re.compile(r"^customfield_(?P<id>[0-9a-fA-F-]{36})(?:__(?P<lookup>[a-z]+))?$")
_RELATIVE_DATE_RE = re.compile(r"^@today(?:(?P<sign>[+-])(?P<days>\d{1,4}))?$")

_url_validator = URLValidator(schemes=["http", "https"])


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------


def clean_options(field_type, options, existing=None):
    """Validate an option list for select, multi_select and label fields.

    Each option is ``{"id", "name", "color"}``. A missing id gets a new one.
    Ids of ``existing`` options are kept so values stay linked after a rename.
    """
    if field_type not in CustomField.OPTION_TYPES:
        return []
    if options is None:
        return existing or []
    if not isinstance(options, list):
        raise ValidationError({"options": "Options must be a list."})
    if len(options) > MAX_OPTIONS:
        raise ValidationError({"options": f"A field can have at most {MAX_OPTIONS} options."})

    cleaned = []
    seen_ids = set()
    seen_names = set()
    for option in options:
        if isinstance(option, str):
            option = {"name": option}
        if not isinstance(option, dict):
            raise ValidationError({"options": "Each option must be an object with a name."})
        name = str(option.get("name", "")).strip()
        if not name:
            raise ValidationError({"options": "Each option needs a name."})
        if len(name) > OPTION_NAME_MAX:
            raise ValidationError({"options": f"Option names can be at most {OPTION_NAME_MAX} characters."})
        if name.lower() in seen_names:
            raise ValidationError({"options": f"The option '{name}' is listed twice."})
        option_id = str(option.get("id") or uuid.uuid4())
        if option_id in seen_ids:
            raise ValidationError({"options": "Option ids must be unique."})
        color = str(option.get("color") or "")[:32]
        seen_ids.add(option_id)
        seen_names.add(name.lower())
        cleaned.append({"id": option_id, "name": name, "color": color})
    return cleaned


def clean_settings(field_type, settings):
    settings = settings or {}
    if not isinstance(settings, dict):
        raise ValidationError({"settings": "Settings must be an object."})
    if field_type in CustomField.LINKED_TYPES:
        # Relation and rollup settings need the board and the user; the field serializer
        # checks them with plane.relations.service.
        return dict(settings)
    if field_type in CustomField.AUDIT_TYPES:
        return {}
    cleaned = {}
    if field_type == FT.DATE:
        cleaned["include_time"] = bool(settings.get("include_time", False))
    if field_type == FT.PERSON:
        cleaned["multiple"] = bool(settings.get("multiple", False))
    if field_type == FT.NUMBER:
        # None means "keep what was typed" (up to 6 places).
        decimals = settings.get("decimals")
        if decimals is None:
            return cleaned
        try:
            decimals = int(decimals)
        except (TypeError, ValueError):
            raise ValidationError({"settings": "decimals must be a whole number."})
        cleaned["decimals"] = max(0, min(decimals, 6))
    if field_type == FT.FORMULA:
        expression = settings.get("expression")
        result_type = settings.get("result_type", "number")
        if result_type not in CustomField.FORMULA_RESULT_TYPES:
            choices = ", ".join(sorted(CustomField.FORMULA_RESULT_TYPES))
            raise ValidationError({"settings": f"result_type must be one of: {choices}."})
        try:
            formula.parse(expression)
        except formula.FormulaError as e:
            raise ValidationError({"settings": f"Formula: {e}"})
        cleaned["expression"] = expression.strip()
        cleaned["result_type"] = result_type
    return cleaned


# Built-in card properties a formula can read with prop("..."). A custom field with
# the same name wins.
BUILTIN_PROPS = {
    "Title": lambda issue: issue.name,
    "Start date": lambda issue: issue.start_date,
    "Due date": lambda issue: issue.target_date,
    "Priority": lambda issue: issue.priority,
    "State": lambda issue: issue.state.name if issue.state_id and issue.state else None,
    "Created": lambda issue: issue.created_at,
}


def effective_type(field):
    """The type a field's stored value behaves as. A formula behaves as its result type."""
    if field.field_type == FT.FORMULA:
        return {
            "number": FT.NUMBER,
            "money": FT.MONEY,
            "text": FT.TEXT,
            "date": FT.DATE,
            "checkbox": FT.CHECKBOX,
        }.get((field.settings or {}).get("result_type"), FT.NUMBER)
    return field.field_type


def check_formula_references(project_id, field_name, settings, field_id=None):
    """A formula must only name existing fields and must not loop back to itself."""
    tree = formula.parse(settings["expression"])
    fields = {
        f.name: f
        for f in CustomField.objects.filter(project_id=project_id, archived_at__isnull=True).exclude(pk=field_id)
    }
    known = set(fields) | set(BUILTIN_PROPS)
    for name in formula.referenced_names(tree):
        if name == field_name:
            raise ValidationError({"settings": "Formula: a formula cannot use itself."})
        if name in fields and fields[name].field_type in CustomField.LINKED_TYPES:
            # Formula results are stored for everyone; linked cards differ per viewer.
            raise ValidationError(
                {"settings": f'Formula: "{name}" is a relation or rollup, which formulas cannot use.'}
            )
        if name not in known:
            raise ValidationError({"settings": f'Formula: there is no field called "{name}" on this project.'})

    # Loop check across formula fields: A uses B uses A.
    graph = {}
    for f in fields.values():
        if f.field_type == FT.FORMULA:
            try:
                graph[f.name] = set(formula.referenced_names(formula.parse(f.settings.get("expression", ""))))
            except formula.FormulaError:
                graph[f.name] = set()
    graph[field_name] = set(formula.referenced_names(tree))

    def reaches(start, target, seen):
        for nxt in graph.get(start, ()):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                if reaches(nxt, target, seen):
                    return True
        return False

    if reaches(field_name, field_name, set()):
        raise ValidationError({"settings": "Formula: these formulas use each other in a loop."})


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


def _empty(raw):
    return raw is None or raw == "" or raw == []


def _to_list(raw):
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return [raw]


def clean_value(field, raw, new_label_options=None):
    """Return ``(value, typed_columns)`` for one field, or raise ValidationError.

    ``value`` is None when the input means "clear this field".
    ``new_label_options`` collects options created on the fly by label fields.
    """
    if _empty(raw):
        return None, {}

    t = field.field_type
    err = lambda msg: ValidationError({str(field.id): msg})  # noqa: E731

    if t in (FT.TEXT, FT.LONG_TEXT):
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            raise err("Must be text.")
        text = str(raw)
        if t == FT.TEXT:
            text = " ".join(text.split())
            if len(text) > TEXT_MAX:
                raise err(f"Text can be at most {TEXT_MAX} characters.")
        else:
            text = text.strip()
            if len(text) > LONG_TEXT_MAX:
                raise err(f"Long text can be at most {LONG_TEXT_MAX} characters.")
        if not text:
            return None, {}
        return text, {"value_text": text}

    if t == FT.URL:
        if not isinstance(raw, str):
            raise err("Must be a link.")
        url = raw.strip()
        if len(url) > URL_MAX:
            raise err(f"Links can be at most {URL_MAX} characters.")
        if "://" not in url:
            url = "https://" + url
        try:
            _url_validator(url)
        except DjangoValidationError:
            raise err("Must be a valid http or https link.")
        return url, {"value_text": url}

    if t == FT.NUMBER:
        if isinstance(raw, bool):
            raise err("Must be a number.")
        try:
            number = Decimal(str(raw).strip())
        except (InvalidOperation, ValueError):
            raise err("Must be a number.")
        if not number.is_finite() or abs(number) >= NUMBER_MAX:
            raise err("Number is out of range.")
        decimals = (field.settings or {}).get("decimals")
        number = round(number, 6 if decimals is None else min(int(decimals), 6))
        value = int(number) if number == number.to_integral_value() else float(number)
        return value, {"value_number": number}

    if t == FT.MONEY:
        # Whole cents only. 121400 means $1,214.00.
        if isinstance(raw, bool):
            raise err("Money must be a whole number of cents.")
        if isinstance(raw, float):
            if not raw.is_integer():
                raise err("Money must be a whole number of cents.")
            raw = int(raw)
        if isinstance(raw, str) and re.fullmatch(r"-?\d+", raw.strip()):
            raw = int(raw.strip())
        if not isinstance(raw, int):
            raise err("Money must be a whole number of cents.")
        if abs(raw) >= MONEY_MAX_CENTS:
            raise err("Amount is out of range.")
        return raw, {"value_number": Decimal(raw)}

    if t == FT.DATE:
        if not isinstance(raw, str):
            raise err("Must be a date (YYYY-MM-DD).")
        if (field.settings or {}).get("include_time"):
            parsed = parse_datetime(raw.strip())
            if parsed is None:
                only_date = parse_date(raw.strip())
                if only_date is None:
                    raise err("Must be a date and time (ISO 8601).")
                parsed = datetime.datetime.combine(only_date, datetime.time())
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            parsed = parsed.astimezone(datetime.timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z"), {"value_datetime": parsed}
        try:
            parsed = parse_date(raw.strip()[:10])
        except ValueError:
            parsed = None
        if parsed is None:
            raise err("Must be a date (YYYY-MM-DD).")
        return parsed.isoformat(), {"value_date": parsed}

    if t == FT.CHECKBOX:
        if isinstance(raw, bool):
            checked = raw
        elif isinstance(raw, str) and raw.lower() in ("true", "false"):
            checked = raw.lower() == "true"
        else:
            raise err("Must be true or false.")
        return checked, {"value_bool": checked}

    if t == FT.SELECT:
        if not isinstance(raw, str):
            raise err("Must be one option id.")
        by_id = {o["id"]: o for o in field.options or []}
        if raw not in by_id:
            raise err("Not one of this field's options.")
        return raw, {"value_text": by_id[raw]["name"]}

    if t in (FT.MULTI_SELECT, FT.LABEL):
        options = list(field.options or [])
        by_id = {o["id"]: o for o in options}
        by_name = {o["name"].lower(): o for o in options}
        ids = []
        for item in _to_list(raw):
            if isinstance(item, str) and item in by_id:
                option_id = item
            elif t == FT.LABEL and isinstance(item, (str, dict)):
                # Labels can grow: an unknown name (or {"name", "color"}) adds a new option.
                name = (item.get("name") if isinstance(item, dict) else item) or ""
                name = str(name).strip()
                if not name or len(name) > OPTION_NAME_MAX:
                    raise err("Each label needs a name of at most 255 characters.")
                existing = by_name.get(name.lower())
                if existing is None:
                    if len(options) >= MAX_OPTIONS:
                        raise err(f"A field can have at most {MAX_OPTIONS} labels.")
                    color = str(item.get("color") or "")[:32] if isinstance(item, dict) else ""
                    existing = {"id": str(uuid.uuid4()), "name": name, "color": color}
                    options.append(existing)
                    by_id[existing["id"]] = existing
                    by_name[name.lower()] = existing
                    if new_label_options is not None:
                        new_label_options.setdefault(field.id, []).append(existing)
                option_id = existing["id"]
            else:
                raise err("Not one of this field's options.")
            if option_id not in ids:
                ids.append(option_id)
        if not ids:
            return None, {}
        return ids, {"value_text": ", ".join(by_id[i]["name"] for i in ids)}

    if t == FT.PERSON:
        ids = []
        for item in _to_list(raw):
            try:
                ids.append(str(uuid.UUID(str(item))))
            except (ValueError, TypeError, AttributeError):
                raise err("Each person must be a user id.")
        ids = list(dict.fromkeys(ids))
        if not (field.settings or {}).get("multiple") and len(ids) > 1:
            raise err("This field allows one person only.")
        members = dict(
            WorkspaceMember.objects.filter(
                workspace_id=field.workspace_id, member_id__in=ids, is_active=True
            ).values_list("member_id", "member__display_name")
        )
        members = {str(k): v for k, v in members.items()}
        missing = [i for i in ids if i not in members]
        if missing:
            raise err("Each person must be an active member of this workspace.")
        if not ids:
            return None, {}
        return ids, {"value_text": ", ".join(members[i] for i in ids)}

    raise err("Unknown field type.")


def validate_values(project_id, data, current=None):
    """Check a ``{field_id: value}`` dict for a project.

    Returns a list of ``(field, value, typed_columns)``. Raises ValidationError
    for unknown or archived fields and for bad values. Nothing is saved.

    ``current`` is the work item's stored ``{field_id: value}``. Keys whose value
    did not change are skipped, so a client may send back the whole map.
    """
    if data is None:
        return []
    if not isinstance(data, dict):
        raise ValidationError({"custom_fields": "Must be an object of field id to value."})
    if current:
        data = {k: v for k, v in data.items() if str(k) not in current or current[str(k)] != v}

    ids = []
    for key in data.keys():
        try:
            ids.append(uuid.UUID(str(key)))
        except ValueError:
            raise ValidationError({"custom_fields": f"'{key}' is not a field id."})

    fields = {
        str(f.id): f for f in CustomField.objects.filter(project_id=project_id, id__in=ids, archived_at__isnull=True)
    }
    errors = {}
    cleaned = []
    new_label_options = {}
    for key, raw in data.items():
        field = fields.get(str(uuid.UUID(str(key))))
        if field is None:
            errors[str(key)] = "This field does not exist on this project or is archived."
            continue
        if field.field_type in (FT.FORMULA, CustomField.ROLLUP) or field.field_type in CustomField.AUDIT_TYPES:
            # Formulas, rollups and audit fields are worked out by the server. A client sending one back is ignored.
            continue
        try:
            if field.field_type == CustomField.RELATION:
                from plane.relations.service import clean_relation_value

                now = (current or {}).get(str(field.id))
                cleaned.append((field, clean_relation_value(field, raw, current=now), None))
                continue
            value, columns = clean_value(field, raw, new_label_options)
        except ValidationError as e:
            errors.update(e.detail if isinstance(e.detail, dict) else {str(field.id): e.detail})
            continue
        cleaned.append((field, value, columns))
    if errors:
        raise ValidationError({"custom_fields": errors})
    # Remember which label options to add when the values are saved.
    for field, _, _ in cleaned:
        if field.id in new_label_options:
            field._new_label_options = new_label_options[field.id]
    return cleaned


_TYPED_COLUMNS = ("value_text", "value_number", "value_date", "value_datetime", "value_bool")


@transaction.atomic
def set_values(issue, cleaned):
    """Save cleaned values (from ``validate_values``) on one work item.

    Returns a dict of what changed: ``{field_id: (old_value, new_value)}``.
    """
    changes = {}
    if not cleaned:
        return changes
    linked = [(f, v) for f, v, _ in cleaned if f.field_type == CustomField.RELATION]
    if linked:
        from plane.relations.service import set_links

        for field, ids in linked:
            old_ids, new_ids = set_links(issue, field, ids)
            if set(old_ids) != set(new_ids):
                changes[str(field.id)] = (old_ids, new_ids)
        cleaned = [(f, v, c) for f, v, c in cleaned if f.field_type != CustomField.RELATION]
        if not cleaned:
            return changes
    existing = {
        v.field_id: v
        for v in CustomFieldValue.objects.select_for_update().filter(
            issue_id=issue.id, field_id__in=[f.id for f, _, _ in cleaned]
        )
    }
    for field, value, columns in cleaned:
        new_options = getattr(field, "_new_label_options", None)
        if new_options:
            # Re-read under lock so two cards adding labels at once do not lose one.
            locked = CustomField.objects.select_for_update().get(pk=field.id)
            known = {o["id"] for o in locked.options}
            locked.options = list(locked.options) + [o for o in new_options if o["id"] not in known]
            locked.save(update_fields=["options", "updated_at"])
            field.options = locked.options
            field._new_label_options = None

        row = existing.get(field.id)
        old_value = row.value if row else None
        if value is None:
            if row is not None:
                row.delete(soft=False)
                changes[str(field.id)] = (old_value, None)
            continue
        typed = {c: columns.get(c) for c in _TYPED_COLUMNS}
        if row is None:
            CustomFieldValue.objects.create(
                issue_id=issue.id,
                field=field,
                project_id=issue.project_id,
                workspace_id=issue.workspace_id,
                value=value,
                **typed,
            )
        else:
            if row.value == value:
                continue
            row.value = value
            for c, v in typed.items():
                setattr(row, c, v)
            row.save()
        changes[str(field.id)] = (old_value, value)
    compute_formulas(issue)
    return changes


# ---------------------------------------------------------------------------
# Formulas: values are worked out on the server and stored like any other value
# ---------------------------------------------------------------------------


def _prop_value(field, value):
    """Turn a stored value into what a formula sees."""
    if value is None:
        return None
    t = effective_type(field)
    if t == FT.NUMBER:
        return Decimal(str(value))
    if t == FT.MONEY:
        return Decimal(int(value)) / 100
    if t == FT.CHECKBOX:
        return bool(value)
    if t == FT.DATE:
        text = str(value)
        if "T" in text:
            return parse_datetime(text.replace("Z", "+00:00"))
        return parse_date(text[:10])
    if t == FT.SELECT:
        return next((o["name"] for o in field.options or [] if o["id"] == value), None)
    if t in (FT.MULTI_SELECT, FT.LABEL):
        by_id = {o["id"]: o["name"] for o in field.options or []}
        return [by_id[i] for i in _to_list(value) if i in by_id]
    if t == FT.PERSON:
        names = dict(
            WorkspaceMember.objects.filter(workspace_id=field.workspace_id, member_id__in=_to_list(value)).values_list(
                "member_id", "member__display_name"
            )
        )
        return [names.get(uuid.UUID(i), "") for i in _to_list(value)]
    return str(value)


def _formula_result(field, result):
    """Turn a formula result into (stored value, typed columns), or (None, {}) for empty."""
    if result is None:
        return None, {}
    t = (field.settings or {}).get("result_type", "number")
    if t == "number":
        number = formula._to_number(result)
        if number is None or not number.is_finite() or abs(number) >= NUMBER_MAX:
            return None, {}
        number = round(number, 6)
        value = int(number) if number == number.to_integral_value() else float(number)
        return value, {"value_number": number}
    if t == "money":
        number = formula._to_number(result)
        if number is None or not number.is_finite():
            return None, {}
        cents = int((number * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if abs(cents) >= MONEY_MAX_CENTS:
            return None, {}
        return cents, {"value_number": Decimal(cents)}
    if t == "checkbox":
        checked = formula._truthy(result)
        return checked, {"value_bool": checked}
    if t == "date":
        if isinstance(result, datetime.datetime):
            if timezone.is_naive(result):
                result = timezone.make_aware(result, datetime.timezone.utc)
            result = result.astimezone(datetime.timezone.utc)
            return result.isoformat().replace("+00:00", "Z"), {"value_datetime": result, "value_date": result.date()}
        if isinstance(result, datetime.date):
            return result.isoformat(), {"value_date": result}
        return None, {}
    text = formula._to_text(result)[:TEXT_MAX]
    if not text:
        return None, {}
    return text, {"value_text": text}


def _formula_order(formula_fields):
    """Formula fields in an order where each comes after the formulas it uses."""
    by_name = {f.name: f for f in formula_fields}
    deps = {}
    for f in formula_fields:
        try:
            names = formula.referenced_names(formula.parse(f.settings.get("expression", "")))
        except formula.FormulaError:
            names = []
        deps[f.name] = [n for n in names if n in by_name]
    ordered, done, visiting = [], set(), set()

    def visit(name):
        if name in done or name in visiting:
            return
        visiting.add(name)
        for dep in deps.get(name, []):
            visit(dep)
        visiting.discard(name)
        done.add(name)
        ordered.append(by_name[name])

    for f in formula_fields:
        visit(f.name)
    return ordered


def compute_formulas(issue, fields=None):
    """Work out every formula field on one card and store the results."""
    if fields is None:
        fields = list(CustomField.objects.filter(project_id=issue.project_id, archived_at__isnull=True))
    formula_fields = [f for f in fields if f.field_type == FT.FORMULA]
    if not formula_fields:
        return
    by_name = {f.name: f for f in fields}
    stored = {row.field_id: row for row in CustomFieldValue.objects.filter(issue_id=issue.id, field__in=fields)}
    computed = {}

    def get_prop(name):
        field = by_name.get(name)
        if field is not None:
            if field.id in computed:
                return computed[field.id]
            row = stored.get(field.id)
            return _prop_value(field, row.value if row else None)
        builtin = BUILTIN_PROPS.get(name)
        return builtin(issue) if builtin else None

    for field in _formula_order(formula_fields):
        try:
            result = formula.evaluate(formula.parse(field.settings.get("expression", "")), get_prop)
        except formula.FormulaError:
            result = None
        value, columns = _formula_result(field, result)
        computed[field.id] = _prop_value(field, value)
        _store_formula_value(issue, field, stored.get(field.id), value, columns)


def _store_formula_value(issue, field, row, value, columns):
    if value is None:
        if row is not None:
            CustomFieldValue.all_objects.filter(pk=row.pk).delete()
        return
    typed = {c: columns.get(c) for c in _TYPED_COLUMNS}
    if row is None:
        CustomFieldValue.objects.create(
            issue_id=issue.id,
            field=field,
            project_id=issue.project_id,
            workspace_id=issue.workspace_id,
            value=value,
            **typed,
        )
    elif row.value != value or any(getattr(row, c) != v for c, v in typed.items()):
        row.value = value
        for c, v in typed.items():
            setattr(row, c, v)
        row.save()


def recompute_project_formulas(project_id):
    """Work out formulas again on every card of a project (after a field changes)."""
    from plane.db.models import Issue

    fields = list(CustomField.objects.filter(project_id=project_id, archived_at__isnull=True))
    if not any(f.field_type == FT.FORMULA for f in fields):
        return
    for issue in Issue.issue_objects.filter(project_id=project_id).select_related("state"):
        compute_formulas(issue, fields)


def refresh_display_text(field):
    """Re-derive ``value_text`` after option names change (for sort and search)."""
    if field.field_type not in CustomField.OPTION_TYPES:
        return
    by_id = {o["id"]: o["name"] for o in field.options or []}
    keep, drop = [], []
    for row in CustomFieldValue.objects.filter(field_id=field.id):
        ids = _to_list(row.value) if row.value is not None else []
        kept = [i for i in ids if i in by_id]
        if not kept:
            # The option was removed from the field, so the value goes too.
            drop.append(row.pk)
            continue
        row.value = kept[0] if field.field_type == FT.SELECT else kept
        row.value_text = ", ".join(by_id[i] for i in kept)
        keep.append(row)
    if drop:
        CustomFieldValue.all_objects.filter(pk__in=drop).delete()
    CustomFieldValue.objects.bulk_update(keep, ["value", "value_text"], batch_size=500)


# ---------------------------------------------------------------------------
# Reading values for work items (always scoped to the items given)
# ---------------------------------------------------------------------------


def display_value(field, value):
    """Plain text for activity logs and exports."""
    if value is None or value == []:
        return ""
    t = effective_type(field)
    if t == FT.MONEY:
        cents = int(value)
        sign = "-" if cents < 0 else ""
        return f"{sign}${abs(cents) // 100:,}.{abs(cents) % 100:02d}"
    if t == FT.CHECKBOX:
        return "Yes" if value else "No"
    if t in CustomField.OPTION_TYPES:
        by_id = {o["id"]: o["name"] for o in field.options or []}
        return ", ".join(by_id.get(i, "") for i in _to_list(value) if by_id.get(i))
    if t == FT.PERSON:
        names = dict(
            WorkspaceMember.objects.filter(workspace_id=field.workspace_id, member_id__in=_to_list(value)).values_list(
                "member_id", "member__display_name"
            )
        )
        return ", ".join(names.get(uuid.UUID(i), "") for i in _to_list(value))
    return str(value)


def values_for_issues(issue_ids, user=None):
    """Return ``{issue_id: {field_id: value}}`` for live (not archived) fields.

    Relation and rollup values depend on who is looking (``plane.relations``): they
    are worked out for ``user``, or the request's user when not given, and left out
    when there is no user (background jobs, webhooks, exports).
    """
    issue_ids = [i for i in issue_ids if i]
    if not issue_ids:
        return {}
    result = {}
    rows = CustomFieldValue.objects.filter(
        issue_id__in=issue_ids, field__archived_at__isnull=True, field__deleted_at__isnull=True
    ).values_list("issue_id", "field_id", "value")
    for issue_id, field_id, value in rows:
        result.setdefault(str(issue_id), {})[str(field_id)] = value

    from plane.relations.service import linked_values

    for issue_id, values in linked_values(issue_ids, user).items():
        result.setdefault(issue_id, {}).update(values)
    for issue_id, values in audit_values(issue_ids).items():
        result.setdefault(issue_id, {}).update(values)
    return result


# Created / last edited fields read these columns of the card.
AUDIT_COLUMNS = {
    CustomField.CREATED_TIME: "created_at",
    CustomField.LAST_EDITED_TIME: "updated_at",
    CustomField.CREATED_BY: "created_by_id",
    CustomField.LAST_EDITED_BY: "updated_by_id",
}
# What the sort uses: people sort by name, not by id.
AUDIT_SORT = {
    CustomField.CREATED_TIME: "created_at",
    CustomField.LAST_EDITED_TIME: "updated_at",
    CustomField.CREATED_BY: "created_by__display_name",
    CustomField.LAST_EDITED_BY: "updated_by__display_name",
}


def audit_values(issue_ids):
    """``{issue_id: {field_id: value}}`` for created/last edited fields on these cards.

    Times are ISO date-times. People are a one-item list of user ids (the shape of a person
    field), or None when the card has no such person (made by a background job, say).
    """
    from plane.db.models import Issue

    fields = list(
        CustomField.objects.filter(
            field_type__in=list(CustomField.AUDIT_TYPES),
            archived_at__isnull=True,
            project_id__in=Issue.objects.filter(pk__in=issue_ids).values("project_id"),
        ).values_list("id", "project_id", "field_type")
    )
    if not fields:
        return {}
    cards = Issue.objects.filter(pk__in=issue_ids).values(
        "id", "project_id", "created_at", "updated_at", "created_by_id", "updated_by_id"
    )
    result = {}
    for card in cards:
        for field_id, project_id, field_type in fields:
            if project_id != card["project_id"]:
                continue
            raw = card[AUDIT_COLUMNS[field_type]]
            if field_type in (CustomField.CREATED_BY, CustomField.LAST_EDITED_BY):
                value = [str(raw)] if raw else None
            else:
                value = raw.isoformat() if raw else None
            result.setdefault(str(card["id"]), {})[str(field_id)] = value
    return result


def prefetch_onto(issues, user=None):
    """Load values for many work items in one query. Returns a list of the items.

    Serializers read ``issue._custom_field_values`` when it is set.
    """
    issues = list(issues)
    values = values_for_issues([i.id for i in issues], user)
    for issue in issues:
        issue._custom_field_values = values.get(str(issue.id), {})
    return issues


def attach_to_rows(rows, key="id", user=None):
    """Add ``custom_fields`` to a list of work-item dicts, in place. Returns rows."""
    if not rows:
        return rows
    values = values_for_issues([row.get(key) for row in rows], user)
    for row in rows:
        row["custom_fields"] = values.get(str(row.get(key)), {})
    return rows


# ---------------------------------------------------------------------------
# Filters  (rich filter keys: customfield_<field_id>__<lookup>)
# ---------------------------------------------------------------------------

_LOOKUPS_BY_TYPE = {
    FT.TEXT: {"exact", "icontains", "isnull"},
    FT.LONG_TEXT: {"icontains", "isnull"},
    FT.URL: {"exact", "icontains", "isnull"},
    FT.NUMBER: {"exact", "gt", "gte", "lt", "lte", "range", "isnull"},
    FT.MONEY: {"exact", "gt", "gte", "lt", "lte", "range", "isnull"},
    FT.DATE: {"exact", "gt", "gte", "lt", "lte", "range", "isnull"},
    FT.CHECKBOX: {"exact"},
    FT.SELECT: {"exact", "in", "isnull"},
    # "exact" with one id means the same as "in" (the filter screen sends it for a single pick).
    FT.MULTI_SELECT: {"exact", "in", "isnull"},
    FT.LABEL: {"exact", "in", "isnull"},
    FT.PERSON: {"exact", "in", "isnull"},
    CustomField.CREATED_TIME: {"exact", "gt", "gte", "lt", "lte", "range"},
    CustomField.LAST_EDITED_TIME: {"exact", "gt", "gte", "lt", "lte", "range"},
    CustomField.CREATED_BY: {"exact", "in", "isnull"},
    CustomField.LAST_EDITED_BY: {"exact", "in", "isnull"},
}


def is_filter_key(key):
    return isinstance(key, str) and key.startswith(FILTER_KEY_PREFIX)


def parse_filter_key(key):
    match = _FILTER_KEY_RE.match(key or "")
    if not match:
        raise ValidationError(
            {"message": f"'{key}' is not a valid custom field filter.", "code": "invalid_filter_field"}
        )
    return match.group("id"), match.group("lookup") or "exact"


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _split_list(value):
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value).split(",")
    return [str(i).strip() for i in items if str(i).strip() != ""]


def _resolve_date(raw):
    raw = str(raw).strip()
    match = _RELATIVE_DATE_RE.match(raw)
    if match:
        today = timezone.localdate()
        days = int(match.group("days") or 0)
        return today + datetime.timedelta(days=days if match.group("sign") != "-" else -days)
    parsed = parse_date(raw[:10])
    if parsed is None:
        raise ValidationError({"message": f"'{raw}' is not a date.", "code": "invalid_filter_value"})
    return parsed


def _to_number(field, raw):
    try:
        if field.field_type == FT.MONEY:
            return Decimal(int(Decimal(str(raw).strip())))
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError({"message": f"'{raw}' is not a number.", "code": "invalid_filter_value"})


def _has_value_q(field, **conditions):
    return Q(pk__in=CustomFieldValue.objects.filter(field_id=field.id, **conditions).values("issue_id"))


def _audit_filter_q(field, lookup, raw):
    """Filter on the card's own created/updated columns."""
    column = AUDIT_COLUMNS[field.field_type]
    if field.field_type in (CustomField.CREATED_BY, CustomField.LAST_EDITED_BY):
        if lookup == "isnull":
            return Q(**{f"{column}__isnull": _as_bool(raw)})
        ids = _split_list(raw)
        try:
            ids = [uuid.UUID(i) for i in ids]
        except ValueError:
            raise ValidationError({"message": "People are filtered by id.", "code": "invalid_filter_value"})
        return Q(**{f"{column}__in": ids}) if ids else Q()
    # Times compare by calendar day, in the server's time zone.
    day = column.replace("_at", "_at__date")
    if lookup == "range":
        bounds = _split_list(raw)
        if len(bounds) != 2:
            raise ValidationError({"message": "A range needs two dates.", "code": "invalid_filter_value"})
        return Q(**{f"{day}__range": [_resolve_date(b) for b in bounds]})
    return Q(**{f"{day}__{lookup}" if lookup != "exact" else day: _resolve_date(raw)})


def build_filter_q(key, raw, fields_by_id):
    """Build a Q on Issue for one custom field filter key."""
    field_id, lookup = parse_filter_key(key)
    field = fields_by_id.get(field_id.lower())
    if field is None:
        raise ValidationError({"message": f"Custom field '{field_id}' does not exist.", "code": "invalid_filter_field"})
    allowed = _LOOKUPS_BY_TYPE.get(effective_type(field), set())
    if lookup not in allowed:
        raise ValidationError(
            {"message": f"'{lookup}' is not allowed for a {field.field_type} field.", "code": "invalid_filter_lookup"}
        )

    t = effective_type(field)
    if t in CustomField.AUDIT_TYPES:
        return _audit_filter_q(field, lookup, raw)
    if lookup == "isnull":
        exists = _has_value_q(field)
        return ~exists if _as_bool(raw) else exists

    if t == FT.CHECKBOX:
        checked = _has_value_q(field, value_bool=True)
        return checked if _as_bool(raw) else ~checked

    if t in (FT.TEXT, FT.LONG_TEXT, FT.URL):
        text = str(raw)
        if lookup == "icontains":
            return _has_value_q(field, value_text__icontains=text)
        return _has_value_q(field, value_text__iexact=text)

    if t in (FT.NUMBER, FT.MONEY):
        if lookup == "range":
            bounds = _split_list(raw)
            if len(bounds) != 2:
                raise ValidationError({"message": "A range needs two values.", "code": "invalid_filter_value"})
            return _has_value_q(field, value_number__range=[_to_number(field, b) for b in bounds])
        return _has_value_q(field, **{f"value_number__{lookup}": _to_number(field, raw)})

    if t == FT.DATE:
        uses_time = (field.settings or {}).get("include_time") and field.field_type != FT.FORMULA
        column = "value_datetime__date" if uses_time else "value_date"
        if lookup == "range":
            bounds = _split_list(raw)
            if len(bounds) != 2:
                raise ValidationError({"message": "A range needs two dates.", "code": "invalid_filter_value"})
            return _has_value_q(field, **{f"{column}__range": [_resolve_date(b) for b in bounds]})
        return _has_value_q(field, **{f"{column}__{lookup}": _resolve_date(raw)})

    if t == FT.SELECT:
        ids = _split_list(raw)
        return _has_value_q(field, value__in=ids)

    # multi_select, label, person: matches cards that have ANY of the ids.
    ids = _split_list(raw)
    if not ids:
        return Q()
    q = Q()
    for i in ids:
        q |= Q(value__contains=[i])
    return Q(pk__in=CustomFieldValue.objects.filter(q, field_id=field.id).values("issue_id"))


def build_flat_filters(raw, project_id):
    """Build an AND of custom field filters from a flat JSON object (public API)."""
    import json

    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        raise ValidationError({"custom_field_filters": "Must be a JSON object."})
    if not isinstance(data, dict) or not data:
        raise ValidationError({"custom_field_filters": "Must be a JSON object of filter keys to values."})
    for key in data:
        if not is_filter_key(key):
            raise ValidationError({"custom_field_filters": f"'{key}' is not a custom field filter key."})
    fields = {k: f for k, f in fields_for_filter_keys(data.keys()).items() if str(f.project_id) == str(project_id)}
    q = Q()
    for key, value in data.items():
        q &= build_filter_q(key, value, fields)
    return q


def fields_for_filter_keys(keys):
    ids = set()
    for key in keys:
        field_id, _ = parse_filter_key(key)
        ids.add(field_id.lower())
    return {str(f.id): f for f in CustomField.objects.filter(id__in=list(ids), archived_at__isnull=True)}


# ---------------------------------------------------------------------------
# Sort  (order_by=custom_field__<field_id> or -custom_field__<field_id>)
# ---------------------------------------------------------------------------


def is_order_key(order_by):
    bare = (order_by or "").lstrip("-")
    return bare.startswith(ORDER_KEY_PREFIX)


def order_queryset(issue_queryset, order_by):
    """Annotate and order by a custom field. Returns ``(queryset, order_key)``.

    Returns ``(None, None)`` when the key is not a valid live field, so the caller
    can fall back to its default order.
    """
    desc = order_by.startswith("-")
    bare = order_by[1:] if desc else order_by
    try:
        field_id = uuid.UUID(bare[len(ORDER_KEY_PREFIX) :])
    except ValueError:
        return None, None
    field = CustomField.objects.filter(id=field_id, archived_at__isnull=True).first()
    if field is None or field.field_type in CustomField.LINKED_TYPES:
        return None, None

    values = CustomFieldValue.objects.filter(issue_id=OuterRef("pk"), field_id=field.id)
    t = effective_type(field)
    if t in CustomField.AUDIT_TYPES:
        expression = F(AUDIT_SORT[t])
    elif t in (FT.NUMBER, FT.MONEY):
        expression = Subquery(values.values("value_number")[:1])
    elif t == FT.DATE:
        uses_time = (field.settings or {}).get("include_time") and field.field_type != FT.FORMULA
        column = "value_datetime" if uses_time else "value_date"
        expression = Subquery(values.values(column)[:1])
    elif t == FT.CHECKBOX:
        expression = Subquery(values.values("value_bool")[:1])
    elif t == FT.SELECT:
        # Sort dropdowns by the option order the admin set, not by name.
        positions = [When(value_text=o["name"], then=Value(i)) for i, o in enumerate(field.options or [])]
        if positions:
            expression = Subquery(
                values.annotate(
                    position=Case(*positions, default=Value(len(positions)), output_field=IntegerField())
                ).values("position")[:1]
            )
        else:
            expression = Subquery(values.values("value_text")[:1])
    else:
        expression = Subquery(values.values("value_text")[:1])

    queryset = issue_queryset.annotate(**{ORDER_ANNOTATION: expression})
    ordering = F(ORDER_ANNOTATION).desc(nulls_last=True) if desc else F(ORDER_ANNOTATION).asc(nulls_last=True)
    queryset = queryset.order_by(ordering, "-created_at")
    return queryset, (f"-{ORDER_ANNOTATION}" if desc else ORDER_ANNOTATION)
