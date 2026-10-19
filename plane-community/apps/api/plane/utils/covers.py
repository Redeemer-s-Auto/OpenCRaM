# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Cover images for the gallery layout.

A work item's cover is the first image in its page body, or, if there is none,
its first image attachment. Like custom field values, covers are only looked up
for work items already in a result the caller was allowed to see.
"""

from plane.db.models import FileAsset

_DESCRIPTION = FileAsset.EntityTypeContext.ISSUE_DESCRIPTION
_ATTACHMENT = FileAsset.EntityTypeContext.ISSUE_ATTACHMENT


def covers_for_issues(issue_ids):
    """Return ``{issue_id: cover path}`` (a relative /api/assets/... path)."""
    issue_ids = [i for i in issue_ids if i]
    if not issue_ids:
        return {}
    rows = (
        FileAsset.objects.filter(
            issue_id__in=issue_ids,
            entity_type__in=[_DESCRIPTION, _ATTACHMENT],
            is_uploaded=True,
            is_deleted=False,
            attributes__type__startswith="image/",
        )
        .select_related("workspace")
        .order_by("created_at")
    )
    best = {}
    for asset in rows:
        key = str(asset.issue_id)
        current = best.get(key)
        # Body images win over attachments; within a kind, the oldest wins.
        if current is None or (current.entity_type == _ATTACHMENT and asset.entity_type == _DESCRIPTION):
            best[key] = asset
    return {key: asset.asset_url for key, asset in best.items()}


def attach_covers(rows, key="id"):
    """Add ``cover_image`` to a list of work-item dicts, in place. Returns rows."""
    if not rows:
        return rows
    covers = covers_for_issues([row.get(key) for row in rows])
    for row in rows:
        row["cover_image"] = covers.get(str(row.get(key)))
    return rows
