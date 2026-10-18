# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import os
from enum import Enum
from functools import wraps

from rest_framework import status
from rest_framework.response import Response

from plane.db.models import ProjectMember, Workspace, WorkspaceMember


class ROLE(Enum):
    ADMIN = 20
    MEMBER = 15
    GUEST = 5


def _is_workspace_owner(request, slug):
    """Keep the workspace owner from being locked out by a stale member row."""
    return Workspace.objects.filter(slug=slug, owner=request.user).exists()


def _garden_session_workspace_role(request, slug):
    """Return the server-verified Garden role attached at Firebase session exchange.

    The value is accepted only for the configured Garden-managed workspace and
    only when Garden auth is enabled. It is stored server-side in Plane's session
    after Firebase/canonical access verification, never accepted from a browser
    request body or header.
    """
    if os.environ.get("GARDEN_AUTH_ENABLED", "0") != "1":
        return None
    managed_slug = os.environ.get("GARDEN_WORKSPACE_SLUG", "the-garden").strip() or "the-garden"
    if slug != managed_slug:
        return None
    session = getattr(request, "session", None)
    if session is None or session.get("garden_work_workspace_slug") != slug:
        return None
    role = session.get("garden_work_workspace_role")
    return role if role in {ROLE.ADMIN.value, ROLE.MEMBER.value, ROLE.GUEST.value} else None


def has_workspace_role(request, slug, allowed_roles):
    """Single workspace-role check used by Garden and upstream project views."""
    allowed_role_values = [role.value if isinstance(role, ROLE) else role for role in allowed_roles]
    if WorkspaceMember.objects.filter(
        member=request.user,
        workspace__slug=slug,
        role__in=allowed_role_values,
        is_active=True,
    ).exists():
        return True
    if ROLE.ADMIN.value in allowed_role_values and _is_workspace_owner(request, slug):
        return True
    return _garden_session_workspace_role(request, slug) in allowed_role_values


def is_workspace_admin(request, slug):
    return has_workspace_role(request, slug, [ROLE.ADMIN])


def allow_permission(allowed_roles, level="PROJECT", creator=False, model=None):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(instance, request, *args, **kwargs):
            slug = kwargs["slug"]

            # Check for creator if required
            if creator and model:
                if not has_workspace_role(request, slug, [ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST]):
                    return Response(
                        {"error": "You don't have the required permissions."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                obj = model.objects.filter(id=kwargs["pk"], created_by=request.user).exists()
                if obj:
                    return view_func(instance, request, *args, **kwargs)

            # Convert allowed_roles to their values if they are enum members
            allowed_role_values = [role.value if isinstance(role, ROLE) else role for role in allowed_roles]

            # Check role permissions
            if level == "WORKSPACE":
                if has_workspace_role(request, slug, allowed_role_values):
                    return view_func(instance, request, *args, **kwargs)
            else:
                is_user_has_allowed_role = ProjectMember.objects.filter(
                    member=request.user,
                    workspace__slug=slug,
                    project_id=kwargs["project_id"],
                    role__in=allowed_role_values,
                    is_active=True,
                ).exists()

                if is_user_has_allowed_role:
                    return view_func(instance, request, *args, **kwargs)

                # A Garden global Work admin is authoritative for the managed
                # workspace even if the corresponding ProjectMember row has not
                # been materialized yet. Upstream behavior remains unchanged for
                # every non-Garden workspace.
                if is_workspace_admin(request, slug):
                    garden_role = _garden_session_workspace_role(request, slug)
                    if garden_role == ROLE.ADMIN.value:
                        return view_func(instance, request, *args, **kwargs)

                # Preserve upstream behavior: a normal workspace admin may act
                # on a project when they are at least an active project member.
                if (
                    ProjectMember.objects.filter(
                        member=request.user,
                        workspace__slug=slug,
                        project_id=kwargs["project_id"],
                        is_active=True,
                    ).exists()
                    and is_workspace_admin(request, slug)
                ):
                    return view_func(instance, request, *args, **kwargs)

            return Response(
                {"error": "You don't have the required permissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return _wrapped_view

    return decorator
