# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Leak tests: public API v1, public deploy boards (space) and project pages."""

import pytest
from rest_framework.test import APIClient

from plane.db.models import (
    Cycle,
    CycleIssue,
    DeployBoard,
    Intake,
    IntakeIssue,
    Issue,
    IssueActivity,
    IssueRelation,
    Module,
    ModuleIssue,
    Page,
    PageLog,
)
from plane.db.models.api import APIToken
from plane.sharing.models import AccessLevel, ItemRestriction, ItemShare, ShareTarget
from plane.sharing.tests.conftest import make_issue, make_page, restrict

MARK = b"TOPSECRET"


def api_client(cast, user):
    token = APIToken.objects.create(user=user, workspace=cast.workspace)
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


def v1(cast, path):
    return f"/api/v1/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/{path}"


def app(cast, path):
    return f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/{path}"


def ids(rows):
    return {str(row["id"]) for row in rows}


@pytest.fixture
def api(cast):
    return {name: api_client(cast, getattr(cast, name)) for name in ("author", "insider", "friend", "owner")}


# --- Public API v1 -------------------------------------------------------------------------------


@pytest.mark.django_db
class TestApiV1Issues:
    def test_list_and_total(self, cast, api, secret_issue, open_issue):
        hidden = api["insider"].get(v1(cast, "issues/"))
        assert hidden.status_code == 200, hidden.content
        assert MARK not in hidden.content
        assert ids(hidden.data["results"]) == {str(open_issue.id)}
        assert hidden.data["total_count"] == 1
        shown = api["author"].get(v1(cast, "issues/"))
        assert str(secret_issue.id) in ids(shown.data["results"])
        assert shown.data["total_count"] == 2

    def test_workspace_identifier_lookup(self, cast, api, secret_issue):
        url = f"/api/v1/workspaces/{cast.workspace.slug}/issues/ALP-{secret_issue.sequence_id}/"
        assert api["insider"].get(url).status_code == 404
        assert api["friend"].get(url).status_code == 200

    def test_external_id_lookup(self, cast, api, secret_issue):
        Issue.objects.filter(pk=secret_issue.pk).update(external_id="ext-1", external_source="jira")
        url = v1(cast, "issues/?external_id=ext-1&external_source=jira")
        response = api["insider"].get(url)
        assert response.status_code == 404 and MARK not in response.content
        assert MARK in api["author"].get(url).content

    def test_external_id_conflict_hides_id(self, cast, api, secret_issue):
        Issue.objects.filter(pk=secret_issue.pk).update(external_id="ext-2", external_source="jira")
        body = {"name": "dup", "external_id": "ext-2", "external_source": "jira"}
        response = api["insider"].post(v1(cast, "issues/"), body, format="json")
        assert response.status_code == 409
        assert str(secret_issue.id) not in response.content.decode()
        assert str(secret_issue.id) in api["author"].post(v1(cast, "issues/"), body, format="json").content.decode()

    def test_search(self, cast, api, secret_issue):
        url = f"/api/v1/workspaces/{cast.workspace.slug}/work-items/search/?search=TOPSECRET"
        response = api["insider"].get(url)
        assert response.status_code == 200 and MARK not in response.content
        assert MARK in api["author"].get(url).content

    def test_hidden_parent(self, cast, api, secret_issue):
        child = make_issue(cast, "Open child", parent=secret_issue)
        hidden = api["insider"].get(v1(cast, f"issues/{child.id}/"))
        assert hidden.status_code == 200
        assert hidden.data["parent"] is None
        assert api["author"].get(v1(cast, f"issues/{child.id}/")).data["parent"] == secret_issue.id

    def test_relations(self, cast, api, secret_issue, open_issue):
        IssueRelation.objects.create(
            issue=open_issue,
            related_issue=secret_issue,
            relation_type="relates_to",
            project=cast.alpha,
            workspace=cast.workspace,
        )
        url = v1(cast, f"work-items/{open_issue.id}/relations/")
        assert str(secret_issue.id) not in api["insider"].get(url).content.decode()
        assert str(secret_issue.id) in api["author"].get(url).content.decode()

    def test_relation_create_skips_hidden(self, cast, api, secret_issue, open_issue):
        url = v1(cast, f"work-items/{open_issue.id}/relations/")
        body = {"relation_type": "relates_to", "issues": [str(secret_issue.id)]}
        response = api["insider"].post(url, body, format="json")
        assert MARK not in response.content
        assert not IssueRelation.objects.filter(related_issue=secret_issue).exists()

    def test_activity_pointing_at_hidden(self, cast, api, secret_issue, open_issue):
        IssueActivity.objects.create(
            issue=open_issue,
            project=cast.alpha,
            workspace=cast.workspace,
            field="parent",
            verb="updated",
            new_value=f"ALP-{secret_issue.sequence_id}",
            new_identifier=secret_issue.id,
        )
        url = v1(cast, f"issues/{open_issue.id}/activities/")
        assert str(secret_issue.id) not in api["insider"].get(url).content.decode()
        assert str(secret_issue.id) in api["author"].get(url).content.decode()

    def test_project_summary_counts(self, cast, api, secret_issue, open_issue, secret_page):
        url = f"/api/v1/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/summary/?fields=issues,pages"
        hidden = api["insider"].get(url)
        assert hidden.status_code == 200, hidden.content
        shown = api["author"].get(url)
        assert hidden.data["counts"]["issues"] == shown.data["counts"]["issues"] - 1
        assert hidden.data["counts"]["pages"] == shown.data["counts"]["pages"] - 1


@pytest.mark.django_db
class TestApiV1CyclesModulesIntake:
    def test_cycle_items_and_counts(self, cast, api, secret_issue, open_issue):
        cycle = Cycle.objects.create(name="Sprint", project=cast.alpha, workspace=cast.workspace, owned_by=cast.owner)
        for issue in (secret_issue, open_issue):
            CycleIssue.objects.create(cycle=cycle, issue=issue, project=cast.alpha, workspace=cast.workspace)
        items = v1(cast, f"cycles/{cycle.id}/cycle-issues/")
        hidden = api["insider"].get(items)
        assert hidden.status_code == 200 and MARK not in hidden.content
        assert MARK in api["author"].get(items).content
        detail = v1(cast, f"cycles/{cycle.id}/")
        assert api["insider"].get(detail).data["total_issues"] == 1
        assert api["author"].get(detail).data["total_issues"] == 2

    def test_cycle_add_skips_hidden(self, cast, api, secret_issue):
        cycle = Cycle.objects.create(name="Sprint", project=cast.alpha, workspace=cast.workspace, owned_by=cast.owner)
        response = api["insider"].post(
            v1(cast, f"cycles/{cycle.id}/cycle-issues/"), {"issues": [str(secret_issue.id)]}, format="json"
        )
        assert MARK not in response.content
        assert not CycleIssue.objects.filter(issue=secret_issue).exists()

    def test_module_items_and_counts(self, cast, api, secret_issue, open_issue):
        module = Module.objects.create(name="Epic", project=cast.alpha, workspace=cast.workspace)
        for issue in (secret_issue, open_issue):
            ModuleIssue.objects.create(module=module, issue=issue, project=cast.alpha, workspace=cast.workspace)
        items = v1(cast, f"modules/{module.id}/module-issues/")
        hidden = api["insider"].get(items)
        assert hidden.status_code == 200 and MARK not in hidden.content
        assert MARK in api["author"].get(items).content
        detail = v1(cast, f"modules/{module.id}/")
        assert api["insider"].get(detail).data["total_issues"] == 1
        assert api["author"].get(detail).data["total_issues"] == 2

    def test_intake_list(self, cast, api, secret_issue):
        cast.alpha.intake_view = True
        cast.alpha.save()
        intake = Intake.objects.create(name="Intake", project=cast.alpha, workspace=cast.workspace)
        IntakeIssue.objects.create(intake=intake, issue=secret_issue, project=cast.alpha, workspace=cast.workspace)
        url = v1(cast, "intake-issues/")
        hidden = api["insider"].get(url)
        assert hidden.status_code == 200 and MARK not in hidden.content
        assert MARK in api["author"].get(url).content


# --- Public deploy boards ------------------------------------------------------------------------


@pytest.fixture
def board(cast):
    return DeployBoard.objects.create(
        workspace=cast.workspace,
        project=cast.alpha,
        entity_name="project",
        entity_identifier=cast.alpha.id,
        is_comments_enabled=True,
        is_reactions_enabled=True,
        is_votes_enabled=True,
    )


@pytest.mark.django_db
class TestPublicBoard:
    def test_list_never_shows_restricted(self, cast, board, secret_issue, open_issue):
        url = f"/api/public/anchor/{board.anchor}/issues/"
        for client in (APIClient(), cast.author_client, cast.owner_client):
            response = client.get(url)
            assert response.status_code == 200, response.content
            assert MARK not in response.content
            assert str(open_issue.id) in response.content.decode()

    def test_retrieve_and_comments_are_404(self, cast, board, secret_issue, open_issue):
        base = f"/api/public/anchor/{board.anchor}/issues/"
        for suffix in ("", "comments/", "reactions/", "votes/"):
            assert cast.author_client.get(f"{base}{secret_issue.id}/{suffix}").status_code == 404
        assert APIClient().get(f"{base}{secret_issue.id}/").status_code == 404
        assert APIClient().get(f"{base}{open_issue.id}/").status_code == 200

    def test_restricted_parent_not_named(self, cast, board, secret_issue):
        child = make_issue(cast, "Public child", parent=secret_issue)
        response = APIClient().get(f"/api/public/anchor/{board.anchor}/issues/{child.id}/")
        assert response.status_code == 200
        assert response.data["parent_id"] is None
        assert str(secret_issue.id) not in response.content.decode()


# --- Pages ---------------------------------------------------------------------------------------


@pytest.mark.django_db
class TestPages:
    def test_list(self, cast, secret_page):
        hidden = cast.insider_client.get(app(cast, "pages/"))
        assert hidden.status_code == 200 and MARK not in hidden.content
        assert MARK in cast.author_client.get(app(cast, "pages/")).content
        assert MARK in cast.friend_client.get(app(cast, "pages/")).content

    def test_summary_counts(self, cast, secret_page):
        make_page(cast, "Open page")
        url = app(cast, "pages-summary/")
        assert cast.insider_client.get(url).data["public_pages"] == 1
        assert cast.author_client.get(url).data["public_pages"] == 2

    def test_description(self, cast, secret_page):
        url = app(cast, f"pages/{secret_page.id}/description/")
        assert cast.insider_client.get(url).status_code == 404
        assert cast.friend_client.get(url).status_code == 200

    def test_versions(self, cast, secret_page):
        url = app(cast, f"pages/{secret_page.id}/versions/")
        assert cast.insider_client.get(url).status_code == 404
        assert cast.friend_client.get(url).status_code == 200

    def test_embedded_work_item_ids(self, cast, secret_issue):
        page = make_page(cast, "Open page")
        PageLog.objects.create(
            page=page,
            workspace=cast.workspace,
            entity_name="issue",
            entity_identifier=secret_issue.id,
            transaction=secret_issue.id,
        )
        url = app(cast, f"pages/{page.id}/")
        hidden = cast.insider_client.get(url)
        assert hidden.status_code == 200
        assert str(secret_issue.id) not in [str(i) for i in hidden.data["issue_ids"]]
        assert str(secret_issue.id) in [str(i) for i in cast.author_client.get(url).data["issue_ids"]]

    def test_cannot_nest_under_hidden_page(self, cast, secret_page):
        response = cast.insider_client.post(app(cast, "pages/"), {"name": "x", "parent": str(secret_page.id)})
        assert response.status_code == 400
        assert not Page.objects.filter(parent=secret_page).exists()

    def test_duplicate_keeps_restriction(self, cast):
        page = make_page(cast, "Editable secret TOPSECRET")
        restrict(cast, page=page, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.EDIT)])
        response = cast.friend_client.post(app(cast, f"pages/{page.id}/duplicate/"))
        assert response.status_code == 201, response.content
        copy = Page.objects.get(pk=response.data["id"])
        assert ItemRestriction.objects.filter(page=copy).exists()
        assert ItemShare.objects.filter(page=copy, member=cast.author, level=AccessLevel.EDIT).exists()
        assert MARK not in cast.insider_client.get(app(cast, "pages/")).content
        assert str(copy.id) in cast.author_client.get(app(cast, "pages/")).content.decode()
