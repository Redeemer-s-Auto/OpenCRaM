# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Saved views can hide from the view tabs above a board. Hand-written."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0128_project_placement"),
    ]

    operations = [
        migrations.AddField(
            model_name="issueview",
            name="is_hidden",
            field=models.BooleanField(default=False),
        ),
    ]
