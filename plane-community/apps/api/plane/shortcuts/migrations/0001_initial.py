# Card shortcuts and the backlink index (plane.shortcuts).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('db', '0126_issue_templates'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CardShortcut',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('issue', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='card_shortcut', to='db.issue')),
                ('target', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='shortcuts_to_here', to='db.issue')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='db.workspace')),
            ],
            options={
                'db_table': 'shortcuts_card_shortcuts',
                'ordering': ('created_at',),
                'indexes': [models.Index(fields=['target'], name='shortcuts_target_idx')],
            },
        ),
        migrations.CreateModel(
            name='CardBodyLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('target_id', models.UUIDField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='db.issue')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='db.workspace')),
            ],
            options={
                'db_table': 'shortcuts_card_body_links',
                'ordering': ('created_at',),
                'indexes': [models.Index(fields=['target_id'], name='shortcuts_body_target_idx')],
                'constraints': [models.UniqueConstraint(fields=('source', 'target_id'), name='shortcuts_body_link_unique')],
            },
        ),
    ]
