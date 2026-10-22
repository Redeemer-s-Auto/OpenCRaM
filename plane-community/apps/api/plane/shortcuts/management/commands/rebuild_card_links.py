# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rebuild the "Linked from" index from every card body: ``manage.py rebuild_card_links``."""

from django.core.management.base import BaseCommand

from plane.db.models import Issue
from plane.shortcuts.models import CardBodyLink
from plane.shortcuts.service import reindex_card


class Command(BaseCommand):
    help = "Rebuild the card backlink index from card bodies."

    def handle(self, *args, **options):
        count = 0
        cards = Issue.all_objects.filter(description_html__icontains="card-link-component").only(
            "id", "workspace_id", "description_html"
        )
        for issue in cards.iterator(chunk_size=500):
            reindex_card(issue)
            count += 1
        stale, _ = CardBodyLink.objects.exclude(source_id__in=cards.values("id")).delete()
        self.stdout.write(f"Reindexed {count} card(s), removed {stale} stale link(s).")
