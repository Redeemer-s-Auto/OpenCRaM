# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who may read or change a synced block, and how its text is cleaned.

Access follows the home card (the card the block was made on):
- read: the viewer can see the home card (board membership plus sharing rules);
- change: the viewer can edit the home card.
A block the viewer may not read looks the same as a block that does not exist.
"""

import re

from django.db.models import F
from django.utils.html import strip_tags
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, WorkspaceMember
from plane.relations.visibility import editable_issues, viewable_issues
from plane.utils.content_validator import validate_html_content

from .models import SyncedBlock

# A synced block inside a synced block could point back at itself.
NESTED = re.compile(r'data-block-type=["\']synced-block["\']', re.IGNORECASE)
MAX_LIST = 20


def _home(block):
    # Includes archived cards. A deleted home card hides the block from everyone.
    return Issue.objects.filter(pk=block.home_issue_id)


def can_read(user, block):
    return viewable_issues(user, _home(block)).exists()


def can_edit(user, block):
    return editable_issues(user, _home(block)).exists()


def can_delete(user, block):
    if not can_read(user, block):
        return False
    if block.created_by_id == user.id:
        return True
    return WorkspaceMember.objects.filter(
        workspace_id=block.workspace_id, member_id=user.id, role=20, is_active=True
    ).exists()


def clean_content(raw):
    if not isinstance(raw, str):
        raise ValidationError({"content_html": "Must be text."})
    if NESTED.search(raw):
        raise ValidationError({"content_html": "A synced block cannot hold another synced block."})
    ok, error, cleaned = validate_html_content(raw)
    if not ok:
        raise ValidationError({"content_html": error or "Not allowed."})
    cleaned = raw if cleaned is None else cleaned
    return cleaned or "<p></p>"


def create_block(user, slug, home_issue_id, content_html):
    home = editable_issues(user, Issue.issue_objects.filter(workspace__slug=slug, pk=home_issue_id)).first()
    if home is None:
        return None
    return SyncedBlock.objects.create(
        workspace_id=home.workspace_id,
        home_issue=home,
        content_html=clean_content(content_html) if content_html else "<p></p>",
        created_by=user,
        updated_by=user,
    )


def save_block(user, block, content_html):
    SyncedBlock.objects.filter(pk=block.pk).update(
        content_html=clean_content(content_html), version=F("version") + 1, updated_by=user
    )
    block.refresh_from_db()
    return block


def readable_blocks(user, slug, search=""):
    """Blocks the viewer may read, newest first, for the "use an existing block" picker."""
    home_ids = viewable_issues(user, Issue.objects.filter(workspace__slug=slug)).values("id")
    blocks = SyncedBlock.objects.filter(workspace__slug=slug, home_issue_id__in=home_ids).select_related("home_issue")
    results = []
    needle = (search or "").strip().lower()
    for block in blocks[:200]:
        text = " ".join(strip_tags(block.content_html).split())
        if needle and needle not in text.lower():
            continue
        results.append((block, text[:120]))
        if len(results) >= MAX_LIST:
            break
    return results


def payload(user, block, text=None):
    home = block.home_issue
    data = {
        "id": str(block.id),
        "content_html": block.content_html,
        "version": block.version,
        "can_edit": can_edit(user, block),
        "updated_at": block.updated_at,
        "home": {
            "id": str(home.id),
            "name": home.name,
            "project_id": str(home.project_id),
            "project_identifier": home.project.identifier,
            "sequence_id": home.sequence_id,
        },
    }
    if text is not None:
        data["snippet"] = text
    return data
