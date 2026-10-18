# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from firebase_admin import firestore

from plane.db.models import Project, ProjectMember, ProjectNetwork, Workspace, WorkspaceMember
from plane.garden.models import GardenExternalIdentity
from plane.garden.services.firebase_identity import GardenIdentityError, _firebase_app
from plane.garden.services.project_policy import harden_garden_workspace_projects


VALID_WORKSPACE_ROLES = {15, 20}
VALID_PROJECT_ROLES = {15, 20}


def load_work_projection(firebase_uid: str) -> dict[str, Any] | None:
    snapshot = (
        firestore.client(app=_firebase_app())
        .collection("workAccessProjections")
        .document(firebase_uid)
        .get()
    )
    if not snapshot.exists:
        return None
    data = snapshot.to_dict()
    return data if isinstance(data, dict) else None


def _integer(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) and value >= 0 else default


def projection_allows_work(projection: dict[str, Any] | None) -> bool:
    if not projection:
        return False
    workspace_role = projection.get("workspaceRole")
    if workspace_role in VALID_WORKSPACE_ROLES:
        return True
    projects = projection.get("projects")
    return isinstance(projects, list) and any(isinstance(project, dict) and project.get("readable") is True for project in projects)


def projection_is_global_admin(projection: dict[str, Any] | None) -> bool:
    return bool(projection and projection.get("workspaceRole") == 20)


@transaction.atomic
def apply_work_projection(firebase_uid: str, user, workspace: Workspace, projection: dict[str, Any] | None = None):
    projection = projection if projection is not None else load_work_projection(firebase_uid)
    if projection is None:
        raise GardenIdentityError("Garden Work access projection is missing")

    harden_garden_workspace_projects(workspace)
    workspace_role = projection.get("workspaceRole")
    if workspace_role not in VALID_WORKSPACE_ROLES and workspace_role is not None:
        raise GardenIdentityError("Garden Work projection has an invalid workspace role")

    membership = WorkspaceMember.objects.filter(
        workspace=workspace,
        member=user,
        deleted_at__isnull=True,
    ).first()
    if workspace_role is None:
        if membership and membership.is_active:
            membership.is_active = False
            membership.save(update_fields=["is_active", "updated_at"])
    elif membership is None:
        membership = WorkspaceMember.objects.create(workspace=workspace, member=user, role=workspace_role, is_active=True)
    else:
        changed_fields = []
        if membership.role != workspace_role:
            membership.role = workspace_role
            changed_fields.append("role")
        if not membership.is_active:
            membership.is_active = True
            changed_fields.append("is_active")
        if changed_fields:
            membership.save(update_fields=[*changed_fields, "updated_at"])

    managed_ids_raw = projection.get("managedProjectIds")
    managed_project_ids = {str(value) for value in managed_ids_raw if isinstance(value, str)} if isinstance(managed_ids_raw, list) else set()
    projects_raw = projection.get("projects")
    desired_roles: dict[str, int] = {}
    if isinstance(projects_raw, list):
        for entry in projects_raw:
            if not isinstance(entry, dict):
                continue
            project_id = entry.get("planeProjectId")
            plane_role = entry.get("planeRole")
            if isinstance(project_id, str) and plane_role in VALID_PROJECT_ROLES and project_id in managed_project_ids:
                desired_roles[project_id] = int(plane_role)

    existing_projects = {
        str(project.id): project
        for project in Project.objects.filter(
            workspace=workspace,
            id__in=list(managed_project_ids),
            deleted_at__isnull=True,
        )
    }
    for project_id, role in desired_roles.items():
        project = existing_projects.get(project_id)
        if project is None:
            raise GardenIdentityError("Garden Work projection references an unknown managed project")
        if project.network != ProjectNetwork.SECRET.value:
            project.network = ProjectNetwork.SECRET.value
            project.save(update_fields=["network", "updated_at"])
        project_member = ProjectMember.objects.filter(project=project, member=user, deleted_at__isnull=True).first()
        if project_member is None:
            ProjectMember.objects.create(project=project, member=user, role=role, is_active=True)
        else:
            changed_fields = []
            if project_member.role != role:
                project_member.role = role
                changed_fields.append("role")
            if not project_member.is_active:
                project_member.is_active = True
                changed_fields.append("is_active")
            if changed_fields:
                project_member.save(update_fields=[*changed_fields, "updated_at"])

    stale_memberships = ProjectMember.objects.filter(
        workspace=workspace,
        member=user,
        project_id__in=list(managed_project_ids),
        is_active=True,
        deleted_at__isnull=True,
    ).exclude(project_id__in=list(desired_roles.keys()))
    stale_count = stale_memberships.update(is_active=False, updated_at=timezone.now())

    identity = GardenExternalIdentity.objects.filter(provider="firebase", external_id=firebase_uid, user=user).first()
    if identity:
        identity.access_version = _integer(projection.get("accessVersion"))
        projection_hash = projection.get("projectionHash")
        identity.projection_hash = projection_hash if isinstance(projection_hash, str) else ""
        identity.projection_synced_at = timezone.now()
        identity.save(update_fields=["access_version", "projection_hash", "projection_synced_at", "updated_at"])

    return {
        "workspaceRole": workspace_role,
        "projectMembershipCount": len(desired_roles),
        "deactivatedProjectMembershipCount": stale_count,
        "accessVersion": _integer(projection.get("accessVersion")),
        "projectionHash": projection.get("projectionHash") if isinstance(projection.get("projectionHash"), str) else "",
    }
