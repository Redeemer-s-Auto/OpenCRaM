# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Endpoints for the sidebar page tree and "Link to page" blocks (see ``service``)."""

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView

from . import service


class PageTreeEndpoint(BaseAPIView):
    """GET ``?project_id=`` (optional) -> ``{"results": [page rows]}``: visible live pages, flat, with parent ids."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        project_id = service.as_uuid(request.query_params.get("project_id"))
        if request.query_params.get("project_id") and project_id is None:
            return Response({"error": "project_id must be a uuid"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"results": service.tree(request.user, slug, project_id)}, status=status.HTTP_200_OK)


class PageLinkResolveEndpoint(BaseAPIView):
    """POST ``{"pages": [...], "projects": [...]}`` -> what each id is, for the caller."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug):
        data = request.data if isinstance(request.data, dict) else {}
        pages = data.get("pages") or []
        projects = data.get("projects") or []
        if not isinstance(pages, list) or not isinstance(projects, list):
            return Response({"error": "pages and projects must be lists"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(service.resolve(request.user, slug, pages, projects), status=status.HTTP_200_OK)


class PageLinkSearchEndpoint(BaseAPIView):
    """GET ``?search=&limit=`` -> ``{"pages": [...], "projects": [...]}`` the caller may link to."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        return Response(
            service.search(request.user, slug, request.query_params.get("search", ""), request.query_params.get("limit", 20)),
            status=status.HTTP_200_OK,
        )
