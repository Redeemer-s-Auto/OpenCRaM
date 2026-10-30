# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Teamspaces and Private areas: where a board sits decides who sees it.

Cast (see conftest): ``owner`` is the workspace admin and a member of Alpha and Beta;
``author``/``insider``/``friend`` are Alpha members; ``outsider`` is a Beta member only.
Alpha is made secret (network=0) so that only the resolver can open it for an outsider.
"""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember, WorkspaceMember
from plane.db.models.api import APIToken
from plane.sharing.board_access import LEVEL_OWNER, placement_levels, project_share_level, user_teamspace_ids
from plane.sharing.models import (
    PRIVATE_READERS_GROUP_NAME,
    AccessGroup,
    AccessGroupInclude,
    AccessGroupMember,
    AccessLevel,
    ProjectShare,
    Teamspace,
)
from plane.sharing.tests.conftest import client_for, make_issue, make_user

PROJECTS = "/api/workspaces/{slug}/projects/"
PROJECT_DETAILS = "/api/workspaces/{slug}/projects/details/"
PROJECT = "/api/workspaces/{slug}/projects/{project}/"
ISSUES = "/api/workspaces/{slug}/projects/{project}/issues/"
ISSUES_DETAIL = "/api/workspaces/{slug}/projects/{project}/issues-detail/"
GLOBAL_SEARCH = "/api/workspaces/{slug}/search/"
GROUP_SHARES = "/api/workspaces/{slug}/projects/{project}/group-shares/"
TEAMSPACES = "/api/workspaces/{slug}/teamspaces/"
V1_PROJECTS = "/api/v1/workspaces/{slug}/projects/"
V1_TEAMSPACES = "/api/v1/workspaces/{slug}/teamspaces/"


def _rows(response):
    data = response.data
    return data.get("results", data) if isinstance(data, dict) else data


def _ids(response):
    return {str(row["id"]) for row in _rows(response)}


def _row(response, project):
    return next(row for row in _rows(response) if str(row["id"]) == str(project.id))


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


def _teamspace(cast, name, group=None, is_default=False, position=0):
    return Teamspace.objects.create(
        workspace=cast.workspace, name=name, slug=name.lower().replace(" ", "-"), group=group, is_default=is_default, position=position
    )


def _api_client(user):
    token = APIToken.objects.create(user=user, label="t", token=f"tok-{uuid4().hex}")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.fixture
def secret_alpha(cast):
    Project.objects.filter(pk=cast.alpha.pk).update(network=0)
    cast.alpha.refresh_from_db()
    return cast.alpha


@pytest.fixture
def stranger(cast):
    """Workspace member in no project and no group."""
    user = make_user("stranger")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=user, role=15)
    return user


@pytest.fixture
def other_admin(cast):
    """A second workspace admin: in no project, no group, no teamspace group."""
    user = make_user("admin2")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=user, role=20)
    return user


@pytest.fixture
def upper(cast):
    """Group "Upper Management" with ``outsider`` in it."""
    return _group(cast, "Upper Management", cast.outsider)


@pytest.fixture
def upper_space(cast, upper, secret_alpha):
    """Teamspace "Upper Management" (its group) holding Alpha."""
    space = _teamspace(cast, "Upper Management", group=upper, position=1)
    Project.objects.filter(pk=secret_alpha.pk).update(teamspace=space)
    secret_alpha.refresh_from_db()
    return space


def _assert_cannot_open(client, cast, project):
    assert str(project.id) not in _ids(client.get(_url(PROJECTS, cast)))
    assert str(project.id) not in _ids(client.get(_url(PROJECT_DETAILS, cast)))
    assert client.get(_url(PROJECT, cast, project=project)).status_code == 404
    assert client.get(_url(ISSUES_DETAIL, cast, project=project)).status_code == 404


def _assert_can_open(client, cast, project, role):
    listed = client.get(_url(PROJECTS, cast))
    assert str(project.id) in _ids(listed)
    assert _row(listed, project)["member_role"] == role
    assert str(project.id) in _ids(client.get(_url(PROJECT_DETAILS, cast)))
    detail = client.get(_url(PROJECT, cast, project=project))
    assert detail.status_code == 200, detail.data
    assert detail.data["member_role"] == role
    assert client.get(_url(ISSUES_DETAIL, cast, project=project)).status_code == 200


@pytest.mark.django_db
class TestTeamspaceVisibility:
    def test_group_teamspace_member_sees_the_board_others_do_not(self, cast, upper_space, secret_alpha, stranger, other_admin):
        _assert_can_open(cast.outsider_client, cast, secret_alpha, role=15)  # teamspace members act as editors
        _assert_cannot_open(client_for(stranger), cast, secret_alpha)
        # Workspace admins belong the way anyone else does: this one is in no group and no project.
        _assert_cannot_open(client_for(other_admin), cast, secret_alpha)
        # An active project membership still counts on a teamspace board.
        _assert_can_open(cast.author_client, cast, secret_alpha, role=15)
        listed = cast.outsider_client.get(_url(PROJECTS, cast))
        row = _row(listed, secret_alpha)
        assert row["section"] == "teamspace"
        assert row["teamspace_id"] == upper_space.id
        assert row["teamspace_detail"]["name"] == "Upper Management"
        assert row["private_owner_id"] is None and row["is_sealed"] is False

    def test_a_public_board_in_a_teamspace_is_still_closed(self, cast, upper_space, secret_alpha, stranger):
        Project.objects.filter(pk=secret_alpha.pk).update(network=2)
        _assert_cannot_open(client_for(stranger), cast, secret_alpha)

    def test_default_teamspace_reaches_every_workspace_member(self, cast, secret_alpha, stranger):
        hq = _teamspace(cast, "Redeemer's Auto Space HQ", is_default=True)
        Project.objects.filter(pk=secret_alpha.pk).update(teamspace=hq)
        card = make_issue(cast, "Needle in HQ")
        client = client_for(stranger)
        _assert_can_open(client, cast, secret_alpha, role=15)
        assert hq.id in user_teamspace_ids(stranger, slug=cast.workspace.slug)
        found = client.get(_url(GLOBAL_SEARCH, cast), {"search": "Needle", "workspace_search": "true"})
        assert found.status_code == 200, found.data
        assert str(card.id) in {str(row["id"]) for row in found.data["results"]["issue"]}
        assert str(secret_alpha.id) in {str(row["id"]) for row in found.data["results"]["project"]}

    def test_nested_group_reaches_the_teamspace(self, cast, secret_alpha, stranger):
        upper = _group(cast, "Upper Management", stranger)
        advisors = _group(cast, "Service Advisors")
        AccessGroupInclude.objects.create(group=advisors, included_group=upper)
        space = _teamspace(cast, "Advisors", group=advisors)
        Project.objects.filter(pk=secret_alpha.pk).update(teamspace=space)
        _assert_can_open(client_for(stranger), cast, secret_alpha, role=15)

    def test_new_group_member_sees_everything_at_once(self, cast, upper, upper_space, secret_alpha, stranger):
        make_issue(cast, "Card one")
        make_issue(cast, "Card two")
        client = client_for(stranger)
        _assert_cannot_open(client, cast, secret_alpha)
        membership = AccessGroupMember.objects.create(group=upper, member=stranger)
        _assert_can_open(client, cast, secret_alpha, role=15)
        assert len(_rows(client.get(_url(ISSUES_DETAIL, cast)))) == 2
        membership.delete()
        _assert_cannot_open(client, cast, secret_alpha)

    def test_child_follows_the_parent_into_the_teamspace(self, cast, upper_space, secret_alpha, stranger):
        gamma = _project(cast, "Gamma")
        assert gamma.teamspace_id is None
        moved = cast.owner_client.patch(_url(PROJECT, cast, project=gamma), {"parent_id": str(secret_alpha.id)}, format="json")
        assert moved.status_code == 200, moved.data
        gamma.refresh_from_db()
        assert gamma.teamspace_id == upper_space.id
        assert moved.data["section"] == "teamspace"
        # The teamspace member sees the child under its parent; a stranger sees neither.
        rows = {str(row["id"]): row for row in _rows(cast.outsider_client.get(_url(PROJECTS, cast)))}
        assert str(gamma.id) in rows and str(rows[str(gamma.id)]["parent_id"]) == str(secret_alpha.id)
        _assert_cannot_open(client_for(stranger), cast, gamma)
        # Changing the parent's place cascades to the subtree.
        cleared = cast.owner_client.patch(_url(PROJECT, cast), {"teamspace_id": None}, format="json")
        assert cleared.status_code == 200, cleared.data
        gamma.refresh_from_db()
        assert gamma.teamspace_id is None
        # Asking for a different place on a child is refused.
        refused = cast.owner_client.patch(
            _url(PROJECT, cast, project=gamma), {"teamspace_id": str(upper_space.id)}, format="json"
        )
        assert refused.status_code == 400

    def test_v1_project_list_includes_the_teamspace_board(self, cast, upper_space, secret_alpha, stranger):
        listed = _api_client(cast.outsider).get(_url(V1_PROJECTS, cast))
        assert listed.status_code == 200, listed.data
        assert str(secret_alpha.id) in _ids(listed)
        assert _row(listed, secret_alpha)["section"] == "teamspace"
        assert str(secret_alpha.id) not in _ids(_api_client(stranger).get(_url(V1_PROJECTS, cast)))


@pytest.fixture
def private_alpha(cast, secret_alpha):
    """Alpha moved into ``author``'s Private area by the workspace admin."""
    response = cast.owner_client.patch(_url(PROJECT, cast), {"private_owner_id": str(cast.author.id)}, format="json")
    assert response.status_code == 200, response.data
    secret_alpha.refresh_from_db()
    return secret_alpha


@pytest.fixture
def readers(cast, stranger):
    """Group "Private Readers" with ``stranger`` in it."""
    return _group(cast, PRIVATE_READERS_GROUP_NAME, stranger)


@pytest.mark.django_db
class TestPrivateArea:
    def test_only_the_owner_sees_a_private_board(self, cast, private_alpha, other_admin):
        assert private_alpha.private_owner_id == cast.author.id
        _assert_can_open(cast.author_client, cast, private_alpha, role=20)  # the owner is its project admin
        assert placement_levels(cast.author, slug=cast.workspace.slug)[private_alpha.id] == LEVEL_OWNER
        # Former members, the workspace admin who moved it, and another admin: nothing.
        for client in (cast.insider_client, cast.friend_client, cast.owner_client, client_for(other_admin)):
            _assert_cannot_open(client, cast, private_alpha)
        assert not ProjectMember.objects.filter(project=private_alpha, member=cast.insider, is_active=True).exists()
        assert ProjectMember.objects.filter(project=private_alpha, member=cast.author, is_active=True, role=20).exists()

    def test_private_board_is_out_of_search_and_shows_its_section(self, cast, private_alpha):
        card = make_issue(cast, "Needle private")
        found = cast.owner_client.get(_url(GLOBAL_SEARCH, cast), {"search": "Needle", "workspace_search": "true"})
        assert str(card.id) not in {str(row["id"]) for row in found.data["results"]["issue"]}
        assert str(private_alpha.id) not in {str(row["id"]) for row in found.data["results"]["project"]}
        row = _row(cast.author_client.get(_url(PROJECTS, cast)), private_alpha)
        assert row["section"] == "private" and row["private_owner_id"] == cast.author.id

    def test_private_readers_read_only_unless_sealed(self, cast, private_alpha, readers, stranger, other_admin):
        client = client_for(stranger)
        _assert_can_open(client, cast, private_alpha, role=5)  # readers act as guests
        assert client.post(_url(ISSUES, cast), {"name": "From a reader"}, format="json").status_code == 403
        assert client.patch(_url(PROJECT, cast), {"is_sealed": True}, format="json").status_code in (400, 403)

        sealed = cast.author_client.patch(_url(PROJECT, cast), {"is_sealed": True}, format="json")
        assert sealed.status_code == 200, sealed.data
        assert sealed.data["is_sealed"] is True
        _assert_cannot_open(client, cast, private_alpha)
        _assert_cannot_open(client_for(other_admin), cast, private_alpha)
        _assert_cannot_open(cast.owner_client, cast, private_alpha)
        _assert_can_open(cast.author_client, cast, private_alpha, role=20)

    def test_sealing_cascades_to_the_boards_inside(self, cast, private_alpha, readers, stranger):
        gamma = _project(cast, "Gamma")
        url = _url(PROJECT, cast, project=gamma)
        # The admin cannot see the private parent any more, so cannot move a board under it.
        assert cast.owner_client.patch(url, {"parent_id": str(private_alpha.id)}, format="json").status_code == 400
        # The owner is not an admin of Gamma.
        assert cast.author_client.patch(url, {"parent_id": str(private_alpha.id)}, format="json").status_code == 403
        # A board that ends up under the private board (here: by hand) follows it when the owner seals.
        Project.objects.filter(pk=gamma.pk).update(parent=private_alpha)
        assert cast.author_client.patch(_url(PROJECT, cast), {"is_sealed": True}, format="json").status_code == 200
        gamma.refresh_from_db()
        assert gamma.is_sealed is True and gamma.private_owner_id == cast.author.id
        assert not ProjectMember.objects.filter(project=gamma, member=cast.owner, is_active=True).exists()
        assert ProjectMember.objects.filter(project=gamma, member=cast.author, is_active=True, role=20).exists()
        _assert_cannot_open(client_for(stranger), cast, gamma)
        _assert_cannot_open(cast.owner_client, cast, gamma)
        _assert_can_open(cast.author_client, cast, gamma, role=20)

    def test_a_group_share_on_a_private_board_is_ignored(self, cast, private_alpha, stranger):
        group = _group(cast, "Service Advisors", stranger)
        ProjectShare.objects.create(workspace=cast.workspace, project=private_alpha, group=group, level=AccessLevel.EDIT)
        assert project_share_level(stranger, private_alpha.id) == 0
        _assert_cannot_open(client_for(stranger), cast, private_alpha)
        # Nothing flows through it to the boards inside either.
        gamma = _project(cast, "Gamma", parent=private_alpha, private_owner=cast.author)
        assert project_share_level(stranger, gamma.id) == 0

    def test_share_endpoint_refuses_a_private_board(self, cast, private_alpha, stranger):
        group = _group(cast, "Service Advisors", stranger)
        response = cast.author_client.post(_url(GROUP_SHARES, cast), {"group_id": str(group.id)}, format="json")
        assert response.status_code in (400, 403)
        assert not ProjectShare.objects.filter(project=private_alpha).exists()

    def test_a_member_makes_their_own_private_board(self, cast, other_admin):
        created = cast.author_client.post(
            _url(PROJECTS, cast), {"name": "Mine", "identifier": "MINE", "private": True}, format="json"
        )
        assert created.status_code == 201, created.data
        assert created.data["section"] == "private"
        assert str(created.data["private_owner_id"]) == str(cast.author.id)
        board = Project.objects.get(pk=created.data["id"])
        assert board.private_owner_id == cast.author.id and board.teamspace_id is None
        _assert_can_open(cast.author_client, cast, board, role=20)
        for client in (cast.insider_client, cast.owner_client, client_for(other_admin)):
            _assert_cannot_open(client, cast, board)

    def test_only_admins_move_boards(self, cast, secret_alpha, upper_space):
        other = _project(cast, "Other")
        ProjectMember.objects.create(project=other, member=cast.author, workspace=cast.workspace, role=20)
        response = cast.author_client.patch(
            _url(PROJECT, cast, project=other), {"teamspace_id": str(upper_space.id)}, format="json"
        )
        assert response.status_code == 400, response.data
        response = cast.author_client.patch(
            _url(PROJECT, cast, project=other), {"private_owner_id": str(cast.author.id)}, format="json"
        )
        assert response.status_code == 400, response.data
        other.refresh_from_db()
        assert other.teamspace_id is None and other.private_owner_id is None

    def test_private_owner_must_be_a_workspace_member_and_seal_needs_an_owner(self, cast, secret_alpha):
        nobody = make_user("nobody")
        response = cast.owner_client.patch(_url(PROJECT, cast), {"private_owner_id": str(nobody.id)}, format="json")
        assert response.status_code == 400
        response = cast.owner_client.patch(_url(PROJECT, cast), {"is_sealed": True}, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestTeamspaceEndpoints:
    def test_admin_crud_and_membership_based_listing(self, cast, upper, stranger, other_admin):
        url = _url(TEAMSPACES, cast)
        created = cast.owner_client.post(url, {"name": "Upper Management", "group_id": str(upper.id)}, format="json")
        assert created.status_code == 201, created.data
        assert created.data["slug"] == "upper-management"
        assert created.data["group_id"] == str(upper.id) and created.data["is_default"] is False
        hq = cast.owner_client.post(url, {"name": "Redeemer's Auto Space HQ", "is_default": True, "position": 5}, format="json")
        assert hq.status_code == 201, hq.data
        assert hq.data["slug"] == "redeemers-auto-space-hq" and hq.data["position"] == 5

        # Listing is by belonging, not role: the admin who made the group teamspace is not in its group.
        assert {row["id"] for row in cast.owner_client.get(url).data} == {hq.data["id"]}
        assert {row["id"] for row in client_for(other_admin).get(url).data} == {hq.data["id"]}
        assert {row["id"] for row in cast.outsider_client.get(url).data} == {created.data["id"], hq.data["id"]}
        assert {row["id"] for row in client_for(stranger).get(url).data} == {hq.data["id"]}
        assert cast.owner_client.get(f"{url}{created.data['id']}/").status_code == 404
        assert cast.outsider_client.get(f"{url}{created.data['id']}/").status_code == 200

        changed = cast.owner_client.patch(f"{url}{hq.data['id']}/", {"name": "HQ", "position": 0}, format="json")
        assert changed.status_code == 200 and changed.data["name"] == "HQ" and changed.data["position"] == 0
        dup = cast.owner_client.post(url, {"name": "HQ", "slug": "redeemers-auto-space-hq"}, format="json")
        assert dup.status_code == 400

        Project.objects.filter(pk=cast.alpha.pk).update(teamspace_id=hq.data["id"])
        assert cast.owner_client.delete(f"{url}{hq.data['id']}/").status_code == 204
        cast.alpha.refresh_from_db()
        assert cast.alpha.teamspace_id is None  # boards fall back to the workspace section

    def test_members_cannot_write_teamspaces(self, cast):
        url = _url(TEAMSPACES, cast)
        assert cast.author_client.post(url, {"name": "Nope"}, format="json").status_code == 403
        space = _teamspace(cast, "Space")
        assert cast.author_client.patch(f"{url}{space.id}/", {"name": "Nope"}, format="json").status_code == 403
        assert cast.author_client.delete(f"{url}{space.id}/").status_code == 403

    def test_v1_api_key_flow_for_scripts(self, cast, secret_alpha, stranger):
        """What the import script does: make a group and its teamspace, move a board in; the member sees it."""
        client = _api_client(cast.owner)
        group = client.post(f"/api/v1/workspaces/{cast.workspace.slug}/access-groups/", {"name": "Upper Management", "member_ids": [str(stranger.id)]}, format="json")
        assert group.status_code == 201, group.data
        space = client.post(_url(V1_TEAMSPACES, cast), {"name": "Upper Management", "group_id": group.data["id"]}, format="json")
        assert space.status_code == 201, space.data
        moved = client.patch(f"{_url(V1_PROJECTS, cast)}{secret_alpha.id}/", {"teamspace_id": space.data["id"]}, format="json")
        assert moved.status_code == 200, moved.data
        assert moved.data["section"] == "teamspace" and moved.data["teamspace_detail"]["id"] == space.data["id"]
        _assert_can_open(client_for(stranger), cast, secret_alpha, role=15)
        assert {row["id"] for row in client_for(stranger).get(_url(TEAMSPACES, cast)).data} == {space.data["id"]}

        # The same key puts the owner's own board in their Private area and seals it.
        mine = client.post(_url(V1_PROJECTS, cast), {"name": "Dashboard", "identifier": "DASH", "private": True}, format="json")
        assert mine.status_code == 201, mine.data
        assert mine.data["section"] == "private"
        sealed = client.patch(f"{_url(V1_PROJECTS, cast)}{mine.data['id']}/", {"is_sealed": True}, format="json")
        assert sealed.status_code == 200 and sealed.data["is_sealed"] is True
        board = Project.objects.get(pk=mine.data["id"])
        _assert_cannot_open(client_for(stranger), cast, board)
        _assert_cannot_open(cast.author_client, cast, board)

    def test_v1_key_of_a_member_cannot_make_a_teamspace(self, cast):
        response = _api_client(cast.author).post(_url(V1_TEAMSPACES, cast), {"name": "Nope"}, format="json")
        assert response.status_code == 403
