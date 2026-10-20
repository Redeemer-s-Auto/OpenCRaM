# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Save, re-capture, import and use board blueprints. Who may do what.

Who (defaults, see the branch report):
- See and use a blueprint: workspace admins and members (not guests). A blueprint
  that is not shared is seen and used by the person who saved it only.
- Save one from a board, or update one from a board: an admin of that board, or a
  workspace admin who can see the board (a private board hides itself from
  workspace admins who are not on it).
- Rename, edit, share, delete, export: the person who saved it, or a workspace
  admin (shared blueprints only).
- Import: workspace admins and members.
"""

import uuid

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from plane.blueprints import spec as S
from plane.blueprints.models import Blueprint, BlueprintVersion, BoardOrigin
from plane.db.models import (
    CustomField,
    IssueTemplate,
    IssueView,
    Label,
    Project,
    ProjectMember,
    ProjectUserProperty,
    State,
    WorkspaceMember,
)
from plane.db.models.state import DEFAULT_STATES, StateGroup

ADMIN, MEMBER = 20, 15
NAME_MAX = 255


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def workspace_role(user, workspace_id):
    row = (
        WorkspaceMember.objects.filter(workspace_id=workspace_id, member_id=user.id, is_active=True)
        .values_list("role", flat=True)
        .first()
    )
    return row or 0


def _board_role(user, project_id):
    return (
        ProjectMember.objects.filter(project_id=project_id, member_id=user.id, is_active=True)
        .values_list("role", flat=True)
        .first()
        or 0
    )


def can_save_from(user, project):
    from plane.utils.private_projects import is_hidden_from

    if _board_role(user, project.id) >= ADMIN:
        return True
    return workspace_role(user, project.workspace_id) >= ADMIN and not is_hidden_from(user, project.id)


def visible_blueprints(user, workspace):
    if workspace_role(user, workspace.id) < MEMBER:
        return Blueprint.objects.none()
    from django.db.models import Q

    return Blueprint.objects.filter(workspace=workspace).filter(Q(is_shared=True) | Q(created_by=user))


def can_manage(user, blueprint):
    if blueprint.created_by_id == user.id:
        return True
    return blueprint.is_shared and workspace_role(user, blueprint.workspace_id) >= ADMIN


def get_visible(user, workspace, blueprint_id):
    blueprint = visible_blueprints(user, workspace).filter(pk=blueprint_id).first()
    if blueprint is None:
        raise NotFound("Blueprint not found.")
    return blueprint


def require_manage(user, blueprint):
    if not can_manage(user, blueprint):
        raise PermissionDenied("Only the person who saved this blueprint, or a workspace admin, can change it.")


def source_board(user, workspace, project_id):
    """The board to capture from, if the person may save from it. 404 when hidden or missing."""
    from plane.utils.private_projects import is_hidden_from

    project = Project.objects.filter(pk=project_id, workspace=workspace, archived_at__isnull=True).first()
    if project is None or is_hidden_from(user, project.id):
        raise NotFound("Board not found.")
    if not can_save_from(user, project):
        raise PermissionDenied("Only an admin of this board, or a workspace admin, can save it as a blueprint.")
    return project


# ---------------------------------------------------------------------------
# Save, re-capture, import
# ---------------------------------------------------------------------------


def _clean_name(value, what="A blueprint"):
    name = " ".join(str(value or "").split())[:NAME_MAX]
    if not name:
        raise ValidationError({"name": f"{what} needs a name."})
    return name


def free_name(workspace, base):
    base = _clean_name(base)[: NAME_MAX - 6]
    taken = {n.lower() for n in Blueprint.objects.filter(workspace=workspace).values_list("name", flat=True)}
    if base.lower() not in taken:
        return base
    for n in range(2, 1000):
        candidate = f"{base} ({n})"
        if candidate.lower() not in taken:
            return candidate
    return f"{base} ({uuid.uuid4().hex[:6]})"


def _logo(value):
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationError({"logo_props": "logo_props must be an object."})
    cleaned = S.detokenize(value, {})
    return cleaned if isinstance(cleaned, dict) else {}


def _full_doc(blueprint):
    """The stored spec plus the blueprint's own name, description and icon (what an export writes)."""
    doc = dict(blueprint.spec or {})
    doc["name"] = blueprint.name
    doc["description"] = blueprint.description
    doc["logo_props"] = blueprint.logo_props or {}
    doc["version"] = blueprint.version
    return doc


SAMPLES_NOT_EXPORTED = "Sample cards were left out of this file: they are real cards and stay in their workspace."


def export_document(blueprint):
    """The blueprint as a file to share with another workspace: design only, never shop data.

    Sample cards are real cards (titles, page text, field values), so a file never
    carries them, even when the blueprint holds some. The names of other boards a
    relation field links to stay behind too (the person using the file picks a board
    of their own). ``validate_document`` then refuses ids and email addresses
    anywhere in the file.
    """
    doc = _full_doc(blueprint)
    notes = [n for n in doc.get("notes") or [] if n != SAMPLES_NOT_EXPORTED]
    if doc.get("sample_cards"):
        notes.append(SAMPLES_NOT_EXPORTED)
    doc["sample_cards"] = []
    doc["notes"] = notes
    fields = []
    for field in doc.get("fields") or []:
        settings = field.get("settings") if isinstance(field, dict) else None
        if isinstance(settings, dict) and "board_name" in settings:
            field = {**field, "settings": {**settings, "board_name": None}}
        fields.append(field)
    doc["fields"] = fields
    S.validate_document(doc)  # never hand out a file this app would refuse (ids, emails)
    return doc


def _check_name_free(workspace, name, exclude=None):
    clash = Blueprint.objects.filter(workspace=workspace, name__iexact=name)
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    if clash.exists():
        raise ValidationError({"name": "This workspace already has a blueprint with this name."})


def save_from_board(user, workspace, project, data):
    name = _clean_name(data.get("name") or project.name)
    _check_name_free(workspace, name)
    include_samples = bool(data.get("include_samples", False))
    doc = S.capture(
        project,
        user,
        include_samples=include_samples,
        include_repeat_rules=include_samples and bool(data.get("include_repeat_rules", False)),
    )
    S.validate_document(doc)
    logo = _logo(data.get("logo_props")) or doc["board"].get("logo_props") or {}
    # A private board's design stays with its saver unless they choose to share it.
    shared = data.get("is_shared")
    is_shared = (not project.is_private) if shared is None else bool(shared)
    try:
        with transaction.atomic():
            blueprint = Blueprint.objects.create(
                workspace=workspace,
                name=name,
                description=str(data.get("description") or "")[:5000],
                logo_props=logo,
                spec=doc,
                is_shared=is_shared,
                source_project=project,
                created_by=user,
                updated_by=user,
            )
            BlueprintVersion.objects.create(
                blueprint=blueprint, version=1, spec=doc, note="Saved from a board", created_by=user
            )
    except IntegrityError:
        raise ValidationError({"name": "This workspace already has a blueprint with this name."})
    return blueprint


def recapture(user, blueprint, project, data):
    include_samples = bool(data.get("include_samples", bool((blueprint.spec or {}).get("sample_cards"))))
    doc = S.capture(
        project,
        user,
        include_samples=include_samples,
        include_repeat_rules=include_samples and bool(data.get("include_repeat_rules", False)),
    )
    S.validate_document(doc)
    with transaction.atomic():
        blueprint = Blueprint.objects.select_for_update().get(pk=blueprint.pk)
        blueprint.version += 1
        blueprint.spec = doc
        blueprint.source_project = project
        blueprint.updated_by = user
        blueprint.save()
        BlueprintVersion.objects.create(
            blueprint=blueprint, version=blueprint.version, spec=doc, note="Updated from a board", created_by=user
        )
    return blueprint


def import_document(user, workspace, doc):
    doc = S.validate_document(doc)
    name = free_name(workspace, doc.get("name") or "Imported blueprint")
    stored = {k: v for k, v in doc.items() if k not in ("name", "description", "logo_props", "version")}
    with transaction.atomic():
        blueprint = Blueprint.objects.create(
            workspace=workspace,
            name=name,
            description=str(doc.get("description") or "")[:5000],
            logo_props=_logo(doc.get("logo_props")),
            spec=stored,
            is_shared=True,
            created_by=user,
            updated_by=user,
        )
        source_version = doc.get("version")
        note = f"Imported (was v{source_version})" if isinstance(source_version, int) else "Imported"
        BlueprintVersion.objects.create(blueprint=blueprint, version=1, spec=stored, note=note, created_by=user)
    return blueprint


# ---------------------------------------------------------------------------
# Use: blueprint -> new board
# ---------------------------------------------------------------------------


def _setting(settings, key, kind):
    value = settings.get(key)
    if value is None:
        return None
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


class _Maker:
    """Makes one board from a document. ``newmap`` holds token -> new id."""

    def __init__(self, request, workspace, doc, user):
        self.request = request
        self.workspace = workspace
        self.doc = doc
        self.user = user
        self.newmap = {}
        self.notes = []
        self.project = None

    # -- board ----------------------------------------------------------
    def make_project(self, values):
        from plane.app.serializers import ProjectSerializer

        board = self.doc.get("board") or {}
        settings = board.get("settings") or {}
        data = {"page_view": False}
        for key, kind in S.BOARD_SETTINGS.items():
            value = _setting(settings, key, kind)
            if value is not None:
                data[key] = value
        if data.get("network") not in (0, 2):
            data.pop("network", None)
        data["description"] = str(board.get("description") or "")
        logo = S.detokenize(board.get("logo_props") or {}, {})
        if isinstance(logo, dict) and logo:
            data["logo_props"] = logo
        for key in ("name", "identifier", "description", "logo_props", "network"):
            if values.get(key) not in (None, "", {}):
                data[key] = values[key]
        if "identifier" in data:
            data["identifier"] = str(data["identifier"]).upper()
        serializer = ProjectSerializer(data=data, context={"workspace_id": self.workspace.id})
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        ProjectMember.objects.create(project=project, member=self.user, role=ADMIN, workspace=self.workspace)
        self.project = project
        return project

    # -- states and labels ----------------------------------------------
    def make_states(self):
        rows = self.doc.get("states") or []
        if not rows:
            rows = [{"key": f"d{n}", **s} for n, s in enumerate(DEFAULT_STATES) if s["group"] != StateGroup.TRIAGE]
            self.notes.append("The blueprint had no states, so the standard ones were used.")
        groups = {g.value for g in StateGroup} - {StateGroup.TRIAGE.value}
        default_key = self.doc.get("default_state")
        made = []
        for row in rows:
            group = row.get("group") if row.get("group") in groups else StateGroup.BACKLOG.value
            state = State(
                name=str(row["name"])[:255],
                color=row["color"][:255] if isinstance(row.get("color"), str) else "#60646C",
                group=group,
                description=str(row.get("description") or ""),
                default=False,
                project=self.project,
                workspace=self.workspace,
            )
            if isinstance(row.get("sequence"), (int, float)):
                state.sequence = row["sequence"]
            state.save(created_by_id=self.user.id)
            self.newmap[S.token("state", row["key"])] = state.id
            made.append((row, state))
        default = next((s for r, s in made if r["key"] == default_key), None)
        default = default or next((s for r, s in made if r.get("default")), None) or made[0][1]
        default.default = True
        default.save(update_fields=["default"], disable_auto_set_user=True)
        triage = next(s for s in DEFAULT_STATES if s["group"] == StateGroup.TRIAGE)
        if State.all_state_objects.filter(project=self.project, name__iexact=triage["name"]).exists():
            return self._set_default_state(default)
        State.all_state_objects.create(
            name=triage["name"],
            color=triage["color"],
            sequence=triage["sequence"],
            group=triage["group"],
            project=self.project,
            workspace=self.workspace,
            created_by=self.user,
        )
        self._set_default_state(default)

    def _set_default_state(self, default):
        if self.doc.get("default_state"):
            Project.objects.filter(pk=self.project.pk).update(default_state=default)

    def make_labels(self):
        rows = self.doc.get("labels") or []
        made = {}
        for row in rows:
            label = Label(
                name=str(row["name"])[:255],
                color=str(row.get("color") or "")[:255],
                description=str(row.get("description") or ""),
                project=self.project,
                workspace=self.workspace,
            )
            label.save(created_by_id=self.user.id)
            if isinstance(row.get("sort_order"), (int, float)):
                Label.objects.filter(pk=label.pk).update(sort_order=row["sort_order"])
            made[row["key"]] = label
            self.newmap[S.token("label", row["key"])] = label.id
        for row in rows:
            parent = made.get(row.get("parent") or "")
            if parent is not None and parent.pk != made[row["key"]].pk:
                Label.objects.filter(pk=made[row["key"]].pk).update(parent=parent)

    # -- custom fields --------------------------------------------------
    def _new_field(self, row, settings, options=()):
        field = CustomField(
            project=self.project,
            workspace=self.workspace,
            name=" ".join(str(row["name"]).split())[:255],
            description=str(row.get("description") or ""),
            field_type=row["field_type"],
            options=list(options),
            settings=settings,
        )
        if isinstance(row.get("sort_order"), (int, float)):
            field.sort_order = row["sort_order"]
        field.save(created_by_id=self.user.id)
        self.newmap[S.token("field", row["key"])] = field.id
        return field

    def make_fields(self, relation_targets):
        from plane.utils.custom_fields import check_formula_references, clean_options, clean_settings

        rows = self.doc.get("fields") or []
        plain = [r for r in rows if r.get("field_type") not in ("formula", "relation", "rollup")]
        formulas = [r for r in rows if r.get("field_type") == "formula"]
        relations = [r for r in rows if r.get("field_type") == CustomField.RELATION]
        rollups = [r for r in rows if r.get("field_type") == CustomField.ROLLUP]

        for row in plain:
            options = []
            for option in row.get("options") or []:
                new_id = str(uuid.uuid4())
                if option.get("key"):
                    self.newmap[S.token("option", option["key"])] = new_id
                options.append({"id": new_id, "name": option.get("name"), "color": option.get("color")})
            try:
                options = clean_options(row["field_type"], options)
                settings = clean_settings(row["field_type"], S.detokenize(row.get("settings") or {}, self.newmap))
            except ValidationError:
                self.notes.append(f'Left out field "{row["name"]}": its settings are not valid here.')
                continue
            self._new_field(row, settings, options)

        # Formulas name other fields, so make them once the fields they use exist.
        waiting = list(formulas)
        while waiting:
            progress = False
            for row in list(waiting):
                try:
                    settings = clean_settings("formula", row.get("settings") or {})
                    check_formula_references(self.project.id, row["name"], settings)
                except ValidationError:
                    continue
                self._new_field(row, settings)
                waiting.remove(row)
                progress = True
            if not progress:
                break
        for row in waiting:
            self.notes.append(f'Left out formula "{row["name"]}": it uses a field that is not on the new board.')

        for row in relations:
            self._make_relation(row, relation_targets)
        for row in rollups:
            self._make_rollup(row)

    def _make_relation(self, row, relation_targets):
        from plane.relations.service import clean_relation_settings, sync_mirror

        raw = row.get("settings") or {}
        if raw.get("target") == "self":
            target_id = str(self.project.id)
        else:
            target_id = (relation_targets or {}).get(row["key"])
            if not target_id:
                self.notes.append(
                    f'Left out relation "{row["name"]}": it links to another board and no board was picked.'
                )
                return
        two_way = bool(raw.get("two_way"))
        try:
            settings, _ = clean_relation_settings(
                self.project.id, {"target_project_id": target_id, "two_way": two_way}, user=self.user
            )
        except ValidationError:
            if not two_way:
                self.notes.append(f'Left out relation "{row["name"]}": you are not a member of the board picked.')
                return
            try:
                settings, _ = clean_relation_settings(
                    self.project.id, {"target_project_id": target_id, "two_way": False}, user=self.user
                )
            except ValidationError:
                self.notes.append(f'Left out relation "{row["name"]}": you are not a member of the board picked.')
                return
            self.notes.append(
                f'Relation "{row["name"]}" was made one-way: two-way needs you to be an admin of the board picked.'
            )
        field = self._new_field(row, settings)
        mirror_name = raw.get("mirror_name") if raw.get("target") == "self" else None
        sync_mirror(field, mirror_name)
        field.refresh_from_db()
        mirror_id = (field.settings or {}).get("mirror_field_id")
        if mirror_id and raw.get("mirror_key"):
            self.newmap[S.token("field", raw["mirror_key"])] = mirror_id
            if isinstance(raw.get("mirror_sort_order"), (int, float)):
                CustomField.objects.filter(pk=mirror_id).update(sort_order=raw["mirror_sort_order"])

    def _make_rollup(self, row):
        from plane.relations.service import clean_rollup_settings

        raw = row.get("settings") or {}
        relation_id = self.newmap.get(S.token("field", str(raw.get("relation") or "")))
        if relation_id is None:
            self.notes.append(f'Left out rollup "{row["name"]}": its relation field was left out.')
            return
        settings = {"relation_field_id": str(relation_id), "function": raw.get("function")}
        if raw.get("target_builtin"):
            settings["target_field_id"] = raw["target_builtin"]
        elif raw.get("target_field"):
            target = self.newmap.get(S.token("field", raw["target_field"]))
            settings["target_field_id"] = str(target) if target else None
        elif raw.get("target_field_name"):
            relation = CustomField.objects.get(pk=relation_id)
            target = CustomField.objects.filter(
                project_id=(relation.settings or {}).get("target_project_id"),
                name__iexact=raw["target_field_name"],
                archived_at__isnull=True,
            ).first()
            settings["target_field_id"] = str(target.id) if target else None
        try:
            settings = clean_rollup_settings(self.project.id, settings, user=self.user)
        except ValidationError:
            self.notes.append(f'Left out rollup "{row["name"]}": the field it adds up is not on the linked board.')
            return
        self._new_field(row, settings)

    # -- views, layout, templates ---------------------------------------
    def make_views(self):
        from plane.utils.issue_filters import issue_filters

        for row in self.doc.get("views") or []:
            filters = S.detokenize(row.get("filters") or {}, self.newmap) or {}
            view = IssueView(
                workspace=self.workspace,
                project=self.project,
                name=str(row.get("name") or "View")[:255],
                description=str(row.get("description") or ""),
                filters=filters,
                query=issue_filters(filters, "POST") if filters else {},
                display_filters=S.detokenize(row.get("display_filters") or {}, self.newmap) or {},
                display_properties=S.detokenize(row.get("display_properties") or {}, self.newmap) or {},
                rich_filters=S.detokenize(row.get("rich_filters") or {}, self.newmap) or {},
                logo_props=S.detokenize(row.get("logo_props") or {}, self.newmap) or {},
                access=1 if row.get("access", 1) == 1 else 0,
                owned_by=self.user,
            )
            view.save(created_by_id=self.user.id)

    def apply_layout(self):
        layout = self.doc.get("layout")
        if not isinstance(layout, dict):
            return
        prop, _ = ProjectUserProperty.objects.get_or_create(
            user=self.user, project=self.project, defaults={"workspace": self.workspace}
        )
        for key in ("filters", "display_filters", "display_properties", "rich_filters"):
            value = S.detokenize(layout.get(key), self.newmap)
            if isinstance(value, dict):
                setattr(prop, key, value)
        prop.save()

    def make_templates(self):
        from plane.utils.issue_templates import clean_template_data

        for row in self.doc.get("templates") or []:
            data = S.detokenize(row.get("data") or {}, self.newmap) or {}
            try:
                data = clean_template_data(self.project.id, data)
            except ValidationError:
                self.notes.append(f'Left out template "{row.get("name")}": its card is not valid here.')
                continue
            template = IssueTemplate(
                project=self.project,
                workspace=self.workspace,
                name=_clean_name(row.get("name") or "Template", "A template"),
                description=str(row.get("description") or ""),
                data=data,
            )
            if isinstance(row.get("sort_order"), (int, float)):
                template.sort_order = row["sort_order"]
            template.save(created_by_id=self.user.id)

    # -- sample cards (after the board is committed) ----------------------
    def make_samples(self):
        from plane.utils.issue_templates import create_from_template

        made = 0
        for row in self.doc.get("sample_cards") or []:
            node = S.detokenize(row, self.newmap) or {}
            repeat = node.pop("repeat", None)

            class _Card:
                name = str(node.get("name") or "Card")
                data = node

            try:
                top, count = create_from_template(self.request, self.project, _Card)
            except ValidationError:
                self.notes.append(f'Left out sample card "{_Card.name}": it is not valid here.')
                continue
            made += count
            if isinstance(repeat, dict):
                self._repeat(top, repeat)
        return made

    def _repeat(self, issue, repeat):
        try:
            from plane.recurrence.services import save_rule
        except ImportError:  # pragma: no cover
            return
        data = {k: v for k, v in repeat.items() if k in (
            "frequency", "interval", "weekdays", "month_day", "time_of_day", "timezone", "max_count"
        )}
        try:
            with transaction.atomic():
                save_rule(issue, data, self.user)
        except ValidationError:
            self.notes.append(f'The repeat rule on "{issue.name}" was left out: it is not valid here.')


def use_blueprint(request, user, blueprint, values, relation_targets=None, include_samples=True):
    """Make a new board from ``blueprint``. Returns (project, notes, sample card count)."""
    from plane.bgtasks.webhook_task import model_activity
    from plane.utils.host import base_host

    if workspace_role(user, blueprint.workspace_id) < MEMBER:
        raise PermissionDenied("Only workspace admins and members can make boards.")
    if not isinstance(relation_targets or {}, dict):
        raise ValidationError({"relation_targets": "relation_targets must be an object (field key -> board id)."})
    doc = S.validate_document(_full_doc(blueprint))
    maker = _Maker(request, blueprint.workspace, doc, user)
    with transaction.atomic():
        project = maker.make_project(values)
        maker.make_states()
        maker.make_labels()
        maker.make_fields(relation_targets or {})
        maker.make_views()
        maker.apply_layout()
        maker.make_templates()
        BoardOrigin.objects.create(
            project=project,
            blueprint=blueprint,
            blueprint_name=blueprint.name,
            version=blueprint.version,
            created_by=user,
        )
    samples = maker.make_samples() if include_samples else 0
    model_activity.delay(
        model_name="project",
        model_id=str(project.id),
        requested_data={"name": project.name, "identifier": project.identifier},
        current_instance=None,
        actor_id=user.id,
        slug=blueprint.workspace.slug,
        origin=base_host(request=request, is_app=True),
    )
    return project, list(doc.get("notes") or []) + maker.notes, samples
