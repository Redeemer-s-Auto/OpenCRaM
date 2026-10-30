# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Boards inside boards: Project.parent, exposed as parent_id (app API and public v1 API)."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember, User, Workspace, WorkspaceMember
from plane.db.models.api import APIToken
from plane.utils.project_tree import MAX_PROJECT_TREE_DEPTH


def _project(workspace, user, name, **kwargs):
    project = Project.objects.create(
        name=name, identifier=name[:10].upper(), workspace=workspace, created_by=user, **kwargs
    )
    if user is not None:
        ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=20)
    return project


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _rows(response):
    data = response.data
    return data.get("results", data) if isinstance(data, dict) else data


@pytest.fixture
def parent(db, workspace, create_user):
    return _project(workspace, create_user, "Parent")


@pytest.fixture
def child(db, workspace, create_user):
    return _project(workspace, create_user, "Child")


@pytest.fixture
def other_admin(db, workspace):
    """A workspace admin who is not a member of any project yet."""
    user = User.objects.create(email=f"admin-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
    return user


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectParentApp:
    def url(self, workspace, project=None):
        base = f"/api/workspaces/{workspace.slug}/projects/"
        return f"{base}{project.id}/" if project else base

    def test_set_parent_and_list_it(self, session_client, workspace, parent, child):
        response = session_client.patch(self.url(workspace, child), {"parent_id": str(parent.id)}, format="json")
        assert response.status_code == 200, response.data
        assert str(response.data["parent_id"]) == str(parent.id)
        child.refresh_from_db()
        assert child.parent_id == parent.id

        rows = {str(p["id"]): p for p in session_client.get(self.url(workspace)).data}
        assert str(rows[str(child.id)]["parent_id"]) == str(parent.id)
        assert rows[str(parent.id)]["parent_id"] is None
        assert "parent" not in rows[str(child.id)]

        details = {str(p["id"]): p for p in session_client.get(f"{self.url(workspace)}details/").data}
        assert str(details[str(child.id)]["parent_id"]) == str(parent.id)
        assert "parent" not in details[str(child.id)]

        assert str(session_client.get(self.url(workspace, child)).data["parent_id"]) == str(parent.id)

    def test_create_inside_a_parent(self, session_client, workspace, parent):
        response = session_client.post(
            self.url(workspace), {"name": "Nested", "identifier": "NEST", "parent_id": str(parent.id)}, format="json"
        )
        assert response.status_code == 201, response.data
        assert str(response.data["parent_id"]) == str(parent.id)
        assert Project.objects.get(pk=response.data["id"]).parent_id == parent.id

    def test_clear_parent(self, session_client, workspace, parent, child):
        Project.objects.filter(pk=child.pk).update(parent=parent)
        response = session_client.patch(self.url(workspace, child), {"parent_id": None}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["parent_id"] is None
        child.refresh_from_db()
        assert child.parent_id is None

    def test_rejects_itself(self, session_client, workspace, child):
        response = session_client.patch(self.url(workspace, child), {"parent_id": str(child.id)}, format="json")
        assert response.status_code == 400
        assert "parent_id" in response.data

    def test_rejects_a_cycle(self, session_client, workspace, parent, child, create_user):
        grandchild = _project(workspace, create_user, "Grandchild")
        Project.objects.filter(pk=child.pk).update(parent=parent)
        Project.objects.filter(pk=grandchild.pk).update(parent=child)
        response = session_client.patch(self.url(workspace, parent), {"parent_id": str(grandchild.id)}, format="json")
        assert response.status_code == 400
        assert "parent_id" in response.data
        parent.refresh_from_db()
        assert parent.parent_id is None

    def test_rejects_another_workspace(self, session_client, workspace, child, create_user):
        elsewhere = Workspace.objects.create(name="Elsewhere", owner=create_user, slug=f"else-{uuid4().hex[:6]}")
        WorkspaceMember.objects.create(workspace=elsewhere, member=create_user, role=20)
        foreign = _project(elsewhere, create_user, "Foreign")
        response = session_client.patch(self.url(workspace, child), {"parent_id": str(foreign.id)}, format="json")
        assert response.status_code == 400
        assert "parent_id" in response.data

    def test_depth_limit(self, session_client, workspace, create_user):
        chain = [_project(workspace, create_user, f"Level{i:02d}") for i in range(1, MAX_PROJECT_TREE_DEPTH + 2)]
        for upper, lower in zip(chain, chain[1 : MAX_PROJECT_TREE_DEPTH - 1]):
            Project.objects.filter(pk=lower.pk).update(parent=upper)
        # chain[MAX-2] is now at level MAX-1; putting a board under it lands at level MAX: allowed.
        last_ok, too_deep = chain[MAX_PROJECT_TREE_DEPTH - 1], chain[MAX_PROJECT_TREE_DEPTH]
        ok = session_client.patch(
            self.url(workspace, last_ok), {"parent_id": str(chain[MAX_PROJECT_TREE_DEPTH - 2].id)}, format="json"
        )
        assert ok.status_code == 200, ok.data
        # One more level is refused.
        refused = session_client.patch(self.url(workspace, too_deep), {"parent_id": str(last_ok.id)}, format="json")
        assert refused.status_code == 400
        assert "parent_id" in refused.data

    def test_depth_counts_the_moved_subtree(self, session_client, workspace, create_user):
        chain = [_project(workspace, create_user, f"Deep{i:02d}") for i in range(1, MAX_PROJECT_TREE_DEPTH + 1)]
        for upper, lower in zip(chain, chain[1:]):
            Project.objects.filter(pk=lower.pk).update(parent=upper)
        # The chain is exactly MAX levels deep; hanging its root under another board makes MAX + 1.
        host = _project(workspace, create_user, "Host")
        response = session_client.patch(self.url(workspace, chain[0]), {"parent_id": str(host.id)}, format="json")
        assert response.status_code == 400

    def test_deleting_a_parent_keeps_its_children(self, session_client, workspace, parent, child):
        from plane.bgtasks.deletion_task import soft_delete_related_objects

        Project.objects.filter(pk=child.pk).update(parent=parent)
        assert session_client.delete(self.url(workspace, parent)).status_code == 204
        # The view queues this job; run it here so the test does not depend on a worker.
        soft_delete_related_objects("db", "project", parent.pk)
        child = Project.objects.get(pk=child.pk)
        assert child.deleted_at is None
        assert child.parent_id is None

    def test_hard_deleting_a_parent_keeps_its_children(self, parent, child):
        Project.objects.filter(pk=child.pk).update(parent=parent)
        Project.all_objects.filter(pk=parent.pk).delete()
        child = Project.objects.get(pk=child.pk)
        assert child.parent_id is None


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectParentPrivacy:
    """Someone who cannot see the parent sees the child at top level and never the parent's id."""

    @pytest.fixture
    def private_parent(self, workspace, create_user, child):
        parent = _project(workspace, create_user, "Secret", is_private=True)
        Project.objects.filter(pk=child.pk).update(parent=parent)
        return parent

    def test_hidden_parent_reads_as_null(self, other_admin, workspace, private_parent, child):
        ProjectMember.objects.create(project=child, member=other_admin, workspace=workspace, role=20)
        client = _client(other_admin)
        base = f"/api/workspaces/{workspace.slug}/projects/"

        rows = {str(p["id"]): p for p in client.get(base).data}
        assert str(private_parent.id) not in rows
        assert rows[str(child.id)]["parent_id"] is None

        details = {str(p["id"]): p for p in client.get(f"{base}details/").data}
        assert details[str(child.id)]["parent_id"] is None
        assert "parent" not in details[str(child.id)]

        assert client.get(f"{base}{child.id}/").data["parent_id"] is None
        assert str(private_parent.id) not in str(client.get(f"{base}{child.id}/").content)

    def test_member_of_the_parent_still_sees_it(self, session_client, workspace, private_parent, child):
        rows = {str(p["id"]): p for p in session_client.get(f"/api/workspaces/{workspace.slug}/projects/").data}
        assert str(rows[str(child.id)]["parent_id"]) == str(private_parent.id)

    def test_echoing_null_does_not_detach_from_a_hidden_parent(self, other_admin, workspace, private_parent, child):
        ProjectMember.objects.create(project=child, member=other_admin, workspace=workspace, role=20)
        client = _client(other_admin)
        response = client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{child.id}/",
            {"parent_id": None, "name": "Renamed"},
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data["parent_id"] is None
        child.refresh_from_db()
        assert child.name == "Renamed"
        assert child.parent_id == private_parent.id

    def test_cannot_pick_a_hidden_parent(self, other_admin, workspace, create_user):
        hidden = _project(workspace, create_user, "Hidden", is_private=True)
        mine = _project(workspace, other_admin, "Mine")
        client = _client(other_admin)
        response = client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{mine.id}/", {"parent_id": str(hidden.id)}, format="json"
        )
        assert response.status_code == 400
        mine.refresh_from_db()
        assert mine.parent_id is None

    def test_member_cannot_pick_a_secret_parent_they_are_not_in(self, workspace, create_user):
        user = User.objects.create(email=f"m-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
        secret = _project(workspace, create_user, "Network0", network=0)
        mine = _project(workspace, user, "Mine")
        response = _client(user).patch(
            f"/api/workspaces/{workspace.slug}/projects/{mine.id}/", {"parent_id": str(secret.id)}, format="json"
        )
        assert response.status_code == 400

    def test_public_api_hides_the_parent(self, other_admin, workspace, private_parent, child):
        ProjectMember.objects.create(project=child, member=other_admin, workspace=workspace, role=20)
        token = APIToken.objects.create(user=other_admin, label="t", token=f"tok-{uuid4().hex}")
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=token.token)
        base = f"/api/v1/workspaces/{workspace.slug}/projects/"
        rows = {str(p["id"]): p for p in _rows(client.get(base))}
        assert rows[str(child.id)]["parent_id"] is None
        assert "parent" not in rows[str(child.id)]
        assert client.get(f"{base}{child.id}/").data["parent_id"] is None


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectParentPublicApi:
    def url(self, workspace, project=None):
        base = f"/api/v1/workspaces/{workspace.slug}/projects/"
        return f"{base}{project.id}/" if project else base

    def test_patch_sets_parent(self, api_key_client, workspace, parent, child):
        response = api_key_client.patch(self.url(workspace, child), {"parent_id": str(parent.id)}, format="json")
        assert response.status_code == 200, response.data
        assert str(response.data["parent_id"]) == str(parent.id)
        child.refresh_from_db()
        assert child.parent_id == parent.id

        listed = {str(p["id"]): p for p in _rows(api_key_client.get(self.url(workspace)))}
        assert str(listed[str(child.id)]["parent_id"]) == str(parent.id)

    def test_create_with_parent(self, api_key_client, workspace, parent):
        response = api_key_client.post(
            self.url(workspace), {"name": "Scripted", "identifier": "SCR", "parent_id": str(parent.id)}, format="json"
        )
        assert response.status_code == 201, response.data
        assert Project.objects.get(pk=response.data["id"]).parent_id == parent.id

    def test_patch_rejects_cycle(self, api_key_client, workspace, parent, child):
        Project.objects.filter(pk=child.pk).update(parent=parent)
        response = api_key_client.patch(self.url(workspace, parent), {"parent_id": str(child.id)}, format="json")
        assert response.status_code == 400
        assert "parent_id" in response.data
