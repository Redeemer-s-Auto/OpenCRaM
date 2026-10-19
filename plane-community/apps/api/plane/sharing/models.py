# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Per-item sharing rules for work items and pages.

An item with no ``ItemRestriction`` row follows Plane's normal project rules.
An item with a restriction row is visible only to its creator, workspace
admins, and the targets listed in ``ItemShare``.
"""

import uuid

from django.conf import settings
from django.db import models


class AccessLevel(models.IntegerChoices):
    VIEW = 5, "Can view"
    COMMENT = 10, "Can comment"
    EDIT = 15, "Can edit"


class ShareTarget(models.TextChoices):
    MEMBER = "member", "Person"
    PROJECT = "project", "Department"
    GROUP = "group", "Group"
    WORKSPACE = "workspace", "Everybody"


class TimestampedModel(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        abstract = True


class AccessGroup(TimestampedModel):
    """A named list of people from any project, managed by workspace admins."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="access_groups")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "sharing_access_groups"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["workspace", "name"], name="sharing_access_group_workspace_name_unique"),
        ]

    def __str__(self):
        return self.name


class AccessGroupMember(TimestampedModel):
    group = models.ForeignKey(AccessGroup, on_delete=models.CASCADE, related_name="members")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="access_group_memberships")

    class Meta:
        db_table = "sharing_access_group_members"
        constraints = [
            models.UniqueConstraint(fields=["group", "member"], name="sharing_access_group_member_unique"),
        ]


class ItemRestriction(TimestampedModel):
    """Marks one work item or page as "only the people I pick"."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="item_restrictions")
    issue = models.OneToOneField(
        "db.Issue", on_delete=models.CASCADE, null=True, blank=True, related_name="sharing_restriction"
    )
    page = models.OneToOneField(
        "db.Page", on_delete=models.CASCADE, null=True, blank=True, related_name="sharing_restriction"
    )

    class Meta:
        db_table = "sharing_item_restrictions"
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(issue__isnull=False, page__isnull=True) | models.Q(issue__isnull=True, page__isnull=False)),
                name="sharing_item_restriction_one_item",
            ),
        ]


class ItemShare(TimestampedModel):
    """One entry on a restricted item's share list."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="item_shares")
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, null=True, blank=True, related_name="sharing_shares")
    page = models.ForeignKey("db.Page", on_delete=models.CASCADE, null=True, blank=True, related_name="sharing_shares")
    target_type = models.CharField(max_length=16, choices=ShareTarget.choices)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="item_shares"
    )
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, null=True, blank=True, related_name="item_shares")
    group = models.ForeignKey(AccessGroup, on_delete=models.CASCADE, null=True, blank=True, related_name="item_shares")
    level = models.PositiveSmallIntegerField(choices=AccessLevel.choices, default=AccessLevel.VIEW)

    class Meta:
        db_table = "sharing_item_shares"
        indexes = [
            models.Index(fields=["issue"], name="sharing_share_issue_idx"),
            models.Index(fields=["page"], name="sharing_share_page_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(issue__isnull=False, page__isnull=True) | models.Q(issue__isnull=True, page__isnull=False)),
                name="sharing_item_share_one_item",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(target_type="member", member__isnull=False, project__isnull=True, group__isnull=True)
                    | models.Q(target_type="project", member__isnull=True, project__isnull=False, group__isnull=True)
                    | models.Q(target_type="group", member__isnull=True, project__isnull=True, group__isnull=False)
                    | models.Q(target_type="workspace", member__isnull=True, project__isnull=True, group__isnull=True)
                ),
                name="sharing_item_share_target_matches_type",
            ),
        ]
