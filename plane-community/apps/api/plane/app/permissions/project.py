# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third Party imports
from rest_framework.permissions import SAFE_METHODS, BasePermission

# Module import
from plane.db.models import ProjectMember, WorkspaceMember
from plane.db.models.project import ROLE


def _shared_role(request, view, allowed_roles):
    """Stand-in role from a group share on the board the view names, when it is one of ``allowed_roles``."""
    from plane.sharing.guard import shared_project_role

    role = shared_project_role(
        request,
        view.workspace_slug,
        project_id=getattr(view, "project_id", None),
        project_identifier=getattr(view, "project_identifier", None),
    )
    return role is not None and role in allowed_roles


ANY_ROLE = [ROLE.ADMIN.value, ROLE.MEMBER.value, ROLE.GUEST.value]
WRITE_ROLES = [ROLE.ADMIN.value, ROLE.MEMBER.value]


class ProjectBasePermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False

        ## Safe Methods -> Handle the filtering logic in queryset
        if request.method in SAFE_METHODS:
            return WorkspaceMember.objects.filter(
                workspace__slug=view.workspace_slug, member=request.user, is_active=True
            ).exists()

        ## Only workspace owners or admins can create the projects
        if request.method == "POST":
            return WorkspaceMember.objects.filter(
                workspace__slug=view.workspace_slug,
                member=request.user,
                role__in=[ROLE.ADMIN.value, ROLE.MEMBER.value],
                is_active=True,
            ).exists()

        project_member_qs = ProjectMember.objects.filter(
            workspace__slug=view.workspace_slug,
            member=request.user,
            project_id=view.project_id,
            is_active=True,
        )

        ## Only project admins or workspace admin who is part of the project can access

        if project_member_qs.filter(role=ROLE.ADMIN.value).exists():
            return True
        else:
            return (
                project_member_qs.exists()
                and WorkspaceMember.objects.filter(
                    member=request.user,
                    workspace__slug=view.workspace_slug,
                    role=ROLE.ADMIN.value,
                    is_active=True,
                ).exists()
            )


class ProjectMemberPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False

        ## Safe Methods -> Handle the filtering logic in queryset
        if request.method in SAFE_METHODS:
            return (
                ProjectMember.objects.filter(
                    workspace__slug=view.workspace_slug,
                    member=request.user,
                    project_id=view.project_id,
                    is_active=True,
                ).exists()
                or _shared_role(request, view, ANY_ROLE)
            )
        ## Only workspace owners or admins can create the projects
        if request.method == "POST":
            return WorkspaceMember.objects.filter(
                workspace__slug=view.workspace_slug,
                member=request.user,
                role__in=[ROLE.ADMIN.value, ROLE.MEMBER.value],
                is_active=True,
            ).exists()

        ## Only Project Admins can update project attributes
        return (
            ProjectMember.objects.filter(
                workspace__slug=view.workspace_slug,
                member=request.user,
                role__in=[ROLE.ADMIN.value, ROLE.MEMBER.value],
                project_id=view.project_id,
                is_active=True,
            ).exists()
            or _shared_role(request, view, WRITE_ROLES)
        )


class ProjectEntityPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False

        # Handle requests based on project__identifier
        if hasattr(view, "project_identifier") and view.project_identifier:
            if request.method in SAFE_METHODS:
                return (
                    ProjectMember.objects.filter(
                        workspace__slug=view.workspace_slug,
                        member=request.user,
                        project__identifier=view.project_identifier,
                        is_active=True,
                    ).exists()
                    or _shared_role(request, view, ANY_ROLE)
                )

        ## Safe Methods -> Handle the filtering logic in queryset
        if request.method in SAFE_METHODS:
            return (
                ProjectMember.objects.filter(
                    workspace__slug=view.workspace_slug,
                    member=request.user,
                    project_id=view.project_id,
                    is_active=True,
                ).exists()
                or _shared_role(request, view, ANY_ROLE)
            )

        ## Only project members or admins can create and edit the project attributes
        return (
            ProjectMember.objects.filter(
                workspace__slug=view.workspace_slug,
                member=request.user,
                role__in=[ROLE.ADMIN.value, ROLE.MEMBER.value],
                project_id=view.project_id,
                is_active=True,
            ).exists()
            or _shared_role(request, view, WRITE_ROLES)
        )


class ProjectAdminPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False

        return ProjectMember.objects.filter(
            workspace__slug=view.workspace_slug,
            member=request.user,
            role=ROLE.ADMIN.value,
            project_id=view.project_id,
            is_active=True,
        ).exists()


class ProjectLitePermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False

        return (
            ProjectMember.objects.filter(
                workspace__slug=view.workspace_slug,
                member=request.user,
                project_id=view.project_id,
                is_active=True,
            ).exists()
            or _shared_role(request, view, ANY_ROLE)
        )
