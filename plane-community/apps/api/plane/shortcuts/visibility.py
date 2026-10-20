# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who may see a linked card. One rule for blocks, shortcut cards and backlinks.

A card is visible to ``user`` when ALL hold:
- ``user`` reaches its board (``plane.one_unit.reach.reach_q``): an active member;
  a guest only sees the cards they made unless the board lets guests see all.
  Workspace admins get no extra reach, as in the sidebar tree.
- the sharing rules do not hide it (``plane.sharing.visibility.visible_issues``),
  which also covers private boards.

No user (anonymous, background jobs) sees no card at all.
"""

from plane.db.models import Issue
from plane.one_unit.reach import reach_q
from plane.sharing.visibility import visible_issues


def _real_user(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def linkable_cards():
    """Cards a link can point at: not deleted, not a draft, not waiting in intake. Archived cards count."""
    return Issue.objects.filter(is_draft=False).exclude(state__group="triage")


def viewable_cards(user, queryset=None):
    """Of ``queryset`` (default: every linkable card), the cards ``user`` may see."""
    queryset = linkable_cards() if queryset is None else queryset
    user = _real_user(user)
    if user is None:
        return queryset.none()
    return visible_issues(queryset.filter(reach_q(user)), user)


def reachable_ignoring_deletion(user, ids):
    """Of ``ids``, the (string) ids ``user`` could see if they were not deleted."""
    user = _real_user(user)
    ids = [str(i) for i in ids if i]
    if user is None or not ids:
        return set()
    queryset = visible_issues(Issue.all_objects.filter(pk__in=ids).filter(reach_q(user)), user)
    return {str(i) for i in queryset.values_list("id", flat=True)}
