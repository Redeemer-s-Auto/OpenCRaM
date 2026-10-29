# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Update the backlink index whenever a card is saved.

Every Plane path that changes a card body (app, public API, templates, repeating
cards, the live editor's save) ends in ``Issue.save()``. Saves that name
``update_fields`` without the body skip the work. Bulk updates that bypass
``save()`` are caught by ``manage.py rebuild_card_links``.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from plane.db.models import Issue

from .service import reindex_card

logger = logging.getLogger("plane.shortcuts")


@receiver(post_save, sender=Issue, dispatch_uid="shortcuts_reindex_card_body")
def reindex_on_save(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    if update_fields is not None and "description_html" not in update_fields:
        return
    try:
        reindex_card(instance)
    except Exception:  # never let the index break a save
        logger.exception("could not update card links for %s", instance.pk)
