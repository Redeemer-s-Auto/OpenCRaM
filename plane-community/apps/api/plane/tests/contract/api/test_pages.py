# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the public (API key) pages endpoints.

/api/v1/workspaces/<slug>/projects/<project_id>/pages/
/api/v1/workspaces/<slug>/projects/<project_id>/pages/<page_id>/
/api/v1/workspaces/<slug>/projects/<project_id>/pages/<page_id>/archive/
"""

from unittest import mock
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Page, Project, ProjectMember, ProjectPage, User, WorkspaceMember
from plane.db.models.api import APIToken


def _list_url(slug, project_id):
    return f"/api/v1/workspaces/{slug}/projects/{project_id}/pages/"


def _detail_url(slug, project_id, page_id):
    return f"/api/v1/workspaces/{slug}/projects/{project_id}/pages/{page_id}/"


def _archive_url(slug, project_id, page_id):
    return f"/api/v1/workspaces/{slug}/projects/{project_id}/pages/{page_id}/archive/"


@pytest.fixture(autouse=True)
def no_background_tasks():
    """Background tasks are not under test here; record the calls instead of queueing them."""
    with (
        mock.patch("plane.api.views.page.page_transaction.delay") as transaction,
        mock.patch("plane.api.views.page.track_page_version.delay") as version,
    ):
        yield {"transaction": transaction, "version": version}


def _make_user(workspace, role):
    user = User.objects.create(email=f"user-{uuid4().hex[:8]}@example.com", username=f"u_{uuid4().hex[:8]}")
    if role is not None:
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    return user


def _client_for(user):
    token = APIToken.objects.create(user=user, label="test", token=f"test-token-{uuid4().hex}")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Pages Project",
        identifier="PGS",
        workspace=workspace,
        created_by=create_user,
        page_view=True,
    )
    ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)
    return project


@pytest.fixture
def member(db, workspace, project):
    user = _make_user(workspace, 15)
    ProjectMember.objects.create(workspace=workspace, project=project, member=user, role=15, is_active=True)
    return user


@pytest.fixture
def member_client(member):
    return _client_for(member)


@pytest.fixture
def outsider_client(db, workspace):
    """A workspace member who is not in the project."""
    return _client_for(_make_user(workspace, 15))


def _make_page(project, owner, **kwargs):
    page = Page.objects.create(
        workspace=project.workspace,
        owned_by=owner,
        name=kwargs.pop("name", "Seed page"),
        description_html=kwargs.pop("description_html", "<p>seed</p>"),
        **kwargs,
    )
    ProjectPage.objects.create(workspace=project.workspace, project=project, page=page)
    return page


@pytest.mark.contract
class TestPagesLifecycle:
    @pytest.mark.django_db
    def test_create_list_read_update_archive_delete(
        self, api_key_client, workspace, project, create_user, no_background_tasks
    ):
        slug = workspace.slug

        # Create
        response = api_key_client.post(
            _list_url(slug, project.id),
            {
                "name": "Call notes",
                "description_html": "<p>Hello <strong>world</strong></p><script>alert(1)</script>",
                "access": 0,
                "logo_props": {"in_use": "emoji", "emoji": {"value": "128221"}},
                "external_source": "crm",
                "external_id": "note-1",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.content
        page_id = response.data["id"]
        assert response.data["name"] == "Call notes"
        assert response.data["owned_by"] == create_user.id
        assert "<strong>world</strong>" in response.data["description_html"]
        assert "<script>" not in response.data["description_html"]
        no_background_tasks["transaction"].assert_called_once()

        page = Page.objects.get(pk=page_id)
        # The live server builds the editor document from the HTML on first open.
        assert page.description_binary is None
        assert page.workspace_id == workspace.id
        assert ProjectPage.objects.filter(page=page, project=project).exists()
        assert page.logo_props["in_use"] == "emoji"

        # Duplicate external id -> 409 with the existing id
        response = api_key_client.post(
            _list_url(slug, project.id),
            {"name": "Again", "external_source": "crm", "external_id": "note-1"},
            format="json",
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["id"] == page_id

        # List
        response = api_key_client.get(_list_url(slug, project.id))
        assert response.status_code == status.HTTP_200_OK
        assert page_id in {str(row["id"]) for row in response.data["results"]}
        assert "description_html" not in response.data["results"][0]

        # Read
        response = api_key_client.get(_detail_url(slug, project.id, page_id))
        assert response.status_code == status.HTTP_200_OK
        assert "<strong>world</strong>" in response.data["description_html"]

        # Update: new HTML drops the stale editor copy so the editor shows the new text
        Page.objects.filter(pk=page_id).update(description_binary=b"stale")
        response = api_key_client.patch(
            _detail_url(slug, project.id, page_id),
            {"name": "Call notes (done)", "description_html": "<p>Updated</p>", "access": 1},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.content
        assert response.data["name"] == "Call notes (done)"
        assert response.data["access"] == 1
        page.refresh_from_db()
        assert page.description_html == "<p>Updated</p>"
        assert page.description_binary is None
        assert page.description_stripped == "Updated"
        no_background_tasks["version"].assert_called_once()

        # Name-only update keeps the editor copy
        Page.objects.filter(pk=page_id).update(description_binary=b"live")
        response = api_key_client.patch(_detail_url(slug, project.id, page_id), {"name": "Renamed"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        page.refresh_from_db()
        assert bytes(page.description_binary) == b"live"

        # Delete before archive is refused
        response = api_key_client.delete(_detail_url(slug, project.id, page_id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Archive
        response = api_key_client.post(_archive_url(slug, project.id, page_id))
        assert response.status_code == status.HTTP_200_OK
        assert Page.objects.get(pk=page_id).archived_at is not None
        listed = api_key_client.get(_list_url(slug, project.id)).data["results"]
        assert page_id not in {str(row["id"]) for row in listed}
        archived = api_key_client.get(_list_url(slug, project.id) + "?archived=true").data["results"]
        assert page_id in {str(row["id"]) for row in archived}

        # Archived pages cannot be edited
        response = api_key_client.patch(_detail_url(slug, project.id, page_id), {"name": "x"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Unarchive, archive again, delete
        response = api_key_client.delete(_archive_url(slug, project.id, page_id))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert Page.objects.get(pk=page_id).archived_at is None
        api_key_client.post(_archive_url(slug, project.id, page_id))
        response = api_key_client.delete(_detail_url(slug, project.id, page_id))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Page.objects.filter(pk=page_id).exists()

    @pytest.mark.django_db
    def test_create_child_page_and_filters(self, api_key_client, workspace, project, create_user):
        parent = _make_page(project, create_user, name="Parent")
        response = api_key_client.post(
            _list_url(workspace.slug, project.id), {"name": "Child", "parent": str(parent.id)}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED, response.content
        assert str(response.data["parent"]) == str(parent.id)

        children = api_key_client.get(_list_url(workspace.slug, project.id) + f"?parent={parent.id}").data
        assert [row["name"] for row in children["results"]] == ["Child"]
        top = api_key_client.get(_list_url(workspace.slug, project.id) + "?parent=null").data
        assert [row["name"] for row in top["results"]] == ["Parent"]

        response = api_key_client.post(
            _list_url(workspace.slug, project.id), {"name": "Orphan", "parent": str(uuid4())}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_invalid_access_value(self, api_key_client, workspace, project):
        response = api_key_client.post(_list_url(workspace.slug, project.id), {"name": "x", "access": 7}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.contract
class TestPagesPermissions:
    @pytest.mark.django_db
    def test_non_member_is_refused(self, outsider_client, workspace, project, create_user):
        page = _make_page(project, create_user)
        assert outsider_client.get(_list_url(workspace.slug, project.id)).status_code in (403, 404)
        assert outsider_client.get(_detail_url(workspace.slug, project.id, page.id)).status_code in (403, 404)
        response = outsider_client.post(_list_url(workspace.slug, project.id), {"name": "x"}, format="json")
        assert response.status_code in (403, 404)
        assert not Page.objects.filter(name="x").exists()

    @pytest.mark.django_db
    def test_page_from_another_project_is_not_reachable(self, api_key_client, workspace, project, create_user):
        other = Project.objects.create(name="Other", identifier="OTH", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(workspace=workspace, project=other, member=create_user, role=20, is_active=True)
        page = _make_page(other, create_user)
        response = api_key_client.get(_detail_url(workspace.slug, project.id, page.id))
        assert response.status_code in (403, 404)

    @pytest.mark.django_db
    def test_private_page_hidden_from_non_owner(self, member_client, workspace, project, create_user):
        private = _make_page(project, create_user, name="Private", access=Page.PRIVATE_ACCESS)
        public = _make_page(project, create_user, name="Public")

        listed = member_client.get(_list_url(workspace.slug, project.id))
        assert listed.status_code == status.HTTP_200_OK
        ids = {str(row["id"]) for row in listed.data["results"]}
        assert str(public.id) in ids
        assert str(private.id) not in ids

        for method in ("get", "patch", "delete"):
            response = getattr(member_client, method)(_detail_url(workspace.slug, project.id, private.id))
            assert response.status_code in (403, 404), method
        assert member_client.post(_archive_url(workspace.slug, project.id, private.id)).status_code in (403, 404)

    @pytest.mark.django_db
    def test_owner_sees_own_private_page(self, member_client, member, workspace, project):
        mine = _make_page(project, member, name="Mine", access=Page.PRIVATE_ACCESS)
        response = member_client.get(_detail_url(workspace.slug, project.id, mine.id))
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_locked_page_refuses_edit(self, api_key_client, workspace, project, create_user):
        page = _make_page(project, create_user, is_locked=True)
        response = api_key_client.patch(
            _detail_url(workspace.slug, project.id, page.id), {"description_html": "<p>new</p>"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        page.refresh_from_db()
        assert page.description_html == "<p>seed</p>"

    @pytest.mark.django_db
    def test_only_owner_changes_access(self, member_client, workspace, project, create_user):
        page = _make_page(project, create_user)
        response = member_client.patch(
            _detail_url(workspace.slug, project.id, page.id), {"access": 1}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # A member may still edit the text of a public page
        response = member_client.patch(
            _detail_url(workspace.slug, project.id, page.id), {"name": "Edited by member"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_member_cannot_archive_or_delete_others_page(self, member_client, workspace, project, create_user):
        page = _make_page(project, create_user, archived_at=timezone.now().date())
        assert member_client.delete(_detail_url(workspace.slug, project.id, page.id)).status_code == 403
        assert member_client.delete(_archive_url(workspace.slug, project.id, page.id)).status_code == 403
        live = _make_page(project, create_user, name="Live")
        assert member_client.post(_archive_url(workspace.slug, project.id, live.id)).status_code == 403
        assert Page.objects.filter(pk=page.id).exists()
        assert Page.objects.get(pk=live.id).archived_at is None

    @pytest.mark.django_db
    def test_member_manages_own_page(self, member_client, member, workspace, project):
        response = member_client.post(_list_url(workspace.slug, project.id), {"name": "Member page"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        page_id = response.data["id"]
        assert member_client.post(_archive_url(workspace.slug, project.id, page_id)).status_code == 200
        assert member_client.delete(_detail_url(workspace.slug, project.id, page_id)).status_code == 204

    @pytest.mark.django_db
    def test_guest_sees_only_own_pages(self, workspace, project, create_user):
        guest = _make_user(workspace, 5)
        ProjectMember.objects.create(workspace=workspace, project=project, member=guest, role=5, is_active=True)
        client = _client_for(guest)
        page = _make_page(project, create_user)
        listed = client.get(_list_url(workspace.slug, project.id))
        assert listed.status_code == status.HTTP_200_OK
        assert listed.data["results"] == []
        assert client.get(_detail_url(workspace.slug, project.id, page.id)).status_code == 404
        assert client.post(_list_url(workspace.slug, project.id), {"name": "g"}, format="json").status_code == 403
