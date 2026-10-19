# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Which linked cards a viewer may see or link to.

A linked card is shown, counted, or offered in the picker only when ALL hold:
- it is live (``Issue.issue_objects``: not deleted, archived or a draft),
- the viewer is an active member of the card's board (a guest sees only cards
  they made unless the board lets guests see everything) - this also covers
  private boards, which only members can see,
- the card passes the sharing rules (``plane.sharing.visibility.visible_issues``).

Anyone else (no user, a background job) sees no linked card at all.
"""

from django.db.models import Q

from plane.db.models import Issue, ProjectMember
from plane.sharing.models import AccessLevel
from plane.sharing.visibility import visible_issues

GUEST = 5
MEMBER = 15


def _real_user(user):
    if user is None or getattr(user, "is_anonymous", True) or not getattr(user, "is_authenticated", False):
        return None
    return user


def _membership_q(user, min_role):
    memberships = ProjectMember.objects.filter(
        member_id=user.id, is_active=True, deleted_at__isnull=True, role__gte=min_role
    )
    full = memberships.filter(Q(role__gt=GUEST) | Q(project__guest_view_all_features=True)).values("project_id")
    own_only = memberships.filter(role=GUEST, project__guest_view_all_features=False).values("project_id")
    return Q(project_id__in=full) | (Q(project_id__in=own_only) & Q(created_by_id=user.id))


def viewable_issues(user, queryset=None):
    """Cards ``user`` may see, as an Issue queryset. Empty for no user."""
    queryset = Issue.issue_objects.all() if queryset is None else queryset
    user = _real_user(user)
    if user is None:
        return queryset.none()
    return visible_issues(queryset.filter(_membership_q(user, GUEST)), user)


def editable_issues(user, queryset=None):
    """Cards ``user`` may change: members of the board (guests only their own), and EDIT under sharing rules."""
    queryset = Issue.issue_objects.all() if queryset is None else queryset
    user = _real_user(user)
    if user is None:
        return queryset.none()
    memberships = ProjectMember.objects.filter(member_id=user.id, is_active=True, deleted_at__isnull=True)
    q = Q(project_id__in=memberships.filter(role__gte=MEMBER).values("project_id")) | (
        Q(project_id__in=memberships.filter(role=GUEST).values("project_id")) & Q(created_by_id=user.id)
    )
    return visible_issues(queryset.filter(q), user, min_level=AccessLevel.EDIT)
