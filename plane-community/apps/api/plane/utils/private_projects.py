# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Closed boards: private projects, teamspace boards and Private-area boards.

Plane's "secret" network hides a project from normal members, but workspace
admins still see its name and can join it. This fork has three stricter kinds
of board; anyone who cannot open one gets nothing back - not the name, not the
cards, not a way to join:

- ``is_private``: only active members.
- ``teamspace``: people who belong to that teamspace, plus active members and
  group shares (``plane.sharing.board_access``).
- ``private_owner``: that person; "Private Readers" read-only unless sealed.
  Membership does not count here, and neither does being a workspace admin.

Enforcement points:
- ``check_private_project_access`` runs in every API view's ``initial()`` for
  any URL that names a project (app API and public API).
- ``visible_projects_q`` filters project lists, search, and other lists that
  span projects.
"""

# Third party imports
from rest_framework.exceptions import NotFound

# Django imports
from django.db.models import Q

# Module imports
from plane.db.models import Project, ProjectMember


def _member_project_ids(user):
    # objects already skips soft-deleted rows; the explicit filter keeps that true if the manager changes.
    return ProjectMember.objects.filter(member_id=user.id, is_active=True, deleted_at__isnull=True).values(
        "project_id"
    )


def closed_projects_q(prefix=""):
    """Q that keeps rows whose project is closed (private, in a teamspace, or in someone's Private area)."""
    return (
        Q(**{f"{prefix}is_private": True})
        | Q(**{f"{prefix}teamspace__isnull": False})
        | Q(**{f"{prefix}private_owner__isnull": False})
    )


def visible_projects_q(user, prefix="", workspace_id=None, slug=None):
    """Q that keeps rows whose project is open, or closed but reachable by ``user``.

    Open = not private, not in a teamspace, not in a Private area. Reachable = an
    active membership (never on a Private-area board) or the resolver in
    ``plane.sharing.board_access`` (teamspace, own Private area, Private Readers,
    group share). ``prefix`` is the path to the project: "" for a Project queryset,
    "project__" for a queryset of things that belong to a project.
    """
    open_q = Q(
        **{f"{prefix}is_private": False, f"{prefix}teamspace__isnull": True, f"{prefix}private_owner__isnull": True}
    )
    if user is None or not user.is_authenticated:
        return open_q
    from plane.sharing.board_access import shared_project_ids

    id_field = f"{prefix}id" if prefix else "id"
    member_q = Q(**{f"{id_field}__in": _member_project_ids(user), f"{prefix}private_owner__isnull": True})
    reached_q = Q(**{f"{id_field}__in": shared_project_ids(user, workspace_id=workspace_id, slug=slug)})
    return open_q | member_q | reached_q


def is_hidden_from(user, project_id):
    """True when the project is closed and ``user`` cannot open it."""
    if not project_id:
        return False
    closed = Project.objects.filter(pk=project_id).filter(closed_projects_q())
    if not closed.exists():
        return False
    return not closed.filter(visible_projects_q(user)).exists()


def check_private_project_access(view, request):
    """Raise 404 when the URL names a closed project the user cannot open.

    404 (not 403) so the response does not even confirm the project exists.
    """
    if not request.user or not request.user.is_authenticated:
        return
    kwargs = getattr(view, "kwargs", {}) or {}
    try:
        project_id = view.project_id
    except Exception:
        project_id = kwargs.get("project_id")
    # Project endpoints name the board as ``pk``.
    if not project_id and kwargs.get("pk") and getattr(view, "model", None) is Project:
        project_id = kwargs.get("pk")
    if project_id and is_hidden_from(request.user, project_id):
        raise NotFound("The requested resource does not exist.")

    identifier = kwargs.get("project_identifier")
    slug = kwargs.get("slug")
    if identifier and slug:
        named = (
            Project.objects.filter(workspace__slug=slug, identifier=identifier).values_list("id", flat=True).first()
        )
        if named and is_hidden_from(request.user, named):
            raise NotFound("The requested resource does not exist.")


def check_published_anchor(view):
    """Public boards (space app): a closed project is never public.

    Raise 404 for any ``anchor`` URL whose board belongs to a private, teamspace or
    Private-area project, so a board published before the project was closed stops answering.
    """
    anchor = (getattr(view, "kwargs", {}) or {}).get("anchor")
    if not anchor:
        return
    from plane.db.models import DeployBoard

    board = DeployBoard.objects.filter(anchor=anchor).values("project_id", "entity_name", "entity_identifier").first()
    if not board:
        return
    project_id = board["project_id"] or (board["entity_identifier"] if board["entity_name"] == "project" else None)
    if project_id and Project.objects.filter(pk=project_id).filter(closed_projects_q()).exists():
        raise NotFound("The requested resource does not exist.")
