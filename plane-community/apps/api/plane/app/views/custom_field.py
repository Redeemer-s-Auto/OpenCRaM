# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import transaction
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import CustomFieldSerializer
from plane.db.models import CustomField, CustomFieldValue
from plane.utils.custom_fields import recompute_project_formulas, refresh_display_text
from plane.utils.formula import rename_prop

from .base import BaseAPIView


def _field_queryset(slug, project_id):
    return CustomField.objects.filter(workspace__slug=slug, project_id=project_id)


def _rename_in_formulas(project_id, old_name, new_name):
    """Keep formulas working when a field they use is renamed (like Notion does)."""
    formulas = CustomField.objects.filter(project_id=project_id, field_type=CustomField.FieldType.FORMULA)
    for formula_field in formulas:
        expression = (formula_field.settings or {}).get("expression", "")
        rewritten = rename_prop(expression, old_name, new_name)
        if rewritten != expression:
            formula_field.settings = {**formula_field.settings, "expression": rewritten}
            formula_field.save(update_fields=["settings", "updated_at"])


class CustomFieldEndpoint(BaseAPIView):
    """List and create the custom fields of a project."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        fields = _field_queryset(slug, project_id)
        if request.GET.get("archived") == "true":
            fields = fields.filter(archived_at__isnull=False)
        elif request.GET.get("archived") != "all":
            fields = fields.filter(archived_at__isnull=True)
        return Response(CustomFieldSerializer(fields.order_by("sort_order", "created_at"), many=True).data)

    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id):
        serializer = CustomFieldSerializer(data=request.data, context={"project_id": project_id})
        serializer.is_valid(raise_exception=True)
        serializer.save(project_id=project_id)
        recompute_project_formulas(project_id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CustomFieldDetailEndpoint(BaseAPIView):
    """Read, edit, or delete one custom field.

    DELETE removes the field and every value in it. The body must repeat the
    field name as ``{"confirm_name": "<name>"}``. To keep values, archive instead.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, pk):
        field = _field_queryset(slug, project_id).filter(pk=pk).first()
        if field is None:
            return Response({"error": "Field not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CustomFieldSerializer(field).data)

    @allow_permission([ROLE.ADMIN])
    def patch(self, request, slug, project_id, pk):
        field = _field_queryset(slug, project_id).filter(pk=pk).first()
        if field is None:
            return Response({"error": "Field not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CustomFieldSerializer(field, data=request.data, partial=True, context={"project_id": project_id})
        serializer.is_valid(raise_exception=True)
        old_name = field.name
        with transaction.atomic():
            field = serializer.save()
            if "options" in request.data:
                refresh_display_text(field)
            if field.name != old_name:
                _rename_in_formulas(project_id, old_name, field.name)
        recompute_project_formulas(project_id)
        return Response(CustomFieldSerializer(field).data)

    @allow_permission([ROLE.ADMIN])
    def delete(self, request, slug, project_id, pk):
        field = _field_queryset(slug, project_id).filter(pk=pk).first()
        if field is None:
            return Response({"error": "Field not found."}, status=status.HTTP_404_NOT_FOUND)
        if (request.data or {}).get("confirm_name") != field.name:
            return Response(
                {
                    "error": "Deleting a field deletes every value in it. "
                    "Send confirm_name with the exact field name, or archive the field instead.",
                    "code": "confirm_name_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            CustomFieldValue.all_objects.filter(field_id=field.id).delete()
            CustomField.all_objects.filter(pk=field.id).delete()
        recompute_project_formulas(project_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomFieldArchiveEndpoint(BaseAPIView):
    """POST archives a field (values kept, hidden everywhere). DELETE restores it."""

    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id, pk):
        field = _field_queryset(slug, project_id).filter(pk=pk).first()
        if field is None:
            return Response({"error": "Field not found."}, status=status.HTTP_404_NOT_FOUND)
        if field.archived_at is None:
            field.archived_at = timezone.now()
            field.save(update_fields=["archived_at", "updated_at"])
        recompute_project_formulas(project_id)
        return Response(CustomFieldSerializer(field).data)

    @allow_permission([ROLE.ADMIN])
    def delete(self, request, slug, project_id, pk):
        field = _field_queryset(slug, project_id).filter(pk=pk).first()
        if field is None:
            return Response({"error": "Field not found."}, status=status.HTTP_404_NOT_FOUND)
        field.archived_at = None
        field.save(update_fields=["archived_at", "updated_at"])
        recompute_project_formulas(project_id)
        return Response(CustomFieldSerializer(field).data)


class CustomFieldReorderEndpoint(BaseAPIView):
    """POST ``{"field_ids": [...]}`` sets the field order to the list order."""

    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id):
        field_ids = (request.data or {}).get("field_ids")
        if not isinstance(field_ids, list) or not field_ids:
            return Response({"error": "field_ids must be a list of field ids."}, status=status.HTTP_400_BAD_REQUEST)
        fields = {str(f.id): f for f in _field_queryset(slug, project_id).filter(pk__in=field_ids)}
        if len(fields) != len(set(map(str, field_ids))):
            return Response(
                {"error": "Every id must be a field of this project, listed once."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ordered = []
        for position, field_id in enumerate(field_ids):
            field = fields[str(field_id)]
            field.sort_order = (position + 1) * 10000
            ordered.append(field)
        CustomField.objects.bulk_update(ordered, ["sort_order"])
        all_fields = _field_queryset(slug, project_id).filter(archived_at__isnull=True).order_by("sort_order")
        return Response(CustomFieldSerializer(all_fields, many=True).data)
