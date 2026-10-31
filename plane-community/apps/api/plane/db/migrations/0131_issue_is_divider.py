# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Task lists: a card can be a divider row (a section header in the list). Hand-written."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0130_project_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="issue",
            name="is_divider",
            field=models.BooleanField(default=False),
        ),
    ]
