# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Public API (API key) endpoints for project pages.

These mirror the rules of the app-side page views in
``plane/app/views/page/base.py``:

- Only active members of the project reach its pages (``ProjectPagePermission``).
- Private pages are seen and changed only by their owner.
- Guests without "guest view all features" see only their own pages.
- Locked or archived pages cannot be edited.
- Only the owner can change a page's access.
- Only the owner or a project admin can archive / unarchive a page.
- A page must be archived before it is deleted, and only its owner or a project
  admin can delete it.

The API key's user is the actor for every change.

Every read and write starts from ``visible_project_pages()``. That is the one
place to narrow which pages an API caller may see (for example a per-item sharing
filter).
"""

# Python imports
import json
from datetime import datetime

# Django imports
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Exists, OuterRef, Q

# Third party imports
from rest_framework import status
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiRequest, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

# Module imports
from plane.api.serializers.page import (
    PageAPISerializer,
    PageDetailAPISerializer,
    PageCreateAPISerializer,
    PageUpdateAPISerializer,
)
from plane.app.permissions import ProjectPagePermission, ROLE
from plane.app.views.page.base import unarchive_archive_page_and_descendants
from plane.bgtasks.page_transaction_task import page_transaction
from plane.bgtasks.page_version_task import track_page_version
from plane.db.models import (
    Page,
    Project,
    ProjectMember,
    ProjectPage,
    UserFavorite,
    UserRecentVisit,
)
from plane.utils.order_queryset import sanitize_order_by
from plane.utils.openapi import (
    CURSOR_PARAMETER,
    PER_PAGE_PARAMETER,
    ORDER_BY_PARAMETER,
    FIELDS_PARAMETER,
    INVALID_REQUEST_RESPONSE,
    DELETED_RESPONSE,
    UNARCHIVED_RESPONSE,
    create_paginated_response,
)
from plane.utils.openapi.decorators import page_docs
from plane.utils.openapi.parameters import PAGE_ID_PARAMETER

from .base import BaseAPIView


PAGE_ORDER_BY_ALLOWLIST = frozenset(
    {
        "created_at",
        "updated_at",
        "name",
        "sort_order",
        "archived_at",
    }
)

PAGE_NOT_FOUND = {"error": "Page not found"}


# --- Visibility --------------------------------------------------------------------------------


def visible_project_pages(user, slug, project_id):
    """Pages of ``project_id`` that ``user`` may see through the public API.

    Same rules as the app's page list (``PageViewSet.get_queryset`` + ``list``):
    an active, linked page in a non-archived project the user is an active member
    of; public pages plus the user's own private pages; guests without
    ``guest_view_all_features`` only their own pages.

    HOOK POINT: this is the single queryset every pages API endpoint reads from.
    A per-item sharing filter wraps it here, e.g.
    ``return visible_pages(queryset, user)`` from ``plane.sharing.visibility``.
    """
    membership = ProjectMember.objects.filter(
        project_id=project_id,
        member=user,
        is_active=True,
        project__archived_at__isnull=True,
        workspace__slug=slug,
    ).values("role", "project__guest_view_all_features").first()
    if membership is None:
        return Page.objects.none()

    queryset = (
        Page.objects.filter(workspace__slug=slug)
        .filter(
            Exists(
                ProjectPage.objects.filter(
                    page_id=OuterRef("pk"),
                    project_id=project_id,
                    deleted_at__isnull=True,
                )
            )
        )
        .filter(Q(owned_by=user) | Q(access=Page.PUBLIC_ACCESS))
    )

    if membership["role"] == ROLE.GUEST.value and not membership["project__guest_view_all_features"]:
        queryset = queryset.filter(owned_by=user)

    return queryset.select_related("workspace", "owned_by")


def _is_project_admin(user, project_id):
    return ProjectMember.objects.filter(
        project_id=project_id, member=user, is_active=True, role=ROLE.ADMIN.value
    ).exists()


def _external_id_conflict(slug, project_id, external_source, external_id, exclude_pk=None):
    if not (external_id and external_source):
        return None
    queryset = Page.objects.filter(
        workspace__slug=slug,
        external_source=external_source,
        external_id=external_id,
        project_pages__project_id=project_id,
        project_pages__deleted_at__isnull=True,
    )
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.first()


# --- OpenAPI examples --------------------------------------------------------------------------

PAGE_CREATE_EXAMPLE = OpenApiExample(
    name="Create page",
    value={
        "name": "Call notes",
        "description_html": "<p>Client asked for a call back on Friday.</p>",
        "access": 0,
        "external_source": "crm",
        "external_id": "note-1042",
    },
)

PAGE_UPDATE_EXAMPLE = OpenApiExample(
    name="Update page",
    value={"name": "Call notes (done)", "description_html": "<p>Called back. All set.</p>"},
)

PAGE_EXAMPLE = OpenApiExample(
    name="Page",
    value={
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Call notes",
        "owned_by": "550e8400-e29b-41d4-a716-446655440001",
        "access": 0,
        "color": "",
        "parent": None,
        "is_locked": False,
        "archived_at": None,
        "logo_props": {},
        "view_props": {"full_width": False},
        "sort_order": 65535,
        "external_id": "note-1042",
        "external_source": "crm",
        "workspace": "550e8400-e29b-41d4-a716-446655440002",
        "description_html": "<p>Client asked for a call back on Friday.</p>",
        "created_at": "2026-10-19T10:30:00Z",
        "updated_at": "2026-10-19T10:30:00Z",
        "created_by": "550e8400-e29b-41d4-a716-446655440001",
        "updated_by": "550e8400-e29b-41d4-a716-446655440001",
    },
)

ARCHIVED_FILTER_PARAMETER = OpenApiParameter(
    name="archived",
    description="true: only archived pages. false (default): only pages that are not archived.",
    required=False,
    type=OpenApiTypes.BOOL,
    location=OpenApiParameter.QUERY,
)

ACCESS_FILTER_PARAMETER = OpenApiParameter(
    name="access",
    description="0: public pages only. 1: private pages only (your own).",
    required=False,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.QUERY,
)

PARENT_FILTER_PARAMETER = OpenApiParameter(
    name="parent",
    description="Only child pages of this page id. Use 'null' for top-level pages.",
    required=False,
    type=OpenApiTypes.STR,
    location=OpenApiParameter.QUERY,
)


# --- Endpoints ---------------------------------------------------------------------------------


class PageListCreateAPIEndpoint(BaseAPIView):
    """List and create project pages."""

    serializer_class = PageAPISerializer
    model = Page
    permission_classes = [ProjectPagePermission]

    @page_docs(
        operation_id="list_pages",
        summary="List pages",
        description="List the pages of a project that the API key's user can see. Content is not included.",
        parameters=[
            CURSOR_PARAMETER,
            PER_PAGE_PARAMETER,
            ORDER_BY_PARAMETER,
            FIELDS_PARAMETER,
            ARCHIVED_FILTER_PARAMETER,
            ACCESS_FILTER_PARAMETER,
            PARENT_FILTER_PARAMETER,
        ],
        responses={
            200: create_paginated_response(
                PageAPISerializer,
                "PaginatedPageResponse",
                "Paginated list of pages",
                "Paginated Pages",
            ),
            400: INVALID_REQUEST_RESPONSE,
        },
    )
    def get(self, request, slug, project_id):
        """List pages"""
        queryset = visible_project_pages(request.user, slug, project_id)

        archived = request.GET.get("archived", "false").lower()
        if archived in ("true", "1"):
            queryset = queryset.filter(archived_at__isnull=False)
        else:
            queryset = queryset.filter(archived_at__isnull=True)

        access = request.GET.get("access")
        if access is not None and access != "":
            if access not in ("0", "1"):
                return Response({"error": "access must be 0 or 1"}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(access=int(access))

        parent = request.GET.get("parent")
        if parent:
            if parent.lower() == "null":
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent_id=parent)

        order_by = sanitize_order_by(request.GET.get("order_by", "-created_at"), PAGE_ORDER_BY_ALLOWLIST)

        return self.paginate(
            request=request,
            queryset=queryset,
            order_by=order_by,
            on_results=lambda pages: PageAPISerializer(pages, many=True, fields=self.fields).data,
        )

    @page_docs(
        operation_id="create_page",
        summary="Create page",
        description=(
            "Create a page in a project. The API key's user owns the page. "
            "Content is given as HTML; the web editor builds its own copy from it the first time the page is opened."
        ),
        request=OpenApiRequest(request=PageCreateAPISerializer, examples=[PAGE_CREATE_EXAMPLE]),
        responses={
            201: OpenApiResponse(description="Page created", response=PageDetailAPISerializer, examples=[PAGE_EXAMPLE]),
            400: INVALID_REQUEST_RESPONSE,
            409: OpenApiResponse(description="Page with the same external_source and external_id already exists"),
        },
    )
    def post(self, request, slug, project_id):
        """Create page"""
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        serializer = PageCreateAPISerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        existing = _external_id_conflict(slug, project_id, data.get("external_source"), data.get("external_id"))
        if existing is not None:
            return Response(
                {
                    "error": "Page with the same external id and external source already exists",
                    "id": str(existing.id),
                },
                status=status.HTTP_409_CONFLICT,
            )

        parent_id = data.get("parent")
        if parent_id:
            parent = visible_project_pages(request.user, slug, project_id).filter(pk=parent_id).first()
            if parent is None:
                return Response({"parent": ["Parent page not found in this project"]}, status=status.HTTP_400_BAD_REQUEST)
            if parent.archived_at:
                return Response({"parent": ["Parent page is archived"]}, status=status.HTTP_400_BAD_REQUEST)

        description_html = data.get("description_html") or "<p></p>"
        page = Page.objects.create(
            workspace_id=project.workspace_id,
            name=data.get("name", ""),
            description_html=description_html,
            # Left empty on purpose: the live server converts description_html into
            # the editor's binary document the first time the page is opened.
            description_binary=None,
            description_json={},
            access=data.get("access", Page.PUBLIC_ACCESS),
            color=data.get("color", "") or "",
            parent_id=parent_id,
            logo_props=data.get("logo_props") or {},
            view_props=data.get("view_props") or {"full_width": False},
            external_id=data.get("external_id"),
            external_source=data.get("external_source"),
            owned_by=request.user,
        )
        ProjectPage.objects.create(
            workspace_id=project.workspace_id,
            project_id=project_id,
            page_id=page.id,
            created_by_id=page.created_by_id,
            updated_by_id=page.updated_by_id,
        )

        # Same background task as the app: records mentions / embeds in the page.
        page_transaction.delay(
            new_description_html=description_html,
            old_description_html=None,
            page_id=page.id,
        )

        page = visible_project_pages(request.user, slug, project_id).get(pk=page.id)
        return Response(PageDetailAPISerializer(page).data, status=status.HTTP_201_CREATED)


class PageDetailAPIEndpoint(BaseAPIView):
    """Read, update and delete one project page."""

    serializer_class = PageDetailAPISerializer
    model = Page
    permission_classes = [ProjectPagePermission]

    @page_docs(
        operation_id="retrieve_page",
        summary="Retrieve page",
        description="Get one page with its HTML content.",
        parameters=[PAGE_ID_PARAMETER, FIELDS_PARAMETER],
        responses={
            200: OpenApiResponse(description="Page", response=PageDetailAPISerializer, examples=[PAGE_EXAMPLE]),
        },
    )
    def get(self, request, slug, project_id, page_id):
        """Retrieve page"""
        page = visible_project_pages(request.user, slug, project_id).filter(pk=page_id).first()
        if page is None:
            return Response(PAGE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(PageDetailAPISerializer(page, fields=self.fields).data, status=status.HTTP_200_OK)

    @page_docs(
        operation_id="update_page",
        summary="Update page",
        description=(
            "Change a page's name, HTML content, access or other details. Locked and archived pages cannot be "
            "changed. Only the owner can change access. New HTML replaces the editor's copy; if someone has the "
            "page open in the editor at that moment, their open copy is saved over it."
        ),
        parameters=[PAGE_ID_PARAMETER],
        request=OpenApiRequest(request=PageUpdateAPISerializer, examples=[PAGE_UPDATE_EXAMPLE]),
        responses={
            200: OpenApiResponse(description="Page updated", response=PageDetailAPISerializer, examples=[PAGE_EXAMPLE]),
            400: INVALID_REQUEST_RESPONSE,
            409: OpenApiResponse(description="Page with the same external_source and external_id already exists"),
        },
    )
    def patch(self, request, slug, project_id, page_id):
        """Update page"""
        page = visible_project_pages(request.user, slug, project_id).filter(pk=page_id).first()
        if page is None:
            return Response(PAGE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        if page.is_locked:
            return Response({"error": "Page is locked"}, status=status.HTTP_400_BAD_REQUEST)
        if page.archived_at:
            return Response({"error": "Archived page cannot be edited"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PageUpdateAPISerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        if "access" in data and data["access"] != page.access and page.owned_by_id != request.user.id:
            return Response(
                {"error": "Access cannot be updated since this page is owned by someone else"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "parent" in data and data["parent"]:
            if str(data["parent"]) == str(page.id):
                return Response({"parent": ["A page cannot be its own parent"]}, status=status.HTTP_400_BAD_REQUEST)
            parent = visible_project_pages(request.user, slug, project_id).filter(pk=data["parent"]).first()
            if parent is None:
                return Response({"parent": ["Parent page not found in this project"]}, status=status.HTTP_400_BAD_REQUEST)

        external_source = data.get("external_source", page.external_source)
        external_id = data.get("external_id", page.external_id)
        if ("external_id" in data or "external_source" in data) and _external_id_conflict(
            slug, project_id, external_source, external_id, exclude_pk=page.id
        ):
            return Response(
                {"error": "Page with the same external id and external source already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        old_description_html = page.description_html
        existing_instance = json.dumps({"description_html": old_description_html}, cls=DjangoJSONEncoder)

        for field in ("name", "access", "logo_props", "view_props", "external_id", "external_source"):
            if field in data:
                setattr(page, field, data[field])
        if "color" in data:
            page.color = data["color"] or ""
        if "logo_props" in data and data["logo_props"] is None:
            page.logo_props = {}
        if "view_props" in data and data["view_props"] is None:
            page.view_props = {"full_width": False}
        if "parent" in data:
            page.parent_id = data["parent"]

        description_changed = "description_html" in data and data["description_html"] != old_description_html
        if description_changed:
            page.description_html = data["description_html"] or "<p></p>"
            # Drop the editor's binary copy so the live server rebuilds it from the
            # new HTML the next time the page is opened (as the app does on duplicate).
            page.description_binary = None
            page.description_json = {}

        page.save()

        if description_changed:
            page_transaction.delay(
                new_description_html=page.description_html,
                old_description_html=old_description_html,
                page_id=page.id,
            )
            track_page_version.delay(
                page_id=page.id,
                existing_instance=existing_instance,
                user_id=request.user.id,
            )

        page = visible_project_pages(request.user, slug, project_id).get(pk=page.id)
        return Response(PageDetailAPISerializer(page).data, status=status.HTTP_200_OK)

    @page_docs(
        operation_id="delete_page",
        summary="Delete page",
        description=(
            "Permanently delete a page. The page must be archived first. Only the page owner or a project admin "
            "can delete it. Child pages are kept and moved to the top level."
        ),
        parameters=[PAGE_ID_PARAMETER],
        responses={
            204: DELETED_RESPONSE,
            400: OpenApiResponse(description="The page should be archived before deleting"),
        },
    )
    def delete(self, request, slug, project_id, page_id):
        """Delete page"""
        page = visible_project_pages(request.user, slug, project_id).filter(pk=page_id).first()
        if page is None:
            return Response(PAGE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        if page.archived_at is None:
            return Response(
                {"error": "The page should be archived before deleting"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page.owned_by_id != request.user.id and not _is_project_admin(request.user, project_id):
            return Response(
                {"error": "Only admin or owner can delete the page"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Same clean-up as the app: keep child pages, drop favorites and recent visits.
        Page.objects.filter(
            parent_id=page_id,
            projects__id=project_id,
            workspace__slug=slug,
            project_pages__deleted_at__isnull=True,
        ).update(parent=None)
        page.delete()
        UserFavorite.objects.filter(
            project=project_id,
            workspace__slug=slug,
            entity_identifier=page_id,
            entity_type="page",
        ).delete()
        UserRecentVisit.objects.filter(
            project_id=project_id,
            workspace__slug=slug,
            entity_identifier=page_id,
            entity_name="page",
        ).delete(soft=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PageArchiveUnarchiveAPIEndpoint(BaseAPIView):
    """Archive (POST) and unarchive (DELETE) a page and its child pages."""

    permission_classes = [ProjectPagePermission]

    def _get_page_or_refuse(self, request, slug, project_id, page_id, verb):
        page = visible_project_pages(request.user, slug, project_id).filter(pk=page_id).first()
        if page is None:
            return None, Response(PAGE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        if page.owned_by_id != request.user.id and not _is_project_admin(request.user, project_id):
            return None, Response(
                {"error": f"Only the owner or admin can {verb} the page"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return page, None

    @page_docs(
        operation_id="archive_page",
        summary="Archive page",
        description="Archive a page and all of its child pages. Only the owner or a project admin can do this.",
        parameters=[PAGE_ID_PARAMETER],
        request={},
        responses={
            200: OpenApiResponse(
                description="Page archived",
                examples=[OpenApiExample(name="Archived", value={"archived_at": "2026-10-19"})],
            ),
        },
    )
    def post(self, request, slug, project_id, page_id):
        """Archive page"""
        page, refusal = self._get_page_or_refuse(request, slug, project_id, page_id, "archive")
        if refusal is not None:
            return refusal

        UserFavorite.objects.filter(
            entity_type="page",
            entity_identifier=page_id,
            project_id=project_id,
            workspace__slug=slug,
        ).delete()

        archived_at = datetime.now()
        unarchive_archive_page_and_descendants(page_id, archived_at)
        return Response({"archived_at": str(archived_at.date())}, status=status.HTTP_200_OK)

    @page_docs(
        operation_id="unarchive_page",
        summary="Unarchive page",
        description=(
            "Restore an archived page and its child pages. If its parent is still archived, the page moves to the "
            "top level. Only the owner or a project admin can do this."
        ),
        parameters=[PAGE_ID_PARAMETER],
        request={},
        responses={204: UNARCHIVED_RESPONSE},
    )
    def delete(self, request, slug, project_id, page_id):
        """Unarchive page"""
        page, refusal = self._get_page_or_refuse(request, slug, project_id, page_id, "unarchive")
        if refusal is not None:
            return refusal

        if page.parent_id and page.parent.archived_at:
            page.parent = None
            page.save(update_fields=["parent"])

        unarchive_archive_page_and_descendants(page_id, None)
        return Response(status=status.HTTP_204_NO_CONTENT)
