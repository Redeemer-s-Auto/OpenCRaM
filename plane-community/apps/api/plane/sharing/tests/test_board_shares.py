# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Boards shared with groups, groups inside groups, and inheritance down the board tree.

Cast (see conftest): ``outsider`` belongs to Beta only. Alpha is made secret
(network=0) so the only way for ``outsider`` to reach it is a group share.
"""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember, WorkspaceMember
from plane.db.models.api import APIToken
from plane.sharing.board_access import effective_group_ids, project_share_level, shared_project_levels
from plane.sharing.models import (
    AccessGroup,
    AccessGroupInclude,
    AccessGroupMember,
    AccessLevel,
    ProjectShare,
    ProjectShareExclusion,
    ShareTarget,
)
from plane.sharing.tests.conftest import client_for, make_issue, make_page, make_user, restrict
from plane.sharing.visibility import issue_access_level

PROJECTS = "/api/workspaces/{slug}/projects/"
PROJECT_DETAILS = "/api/workspaces/{slug}/projects/details/"
PROJECT = "/api/workspaces/{slug}/projects/{project}/"
ISSUES = "/api/workspaces/{slug}/projects/{project}/issues/"
ISSUES_DETAIL = "/api/workspaces/{slug}/projects/{project}/issues-detail/"
ISSUE_COMMENTS = "/api/workspaces/{slug}/projects/{project}/issues/{issue}/comments/"
STATES = "/api/workspaces/{slug}/projects/{project}/states/"
PAGES = "/api/workspaces/{slug}/projects/{project}/pages/"
GLOBAL_SEARCH = "/api/workspaces/{slug}/search/"
ENTITY_SEARCH = "/api/workspaces/{slug}/entity-search/"
GROUP_SHARES = "/api/workspaces/{slug}/projects/{project}/group-shares/"
GROUP_EXCLUSIONS = "/api/workspaces/{slug}/projects/{project}/group-exclusions/"
GROUPS = "/api/workspaces/{slug}/access-groups/"
V1_PROJECTS = "/api/v1/workspaces/{slug}/projects/"
V1_GROUPS = "/api/v1/workspaces/{slug}/access-groups/"
V1_GROUP_SHARES = "/api/v1/workspaces/{slug}/projects/{project}/group-shares/"


def _rows(response):
    data = response.data
    return data.get("results", data) if isinstance(data, dict) else data


def _ids(response):
    return {str(row["id"]) for row in _rows(response)}


def _url(template, cast, project=None, **extra):
    return template.format(slug=cast.workspace.slug, project=(project or cast.alpha).id, **extra)


def _project(cast, name, parent=None, **fields):
    project = Project.objects.create(
        name=name,
        identifier=name[:6].upper() + uuid4().hex[:4].upper(),
        workspace=cast.workspace,
        created_by=cast.owner,
        network=0,
        parent=parent,
        **fields,
    )
    ProjectMember.objects.create(project=project, member=cast.owner, workspace=cast.workspace, role=20)
    return project


def _group(cast, name, *members):
    group = AccessGroup.objects.create(workspace=cast.workspace, name=name)
    for member in members:
        AccessGroupMember.objects.create(group=group, member=member)
    return group


def _share(cast, project, group, level=AccessLevel.VIEW):
    return ProjectShare.objects.create(workspace=cast.workspace, project=project, group=group, level=level)


@pytest.fixture
def secret_alpha(cast):
    """Alpha is secret: nobody outside it sees it without a share."""
    Project.objects.filter(pk=cast.alpha.pk).update(network=0)
    cast.alpha.refresh_from_db()
    return cast.alpha


@pytest.fixture
def advisors(cast):
    """Group "Service Advisors" with ``outsider`` in it."""
    return _group(cast, "Service Advisors", cast.outsider)


@pytest.fixture
def stranger(cast):
    """Workspace member in no project and no group."""
    user = make_user("stranger")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=user, role=15)
    return user


@pytest.mark.django_db
class TestBoardShare:
    def test_secret_board_is_hidden_without_a_share(self, cast, secret_alpha, advisors):
        assert str(secret_alpha.id) not in _ids(cast.outsider_client.get(_url(PROJECTS, cast)))
        assert cast.outsider_client.get(_url(PROJECT, cast)).status_code in (403, 409)
        assert cast.outsider_client.get(_url(ISSUES_DETAIL, cast)).status_code == 403

    def test_group_member_sees_board_cards_pages_and_states(self, cast, secret_alpha, advisors):
        card = make_issue(cast, "Shared card")
        page = make_page(cast, "Shared page")
        _share(cast, secret_alpha, advisors)
        client = cast.outsider_client

        assert str(secret_alpha.id) in _ids(client.get(_url(PROJECTS, cast)))
        assert str(secret_alpha.id) in _ids(client.get(_url(PROJECT_DETAILS, cast)))
        detail = client.get(_url(PROJECT, cast))
        assert detail.status_code == 200, detail.data
        assert detail.data["member_role"] == 5  # viewers act as guests

        listed = {str(row["id"]) for row in _rows(client.get(_url(PROJECTS, cast)))}
        assert str(secret_alpha.id) in listed
        row = next(r for r in _rows(client.get(_url(PROJECTS, cast))) if str(r["id"]) == str(secret_alpha.id))
        assert row["member_role"] == 5

        issues = client.get(_url(ISSUES_DETAIL, cast))
        assert issues.status_code == 200, issues.data
        assert str(card.id) in _ids(issues)

        states = client.get(_url(STATES, cast))
        assert states.status_code == 200
        assert len(_rows(states)) >= 1

        pages = client.get(_url(PAGES, cast))
        assert pages.status_code == 200, pages.data
        assert str(page.id) in _ids(pages)

    def test_search_finds_cards_on_a_shared_board(self, cast, secret_alpha, advisors):
        card = make_issue(cast, "Needle card")
        _share(cast, secret_alpha, advisors)
        found = cast.outsider_client.get(_url(GLOBAL_SEARCH, cast), {"search": "Needle", "workspace_search": "true"})
        assert found.status_code == 200, found.data
        assert str(card.id) in {str(row["id"]) for row in found.data["results"]["issue"]}
        assert str(secret_alpha.id) in {str(row["id"]) for row in found.data["results"]["project"]}
        projects = cast.outsider_client.get(_url(ENTITY_SEARCH, cast), {"query_type": "project", "query": "Alpha"})
        assert str(secret_alpha.id) in {str(row["id"]) for row in projects.data["project"]}

    def test_someone_outside_the_group_stays_blocked(self, cast, secret_alpha, advisors, stranger):
        _share(cast, secret_alpha, advisors)
        client = client_for(stranger)
        assert str(secret_alpha.id) not in _ids(client.get(_url(PROJECTS, cast)))
        assert client.get(_url(ISSUES_DETAIL, cast)).status_code == 403
        assert client.get(_url(PAGES, cast)).status_code == 403

    def test_viewer_cannot_create_a_card_but_editor_can(self, cast, secret_alpha, advisors):
        share = _share(cast, secret_alpha, advisors, AccessLevel.VIEW)
        client = cast.outsider_client
        assert client.post(_url(ISSUES, cast), {"name": "From a viewer"}, format="json").status_code == 403
        share.level = AccessLevel.EDIT
        share.save()
        assert client.get(_url(PROJECT, cast)).data["member_role"] == 15  # editors act as members
        created = client.post(_url(ISSUES, cast), {"name": "From an editor"}, format="json")
        assert created.status_code == 201, created.data

    def test_viewer_cannot_comment_but_commenter_can(self, cast, secret_alpha, advisors):
        card = make_issue(cast, "Comment here")
        share = _share(cast, secret_alpha, advisors, AccessLevel.VIEW)
        url = _url(ISSUE_COMMENTS, cast, issue=card.id)
        body = {"comment_html": "<p>hello</p>"}
        assert cast.outsider_client.post(url, body, format="json").status_code == 403
        share.level = AccessLevel.COMMENT
        share.save()
        assert cast.outsider_client.post(url, body, format="json").status_code == 201

    def test_new_group_member_sees_everything_at_once(self, cast, secret_alpha, advisors, stranger):
        make_issue(cast, "Card one")
        make_issue(cast, "Card two")
        _share(cast, secret_alpha, advisors)
        client = client_for(stranger)
        assert str(secret_alpha.id) not in _ids(client.get(_url(PROJECTS, cast)))

        membership = AccessGroupMember.objects.create(group=advisors, member=stranger)
        assert str(secret_alpha.id) in _ids(client.get(_url(PROJECTS, cast)))
        assert len(_rows(client.get(_url(ISSUES_DETAIL, cast)))) == 2

        membership.delete()
        assert str(secret_alpha.id) not in _ids(client.get(_url(PROJECTS, cast)))
        assert client.get(_url(ISSUES_DETAIL, cast)).status_code == 403

    def test_counts_and_lists_agree(self, cast, secret_alpha, advisors):
        for n in range(3):
            make_issue(cast, f"Card {n}")
        _share(cast, secret_alpha, advisors)
        rows = _rows(cast.outsider_client.get(_url(ISSUES_DETAIL, cast)))
        assert len(rows) == 3
        v1 = cast.outsider_client.get(_url(V1_PROJECTS, cast))
        # The session client has no API key, so v1 answers 401/403; the member check is in the next test.
        assert v1.status_code in (401, 403)

    def test_v1_project_list_includes_the_shared_board(self, cast, secret_alpha, advisors):
        _share(cast, secret_alpha, advisors)
        token = APIToken.objects.create(user=cast.outsider, label="t", token=f"tok-{uuid4().hex}")
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=token.token)
        listed = client.get(_url(V1_PROJECTS, cast))
        assert listed.status_code == 200, listed.data
        assert str(secret_alpha.id) in _ids(listed)
        assert client.get(f"{_url(V1_PROJECTS, cast)}{secret_alpha.id}/").status_code == 200


@pytest.mark.django_db
class TestInheritance:
    @pytest.fixture
    def gamma(self, cast, secret_alpha):
        """A secret board inside Alpha."""
        return _project(cast, "Gamma", parent=secret_alpha)

    def test_share_on_parent_reaches_child_and_parent_id_is_returned(self, cast, secret_alpha, advisors, gamma):
        _share(cast, secret_alpha, advisors)
        assert project_share_level(cast.outsider, gamma.id) == AccessLevel.VIEW
        rows = {str(row["id"]): row for row in _rows(cast.outsider_client.get(_url(PROJECTS, cast)))}
        assert str(gamma.id) in rows and str(secret_alpha.id) in rows
        assert str(rows[str(gamma.id)]["parent_id"]) == str(secret_alpha.id)
        assert cast.outsider_client.get(_url(ISSUES_DETAIL, cast, project=gamma)).status_code == 200

    def test_exclusion_on_child_stops_the_share_there_and_below(self, cast, secret_alpha, advisors, gamma):
        delta = _project(cast, "Delta", parent=gamma)
        _share(cast, secret_alpha, advisors)
        ProjectShareExclusion.objects.create(workspace=cast.workspace, project=gamma, group=advisors)
        levels = shared_project_levels(cast.outsider, slug=cast.workspace.slug)
        assert levels.get(secret_alpha.id) == AccessLevel.VIEW
        assert gamma.id not in levels and delta.id not in levels
        ids = _ids(cast.outsider_client.get(_url(PROJECTS, cast)))
        assert str(secret_alpha.id) in ids and str(gamma.id) not in ids and str(delta.id) not in ids
        assert cast.outsider_client.get(_url(ISSUES_DETAIL, cast, project=gamma)).status_code == 403

    def test_private_child_never_leaks_through_a_shared_parent(self, cast, secret_alpha, advisors, gamma):
        Project.objects.filter(pk=gamma.pk).update(is_private=True)
        epsilon = _project(cast, "Epsilon", parent=gamma)
        _share(cast, secret_alpha, advisors)
        levels = shared_project_levels(cast.outsider, slug=cast.workspace.slug)
        assert gamma.id not in levels
        assert epsilon.id not in levels  # nothing flows through a private board
        ids = _ids(cast.outsider_client.get(_url(PROJECTS, cast)))
        assert str(gamma.id) not in ids and str(epsilon.id) not in ids
        assert cast.outsider_client.get(_url(ISSUES_DETAIL, cast, project=gamma)).status_code == 404
        # Even a direct share row on a private board grants nothing.
        _share(cast, gamma, advisors, AccessLevel.EDIT)
        assert project_share_level(cast.outsider, gamma.id) == 0

    def test_nearest_share_decides_the_level(self, cast, secret_alpha, advisors, gamma):
        _share(cast, secret_alpha, advisors, AccessLevel.VIEW)
        _share(cast, gamma, advisors, AccessLevel.EDIT)
        assert project_share_level(cast.outsider, secret_alpha.id) == AccessLevel.VIEW
        assert project_share_level(cast.outsider, gamma.id) == AccessLevel.EDIT

    def test_best_level_across_groups_wins(self, cast, secret_alpha, advisors):
        editors = _group(cast, "Editors", cast.outsider)
        _share(cast, secret_alpha, advisors, AccessLevel.VIEW)
        _share(cast, secret_alpha, editors, AccessLevel.EDIT)
        assert project_share_level(cast.outsider, secret_alpha.id) == AccessLevel.EDIT

    def test_share_list_shows_inherited_rows(self, cast, secret_alpha, advisors, gamma):
        _share(cast, secret_alpha, advisors)
        listed = cast.owner_client.get(_url(GROUP_SHARES, cast, project=gamma))
        assert listed.status_code == 200, listed.data
        assert listed.data["shares"] == []
        assert [row["group_id"] for row in listed.data["inherited"]] == [str(advisors.id)]
        assert listed.data["inherited"][0]["from_project_id"] == str(secret_alpha.id)


@pytest.mark.django_db
class TestNestedGroups:
    def test_included_group_inherits_the_parent_groups_access(self, cast, secret_alpha):
        upper = _group(cast, "Upper Management", cast.outsider)
        advisors = _group(cast, "Service Advisors")
        AccessGroupInclude.objects.create(group=advisors, included_group=upper)
        assert effective_group_ids(cast.outsider) == {upper.id, advisors.id}
        _share(cast, secret_alpha, advisors)
        assert project_share_level(cast.outsider, secret_alpha.id) == AccessLevel.VIEW
        assert str(secret_alpha.id) in _ids(cast.outsider_client.get(_url(PROJECTS, cast)))

    def test_it_does_not_flow_the_other_way(self, cast, secret_alpha):
        upper = _group(cast, "Upper Management")
        advisors = _group(cast, "Service Advisors", cast.outsider)
        AccessGroupInclude.objects.create(group=advisors, included_group=upper)
        _share(cast, secret_alpha, upper)
        assert effective_group_ids(cast.outsider) == {advisors.id}
        assert project_share_level(cast.outsider, secret_alpha.id) == 0

    def test_chain_of_three(self, cast, secret_alpha):
        top = _group(cast, "Top")
        middle = _group(cast, "Middle")
        bottom = _group(cast, "Bottom", cast.outsider)
        AccessGroupInclude.objects.create(group=top, included_group=middle)
        AccessGroupInclude.objects.create(group=middle, included_group=bottom)
        assert effective_group_ids(cast.outsider) == {top.id, middle.id, bottom.id}

    def test_card_shares_reach_nested_members(self, cast):
        upper = _group(cast, "Upper Management", cast.outsider)
        advisors = _group(cast, "Service Advisors")
        AccessGroupInclude.objects.create(group=advisors, included_group=upper)
        card = make_issue(cast, "Card for advisors")
        restrict(cast, issue=card, shares=[(ShareTarget.GROUP, advisors, AccessLevel.COMMENT)])
        assert issue_access_level(cast.outsider, card.id) == AccessLevel.COMMENT

    def test_resolver_survives_a_loop_in_the_rows(self, cast):
        a = _group(cast, "A", cast.outsider)
        b = _group(cast, "B")
        AccessGroupInclude.objects.create(group=a, included_group=b)
        AccessGroupInclude.objects.create(group=b, included_group=a)  # bypasses the endpoint check
        assert effective_group_ids(cast.outsider) == {a.id, b.id}

    def test_endpoint_rejects_loops_and_self(self, cast):
        a = _group(cast, "A")
        b = _group(cast, "B")
        c = _group(cast, "C")
        base = _url(GROUPS, cast)
        assert cast.owner_client.post(f"{base}{a.id}/includes/", {"group_id": str(a.id)}, format="json").status_code == 400
        assert cast.owner_client.post(f"{base}{a.id}/includes/", {"group_id": str(b.id)}, format="json").status_code == 201
        assert cast.owner_client.post(f"{base}{b.id}/includes/", {"group_id": str(c.id)}, format="json").status_code == 201
        # C already sits under A through B, so C including A would loop.
        assert cast.owner_client.post(f"{base}{c.id}/includes/", {"group_id": str(a.id)}, format="json").status_code == 400
        assert cast.owner_client.post(f"{base}{b.id}/includes/", {"group_id": str(a.id)}, format="json").status_code == 400
        payload = cast.owner_client.get(f"{base}{a.id}/").data
        assert payload["includes"] == [str(b.id)]
        assert cast.owner_client.get(f"{base}{b.id}/").data["included_in"] == [str(a.id)]
        assert cast.owner_client.delete(f"{base}{a.id}/includes/{b.id}/").status_code == 204
        assert not AccessGroupInclude.objects.filter(group=a, included_group=b).exists()

    def test_only_admins_nest_groups(self, cast):
        a = _group(cast, "A")
        b = _group(cast, "B")
        url = f"{_url(GROUPS, cast)}{a.id}/includes/"
        assert cast.insider_client.post(url, {"group_id": str(b.id)}, format="json").status_code == 403


@pytest.mark.django_db
class TestBoardShareEndpoints:
    def test_admin_shares_a_board_and_removes_the_share(self, cast, secret_alpha, advisors):
        url = _url(GROUP_SHARES, cast)
        created = cast.owner_client.post(url, {"group_id": str(advisors.id), "level": AccessLevel.EDIT}, format="json")
        assert created.status_code == 201, created.data
        assert created.data["shares"] == [{"group_id": str(advisors.id), "name": "Service Advisors", "level": 15}]
        assert str(secret_alpha.id) in _ids(cast.outsider_client.get(_url(PROJECTS, cast)))

        changed = cast.owner_client.post(url, {"group_id": str(advisors.id), "level": AccessLevel.VIEW}, format="json")
        assert changed.status_code == 200 and changed.data["shares"][0]["level"] == 5

        assert cast.owner_client.delete(f"{url}{advisors.id}/").status_code == 204
        assert str(secret_alpha.id) not in _ids(cast.outsider_client.get(_url(PROJECTS, cast)))

    def test_members_cannot_share_a_board(self, cast, secret_alpha, advisors):
        url = _url(GROUP_SHARES, cast)
        assert cast.author_client.post(url, {"group_id": str(advisors.id)}, format="json").status_code == 403
        assert cast.author_client.delete(f"{url}{advisors.id}/").status_code == 403
        assert cast.author_client.post(_url(GROUP_EXCLUSIONS, cast), {"group_id": str(advisors.id)}, format="json").status_code == 403

    def test_rejects_bad_group_level_and_private_board(self, cast, secret_alpha, advisors):
        url = _url(GROUP_SHARES, cast)
        bad_group = cast.owner_client.post(url, {"group_id": "00000000-0000-0000-0000-000000000000"}, format="json")
        assert bad_group.status_code == 400
        bad_level = cast.owner_client.post(url, {"group_id": str(advisors.id), "level": 99}, format="json")
        assert bad_level.status_code == 400
        Project.objects.filter(pk=secret_alpha.pk).update(is_private=True)
        private = cast.owner_client.post(url, {"group_id": str(advisors.id)}, format="json")
        assert private.status_code == 400
        assert not ProjectShare.objects.filter(project=secret_alpha).exists()

    def test_exclusion_endpoint(self, cast, secret_alpha, advisors):
        gamma = _project(cast, "Gamma", parent=secret_alpha)
        _share(cast, secret_alpha, advisors)
        url = _url(GROUP_EXCLUSIONS, cast, project=gamma)
        excluded = cast.owner_client.post(url, {"group_id": str(advisors.id)}, format="json")
        assert excluded.status_code == 201, excluded.data
        assert excluded.data["exclusions"] == [{"group_id": str(advisors.id), "name": "Service Advisors"}]
        assert excluded.data["inherited"] == []
        assert str(gamma.id) not in _ids(cast.outsider_client.get(_url(PROJECTS, cast)))
        assert cast.owner_client.delete(f"{url}{advisors.id}/").status_code == 204
        assert str(gamma.id) in _ids(cast.outsider_client.get(_url(PROJECTS, cast)))

    def test_v1_api_key_flow_for_scripts(self, cast, secret_alpha):
        """What a script does: make two groups, nest one, share the board; the nested member sees it."""
        token = APIToken.objects.create(user=cast.owner, label="t", token=f"tok-{uuid4().hex}")
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=token.token)
        groups = _url(V1_GROUPS, cast)

        advisors = client.post(groups, {"name": "Service Advisors"}, format="json")
        assert advisors.status_code == 201, advisors.data
        upper = client.post(groups, {"name": "Upper Management", "member_ids": [str(cast.outsider.id)]}, format="json")
        assert upper.status_code == 201, upper.data

        nested = client.post(f"{groups}{advisors.data['id']}/includes/", {"group_id": upper.data["id"]}, format="json")
        assert nested.status_code == 201, nested.data
        assert nested.data["includes"] == [upper.data["id"]]

        shared = client.post(
            _url(V1_GROUP_SHARES, cast), {"group_id": advisors.data["id"], "level": AccessLevel.VIEW}, format="json"
        )
        assert shared.status_code == 201, shared.data
        assert client.get(_url(V1_GROUP_SHARES, cast)).data["shares"][0]["group_id"] == advisors.data["id"]

        assert str(secret_alpha.id) in _ids(cast.outsider_client.get(_url(PROJECTS, cast)))

    def test_v1_api_key_of_a_member_cannot_share(self, cast, secret_alpha, advisors):
        token = APIToken.objects.create(user=cast.author, label="t", token=f"tok-{uuid4().hex}")
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=token.token)
        response = client.post(_url(V1_GROUP_SHARES, cast), {"group_id": str(advisors.id)}, format="json")
        assert response.status_code == 403
