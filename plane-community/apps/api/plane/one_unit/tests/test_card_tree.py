# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Card tree, page list and breadcrumb: only what the person may see, never a hint of the rest."""

import pytest

from plane.db.models import Project, ProjectMember
from plane.one_unit.tests.conftest import card

MARK = b"TOPSECRET"


def tree(cast, client, **params):
    return client.get(f"/api/workspaces/{cast.workspace.slug}/card-tree/", params)


def ids(response):
    return {str(row["id"]) for row in response.data["results"]}


def row(response, issue):
    return next(r for r in response.data["results"] if str(r["id"]) == str(issue.id))


@pytest.mark.django_db
class TestTreeRoots:
    def test_project_roots_for_member(self, world):
        response = tree(world, world.author_client, project_id=world.alpha.id)
        assert response.status_code == 200, response.content
        # author created the secret card, so author sees it
        assert ids(response) == {str(world.root.id), str(world.secret.id)}
        # the Beta grandchild is out of author's reach and is not counted
        assert row(tree(world, world.author_client, parent_id=world.root.id), world.child)["child_count"] == 0

    def test_restricted_card_never_in_insider_tree(self, world):
        response = tree(world, world.insider_client, project_id=world.alpha.id)
        assert MARK not in response.content
        assert str(world.secret.id) not in ids(response)
        # the open card under the secret one surfaces at the top, with no parent shown
        assert str(world.under_secret.id) in ids(response)
        assert row(response, world.under_secret)["parent_id"] is None

    def test_friend_sees_shared_card(self, world):
        response = tree(world, world.friend_client, project_id=world.alpha.id)
        assert str(world.secret.id) in ids(response)
        assert row(response, world.secret)["child_count"] == 1

    def test_cross_project_child_is_root_of_its_own_project(self, world):
        both = tree(world, world.both_client, project_id=world.beta.id)
        assert ids(both) == {str(world.grandchild.id)}
        assert str(row(both, world.grandchild)["parent_id"]) == str(world.child.id)
        outsider = tree(world, world.outsider_client, project_id=world.beta.id)
        assert ids(outsider) == {str(world.grandchild.id)}
        # outsider is not in Alpha: the parent is masked
        assert row(outsider, world.grandchild)["parent_id"] is None

    def test_non_member_project_is_empty(self, world):
        response = tree(world, world.outsider_client, project_id=world.alpha.id)
        assert response.status_code == 200
        assert response.data["results"] == [] and response.data["total"] == 0

    def test_needs_project_or_parent(self, world):
        assert tree(world, world.author_client).status_code == 400
        assert tree(world, world.author_client, project_id="nope").status_code == 400


@pytest.mark.django_db
class TestTreeChildren:
    def test_children_across_projects_for_member_of_both(self, world):
        response = tree(world, world.both_client, parent_id=world.child.id)
        assert ids(response) == {str(world.grandchild.id)}
        assert row(tree(world, world.both_client, parent_id=world.root.id), world.child)["child_count"] == 1

    def test_children_hide_other_project(self, world):
        assert ids(tree(world, world.author_client, parent_id=world.child.id)) == set()

    def test_hidden_parent_is_404(self, world):
        assert tree(world, world.insider_client, parent_id=world.secret.id).status_code == 404
        assert tree(world, world.outsider_client, parent_id=world.root.id).status_code == 404

    def test_paging(self, world):
        for n in range(5):
            card(world, f"extra {n}", parent=world.root)
        first = tree(world, world.author_client, parent_id=world.root.id, limit=4)
        assert len(first.data["results"]) == 4 and first.data["total"] == 6 and first.data["next_offset"] == 4
        second = tree(world, world.author_client, parent_id=world.root.id, limit=4, offset=4)
        assert len(second.data["results"]) == 2 and second.data["next_offset"] is None
        assert ids(first).isdisjoint(ids(second))


@pytest.mark.django_db
class TestPrivateAndGuest:
    def test_private_project_cards_never_in_tree(self, world):
        if not any(f.name == "is_private" for f in Project._meta.get_fields()):
            pytest.skip("private projects not in this build")
        Project.objects.filter(pk=world.beta.pk).update(is_private=True)
        # author is not a Beta member: nothing from Beta, not even under an Alpha card
        assert ids(tree(world, world.author_client, parent_id=world.child.id)) == set()
        # the workspace owner is a Beta member here, so still sees it
        assert ids(tree(world, world.owner_client, parent_id=world.child.id)) == {str(world.grandchild.id)}
        ProjectMember.objects.filter(project=world.beta, member=world.owner).update(is_active=False)
        assert ids(tree(world, world.owner_client, parent_id=world.child.id)) == set()

    def test_guest_sees_only_own_cards(self, world):
        ProjectMember.objects.filter(project=world.alpha, member=world.insider).update(role=5)
        Project.objects.filter(pk=world.alpha.pk).update(guest_view_all_features=False)
        own = card(world, "guest note", author=world.insider)
        assert ids(tree(world, world.insider_client, project_id=world.alpha.id)) == {str(own.id)}


@pytest.mark.django_db
class TestBreadcrumb:
    def crumb(self, world, client, issue):
        return client.get(f"/api/workspaces/{world.workspace.slug}/cards/{issue.id}/breadcrumb/")

    def test_full_chain_for_member_of_both(self, world):
        response = self.crumb(world, world.both_client, world.grandchild)
        assert response.status_code == 200
        assert [str(a["id"]) for a in response.data["ancestors"]] == [str(world.root.id), str(world.child.id)]

    def test_chain_stops_at_unreachable(self, world):
        response = self.crumb(world, world.outsider_client, world.grandchild)
        assert response.status_code == 200 and response.data["ancestors"] == []

    def test_chain_never_skips_over_hidden(self, world):
        top = card(world, "ALP top")
        world.secret.parent = top
        world.secret.save()
        response = self.crumb(world, world.insider_client, world.under_secret)
        assert response.data["ancestors"] == []
        assert MARK not in response.content
        friend = self.crumb(world, world.friend_client, world.under_secret)
        assert [str(a["id"]) for a in friend.data["ancestors"]] == [str(top.id), str(world.secret.id)]

    def test_hidden_card_is_404(self, world):
        assert self.crumb(world, world.insider_client, world.secret).status_code == 404
        assert self.crumb(world, world.author_client, world.grandchild).status_code == 404


@pytest.mark.django_db
class TestPageList:
    def url(self, world, project):
        return f"/api/workspaces/{world.workspace.slug}/projects/{project.id}/page-list/"

    def test_lists_visible_cards_with_masked_parents(self, world):
        response = world.insider_client.get(self.url(world, world.alpha))
        assert response.status_code == 200, response.content
        assert MARK not in response.content
        assert ids(response) == {str(world.root.id), str(world.child.id), str(world.under_secret.id)}
        assert row(response, world.under_secret)["parent_id"] is None
        assert str(row(response, world.child)["parent_id"]) == str(world.root.id)
        assert "updated_at" in response.data["results"][0]

    def test_cross_project_parent_masked_for_outsider(self, world):
        response = world.outsider_client.get(self.url(world, world.beta))
        assert ids(response) == {str(world.grandchild.id)}
        assert row(response, world.grandchild)["parent_id"] is None

    def test_non_member_refused(self, world):
        assert world.outsider_client.get(self.url(world, world.alpha)).status_code in (403, 404)
