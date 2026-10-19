# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Which cards a person may reach outside one project's own pages.

A card is reachable by ``user`` when all of these hold:
- ``user`` is an active member of the card's project (a guest of a project that
  does not let guests see everything reaches only the cards they created),
- the project is not deleted,
- the sharing rules do not hide it (``plane.sharing.visibility.hidden_issue_ids``,
  which also covers private projects).

Workspace admins get no extra reach here: Plane's own project screens need
membership too, so the tree never offers a card that would not open.

Every list that spans projects (card tree, page list, breadcrumbs, references to
a parent or sub-card in another project) goes through this module.
"""

from django.db.models import Q

from plane.db.models import Issue, ProjectMember
from plane.sharing.models import AccessLevel
from plane.sharing.visibility import hidden_issue_ids

GUEST = 5
MAX_DEPTH = 100


def _real_user(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def _memberships(user):
    return ProjectMember.objects.filter(
        member=user, is_active=True, deleted_at__isnull=True, project__deleted_at__isnull=True
    )


def reach_q(user, prefix=""):
    """Q on Issue (or ``prefix`` + Issue fields) for the projects ``user`` reaches."""
    user = _real_user(user)
    if user is None:
        return Q(pk__in=[])
    full = _memberships(user).filter(Q(role__gt=GUEST) | Q(project__guest_view_all_features=True)).values("project_id")
    own_only = _memberships(user).filter(role=GUEST, project__guest_view_all_features=False).values("project_id")
    return Q(**{f"{prefix}project_id__in": full}) | (
        Q(**{f"{prefix}project_id__in": own_only}) & Q(**{f"{prefix}created_by": user})
    )


def reachable_issues(queryset, user, min_level=AccessLevel.VIEW):
    """Keep only the cards ``user`` may reach (project membership + sharing rules)."""
    if _real_user(user) is None:
        return queryset.none()
    return queryset.filter(reach_q(user)).exclude(pk__in=hidden_issue_ids(user, min_level))


def unreachable_issue_ids(user, ids):
    """Of ``ids`` (strings or UUIDs), the ones ``user`` may not reach, as strings."""
    ids = {str(i) for i in ids if i}
    if not ids:
        return set()
    reachable = reachable_issues(Issue.all_objects.filter(pk__in=ids), user).values_list("id", flat=True)
    return ids - {str(i) for i in reachable}


def is_reachable(user, issue_id, min_level=AccessLevel.VIEW):
    if not issue_id:
        return False
    return reachable_issues(Issue.all_objects.filter(pk=issue_id), user, min_level).exists()


def ancestor_ids(issue_id):
    """Ids above ``issue_id``, nearest first. Stops on a loop or after MAX_DEPTH steps."""
    chain, seen = [], {str(issue_id)}
    current = Issue.all_objects.filter(pk=issue_id).values_list("parent_id", flat=True).first()
    while current and str(current) not in seen and len(chain) < MAX_DEPTH:
        chain.append(str(current))
        seen.add(str(current))
        current = Issue.all_objects.filter(pk=current).values_list("parent_id", flat=True).first()
    return chain


def creates_cycle(issue_id, parent_id):
    """True when making ``parent_id`` the parent of ``issue_id`` would close a loop."""
    if not issue_id or not parent_id:
        return False
    if str(issue_id) == str(parent_id):
        return True
    return str(issue_id) in ancestor_ids(parent_id)


def descendant_ids(issue_id, limit=1000):
    """Ids below ``issue_id`` (any depth), at most ``limit``."""
    found, frontier = set(), [str(issue_id)]
    while frontier and len(found) < limit:
        children = [
            str(i)
            for i in Issue.all_objects.filter(parent_id__in=frontier).values_list("id", flat=True)
            if str(i) not in found
        ]
        found.update(children)
        frontier = children
    return found
