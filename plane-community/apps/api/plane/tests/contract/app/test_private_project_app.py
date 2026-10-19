# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Private projects: only active members see them - workspace admins included."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import (
    CustomField,
    Issue,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)
from plane.db.models.api import APIToken


@pytest.fixture
def private_project(db, workspace, create_user):
    project = Project.objects.create(
        name="Personal", identifier="PERS", workspace=workspace, created_by=create_user, is_private=True, network=2
    )
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def card(db, workspace, private_project, create_user):
    state = State.objects.create(name="Todo", project=private_project, workspace=workspace, group="backlog")
    issue = Issue(name="Private note", project=private_project, workspace=workspace, state=state)
    issue.save(created_by_id=create_user.id)
    return issue


@pytest.fixture
def other_admin(db, workspace):
    user = User.objects.create(email=f"admin-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.contract
@pytest.mark.django_db
class TestPrivateProject:
    def test_owner_sees_everything(self, session_client, workspace, private_project, card):
        base = f"/api/workspaces/{workspace.slug}/projects/"
        assert str(private_project.id) in {str(p["id"]) for p in session_client.get(base).data}
        assert session_client.get(f"{base}{private_project.id}/").status_code == 200
        assert session_client.get(f"{base}{private_project.id}/issues/{card.id}/").status_code == 200

    def test_other_admin_sees_nothing(self, other_admin, workspace, private_project, card):
        client = _client(other_admin)
        base = f"/api/workspaces/{workspace.slug}/projects/"
        # Not in the project lists, not even the name.
        assert str(private_project.id) not in {str(p["id"]) for p in client.get(base).data}
        detail_list = client.get(f"/api/workspaces/{workspace.slug}/projects/details/")
        if detail_list.status_code == 200:
            assert str(private_project.id) not in {str(p["id"]) for p in detail_list.data}
        # Every project-scoped URL answers 404.
        for path in [
            f"{base}{private_project.id}/",
            f"{base}{private_project.id}/issues/",
            f"{base}{private_project.id}/issues/{card.id}/",
            f"{base}{private_project.id}/custom-fields/",
            f"{base}{private_project.id}/members/",
            f"{base}{private_project.id}/states/",
        ]:
            assert client.get(path).status_code == 404, path
        # Cannot write either.
        assert (
            client.patch(f"{base}{private_project.id}/issues/{card.id}/", {"name": "x"}, format="json").status_code
            == 404
        )
        assert client.patch(f"{base}{private_project.id}/", {"is_private": False}, format="json").status_code == 404
        assert client.delete(f"{base}{private_project.id}/").status_code == 404

    def test_other_admin_cannot_join(self, other_admin, workspace, private_project):
        client = _client(other_admin)
        client.post(
            f"/api/workspaces/{workspace.slug}/projects/join/",
            {"project_ids": [str(private_project.id)]},
            format="json",
        )
        assert not ProjectMember.objects.filter(project=private_project, member=other_admin, is_active=True).exists()

    def test_search_hides_private_project(self, other_admin, workspace, private_project):
        client = _client(other_admin)
        response = client.get(f"/api/workspaces/{workspace.slug}/search/", {"search": "Personal"})
        if response.status_code == 200:
            projects = response.data.get("results", response.data).get("project", [])
            assert all(str(p["id"]) != str(private_project.id) for p in projects)

    def test_public_api_hides_private_project(self, other_admin, workspace, private_project, card):
        token = APIToken.objects.create(user=other_admin, label="t", token=f"tok-{uuid4().hex}")
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=token.token)
        base = f"/api/v1/workspaces/{workspace.slug}/projects/"
        listed = client.get(base)
        rows = listed.data.get("results", listed.data) if isinstance(listed.data, dict) else listed.data
        assert str(private_project.id) not in {str(p["id"]) for p in rows}
        assert client.get(f"{base}{private_project.id}/issues/").status_code == 404
        assert client.get(f"{base}{private_project.id}/issues/{card.id}/").status_code == 404
        assert client.get(f"/api/v1/workspaces/{workspace.slug}/issues/PERS-{card.sequence_id}/").status_code == 404

    def test_member_of_private_project_has_access(self, workspace, private_project, card):
        user = User.objects.create(email=f"m-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
        ProjectMember.objects.create(project=private_project, member=user, workspace=workspace, role=15)
        client = _client(user)
        base = f"/api/workspaces/{workspace.slug}/projects/{private_project.id}"
        assert client.get(f"{base}/issues/{card.id}/").status_code == 200

    def test_removed_member_loses_access(self, workspace, private_project, card):
        user = User.objects.create(email=f"r-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
        ProjectMember.objects.create(
            project=private_project, member=user, workspace=workspace, role=20, is_active=False
        )
        client = _client(user)
        assert client.get(f"/api/workspaces/{workspace.slug}/projects/{private_project.id}/issues/").status_code == 404

    def test_custom_field_filter_cannot_probe_private_values(
        self, other_admin, session_client, workspace, private_project, card, create_user
    ):
        """A field id from a private project cannot be used from another project to read values."""
        field = CustomField.objects.create(project=private_project, name="Secret", field_type="text")
        other = Project.objects.create(name="Open", identifier="OPEN", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=other, member=other_admin, workspace=workspace, role=20)
        client = _client(other_admin)
        import json

        response = client.get(
            f"/api/workspaces/{workspace.slug}/projects/{other.id}/issues/",
            {"filters": json.dumps({f"customfield_{field.id}__isnull": False})},
        )
        assert response.status_code in (200, 400)
        if response.status_code == 200:
            results = response.data.get("results", [])
            rows = results if isinstance(results, list) else []
            assert all(str(r["id"]) != str(card.id) for r in rows)


@pytest.mark.contract
@pytest.mark.django_db
class TestPrivateProjectPublicBoards:
    def test_cannot_publish_private_project(self, session_client, workspace, private_project):
        url = f"/api/workspaces/{workspace.slug}/projects/{private_project.id}/project-deploy-boards/"
        assert session_client.post(url, {}, format="json").status_code == 400

    def test_published_board_goes_dark_when_project_turns_private(self, session_client, workspace, create_user):
        from plane.db.models import DeployBoard

        project = Project.objects.create(name="Open", identifier="OPN", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
        url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/project-deploy-boards/"
        assert session_client.post(url, {}, format="json").status_code == 200
        anchor = DeployBoard.objects.get(entity_identifier=project.id).anchor

        public = APIClient()
        assert public.get(f"/api/public/anchor/{anchor}/settings/").status_code == 200
        project.is_private = True
        project.save(update_fields=["is_private"])
        for path in ["settings", "meta", "issues"]:
            assert public.get(f"/api/public/anchor/{anchor}/{path}/").status_code == 404, path
