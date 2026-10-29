# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Endpoints for "Link to card" blocks, shortcut cards and "Linked from".

Every answer is worked out for the caller (``plane.shortcuts.service``); a card the
caller cannot see is ``{"status": "hidden"}`` or is left out.
"""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Project

from . import service
from .visibility import linkable_cards, viewable_cards


def _not_found():
    return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


def _visible_card(request, slug, issue_id):
    issue_id = service.as_uuid(issue_id)
    if not issue_id:
        return None
    # Drafts and intake cards are never link targets (and reach_q does not know draft ownership).
    return viewable_cards(request.user, linkable_cards().filter(workspace__slug=slug, pk=issue_id)).first()


class CardLinkResolveEndpoint(BaseAPIView):
    """POST ``{"ids": [...]}`` -> ``{"results": {id: {"status": "visible"|"hidden"|"removed", "card"?}}}``."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug):
        ids = request.data.get("ids") if isinstance(request.data, dict) else None
        if not isinstance(ids, list):
            return Response({"error": "ids must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"results": service.resolve(request.user, slug, ids)}, status=status.HTTP_200_OK)


class CardLinkSearchEndpoint(BaseAPIView):
    """GET ``?search=&limit=`` - cards the caller may link to (name, or ``ABC-12``)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        results = service.search(request.user, slug, request.query_params.get("search", ""),
                                 request.query_params.get("limit", 20))
        return Response({"results": results}, status=status.HTTP_200_OK)


class CardBacklinksEndpoint(BaseAPIView):
    """GET - the cards the caller may see that link to this card ("Linked from")."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, issue_id):
        if _visible_card(request, slug, issue_id) is None:
            return _not_found()
        return Response({"results": service.backlinks(request.user, slug, issue_id)}, status=status.HTTP_200_OK)


class CardShortcutInfoEndpoint(BaseAPIView):
    """GET - is this card a shortcut, and where does it go (for the caller)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, issue_id):
        card = _visible_card(request, slug, issue_id)
        if card is None:
            return _not_found()
        info = service.shortcuts_for_cards(request.user, slug, [card.id])
        target = info.get(str(card.id))
        return Response({"is_shortcut": target is not None, "target": target}, status=status.HTTP_200_OK)


class ProjectShortcutsEndpoint(BaseAPIView):
    """GET - shortcut cards on this board with their targets; POST ``{"target_id"}`` - add one."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        return Response(
            {"results": service.project_shortcuts(request.user, slug, project_id)}, status=status.HTTP_200_OK
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id):
        project = Project.objects.filter(workspace__slug=slug, pk=project_id).select_related("workspace").first()
        if project is None:
            return _not_found()
        data = request.data if isinstance(request.data, dict) else {}
        try:
            issue = service.create_shortcut(request.user, project, data.get("target_id"), data.get("parent_id"))
        except service.ShortcutError as error:
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        _created_jobs(request, project, issue)
        target = service.shortcuts_for_cards(request.user, slug, [issue.id]).get(str(issue.id))
        return Response(
            {
                "id": str(issue.id),
                "project_id": str(issue.project_id),
                "sequence_id": issue.sequence_id,
                "name": issue.name,
                "target": target,
            },
            status=status.HTTP_201_CREATED,
        )


def _created_jobs(request, project, issue):
    """The same activity and webhook work as the "new card" screen. Payload: the neutral name only."""
    from plane.bgtasks.issue_activities_task import issue_activity
    from plane.bgtasks.webhook_task import model_activity
    from plane.utils.host import base_host

    payload = {"name": issue.name}
    origin = base_host(request=request, is_app=True)
    issue_activity.delay(
        type="issue.activity.created",
        requested_data=json.dumps(payload, cls=DjangoJSONEncoder),
        actor_id=str(request.user.id),
        issue_id=str(issue.id),
        project_id=str(project.id),
        current_instance=None,
        epoch=int(timezone.now().timestamp()),
        notification=True,
        origin=origin,
    )
    model_activity.delay(
        model_name="issue",
        model_id=str(issue.id),
        requested_data=payload,
        current_instance=None,
        actor_id=request.user.id,
        slug=project.workspace.slug,
        origin=origin,
    )
