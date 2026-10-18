# SPDX-License-Identifier: AGPL-3.0-only

from django.db import migrations


def disable_plane_services(apps, schema_editor):
    Instance = apps.get_model("license", "Instance")
    Instance.objects.all().update(is_telemetry_enabled=False, is_support_required=False)


class Migration(migrations.Migration):
    dependencies = [
        ("garden", "0001_initial"),
        ("license", "0006_instance_is_current_version_deprecated"),
    ]

    operations = [
        migrations.RunPython(disable_plane_services, migrations.RunPython.noop),
    ]
