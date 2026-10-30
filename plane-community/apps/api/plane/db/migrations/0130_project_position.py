# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Boards carry a shared position among their siblings in the sidebar tree. Hand-written."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0129_issueview_is_hidden"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="position",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
