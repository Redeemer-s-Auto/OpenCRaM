# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Private projects: only active members can see them. Workspace admins included.

Plane's "secret" network hides a project from normal members, but workspace
admins still see its name and can join it. A project with ``is_private=True``
is stricter: anyone who is not an active member gets nothing back - not the
name, not the cards, not a way to join.

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
    return ProjectMember.objects.filter(member_id=user.id, is_active=True).values("project_id")


def visible_projects_q(user, prefix=""):
    """Q that keeps rows whose project is not private, or where ``user`` is an active member.

    ``prefix`` is the path to the project: "" for a Project queryset,
    "project__" for a queryset of things that belong to a project.
    """
    if user is None or not user.is_authenticated:
        return Q(**{f"{prefix}is_private": False})
    id_field = f"{prefix}id" if prefix else "id"
    return Q(**{f"{prefix}is_private": False}) | Q(**{f"{id_field}__in": _member_project_ids(user)})


def is_hidden_from(user, project_id):
    """True when the project is private and ``user`` is not an active member."""
    if not project_id:
        return False
    return Project.objects.filter(pk=project_id, is_private=True).exclude(pk__in=_member_project_ids(user)).exists()


def check_private_project_access(view, request):
    """Raise 404 when the URL names a private project the user is not a member of.

    404 (not 403) so the response does not even confirm the project exists.
    """
    if not request.user or not request.user.is_authenticated:
        return
    kwargs = getattr(view, "kwargs", {}) or {}
    try:
        project_id = view.project_id
    except Exception:
        project_id = kwargs.get("project_id")
    if project_id and is_hidden_from(request.user, project_id):
        raise NotFound("The requested resource does not exist.")

    identifier = kwargs.get("project_identifier")
    slug = kwargs.get("slug")
    if identifier and slug:
        hidden = (
            Project.objects.filter(workspace__slug=slug, identifier=identifier, is_private=True)
            .exclude(pk__in=_member_project_ids(request.user))
            .exists()
        )
        if hidden:
            raise NotFound("The requested resource does not exist.")
