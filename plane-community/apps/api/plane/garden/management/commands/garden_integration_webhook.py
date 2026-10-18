# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from plane.db.models import Webhook, Workspace


@transaction.atomic
def reconcile_integration_webhook():
    workspace_slug = os.environ.get("GARDEN_WORKSPACE_SLUG", "the-garden").strip() or "the-garden"
    workspace = Workspace.objects.filter(slug=workspace_slug).first()
    if workspace is None:
        raise CommandError(f"Workspace '{workspace_slug}' does not exist. Bootstrap Garden Work first.")

    url = os.environ.get("GARDEN_WORK_WEBHOOK_URL", "").strip()
    secret = os.environ.get("GARDEN_WORK_WEBHOOK_SECRET", "").strip()
    if not url:
        raise CommandError("GARDEN_WORK_WEBHOOK_URL is required")
    if not secret or len(secret) < 32:
        raise CommandError("GARDEN_WORK_WEBHOOK_SECRET must contain at least 32 characters")

    webhook = Webhook.objects.filter(workspace=workspace, url=url, deleted_at__isnull=True).first()
    created = webhook is None
    if webhook is None:
        webhook = Webhook.objects.create(
            workspace=workspace,
            url=url,
            secret_key=secret,
            issue=True,
            project=False,
            module=False,
            cycle=False,
            issue_comment=False,
            is_active=True,
            is_internal=False,
            version="v1",
        )
    else:
        changed = []
        desired = {
            "secret_key": secret,
            "issue": True,
            "project": False,
            "module": False,
            "cycle": False,
            "issue_comment": False,
            "is_active": True,
            "is_internal": False,
            "version": "v1",
        }
        for field, value in desired.items():
            if getattr(webhook, field) != value:
                setattr(webhook, field, value)
                changed.append(field)
        if changed:
            webhook.save(update_fields=[*changed, "updated_at"])

    return webhook, created


class Command(BaseCommand):
    help = "Create/update the signed Garden Work -> Firebase webhook using Garden-controlled secrets."

    def handle(self, *args, **options):
        webhook, created = reconcile_integration_webhook()
        self.stdout.write(self.style.SUCCESS(f"Garden Work webhook {'created' if created else 'reconciled'}."))
        self.stdout.write(f"Webhook ID: {webhook.id}")
        self.stdout.write(f"URL: {webhook.url}")
        self.stdout.write("Events: work items only")
        self.stdout.write("")
        self.stdout.write("The same secret must be stored in Firebase Functions as PLANE_WORK_WEBHOOK_SECRET.")
        self.stdout.write("Do not commit the webhook secret or expose it to browser/mobile code.")
