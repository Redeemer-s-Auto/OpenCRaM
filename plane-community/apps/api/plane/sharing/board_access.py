# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Boards shared with groups: the one resolver every read path uses.

Nothing is copied per person or per card. Access is computed at read time from
the share rows, so a person added to a group sees everything shared with that
group at once, and loses it the moment they are removed.

Groups inside groups
    ``AccessGroupInclude(group=G, included_group=H)`` means G includes H: H's
    members inherit everything shared with G, and with everything that includes
    G, and so on up. ``effective_group_ids`` walks that chain with a visited set
    and a depth cap, so a bad row can never loop it.

Inheritance (the rule, in three lines)
    1. A share on a board reaches the board and every board inside it
       (``Project.parent`` chain), at the share's level.
    2. Walking up from a board, the NEAREST board that carries either a share or
       an exclusion for the group decides: share = that level, exclusion = none.
    3. A private board (``is_private``) is never reached through a group share,
       directly or inherited, and nothing flows through it to the boards inside.

Being an active project member is unchanged and always wins over a share.
"""

import uuid

from django.db.models import Case, IntegerField, Q, Value, When

from plane.db.models import Project, ProjectMember
from plane.sharing.models import AccessGroupInclude, AccessGroupMember, AccessLevel, ProjectShare, ProjectShareExclusion

# Levels of group nesting the resolver will follow. Writes reject loops; this is the belt to that brace.
MAX_GROUP_NESTING = 20
# Project.parent levels the resolver will walk. Mirrors plane.utils.project_tree.MAX_PROJECT_TREE_DEPTH.
MAX_BOARD_DEPTH = 12

ROLE_ADMIN, ROLE_MEMBER, ROLE_GUEST = 20, 15, 5


def _real_user(user):
    if user is None or getattr(user, "is_anonymous", True):
        return None
    return user


def effective_group_ids(user):
    """Set of group ids ``user`` acts as: direct memberships plus every group that (transitively) includes one."""
    user = _real_user(user)
    if user is None:
        return set()
    found = set(AccessGroupMember.objects.filter(member=user).values_list("group_id", flat=True))
    frontier = set(found)
    depth = 0
    while frontier and depth < MAX_GROUP_NESTING:
        parents = set(
            AccessGroupInclude.objects.filter(included_group_id__in=frontier).values_list("group_id", flat=True)
        )
        frontier = parents - found
        found |= frontier
        depth += 1
    return found


def group_includes_transitively(group_id, candidate_id):
    """True when ``group_id`` includes ``candidate_id`` directly or through other groups. Loop-safe."""
    seen = set()
    frontier = {group_id}
    depth = 0
    while frontier and depth < MAX_GROUP_NESTING:
        children = set(
            AccessGroupInclude.objects.filter(group_id__in=frontier).values_list("included_group_id", flat=True)
        )
        if candidate_id in children:
            return True
        frontier = children - seen
        seen |= frontier
        depth += 1
    return False


def _workspace_filter(workspace_id=None, slug=None, prefix=""):
    if workspace_id is not None:
        return {f"{prefix}workspace_id": workspace_id}
    if slug is not None:
        return {f"{prefix}workspace__slug": slug}
    return {}


def shared_project_levels(user, workspace_id=None, slug=None):
    """``{project_id: level}`` for every board ``user`` reaches through a group share.

    Scoped to one workspace when ``workspace_id`` or ``slug`` is given; otherwise every
    workspace where one of the user's groups holds a share. See the module docstring
    for the rule.
    """
    groups = effective_group_ids(user)
    if not groups:
        return {}
    scope = _workspace_filter(workspace_id, slug)
    shares = list(
        ProjectShare.objects.filter(group_id__in=groups, **scope).values_list("project_id", "group_id", "level")
    )
    if not shares:
        return {}
    exclusions = list(
        ProjectShareExclusion.objects.filter(group_id__in=groups, **scope).values_list("project_id", "group_id")
    )
    share_by_group = {}
    for project_id, group_id, level in shares:
        share_by_group.setdefault(group_id, {})[project_id] = level
    excluded_by_group = {}
    for project_id, group_id in exclusions:
        excluded_by_group.setdefault(group_id, set()).add(project_id)

    if not scope:
        workspace_ids = set(
            ProjectShare.objects.filter(group_id__in=groups).values_list("workspace_id", flat=True).distinct()
        )
        scope = {"workspace_id__in": workspace_ids}
    boards = {
        project_id: (parent_id, is_private)
        for project_id, parent_id, is_private in Project.objects.filter(**scope).values_list(
            "id", "parent_id", "is_private"
        )
    }

    def level_for(project_id, shared, excluded):
        # Walk up: nearest share or exclusion decides; a private board on the way ends it.
        current = project_id
        visited = set()
        for _ in range(MAX_BOARD_DEPTH + 1):
            if current is None or current in visited or current not in boards:
                return 0
            visited.add(current)
            parent_id, is_private = boards[current]
            if is_private or current in excluded:
                return 0
            if current in shared:
                return shared[current]
            current = parent_id
        return 0

    levels = {}
    for group_id, shared in share_by_group.items():
        excluded = excluded_by_group.get(group_id, set())
        for project_id in boards:
            level = level_for(project_id, shared, excluded)
            if level and level > levels.get(project_id, 0):
                levels[project_id] = level
    return levels


def shared_project_ids(user, workspace_id=None, slug=None):
    """List of board ids ``user`` reaches through a group share (any level)."""
    return list(shared_project_levels(user, workspace_id=workspace_id, slug=slug))


def project_share_level(user, project_id, workspace_id=None, slug=None):
    """0 when no group share reaches ``project_id`` for ``user``, else the best AccessLevel."""
    if not project_id:
        return 0
    if workspace_id is None and slug is None:
        workspace_id = Project.objects.filter(pk=project_id).values_list("workspace_id", flat=True).first()
        if workspace_id is None:
            return 0
    levels = shared_project_levels(user, workspace_id=workspace_id, slug=slug)
    # URL kwargs arrive as UUID objects or strings; the keys are UUIDs.
    try:
        key = uuid.UUID(str(project_id))
    except ValueError:
        return 0
    return levels.get(key, 0)


def role_for_level(level):
    """Project role a share level stands in for: editors act as members, everyone else as guests."""
    if not level:
        return None
    return ROLE_MEMBER if level >= AccessLevel.EDIT else ROLE_GUEST


def _member_project_ids(user):
    return ProjectMember.objects.filter(member_id=user.id, is_active=True, deleted_at__isnull=True).values("project_id")


def member_or_shared_projects_q(user, slug=None, workspace_id=None, prefix=""):
    """Q: the row's project is one ``user`` is an active member of, or a board a group share reaches.

    ``prefix`` is the path to the project: "" for a Project queryset, "project" for
    rows that belong to a project, "projects" for pages. Uses subqueries, not joins,
    so it never multiplies rows.
    """
    user = _real_user(user)
    field = f"{prefix}__id__in" if prefix else "id__in"
    if user is None:
        return Q(pk__in=[])
    return Q(**{field: _member_project_ids(user)}) | Q(
        **{field: shared_project_ids(user, workspace_id=workspace_id, slug=slug)}
    )


def shared_role_expr(user, slug=None, workspace_id=None):
    """Case expression on a Project queryset: the stand-in role a share grants, else NULL."""
    levels = shared_project_levels(user, workspace_id=workspace_id, slug=slug)
    editors = [pk for pk, level in levels.items() if level >= AccessLevel.EDIT]
    others = [pk for pk, level in levels.items() if level < AccessLevel.EDIT]
    return Case(
        When(id__in=editors, then=Value(ROLE_MEMBER)),
        When(id__in=others, then=Value(ROLE_GUEST)),
        default=Value(None),
        output_field=IntegerField(),
    )
