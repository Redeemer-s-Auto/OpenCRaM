# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Module imports
from plane.db.models import CustomField
from plane.utils.custom_fields import clean_options, clean_settings

from .base import BaseSerializer


class CustomFieldSerializer(BaseSerializer):
    """Definition of one custom field on a project.

    ``field_type`` is fixed after create: changing it would make stored values
    meaningless. Make a new field instead.
    """

    class Meta:
        model = CustomField
        fields = [
            "id",
            "name",
            "description",
            "field_type",
            "options",
            "settings",
            "sort_order",
            "archived_at",
            "project",
            "workspace",
            "external_source",
            "external_id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = [
            "id",
            "archived_at",
            "project",
            "workspace",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

    def validate_name(self, value):
        value = " ".join(str(value).split())
        if not value:
            raise serializers.ValidationError("A field needs a name.")
        project_id = self.context.get("project_id") or (self.instance and self.instance.project_id)
        clash = CustomField.objects.filter(project_id=project_id, name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("This project already has a field with this name.")
        return value

    def validate(self, attrs):
        if self.instance is not None and "field_type" in attrs and attrs["field_type"] != self.instance.field_type:
            raise serializers.ValidationError({"field_type": "The type of a field cannot change after it is made."})
        field_type = attrs.get("field_type") or (self.instance and self.instance.field_type)
        if not field_type:
            raise serializers.ValidationError({"field_type": "A field needs a type."})
        if "options" in attrs or self.instance is None:
            existing = self.instance.options if self.instance is not None else None
            attrs["options"] = clean_options(field_type, attrs.get("options"), existing)
        if "settings" in attrs or self.instance is None:
            attrs["settings"] = clean_settings(field_type, attrs.get("settings"))
        return attrs
