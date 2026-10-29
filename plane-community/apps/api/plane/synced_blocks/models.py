# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""One block of text shown on many pages.

The text lives here once. A page holds only the block id, so an edit in any copy is an
edit of this row. Who may read or change it follows the *home card*: the card the block
was made on. Someone who cannot see the home card gets no text, so a restricted block
cannot leak onto an open page.
"""

import uuid

from django.conf import settings
from django.db import models


class SyncedBlock(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="+")
    home_issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="+")
    content_html = models.TextField(default="<p></p>")
    # Goes up by one on every save. Copies use it to know they are out of date.
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "synced_blocks"
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=["home_issue"], name="synced_block_home_idx")]

    def __str__(self):
        return f"synced block {self.id} (v{self.version})"
