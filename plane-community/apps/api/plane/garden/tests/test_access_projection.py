# SPDX-License-Identifier: AGPL-3.0-only

import pytest

from plane.db.models import Project, ProjectMember, ProjectNetwork, WorkspaceMember
from plane.garden.models import GardenExternalIdentity
from plane.garden.services.access_projection import apply_work_projection
from plane.garden.services.firebase_identity import GardenFirebasePrincipal
from plane.garden.services.provisioning import reconcile_principal


def principal(uid, email, capabilities=("work.read", "work.manage")):
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


@pytest.mark.django_db
@pytest.mark.unit
def test_projection_applies_only_managed_project_memberships(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    admin, workspace, _ = reconcile_principal(principal("admin", "admin@example.com", ("work.read", "work.admin")))
    user, _, _ = reconcile_principal(principal("member", "member@example.com"))
    managed = Project.objects.create(name="Production", identifier="PROD", workspace=workspace, network=ProjectNetwork.SECRET.value, created_by=admin)
    unmanaged = Project.objects.create(name="Manual", identifier="MAN", workspace=workspace, network=ProjectNetwork.SECRET.value, created_by=admin)
    ProjectMember.objects.create(project=unmanaged, member=user, role=15)

    result = apply_work_projection("member", user, workspace, {
        "accessVersion": 7,
        "workspaceRole": 15,
        "projectionHash": "a" * 64,
        "managedProjectIds": [str(managed.id)],
        "projects": [{"planeProjectId": str(managed.id), "readable": True, "planeRole": 15}],
    })

    assert result["projectMembershipCount"] == 1
    assert ProjectMember.objects.get(project=managed, member=user).role == 15
    assert ProjectMember.objects.get(project=unmanaged, member=user).is_active is True
    identity = GardenExternalIdentity.objects.get(external_id="member")
    assert identity.access_version == 7
    assert identity.projection_hash == "a" * 64


@pytest.mark.django_db
@pytest.mark.unit
def test_projection_revokes_stale_managed_membership_and_workspace_admin(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    admin, workspace, _ = reconcile_principal(principal("admin", "admin@example.com", ("work.read", "work.admin")))
    user, _, membership = reconcile_principal(principal("member", "member@example.com", ("work.read", "work.admin")))
    project = Project.objects.create(name="Production", identifier="PROD", workspace=workspace, network=ProjectNetwork.SECRET.value, created_by=admin)
    ProjectMember.objects.create(project=project, member=user, role=20)
    assert membership.role == 20

    apply_work_projection("member", user, workspace, {
        "accessVersion": 8,
        "workspaceRole": 15,
        "projectionHash": "b" * 64,
        "managedProjectIds": [str(project.id)],
        "projects": [{"planeProjectId": str(project.id), "readable": True, "planeRole": None}],
    })

    workspace_membership = WorkspaceMember.objects.get(workspace=workspace, member=user)
    assert workspace_membership.role == 15
    assert ProjectMember.objects.get(project=project, member=user).is_active is False


@pytest.mark.django_db
@pytest.mark.unit
def test_projection_forces_managed_project_secret(monkeypatch):
    monkeypatch.setenv("GARDEN_WORKSPACE_BOOTSTRAP", "1")
    admin, workspace, _ = reconcile_principal(principal("admin", "admin@example.com", ("work.read", "work.admin")))
    user, _, _ = reconcile_principal(principal("member", "member@example.com"))
    project = Project.objects.create(name="Production", identifier="PROD", workspace=workspace, network=ProjectNetwork.PUBLIC.value, created_by=admin)

    apply_work_projection("member", user, workspace, {
        "accessVersion": 1,
        "workspaceRole": 15,
        "projectionHash": "c" * 64,
        "managedProjectIds": [str(project.id)],
        "projects": [{"planeProjectId": str(project.id), "readable": True, "planeRole": 15}],
    })
    project.refresh_from_db()
    assert project.network == ProjectNetwork.SECRET.value
