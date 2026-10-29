# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView

from .service import (
    editable_issue,
    move_mention,
    own_reminder,
    payload,
    reminders_for,
    set_reminder,
    visible_issue,
)

NO_ACCESS = {"error": "no_access"}


class ReminderListEndpoint(BaseAPIView):
    """GET ``?issue_id=`` - the caller's own reminders on one card."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        issue = visible_issue(request.user, slug, request.GET.get("issue_id"))
        if issue is None:
            return Response(NO_ACCESS, status=status.HTTP_403_FORBIDDEN)
        return Response([payload(row) for row in reminders_for(request.user, issue)])


class ReminderEndpoint(BaseAPIView):
    """PUT - set the caller's reminder on one date mention. DELETE - remove it.

    PUT body: ``issue_id``, ``date`` (YYYY-MM-DD), ``time`` (HH:MM or empty), ``tz`` (zone name),
    ``offset_minutes`` (how long before the event; 0 = at the event).
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def put(self, request, slug, mention_id):
        issue = visible_issue(request.user, slug, request.data.get("issue_id"))
        if issue is None:
            return Response(NO_ACCESS, status=status.HTTP_403_FORBIDDEN)
        existing = own_reminder(request.user, mention_id)
        if existing is not None and existing.issue_id != issue.id:
            # A mention id belongs to the card it was made on.
            return Response({"error": "That date belongs to another card."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload(set_reminder(request.user, issue, mention_id, request.data)))

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def delete(self, request, slug, mention_id):
        row = own_reminder(request.user, mention_id)
        if row is not None and row.workspace.slug == slug:
            row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReminderMoveEndpoint(BaseAPIView):
    """POST - the date or time in a mention changed: move everyone's pending reminders on it.

    Body: ``issue_id``, ``date``, ``time``, ``tz``. Needs edit access to the card, because it
    changes other people's reminders. Reminders already sent are left alone.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug, mention_id):
        issue = editable_issue(request.user, slug, request.data.get("issue_id"))
        if issue is None:
            return Response(NO_ACCESS, status=status.HTTP_403_FORBIDDEN)
        return Response({"moved": move_mention(issue, mention_id, request.data)})
