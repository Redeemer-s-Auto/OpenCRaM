# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Every URL that names one work item or page must pass through the guard.

The guard runs in the ``initial`` hook of the three base view families. A view
that names an item but does not inherit one of them would skip it, so this test
walks the whole URL map and fails on any such view.
"""

import re

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from plane.sharing.guard import ISSUE_KWARGS, PAGE_KWARGS, enforce_item_access  # noqa: F401

ITEM_ROUTE = re.compile(r"<uuid:(?:issue_id|work_item_id|page_id)>|issues/<uuid:pk>|work-items/<uuid:pk>|pages/<uuid:pk>|<str:issue_identifier>")


def _walk(patterns, prefix=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from _walk(entry.url_patterns, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), entry.callback


def _view_class(callback):
    return getattr(callback, "cls", None) or getattr(callback, "view_class", None)


def _is_guarded(cls):
    from plane.api.views.base import TimezoneMixin as ApiMixin
    from plane.app.views.base import TimezoneMixin as AppMixin
    from plane.space.views.base import TimezoneMixin as SpaceMixin

    return issubclass(cls, (AppMixin, ApiMixin, SpaceMixin))


def test_every_item_route_is_guarded():
    unguarded = []
    checked = 0
    for route, callback in _walk(get_resolver().url_patterns):
        if not ITEM_ROUTE.search(route):
            continue
        cls = _view_class(callback)
        checked += 1
        if cls is None or not _is_guarded(cls):
            unguarded.append(f"{route} -> {getattr(cls, '__name__', callback)}")
    assert checked > 50, f"URL walk found only {checked} item routes; the pattern is probably wrong"
    assert unguarded == [], "Views that name an item but skip the sharing guard:\n" + "\n".join(unguarded)


@pytest.mark.parametrize(
    "path",
    [
        "/api/workspaces/ws/projects/p/issues/0b6a1c3e-1111-4a1a-9a1a-111111111111/",
        "/api/v1/workspaces/ws/projects/p/work-items/0b6a1c3e-1111-4a1a-9a1a-111111111111/comments/",
        "/api/workspaces/ws/projects/p/intake-issues/0b6a1c3e-1111-4a1a-9a1a-111111111111/",
    ],
)
def test_issue_path_pattern(path):
    from plane.sharing.guard import ISSUE_PATH

    assert ISSUE_PATH.search(path)


def test_draft_issue_path_is_not_an_issue():
    from plane.sharing.guard import ISSUE_PATH

    assert not ISSUE_PATH.search("/api/workspaces/ws/draft-issues/0b6a1c3e-1111-4a1a-9a1a-111111111111/")
