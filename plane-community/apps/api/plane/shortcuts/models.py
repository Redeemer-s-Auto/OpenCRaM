# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Two small tables.

``CardShortcut``: marks a card as a shortcut to another card (Notion's "link to page"
inside a page tree). The shortcut card is a normal card so every board view, the
sidebar tree and the page list show it; its own name stays the neutral word
"Shortcut" and is never the target's title, so nothing about the target is stored
where other people could read it. When the target is deleted, the shortcut shows
"Card removed" to people who could see the target, and "Hidden card" to everyone else.

``CardBodyLink``: the backlink index, one row per "Link to card" block found in a
card body. Rebuilt from ``description_html`` whenever a card is saved
(``plane.shortcuts.signals``). ``target_id`` is a plain id, not a foreign key: a body
may point at a card that is gone, and the index must not fail on it.

Rows are never returned as they are: ``plane.shortcuts.service`` reads them for one
viewer and drops every card that viewer cannot see.
"""

import uuid

from django.conf import settings
from django.db import models

SHORTCUT_NAME = "Shortcut"


class CardShortcut(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    # The shortcut card itself (lives on the board where the shortcut was put).
    issue = models.OneToOneField("db.Issue", on_delete=models.CASCADE, related_name="card_shortcut")
    # The card it opens. No database constraint and DO_NOTHING on purpose: Plane's
    # soft delete would otherwise blank this (and so tell everyone the target was
    # deleted, even people who could never see it). A target that is gone for good
    # simply no longer matches a row, which reads as "Card removed".
    target = models.ForeignKey(
        "db.Issue",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        blank=True,
        related_name="shortcuts_to_here",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "shortcuts_card_shortcuts"
        ordering = ("created_at",)
        indexes = [models.Index(fields=["target"], name="shortcuts_target_idx")]

    def __str__(self):
        return f"{self.issue_id} -> {self.target_id}"


class CardBodyLink(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    source = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="+")
    target_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shortcuts_card_body_links"
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(fields=["source", "target_id"], name="shortcuts_body_link_unique"),
        ]
        indexes = [models.Index(fields=["target_id"], name="shortcuts_body_target_idx")]

    def __str__(self):
        return f"{self.source_id} -> {self.target_id}"
