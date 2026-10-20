# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Blueprint library endpoints (signed-in app). Rules live in ``service.py``."""

from django.db import IntegrityError
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.blueprints import service
from plane.blueprints import spec as S
from plane.blueprints.models import Blueprint, BlueprintVersion, BoardOrigin
from plane.db.models import Project, Workspace

MEMBERS = [ROLE.ADMIN, ROLE.MEMBER]


def _person(user):
    if user is None:
        return None
    return {"id": str(user.id), "display_name": user.display_name or user.first_name or ""}


def _source(user, blueprint):
    """The board it was captured from, only when the person can see that board."""
    from plane.utils.private_projects import is_hidden_from

    project = blueprint.source_project
    if project is None or project.archived_at is not None or is_hidden_from(user, project.id):
        return None
    return {"id": str(project.id), "name": project.name, "identifier": project.identifier}


def describe(user, blueprint, full=False):
    source = _source(user, blueprint)
    data = {
        "id": str(blueprint.id),
        "name": blueprint.name,
        "description": blueprint.description,
        "logo_props": blueprint.logo_props or {},
        "version": blueprint.version,
        "is_shared": blueprint.is_shared,
        "created_by": _person(blueprint.created_by),
        "created_at": blueprint.created_at,
        "updated_at": blueprint.updated_at,
        "source_project": source,
        "summary": S.summary(blueprint.spec),
        "can_manage": service.can_manage(user, blueprint),
        "can_update_from_board": bool(source)
        and service.can_save_from(user, blueprint.source_project)
        and service.can_manage(user, blueprint),
    }
    if full:
        data["spec"] = blueprint.spec
    return data


def _workspace(slug):
    return Workspace.objects.get(slug=slug)


class BlueprintListEndpoint(BaseAPIView):
    @allow_permission(MEMBERS, level="WORKSPACE")
    def get(self, request, slug):
        workspace = _workspace(slug)
        rows = service.visible_blueprints(request.user, workspace).select_related("created_by", "source_project")
        return Response([describe(request.user, b) for b in rows])

    @allow_permission(MEMBERS, level="WORKSPACE")
    def post(self, request, slug):
        """Save a board as a new blueprint: {project_id, name, description, logo_props, include_samples,
        include_repeat_rules, is_shared}."""
        workspace = _workspace(slug)
        data = request.data or {}
        project = service.source_board(request.user, workspace, data.get("project_id"))
        blueprint = service.save_from_board(request.user, workspace, project, data)
        return Response(describe(request.user, blueprint), status=status.HTTP_201_CREATED)


class BlueprintDetailEndpoint(BaseAPIView):
    @allow_permission(MEMBERS, level="WORKSPACE")
    def get(self, request, slug, pk):
        blueprint = service.get_visible(request.user, _workspace(slug), pk)
        return Response(describe(request.user, blueprint, full=True))

    @allow_permission(MEMBERS, level="WORKSPACE")
    def patch(self, request, slug, pk):
        """Rename, edit the description or icon, share or unshare."""
        workspace = _workspace(slug)
        blueprint = service.get_visible(request.user, workspace, pk)
        service.require_manage(request.user, blueprint)
        data = request.data or {}
        if "name" in data:
            name = service._clean_name(data["name"])
            service._check_name_free(workspace, name, exclude=blueprint)
            blueprint.name = name
        if "description" in data:
            blueprint.description = str(data.get("description") or "")[:5000]
        if "logo_props" in data:
            blueprint.logo_props = service._logo(data.get("logo_props"))
        if "is_shared" in data:
            if blueprint.created_by_id != request.user.id:
                raise ValidationError({"is_shared": "Only the person who saved this blueprint can share or unshare it."})
            blueprint.is_shared = bool(data["is_shared"])
        blueprint.updated_by = request.user
        try:
            blueprint.save()
        except IntegrityError:
            raise ValidationError({"name": "This workspace already has a blueprint with this name."})
        return Response(describe(request.user, blueprint))

    @allow_permission(MEMBERS, level="WORKSPACE")
    def delete(self, request, slug, pk):
        blueprint = service.get_visible(request.user, _workspace(slug), pk)
        service.require_manage(request.user, blueprint)
        blueprint.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BlueprintRecaptureEndpoint(BaseAPIView):
    """POST {project_id?, include_samples?, include_repeat_rules?} -> next version from the board."""

    @allow_permission(MEMBERS, level="WORKSPACE")
    def post(self, request, slug, pk):
        workspace = _workspace(slug)
        blueprint = service.get_visible(request.user, workspace, pk)
        service.require_manage(request.user, blueprint)
        data = request.data or {}
        project_id = data.get("project_id") or blueprint.source_project_id
        if not project_id:
            raise ValidationError({"project_id": "Pick the board to update this blueprint from."})
        project = service.source_board(request.user, workspace, project_id)
        blueprint = service.recapture(request.user, blueprint, project, data)
        return Response(describe(request.user, blueprint))


class BlueprintVersionsEndpoint(BaseAPIView):
    @allow_permission(MEMBERS, level="WORKSPACE")
    def get(self, request, slug, pk):
        blueprint = service.get_visible(request.user, _workspace(slug), pk)
        rows = BlueprintVersion.objects.filter(blueprint=blueprint).select_related("created_by")
        return Response(
            [
                {
                    "version": v.version,
                    "note": v.note,
                    "created_at": v.created_at,
                    "created_by": _person(v.created_by),
                    "summary": S.summary(v.spec),
                }
                for v in rows
            ]
        )


class BlueprintExportEndpoint(BaseAPIView):
    """GET -> the blueprint as a .json file: design only (no sample cards, ids or emails)."""

    @allow_permission(MEMBERS, level="WORKSPACE")
    def get(self, request, slug, pk):
        import json
        import re

        blueprint = service.get_visible(request.user, _workspace(slug), pk)
        service.require_manage(request.user, blueprint)
        doc = service.export_document(blueprint)
        filename = re.sub(r"[^A-Za-z0-9_-]+", "-", blueprint.name).strip("-") or "blueprint"
        response = HttpResponse(json.dumps(doc, indent=2, default=str), content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{filename}.blueprint.json"'
        return response


class BlueprintImportEndpoint(BaseAPIView):
    """POST {"document": {...}} (or the document itself) -> a new blueprint, version 1."""

    @allow_permission(MEMBERS, level="WORKSPACE")
    def post(self, request, slug):
        workspace = _workspace(slug)
        body = request.data or {}
        doc = body.get("document", body) if isinstance(body, dict) else body
        blueprint = service.import_document(request.user, workspace, doc)
        return Response(describe(request.user, blueprint), status=status.HTTP_201_CREATED)


def use_response(request, project, notes, samples):
    return {
        "project": {"id": str(project.id), "name": project.name, "identifier": project.identifier},
        "sample_cards_created": samples,
        "notes": notes,
    }


class BlueprintUseEndpoint(BaseAPIView):
    """POST {name, identifier, description?, logo_props?, network?, relation_targets?: {field key: board id},
    include_samples?: true} -> a new board. The person becomes its admin."""

    @allow_permission(MEMBERS, level="WORKSPACE")
    def post(self, request, slug, pk):
        blueprint = service.get_visible(request.user, _workspace(slug), pk)
        data = request.data or {}
        values = {k: data.get(k) for k in ("name", "identifier", "description", "logo_props", "network")}
        project, notes, samples = service.use_blueprint(
            request,
            request.user,
            blueprint,
            values,
            relation_targets=data.get("relation_targets") or {},
            include_samples=bool(data.get("include_samples", True)),
        )
        return Response(use_response(request, project, notes, samples), status=status.HTTP_201_CREATED)


class BoardOriginEndpoint(BaseAPIView):
    """Which blueprint a board was made from: {blueprint_id, blueprint_name, version} or null."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        origin = BoardOrigin.objects.filter(project_id=project_id, project__workspace__slug=slug).first()
        if origin is None:
            return Response(None)
        blueprint_id = None
        if origin.blueprint_id:
            visible = service.visible_blueprints(request.user, Project.objects.get(pk=project_id).workspace)
            if visible.filter(pk=origin.blueprint_id).exists():
                blueprint_id = str(origin.blueprint_id)
        name = origin.blueprint.name if blueprint_id else origin.blueprint_name
        return Response({"blueprint_id": blueprint_id, "blueprint_name": name, "version": origin.version})
