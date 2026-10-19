# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Reaching an item shared with you from outside its project.

``outsider`` is a member of Beta only. Items live in Alpha.
"""

import pytest

from plane.db.models import IssueComment, WorkspaceMember
from plane.sharing.models import AccessGroup, AccessGroupMember, AccessLevel, ShareTarget
from plane.sharing.tests.conftest import make_issue, make_page, make_user, client_for, restrict

MARK = "TOPSECRET"


def base(cast):
    return f"/api/workspaces/{cast.workspace.slug}/shared-with-me/"


def issue_url(cast, issue, suffix=""):
    return f"{base(cast)}issues/{issue.id}/{suffix}"


@pytest.fixture
def shared(cast):
    """A card shared with the outsider (Can view) and one with the Beta department (Can comment)."""
    view_only = make_issue(cast, f"View only {MARK}")
    restrict(cast, issue=view_only, shares=[(ShareTarget.MEMBER, cast.outsider, AccessLevel.VIEW)])
    commentable = make_issue(cast, f"Commentable {MARK}")
    restrict(cast, issue=commentable, shares=[(ShareTarget.PROJECT, cast.beta, AccessLevel.COMMENT)])
    editable = make_issue(cast, f"Editable {MARK}")
    restrict(cast, issue=editable, shares=[(ShareTarget.MEMBER, cast.outsider, AccessLevel.EDIT)])

    class Shared:
        pass

    s = Shared()
    s.view_only, s.commentable, s.editable = view_only, commentable, editable
    return s


@pytest.mark.django_db
class TestSharedWithMeList:
    def test_outsider_lists_items_shared_with_them(self, cast, shared, secret_issue):
        response = cast.outsider_client.get(base(cast))
        assert response.status_code == 200, response.content
        ids = {row["id"] for row in response.data}
        assert ids == {str(shared.view_only.id), str(shared.commentable.id), str(shared.editable.id)}
        assert str(secret_issue.id) not in response.content.decode()
        row = next(r for r in response.data if r["id"] == str(shared.view_only.id))
        assert row["in_project"] is False and row["level"] == AccessLevel.VIEW

    def test_insider_not_on_list_sees_nothing(self, cast, shared):
        response = cast.insider_client.get(base(cast))
        assert response.status_code == 200
        assert response.data == []

    def test_group_share_reaches_member(self, cast):
        group = AccessGroup.objects.create(workspace=cast.workspace, name="Leads")
        AccessGroupMember.objects.create(group=group, member=cast.outsider)
        issue = make_issue(cast, "Group card")
        restrict(cast, issue=issue, shares=[(ShareTarget.GROUP, group, AccessLevel.VIEW)])
        assert [row["id"] for row in cast.outsider_client.get(base(cast)).data] == [str(issue.id)]

    def test_pages_are_listed(self, cast):
        page = make_page(cast, f"Shared page {MARK}")
        restrict(cast, page=page, shares=[(ShareTarget.MEMBER, cast.outsider, AccessLevel.VIEW)])
        rows = cast.outsider_client.get(base(cast)).data
        assert [(row["kind"], row["id"]) for row in rows] == [("page", str(page.id))]


@pytest.mark.django_db
class TestSharedIssue:
    def test_outsider_reads_shared_item(self, cast, shared):
        response = cast.outsider_client.get(issue_url(cast, shared.view_only))
        assert response.status_code == 200, response.content
        assert response.data["name"].startswith("View only")
        assert response.data["project_name"] == "Alpha"

    def test_outsider_cannot_read_other_items_in_the_project(self, cast, shared, secret_issue, open_issue):
        assert cast.outsider_client.get(issue_url(cast, secret_issue)).status_code == 404
        # an unrestricted item is not "shared": the outsider still needs project membership
        assert cast.outsider_client.get(issue_url(cast, open_issue)).status_code == 404
        # and the normal project screens stay closed
        project_url = f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/issues/{shared.view_only.id}/"
        assert cast.outsider_client.get(project_url).status_code in (403, 404)

    def test_view_level_cannot_edit_or_comment(self, cast, shared):
        assert cast.outsider_client.patch(issue_url(cast, shared.view_only), {"name": "x"}, format="json").status_code == 403
        assert (
            cast.outsider_client.post(issue_url(cast, shared.view_only, "comments/"), {"comment_html": "<p>hi</p>"}, format="json").status_code
            == 403
        )

    def test_comment_level_comments(self, cast, shared):
        url = issue_url(cast, shared.commentable, "comments/")
        response = cast.outsider_client.post(url, {"comment_html": "<p>from outside</p>"}, format="json")
        assert response.status_code == 201, response.content
        assert IssueComment.objects.filter(issue=shared.commentable, actor=cast.outsider).count() == 1
        listed = cast.outsider_client.get(url)
        assert listed.status_code == 200 and "from outside" in listed.content.decode()
        assert cast.outsider_client.patch(issue_url(cast, shared.commentable), {"name": "x"}, format="json").status_code == 403

    def test_edit_level_edits_name_and_text_only(self, cast, shared):
        url = issue_url(cast, shared.editable)
        response = cast.outsider_client.patch(
            url, {"name": "Renamed", "description_html": "<p>New text</p>", "priority": "urgent"}, format="json"
        )
        assert response.status_code == 200, response.content
        shared.editable.refresh_from_db()
        assert shared.editable.name == "Renamed"
        assert "New text" in shared.editable.description_html
        assert shared.editable.priority != "urgent"

    def test_removed_from_workspace_loses_access(self, cast, shared):
        WorkspaceMember.objects.filter(workspace=cast.workspace, member=cast.outsider).update(is_active=False)
        assert cast.outsider_client.get(issue_url(cast, shared.view_only)).status_code in (403, 404)

    def test_everybody_share_skips_guests(self, cast):
        guest = make_user("guest")
        WorkspaceMember.objects.create(workspace=cast.workspace, member=guest, role=5)
        issue = make_issue(cast, "Everybody card")
        restrict(cast, issue=issue, shares=[(ShareTarget.WORKSPACE, None, AccessLevel.VIEW)])
        assert client_for(guest).get(issue_url(cast, issue)).status_code == 404
        assert cast.outsider_client.get(issue_url(cast, issue)).status_code == 200


@pytest.mark.django_db
class TestSharedPage:
    def test_outsider_reads_shared_page_only(self, cast, secret_page):
        page = make_page(cast, "Shared page")
        restrict(cast, page=page, shares=[(ShareTarget.MEMBER, cast.outsider, AccessLevel.VIEW)])
        url = f"{base(cast)}pages/{page.id}/"
        response = cast.outsider_client.get(url)
        assert response.status_code == 200, response.content
        assert response.data["name"] == "Shared page"
        assert cast.outsider_client.get(f"{base(cast)}pages/{secret_page.id}/").status_code == 404
        open_page = make_page(cast, "Open page")
        assert cast.outsider_client.get(f"{base(cast)}pages/{open_page.id}/").status_code == 404


@pytest.mark.django_db
def test_read_view_strips_scripts(cast):
    issue = make_issue(cast, "Script card", description_html='<p>hi</p><script>alert(1)</script><img src=x onerror="alert(2)">')
    restrict(cast, issue=issue, shares=[(ShareTarget.MEMBER, cast.outsider, AccessLevel.VIEW)])
    body = cast.outsider_client.get(issue_url(cast, issue)).data["description_html"]
    assert "<script" not in body and "onerror" not in body and "<p>hi</p>" in body
