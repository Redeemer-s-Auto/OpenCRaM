# Generated for The Garden Plane integration.
# SPDX-License-Identifier: AGPL-3.0-only

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GardenExternalIdentity",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("provider", models.CharField(default="firebase", max_length=32)),
                ("external_id", models.CharField(max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="garden_external_identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "garden_external_identities",
            },
        ),
        migrations.AddConstraint(
            model_name="gardenexternalidentity",
            constraint=models.UniqueConstraint(
                fields=("provider", "external_id"),
                name="garden_external_identity_provider_external_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="gardenexternalidentity",
            constraint=models.UniqueConstraint(
                fields=("provider", "user"),
                name="garden_external_identity_provider_user_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="gardenexternalidentity",
            index=models.Index(fields=["provider", "external_id"], name="garden_identity_lookup_idx"),
        ),
    ]
