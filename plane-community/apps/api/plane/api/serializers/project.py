# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
import random
from rest_framework import serializers


# Python imports
import re

# Module imports
from plane.db.models import Project, ProjectIdentifier, WorkspaceMember, State, Estimate

from plane.utils.content_validator import (
    validate_html_content,
)
from plane.sharing import placement as board_placement
from plane.utils.project_tree import ProjectParentIdField, clean_parent_id
from .base import BaseSerializer

# Where a board sits (plane.sharing.placement): the FKs are exposed as ids, never as nested rows.
PLACEMENT_EXCLUDE = ["parent", "teamspace", "private_owner"]
PLACEMENT_WRITE_FIELDS = ["teamspace_id", "private_owner_id", "is_sealed", "private", "section", "teamspace_detail"]


class ProjectCreateSerializer(BaseSerializer):
    """
    Serializer for creating projects with workspace validation.

    Handles project creation including identifier validation, member verification,
    and workspace association for new project initialization.
    """

    PROJECT_ICON_DEFAULT_COLORS = [
        "#95999f",
        "#6d7b8a",
        "#5e6ad2",
        "#02b5ed",
        "#02b55c",
        "#f2be02",
        "#e57a00",
        "#f38e82",
    ]
    PROJECT_ICON_DEFAULT_ICONS = [
        "home",
        "apps",
        "settings",
        "star",
        "favorite",
        "done",
        "check_circle",
        "add_task",
        "create_new_folder",
        "dataset",
        "terminal",
        "key",
        "rocket",
        "public",
        "quiz",
        "mood",
        "gavel",
        "eco",
        "diamond",
        "forest",
        "bolt",
        "sync",
        "cached",
        "library_add",
        "view_timeline",
        "view_kanban",
        "empty_dashboard",
        "cycle",
    ]

    # Fork: the board this one sits inside (null = top level). Read back only when visible.
    parent_id = ProjectParentIdField()
    # Fork: where the board sits. teamspace_id / private_owner_id for workspace admins, is_sealed
    # also for the owner, private=true for "my own private board". See plane.sharing.placement.
    teamspace_id = serializers.UUIDField(required=False, allow_null=True)
    private_owner_id = serializers.UUIDField(required=False, allow_null=True)
    is_sealed = serializers.BooleanField(required=False)
    private = serializers.BooleanField(required=False, write_only=True)
    section = serializers.SerializerMethodField()
    teamspace_detail = serializers.SerializerMethodField()

    def get_section(self, obj):
        return board_placement.section_of(obj.teamspace_id, obj.private_owner_id)

    def get_teamspace_detail(self, obj):
        return board_placement.teamspace_detail_of(obj.teamspace if obj.teamspace_id else None)

    def apply_placement(self, actor=None, instance=None):
        """Write the placement ``validate`` worked out (if any). Views call it on create after adding members."""
        placement = getattr(self, "_placement", None)
        instance = instance if instance is not None else self.instance
        if placement and instance is not None:
            board_placement.apply_placement(instance, placement, actor=actor)
            self._placement = None

    class Meta:
        model = Project
        fields = [
            "name",
            "description",
            "project_lead",
            "default_assignee",
            "identifier",
            "icon_prop",
            "emoji",
            "cover_image",
            "module_view",
            "cycle_view",
            "issue_views_view",
            "page_view",
            "intake_view",
            "guest_view_all_features",
            "archive_in",
            "close_in",
            "timezone",
            "external_source",
            "external_id",
            "is_issue_type_enabled",
            "is_time_tracking_enabled",
            # Fork: an importer (or any API client) can make a board private or invite-only
            # from the start, so nothing it creates is ever visible wider than intended.
            "network",
            "is_private",
            "parent_id",
        ] + PLACEMENT_WRITE_FIELDS

        read_only_fields = [
            "id",
            "workspace",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "logo_props",
        ]

    def validate(self, data):
        project_name = data.get("name", None)
        project_identifier = data.get("identifier", None)

        if project_name is not None and re.match(Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN, project_name):
            raise serializers.ValidationError("Project name cannot contain special characters.")

        if project_identifier is not None and re.match(Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN, project_identifier):
            raise serializers.ValidationError("Project identifier cannot contain special characters.")

        project_lead = data.get("project_lead")
        if (
            project_lead
            and not WorkspaceMember.objects.filter(
                workspace_id=self.context["workspace_id"],
                member=project_lead,
                is_active=True,
            ).exists()
        ):
            # Field-shaped error so DRF surfaces it under the specific key
            # rather than as non_field_errors. Also requires the membership
            # to be active so that revoked / removed members can't slip
            # through and trigger the FK error downstream.
            raise serializers.ValidationError({"project_lead": "The provided user is not a member of this workspace."})

        if data.get("default_assignee", None) is not None:
            # Check if the default assignee is a member of the workspace
            if not WorkspaceMember.objects.filter(
                workspace_id=self.context["workspace_id"],
                member_id=data.get("default_assignee"),
            ).exists():
                raise serializers.ValidationError("Default assignee should be a user in the workspace")

        self._placement = board_placement.clean_placement(
            data, self.instance, self.context["workspace_id"], self.context.get("user")
        )
        return data

    def validate_parent_id(self, parent_id):
        return clean_parent_id(parent_id, self.instance, self.context["workspace_id"], self.context.get("user"))

    def create(self, validated_data):
        identifier = validated_data.get("identifier", "").strip().upper()

        if identifier == "":
            raise serializers.ValidationError(detail="Project Identifier is required")

        if ProjectIdentifier.objects.filter(name=identifier, workspace_id=self.context["workspace_id"]).exists():
            raise serializers.ValidationError(detail="Project Identifier is taken")

        if validated_data.get("logo_props", None) is None:
            # Generate a random icon and color for the project icon
            validated_data["logo_props"] = {
                "in_use": "icon",
                "icon": {
                    "name": random.choice(self.PROJECT_ICON_DEFAULT_ICONS),
                    "color": random.choice(self.PROJECT_ICON_DEFAULT_COLORS),
                },
            }

        project = Project.objects.create(**validated_data, workspace_id=self.context["workspace_id"])
        return project


class ProjectUpdateSerializer(ProjectCreateSerializer):
    """
    Serializer for updating projects with enhanced state and estimation management.

    Extends project creation with update-specific validations including default state
    assignment, estimation configuration, and project setting modifications.
    """

    class Meta(ProjectCreateSerializer.Meta):
        model = Project
        fields = ProjectCreateSerializer.Meta.fields + [
            "default_state",
            "estimate",
        ]

        read_only_fields = ProjectCreateSerializer.Meta.read_only_fields

    def update(self, instance, validated_data):
        project_name = validated_data.get("name", None)
        project_identifier = validated_data.get("identifier", None)

        if project_name is not None and re.match(Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN, project_name):
            raise serializers.ValidationError("Project name cannot contain special characters.")

        if project_identifier is not None and re.match(Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN, project_identifier):
            raise serializers.ValidationError("Project identifier cannot contain special characters.")

        """Update a project"""
        if (
            validated_data.get("default_state", None) is not None
            and not State.objects.filter(project=instance, id=validated_data.get("default_state")).exists()
        ):
            # Check if the default state is a state in the project
            raise serializers.ValidationError("Default state should be a state in the project")

        if (
            validated_data.get("estimate", None) is not None
            and not Estimate.objects.filter(project=instance, id=validated_data.get("estimate").id).exists()
        ):
            # Check if the estimate is a estimate in the project
            raise serializers.ValidationError("Estimate should be a estimate in the project")
        instance = super().update(instance, validated_data)
        self.apply_placement(actor=self.context.get("user"), instance=instance)
        return instance


class ProjectSerializer(BaseSerializer):
    """
    Comprehensive project serializer with metrics and member context.

    Provides complete project data including member counts, cycle/module totals,
    deployment status, and user-specific context for project management.
    """

    total_members = serializers.IntegerField(read_only=True)
    total_cycles = serializers.IntegerField(read_only=True)
    total_modules = serializers.IntegerField(read_only=True)
    is_member = serializers.BooleanField(read_only=True)
    sort_order = serializers.FloatField(read_only=True)
    member_role = serializers.IntegerField(read_only=True)
    is_deployed = serializers.BooleanField(read_only=True)
    cover_image_url = serializers.CharField(read_only=True)
    parent_id = ProjectParentIdField(read_only=True)
    teamspace_id = serializers.UUIDField(read_only=True)
    private_owner_id = serializers.UUIDField(read_only=True)
    is_sealed = serializers.BooleanField(read_only=True)
    section = serializers.SerializerMethodField()
    teamspace_detail = serializers.SerializerMethodField()

    def get_section(self, obj):
        return board_placement.section_of(obj.teamspace_id, obj.private_owner_id)

    def get_teamspace_detail(self, obj):
        return board_placement.teamspace_detail_of(obj.teamspace if obj.teamspace_id else None)

    class Meta:
        model = Project
        # "parent" is replaced by parent_id, which hides a parent the user cannot see.
        exclude = PLACEMENT_EXCLUDE
        read_only_fields = [
            "id",
            "emoji",
            "workspace",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
            "cover_image_url",
        ]

    def validate(self, data):
        project_name = data.get("name", None)
        project_identifier = data.get("identifier", None)

        if project_name is not None and re.match(Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN, project_name):
            raise serializers.ValidationError("Project name cannot contain special characters.")

        if project_identifier is not None and re.match(Project.FORBIDDEN_IDENTIFIER_CHARS_PATTERN, project_identifier):
            raise serializers.ValidationError("Project identifier cannot contain special characters.")

        # Check project lead should be a member of the workspace
        if (
            data.get("project_lead", None) is not None
            and not WorkspaceMember.objects.filter(
                workspace_id=self.context["workspace_id"],
                member_id=data.get("project_lead"),
            ).exists()
        ):
            raise serializers.ValidationError("Project lead should be a user in the workspace")

        # Check default assignee should be a member of the workspace
        if (
            data.get("default_assignee", None) is not None
            and not WorkspaceMember.objects.filter(
                workspace_id=self.context["workspace_id"],
                member_id=data.get("default_assignee"),
            ).exists()
        ):
            raise serializers.ValidationError("Default assignee should be a user in the workspace")

        # Validate description content for security
        if "description_html" in data and data["description_html"]:
            if isinstance(data["description_html"], dict):
                is_valid, error_msg, sanitized_html = validate_html_content(str(data["description_html"]))
                # Update the data with sanitized HTML if available
                if sanitized_html is not None:
                    data["description_html"] = sanitized_html
            if not is_valid:
                raise serializers.ValidationError({"error": "html content is not valid"})

        return data

    def create(self, validated_data):
        identifier = validated_data.get("identifier", "").strip().upper()
        if identifier == "":
            raise serializers.ValidationError(detail="Project Identifier is required")

        if ProjectIdentifier.objects.filter(name=identifier, workspace_id=self.context["workspace_id"]).exists():
            raise serializers.ValidationError(detail="Project Identifier is taken")

        project = Project.objects.create(**validated_data, workspace_id=self.context["workspace_id"])
        _ = ProjectIdentifier.objects.create(
            name=project.identifier,
            project=project,
            workspace_id=self.context["workspace_id"],
        )
        return project


class ProjectLiteSerializer(BaseSerializer):
    """
    Lightweight project serializer for minimal data transfer.

    Provides essential project information including identifiers, visual properties,
    and basic metadata optimized for list views and references.
    """

    cover_image_url = serializers.CharField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "identifier",
            "name",
            "cover_image",
            "icon_prop",
            "emoji",
            "description",
            "cover_image_url",
            "archived_at",
        ]
        read_only_fields = fields
