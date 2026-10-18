# SPDX-License-Identifier: AGPL-3.0-only

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("garden", "0002_disable_plane_telemetry")]

    operations = [
        migrations.AddField(model_name="gardenexternalidentity", name="access_version", field=models.PositiveBigIntegerField(default=0)),
        migrations.AddField(model_name="gardenexternalidentity", name="projection_hash", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(model_name="gardenexternalidentity", name="projection_synced_at", field=models.DateTimeField(blank=True, null=True)),
    ]
