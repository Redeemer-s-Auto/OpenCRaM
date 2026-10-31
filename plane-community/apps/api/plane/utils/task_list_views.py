# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The task-list views: one definition, used by the board action and the load script.

A task list is a board whose cards move through these tabs, left to right:

- **Active**: state group is not completed and the "Seen" checkbox is not ticked.
- **Completed**: state group is completed and the "Seen" checkbox is not ticked.
- **Checked**: the "Seen" checkbox is ticked, whatever the state.
- **All**: the board's own page with no filter (drawn last by the tab bar, not a saved view).

Team members finish a task by changing its state; the card lands in Completed. The
owner ticks "Seen" to say the completion was noticed; the card moves to Checked.
``ensure_task_list_views`` is idempotent: it creates the Seen field and the three
views when missing and brings existing ones back to this definition. It never
touches a card.
"""

from django.db import transaction

from plane.db.models import CustomField, IssueView

SEEN_FIELD_NAME = "Seen"
SEEN_EXTERNAL_SOURCE = "task_list"
SEEN_EXTERNAL_ID = "seen"

ACTIVE_STATE_GROUPS = ["backlog", "unstarted", "started", "cancelled"]
COMPLETED_STATE_GROUPS = ["completed"]

VIEW_ACTIVE = "Active"
VIEW_COMPLETED = "Completed"
VIEW_CHECKED = "Checked"
VIEW_NAMES = (VIEW_ACTIVE, VIEW_COMPLETED, VIEW_CHECKED)


def seen_filter_key(field_id):
    """Filter key for the Seen checkbox, as the saved-view filter engine reads it."""
    return f"customfield_{field_id}__exact"


def view_definitions(seen_field_id):
    """The three views, keyed by name. ``rich_filters`` is the shape IssueView stores."""
    seen = seen_filter_key(seen_field_id)
    on_card = {f"cardfield_{seen_field_id}": True, f"customfield_{seen_field_id}": True}
    return {
        VIEW_ACTIVE: {
            "description": "Tasks still to do: not completed and not checked off as seen.",
            "rich_filters": {"and": [{"state_group__in": ACTIVE_STATE_GROUPS}, {seen: False}]},
            "display_properties": on_card,
            "is_hidden": False,
        },
        VIEW_COMPLETED: {
            "description": "Tasks marked completed that have not been checked off as seen.",
            "rich_filters": {"and": [{"state_group__in": COMPLETED_STATE_GROUPS}, {seen: False}]},
            "display_properties": on_card,
            "is_hidden": False,
        },
        VIEW_CHECKED: {
            "description": "Tasks checked off as seen, in any state.",
            "rich_filters": {"and": [{seen: True}]},
            "display_properties": on_card,
            "is_hidden": False,
        },
    }


def get_seen_field(project):
    """The project's Seen checkbox, or None."""
    fields = CustomField.objects.filter(project=project, deleted_at__isnull=True)
    field = fields.filter(external_source=SEEN_EXTERNAL_SOURCE, external_id=SEEN_EXTERNAL_ID).first()
    if field is None:
        field = fields.filter(name__iexact=SEEN_FIELD_NAME, field_type=CustomField.FieldType.CHECKBOX).first()
    return field


def ensure_seen_field(project, actor):
    """Return the Seen checkbox of ``project``, creating it when missing. ``(field, created)``."""
    field = get_seen_field(project)
    if field is not None:
        if field.archived_at is not None:
            field.archived_at = None
            field.save(update_fields=["archived_at", "updated_at"])
        return field, False
    name = SEEN_FIELD_NAME
    # A field named Seen of another type keeps its name; ours takes the next free one.
    taken = set(
        CustomField.objects.filter(project=project, deleted_at__isnull=True).values_list("name", flat=True)
    )
    n = 2
    while name in taken:
        name = f"{SEEN_FIELD_NAME} {n}"
        n += 1
    field = CustomField(
        project=project,
        workspace=project.workspace,
        name=name,
        description="Ticked by the owner once a completed task has been noticed.",
        field_type=CustomField.FieldType.CHECKBOX,
        external_source=SEEN_EXTERNAL_SOURCE,
        external_id=SEEN_EXTERNAL_ID,
    )
    # created_by_id: the shell script has no request user, so the base model would blank it.
    field.save(created_by_id=actor.id)
    return field, True


def _apply_view(view, definition):
    """Bring an existing view back to the definition (filters, hidden flag, card checkbox)."""
    changed = []
    if view.rich_filters != definition["rich_filters"]:
        view.rich_filters = definition["rich_filters"]
        changed.append("rich_filters")
    merged = {**(view.display_properties or {}), **definition["display_properties"]}
    if merged != (view.display_properties or {}):
        view.display_properties = merged
        changed.append("display_properties")
    if view.is_hidden != definition["is_hidden"]:
        view.is_hidden = definition["is_hidden"]
        changed.append("is_hidden")
    if view.archived_at is not None:
        view.archived_at = None
        changed.append("archived_at")
    if changed:
        view.save(update_fields=changed + ["updated_at"])
    return changed


@transaction.atomic
def ensure_task_list_views(project, actor):
    """Create or refresh the Seen field and the Active / Completed / Checked views on ``project``.

    Returns ``{"field": CustomField, "field_created": bool, "views": {name: IssueView},
    "created": [names], "updated": [names]}``. Cards are never changed.
    """
    field, field_created = ensure_seen_field(project, actor)
    definitions = view_definitions(str(field.id))
    existing = {
        v.name.strip().lower(): v
        for v in IssueView.objects.filter(project=project, deleted_at__isnull=True, name__in=VIEW_NAMES)
    }
    views, created, updated = {}, [], []
    for name in VIEW_NAMES:
        definition = definitions[name]
        view = existing.get(name.lower())
        if view is None:
            view = IssueView(
                workspace=project.workspace,
                project=project,
                name=name,
                description=definition["description"],
                query={},
                filters={},
                rich_filters=definition["rich_filters"],
                display_filters={
                    "group_by": None,
                    "order_by": "-created_at",
                    "type": None,
                    "sub_issue": True,
                    "show_empty_groups": True,
                    "layout": "list",
                    "calendar_date_range": "",
                },
                display_properties={
                    "assignee": True,
                    "attachment_count": True,
                    "created_on": True,
                    "due_date": True,
                    "estimate": True,
                    "key": True,
                    "labels": True,
                    "link": True,
                    "priority": True,
                    "start_date": True,
                    "state": True,
                    "sub_issue_count": True,
                    "updated_on": True,
                    **definition["display_properties"],
                },
                is_hidden=definition["is_hidden"],
                owned_by=actor,
                access=1,
            )
            view.save(created_by_id=actor.id)
            created.append(name)
        elif _apply_view(view, definition):
            updated.append(name)
        views[name] = view
    return {"field": field, "field_created": field_created, "views": views, "created": created, "updated": updated}
