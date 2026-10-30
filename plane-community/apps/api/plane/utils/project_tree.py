# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Boards inside boards: ``Project.parent`` rules.

- A parent must be in the same workspace, visible to the person setting it, never the
  project itself or one of its descendants, and the tree is at most
  ``MAX_PROJECT_TREE_DEPTH`` levels deep.
- ``parent_id`` is only ever returned to someone who can see the parent. A person who
  cannot see the parent gets ``parent_id: null`` and sees the child at the top level.
  Views annotate ``visible_parent_id`` (see ``visible_parent_id_expr``) and the
  serializers read it through ``ProjectParentIdField``.
"""

# Third party imports
from rest_framework import serializers

# Django imports
from django.db.models import Case, F, Q, UUIDField, Value, When

# Module imports
from plane.db.models import Project, ProjectMember, WorkspaceMember
from plane.db.models.project import ROLE
from plane.utils.private_projects import visible_projects_q

# Top-level boards are level 1.
MAX_PROJECT_TREE_DEPTH = 12


def _workspace_filter(workspace_id=None, slug=None, prefix=""):
    if workspace_id is not None:
        return {f"{prefix}workspace_id": workspace_id}
    return {f"{prefix}workspace__slug": slug}


def visible_project_ids(user, workspace_id=None, slug=None):
    """Values queryset of the ids ``user`` sees in the workspace project list.

    The one rule for "which boards can this person see", used by the sidebar lists
    (``ProjectViewSet.list`` / ``list_detail``) and the parent masking below:
    private projects only for active members; guests see projects they belong to;
    members see those plus public (network=2) ones; workspace admins see every
    open project; and everyone also sees the boards the resolver reaches
    (``plane.sharing.board_access``: group shares inherited down the parent chain,
    teamspaces they belong to, their own Private area, Private Readers). Boards in
    a teamspace or a Private area are closed to everyone else, admins included.
    """
    from plane.sharing.board_access import shared_project_ids

    none = Project.objects.none().values("id")
    if user is None or not user.is_authenticated:
        return none
    role = (
        WorkspaceMember.objects.filter(member=user, is_active=True, **_workspace_filter(workspace_id, slug))
        .values_list("role", flat=True)
        .first()
    )
    if role is None:
        return none

    projects = Project.objects.filter(**_workspace_filter(workspace_id, slug)).filter(
        visible_projects_q(user, workspace_id=workspace_id, slug=slug)
    )
    member_of = ProjectMember.objects.filter(member=user, is_active=True).values("project_id")
    shared = Q(id__in=shared_project_ids(user, workspace_id=workspace_id, slug=slug))
    if role == ROLE.GUEST.value:
        projects = projects.filter(Q(id__in=member_of) | shared)
    elif role == ROLE.MEMBER.value:
        projects = projects.filter(Q(id__in=member_of) | Q(network=2) | shared)
    return projects.values("id")


def visible_parent_id_expr(user, workspace_id=None, slug=None):
    """``parent_id`` when ``user`` can see the parent, else NULL. Annotate it as ``visible_parent_id``."""
    return Case(
        When(parent_id__in=visible_project_ids(user, workspace_id=workspace_id, slug=slug), then=F("parent_id")),
        default=Value(None),
        output_field=UUIDField(),
    )


def _levels_below(project_id):
    """How many levels of children sit under ``project_id`` (0 when it has none)."""
    levels = 0
    frontier = [project_id]
    while frontier and levels <= MAX_PROJECT_TREE_DEPTH:
        frontier = list(Project.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
        if frontier:
            levels += 1
    return levels


def clean_parent_id(parent_id, project, workspace_id, user):
    """Validate a requested ``parent_id`` and return the value to save.

    ``project`` is the project being edited, or None on create. Raises ``ValidationError``.
    """
    current = project.parent_id if project is not None else None
    if parent_id == current:
        return current

    visible = visible_project_ids(user, workspace_id=workspace_id)

    if parent_id is None:
        # The caller was shown parent_id null because the parent is hidden from them; a form
        # that echoes that null back must not move the board out of a parent it cannot see.
        if current is not None and not Project.objects.filter(pk=current, id__in=visible).exists():
            return current
        return None

    if project is not None and parent_id == project.id:
        raise serializers.ValidationError("A project cannot be its own parent.")

    # Same error for "does not exist", "other workspace" and "hidden from you".
    parent = Project.objects.filter(pk=parent_id, workspace_id=workspace_id, id__in=visible).first()
    if parent is None:
        raise serializers.ValidationError("Parent project not found.")

    # Walk up from the new parent. Meeting the project itself means a cycle. Bounded, so a
    # bad row can never loop forever.
    parent_depth = 1
    ancestor_id = parent.parent_id
    while ancestor_id is not None and parent_depth <= MAX_PROJECT_TREE_DEPTH:
        if project is not None and ancestor_id == project.id:
            raise serializers.ValidationError("A project cannot be moved inside one of its own sub-projects.")
        parent_depth += 1
        ancestor_id = Project.objects.filter(pk=ancestor_id).values_list("parent_id", flat=True).first()

    levels_below = _levels_below(project.id) if project is not None else 0
    if parent_depth + 1 + levels_below > MAX_PROJECT_TREE_DEPTH:
        raise serializers.ValidationError(f"Projects can be nested at most {MAX_PROJECT_TREE_DEPTH} levels deep.")

    return parent.id


class ProjectParentIdField(serializers.UUIDField):
    """``parent_id`` on project serializers.

    Write: the parent project's id, or null for top level (check it with ``clean_parent_id``).
    Read: the annotated ``visible_parent_id`` - null unless the view worked out that the
    requesting user can see the parent, so an unannotated project never leaks its parent.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        if isinstance(instance, dict):
            return instance.get("visible_parent_id")
        return getattr(instance, "visible_parent_id", None)
