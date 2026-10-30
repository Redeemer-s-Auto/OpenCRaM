# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""The one place that decides who can see a restricted work item or page.

Every read path filters with ``visible_issues`` / ``visible_pages`` (or the
``hidden_*_ids`` subqueries for rows that point at an item). Every write path
checks ``issue_access_level`` / ``page_access_level``. Do not copy these rules
into views.

An item is hidden from a user when all of these hold:
- it has an ``ItemRestriction`` row,
- the user did not create it (pages: does not own it),
- the user is not an admin or owner of its workspace,
- no ``ItemShare`` row on it matches the user at the needed level.

Private projects (``Project.is_private``, added by the custom-fields work) are
stricter: a restricted item there is hidden from everyone who is not an active
member of that project, whatever their workspace role or share. Only members
see anything in a private project. The rule switches on by itself once the
field exists.

Anonymous callers and background jobs acting for nobody (``user=None``) see no
restricted item.
"""

from django.db.models import Q, QuerySet

from plane.db.models import Issue, Page, Project, ProjectMember, ProjectPage, Workspace, WorkspaceMember
from plane.sharing.board_access import effective_group_ids
from plane.sharing.models import AccessLevel, ItemRestriction, ItemShare, ShareTarget

ADMIN_ROLE = 20


def _private_projects_supported():
    return any(field.name == "is_private" for field in Project._meta.get_fields())


def _member_project_ids(user):
    return ProjectMember.objects.filter(member=user, is_active=True, deleted_at__isnull=True).values("project_id")


def _private_blocked_issue_q(user):
    """Q on ItemRestriction: the work item sits in a private project ``user`` is not a member of."""
    if not _private_projects_supported():
        return Q(pk__in=[])
    return Q(issue__project__is_private=True) & ~Q(issue__project_id__in=_member_project_ids(user))


def _private_blocked_page_q(user):
    """Q on ItemRestriction: the page belongs to a private project ``user`` is not a member of."""
    if not _private_projects_supported():
        return Q(pk__in=[])
    blocked_pages = (
        ProjectPage.objects.filter(project__is_private=True, deleted_at__isnull=True)
        .exclude(project_id__in=_member_project_ids(user))
        .values("page_id")
    )
    return Q(page_id__in=blocked_pages)


def _real_user(user):
    if user is None or getattr(user, "is_anonymous", True):
        return None
    return user


def _admin_workspace_q(user, field="workspace_id"):
    """Workspaces where ``user`` always sees everything: admins and the owner."""
    return Q(
        **{
            f"{field}__in": WorkspaceMember.objects.filter(
                member=user, role=ADMIN_ROLE, is_active=True, deleted_at__isnull=True
            ).values("workspace_id")
        }
    ) | Q(**{f"{field}__in": Workspace.objects.filter(owner=user).values("id")})


def share_matches_user(user, min_level=AccessLevel.VIEW):
    """Q on ItemShare: the share reaches ``user`` at ``min_level`` or higher."""
    project_ids = ProjectMember.objects.filter(member=user, is_active=True, deleted_at__isnull=True).values("project_id")
    # Direct groups plus every group that includes one of them (groups inside groups).
    group_ids = list(effective_group_ids(user))
    # "Everybody" means workspace members and admins, not outside guests (role 5).
    workspace_ids = WorkspaceMember.objects.filter(
        member=user, role__gte=15, is_active=True, deleted_at__isnull=True
    ).values("workspace_id")
    return Q(level__gte=min_level) & (
        Q(target_type=ShareTarget.MEMBER, member=user)
        | Q(target_type=ShareTarget.PROJECT, project_id__in=project_ids)
        | Q(target_type=ShareTarget.GROUP, group_id__in=group_ids)
        | Q(target_type=ShareTarget.WORKSPACE, workspace_id__in=workspace_ids)
    )


def hidden_issue_ids(user, min_level=AccessLevel.VIEW):
    """Subquery of work item ids ``user`` may not reach at ``min_level``."""
    restrictions = ItemRestriction.objects.filter(issue__isnull=False)
    user = _real_user(user)
    if user is None:
        return restrictions.values("issue_id")
    reachable = ItemShare.objects.filter(share_matches_user(user, min_level), issue__isnull=False).values("issue_id")
    not_reached = (
        restrictions.exclude(issue__created_by=user).exclude(_admin_workspace_q(user)).exclude(issue_id__in=reachable)
    )
    return restrictions.filter(Q(pk__in=not_reached.values("pk")) | _private_blocked_issue_q(user)).values("issue_id")


def hidden_page_ids(user, min_level=AccessLevel.VIEW):
    """Subquery of page ids ``user`` may not reach at ``min_level``."""
    restrictions = ItemRestriction.objects.filter(page__isnull=False)
    user = _real_user(user)
    if user is None:
        return restrictions.values("page_id")
    reachable = ItemShare.objects.filter(share_matches_user(user, min_level), page__isnull=False).values("page_id")
    not_reached = (
        restrictions.exclude(page__owned_by=user).exclude(_admin_workspace_q(user)).exclude(page_id__in=reachable)
    )
    return restrictions.filter(Q(pk__in=not_reached.values("pk")) | _private_blocked_page_q(user)).values("page_id")


def visible_issues(queryset: QuerySet, user, field="pk", min_level=AccessLevel.VIEW) -> QuerySet:
    """Drop rows whose work item (``field``) is hidden from ``user``."""
    return queryset.exclude(**{f"{field}__in": hidden_issue_ids(user, min_level)})


def visible_pages(queryset: QuerySet, user, field="pk", min_level=AccessLevel.VIEW) -> QuerySet:
    """Drop rows whose page (``field``) is hidden from ``user``."""
    return queryset.exclude(**{f"{field}__in": hidden_page_ids(user, min_level)})


def visible_activity(queryset, user):
    """Drop activity on hidden work items and rows that point at one (parent, relations)."""
    hidden = hidden_issue_ids(user)
    return visible_issues(queryset, user, field="issue_id").exclude(
        Q(old_identifier__in=hidden) | Q(new_identifier__in=hidden)
    )


def restricted_issue_ids():
    return ItemRestriction.objects.filter(issue__isnull=False).values("issue_id")


def restricted_page_ids():
    return ItemRestriction.objects.filter(page__isnull=False).values("page_id")


def _level_for(user, restriction, owner_id, shares):
    if restriction is None:
        return None  # not restricted: normal project rules apply
    user = _real_user(user)
    if user is None:
        return 0
    if ItemRestriction.objects.filter(
        Q(pk=restriction.pk) & (_private_blocked_issue_q(user) | _private_blocked_page_q(user))
    ).exists():
        return 0
    if owner_id == user.id:
        return AccessLevel.EDIT
    workspace_id = restriction.workspace_id
    if WorkspaceMember.objects.filter(
        workspace_id=workspace_id, member=user, role=ADMIN_ROLE, is_active=True, deleted_at__isnull=True
    ).exists() or Workspace.objects.filter(id=workspace_id, owner=user).exists():
        return AccessLevel.EDIT
    best = shares.filter(share_matches_user(user)).order_by("-level").values_list("level", flat=True).first()
    return best or 0


def issue_access_level(user, issue_id):
    """None when the item is not restricted, else 0 (hidden) or an AccessLevel."""
    restriction = ItemRestriction.objects.filter(issue_id=issue_id).first()
    if restriction is None:
        return None
    owner_id = Issue.all_objects.filter(pk=issue_id).values_list("created_by_id", flat=True).first()
    return _level_for(user, restriction, owner_id, ItemShare.objects.filter(issue_id=issue_id))


def page_access_level(user, page_id):
    """None when the page is not restricted, else 0 (hidden) or an AccessLevel."""
    restriction = ItemRestriction.objects.filter(page_id=page_id).first()
    if restriction is None:
        return None
    owner_id = Page.all_objects.filter(pk=page_id).values_list("owned_by_id", flat=True).first()
    return _level_for(user, restriction, owner_id, ItemShare.objects.filter(page_id=page_id))


def can_reach(level, min_level=AccessLevel.VIEW):
    return level is None or level >= min_level


def can_view_issue(user, issue_id):
    return can_reach(issue_access_level(user, issue_id))


def can_view_page(user, page_id):
    return can_reach(page_access_level(user, page_id))
