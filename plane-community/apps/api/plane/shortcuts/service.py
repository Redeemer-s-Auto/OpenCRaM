# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Resolve links for one viewer, keep the backlink index, make shortcut cards.

Every function that returns card details takes the viewer and goes through
``plane.shortcuts.visibility.viewable_cards``. A card the viewer cannot see comes
back as ``{"status": "hidden"}`` and nothing else: no title, board, identifier,
colour or id.
"""

import re
import uuid

from django.db import transaction
from django.db.models import F

from plane.db.models import Issue, ProjectMember

from .models import SHORTCUT_NAME, CardBodyLink, CardShortcut
from .visibility import linkable_cards, reachable_ignoring_deletion, viewable_cards

MAX_RESOLVE = 100
MEMBER = 15

HIDDEN = {"status": "hidden"}
REMOVED = {"status": "removed"}

# <card-link-component data-card-id="..."> as the editor stores it.
_TAG = re.compile(r"<card-link-component\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"""\bdata-card-id\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

CARD_FIELDS = (
    "id",
    "name",
    "sequence_id",
    "project_id",
    "project_identifier",
    "project_name",
    "state_color",
    "state_group",
    "archived_at",
)


def as_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def card_ids_in(html):
    """Ids of every "Link to card" block in ``html`` (valid uuids only, in order, no repeats)."""
    found = []
    for tag in _TAG.findall(html or ""):
        match = _ATTR.search(tag)
        card_id = as_uuid(match.group(1)) if match else None
        if card_id and card_id not in found:
            found.append(card_id)
    return found


# ---------------------------------------------------------------------------
# Backlink index
# ---------------------------------------------------------------------------


def reindex_card(issue):
    """Make the index rows for ``issue`` match the link blocks in its body."""
    wanted = {i for i in card_ids_in(issue.description_html) if i != str(issue.id)}
    have = {str(i) for i in CardBodyLink.objects.filter(source_id=issue.id).values_list("target_id", flat=True)}
    if wanted == have:
        return
    with transaction.atomic():
        gone = have - wanted
        if gone:
            CardBodyLink.objects.filter(source_id=issue.id, target_id__in=gone).delete()
        CardBodyLink.objects.bulk_create(
            [CardBodyLink(workspace_id=issue.workspace_id, source_id=issue.id, target_id=i) for i in wanted - have],
            ignore_conflicts=True,
        )


# ---------------------------------------------------------------------------
# Resolving ids for a viewer
# ---------------------------------------------------------------------------


def _with_details(queryset):
    return queryset.annotate(
        project_identifier=F("project__identifier"),
        project_name=F("project__name"),
        state_color=F("state__color"),
        state_group=F("state__group"),
    )


def card_rows(queryset):
    rows = []
    for row in _with_details(queryset).values(*CARD_FIELDS):
        row["id"] = str(row["id"])
        row["project_id"] = str(row["project_id"])
        row["archived"] = row.pop("archived_at") is not None
        row["is_shortcut"] = False
        rows.append(row)
    shortcut_ids = {
        str(i)
        for i in CardShortcut.objects.filter(issue_id__in=[r["id"] for r in rows]).values_list("issue_id", flat=True)
    }
    for row in rows:
        row["is_shortcut"] = row["id"] in shortcut_ids
    return rows


def resolve(user, slug, ids):
    """``{id: resolution}`` for each id (at most MAX_RESOLVE). Unknown text ids are skipped."""
    wanted = []
    for value in ids or []:
        card_id = as_uuid(value)
        if card_id and card_id not in wanted:
            wanted.append(card_id)
    wanted = wanted[:MAX_RESOLVE]
    if not wanted:
        return {}
    visible = {
        row["id"]: {"status": "visible", "card": row}
        for row in card_rows(viewable_cards(user, linkable_cards().filter(workspace__slug=slug, pk__in=wanted)))
    }
    rest = [i for i in wanted if i not in visible]
    existing = {
        str(row["id"]): row
        for row in Issue.all_objects.filter(pk__in=rest).values("id", "deleted_at", "workspace__slug")
    }
    could_see = reachable_ignoring_deletion(user, [i for i, row in existing.items() if row["deleted_at"]])
    result = {}
    for card_id in wanted:
        if card_id in visible:
            result[card_id] = visible[card_id]
            continue
        row = existing.get(card_id)
        if row is None:
            # Gone for good: nothing is left to protect.
            result[card_id] = dict(REMOVED)
        elif row["deleted_at"] and row["workspace__slug"] == slug and card_id in could_see:
            result[card_id] = dict(REMOVED)
        else:
            result[card_id] = dict(HIDDEN)
    return result


def search(user, slug, text="", limit=20):
    """Cards ``user`` may see in the workspace, for the "Link to card" and shortcut pickers."""
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 20
    queryset = viewable_cards(user, linkable_cards().filter(workspace__slug=slug)).exclude(
        pk__in=CardShortcut.objects.values("issue_id")
    )
    text = " ".join(str(text or "").split())[:200]
    match = re.fullmatch(r"([A-Za-z0-9]{1,12})-(\d{1,9})", text)
    if match:
        queryset = queryset.filter(project__identifier__iexact=match.group(1), sequence_id=int(match.group(2)))
    elif text:
        queryset = queryset.filter(name__icontains=text)
    return card_rows(queryset.order_by("-updated_at")[:limit])


# ---------------------------------------------------------------------------
# Shortcut cards
# ---------------------------------------------------------------------------


def shortcut_targets(user, slug, shortcuts):
    """``{shortcut card id: resolution of its target}`` for CardShortcut rows."""
    resolved = resolve(user, slug, [s.target_id for s in shortcuts if s.target_id])
    return {
        str(s.issue_id): (resolved.get(str(s.target_id), dict(HIDDEN)) if s.target_id else dict(REMOVED))
        for s in shortcuts
    }


def shortcuts_for_cards(user, slug, issue_ids):
    """Shortcut info for the cards in ``issue_ids`` that are shortcuts (caller already checked reach)."""
    ids = [i for i in (as_uuid(v) for v in issue_ids) if i]
    if not ids:
        return {}
    return shortcut_targets(user, slug, list(CardShortcut.objects.filter(issue_id__in=ids)))


def project_shortcuts(user, slug, project_id):
    """Shortcut cards on a board that ``user`` reaches, with their targets resolved for ``user``."""
    cards = viewable_cards(user, Issue.objects.filter(workspace__slug=slug, project_id=project_id))
    rows = list(CardShortcut.objects.filter(issue_id__in=cards.values("id")))
    return shortcut_targets(user, slug, rows)


class ShortcutError(Exception):
    pass


def create_shortcut(user, project, target_id, parent_id=None):
    """Put a shortcut to ``target_id`` on ``project``. Returns the new shortcut card."""
    if not ProjectMember.objects.filter(
        project_id=project.id, member_id=user.id, is_active=True, deleted_at__isnull=True, role__gte=MEMBER
    ).exists():
        raise ShortcutError("You cannot add cards to this board.")
    target_id = as_uuid(target_id)
    target = (
        viewable_cards(user, linkable_cards().filter(workspace_id=project.workspace_id, pk=target_id)).first()
        if target_id
        else None
    )
    # Same answer for "no such card" and "a card you cannot see".
    if target is None:
        raise ShortcutError("Card not found.")
    if CardShortcut.objects.filter(issue_id=target.id).exists():
        raise ShortcutError("Pick the card itself, not a shortcut to it.")
    parent = None
    if parent_id:
        parent = viewable_cards(user, Issue.issue_objects.filter(project_id=project.id, pk=as_uuid(parent_id))).first()
        if parent is None:
            raise ShortcutError("Parent card not found.")
    with transaction.atomic():
        issue = Issue(
            name=SHORTCUT_NAME,
            project=project,
            workspace_id=project.workspace_id,
            parent=parent,
            description_html="<p></p>",
            created_by=user,
            updated_by=user,
        )
        issue.save()
        CardShortcut.objects.create(workspace_id=project.workspace_id, issue=issue, target=target, created_by=user)
    return issue


# ---------------------------------------------------------------------------
# Backlinks
# ---------------------------------------------------------------------------


def backlinks(user, slug, issue_id):
    """Cards ``user`` may see that link to ``issue_id`` (body blocks and shortcut cards)."""
    issue_id = as_uuid(issue_id)
    body_sources = set(CardBodyLink.objects.filter(target_id=issue_id).values_list("source_id", flat=True))
    shortcut_sources = set(CardShortcut.objects.filter(target_id=issue_id).values_list("issue_id", flat=True))
    ids = {str(i) for i in body_sources | shortcut_sources}
    if not ids:
        return []
    rows = card_rows(
        viewable_cards(user, Issue.issue_objects.filter(workspace__slug=slug, pk__in=ids)).order_by("-updated_at")
    )
    shortcut_ids = {str(i) for i in shortcut_sources}
    for row in rows:
        row["kind"] = "shortcut" if row["id"] in shortcut_ids else "link"
    return rows
