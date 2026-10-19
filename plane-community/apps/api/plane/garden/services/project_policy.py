# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os

from plane.db.models import Project, ProjectNetwork


def garden_mode_enabled() -> bool:
    return os.environ.get("GARDEN_AUTH_ENABLED", "0") == "1"


def garden_workspace_slug() -> str:
    return os.environ.get("GARDEN_WORKSPACE_SLUG", "the-garden").strip() or "the-garden"


def local_project_membership() -> bool:
    """Whether Work admins manage project (board) membership inside Work.

    True in roles mode (GARDEN_ACCESS_MODE=roles), where Firebase carries no
    per-project mapping. In the default projection mode Firebase owns project
    membership and this stays False.
    """
    return os.environ.get("GARDEN_ACCESS_MODE", "projection").strip().lower() == "roles"


def is_garden_workspace(slug: str | None) -> bool:
    return garden_mode_enabled() and bool(slug) and slug == garden_workspace_slug()


def harden_garden_workspace_projects(workspace_or_slug) -> int:
    """Force every project in the managed Garden workspace to SECRET.

    Garden access is projected by department membership. A PUBLIC Plane project
    would create a second authorization path, so Garden mode never permits it.
    This is intentionally idempotent and can run on sign-in and request entry.
    """

    slug = getattr(workspace_or_slug, "slug", workspace_or_slug)
    if not is_garden_workspace(slug):
        return 0
    return (
        Project.objects.filter(workspace__slug=slug, deleted_at__isnull=True)
        .exclude(network=ProjectNetwork.SECRET.value)
        .update(network=ProjectNetwork.SECRET.value)
    )


def guest_role_supports_broad_read_only(project: Project) -> bool:
    """Return whether Plane Guest (5) can see the full project work-item set.

    Upstream Plane restricts guests to work they created unless
    guest_view_all_features is enabled. Batch 11 therefore must not treat Guest
    as a generic read-only department mapping unless this predicate is true.
    """

    return bool(project.guest_view_all_features)
