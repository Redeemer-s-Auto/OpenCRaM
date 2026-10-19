# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Request guard for every endpoint that names one work item or page.

Called from the ``initial`` hook of the app, public API and space base views,
after authentication. A hidden item answers 404 (its existence is not
revealed). A visible item that the user may not change answers 403.
"""

import re

from rest_framework.exceptions import NotFound, PermissionDenied

from plane.db.models import Issue
from plane.sharing.models import AccessLevel
from plane.sharing.visibility import can_reach, issue_access_level, page_access_level

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
# Path segments whose next segment is a work item id.
ISSUE_PATH = re.compile(rf"/(?:issues|work-items|intake-issues|inbox-issues|intake-work-items)/({UUID})(?:/|$)")
PAGE_PATH = re.compile(rf"/pages/({UUID})(?:/|$)")
# Writes on these sub-resources need only "Can comment".
COMMENT_PATH = re.compile(r"/(?:comments|reactions|comment-reactions|votes)(?:/|$)")
# Writes on these sub-resources need only "Can view" (they change nothing others see).
VIEW_WRITE_PATH = re.compile(r"/(?:subscribe|subscribers|mark-read|favorite|favorite-pages|recent-visit)(?:/|$)")

ISSUE_KWARGS = ("issue_id", "work_item_id")
PAGE_KWARGS = ("page_id",)


def _required_level(request):
    if request.method in SAFE_METHODS:
        return AccessLevel.VIEW
    path = request.path_info
    if VIEW_WRITE_PATH.search(path):
        return AccessLevel.VIEW
    if COMMENT_PATH.search(path):
        return AccessLevel.COMMENT
    return AccessLevel.EDIT


def _issue_ids(request, kwargs):
    ids = {str(kwargs[key]) for key in ISSUE_KWARGS if kwargs.get(key)}
    ids.update(match.group(1) for match in ISSUE_PATH.finditer(request.path_info))
    identifier = kwargs.get("issue_identifier")
    project_identifier = kwargs.get("project_identifier")
    if identifier and project_identifier and str(identifier).isdigit():
        issue_id = (
            Issue.all_objects.filter(
                workspace__slug=kwargs.get("slug"),
                project__identifier__iexact=project_identifier,
                sequence_id=int(identifier),
            )
            .values_list("id", flat=True)
            .first()
        )
        if issue_id:
            ids.add(str(issue_id))
    return ids


def _page_ids(request, kwargs):
    ids = {str(kwargs[key]) for key in PAGE_KWARGS if kwargs.get(key)}
    ids.update(match.group(1) for match in PAGE_PATH.finditer(request.path_info))
    return ids


def _check(level, required):
    if level is None:
        return
    if level <= 0:
        raise NotFound("The required object does not exist.")
    if not can_reach(level, required):
        raise PermissionDenied("You don't have the required permissions.")


def enforce_item_access(request, kwargs):
    user = getattr(request, "user", None)
    required = _required_level(request)
    for issue_id in _issue_ids(request, kwargs):
        _check(issue_access_level(user, issue_id), required)
    for page_id in _page_ids(request, kwargs):
        _check(page_access_level(user, page_id), required)
