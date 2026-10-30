# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Board-level group shares, exclusions, and groups inside groups. Hand-written."""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sharing", "0001_initial"),
        ("db", "0127_project_parent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessGroupInclude",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                        on_delete=django.db.models.deletion.CASCADE, related_name="includes", to="sharing.accessgroup"
                    ),
                ),
                (
                    "included_group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="included_in",
                        to="sharing.accessgroup",
                    ),
                ),
            ],
            options={
                "db_table": "sharing_access_group_includes",
            },
        ),
        migrations.CreateModel(
            name="ProjectShare",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "level",
                    models.PositiveSmallIntegerField(
                        choices=[(5, "Can view"), (10, "Can comment"), (15, "Can edit")], default=5
                    ),
                ),
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
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_shares",
                        to="sharing.accessgroup",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="group_shares", to="db.project"
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="project_shares", to="db.workspace"
                    ),
                ),
            ],
            options={
                "db_table": "sharing_project_shares",
            },
        ),
        migrations.CreateModel(
            name="ProjectShareExclusion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_exclusions",
                        to="sharing.accessgroup",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="group_exclusions", to="db.project"
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_share_exclusions",
                        to="db.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "sharing_project_share_exclusions",
            },
        ),
        migrations.AddConstraint(
            model_name="accessgroupinclude",
            constraint=models.UniqueConstraint(
                fields=("group", "included_group"), name="sharing_access_group_include_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="accessgroupinclude",
            constraint=models.CheckConstraint(
                condition=models.Q(("group", models.F("included_group")), _negated=True),
                name="sharing_access_group_include_not_self",
            ),
        ),
        migrations.AddConstraint(
            model_name="projectshare",
            constraint=models.UniqueConstraint(fields=("project", "group"), name="sharing_project_share_unique"),
        ),
        migrations.AddConstraint(
            model_name="projectshareexclusion",
            constraint=models.UniqueConstraint(
                fields=("project", "group"), name="sharing_project_share_exclusion_unique"
            ),
        ),
    ]
