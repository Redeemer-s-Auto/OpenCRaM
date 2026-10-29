# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Public API additions an importer needs: private boards from the start, and card templates."""

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import IssueTemplate, Project, ProjectMember, State, User, WorkspaceMember
from plane.db.models.api import APIToken


@pytest.fixture(autouse=True)
def _reset_api_key_throttle():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def other_admin(db, workspace):
    user = User.objects.create(email=f"admin-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
    return user


def _key_client(user):
    token = APIToken.objects.create(user=user, label="other", token=f"tok-{uuid4().hex}")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.mark.contract
@pytest.mark.django_db
class TestPrivateBoardsThroughV1:
    def test_create_private_invite_only_board(self, api_key_client, workspace, other_admin):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/"
        response = api_key_client.post(
            url,
            {"name": "Imported", "identifier": "IMP", "network": 0, "is_private": True,
             "external_source": "notion", "external_id": "abc"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        project = Project.objects.get(pk=response.data["id"])
        assert project.is_private is True
        assert project.network == 0
        assert response.data["is_private"] is True

        # another workspace admin who is not a member does not see it, through v1 either
        seen = _key_client(other_admin).get(url)
        ids = {str(p["id"]) for p in (seen.data.get("results") if isinstance(seen.data, dict) else seen.data)}
        assert str(project.id) not in ids

    def test_default_stays_public(self, api_key_client, workspace):
        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/projects/", {"name": "Open", "identifier": "OPN"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert Project.objects.get(pk=response.data["id"]).is_private is False

    def test_bad_network_refused(self, api_key_client, workspace):
        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/projects/",
            {"name": "Odd", "identifier": "ODD", "network": 7},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_admin_can_make_board_private_later(self, api_key_client, workspace, create_user):
        project = Project.objects.create(name="Later", identifier="LAT", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
        response = api_key_client.patch(
            f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/", {"is_private": True}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        project.refresh_from_db()
        assert project.is_private is True

    def test_plain_member_cannot_change_privacy(self, workspace, create_user):
        member = User.objects.create(email=f"m-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
        WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
        project = Project.objects.create(name="Shared", identifier="SHR", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=project, member=member, workspace=workspace, role=15)
        response = _key_client(member).patch(
            f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/", {"is_private": True}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        project.refresh_from_db()
        assert project.is_private is False


@pytest.mark.contract
@pytest.mark.django_db
class TestAssetUploadThroughV1:
    def test_asset_upload_link_is_made(self, api_key_client, workspace, create_user, monkeypatch):
        """Was a 500: the v1 asset views pass is_server=True, which S3Storage did not accept.

        The real S3Storage is used (other tests mock it, which hid the crash); signing a POST
        policy needs no network."""
        for key, value in {"AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test-secret",
                           "AWS_S3_BUCKET_NAME": "uploads", "AWS_REGION": "us-east-1",
                           "AWS_S3_ENDPOINT_URL": "http://minio.invalid:9000", "USE_MINIO": "0"}.items():
            monkeypatch.setenv(key, value)
        project = Project.objects.create(name="Img", identifier="IMG", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
        response = api_key_client.post(
            f"/api/v1/workspaces/{workspace.slug}/assets/",
            {"name": "photo.png", "type": "image/png", "size": 100, "project_id": str(project.id),
             "external_source": "notion", "external_id": "img-1"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["asset_id"]
        assert "url" in response.data["upload_data"]


@pytest.mark.contract
@pytest.mark.django_db
class TestTemplatesThroughV1:
    @pytest.fixture
    def board(self, workspace, create_user):
        project = Project.objects.create(name="Tpl", identifier="TPL", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
        State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted")
        return project

    def test_list_create_update_delete(self, api_key_client, workspace, board):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{board.id}/work-item-templates/"
        state = State.objects.get(project=board, name="Todo")
        response = api_key_client.post(
            url,
            {"name": "Weekly check", "data": {"name": "Check", "description_html": "<p>Steps</p>",
                                             "state_id": str(state.id)}},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        tid = response.data["id"]
        assert response.data["data"]["state_id"] == str(state.id)
        assert [t["name"] for t in api_key_client.get(url).data] == ["Weekly check"]
        assert api_key_client.post(url, {"name": "weekly CHECK", "data": {}}, format="json").status_code == 400
        assert api_key_client.patch(f"{url}{tid}/", {"name": "Monthly"}, format="json").data["name"] == "Monthly"
        assert api_key_client.delete(f"{url}{tid}/").status_code == 204
        assert not IssueTemplate.objects.filter(pk=tid).exists()

    def test_non_member_refused(self, workspace, board, other_admin):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{board.id}/work-item-templates/"
        response = _key_client(other_admin).get(url)
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
