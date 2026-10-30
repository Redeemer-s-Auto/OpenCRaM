# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Boards shared with groups, teamspaces and Private areas: the one resolver every read path uses.

Nothing is copied per person or per card. Access is computed at read time from
the share rows and from where a board sits, so a person added to a group sees
everything shared with that group (and every board in that group's teamspace) at
once, and loses it the moment they are removed.

Groups inside groups
    ``AccessGroupInclude(group=G, included_group=H)`` means G includes H: H's
    members inherit everything shared with G, and with everything that includes
    G, and so on up. ``effective_group_ids`` walks that chain with a visited set
    and a depth cap, so a bad row can never loop it.

Inheritance of group shares (the rule, in three lines)
    1. A share on a board reaches the board and every board inside it
       (``Project.parent`` chain), at the share's level.
    2. Walking up from a board, the NEAREST board that carries either a share or
       an exclusion for the group decides: share = that level, exclusion = none.
    3. A private board (``is_private``) or a board in someone's Private area
       (``private_owner``) is never reached through a group share, directly or
       inherited, and nothing flows through it to the boards inside.

Where a board sits (``placement_levels``)
    - Teamspace T: everyone who belongs to T acts as an editor (member) on it.
      Belonging = every active workspace member when T is the default teamspace,
      else acting as T's group. Not through ``is_private``.
    - Private area of U: U acts as a project admin. Members of the workspace group
      "Private Readers" may view it, unless the board is sealed. Nobody else sees
      it: not other members, not workspace admins.
    A board with ``teamspace`` or ``private_owner`` set is closed: the only ways in
    are this resolver and (teamspace boards only) an active project membership.

Being an active project member is unchanged and always wins over a share, except
on a board in someone's Private area, where only the owner counts.
"""

import uuid

from django.db.models import Case, IntegerField, Q, Value, When

from plane.db.models import Project, ProjectMember, WorkspaceMember
from plane.sharing.models import (
    PRIVATE_READERS_GROUP_NAME,
    AccessGroup,
    AccessGroupInclude,
    AccessGroupMember,
    AccessLevel,
    ProjectShare,
    ProjectShareExclusion,
    Teamspace,
)

# Levels of group nesting the resolver will follow. Writes reject loops; this is the belt to that brace.
MAX_GROUP_NESTING = 20
# Project.parent levels the resolver will walk. Mirrors plane.utils.project_tree.MAX_PROJECT_TREE_DEPTH.
MAX_BOARD_DEPTH = 12

ROLE_ADMIN, ROLE_MEMBER, ROLE_GUEST = 20, 15, 5

# Above AccessLevel.EDIT: the owner of a board in their Private area acts as its project admin.
LEVEL_OWNER = 20


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


def _member_workspace_ids(user):
    return WorkspaceMember.objects.filter(member=user, is_active=True, deleted_at__isnull=True).values("workspace_id")


def _user_teamspace_ids(user, groups, scope):
    # Chained filters: ``scope`` may itself be a workspace_id__in lookup.
    rows = Teamspace.objects.filter(workspace_id__in=_member_workspace_ids(user)).filter(**scope)
    return set(rows.filter(Q(is_default=True) | Q(group_id__in=groups)).values_list("id", flat=True))


def user_teamspace_ids(user, workspace_id=None, slug=None):
    """Ids of the teamspaces ``user`` belongs to: default ones in workspaces they are active in, plus those whose group they act as."""
    user = _real_user(user)
    if user is None:
        return set()
    return _user_teamspace_ids(user, effective_group_ids(user), _workspace_filter(workspace_id, slug))


def placement_levels(user, workspace_id=None, slug=None):
    """``{project_id: level}`` for every board ``user`` reaches by where the board sits.

    Teamspace the user belongs to: EDIT. Their own Private board: LEVEL_OWNER.
    Someone else's unsealed Private board, when the user acts as the workspace's
    "Private Readers" group: VIEW. Workspace admins get nothing here that
    membership or a group does not give them.
    """
    user = _real_user(user)
    if user is None:
        return {}
    scope = _workspace_filter(workspace_id, slug)
    if not scope:
        scope = {"workspace_id__in": _member_workspace_ids(user)}
    groups = effective_group_ids(user)
    levels = {}

    teamspaces = _user_teamspace_ids(user, groups, scope)
    if teamspaces:
        in_teamspace = Project.objects.filter(teamspace_id__in=teamspaces, is_private=False, **scope)
        for project_id in in_teamspace.values_list("id", flat=True):
            levels[project_id] = AccessLevel.EDIT

    for project_id in Project.objects.filter(private_owner=user, **scope).values_list("id", flat=True):
        levels[project_id] = LEVEL_OWNER

    if groups:
        reader_in = AccessGroup.objects.filter(name=PRIVATE_READERS_GROUP_NAME, id__in=groups, **scope).values(
            "workspace_id"
        )
        readable = (
            Project.objects.filter(workspace_id__in=reader_in, private_owner__isnull=False, is_sealed=False)
            .filter(**scope)
            .exclude(private_owner=user)
            .values_list("id", flat=True)
        )
        for project_id in readable:
            levels.setdefault(project_id, AccessLevel.VIEW)
    return levels


def _group_share_levels(user, groups, workspace_id=None, slug=None):
    """``{project_id: level}`` from ProjectShare rows, inherited down the board tree. See the module docstring."""
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
    # A board is a wall when it is private or sits in someone's Private area.
    boards = {
        project_id: (parent_id, is_private or private_owner_id is not None)
        for project_id, parent_id, is_private, private_owner_id in Project.objects.filter(**scope).values_list(
            "id", "parent_id", "is_private", "private_owner_id"
        )
    }

    def level_for(project_id, shared, excluded):
        # Walk up: nearest share or exclusion decides; a wall on the way ends it.
        current = project_id
        visited = set()
        for _ in range(MAX_BOARD_DEPTH + 1):
            if current is None or current in visited or current not in boards:
                return 0
            visited.add(current)
            parent_id, wall = boards[current]
            if wall or current in excluded:
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


def shared_project_levels(user, workspace_id=None, slug=None):
    """``{project_id: level}`` for every board ``user`` reaches through a group share or by where it sits.

    Scoped to one workspace when ``workspace_id`` or ``slug`` is given; otherwise every
    workspace the user is active in or where one of their groups holds a share. The best
    level wins. See the module docstring for the rule.
    """
    user = _real_user(user)
    if user is None:
        return {}
    levels = _group_share_levels(user, effective_group_ids(user), workspace_id=workspace_id, slug=slug)
    for project_id, level in placement_levels(user, workspace_id=workspace_id, slug=slug).items():
        if level > levels.get(project_id, 0):
            levels[project_id] = level
    return levels


def shared_project_ids(user, workspace_id=None, slug=None):
    """List of board ids ``user`` reaches through a group share or by where the board sits (any level)."""
    return list(shared_project_levels(user, workspace_id=workspace_id, slug=slug))


def project_share_level(user, project_id, workspace_id=None, slug=None):
    """0 when nothing reaches ``project_id`` for ``user``, else the best level (AccessLevel or LEVEL_OWNER)."""
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
    """Project role a level stands in for: owners act as admins, editors as members, everyone else as guests."""
    if not level:
        return None
    if level >= LEVEL_OWNER:
        return ROLE_ADMIN
    return ROLE_MEMBER if level >= AccessLevel.EDIT else ROLE_GUEST


def _member_project_ids(user):
    return ProjectMember.objects.filter(member_id=user.id, is_active=True, deleted_at__isnull=True).values("project_id")


def member_or_shared_projects_q(user, slug=None, workspace_id=None, prefix=""):
    """Q: the row's project is one ``user`` is an active member of, or a board the resolver reaches.

    ``prefix`` is the path to the project: "" for a Project queryset, "project" for
    rows that belong to a project, "projects" for pages. Uses subqueries, not joins,
    so it never multiplies rows. Membership does not count on a board in someone's
    Private area: only the resolver opens those.
    """
    user = _real_user(user)
    field = f"{prefix}__id__in" if prefix else "id__in"
    not_private_area = f"{prefix}__private_owner__isnull" if prefix else "private_owner__isnull"
    if user is None:
        return Q(pk__in=[])
    return Q(**{field: _member_project_ids(user), not_private_area: True}) | Q(
        **{field: shared_project_ids(user, workspace_id=workspace_id, slug=slug)}
    )


def shared_role_expr(user, slug=None, workspace_id=None):
    """Case expression on a Project queryset: the stand-in role the resolver grants, else NULL."""
    levels = shared_project_levels(user, workspace_id=workspace_id, slug=slug)
    owners = [pk for pk, level in levels.items() if level >= LEVEL_OWNER]
    editors = [pk for pk, level in levels.items() if AccessLevel.EDIT <= level < LEVEL_OWNER]
    others = [pk for pk, level in levels.items() if level < AccessLevel.EDIT]
    return Case(
        When(id__in=owners, then=Value(ROLE_ADMIN)),
        When(id__in=editors, then=Value(ROLE_MEMBER)),
        When(id__in=others, then=Value(ROLE_GUEST)),
        default=Value(None),
        output_field=IntegerField(),
    )
