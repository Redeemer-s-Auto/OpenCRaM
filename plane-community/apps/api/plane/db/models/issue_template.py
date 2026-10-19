# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models
from django.db.models import Q

# Module imports
from .project import ProjectBaseModel


class IssueTemplate(ProjectBaseModel):
    """A card template on one project (board), like a Notion database template.

    ``data`` holds the card to create, in the shape checked by
    ``plane.utils.issue_templates.clean_template_data``:
        {"name", "description_html", "priority", "state_id", "label_ids",
         "custom_fields": {field_id: value}, "sub_items": [<same shape>, ...]}
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict)
    sort_order = models.FloatField(default=65535)

    class Meta:
        verbose_name = "Issue Template"
        verbose_name_plural = "Issue Templates"
        db_table = "issue_templates"
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(deleted_at__isnull=True),
                name="issue_template_unique_project_name_when_not_deleted",
            )
        ]

    def __str__(self):
        return self.name
