# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import uuid

from django.conf import settings
from django.db import models


class GardenExternalIdentity(models.Model):
    """Stable link between a Garden Firebase principal and a Plane user."""

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    provider = models.CharField(max_length=32, default="firebase")
    external_id = models.CharField(max_length=128)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="garden_external_identities")
    access_version = models.PositiveBigIntegerField(default=0)
    projection_hash = models.CharField(max_length=64, blank=True, default="")
    projection_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "garden_external_identities"
        constraints = [
            models.UniqueConstraint(fields=["provider", "external_id"], name="garden_external_identity_provider_external_unique"),
            models.UniqueConstraint(fields=["provider", "user"], name="garden_external_identity_provider_user_unique"),
        ]
        indexes = [models.Index(fields=["provider", "external_id"], name="garden_identity_lookup_idx")]

    def __str__(self):
        return f"{self.provider}:{self.external_id} -> {self.user_id}"
