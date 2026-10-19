# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Gallery covers: list responses carry each card's cover image path."""

import pytest

from plane.db.models import FileAsset, Issue, Project, ProjectMember, State

ISSUES_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/"


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Board", identifier="GAL", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    State.objects.create(name="Todo", project=project, workspace=workspace, group="backlog", default=True)
    return project


def _issue(project, name):
    issue = Issue(name=name, project=project, workspace=project.workspace)
    issue.save()
    return issue


def _asset(issue, kind, mime="image/png", uploaded=True):
    return FileAsset.objects.create(
        asset=f"{issue.id}/{kind}.bin",
        attributes={"name": f"{kind}.bin", "type": mime, "size": 10},
        entity_type=kind,
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        is_uploaded=uploaded,
    )


@pytest.mark.contract
@pytest.mark.django_db
class TestGalleryCovers:
    def test_cover_rules(self, session_client, workspace, project):
        both = _issue(project, "both")
        attach = _asset(both, FileAsset.EntityTypeContext.ISSUE_ATTACHMENT)
        body = _asset(both, FileAsset.EntityTypeContext.ISSUE_DESCRIPTION)

        only_attachment = _issue(project, "attachment")
        a2 = _asset(only_attachment, FileAsset.EntityTypeContext.ISSUE_ATTACHMENT)

        pdf_only = _issue(project, "pdf")
        _asset(pdf_only, FileAsset.EntityTypeContext.ISSUE_ATTACHMENT, mime="application/pdf")

        not_uploaded = _issue(project, "pending")
        _asset(not_uploaded, FileAsset.EntityTypeContext.ISSUE_DESCRIPTION, uploaded=False)

        _issue(project, "none")

        response = session_client.get(ISSUES_URL.format(slug=workspace.slug, project_id=project.id))
        assert response.status_code == 200
        rows = {r["name"]: r for r in response.data["results"]}
        # Body images win over attachments.
        assert rows["both"]["cover_image"] == f"/api/assets/v2/workspaces/{workspace.slug}/projects/{project.id}/{body.id}/"
        assert str(attach.id) not in rows["both"]["cover_image"]
        assert rows["attachment"]["cover_image"].endswith(f"/attachments/{a2.id}/")
        assert rows["pdf"]["cover_image"] is None
        assert rows["pending"]["cover_image"] is None
        assert rows["none"]["cover_image"] is None
