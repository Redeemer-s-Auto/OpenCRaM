# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""The sharing settings endpoints, the Groups endpoints, and the direct-link guard."""

import pytest

from plane.sharing.models import AccessGroup, AccessLevel, ItemRestriction, ShareTarget
from plane.sharing.tests.conftest import make_issue, make_page, restrict

ISSUE_PERMS = "/api/workspaces/{slug}/projects/{project}/issues/{issue}/permissions/"
PAGE_PERMS = "/api/workspaces/{slug}/projects/{project}/pages/{page}/permissions/"
ISSUE_DETAIL = "/api/workspaces/{slug}/projects/{project}/issues/{issue}/"
ISSUE_COMMENTS = "/api/workspaces/{slug}/projects/{project}/issues/{issue}/comments/"


def issue_url(template, cast, issue):
    return template.format(slug=cast.workspace.slug, project=cast.alpha.id, issue=issue.id)


@pytest.mark.django_db
class TestSharingSettings:
    def test_creator_restricts_and_shares(self, cast):
        issue = make_issue(cast, "To restrict")
        response = cast.author_client.put(
            issue_url(ISSUE_PERMS, cast, issue),
            {
                "restricted": True,
                "shares": [
                    {"target_type": "member", "target_id": str(cast.friend.id), "level": AccessLevel.EDIT},
                    {"target_type": "project", "target_id": str(cast.beta.id), "level": AccessLevel.VIEW},
                ],
            },
            format="json",
        )
        assert response.status_code == 200, response.content
        assert response.data["restricted"] is True
        assert {s["target_type"] for s in response.data["shares"]} == {"member", "project"}
        assert cast.insider_client.get(issue_url(ISSUE_DETAIL, cast, issue)).status_code == 404

    def test_back_to_department_mode(self, cast, secret_issue):
        response = cast.author_client.put(
            issue_url(ISSUE_PERMS, cast, secret_issue), {"restricted": False, "shares": []}, format="json"
        )
        assert response.status_code == 200
        assert not ItemRestriction.objects.filter(issue=secret_issue).exists()
        assert cast.insider_client.get(issue_url(ISSUE_DETAIL, cast, secret_issue)).status_code == 200

    def test_shared_editor_cannot_change_sharing(self, cast):
        issue = make_issue(cast, "Friend can edit")
        restrict(cast, issue=issue, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.EDIT)])
        response = cast.friend_client.put(
            issue_url(ISSUE_PERMS, cast, issue), {"restricted": False, "shares": []}, format="json"
        )
        assert response.status_code == 403

    def test_insider_cannot_read_settings_of_hidden_item(self, cast, secret_issue):
        assert cast.insider_client.get(issue_url(ISSUE_PERMS, cast, secret_issue)).status_code == 404

    def test_admin_can_change_sharing(self, cast, secret_issue):
        response = cast.owner_client.put(
            issue_url(ISSUE_PERMS, cast, secret_issue), {"restricted": True, "shares": []}, format="json"
        )
        assert response.status_code == 200
        assert response.data["shares"] == []

    def test_rejects_target_from_other_workspace(self, cast):
        issue = make_issue(cast, "Bad target")
        response = cast.author_client.put(
            issue_url(ISSUE_PERMS, cast, issue),
            {"restricted": True, "shares": [{"target_type": "group", "target_id": "00000000-0000-0000-0000-000000000000"}]},
            format="json",
        )
        assert response.status_code == 400

    def test_page_settings(self, cast):
        page = make_page(cast, "Page to restrict")
        url = PAGE_PERMS.format(slug=cast.workspace.slug, project=cast.alpha.id, page=page.id)
        response = cast.author_client.put(
            url,
            {"restricted": True, "shares": [{"target_type": "member", "target_id": str(cast.friend.id), "level": 5}]},
            format="json",
        )
        assert response.status_code == 200, response.content
        assert cast.insider_client.get(url).status_code == 404
        assert cast.friend_client.get(url).status_code == 200


@pytest.mark.django_db
class TestGuard:
    def test_hidden_detail_is_404(self, cast, secret_issue):
        assert cast.insider_client.get(issue_url(ISSUE_DETAIL, cast, secret_issue)).status_code == 404

    def test_viewer_reads_but_cannot_edit(self, cast, secret_issue):
        url = issue_url(ISSUE_DETAIL, cast, secret_issue)
        assert cast.friend_client.get(url).status_code == 200
        assert cast.friend_client.patch(url, {"name": "changed"}, format="json").status_code == 403

    def test_viewer_cannot_comment_but_commenter_can(self, cast):
        issue = make_issue(cast, "Comment levels")
        restrict(
            cast,
            issue=issue,
            shares=[
                (ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW),
                (ShareTarget.MEMBER, cast.insider, AccessLevel.COMMENT),
            ],
        )
        url = issue_url(ISSUE_COMMENTS, cast, issue)
        body = {"comment_html": "<p>hello</p>"}
        assert cast.friend_client.post(url, body, format="json").status_code == 403
        assert cast.insider_client.post(url, body, format="json").status_code == 201

    def test_editor_can_edit(self, cast):
        issue = make_issue(cast, "Editor")
        restrict(cast, issue=issue, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.EDIT)])
        url = issue_url(ISSUE_DETAIL, cast, issue)
        assert cast.friend_client.patch(url, {"name": "changed"}, format="json").status_code == 204


@pytest.mark.django_db
class TestGroups:
    def test_admin_creates_group(self, cast):
        url = f"/api/workspaces/{cast.workspace.slug}/access-groups/"
        response = cast.owner_client.post(
            url, {"name": "Leads", "member_ids": [str(cast.friend.id), str(cast.outsider.id)]}, format="json"
        )
        assert response.status_code == 201, response.content
        assert response.data["member_count"] == 2
        listed = cast.insider_client.get(url)
        assert listed.status_code == 200
        assert [g["name"] for g in listed.data] == ["Leads"]

    def test_member_cannot_create_or_edit_group(self, cast):
        url = f"/api/workspaces/{cast.workspace.slug}/access-groups/"
        assert cast.insider_client.post(url, {"name": "Mine"}, format="json").status_code == 403
        group = AccessGroup.objects.create(workspace=cast.workspace, name="Leads")
        detail = f"{url}{group.id}/"
        assert cast.insider_client.patch(detail, {"name": "Hacked"}, format="json").status_code == 403
        assert cast.insider_client.delete(detail).status_code == 403

    def test_group_member_must_be_in_workspace(self, cast):
        url = f"/api/workspaces/{cast.workspace.slug}/access-groups/"
        response = cast.owner_client.post(
            url, {"name": "Leads", "member_ids": ["00000000-0000-0000-0000-000000000000"]}, format="json"
        )
        assert response.status_code == 400
