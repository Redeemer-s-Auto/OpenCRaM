# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""One row per link between two cards, for one relation field.

A two-way relation is a pair of fields: the primary (on the board where it was
made) and its mirror (on the target board). Links are stored once, under the
primary field. The mirror reads the same rows backwards, so the two sides can
never disagree.

Rows are never read on their own: ``plane.relations.service`` reads them for
cards the caller already passed, and drops linked cards the viewer cannot see.
"""

import uuid

from django.conf import settings
from django.db import models


class CardLink(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    # Always the primary field of a pair (never the mirror).
    field = models.ForeignKey("db.CustomField", on_delete=models.CASCADE, related_name="card_links")
    from_issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="+")
    to_issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "relations_card_links"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=["field", "from_issue", "to_issue"], name="relations_card_link_unique"),
        ]
        indexes = [
            models.Index(fields=["field", "from_issue"], name="relations_link_from_idx"),
            models.Index(fields=["field", "to_issue"], name="relations_link_to_idx"),
        ]

    def __str__(self):
        return f"{self.from_issue_id} -> {self.to_issue_id} ({self.field_id})"
