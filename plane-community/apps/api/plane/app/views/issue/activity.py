# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from itertools import chain

# Django imports
from django.db.models import Prefetch, Q
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page

# Third Party imports
from rest_framework.response import Response
from rest_framework import status

# Module imports
from .. import BaseAPIView
from plane.app.serializers import IssueActivitySerializer, IssueCommentSerializer
from plane.app.permissions import ProjectEntityPermission, allow_permission, ROLE
from plane.db.models import IssueActivity, IssueComment, CommentReaction, IntakeIssue
from plane.sharing.visibility import visible_issues
from plane.one_unit.reach import unreachable_issue_ids


class IssueActivityEndpoint(BaseAPIView):
    permission_classes = [ProjectEntityPermission]
    use_read_replica = True

    @method_decorator(gzip_page)
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        filters = {}
        if request.GET.get("created_at__gt", None) is not None:
            filters = {"created_at__gt": request.GET.get("created_at__gt")}

        issue_activities = (
            IssueActivity.objects.filter(issue_id=issue_id)
            .filter(
                ~Q(field__in=["comment", "vote", "reaction", "draft"]),
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
                workspace__slug=slug,
            )
            .filter(**filters)
            .select_related("actor", "workspace", "issue", "project")
        ).order_by("created_at")
        # Drop entries that name a hidden work item (parent and relation changes).
        issue_activities = visible_issues(issue_activities, request.user, field="old_identifier")
        issue_activities = visible_issues(issue_activities, request.user, field="new_identifier")
        # A parent may sit in another project: drop parent changes that name a card the user cannot reach.
        named = set()
        for old_id, new_id in issue_activities.filter(field="parent").values_list("old_identifier", "new_identifier"):
            named.update(str(i) for i in (old_id, new_id) if i)
        unreachable = unreachable_issue_ids(request.user, named)
        if unreachable:
            issue_activities = issue_activities.exclude(
                Q(field="parent") & (Q(old_identifier__in=unreachable) | Q(new_identifier__in=unreachable))
            )
        issue_comments = (
            IssueComment.objects.filter(issue_id=issue_id)
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
                workspace__slug=slug,
            )
            .filter(**filters)
            .order_by("created_at")
            .select_related("actor", "issue", "project", "workspace")
            .prefetch_related(
                Prefetch(
                    "comment_reactions",
                    queryset=CommentReaction.objects.select_related("actor"),
                )
            )
        )

        if request.GET.get("activity_type", None) == "issue-property":
            issue_activities = issue_activities.prefetch_related(
                Prefetch(
                    "issue__issue_intake",
                    queryset=IntakeIssue.objects.only("source_email", "source", "extra"),
                    to_attr="source_data",
                )
            )
            issue_activities = IssueActivitySerializer(issue_activities, many=True).data
            return Response(issue_activities, status=status.HTTP_200_OK)

        if request.GET.get("activity_type", None) == "issue-comment":
            issue_comments = IssueCommentSerializer(issue_comments, many=True).data
            return Response(issue_comments, status=status.HTTP_200_OK)

        result_list = sorted(
            chain(issue_activities, issue_comments),
            key=lambda instance: instance["created_at"],
        )

        return Response(result_list, status=status.HTTP_200_OK)
