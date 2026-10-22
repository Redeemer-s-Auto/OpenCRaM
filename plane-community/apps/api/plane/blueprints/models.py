# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Board blueprints: a named, saved board design that can make new boards.

A ``Blueprint`` holds the current design (``spec``, the same portable document
an export writes) and a version number that goes up on every save. Each save is
also kept as a ``BlueprintVersion``. A board made from a blueprint gets a
``BoardOrigin`` row, so its settings can say "Made from blueprint X v3".

The spec never holds ids from the workspace it came from (see ``spec.py``).
"""

import uuid

from django.conf import settings
from django.db import models


class Blueprint(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="board_blueprints")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    # Same shape as a project's logo_props: {"in_use": "emoji"|"icon", "emoji": {...}, "icon": {...}}
    logo_props = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    spec = models.JSONField(default=dict)
    # False = only the person who saved it (and nobody else) sees and uses it.
    is_shared = models.BooleanField(default=True)
    # The board it was last captured from (None for imports, or once that board is deleted).
    source_project = models.ForeignKey(
        "db.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "blueprints"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=["workspace", "name"], name="blueprint_unique_workspace_name"),
        ]

    def __str__(self):
        return f"{self.name} v{self.version}"


class BlueprintVersion(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    blueprint = models.ForeignKey(Blueprint, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    spec = models.JSONField(default=dict)
    # How this version came to be: "saved", "updated from board", "imported".
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "blueprint_versions"
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(fields=["blueprint", "version"], name="blueprint_version_unique"),
        ]


class BoardOrigin(models.Model):
    """Which blueprint (and which version of it) a board was made from."""

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    project = models.OneToOneField("db.Project", on_delete=models.CASCADE, related_name="blueprint_origin")
    blueprint = models.ForeignKey(
        Blueprint, on_delete=models.SET_NULL, null=True, blank=True, related_name="boards"
    )
    # Kept so the line still reads right after the blueprint is renamed or deleted.
    blueprint_name = models.CharField(max_length=255)
    version = models.PositiveIntegerField()

    class Meta:
        db_table = "blueprint_board_origins"
