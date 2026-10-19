# Card links for relation fields (plane.relations).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('db', '0125_custom_field_formula'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CardLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('field', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='card_links', to='db.customfield')),
                ('from_issue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='db.issue')),
                ('to_issue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='db.issue')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='db.workspace')),
            ],
            options={
                'db_table': 'relations_card_links',
                'ordering': ('created_at',),
                'indexes': [models.Index(fields=['field', 'from_issue'], name='relations_link_from_idx'), models.Index(fields=['field', 'to_issue'], name='relations_link_to_idx')],
                'constraints': [models.UniqueConstraint(fields=('field', 'from_issue', 'to_issue'), name='relations_card_link_unique')],
            },
        ),
    ]
