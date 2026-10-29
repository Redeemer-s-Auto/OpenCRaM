# Date reminders (plane.reminders).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("db", "0126_issue_templates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DateReminder",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("mention_id", models.UUIDField()),
                ("event_date", models.DateField()),
                ("event_time", models.TimeField(blank=True, null=True)),
                ("tz", models.CharField(default="UTC", max_length=64)),
                ("offset_minutes", models.PositiveIntegerField(default=0)),
                ("remind_at", models.DateTimeField()),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("stopped_at", models.DateTimeField(blank=True, null=True)),
                ("stop_reason", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "issue",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="db.issue"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="db.workspace"),
                ),
            ],
            options={
                "db_table": "date_reminders",
                "ordering": ("remind_at",),
                "indexes": [
                    models.Index(
                        condition=models.Q(("sent_at__isnull", True), ("stopped_at__isnull", True)),
                        fields=["remind_at"],
                        name="date_reminder_due_idx",
                    ),
                    models.Index(fields=["issue", "user"], name="date_reminder_issue_user_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("mention_id", "user"), name="date_reminder_unique_mention_user")
                ],
            },
        ),
    ]
