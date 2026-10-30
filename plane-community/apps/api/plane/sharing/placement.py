# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Where a board sits: a teamspace, a person's Private area, or neither ("workspace").

Used by the project serializers (app API and public v1 API). The rules:

- A board is in ONE place. Setting ``teamspace_id`` clears ``private_owner_id``
  and the seal; setting ``private_owner_id`` clears ``teamspace_id``.
- ``teamspace_id`` and ``private_owner_id`` are for workspace admins. ``is_sealed``
  is for workspace admins and the board's owner, and only on a Private-area board.
- ``private=true`` on create puts the new board in the caller's own Private area.
- A board inside another board follows its parent: setting ``parent_id`` copies the
  parent's place, and changing a board's place cascades to every board inside it
  (one transaction). Asking for a different place on a child is an error.
- Putting a board in someone's Private area leaves that person as its only active
  member (a project admin); every other membership is deactivated, not deleted.
"""

from django.db import transaction
from rest_framework import serializers

from plane.db.models import Project, ProjectMember, WorkspaceMember
from plane.sharing.models import Teamspace

PLACEMENT_FIELDS = ("teamspace_id", "private_owner_id", "is_sealed")
ADMIN_ROLE = 20
# Mirrors plane.utils.project_tree.MAX_PROJECT_TREE_DEPTH.
MAX_DEPTH = 12


def section_of(teamspace_id, private_owner_id):
    """Sidebar section a board belongs to: "private", "teamspace" or "workspace"."""
    if private_owner_id:
        return "private"
    if teamspace_id:
        return "teamspace"
    return "workspace"


def teamspace_detail_of(teamspace):
    """What the sidebar needs to draw a teamspace header, or None."""
    if teamspace is None:
        return None
    return {
        "id": str(teamspace.id),
        "name": teamspace.name,
        "slug": teamspace.slug,
        "position": teamspace.position,
        "is_default": teamspace.is_default,
    }


def placement_of(project):
    if project is None:
        return {"teamspace_id": None, "private_owner_id": None, "is_sealed": False}
    return {
        "teamspace_id": project.teamspace_id,
        "private_owner_id": project.private_owner_id,
        "is_sealed": project.is_sealed,
    }


def _is_workspace_admin(user, workspace_id):
    return WorkspaceMember.objects.filter(
        workspace_id=workspace_id, member=user, role=ADMIN_ROLE, is_active=True, deleted_at__isnull=True
    ).exists()


def _same_place(a, b):
    return a["teamspace_id"] == b["teamspace_id"] and a["private_owner_id"] == b["private_owner_id"]


def clean_placement(data, instance, workspace_id, user):
    """Pop the placement keys out of validated ``data``; return the place to apply, or None for no change.

    ``instance`` is the board being edited, or None on create. ``data["parent_id"]``,
    when present, has already passed ``clean_parent_id``. Raises ``ValidationError``.
    """
    requested = {key: data.pop(key) for key in PLACEMENT_FIELDS if key in data}
    private = bool(data.pop("private", False)) and instance is None
    if user is None:
        if requested or private:
            raise serializers.ValidationError({"teamspace_id": "Sign in to place a board."})
        return None

    current = placement_of(instance)
    target = dict(current)
    is_admin = _is_workspace_admin(user, workspace_id)

    if private:
        target = {"teamspace_id": None, "private_owner_id": user.id, "is_sealed": False}

    if "teamspace_id" in requested or "private_owner_id" in requested:
        if not is_admin:
            field = "teamspace_id" if "teamspace_id" in requested else "private_owner_id"
            raise serializers.ValidationError({field: "Only a workspace admin can move a board."})
    if "is_sealed" in requested:
        owner_here = instance is not None and instance.private_owner_id == user.id
        if not (is_admin or owner_here):
            raise serializers.ValidationError({"is_sealed": "Only the board's owner or a workspace admin can seal it."})

    teamspace_id = requested.get("teamspace_id")
    if teamspace_id:
        if not Teamspace.objects.filter(pk=teamspace_id, workspace_id=workspace_id).exists():
            raise serializers.ValidationError({"teamspace_id": "Teamspace not found."})
        target = {"teamspace_id": teamspace_id, "private_owner_id": None, "is_sealed": False}
    elif "teamspace_id" in requested:
        target["teamspace_id"] = None

    owner_id = requested.get("private_owner_id")
    if owner_id:
        if not WorkspaceMember.objects.filter(
            workspace_id=workspace_id, member_id=owner_id, is_active=True, deleted_at__isnull=True
        ).exists():
            raise serializers.ValidationError({"private_owner_id": "That person is not in this workspace."})
        target = {"teamspace_id": None, "private_owner_id": owner_id, "is_sealed": target["is_sealed"]}
    elif "private_owner_id" in requested:
        target["private_owner_id"] = None
        target["is_sealed"] = False

    if "is_sealed" in requested:
        target["is_sealed"] = bool(requested["is_sealed"])
    if target["is_sealed"] and not target["private_owner_id"]:
        raise serializers.ValidationError({"is_sealed": "Only a board in someone's Private area can be sealed."})

    # A board inside another board follows that board.
    parent_id = data["parent_id"] if "parent_id" in data else (instance.parent_id if instance is not None else None)
    if parent_id:
        parent = Project.objects.filter(pk=parent_id).first()
        if parent is not None:
            above = placement_of(parent)
            asked = bool(requested) or private
            if asked and not _same_place(target, above):
                raise serializers.ValidationError(
                    {"parent_id": "A board inside another board follows that board. Set the place on the top board."}
                )
            if asked and target["is_sealed"] != above["is_sealed"]:
                raise serializers.ValidationError({"is_sealed": "Seal the top board; the boards inside it follow."})
            target = above

    if instance is not None and target == current:
        return None
    return target


def _subtree_ids(project_id):
    ids = [project_id]
    frontier = [project_id]
    for _ in range(MAX_DEPTH):
        frontier = list(Project.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
        if not frontier:
            break
        ids.extend(frontier)
    return ids


def apply_placement(project, placement, actor=None):
    """Write ``placement`` to ``project`` and every board inside it, in one transaction."""
    with transaction.atomic():
        ids = _subtree_ids(project.id)
        Project.objects.filter(id__in=ids).update(**placement)
        owner_id = placement["private_owner_id"]
        if owner_id:
            # Only the owner is a member of a Private-area board. Deactivated, not deleted.
            ProjectMember.objects.filter(project_id__in=ids, is_active=True).exclude(member_id=owner_id).update(
                is_active=False
            )
            for project_id in ids:
                membership = ProjectMember.objects.filter(project_id=project_id, member_id=owner_id).first()
                if membership is None:
                    ProjectMember.objects.create(
                        project_id=project_id,
                        member_id=owner_id,
                        workspace_id=project.workspace_id,
                        role=ADMIN_ROLE,
                        created_by=actor,
                    )
                elif not membership.is_active or membership.role != ADMIN_ROLE:
                    membership.is_active = True
                    membership.role = ADMIN_ROLE
                    membership.save(update_fields=["is_active", "role", "updated_at"])
    project.refresh_from_db(fields=["teamspace", "private_owner", "is_sealed"])
