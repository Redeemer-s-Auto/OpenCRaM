# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView

from .models import SyncedBlock
from .service import can_delete, can_edit, can_read, create_block, payload, readable_blocks, save_block

NO_ACCESS = {"error": "no_access"}


def _block(slug, block_id):
    return SyncedBlock.objects.select_related("home_issue", "home_issue__project").filter(
        workspace__slug=slug, pk=block_id
    ).first()


class SyncedBlockListEndpoint(BaseAPIView):
    """GET ``?search=`` - blocks the caller may read. POST ``{home_issue_id, content_html?}`` - make a block."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        rows = readable_blocks(request.user, slug, request.GET.get("search", ""))
        return Response([payload(request.user, block, text) for block, text in rows])

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def post(self, request, slug):
        block = create_block(request.user, slug, request.data.get("home_issue_id"), request.data.get("content_html"))
        if block is None:
            return Response({"error": "You cannot add a block to that card."}, status=status.HTTP_403_FORBIDDEN)
        return Response(payload(request.user, _block(slug, block.id)), status=status.HTTP_201_CREATED)


class SyncedBlockEndpoint(BaseAPIView):
    """GET - the block. PATCH ``{content_html}`` - change it for every copy. DELETE - remove it everywhere."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, block_id):
        block = _block(slug, block_id)
        if block is None or not can_read(request.user, block):
            return Response(NO_ACCESS, status=status.HTTP_403_FORBIDDEN)
        return Response(payload(request.user, block))

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def patch(self, request, slug, block_id):
        block = _block(slug, block_id)
        if block is None or not can_read(request.user, block):
            return Response(NO_ACCESS, status=status.HTTP_403_FORBIDDEN)
        if not can_edit(request.user, block):
            return Response({"error": "read_only"}, status=status.HTTP_403_FORBIDDEN)
        block = save_block(request.user, block, request.data.get("content_html"))
        return Response(payload(request.user, _block(slug, block.id)))

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def delete(self, request, slug, block_id):
        block = _block(slug, block_id)
        if block is None or not can_read(request.user, block):
            return Response(NO_ACCESS, status=status.HTTP_403_FORBIDDEN)
        if not can_delete(request.user, block):
            return Response({"error": "read_only"}, status=status.HTTP_403_FORBIDDEN)
        block.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
