# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Who may see a page in the tree or behind a link, and the rows the web app draws.

A page is visible to ``user`` when ALL hold (the project pages list uses the same rules):
- its board is one ``user`` is an active member of, or one the sharing resolver reaches
  (``member_or_shared_projects_q``), and that board is not archived;
- the sharing rules do not hide it (``visible_pages``), which also covers private boards;
- it is public (``access`` 0) or ``user`` owns it;
- on a board where ``user`` is a guest without "guests see everything", ``user`` owns it;
- it is not archived (the tree and links show live pages only).

No user (anonymous, background jobs) sees no page at all. A parent id is sent only when
the parent itself is visible, so a hidden parent never shows through a child.
"""

import uuid

from django.db.models import OuterRef, Q, Subquery

from plane.db.models import Page, Project, ProjectMember, ProjectPage
from plane.sharing.board_access import member_or_shared_projects_q
from plane.sharing.visibility import visible_pages
from plane.utils.project_tree import visible_project_ids

GUEST_ROLE = 5
NOTION_SOURCE = "notion"
FOLDER_PREFIX = "folder:"
PAGE_PREFIX = "page:"

HIDDEN = {"status": "hidden"}
REMOVED = {"status": "removed"}


def _real_user(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def reachable_pages(user, slug):
    """Queryset of the live pages ``user`` may see in the workspace, annotated with ``project_id``."""
    user = _real_user(user)
    if user is None:
        return Page.objects.none()
    project_id = Subquery(
        ProjectPage.objects.filter(page_id=OuterRef("pk"), deleted_at__isnull=True)
        .order_by("created_at")
        .values("project_id")[:1]
    )
    guest_only_own = ProjectMember.objects.filter(
        member=user, role=GUEST_ROLE, is_active=True, deleted_at__isnull=True, project__guest_view_all_features=False
    ).values("project_id")
    return (
        visible_pages(Page.objects.filter(workspace__slug=slug), user)
        .filter(
            member_or_shared_projects_q(user, slug=slug, prefix="projects"),
            projects__archived_at__isnull=True,
        )
        .filter(Q(owned_by=user) | Q(access=Page.PUBLIC_ACCESS))
        .filter(archived_at__isnull=True)
        .annotate(project_id=project_id)
        .filter(project_id__isnull=False)
        .exclude(Q(project_id__in=guest_only_own) & ~Q(owned_by=user))
        .distinct()
    )


def _folder_projects(slug):
    """``{notion page id: project id}`` for the folder projects made by the Notion import."""
    rows = Project.objects.filter(
        workspace__slug=slug, external_source=NOTION_SOURCE, external_id__startswith=FOLDER_PREFIX
    ).values_list("external_id", "id")
    return {external_id[len(FOLDER_PREFIX) :]: str(project_id) for external_id, project_id in rows}


def _is_landing(page, folders):
    """The page a folder project opens on: the imported Notion page the folder was made from."""
    if page.external_source != NOTION_SOURCE or not (page.external_id or "").startswith(PAGE_PREFIX):
        return False
    return folders.get(page.external_id[len(PAGE_PREFIX) :]) == str(page.project_id)


def page_row(page, visible_ids, folders):
    parent_id = str(page.parent_id) if page.parent_id and str(page.parent_id) in visible_ids else None
    return {
        "id": str(page.id),
        "name": page.name or "",
        "logo_props": page.logo_props or {},
        "parent_id": parent_id,
        "project_id": str(page.project_id),
        "access": page.access,
        "owned_by": str(page.owned_by_id),
        "sort_order": page.sort_order,
        "updated_at": page.updated_at,
        "is_landing": _is_landing(page, folders),
    }


def tree(user, slug, project_id=None):
    """Every visible page of the workspace (or of one board) as flat rows; the web app nests them."""
    queryset = reachable_pages(user, slug)
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    pages = list(queryset.order_by("sort_order", "name", "created_at"))
    visible_ids = {str(page.id) for page in pages}
    folders = _folder_projects(slug)
    return [page_row(page, visible_ids, folders) for page in pages]


def _linked_page(page):
    return {
        "id": str(page.id),
        "name": page.name or "",
        "logo_props": page.logo_props or {},
        "project_id": str(page.project_id),
        "access": page.access,
    }


def _linked_project(project):
    return {
        "id": str(project.id),
        "name": project.name,
        "identifier": project.identifier,
        "logo_props": project.logo_props or {},
        "archived": project.archived_at is not None,
    }


def resolve(user, slug, page_ids=(), project_ids=()):
    """``{"pages": {id: resolution}, "projects": {id: resolution}}`` for the caller.

    A resolution is ``{"status": "visible", "page"|"project": {...}}``, ``{"status": "hidden"}``
    (not found, not visible: the same answer so nothing leaks) or ``{"status": "removed"}``
    (deleted, which the caller could have seen).
    """
    page_ids = [u for u in (as_uuid(i) for i in page_ids) if u][:200]
    project_ids = [u for u in (as_uuid(i) for i in project_ids) if u][:200]
    pages = {str(i): dict(HIDDEN) for i in page_ids}
    projects = {str(i): dict(HIDDEN) for i in project_ids}
    user = _real_user(user)
    if user is None:
        return {"pages": pages, "projects": projects}
    if page_ids:
        for page in reachable_pages(user, slug).filter(pk__in=page_ids):
            pages[str(page.id)] = {"status": "visible", "page": _linked_page(page)}
        missing = [i for i in page_ids if pages[str(i)]["status"] == "hidden"]
        if missing:
            # A deleted page is reported as removed only when its board is still one the caller reaches.
            deleted = Page.all_objects.filter(
                pk__in=missing, workspace__slug=slug, deleted_at__isnull=False, access=Page.PUBLIC_ACCESS
            ).filter(member_or_shared_projects_q(user, slug=slug, prefix="projects"))
            for page_id in deleted.values_list("id", flat=True).distinct():
                pages[str(page_id)] = dict(REMOVED)
    if project_ids:
        visible = Project.objects.filter(
            workspace__slug=slug, pk__in=project_ids, id__in=visible_project_ids(user, slug=slug)
        )
        for project in visible:
            projects[str(project.id)] = {"status": "visible", "project": _linked_project(project)}
    return {"pages": pages, "projects": projects}


def search(user, slug, text="", limit=20):
    """Pages and boards ``user`` may link to, by name (boards also by identifier)."""
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 20
    text = " ".join(str(text or "").split())[:200]
    user = _real_user(user)
    if user is None:
        return {"pages": [], "projects": []}
    pages = reachable_pages(user, slug)
    projects = Project.objects.filter(workspace__slug=slug, id__in=visible_project_ids(user, slug=slug))
    if text:
        pages = pages.filter(name__icontains=text)
        projects = projects.filter(Q(name__icontains=text) | Q(identifier__icontains=text))
    return {
        "pages": [_linked_page(page) for page in pages.order_by("-updated_at")[:limit]],
        "projects": [_linked_project(project) for project in projects.order_by("name")[:limit]],
    }
