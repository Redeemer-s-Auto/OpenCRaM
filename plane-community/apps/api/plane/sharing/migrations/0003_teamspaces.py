# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Teamspaces: sidebar sections that hold boards. Hand-written."""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sharing", "0002_board_shares"),
        ("db", "0127_project_parent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Teamspace",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=64)),
                ("is_default", models.BooleanField(default=False)),
                ("position", models.IntegerField(default=0)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="teamspaces",
                        to="sharing.accessgroup",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="teamspaces", to="db.workspace"
                    ),
                ),
            ],
            options={
                "db_table": "sharing_teamspaces",
                "ordering": ("position", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="teamspace",
            constraint=models.UniqueConstraint(fields=("workspace", "slug"), name="sharing_teamspace_workspace_slug_unique"),
        ),
    ]
