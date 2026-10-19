# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""A card's parent may live in another project; each card keeps its own project's rules."""

import pytest

from plane.db.models import Issue, IssueActivity
from plane.one_unit.tests.conftest import card


def issue_url(world, issue, project=None):
    project = project or issue.project
    return f"/api/workspaces/{world.workspace.slug}/projects/{project.id}/issues/{issue.id}/"


@pytest.mark.django_db
class TestSetParent:
    def test_member_of_both_can_set_parent_in_other_project(self, world):
        note = card(world, "BET note", project=world.beta, author=world.both)
        response = world.both_client.patch(issue_url(world, note), {"parent_id": str(world.root.id)}, format="json")
        assert response.status_code == 204, response.content
        assert str(Issue.objects.get(pk=note.pk).parent_id) == str(world.root.id)

    def test_create_with_parent_in_other_project(self, world):
        url = f"/api/workspaces/{world.workspace.slug}/projects/{world.beta.id}/issues/"
        response = world.both_client.post(url, {"name": "BET new", "parent_id": str(world.root.id)}, format="json")
        assert response.status_code == 201, response.content
        assert str(response.data["parent_id"]) == str(world.root.id)

    def test_non_member_of_parent_project_is_refused(self, world):
        note = card(world, "BET note", project=world.beta, author=world.outsider)
        response = world.outsider_client.patch(
            issue_url(world, note), {"parent_id": str(world.root.id)}, format="json"
        )
        assert response.status_code == 400
        assert Issue.objects.get(pk=note.pk).parent_id is None

    def test_restricted_parent_needs_edit(self, world):
        # friend may only view the secret card: cannot hang a Beta card under it (friend is not in Beta anyway)
        note = card(world, "BET note", project=world.beta, author=world.both)
        response = world.both_client.patch(
            issue_url(world, note), {"parent_id": str(world.secret.id)}, format="json"
        )
        assert response.status_code == 400

    def test_loop_is_refused(self, world):
        response = world.author_client.patch(
            issue_url(world, world.root), {"parent_id": str(world.child.id)}, format="json"
        )
        assert response.status_code == 400
        response = world.both_client.patch(
            issue_url(world, world.root), {"parent_id": str(world.grandchild.id)}, format="json"
        )
        assert response.status_code == 400
        assert Issue.objects.get(pk=world.root.pk).parent_id is None


@pytest.mark.django_db
class TestParentMasking:
    def test_detail_hides_parent_in_unreachable_project(self, world):
        hidden = world.outsider_client.get(issue_url(world, world.grandchild))
        assert hidden.status_code == 200, hidden.content
        assert hidden.data["parent_id"] is None
        shown = world.both_client.get(issue_url(world, world.grandchild))
        assert str(shown.data["parent_id"]) == str(world.child.id)

    def test_sub_items_list_hides_other_project(self, world):
        url = issue_url(world, world.child) + "sub-issues/"
        assert world.author_client.get(url).data["sub_issues"] == []
        both = world.both_client.get(url).data["sub_issues"]
        assert {str(r["id"]) for r in both} == {str(world.grandchild.id)}

    def test_parent_change_activity_hidden_from_outsider(self, world):
        note = card(world, "BET note", project=world.beta, author=world.both)
        assert (
            world.both_client.patch(issue_url(world, note), {"parent_id": str(world.root.id)}, format="json").status_code
            == 204
        )
        assert IssueActivity.objects.filter(issue=note, field="parent").exists()
        url = issue_url(world, note) + "history/"
        outsider = world.outsider_client.get(url)
        assert outsider.status_code == 200, outsider.content
        assert b"ALP-" not in outsider.content


@pytest.mark.django_db
class TestAttachSubItems:
    def url(self, world, parent):
        return issue_url(world, parent) + "sub-issues/"

    def test_cannot_attach_unreachable_card(self, world):
        target = card(world, "BET parent", project=world.beta, author=world.outsider)
        response = world.outsider_client.post(
            self.url(world, target), {"sub_issue_ids": [str(world.root.id)]}, format="json"
        )
        assert response.status_code == 200
        assert Issue.objects.get(pk=world.root.pk).parent_id is None

    def test_member_of_both_can_attach_across_projects(self, world):
        note = card(world, "BET note", project=world.beta, author=world.both)
        response = world.both_client.post(
            self.url(world, world.root), {"sub_issue_ids": [str(note.id)]}, format="json"
        )
        assert response.status_code == 200, response.content
        assert str(Issue.objects.get(pk=note.pk).parent_id) == str(world.root.id)

    def test_cannot_attach_an_ancestor(self, world):
        response = world.both_client.post(
            self.url(world, world.grandchild, ), {"sub_issue_ids": [str(world.root.id)]}, format="json"
        )
        assert response.status_code == 200
        assert Issue.objects.get(pk=world.root.pk).parent_id is None


@pytest.mark.django_db
class TestParentSearch:
    def test_workspace_search_offers_other_projects_but_not_descendants(self, world):
        url = f"/api/workspaces/{world.workspace.slug}/projects/{world.alpha.id}/search-issues/"
        params = {"parent": "true", "issue_id": str(world.root.id), "workspace_search": "true"}
        response = world.both_client.get(url, params)
        assert response.status_code == 200, response.content
        found = {str(r["id"]) for r in response.data}
        assert str(world.grandchild.id) not in found and str(world.child.id) not in found
        other = card(world, "BET other", project=world.beta, author=world.both)
        found = {str(r["id"]) for r in world.both_client.get(url, params).data}
        assert str(other.id) in found

    def test_search_never_offers_unreachable(self, world):
        url = f"/api/workspaces/{world.workspace.slug}/projects/{world.alpha.id}/search-issues/"
        response = world.insider_client.get(url, {"workspace_search": "true", "search": "TOPSECRET"})
        assert response.status_code == 200
        assert response.data == [] or all("TOPSECRET" not in r["name"] for r in response.data)
