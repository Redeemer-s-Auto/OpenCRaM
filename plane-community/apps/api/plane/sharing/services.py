# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Read and replace an item's sharing settings."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from plane.db.models import Project, User, WorkspaceMember
from plane.sharing.models import AccessGroup, AccessLevel, ItemRestriction, ItemShare, ShareTarget

ADMIN_ROLE = 20


def is_workspace_admin(user, workspace):
    if workspace.owner_id == user.id:
        return True
    return WorkspaceMember.objects.filter(
        workspace=workspace, member=user, role=ADMIN_ROLE, is_active=True, deleted_at__isnull=True
    ).exists()


def can_manage_sharing(user, workspace, owner_id):
    """Only the item's creator (page owner) and workspace admins change sharing."""
    return owner_id == user.id or is_workspace_admin(user, workspace)


def _item_filter(issue=None, page=None):
    return {"issue": issue} if issue is not None else {"page": page}


def _describe_share(share):
    if share.target_type == ShareTarget.MEMBER:
        member = share.member
        target_id, name = member.id, (member.display_name or member.first_name or member.email)
        avatar = member.avatar_url if hasattr(member, "avatar_url") else None
    elif share.target_type == ShareTarget.PROJECT:
        target_id, name, avatar = share.project_id, share.project.name, None
    elif share.target_type == ShareTarget.GROUP:
        target_id, name, avatar = share.group_id, share.group.name, None
    else:
        target_id, name, avatar = None, "Everybody", None
    return {
        "target_type": share.target_type,
        "target_id": str(target_id) if target_id else None,
        "name": name,
        "avatar": avatar,
        "level": share.level,
    }


def read_sharing(issue=None, page=None):
    restricted = ItemRestriction.objects.filter(**_item_filter(issue, page)).exists()
    shares = (
        ItemShare.objects.filter(**_item_filter(issue, page))
        .select_related("member", "project", "group")
        .order_by("target_type", "created_at")
    )
    return {"restricted": restricted, "shares": [_describe_share(share) for share in shares]}


def _clean_shares(workspace, raw_shares):
    if not isinstance(raw_shares, list):
        raise ValidationError({"shares": "Must be a list."})
    cleaned, seen = [], set()
    for raw in raw_shares:
        if not isinstance(raw, dict):
            raise ValidationError({"shares": "Each share must be an object."})
        target_type = raw.get("target_type")
        target_id = raw.get("target_id")
        level = raw.get("level", AccessLevel.VIEW)
        if target_type not in ShareTarget.values:
            raise ValidationError({"shares": f"Unknown target_type {target_type!r}."})
        if level not in AccessLevel.values:
            raise ValidationError({"shares": f"Unknown level {level!r}."})
        fields = {}
        if target_type == ShareTarget.MEMBER:
            member = User.objects.filter(
                id=target_id,
                member_workspace__workspace=workspace,
                member_workspace__is_active=True,
                member_workspace__deleted_at__isnull=True,
            ).first()
            if member is None:
                raise ValidationError({"shares": "Person is not in this workspace."})
            fields["member"] = member
        elif target_type == ShareTarget.PROJECT:
            project = Project.objects.filter(id=target_id, workspace=workspace, deleted_at__isnull=True).first()
            if project is None:
                raise ValidationError({"shares": "Department is not in this workspace."})
            fields["project"] = project
        elif target_type == ShareTarget.GROUP:
            group = AccessGroup.objects.filter(id=target_id, workspace=workspace).first()
            if group is None:
                raise ValidationError({"shares": "Group is not in this workspace."})
            fields["group"] = group
        key = (target_type, str(target_id) if target_type != ShareTarget.WORKSPACE else None)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append((target_type, level, fields))
    return cleaned


@transaction.atomic
def write_sharing(workspace, data, issue=None, page=None):
    """Replace the item's mode and share list with ``data``."""
    restricted = data.get("restricted")
    if not isinstance(restricted, bool):
        raise ValidationError({"restricted": "Must be true or false."})
    item = _item_filter(issue, page)
    shares = _clean_shares(workspace, data.get("shares", [])) if restricted else []
    ItemShare.objects.filter(**item).delete()
    if not restricted:
        ItemRestriction.objects.filter(**item).delete()
        return read_sharing(issue, page)
    ItemRestriction.objects.get_or_create(workspace=workspace, **item)
    ItemShare.objects.bulk_create(
        ItemShare(workspace=workspace, target_type=target_type, level=level, **item, **fields)
        for target_type, level, fields in shares
    )
    return read_sharing(issue, page)


def copy_restriction(page, restriction, shares, original_owner_id):
    """Give a duplicated page the restriction and share list of its source."""
    ItemRestriction.objects.create(workspace_id=restriction.workspace_id, page=page)
    copied = [
        ItemShare(
            workspace_id=share.workspace_id,
            page=page,
            target_type=share.target_type,
            member_id=share.member_id,
            project_id=share.project_id,
            group_id=share.group_id,
            level=share.level,
        )
        for share in shares
    ]
    # The source page's owner keeps full access to the copy.
    if original_owner_id != page.owned_by_id:
        copied = [s for s in copied if not (s.target_type == ShareTarget.MEMBER and s.member_id == original_owner_id)]
        copied.append(
            ItemShare(
                workspace_id=restriction.workspace_id,
                page=page,
                target_type=ShareTarget.MEMBER,
                member_id=original_owner_id,
                level=AccessLevel.EDIT,
            )
        )
    ItemShare.objects.bulk_create(copied)
