# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import json


# Django imports
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Exists, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Count
from django.db.models.functions import Coalesce
from django.utils import timezone

# Third Party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, ProjectMemberPermission, allow_permission
from plane.app.serializers import (
    DeployBoardSerializer,
    ProjectListSerializer,
    ProjectSerializer,
)
from plane.app.views.base import BaseAPIView, BaseViewSet
from plane.bgtasks.recent_visited_task import recent_visited_task
from plane.bgtasks.webhook_task import model_activity, webhook_activity
from plane.db.models import (
    UserFavorite,
    DeployBoard,
    Intake,
    Project,
    ProjectIdentifier,
    ProjectMember,
    ProjectNetwork,
    ProjectUserProperty,
    State,
    DEFAULT_STATES,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.intake import IntakeIssueStatus
from plane.sharing.board_access import project_share_level, shared_role_expr
from plane.sharing.placement import section_of
from plane.sharing.visibility import hidden_issue_ids
from plane.utils.private_projects import visible_projects_q
from plane.utils.project_tree import visible_parent_id_expr, visible_project_ids
from plane.utils.host import base_host
from plane.utils.order_queryset import PROJECT_ORDER_BY_ALLOWLIST, sanitize_order_by


class ProjectViewSet(BaseViewSet):
    serializer_class = ProjectListSerializer
    model = Project
    webhook_event = "project"
    use_read_replica = True

    def get_queryset(self):
        sort_order = ProjectUserProperty.objects.filter(
            user=self.request.user,
            project_id=OuterRef("pk"),
            workspace__slug=self.kwargs.get("slug"),
        ).values("sort_order")
        return self.filter_queryset(
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("slug"))
            .filter(visible_projects_q(self.request.user, slug=self.kwargs.get("slug")))
            .select_related("workspace", "workspace__owner", "default_assignee", "project_lead", "teamspace")
            .annotate(
                is_favorite=Exists(
                    UserFavorite.objects.filter(
                        user=self.request.user,
                        entity_identifier=OuterRef("pk"),
                        entity_type="project",
                        project_id=OuterRef("pk"),
                    )
                )
            )
            .annotate(member_role=self._member_role_expr())
            .annotate(
                anchor=DeployBoard.objects.filter(
                    entity_name="project",
                    entity_identifier=OuterRef("pk"),
                    workspace__slug=self.kwargs.get("slug"),
                ).values("anchor")
            )
            .annotate(sort_order=Subquery(sort_order))
            .annotate(visible_parent_id=visible_parent_id_expr(self.request.user, slug=self.kwargs.get("slug")))
            .prefetch_related(
                Prefetch(
                    "project_projectmember",
                    queryset=ProjectMember.objects.filter(
                        workspace__slug=self.kwargs.get("slug"), is_active=True
                    ).select_related("member"),
                    to_attr="members_list",
                )
            )
            .distinct()
        )

    def _project_for_response(self, pk):
        """The board as the caller sees it after a write; the bare row when the write just hid it from them.

        A workspace admin who moves a board into someone else's Private area, or a
        teamspace they are not in, gets its data back once more and never again.
        """
        return self.get_queryset().filter(pk=pk).first() or Project.objects.get(pk=pk)

    def _member_role_expr(self):
        """The user's project role; on a board a group share reaches, the share's stand-in role."""
        membership = ProjectMember.objects.filter(
            project_id=OuterRef("pk"),
            member_id=self.request.user.id,
            is_active=True,
        ).values("role")[:1]
        return Coalesce(
            Subquery(membership),
            shared_role_expr(self.request.user, slug=self.kwargs.get("slug")),
            output_field=IntegerField(),
        )

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def list_detail(self, request, slug):
        fields = [field for field in request.GET.get("fields", "").split(",") if field]
        # One rule for "which boards can this person see": membership, network, private,
        # and boards shared with the user's groups. See plane.utils.project_tree.
        projects = (
            self.get_queryset().filter(id__in=visible_project_ids(request.user, slug=slug)).order_by("sort_order", "name")
        )

        if request.GET.get("per_page", False) and request.GET.get("cursor", False):
            return self.paginate(
                order_by=sanitize_order_by(
                    request.GET.get("order_by", "-created_at"),
                    PROJECT_ORDER_BY_ALLOWLIST,
                    "-created_at",
                ),
                request=request,
                queryset=(projects),
                on_results=lambda projects: ProjectListSerializer(projects, many=True).data,
            )

        projects = ProjectListSerializer(projects, many=True, fields=fields if fields else None).data
        return Response(projects, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def list(self, request, slug):
        sort_order = ProjectUserProperty.objects.filter(
            user=self.request.user,
            project_id=OuterRef("pk"),
            workspace__slug=self.kwargs.get("slug"),
        ).values("sort_order")

        projects = (
            Project.objects.filter(workspace__slug=self.kwargs.get("slug"))
            .filter(visible_projects_q(self.request.user, slug=slug))
            .select_related("workspace", "workspace__owner", "default_assignee", "project_lead")
            .annotate(member_role=self._member_role_expr())
            .annotate(
                intake_count=Count(
                    "project_intakeissue",
                    filter=Q(
                        project_intakeissue__status=IntakeIssueStatus.PENDING.value,
                        project_intakeissue__deleted_at__isnull=True,
                    )
                    & ~Q(project_intakeissue__issue_id__in=hidden_issue_ids(self.request.user)),
                )
            )
            .annotate(inbox_view=F("intake_view"))
            .annotate(sort_order=Subquery(sort_order))
            .annotate(visible_parent_id=visible_parent_id_expr(self.request.user, slug=slug))
            .distinct()
        ).values(
            "id",
            "name",
            "identifier",
            "sort_order",
            "logo_props",
            "member_role",
            "intake_count",
            "archived_at",
            "workspace",
            "cycle_view",
            "issue_views_view",
            "module_view",
            "page_view",
            "inbox_view",
            "guest_view_all_features",
            "project_lead",
            "network",
            "is_private",
            "visible_parent_id",
            "teamspace_id",
            "private_owner_id",
            "is_sealed",
            "teamspace__name",
            "teamspace__slug",
            "teamspace__position",
            "teamspace__is_default",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )

        # One rule for "which boards can this person see" (plane.utils.project_tree).
        projects = projects.filter(id__in=visible_project_ids(request.user, slug=slug))
        # parent_id is a model field, so the masked value is annotated under another name.
        projects = list(projects)
        for project in projects:
            project["parent_id"] = project.pop("visible_parent_id")
            # Sidebar section and teamspace header, so the sidebar groups without a second call.
            project["section"] = section_of(project["teamspace_id"], project["private_owner_id"])
            project["teamspace_detail"] = (
                {
                    "id": str(project["teamspace_id"]),
                    "name": project["teamspace__name"],
                    "slug": project["teamspace__slug"],
                    "position": project["teamspace__position"],
                    "is_default": project["teamspace__is_default"],
                }
                if project["teamspace_id"]
                else None
            )
            for key in ("teamspace__name", "teamspace__slug", "teamspace__position", "teamspace__is_default"):
                project.pop(key)
        return Response(projects, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=[ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def retrieve(self, request, slug, pk):
        project = self.get_queryset().filter(archived_at__isnull=True).filter(pk=pk).first()

        if project is None:
            return Response({"error": "Project does not exist"}, status=status.HTTP_404_NOT_FOUND)

        member_ids = [str(project_member.member_id) for project_member in project.members_list]

        # A board shared with one of the user's groups opens like a board they belong to.
        if str(request.user.id) not in member_ids and not project_share_level(request.user, pk, slug=slug):
            if project.network == ProjectNetwork.SECRET.value:
                return Response(
                    {"error": "You do not have permission"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            else:
                return Response(
                    {"error": "You are not a member of this project"},
                    status=status.HTTP_409_CONFLICT,
                )

        recent_visited_task.delay(
            slug=slug,
            project_id=pk,
            entity_name="project",
            entity_identifier=pk,
            user_id=request.user.id,
        )

        serializer = ProjectListSerializer(project)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def create(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)

        # Plane Pages are retired in this fork (cards are the pages): new projects start with Pages off.
        serializer = ProjectSerializer(
            data={"page_view": False, **request.data}, context={"workspace_id": workspace.id, "user": request.user}
        )
        if serializer.is_valid():
            serializer.save()

            # Add the user as Administrator to the project
            _ = ProjectMember.objects.create(
                project_id=serializer.data["id"],
                member=request.user,
                role=ROLE.ADMIN.value,
            )

            if serializer.data["project_lead"] is not None and str(serializer.data["project_lead"]) != str(
                request.user.id
            ):
                ProjectMember.objects.create(
                    project_id=serializer.data["id"],
                    member_id=serializer.data["project_lead"],
                    role=ROLE.ADMIN.value,
                )

            State.objects.bulk_create(
                [
                    State(
                        name=state["name"],
                        color=state["color"],
                        project=serializer.instance,
                        sequence=state["sequence"],
                        workspace=serializer.instance.workspace,
                        group=state["group"],
                        default=state.get("default", False),
                        created_by=request.user,
                    )
                    for state in DEFAULT_STATES
                ]
            )

            # Where the board sits (private=true, teamspace_id, private_owner_id): applied after the
            # memberships above, so a board put in someone's Private area keeps only that person.
            serializer.apply_placement(actor=request.user)

            project = self._project_for_response(serializer.data["id"])

            # Create the model activity
            model_activity.delay(
                model_name="project",
                model_id=str(project.id),
                requested_data=request.data,
                current_instance=None,
                actor_id=request.user.id,
                slug=slug,
                origin=base_host(request=request, is_app=True),
            )

            serializer = ProjectListSerializer(project)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, slug, pk=None):
        # try:
        is_workspace_admin = WorkspaceMember.objects.filter(
            member=request.user,
            workspace__slug=slug,
            is_active=True,
            role=ROLE.ADMIN.value,
        ).exists()

        is_project_admin = ProjectMember.objects.filter(
            member=request.user,
            workspace__slug=slug,
            project_id=pk,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

        # Return error for if the user is neither workspace admin nor project admin
        if not is_project_admin and not is_workspace_admin:
            return Response(
                {"error": "You don't have the required permissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        workspace = Workspace.objects.get(slug=slug)

        project = Project.objects.get(pk=pk, workspace__slug=slug)
        intake_view = request.data.get("inbox_view", project.intake_view)
        current_instance = json.dumps(ProjectSerializer(project).data, cls=DjangoJSONEncoder)
        if project.archived_at:
            return Response(
                {"error": "Archived projects cannot be updated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProjectSerializer(
            project,
            data={**request.data, "intake_view": intake_view},
            context={"workspace_id": workspace.id, "user": request.user},
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()
            if intake_view:
                intake = Intake.objects.filter(project=project, is_default=True).first()
                if not intake:
                    Intake.objects.create(
                        name=f"{project.name} Intake",
                        project=project,
                        is_default=True,
                    )

            project = self._project_for_response(serializer.data["id"])

            model_activity.delay(
                model_name="project",
                model_id=str(project.id),
                requested_data=request.data,
                current_instance=current_instance,
                actor_id=request.user.id,
                slug=slug,
                origin=base_host(request=request, is_app=True),
            )
            serializer = ProjectListSerializer(project)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, slug, pk):
        if (
            WorkspaceMember.objects.filter(
                member=request.user,
                workspace__slug=slug,
                is_active=True,
                role=ROLE.ADMIN.value,
            ).exists()
            or ProjectMember.objects.filter(
                member=request.user,
                workspace__slug=slug,
                project_id=pk,
                role=ROLE.ADMIN.value,
                is_active=True,
            ).exists()
        ):
            project = Project.objects.get(pk=pk, workspace__slug=slug)
            project.delete()
            webhook_activity.delay(
                event="project",
                verb="deleted",
                field=None,
                old_value=None,
                new_value=None,
                actor_id=request.user.id,
                slug=slug,
                current_site=base_host(request=request, is_app=True),
                event_id=project.id,
                old_identifier=None,
                new_identifier=None,
            )
            # Delete the project members
            DeployBoard.objects.filter(project_id=pk, workspace__slug=slug).delete()

            # Delete the user favorite
            UserFavorite.objects.filter(project_id=pk, workspace__slug=slug).delete()

            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {"error": "You don't have the required permissions."},
                status=status.HTTP_403_FORBIDDEN,
            )


class ProjectArchiveUnarchiveEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        project.archived_at = timezone.now()
        project.save()
        UserFavorite.objects.filter(workspace__slug=slug, project=project_id).delete()
        return Response({"archived_at": str(project.archived_at)}, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def delete(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        project.archived_at = None
        project.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectIdentifierEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request, slug):
        name = request.GET.get("name", "").strip().upper()

        if name == "":
            return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)

        exists = ProjectIdentifier.objects.filter(name=name, workspace__slug=slug).values("id", "name", "project")

        return Response({"exists": len(exists), "identifiers": exists}, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def delete(self, request, slug):
        name = request.data.get("name", "").strip().upper()

        if name == "":
            return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)

        if Project.objects.filter(identifier=name, workspace__slug=slug).exists():
            return Response(
                {"error": "Cannot delete an identifier of an existing project"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ProjectIdentifier.objects.filter(name=name, workspace__slug=slug).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectUserViewsEndpoint(BaseAPIView):
    def post(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)

        project_member = ProjectMember.objects.filter(member=request.user, project=project, is_active=True).first()

        if project_member is None:
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        view_props = project_member.view_props
        default_props = project_member.default_props
        preferences = project_member.preferences
        sort_order = project_member.sort_order

        project_member.view_props = request.data.get("view_props", view_props)
        project_member.default_props = request.data.get("default_props", default_props)
        project_member.preferences = request.data.get("preferences", preferences)
        project_member.sort_order = request.data.get("sort_order", sort_order)

        project_member.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectFavoritesViewSet(BaseViewSet):
    model = UserFavorite

    def get_queryset(self):
        return self.filter_queryset(
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("slug"))
            .filter(user=self.request.user)
            .select_related("project", "project__project_lead", "project__default_assignee")
            .select_related("workspace", "workspace__owner")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, slug):
        _ = UserFavorite.objects.create(
            user=request.user,
            entity_type="project",
            entity_identifier=request.data.get("project"),
            project_id=request.data.get("project"),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def destroy(self, request, slug, project_id):
        project_favorite = UserFavorite.objects.get(
            entity_identifier=project_id,
            entity_type="project",
            project=project_id,
            user=request.user,
            workspace__slug=slug,
        )
        project_favorite.delete(soft=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeployBoardViewSet(BaseViewSet):
    permission_classes = [ProjectMemberPermission]
    serializer_class = DeployBoardSerializer
    model = DeployBoard

    def list(self, request, slug, project_id):
        project_deploy_board = DeployBoard.objects.filter(
            entity_name="project", entity_identifier=project_id, workspace__slug=slug
        ).first()

        serializer = DeployBoardSerializer(project_deploy_board)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, slug, project_id):
        if Project.objects.filter(pk=project_id, is_private=True).exists():
            return Response(
                {"error": "A private project cannot be published. Turn off Private project first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        comments = request.data.get("is_comments_enabled", False)
        reactions = request.data.get("is_reactions_enabled", False)
        intake = request.data.get("intake", None)
        votes = request.data.get("is_votes_enabled", False)
        views = request.data.get(
            "views",
            {
                "list": True,
                "kanban": True,
                "calendar": True,
                "gantt": True,
                "spreadsheet": True,
            },
        )

        project_deploy_board, _ = DeployBoard.objects.get_or_create(
            entity_name="project", entity_identifier=project_id, project_id=project_id
        )
        project_deploy_board.intake = intake
        project_deploy_board.view_props = views
        project_deploy_board.is_votes_enabled = votes
        project_deploy_board.is_comments_enabled = comments
        project_deploy_board.is_reactions_enabled = reactions

        project_deploy_board.save()

        serializer = DeployBoardSerializer(project_deploy_board)
        return Response(serializer.data, status=status.HTTP_200_OK)
