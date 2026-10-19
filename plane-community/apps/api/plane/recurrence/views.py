# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Read, set and stop a work item's repeat rule.

The path names the work item, so the sharing guard runs first: a card the
person cannot see answers 404, and changing the rule needs "Can edit".
"""

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue
from plane.recurrence.models import RepeatRule
from plane.recurrence.services import describe_copy_of, describe_rule, save_rule, stop_rule
from plane.sharing.visibility import can_view_issue, visible_issues


class IssueRepeatEndpoint(BaseAPIView):
    def _issue(self, slug, project_id, issue_id):
        return Issue.issue_objects.filter(workspace__slug=slug, project_id=project_id, pk=issue_id).first()

    def _payload(self, request, issue):
        rule = RepeatRule.objects.filter(issue=issue).select_related("created_by").first()
        visible_ids = None
        if rule is not None:
            visible_ids = visible_issues(Issue.issue_objects.filter(project_id=issue.project_id), request.user).values(
                "id"
            )
        return {
            "rule": describe_rule(rule, visible_ids) if rule else None,
            "copy_of": describe_copy_of(issue, lambda issue_id: can_view_issue(request.user, issue_id)),
        }

    # Guests are left out: Plane may limit them to their own cards, and a rule
    # lists recent copies.
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id, issue_id):
        issue = self._issue(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Work item not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self._payload(request, issue))

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def put(self, request, slug, project_id, issue_id):
        issue = self._issue(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Work item not found."}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            save_rule(issue, request.data, request.user)
        return Response(self._payload(request, issue))

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def delete(self, request, slug, project_id, issue_id):
        issue = self._issue(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Work item not found."}, status=status.HTTP_404_NOT_FOUND)
        rule = RepeatRule.objects.filter(issue=issue).first()
        if rule is not None and rule.is_active:
            stop_rule(rule, request.user, reason="Stopped by hand.")
        return Response(self._payload(request, issue))


class ProjectRepeatRulesEndpoint(BaseAPIView):
    """Ids of the cards in a project that repeat (for the small repeat icon on cards)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        rules = RepeatRule.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            is_active=True,
            issue__deleted_at__isnull=True,
        )
        rules = visible_issues(rules, request.user, field="issue_id")
        return Response(
            [
                {"issue_id": str(issue_id), "next_run_at": next_run_at.isoformat() if next_run_at else None}
                for issue_id, next_run_at in rules.values_list("issue_id", "next_run_at")
            ]
        )
