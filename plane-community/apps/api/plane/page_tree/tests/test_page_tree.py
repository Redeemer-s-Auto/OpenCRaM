# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Page tree and "Link to page" look-ups: the same rules as the project pages list, never more.

Cast (see plane.sharing.tests.conftest): ``owner`` is the workspace admin and a member of
Alpha and Beta; ``author``/``insider``/``friend`` are Alpha members; ``outsider`` is a Beta
member only.
"""

import pytest

from plane.db.models import Page, Project, ProjectMember, ProjectPage
from plane.sharing.models import AccessLevel, ShareTarget
from plane.sharing.tests.conftest import make_page, restrict

TREE = "/api/workspaces/{slug}/page-tree/"
RESOLVE = "/api/workspaces/{slug}/page-links/resolve/"
SEARCH = "/api/workspaces/{slug}/page-links/search/"
MARK = b"TOPSECRET"


def _url(template, cast):
    return template.format(slug=cast.workspace.slug)


def _ids(rows):
    return {row["id"] for row in rows}


def _child(cast, parent, name, author=None):
    page = make_page(cast, name, author=author)
    Page.objects.filter(pk=page.pk).update(parent=parent)
    return page


@pytest.mark.django_db
class TestTree:
    def test_tree_sends_visible_pages_with_parents(self, cast):
        home = make_page(cast, "Home")
        child = _child(cast, home, "Child")
        response = cast.insider_client.get(_url(TREE, cast))
        assert response.status_code == 200, response.content
        rows = {row["id"]: row for row in response.data["results"]}
        assert set(rows) == {str(home.id), str(child.id)}
        assert rows[str(child.id)]["parent_id"] == str(home.id)
        assert rows[str(child.id)]["project_id"] == str(cast.alpha.id)
        assert rows[str(home.id)]["parent_id"] is None
        assert rows[str(home.id)]["is_landing"] is False

    def test_outsider_sees_nothing_from_alpha(self, cast):
        make_page(cast, "Alpha page TOPSECRET")
        response = cast.outsider_client.get(_url(TREE, cast))
        assert response.status_code == 200
        assert response.data["results"] == []
        assert MARK not in response.content

    def test_restricted_page_hidden_and_parent_masked(self, cast):
        secret = make_page(cast, "Secret parent TOPSECRET")
        restrict(cast, page=secret, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
        child = _child(cast, secret, "Open child")
        hidden = cast.insider_client.get(_url(TREE, cast))
        assert MARK not in hidden.content
        rows = {row["id"]: row for row in hidden.data["results"]}
        assert set(rows) == {str(child.id)}
        # the parent is hidden, so the child sits at the top: no parent id leaks through
        assert rows[str(child.id)]["parent_id"] is None
        shown = cast.friend_client.get(_url(TREE, cast))
        assert _ids(shown.data["results"]) == {str(secret.id), str(child.id)}

    def test_private_page_only_for_its_owner(self, cast):
        mine = make_page(cast, "My private TOPSECRET")
        Page.objects.filter(pk=mine.pk).update(access=Page.PRIVATE_ACCESS)
        assert MARK not in cast.insider_client.get(_url(TREE, cast)).content
        assert str(mine.id) in _ids(cast.author_client.get(_url(TREE, cast)).data["results"])

    def test_archived_page_and_archived_board_left_out(self, cast):
        gone = make_page(cast, "Archived TOPSECRET")
        Page.objects.filter(pk=gone.pk).update(archived_at="2026-01-01")
        assert MARK not in cast.author_client.get(_url(TREE, cast)).content
        live = make_page(cast, "Live page")
        Project.objects.filter(pk=cast.alpha.pk).update(archived_at="2026-01-01")
        assert str(live.id) not in _ids(cast.author_client.get(_url(TREE, cast)).data["results"])

    def test_guest_without_view_all_sees_only_own_pages(self, cast):
        ProjectMember.objects.filter(project=cast.alpha, member=cast.insider).update(role=5)
        Project.objects.filter(pk=cast.alpha.pk).update(guest_view_all_features=False)
        make_page(cast, "Someone else's TOPSECRET")
        own = make_page(cast, "Guest's own page", author=cast.insider)
        response = cast.insider_client.get(_url(TREE, cast))
        assert MARK not in response.content
        assert _ids(response.data["results"]) == {str(own.id)}

    def test_project_filter_and_landing_flag(self, cast):
        Project.objects.filter(pk=cast.alpha.pk).update(external_source="notion", external_id="folder:" + "a" * 32)
        landing = make_page(cast, "Alpha home")
        Page.objects.filter(pk=landing.pk).update(external_source="notion", external_id="page:" + "a" * 32)
        other = make_page(cast, "Alpha other")
        beta_page = Page(name="Beta page", workspace=cast.workspace, owned_by=cast.owner)
        beta_page.save(created_by_id=cast.owner.id)
        ProjectPage.objects.create(project=cast.beta, page=beta_page, workspace=cast.workspace)
        response = cast.owner_client.get(_url(TREE, cast), {"project_id": str(cast.alpha.id)})
        rows = {row["id"]: row for row in response.data["results"]}
        assert set(rows) == {str(landing.id), str(other.id)}
        assert rows[str(landing.id)]["is_landing"] is True
        assert rows[str(other.id)]["is_landing"] is False
        assert cast.owner_client.get(_url(TREE, cast), {"project_id": "nope"}).status_code == 400

    def test_anonymous_is_refused(self, cast):
        from rest_framework.test import APIClient

        assert APIClient().get(_url(TREE, cast)).status_code in (401, 403)


@pytest.mark.django_db
class TestResolve:
    def test_visible_hidden_and_removed(self, cast):
        page = make_page(cast, "Linked page")
        secret = make_page(cast, "Secret TOPSECRET")
        restrict(cast, page=secret, shares=[])
        gone = make_page(cast, "Gone page")
        gone.delete()
        # Beta is made secret: a board is open to every workspace member while it is public (network=2)
        Project.objects.filter(pk=cast.beta.pk).update(network=0)
        payload = {"pages": [str(page.id), str(secret.id), str(gone.id), "not-a-uuid"], "projects": [str(cast.beta.id)]}
        response = cast.insider_client.post(_url(RESOLVE, cast), payload, format="json")
        assert response.status_code == 200, response.content
        assert MARK not in response.content
        pages = response.data["pages"]
        assert pages[str(page.id)]["status"] == "visible"
        assert pages[str(page.id)]["page"]["project_id"] == str(cast.alpha.id)
        assert pages[str(secret.id)] == {"status": "hidden"}
        assert pages[str(gone.id)] == {"status": "removed"}
        assert "not-a-uuid" not in pages
        # insider is not on Beta and Beta is not public: hidden, no name
        assert response.data["projects"][str(cast.beta.id)] == {"status": "hidden"}
        assert b"Beta" not in response.content

    def test_project_visible_to_member_and_bad_payload(self, cast):
        response = cast.outsider_client.post(_url(RESOLVE, cast), {"projects": [str(cast.beta.id)]}, format="json")
        assert response.data["projects"][str(cast.beta.id)]["status"] == "visible"
        assert response.data["projects"][str(cast.beta.id)]["project"]["identifier"] == "BET"
        bad = cast.outsider_client.post(_url(RESOLVE, cast), {"pages": "x"}, format="json")
        assert bad.status_code == 400


@pytest.mark.django_db
class TestSearch:
    def test_search_matches_only_what_the_caller_sees(self, cast):
        make_page(cast, "Warranty TOPSECRET")
        secret = make_page(cast, "Warranty secret TOPSECRET")
        restrict(cast, page=secret, shares=[])
        shown = cast.author_client.get(_url(SEARCH, cast), {"search": "warranty"})
        assert shown.status_code == 200
        assert len(shown.data["pages"]) == 2
        partial = cast.insider_client.get(_url(SEARCH, cast), {"search": "warranty"})
        assert [row["name"] for row in partial.data["pages"]] == ["Warranty TOPSECRET"]
        assert cast.outsider_client.get(_url(SEARCH, cast), {"search": "warranty"}).data["pages"] == []
        boards = cast.outsider_client.get(_url(SEARCH, cast), {"search": "BET"})
        assert [row["identifier"] for row in boards.data["projects"]] == ["BET"]
        # Alpha is made secret: a public board (network=2) is open to every workspace member
        Project.objects.filter(pk=cast.alpha.pk).update(network=0)
        assert "ALP" not in str(cast.outsider_client.get(_url(SEARCH, cast), {"search": ""}).data["projects"])
