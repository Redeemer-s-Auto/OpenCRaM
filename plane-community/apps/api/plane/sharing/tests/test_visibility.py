# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

import pytest
from django.contrib.auth.models import AnonymousUser

from plane.db.models import Issue, Page
from plane.sharing.models import AccessGroup, AccessGroupMember, AccessLevel, ShareTarget
from plane.sharing.tests.conftest import make_issue, make_page, restrict
from plane.sharing.visibility import (
    issue_access_level,
    page_access_level,
    visible_issues,
    visible_pages,
)


def ids(queryset):
    return set(queryset.values_list("id", flat=True))


@pytest.mark.django_db
class TestIssueVisibility:
    def test_unrestricted_item_is_unchanged(self, cast, open_issue):
        for user in (cast.insider, cast.outsider, cast.friend):
            assert open_issue.id in ids(visible_issues(Issue.objects.all(), user))
            assert issue_access_level(user, open_issue.id) is None

    def test_insider_without_share_sees_nothing(self, cast, secret_issue):
        assert secret_issue.id not in ids(visible_issues(Issue.objects.all(), cast.insider))
        assert issue_access_level(cast.insider, secret_issue.id) == 0

    def test_creator_admin_owner_and_friend_see_it(self, cast, secret_issue):
        for user in (cast.author, cast.owner, cast.friend):
            assert secret_issue.id in ids(visible_issues(Issue.objects.all(), user))
        assert issue_access_level(cast.author, secret_issue.id) == AccessLevel.EDIT
        assert issue_access_level(cast.owner, secret_issue.id) == AccessLevel.EDIT
        assert issue_access_level(cast.friend, secret_issue.id) == AccessLevel.VIEW

    def test_non_owner_workspace_admin_sees_it(self, cast, secret_issue):
        from plane.db.models import WorkspaceMember

        WorkspaceMember.objects.filter(workspace=cast.workspace, member=cast.insider).update(role=20)
        assert issue_access_level(cast.insider, secret_issue.id) == AccessLevel.EDIT

    def test_anonymous_and_none_see_nothing(self, cast, secret_issue):
        for user in (None, AnonymousUser()):
            assert secret_issue.id not in ids(visible_issues(Issue.objects.all(), user))
            assert issue_access_level(user, secret_issue.id) == 0

    def test_min_level_filters(self, cast, secret_issue):
        assert secret_issue.id not in ids(visible_issues(Issue.objects.all(), cast.friend, min_level=AccessLevel.EDIT))

    def test_project_share(self, cast):
        issue = make_issue(cast, "Shared with Beta")
        restrict(cast, issue=issue, shares=[(ShareTarget.PROJECT, cast.beta, AccessLevel.COMMENT)])
        assert issue_access_level(cast.outsider, issue.id) == AccessLevel.COMMENT
        assert issue_access_level(cast.insider, issue.id) == 0

    def test_group_share(self, cast):
        group = AccessGroup.objects.create(workspace=cast.workspace, name="Leads")
        AccessGroupMember.objects.create(group=group, member=cast.outsider)
        issue = make_issue(cast, "Shared with a group")
        restrict(cast, issue=issue, shares=[(ShareTarget.GROUP, group, AccessLevel.EDIT)])
        assert issue_access_level(cast.outsider, issue.id) == AccessLevel.EDIT
        assert issue_access_level(cast.insider, issue.id) == 0

    def test_workspace_share(self, cast):
        issue = make_issue(cast, "Shared with everybody")
        restrict(cast, issue=issue, shares=[(ShareTarget.WORKSPACE, None, AccessLevel.VIEW)])
        assert issue_access_level(cast.insider, issue.id) == AccessLevel.VIEW
        assert issue_access_level(cast.outsider, issue.id) == AccessLevel.VIEW

    def test_highest_level_wins(self, cast):
        issue = make_issue(cast, "Two shares")
        restrict(
            cast,
            issue=issue,
            shares=[
                (ShareTarget.PROJECT, cast.alpha, AccessLevel.VIEW),
                (ShareTarget.MEMBER, cast.friend, AccessLevel.EDIT),
            ],
        )
        assert issue_access_level(cast.friend, issue.id) == AccessLevel.EDIT
        assert issue_access_level(cast.insider, issue.id) == AccessLevel.VIEW

    def test_inactive_project_member_loses_access(self, cast):
        from plane.db.models import ProjectMember

        issue = make_issue(cast, "Shared with Beta")
        restrict(cast, issue=issue, shares=[(ShareTarget.PROJECT, cast.beta, AccessLevel.VIEW)])
        ProjectMember.objects.filter(project=cast.beta, member=cast.outsider).update(is_active=False)
        assert issue_access_level(cast.outsider, issue.id) == 0

    def test_nullable_field_filter_keeps_null_rows(self, cast, secret_issue, open_issue):
        """Rows with no linked item must not vanish from related-row filters."""
        child = make_issue(cast, "No parent")
        queryset = visible_issues(Issue.objects.filter(id__in=[child.id]), cast.insider, field="parent_id")
        assert child.id in ids(queryset)
        hidden_child = make_issue(cast, "Child of secret", parent=secret_issue)
        queryset = visible_issues(Issue.objects.filter(id__in=[hidden_child.id]), cast.insider, field="parent_id")
        assert hidden_child.id not in ids(queryset)


@pytest.mark.django_db
class TestPageVisibility:
    def test_insider_without_share_sees_nothing(self, cast, secret_page):
        assert secret_page.id not in ids(visible_pages(Page.objects.all(), cast.insider))
        assert page_access_level(cast.insider, secret_page.id) == 0

    def test_owner_admin_and_friend_see_it(self, cast, secret_page):
        for user in (cast.author, cast.owner, cast.friend):
            assert secret_page.id in ids(visible_pages(Page.objects.all(), user))

    def test_unrestricted_page_is_unchanged(self, cast):
        page = make_page(cast, "Open page")
        assert page.id in ids(visible_pages(Page.objects.all(), cast.outsider))
