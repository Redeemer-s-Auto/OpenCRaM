# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils.text import slugify
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, Page, Project, User, Workspace
from plane.sharing.board_access import MAX_BOARD_DEPTH, group_includes_transitively, user_teamspace_ids
from plane.sharing.models import (
    AccessGroup,
    AccessGroupInclude,
    AccessGroupMember,
    AccessLevel,
    ProjectShare,
    ProjectShareExclusion,
    Teamspace,
)
from plane.sharing.services import can_manage_sharing, is_workspace_admin, read_sharing, write_sharing

FORBIDDEN = Response({"error": "You don't have the required permissions."}, status=status.HTTP_403_FORBIDDEN)


class IssueSharingEndpoint(BaseAPIView):
    """GET/PUT the "who can see this" settings of one work item."""

    def _issue(self, slug, project_id, issue_id):
        return Issue.objects.get(workspace__slug=slug, project_id=project_id, pk=issue_id)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        issue = self._issue(slug, project_id, issue_id)
        data = read_sharing(issue=issue)
        data["can_manage"] = can_manage_sharing(request.user, issue.workspace, issue.created_by_id)
        return Response(data)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def put(self, request, slug, project_id, issue_id):
        issue = self._issue(slug, project_id, issue_id)
        if not can_manage_sharing(request.user, issue.workspace, issue.created_by_id):
            return FORBIDDEN
        data = write_sharing(issue.workspace, request.data, issue=issue)
        data["can_manage"] = True
        return Response(data)


class PageSharingEndpoint(BaseAPIView):
    """GET/PUT the "who can see this" settings of one page."""

    def _page(self, slug, project_id, page_id):
        return Page.objects.get(
            workspace__slug=slug,
            pk=page_id,
            project_pages__project_id=project_id,
            project_pages__deleted_at__isnull=True,
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, page_id):
        page = self._page(slug, project_id, page_id)
        data = read_sharing(page=page)
        data["can_manage"] = can_manage_sharing(request.user, page.workspace, page.owned_by_id)
        return Response(data)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def put(self, request, slug, project_id, page_id):
        page = self._page(slug, project_id, page_id)
        if not can_manage_sharing(request.user, page.workspace, page.owned_by_id):
            return FORBIDDEN
        data = write_sharing(page.workspace, request.data, page=page)
        data["can_manage"] = True
        return Response(data)


def _group_payload(group):
    members = list(group.members.select_related("member").order_by("member__display_name"))
    return {
        "id": str(group.id),
        "name": group.name,
        "description": group.description,
        "member_ids": [str(row.member_id) for row in members],
        "member_count": len(members),
        "shared_item_count": getattr(group, "shared_item_count", None),
        # Groups this group includes (their members inherit this group's access) and the reverse.
        "includes": [str(row.included_group_id) for row in group.includes.all()],
        "included_in": [str(row.group_id) for row in group.included_in.all()],
    }


def _set_group_members(group, workspace, member_ids):
    if not isinstance(member_ids, list):
        raise ValidationError({"member_ids": "Must be a list."})
    valid = set(
        User.objects.filter(
            id__in=member_ids,
            member_workspace__workspace=workspace,
            member_workspace__is_active=True,
            member_workspace__deleted_at__isnull=True,
        ).values_list("id", flat=True)
    )
    if len(valid) != len(set(map(str, member_ids))):
        raise ValidationError({"member_ids": "Every person must be in this workspace."})
    group.members.exclude(member_id__in=valid).delete()
    existing = set(group.members.values_list("member_id", flat=True))
    AccessGroupMember.objects.bulk_create(
        AccessGroupMember(group=group, member_id=member_id) for member_id in valid - existing
    )


class AccessGroupViews:
    """Groups: every workspace member may list them; only admins change them.

    A mixin so the same handlers serve the app (session) and the v1 API (API key).
    """

    def _groups(self, slug):
        return AccessGroup.objects.filter(workspace__slug=slug).annotate(
            shared_item_count=Count("item_shares", distinct=True)
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, group_id=None):
        if group_id:
            return Response(_group_payload(self._groups(slug).get(pk=group_id)))
        return Response([_group_payload(group) for group in self._groups(slug)])

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "Name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if AccessGroup.objects.filter(workspace=workspace, name__iexact=name).exists():
            return Response({"error": "A group with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            group = AccessGroup.objects.create(
                workspace=workspace, name=name, description=request.data.get("description", ""), created_by=request.user
            )
            _set_group_members(group, workspace, request.data.get("member_ids", []))
        return Response(_group_payload(self._groups(slug).get(pk=group.id)), status=status.HTTP_201_CREATED)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug, group_id):
        workspace = Workspace.objects.get(slug=slug)
        group = AccessGroup.objects.get(workspace=workspace, pk=group_id)
        with transaction.atomic():
            if "name" in request.data:
                name = (request.data.get("name") or "").strip()
                if not name:
                    return Response({"error": "Name is required."}, status=status.HTTP_400_BAD_REQUEST)
                if AccessGroup.objects.filter(workspace=workspace, name__iexact=name).exclude(pk=group.pk).exists():
                    return Response(
                        {"error": "A group with this name already exists."}, status=status.HTTP_400_BAD_REQUEST
                    )
                group.name = name
            if "description" in request.data:
                group.description = request.data.get("description") or ""
            group.save()
            if "member_ids" in request.data:
                _set_group_members(group, workspace, request.data.get("member_ids"))
        return Response(_group_payload(self._groups(slug).get(pk=group.id)))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, group_id):
        AccessGroup.objects.filter(workspace__slug=slug, pk=group_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccessGroupEndpoint(AccessGroupViews, BaseAPIView):
    pass


def _group_in_workspace(slug, group_id, field="group_id"):
    group = AccessGroup.objects.filter(workspace__slug=slug, pk=group_id).first() if group_id else None
    if group is None:
        raise ValidationError({field: "Group is not in this workspace."})
    return group


class AccessGroupIncludeViews:
    """Groups inside groups: ``group_id`` includes the group named in the body.

    Members of the included group inherit everything shared with ``group_id``.
    A loop (the included group already includes ``group_id``, directly or through
    other groups) is rejected, as is a group including itself.
    """

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug, group_id):
        group = _group_in_workspace(slug, group_id)
        included = _group_in_workspace(slug, request.data.get("group_id"))
        if included.pk == group.pk:
            return Response({"error": "A group cannot include itself."}, status=status.HTTP_400_BAD_REQUEST)
        if group_includes_transitively(included.pk, group.pk):
            return Response(
                {"error": f"{included.name} already includes {group.name}; that would make a loop."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _, created = AccessGroupInclude.objects.get_or_create(
            group=group, included_group=included, defaults={"created_by": request.user}
        )
        return Response(
            _group_payload(AccessGroup.objects.get(pk=group.pk)),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, group_id, included_group_id):
        AccessGroupInclude.objects.filter(
            group__workspace__slug=slug, group_id=group_id, included_group_id=included_group_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccessGroupIncludeEndpoint(AccessGroupIncludeViews, BaseAPIView):
    pass


def _teamspace_payload(teamspace):
    return {
        "id": str(teamspace.id),
        "name": teamspace.name,
        "slug": teamspace.slug,
        "group_id": str(teamspace.group_id) if teamspace.group_id else None,
        "group_name": teamspace.group.name if teamspace.group_id else None,
        "is_default": teamspace.is_default,
        "position": teamspace.position,
        "board_count": getattr(teamspace, "board_count", None),
    }


def _teamspace_slug(workspace, raw, name, exclude_pk=None):
    value = slugify(raw or name)[:64]
    if not value:
        raise ValidationError({"slug": "Slug is required."})
    taken = Teamspace.objects.filter(workspace=workspace, slug=value).exclude(pk=exclude_pk).exists()
    if taken:
        raise ValidationError({"slug": "A teamspace with this slug already exists."})
    return value


class TeamspaceViews:
    """Teamspaces: sidebar sections that hold boards.

    GET returns only the teamspaces the caller belongs to (default ones, and those whose
    group they act as) - workspace admins included: belonging, not role. POST / PATCH /
    DELETE are for workspace admins. Body: ``name`` (required), ``slug`` (from the name
    when absent), ``group_id`` (null = no group), ``is_default``, ``position``. Deleting
    a teamspace leaves its boards in the workspace section.
    """

    def _mine(self, request, slug):
        return (
            Teamspace.objects.filter(workspace__slug=slug, id__in=user_teamspace_ids(request.user, slug=slug))
            .select_related("group")
            .annotate(
                board_count=Count(
                    "projects",
                    filter=Q(projects__deleted_at__isnull=True, projects__archived_at__isnull=True),
                    distinct=True,
                )
            )
            .order_by("position", "name")
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, teamspace_id=None):
        if teamspace_id:
            teamspace = self._mine(request, slug).filter(pk=teamspace_id).first()
            if teamspace is None:
                return Response({"error": "Teamspace not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response(_teamspace_payload(teamspace))
        return Response([_teamspace_payload(row) for row in self._mine(request, slug)])

    def _apply(self, request, workspace, teamspace):
        data = request.data
        # The id is a uuid default, so "new" is the ORM's adding flag, not an empty pk.
        new = teamspace._state.adding
        if "name" in data or new:
            name = (data.get("name") or "").strip()
            if not name:
                raise ValidationError({"name": "Name is required."})
            teamspace.name = name
        if "slug" in data or new:
            teamspace.slug = _teamspace_slug(workspace, data.get("slug"), teamspace.name, exclude_pk=teamspace.pk)
        if "group_id" in data:
            group_id = data.get("group_id")
            teamspace.group = _group_in_workspace(workspace.slug, group_id) if group_id else None
        if "is_default" in data:
            teamspace.is_default = bool(data.get("is_default"))
        if "position" in data:
            try:
                teamspace.position = int(data.get("position"))
            except (TypeError, ValueError):
                raise ValidationError({"position": "Must be a whole number."})
        elif new:
            last = Teamspace.objects.filter(workspace=workspace).aggregate(last=Max("position"))["last"]
            teamspace.position = (last + 1) if last is not None else 0
        teamspace.save()

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        teamspace = Teamspace(workspace=workspace, created_by=request.user)
        with transaction.atomic():
            self._apply(request, workspace, teamspace)
        return Response(
            _teamspace_payload(Teamspace.objects.select_related("group").get(pk=teamspace.pk)),
            status=status.HTTP_201_CREATED,
        )

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug, teamspace_id):
        workspace = Workspace.objects.get(slug=slug)
        teamspace = Teamspace.objects.filter(workspace=workspace, pk=teamspace_id).first()
        if teamspace is None:
            return Response({"error": "Teamspace not found."}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            self._apply(request, workspace, teamspace)
        return Response(_teamspace_payload(Teamspace.objects.select_related("group").get(pk=teamspace.pk)))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, teamspace_id):
        Teamspace.objects.filter(workspace__slug=slug, pk=teamspace_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamspaceEndpoint(TeamspaceViews, BaseAPIView):
    pass


def _board(slug, project_id):
    return Project.objects.get(workspace__slug=slug, pk=project_id)


def _board_sharing(project):
    """Shares and exclusions set on this board, plus what it inherits from the boards above it."""
    shares = project.group_shares.select_related("group").order_by("group__name")
    exclusions = project.group_exclusions.select_related("group").order_by("group__name")
    decided = {share.group_id for share in shares} | {row.group_id for row in exclusions}
    inherited = []
    ancestor_id = project.parent_id
    visited = {project.id}
    while ancestor_id and ancestor_id not in visited and len(visited) <= MAX_BOARD_DEPTH:
        visited.add(ancestor_id)
        ancestor = Project.objects.filter(pk=ancestor_id).first()
        if ancestor is None or ancestor.is_private or ancestor.private_owner_id:
            break
        for row in ancestor.group_exclusions.all():
            decided.add(row.group_id)
        for share in ancestor.group_shares.select_related("group").order_by("group__name"):
            if share.group_id in decided:
                continue
            decided.add(share.group_id)
            inherited.append(
                {
                    "group_id": str(share.group_id),
                    "name": share.group.name,
                    "level": share.level,
                    "from_project_id": str(ancestor.id),
                    "from_project_name": ancestor.name,
                }
            )
        ancestor_id = ancestor.parent_id
    return {
        "shares": [{"group_id": str(s.group_id), "name": s.group.name, "level": s.level} for s in shares],
        "exclusions": [{"group_id": str(e.group_id), "name": e.group.name} for e in exclusions],
        "inherited": inherited,
    }


class ProjectGroupShareViews:
    """Share a whole board with a group.

    GET: anyone who can open the board sees its share list. POST ``{"group_id", "level"}``
    (5 view, 10 comment, 15 edit) adds or changes the share; DELETE removes it.
    Writes are for workspace admins. The share flows down to the boards inside this
    one (see ``plane.sharing.board_access``).
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        return Response(_board_sharing(_board(slug, project_id)))

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug, project_id):
        project = _board(slug, project_id)
        if project.is_private or project.private_owner_id:
            return Response(
                {"error": "A private board cannot be shared. Turn off Private first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        group = _group_in_workspace(slug, request.data.get("group_id"))
        level = request.data.get("level", AccessLevel.VIEW)
        if level not in AccessLevel.values:
            raise ValidationError({"level": f"Unknown level {level!r}."})
        with transaction.atomic():
            share, created = ProjectShare.objects.update_or_create(
                project=project,
                group=group,
                defaults={"workspace_id": project.workspace_id, "level": level, "created_by": request.user},
            )
            # A share on this board replaces an exclusion for the same group here.
            ProjectShareExclusion.objects.filter(project=project, group=group).delete()
        return Response(
            _board_sharing(project), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, project_id, group_id):
        ProjectShare.objects.filter(project__workspace__slug=slug, project_id=project_id, group_id=group_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectGroupShareEndpoint(ProjectGroupShareViews, BaseAPIView):
    pass


class ProjectGroupExclusionViews:
    """"Not this board": stop a group's inherited share at this board and everything inside it.

    POST ``{"group_id"}`` adds the exclusion (and drops a direct share for that group
    here); DELETE removes it. Workspace admins only.
    """

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug, project_id):
        project = _board(slug, project_id)
        group = _group_in_workspace(slug, request.data.get("group_id"))
        with transaction.atomic():
            _, created = ProjectShareExclusion.objects.get_or_create(
                project=project,
                group=group,
                defaults={"workspace_id": project.workspace_id, "created_by": request.user},
            )
            ProjectShare.objects.filter(project=project, group=group).delete()
        return Response(
            _board_sharing(project), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, project_id, group_id):
        ProjectShareExclusion.objects.filter(
            project__workspace__slug=slug, project_id=project_id, group_id=group_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectGroupExclusionEndpoint(ProjectGroupExclusionViews, BaseAPIView):
    pass


class ShareTargetSearchEndpoint(BaseAPIView):
    """Picker search: people, departments and groups that an item can be shared with."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request, slug):
        search = (request.query_params.get("search") or "").strip()
        people = User.objects.filter(
            member_workspace__workspace__slug=slug,
            member_workspace__is_active=True,
            member_workspace__deleted_at__isnull=True,
            is_bot=False,
        )
        projects = Project.objects.filter(workspace__slug=slug, deleted_at__isnull=True, archived_at__isnull=True)
        groups = AccessGroup.objects.filter(workspace__slug=slug)
        if search:
            people = people.filter(
                Q(display_name__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )
            projects = projects.filter(name__icontains=search)
            groups = groups.filter(name__icontains=search)
        return Response(
            {
                "people": [
                    {"id": str(user.id), "name": user.display_name or user.first_name or user.email, "avatar": user.avatar_url}
                    for user in people.order_by("display_name")[:20]
                ],
                "projects": [{"id": str(p.id), "name": p.name} for p in projects.order_by("name")[:20]],
                "groups": [
                    {"id": str(g.id), "name": g.name, "member_count": g.member_count}
                    for g in groups.annotate(member_count=Count("members")).order_by("name")[:20]
                ],
                "is_admin": is_workspace_admin(request.user, Workspace.objects.get(slug=slug)),
            }
        )
