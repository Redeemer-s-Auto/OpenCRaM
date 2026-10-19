# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Private projects: only active members see restricted items, admins included.

Runs once ``Project.is_private`` exists (added by the custom-fields work).
"""

import pytest

from plane.db.models import Issue, Project, ProjectMember, WorkspaceMember
from plane.sharing.models import AccessLevel, ShareTarget
from plane.sharing.tests.conftest import make_issue, make_page, make_user, client_for, restrict
from plane.sharing.visibility import _private_projects_supported, issue_access_level, page_access_level, visible_issues

pytestmark = pytest.mark.skipif(
    not _private_projects_supported(), reason="Project.is_private is not on this branch yet"
)


@pytest.fixture
def private_alpha(cast):
    Project.objects.filter(pk=cast.alpha.pk).update(is_private=True)
    return cast.alpha


@pytest.fixture
def other_admin(cast):
    """A workspace admin who is NOT a member of Alpha."""
    user = make_user("admin2")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=user, role=20)
    return user


@pytest.mark.django_db
class TestPrivateProjectGate:
    def test_non_member_admin_cannot_see_restricted_item(self, cast, private_alpha, other_admin, secret_issue):
        assert issue_access_level(other_admin, secret_issue.id) == 0
        assert secret_issue.id not in set(visible_issues(Issue.objects.all(), other_admin).values_list("id", flat=True))

    def test_admin_in_normal_project_still_sees_it(self, cast, other_admin, secret_issue):
        assert issue_access_level(other_admin, secret_issue.id) == AccessLevel.EDIT

    def test_share_does_not_reach_outside_a_private_project(self, cast, private_alpha):
        issue = make_issue(cast, "Private card shared out")
        restrict(cast, issue=issue, shares=[(ShareTarget.MEMBER, cast.outsider, AccessLevel.EDIT)])
        assert issue_access_level(cast.outsider, issue.id) == 0
        response = cast.outsider_client.get(f"/api/workspaces/{cast.workspace.slug}/shared-with-me/")
        assert response.status_code == 200 and response.data == []
        assert (
            cast.outsider_client.get(f"/api/workspaces/{cast.workspace.slug}/shared-with-me/issues/{issue.id}/").status_code
            == 404
        )

    def test_members_keep_their_access(self, cast, private_alpha, secret_issue):
        assert issue_access_level(cast.author, secret_issue.id) == AccessLevel.EDIT
        assert issue_access_level(cast.friend, secret_issue.id) == AccessLevel.VIEW
        assert issue_access_level(cast.insider, secret_issue.id) == 0

    def test_creator_removed_from_private_project_loses_access(self, cast, private_alpha, secret_issue):
        ProjectMember.objects.filter(project=cast.alpha, member=cast.author).update(is_active=False)
        assert issue_access_level(cast.author, secret_issue.id) == 0

    def test_owner_who_is_not_a_member_is_blocked(self, cast, private_alpha, secret_issue):
        ProjectMember.objects.filter(project=cast.alpha, member=cast.owner).update(is_active=False)
        assert issue_access_level(cast.owner, secret_issue.id) == 0
        assert client_for(cast.owner).get(
            f"/api/workspaces/{cast.workspace.slug}/shared-with-me/issues/{secret_issue.id}/"
        ).status_code == 404

    def test_pages_follow_the_same_rule(self, cast, private_alpha, other_admin):
        page = make_page(cast, "Private page")
        restrict(cast, page=page, shares=[(ShareTarget.MEMBER, cast.outsider, AccessLevel.VIEW)])
        assert page_access_level(other_admin, page.id) == 0
        assert page_access_level(cast.outsider, page.id) == 0
        assert page_access_level(cast.author, page.id) == AccessLevel.EDIT
