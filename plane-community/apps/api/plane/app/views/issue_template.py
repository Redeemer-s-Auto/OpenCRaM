# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Card templates for a project (board). Any member of the board can manage and use them."""

# Django imports
from django.db import IntegrityError

# Third party imports
from rest_framework import serializers, status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers.base import BaseSerializer
from plane.db.models import Issue, IssueTemplate, Project
from plane.utils.issue_templates import (
    clean_template_data,
    create_from_template,
    new_template_name,
    snapshot_issue,
)

from .base import BaseAPIView


def _visible_filter(request):
    """The sharing filter, when the sharing-rules app is installed. Otherwise no extra filter."""
    try:
        from plane.sharing.visibility import visible_issues  # noqa: WPS433
    except ImportError:  # pragma: no cover - only on branches without sharing rules
        return None
    return lambda queryset: visible_issues(queryset, request.user)


class IssueTemplateSerializer(BaseSerializer):
    class Meta:
        model = IssueTemplate
        fields = [
            "id",
            "name",
            "description",
            "data",
            "sort_order",
            "project",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = ["id", "project", "created_at", "updated_at", "created_by"]

    def validate_name(self, value):
        value = " ".join(str(value).split())
        if not value:
            raise serializers.ValidationError("A template needs a name.")
        project_id = self.context.get("project_id") or (self.instance and self.instance.project_id)
        clash = IssueTemplate.objects.filter(project_id=project_id, name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("This board already has a template with this name.")
        return value

    def validate_data(self, value):
        project_id = self.context.get("project_id") or (self.instance and self.instance.project_id)
        return clean_template_data(project_id, value)


def _templates(slug, project_id):
    return IssueTemplate.objects.filter(workspace__slug=slug, project_id=project_id)


MEMBERS = [ROLE.ADMIN, ROLE.MEMBER]


class IssueTemplateEndpoint(BaseAPIView):
    @allow_permission(MEMBERS)
    def get(self, request, slug, project_id):
        return Response(IssueTemplateSerializer(_templates(slug, project_id), many=True).data)

    @allow_permission(MEMBERS)
    def post(self, request, slug, project_id):
        serializer = IssueTemplateSerializer(data=request.data, context={"project_id": project_id})
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save(project_id=project_id)
        except IntegrityError:
            return Response({"error": "This board already has a template with this name."}, status=400)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IssueTemplateDetailEndpoint(BaseAPIView):
    @allow_permission(MEMBERS)
    def get(self, request, slug, project_id, pk):
        template = _templates(slug, project_id).filter(pk=pk).first()
        if template is None:
            return Response({"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(IssueTemplateSerializer(template).data)

    @allow_permission(MEMBERS)
    def patch(self, request, slug, project_id, pk):
        template = _templates(slug, project_id).filter(pk=pk).first()
        if template is None:
            return Response({"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = IssueTemplateSerializer(
            template, data=request.data, partial=True, context={"project_id": project_id}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @allow_permission(MEMBERS)
    def delete(self, request, slug, project_id, pk):
        template = _templates(slug, project_id).filter(pk=pk).first()
        if template is None:
            return Response({"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND)
        template.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueTemplateUseEndpoint(BaseAPIView):
    """POST {"name": optional title} -> creates the card (and sub-cards) through the normal create path."""

    @allow_permission(MEMBERS)
    def post(self, request, slug, project_id, pk):
        template = _templates(slug, project_id).filter(pk=pk).first()
        if template is None:
            return Response({"error": "Template not found."}, status=status.HTTP_404_NOT_FOUND)
        project = Project.objects.select_related("workspace").get(pk=project_id)
        issue, count = create_from_template(request, project, template, (request.data or {}).get("name"))
        return Response(
            {
                "id": str(issue.id),
                "project_id": str(issue.project_id),
                "sequence_id": issue.sequence_id,
                "name": issue.name,
                "created_count": count,
            },
            status=status.HTTP_201_CREATED,
        )


class IssueSaveAsTemplateEndpoint(BaseAPIView):
    """POST {"name", "include_sub_items": bool} -> a new template copied from this card."""

    @allow_permission(MEMBERS)
    def post(self, request, slug, project_id, issue_id):
        issue = Issue.issue_objects.filter(pk=issue_id, project_id=project_id, workspace__slug=slug)
        visible = _visible_filter(request)
        if visible is not None:
            issue = visible(issue)
        issue = issue.first()
        if issue is None:
            return Response({"error": "Card not found."}, status=status.HTTP_404_NOT_FOUND)
        body = request.data or {}
        data = snapshot_issue(issue, include_sub_items=bool(body.get("include_sub_items", True)), visible=visible)
        name = body.get("name") or new_template_name(project_id, issue.name)
        serializer = IssueTemplateSerializer(
            data={"name": name, "description": body.get("description", ""), "data": data},
            context={"project_id": project_id},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(project_id=project_id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
