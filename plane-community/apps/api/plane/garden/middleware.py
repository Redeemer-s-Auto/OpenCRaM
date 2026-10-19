# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import json
import re

from django.http import JsonResponse

from plane.app.permissions.base import is_workspace_admin
from plane.db.models import Project, ProjectMember, WorkspaceMemberInvite
from plane.garden.services.project_policy import (
    garden_mode_enabled,
    garden_workspace_slug,
    harden_garden_workspace_projects,
    local_project_membership,
)


_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_ADMIN_ROLE = 20
_GARDEN_IDENTITY_FIELDS = {
    "first_name",
    "last_name",
    "display_name",
    "avatar",
    "avatar_url",
    "avatar_asset",
    "email",
}


class GardenAuthorizationMiddleware:
    """Protect Garden-managed Plane state from native authorization/identity drift.

    Firebase/Garden is the authority for staff identity and access. Plane remains
    the work-item state engine. Native Plane endpoints that create ACLs, change
    roles, alter Garden identity, or join/leave managed projects are constrained
    in Garden mode. Global Garden Work administrators may create/delete projects
    through the normal Work UI; project visibility is still forced SECRET and
    membership is still controlled by Garden access policy.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _deny(message: str):
        return JsonResponse({"error": message}, status=403)

    @staticmethod
    def _body_json(request):
        try:
            if not request.body:
                return {}
            return json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _replace_json_body(request, body: dict):
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request._body = encoded
        request._stream = None
        request.META["CONTENT_LENGTH"] = str(len(encoded))

    @staticmethod
    def _workspace_admin(request, slug: str) -> bool:
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return False
        return is_workspace_admin(request, slug)

    def _ensure_global_admin_project_membership(self, request, slug: str, path: str) -> None:
        """Bridge upstream endpoints that still inspect ProjectMember directly.

        Several Plane endpoints perform their own ProjectMember checks instead of
        using allow_permission. Garden global admins are entitled to every managed
        project, so materialize that authority when they first touch a project.
        This is server-derived from the verified Garden session, never from a
        request payload.
        """
        match = re.match(rf"^/api/workspaces/{re.escape(slug)}/projects/(?P<project_id>[^/]+)/", path)
        if not match or not self._workspace_admin(request, slug):
            return
        project = Project.objects.filter(id=match.group("project_id"), workspace__slug=slug, deleted_at__isnull=True).first()
        if project is None:
            return
        membership = ProjectMember.objects.filter(project=project, member=request.user, deleted_at__isnull=True).first()
        if membership is None:
            ProjectMember.objects.create(project=project, member=request.user, role=_ADMIN_ROLE, is_active=True)
            return
        changed = []
        if membership.role != _ADMIN_ROLE:
            membership.role = _ADMIN_ROLE
            changed.append("role")
        if not membership.is_active:
            membership.is_active = True
            changed.append("is_active")
        if changed:
            membership.save(update_fields=[*changed, "updated_at"])

    def __call__(self, request):
        if not garden_mode_enabled():
            return self.get_response(request)

        slug = garden_workspace_slug()
        workspace_prefix = f"/api/workspaces/{slug}/"
        project_collection = f"/api/workspaces/{slug}/projects/"
        user_project_invites = f"/api/users/me/workspaces/{slug}/projects/invitations/"
        user_workspace_invites = "/api/users/me/workspaces/invitations/"
        path = request.path
        method = request.method.upper()

        # Garden owns the identity behind every federated Work account. Work can
        # still update Work-only user preferences through this endpoint, but it
        # must not become a second source of truth for name/avatar/email.
        if path == "/api/users/me/" and method in {"PUT", "PATCH"}:
            body = self._body_json(request)
            attempted = sorted(_GARDEN_IDENTITY_FIELDS.intersection(body.keys()))
            if attempted:
                return self._deny(
                    "Garden manages staff identity. Update name, photo, or email from your Garden profile."
                )
        if path == "/api/users/me/" and method == "DELETE":
            return self._deny("Garden manages staff account activation and Work access")
        if path in {"/api/users/me/email/", "/api/users/me/email/generate-code/"} and method in _MUTATING_METHODS:
            return self._deny("Garden manages staff email and sign-in identity")

        garden_workspace_request = path.startswith(workspace_prefix) or path.startswith(
            f"/api/users/me/workspaces/{slug}/"
        )
        if garden_workspace_request:
            harden_garden_workspace_projects(slug)
            self._ensure_global_admin_project_membership(request, slug, path)

        # Creating a project is a normal Garden Work admin action. Members still
        # cannot self-create a project and promote themselves to Project Admin.
        if path == project_collection and method == "POST" and not self._workspace_admin(request, slug):
            return self._deny("Only Garden global Work administrators may create managed projects")

        project_root = re.fullmatch(
            rf"/api/workspaces/{re.escape(slug)}/projects/[^/]+/",
            path,
        )
        if project_root and method == "DELETE":
            if not self._workspace_admin(request, slug):
                return self._deny("Only Garden global Work administrators may delete managed projects")

        # Network is a security boundary, but the upstream settings form can
        # still submit PUBLIC. Normalize that field to SECRET instead of showing
        # staff a confusing 403, then harden again after the view returns.
        if project_root and method in {"PUT", "PATCH"}:
            body = self._body_json(request)
            if "network" in body and str(body.get("network")) not in {"0", "None"}:
                body["network"] = 0
                self._replace_json_body(request, body)

        project_governance = re.match(
            rf"^/api/workspaces/{re.escape(slug)}/projects/[^/]+/(?:members|invitations|join)(?:/.*)?$",
            path,
        )
        if project_governance and method in _MUTATING_METHODS:
            # In roles mode Firebase has no per-project mapping, so Work admins
            # add people to boards inside Work. Workspace membership (who may
            # sign in at all) still comes only from Firebase.
            if not (local_project_membership() and self._workspace_admin(request, slug)):
                return self._deny("Garden manages project membership from Firebase access policy")

        if path == user_project_invites and method == "POST":
            return self._deny("Garden manages project membership from Firebase access policy")

        workspace_governance = re.match(
            rf"^/api/workspaces/{re.escape(slug)}/(?:members|invitations)(?:/.*)?$",
            path,
        )
        if workspace_governance and method in _MUTATING_METHODS:
            return self._deny("Garden manages workspace membership from Firebase access policy")

        # This bulk invitation acceptance endpoint has no slug in its URL. Block
        # only when the submitted IDs include an invitation for the Garden workspace.
        if path == user_workspace_invites and method == "POST":
            invitation_ids = self._body_json(request).get("invitations", [])
            if isinstance(invitation_ids, list) and invitation_ids and WorkspaceMemberInvite.objects.filter(
                pk__in=invitation_ids,
                workspace__slug=slug,
            ).exists():
                return self._deny("Garden workspace membership is provisioned from Firebase")

        response = self.get_response(request)

        # Defense in depth against an upstream Plane endpoint reintroducing a
        # PUBLIC network value in a future update, including project creation.
        if garden_workspace_request:
            harden_garden_workspace_projects(slug)
        return response
