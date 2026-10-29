# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Custom fields: per-project field definitions and per-work-item values.

A ``CustomField`` row defines one field on a project (board). A
``CustomFieldValue`` row holds the value of one field on one work item.

The canonical value lives in ``CustomFieldValue.value`` (JSON, the shape the API
returns). The typed ``value_*`` columns are derived from it on save so the
database can filter and sort fast. Never write the typed columns directly; use
``plane.utils.custom_fields.set_values``.
"""

# Django imports
from django.db import models
from django.db.models import Q

# Module imports
from .project import ProjectBaseModel


class CustomField(ProjectBaseModel):
    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        LONG_TEXT = "long_text", "Long text"
        NUMBER = "number", "Number"
        MONEY = "money", "Money"
        DATE = "date", "Date"
        CHECKBOX = "checkbox", "Checkbox"
        SELECT = "select", "Dropdown"
        MULTI_SELECT = "multi_select", "Multi-select"
        LABEL = "label", "Label"
        PERSON = "person", "Person"
        URL = "url", "Link"
        FORMULA = "formula", "Formula"

    # Types whose value is a list of option ids or user ids.
    MULTI_VALUE_TYPES = {FieldType.MULTI_SELECT, FieldType.LABEL, FieldType.PERSON}
    # Types that carry an option list in ``options``.
    OPTION_TYPES = {FieldType.SELECT, FieldType.MULTI_SELECT, FieldType.LABEL}
    # What a formula's result is stored and shown as (settings["result_type"]).
    FORMULA_RESULT_TYPES = {"number", "money", "text", "date", "checkbox"}
    # Relation and rollup (plane.relations): worked out per viewer from linked cards, never
    # stored in CustomFieldValue. Kept out of FieldType.choices on purpose so they need no db
    # migration (choices are not enforced by the database); CustomFieldSerializer accepts them.
    RELATION = "relation"
    ROLLUP = "rollup"
    LINKED_TYPES = {RELATION, ROLLUP}
    # Created time, last edited time, created by, last edited by: read from the card itself, never
    # stored in CustomFieldValue, never written by a client. Same reason as above for staying out of
    # FieldType.choices (no db migration).
    CREATED_TIME = "created_time"
    LAST_EDITED_TIME = "last_edited_time"
    CREATED_BY = "created_by"
    LAST_EDITED_BY = "last_edited_by"
    AUDIT_TYPES = {CREATED_TIME, LAST_EDITED_TIME, CREATED_BY, LAST_EDITED_BY}
    # Percent, phone, email and status are stored as the number, text and dropdown types with
    # ``settings["format"]`` set, so filters, sort, rollups and the API treat them like their base
    # type. The field API also accepts the short names below and turns them into base type + format.
    TYPE_ALIASES = {
        "percent": ("number", "percent"),
        "phone": ("text", "phone"),
        "email": ("text", "email"),
        "status": ("select", "status"),
    }
    FORMATS_BY_TYPE = {"number": {"percent"}, "text": {"phone", "email"}, "select": {"status"}}
    # Status options sit in one of these groups, in the order work moves.
    STATUS_GROUPS = ("todo", "in_progress", "complete")
    ALL_TYPE_CHOICES = [
        *FieldType.choices,
        (RELATION, "Relation"),
        (ROLLUP, "Rollup"),
        (CREATED_TIME, "Created time"),
        (LAST_EDITED_TIME, "Last edited time"),
        (CREATED_BY, "Created by"),
        (LAST_EDITED_BY, "Last edited by"),
        ("percent", "Percent"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("status", "Status"),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    field_type = models.CharField(max_length=32, choices=FieldType.choices)
    # Choices for select / multi_select / label: [{"id", "name", "color"}]
    options = models.JSONField(default=list, blank=True)
    # Per-type settings, for example {"include_time": true} for dates,
    # {"multiple": true} for people, {"decimals": 2} for numbers,
    # {"expression": "...", "result_type": "money"} for formulas,
    # {"target_project_id", "two_way", "mirror_field_id", "is_mirror"} for relations,
    # {"relation_field_id", "target_field_id", "function", "result_type"} for rollups.
    settings = models.JSONField(default=dict, blank=True)
    sort_order = models.FloatField(default=65535)
    archived_at = models.DateTimeField(null=True, blank=True)
    external_source = models.CharField(max_length=255, null=True, blank=True)
    external_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Custom Field"
        verbose_name_plural = "Custom Fields"
        db_table = "custom_fields"
        ordering = ("sort_order", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(deleted_at__isnull=True),
                name="custom_field_unique_project_name_when_not_deleted",
            )
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.sort_order == 65535:
            largest = CustomField.objects.filter(project_id=self.project_id).aggregate(
                largest=models.Max("sort_order")
            )["largest"]
            if largest is not None:
                self.sort_order = largest + 10000
        super().save(*args, **kwargs)

    @property
    def is_multi(self):
        return self.field_type in self.MULTI_VALUE_TYPES

    def __str__(self):
        return f"{self.name} ({self.field_type})"


class CustomFieldValue(ProjectBaseModel):
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="custom_field_values")
    field = models.ForeignKey(CustomField, on_delete=models.CASCADE, related_name="values")
    # Canonical value, in API shape.
    value = models.JSONField(null=True, blank=True)
    # Derived columns for filter and sort.
    value_text = models.TextField(null=True, blank=True)
    value_number = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)

    class Meta:
        verbose_name = "Custom Field Value"
        verbose_name_plural = "Custom Field Values"
        db_table = "custom_field_values"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "field"],
                condition=Q(deleted_at__isnull=True),
                name="custom_field_value_unique_issue_field_when_not_deleted",
            )
        ]
        indexes = [
            models.Index(fields=["field", "value_number"], name="cfv_field_number_idx"),
            models.Index(fields=["field", "value_date"], name="cfv_field_date_idx"),
            models.Index(fields=["field", "value_datetime"], name="cfv_field_datetime_idx"),
        ]

    def __str__(self):
        return f"{self.issue_id} - {self.field_id}"
