# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Leak tests for work item lists, sub-items, relations, archives, intake and search.

Each test shows that ``insider`` (same project, not on the share list) gets no row,
no id, no count and no name of a restricted item, and that ``author`` or ``friend``
still does, so a pass proves the filter and not a broken endpoint.
"""

import pytest

from plane.db.models import (
    Intake,
    IntakeIssue,
    Issue,
    IssueActivity,
    IssueComment,
    IssueRelation,
    ProjectMember,
    State,
)
from plane.sharing.models import AccessLevel, ShareTarget
from plane.sharing.tests.conftest import make_issue, make_page, restrict

MARK = b"TOPSECRET"


def base(cast):
    return f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}"


def leaks(response, *items):
    """True when the response names any of ``items`` (by marker or id)."""
    content = response.content
    return MARK in content or any(str(item.id).encode() in content for item in items)


def assert_hidden(response, *items):
    assert response.status_code == 200, response.content
    assert not leaks(response, *items), response.content


def assert_shown(response, item):
    assert response.status_code == 200, response.content
    assert str(item.id).encode() in response.content


def make_admin(cast, user):
    ProjectMember.objects.filter(project=cast.alpha, member=user).update(role=20)


@pytest.mark.django_db
class TestIssueLists:
    def test_project_list(self, cast, secret_issue, open_issue):
        url = f"{base(cast)}/issues/"
        response = cast.insider_client.get(url)
        assert_hidden(response, secret_issue)
        assert response.data["total_count"] == 1
        assert_shown(cast.author_client.get(url), secret_issue)
        assert_shown(cast.friend_client.get(url), secret_issue)

    def test_project_list_grouped(self, cast, secret_issue, open_issue):
        url = f"{base(cast)}/issues/?group_by=state_id"
        response = cast.insider_client.get(url)
        assert_hidden(response, secret_issue)
        assert response.data["results"][str(cast.state.id)]["total_results"] == 1
        assert_shown(cast.author_client.get(url), secret_issue)

    def test_list_by_ids(self, cast, secret_issue, open_issue):
        url = f"{base(cast)}/issues/list/?issues={secret_issue.id},{open_issue.id}"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)

    def test_paginated_v2(self, cast, secret_issue, open_issue):
        url = f"{base(cast)}/v2/issues/"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)

    def test_issues_detail_list_with_relations(self, cast, secret_issue, open_issue):
        IssueRelation.objects.create(
            issue=open_issue, related_issue=secret_issue, relation_type="relates_to",
            project=cast.alpha, workspace=cast.workspace,
        )
        url = f"{base(cast)}/issues-detail/?expand=issue_relation,issue_related"
        response = cast.insider_client.get(url)
        assert_hidden(response, secret_issue)
        assert_shown(response, open_issue)
        assert_shown(cast.author_client.get(url), secret_issue)

    def test_deleted_and_archived_ids(self, cast, secret_issue, open_issue):
        Issue.all_objects.filter(pk=secret_issue.pk).update(archived_at="2026-01-01")
        url = f"{base(cast)}/deleted-issues/"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)

    def test_archived_list(self, cast, secret_issue):
        Issue.all_objects.filter(pk=secret_issue.pk).update(archived_at="2026-01-01")
        url = f"{base(cast)}/archived-issues/"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)


@pytest.mark.django_db
class TestParentAndChildren:
    def test_hidden_child_not_counted(self, cast, open_issue):
        child = make_issue(cast, "Child TOPSECRET", parent=open_issue)
        restrict(cast, issue=child)
        url = f"{base(cast)}/issues/{open_issue.id}/"
        assert not cast.insider_client.get(url).data["sub_issues_count"]
        assert cast.author_client.get(url).data["sub_issues_count"] == 1
        listed = cast.insider_client.get(f"{base(cast)}/issues/")
        assert_hidden(listed, child)

    def test_visible_child_of_hidden_parent_shows_no_parent(self, cast, secret_issue):
        child = make_issue(cast, "Visible child", parent=secret_issue)
        detail = cast.insider_client.get(f"{base(cast)}/issues/{child.id}/")
        assert detail.status_code == 200
        assert detail.data["parent_id"] is None
        assert_hidden(detail, secret_issue)
        listed = cast.insider_client.get(f"{base(cast)}/issues/")
        assert_hidden(listed, secret_issue)
        by_identifier = cast.insider_client.get(
            f"/api/workspaces/{cast.workspace.slug}/work-items/{cast.alpha.identifier}-{child.sequence_id}/"
        )
        assert_hidden(by_identifier, secret_issue)
        assert cast.author_client.get(f"{base(cast)}/issues/{child.id}/").data["parent_id"] == secret_issue.id

    def test_sub_issue_list(self, cast, open_issue):
        child = make_issue(cast, "Child TOPSECRET", parent=open_issue)
        restrict(cast, issue=child)
        url = f"{base(cast)}/issues/{open_issue.id}/sub-issues/"
        assert_hidden(cast.insider_client.get(url), child)
        assert_shown(cast.author_client.get(url), child)

    def test_cannot_attach_hidden_sub_issue(self, cast, secret_issue, open_issue):
        url = f"{base(cast)}/issues/{open_issue.id}/sub-issues/"
        response = cast.insider_client.post(url, {"sub_issue_ids": [str(secret_issue.id)]}, format="json")
        assert_hidden(response, secret_issue)
        secret_issue.refresh_from_db()
        assert secret_issue.parent_id is None

    def test_cannot_create_under_hidden_parent(self, cast, secret_issue):
        response = cast.insider_client.post(
            f"{base(cast)}/issues/", {"name": "Sneaky", "parent_id": str(secret_issue.id)}, format="json"
        )
        assert response.status_code == 400
        assert MARK not in response.content

    def test_cannot_move_under_hidden_parent(self, cast, secret_issue, open_issue):
        response = cast.insider_client.patch(
            f"{base(cast)}/issues/{open_issue.id}/", {"parent_id": str(secret_issue.id)}, format="json"
        )
        assert response.status_code == 400
        open_issue.refresh_from_db()
        assert open_issue.parent_id is None


@pytest.mark.django_db
class TestRelations:
    def test_relation_list_drops_hidden(self, cast, secret_issue, open_issue):
        IssueRelation.objects.create(
            issue=open_issue, related_issue=secret_issue, relation_type="relates_to",
            project=cast.alpha, workspace=cast.workspace,
        )
        url = f"{base(cast)}/issues/{open_issue.id}/issue-relation/"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)

    def test_cannot_relate_to_hidden(self, cast, secret_issue, open_issue):
        url = f"{base(cast)}/issues/{open_issue.id}/issue-relation/"
        response = cast.insider_client.post(
            url, {"relation_type": "relates_to", "issues": [str(secret_issue.id)]}, format="json"
        )
        assert response.status_code == 201
        assert not leaks(response, secret_issue)
        assert not IssueRelation.objects.filter(related_issue=secret_issue).exists()
        assert not IssueActivity.objects.filter(issue=secret_issue).exists()

    def test_activity_does_not_name_hidden(self, cast, secret_issue, open_issue):
        IssueActivity.objects.create(
            issue=open_issue, verb="updated", field="parent", new_value=f"ALP-{secret_issue.sequence_id}",
            new_identifier=secret_issue.id, project=cast.alpha, workspace=cast.workspace, actor=cast.author,
        )
        url = f"{base(cast)}/issues/{open_issue.id}/history/?activity_type=issue-property"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)


@pytest.mark.django_db
class TestBulkEndpoints:
    def test_bulk_delete_skips_hidden(self, cast, secret_issue, open_issue):
        make_admin(cast, cast.insider)
        response = cast.insider_client.delete(
            f"{base(cast)}/bulk-delete-issues/",
            {"issue_ids": [str(secret_issue.id), str(open_issue.id)]},
            format="json",
        )
        assert response.status_code == 200
        assert b"1 issues" in response.content
        secret_issue.refresh_from_db()
        assert secret_issue.deleted_at is None

    def test_bulk_dates_skip_hidden(self, cast, secret_issue):
        response = cast.insider_client.post(
            f"{base(cast)}/issue-dates/",
            {"updates": [{"id": str(secret_issue.id), "target_date": "2030-01-01"}]},
            format="json",
        )
        assert response.status_code == 200
        secret_issue.refresh_from_db()
        assert secret_issue.target_date is None

    def test_bulk_dates_viewer_cannot_change(self, cast, secret_issue):
        cast.friend_client.post(
            f"{base(cast)}/issue-dates/",
            {"updates": [{"id": str(secret_issue.id), "target_date": "2030-01-01"}]},
            format="json",
        )
        secret_issue.refresh_from_db()
        assert secret_issue.target_date is None

    def test_bulk_archive_skips_hidden(self, cast):
        done = State.objects.create(
            name="Done", project=cast.alpha, workspace=cast.workspace, group="completed"
        )
        issue = make_issue(cast, "Done TOPSECRET")
        issue.state = done
        issue.save()
        restrict(cast, issue=issue)
        response = cast.insider_client.post(
            f"{base(cast)}/bulk-archive-issues/", {"issue_ids": [str(issue.id)]}, format="json"
        )
        assert response.status_code == 200
        issue.refresh_from_db()
        assert issue.archived_at is None


@pytest.mark.django_db
class TestCommentReactions:
    def test_reactions_on_hidden_comment(self, cast, secret_issue):
        comment = IssueComment.objects.create(
            issue=secret_issue, project=cast.alpha, workspace=cast.workspace, actor=cast.author,
            comment_html="<p>hi</p>",
        )
        url = f"{base(cast)}/comments/{comment.id}/reactions/"
        assert cast.insider_client.get(url).status_code == 404
        assert cast.insider_client.post(url, {"reaction": "1"}, format="json").status_code == 404
        assert cast.friend_client.get(url).status_code == 200
        assert cast.friend_client.post(url, {"reaction": "1"}, format="json").status_code == 403


@pytest.mark.django_db
class TestIntake:
    def make_intake(self, cast):
        return Intake.objects.create(name="Intake", project=cast.alpha, workspace=cast.workspace, is_default=True)

    def test_intake_list_and_count(self, cast, secret_issue):
        intake = self.make_intake(cast)
        IntakeIssue.objects.create(
            intake=intake, issue=secret_issue, project=cast.alpha, workspace=cast.workspace, status=-2
        )
        url = f"{base(cast)}/intake-issues/"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)
        count_url = f"{base(cast)}/intakes/"
        assert cast.insider_client.get(count_url).data["pending_issue_count"] == 0
        assert cast.author_client.get(count_url).data["pending_issue_count"] == 1

    def test_duplicate_of_hidden_item(self, cast, secret_issue, open_issue):
        intake = self.make_intake(cast)
        IntakeIssue.objects.create(
            intake=intake, issue=open_issue, project=cast.alpha, workspace=cast.workspace, status=-2,
            duplicate_to=secret_issue,
        )
        response = cast.insider_client.get(f"{base(cast)}/intake-issues/{open_issue.id}/")
        assert_hidden(response, secret_issue)
        assert response.data["duplicate_to"] is None
        listed = cast.insider_client.get(f"{base(cast)}/intake-issues/")
        assert_hidden(listed, secret_issue)
        assert_shown(cast.author_client.get(f"{base(cast)}/intake-issues/{open_issue.id}/"), secret_issue)


@pytest.mark.django_db
class TestSearch:
    def test_global_search(self, cast, secret_issue, secret_page):
        intake = Intake.objects.create(name="Intake", project=cast.alpha, workspace=cast.workspace)
        IntakeIssue.objects.create(
            intake=intake, issue=secret_issue, project=cast.alpha, workspace=cast.workspace, status=-2
        )
        url = f"/api/workspaces/{cast.workspace.slug}/search/?search=TOPSECRET&workspace_search=true"
        response = cast.insider_client.get(url)
        assert_hidden(response, secret_issue, secret_page)
        shown = cast.author_client.get(url)
        assert_shown(shown, secret_issue)
        assert_shown(shown, secret_page)

    def test_global_search_skips_private_pages_of_others(self, cast):
        page = make_page(cast, "Private notes TOPSECRET")
        page.access = 1
        page.save()
        url = f"/api/workspaces/{cast.workspace.slug}/search/?search=TOPSECRET&entities=page&workspace_search=true"
        assert_hidden(cast.insider_client.get(url), page)
        assert_shown(cast.author_client.get(url), page)

    def test_entity_search(self, cast, secret_issue, secret_page):
        for suffix in (f"&project_id={cast.alpha.id}", ""):
            url = f"/api/workspaces/{cast.workspace.slug}/entity-search/?query=TOPSECRET&query_type=issue,page{suffix}"
            assert_hidden(cast.insider_client.get(url), secret_issue, secret_page)
            assert_shown(cast.author_client.get(url), secret_issue)

    def test_entity_search_project_pages(self, cast, secret_page):
        url = (
            f"/api/workspaces/{cast.workspace.slug}/entity-search/"
            f"?query=TOPSECRET&query_type=page&project_id={cast.alpha.id}"
        )
        assert_hidden(cast.insider_client.get(url), secret_page)
        assert_shown(cast.author_client.get(url), secret_page)

    def test_issue_picker(self, cast, secret_issue, open_issue):
        url = f"{base(cast)}/search-issues/?search=TOPSECRET"
        assert_hidden(cast.insider_client.get(url), secret_issue)
        assert_shown(cast.author_client.get(url), secret_issue)
        picker = f"{base(cast)}/search-issues/?parent=true&issue_id={open_issue.id}"
        assert_hidden(cast.insider_client.get(picker), secret_issue)
        assert_shown(cast.friend_client.get(picker), secret_issue)

    def test_outsider_sees_nothing(self, cast, secret_issue):
        url = f"/api/workspaces/{cast.workspace.slug}/search/?search=TOPSECRET&workspace_search=true"
        assert_hidden(cast.outsider_client.get(url), secret_issue)
