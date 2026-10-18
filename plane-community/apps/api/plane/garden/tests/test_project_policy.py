# SPDX-License-Identifier: AGPL-3.0-only

import json

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.db.models import Q
from rest_framework.response import Response

from plane.app.permissions.base import ROLE, allow_permission
from plane.db.models import Project, ProjectMember, ProjectNetwork
from plane.garden.middleware import GardenAuthorizationMiddleware
from plane.garden.services.firebase_identity import GardenFirebasePrincipal
from plane.garden.services.project_policy import (
    guest_role_supports_broad_read_only,
    harden_garden_workspace_projects,
)
from plane.garden.services.provisioning import reconcile_principal


def principal(uid, email, capabilities):
    return GardenFirebasePrincipal(
        uid=uid,
        email=email,
        email_verified=True,
        display_name=email.split("@")[0],
        first_name="Garden",
        last_name="Staff",
        photo_url="",
        roles=("staff",),
        capabilities=tuple(capabilities),
    )


def setup_workspace(monkeypatch):
    monkeypatch.setenv("GARDEN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    monkeypatch.setenv("GARDEN_WORKSPACE_SLUG", "the-garden")
    admin_user, workspace, _ = reconcile_principal(
        principal("admin", "admin@example.com", ("work.read", "work.admin"))
    )
    member_user, _, _ = reconcile_principal(
        principal("member", "member@example.com", ("work.read", "work.manage"))
    )
    return admin_user, member_user, workspace


@pytest.mark.django_db
@pytest.mark.unit
def test_garden_hardening_forces_projects_secret(monkeypatch):
    admin_user, _, workspace = setup_workspace(monkeypatch)
    project = Project.objects.create(
        name="Production",
        identifier="PROD",
        workspace=workspace,
        network=ProjectNetwork.PUBLIC.value,
        created_by=admin_user,
    )
    assert project.network == ProjectNetwork.PUBLIC.value

    changed = harden_garden_workspace_projects(workspace)
    project.refresh_from_db()

    assert changed == 1
    assert project.network == ProjectNetwork.SECRET.value


@pytest.mark.django_db
@pytest.mark.unit
def test_workspace_member_cannot_see_unrelated_secret_project(monkeypatch):
    admin_user, member_user, workspace = setup_workspace(monkeypatch)
    unrelated = Project.objects.create(
        name="Kids",
        identifier="KIDS",
        workspace=workspace,
        network=ProjectNetwork.SECRET.value,
        created_by=admin_user,
    )

    visible = Project.objects.filter(workspace=workspace).filter(
        Q(project_projectmember__member=member_user, project_projectmember__is_active=True)
        | Q(network=ProjectNetwork.PUBLIC.value)
    )
    assert not visible.filter(id=unrelated.id).exists()


@pytest.mark.django_db
@pytest.mark.unit
def test_native_project_and_membership_governance_is_blocked_for_non_admins(monkeypatch):
    admin_user, member_user, workspace = setup_workspace(monkeypatch)
    project = Project.objects.create(
        name="Production",
        identifier="PROD",
        workspace=workspace,
        network=ProjectNetwork.SECRET.value,
        created_by=admin_user,
    )
    middleware = GardenAuthorizationMiddleware(lambda request: HttpResponse(status=204))
    factory = RequestFactory()

    member_create_request = factory.post("/api/workspaces/the-garden/projects/", data="{}", content_type="application/json")
    member_create_request.user = member_user
    assert middleware(member_create_request).status_code == 403

    admin_create_request = factory.post("/api/workspaces/the-garden/projects/", data="{}", content_type="application/json")
    admin_create_request.user = admin_user
    assert middleware(admin_create_request).status_code == 204

    member_request = factory.post(
        f"/api/workspaces/the-garden/projects/{project.id}/members/",
        data=json.dumps({"members": []}),
        content_type="application/json",
    )
    member_request.user = admin_user
    assert middleware(member_request).status_code == 403

    workspace_role_request = factory.patch(
        f"/api/workspaces/the-garden/members/{member_user.id}/",
        data=json.dumps({"role": 20}),
        content_type="application/json",
    )
    workspace_role_request.user = admin_user
    assert middleware(workspace_role_request).status_code == 403


@pytest.mark.django_db
@pytest.mark.unit
def test_garden_identity_fields_cannot_be_mutated_from_plane(monkeypatch):
    admin_user, _, _ = setup_workspace(monkeypatch)
    middleware = GardenAuthorizationMiddleware(lambda request: HttpResponse(status=204))
    factory = RequestFactory()

    identity_update = factory.patch(
        "/api/users/me/",
        data=json.dumps({"display_name": "Local Work Alias", "avatar_url": "https://evil.example/avatar.jpg"}),
        content_type="application/json",
    )
    identity_update.user = admin_user
    response = middleware(identity_update)
    assert response.status_code == 403
    assert response.json()["error"].startswith("Garden manages staff identity")

    work_preference_update = factory.patch(
        "/api/users/me/",
        data=json.dumps({"user_timezone": "America/Chicago"}),
        content_type="application/json",
    )
    work_preference_update.user = admin_user
    assert middleware(work_preference_update).status_code == 204

    deactivate = factory.delete("/api/users/me/")
    deactivate.user = admin_user
    assert middleware(deactivate).status_code == 403

    email_update = factory.patch(
        "/api/users/me/email/",
        data=json.dumps({"email": "other@example.com"}),
        content_type="application/json",
    )
    email_update.user = admin_user
    assert middleware(email_update).status_code == 403


@pytest.mark.django_db
@pytest.mark.unit
def test_global_admin_project_access_materializes_missing_project_membership(monkeypatch):
    admin_user, _, workspace = setup_workspace(monkeypatch)
    project = Project.objects.create(
        name="Imported Project",
        identifier="IMPRT",
        workspace=workspace,
        network=ProjectNetwork.SECRET.value,
        created_by=admin_user,
    )
    ProjectMember.objects.filter(project=project, member=admin_user).delete()
    assert not ProjectMember.objects.filter(project=project, member=admin_user).exists()

    request = RequestFactory().get(f"/api/workspaces/the-garden/projects/{project.id}/")
    request.user = admin_user
    response = GardenAuthorizationMiddleware(lambda req: HttpResponse(status=204))(request)

    assert response.status_code == 204
    membership = ProjectMember.objects.get(project=project, member=admin_user)
    assert membership.role == ROLE.ADMIN.value
    assert membership.is_active is True


@pytest.mark.django_db
@pytest.mark.unit
def test_public_network_update_is_normalized_to_secret_without_403(monkeypatch):
    admin_user, _, workspace = setup_workspace(monkeypatch)
    project = Project.objects.create(
        name="Production",
        identifier="PROD",
        workspace=workspace,
        network=ProjectNetwork.SECRET.value,
        created_by=admin_user,
    )
    seen = {}

    def endpoint(request):
        seen.update(json.loads(request.body.decode("utf-8")))
        return HttpResponse(status=200)

    request = RequestFactory().patch(
        f"/api/workspaces/the-garden/projects/{project.id}/",
        data=json.dumps({"name": "Production", "network": ProjectNetwork.PUBLIC.value}),
        content_type="application/json",
    )
    request.user = admin_user
    response = GardenAuthorizationMiddleware(endpoint)(request)

    assert response.status_code == 200
    assert seen["network"] == ProjectNetwork.SECRET.value


@pytest.mark.django_db
@pytest.mark.unit
def test_project_delete_requires_global_work_admin(monkeypatch):
    admin_user, member_user, workspace = setup_workspace(monkeypatch)
    project = Project.objects.create(
        name="Production",
        identifier="PROD",
        workspace=workspace,
        network=ProjectNetwork.SECRET.value,
        created_by=admin_user,
    )
    middleware = GardenAuthorizationMiddleware(lambda request: HttpResponse(status=204))
    factory = RequestFactory()
    path = f"/api/workspaces/the-garden/projects/{project.id}/"

    member_delete = factory.delete(path)
    member_delete.user = member_user
    assert middleware(member_delete).status_code == 403

    admin_delete = factory.delete(path)
    admin_delete.user = admin_user
    assert middleware(admin_delete).status_code == 204


@pytest.mark.django_db
@pytest.mark.unit
def test_project_member_role_15_keeps_normal_work_item_permissions(monkeypatch):
    admin_user, member_user, workspace = setup_workspace(monkeypatch)
    project = Project.objects.create(
        name="Production",
        identifier="PROD",
        workspace=workspace,
        network=ProjectNetwork.SECRET.value,
        created_by=admin_user,
    )
    ProjectMember.objects.create(project=project, member=member_user, role=ROLE.MEMBER.value)

    class DummyProjectEndpoint:
        @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
        def create_work_item(self, request, slug, project_id):
            return Response({"ok": True}, status=200)

    request = RequestFactory().post("/work-item")
    request.user = member_user
    response = DummyProjectEndpoint().create_work_item(
        request,
        slug=workspace.slug,
        project_id=project.id,
    )
    assert response.status_code == 200

    middleware = GardenAuthorizationMiddleware(lambda req: HttpResponse(status=204))
    work_request = RequestFactory().post(
        f"/api/workspaces/the-garden/projects/{project.id}/issues/",
        data="{}",
        content_type="application/json",
    )
    work_request.user = member_user
    assert middleware(work_request).status_code == 204


@pytest.mark.django_db
@pytest.mark.unit
def test_guest_role_is_not_assumed_to_be_broad_read_only(monkeypatch):
    admin_user, _, workspace = setup_workspace(monkeypatch)
    project = Project.objects.create(
        name="Read Only",
        identifier="READ",
        workspace=workspace,
        network=ProjectNetwork.SECRET.value,
        guest_view_all_features=False,
        created_by=admin_user,
    )
    assert guest_role_supports_broad_read_only(project) is False
    project.guest_view_all_features = True
    assert guest_role_supports_broad_read_only(project) is True
