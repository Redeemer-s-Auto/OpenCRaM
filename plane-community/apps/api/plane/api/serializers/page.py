# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Serializers for the public (API key) pages endpoints.

The collaborative editor keeps a page's content in ``description_binary`` (a Yjs
document). The API only reads and writes ``description_html``. Whenever the API
writes the HTML it clears the binary, and the live server rebuilds the binary from
the HTML the next time somebody opens the page - the same thing the app does when
it duplicates a page.
"""

# Third party imports
from rest_framework import serializers

# Module imports
from plane.db.models import Page
from plane.utils.content_validator import validate_html_content

from .base import BaseSerializer


def clean_page_html(value):
    """Sanitize page HTML the same way the app's page description endpoint does."""
    if value is None:
        return value
    if not value.strip():
        return "<p></p>"
    is_valid, error_message, sanitized_html = validate_html_content(value)
    if not is_valid:
        raise serializers.ValidationError(error_message or "html content is not valid")
    return sanitized_html if sanitized_html is not None else value


class PageAPISerializer(BaseSerializer):
    """A project page as returned by the public API (without its content)."""

    class Meta:
        model = Page
        fields = [
            "id",
            "name",
            "owned_by",
            "access",
            "color",
            "parent",
            "is_locked",
            "archived_at",
            "logo_props",
            "view_props",
            "sort_order",
            "external_id",
            "external_source",
            "workspace",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields


class PageDetailAPISerializer(PageAPISerializer):
    """A project page with its HTML content."""

    class Meta(PageAPISerializer.Meta):
        fields = PageAPISerializer.Meta.fields + ["description_html"]
        read_only_fields = fields


class _PageWriteMixin:
    def validate_description_html(self, value):
        return clean_page_html(value)

    def validate_logo_props(self, value):
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError("logo_props must be an object")
        return value

    def validate_view_props(self, value):
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError("view_props must be an object")
        return value


class PageCreateAPISerializer(_PageWriteMixin, BaseSerializer):
    """Request body for creating a page.

    ``parent`` is checked in the view (it must be a page the caller can see in the
    same project).
    """

    name = serializers.CharField(required=False, allow_blank=True, default="")
    description_html = serializers.CharField(required=False, allow_blank=True, default="<p></p>")
    access = serializers.ChoiceField(choices=Page.ACCESS_CHOICES, required=False, default=Page.PUBLIC_ACCESS)
    parent = serializers.UUIDField(required=False, allow_null=True)
    logo_props = serializers.JSONField(required=False)
    view_props = serializers.JSONField(required=False)

    class Meta:
        model = Page
        fields = [
            "name",
            "description_html",
            "access",
            "color",
            "parent",
            "logo_props",
            "view_props",
            "external_id",
            "external_source",
        ]


class PageUpdateAPISerializer(_PageWriteMixin, BaseSerializer):
    """Request body for updating a page. All fields are optional."""

    name = serializers.CharField(required=False, allow_blank=True)
    description_html = serializers.CharField(required=False, allow_blank=True)
    access = serializers.ChoiceField(choices=Page.ACCESS_CHOICES, required=False)
    parent = serializers.UUIDField(required=False, allow_null=True)
    logo_props = serializers.JSONField(required=False)
    view_props = serializers.JSONField(required=False)

    class Meta:
        model = Page
        fields = [
            "name",
            "description_html",
            "access",
            "color",
            "parent",
            "logo_props",
            "view_props",
            "external_id",
            "external_source",
        ]
