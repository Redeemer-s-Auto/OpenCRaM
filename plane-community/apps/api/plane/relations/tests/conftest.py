# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Fixtures for relation and rollup tests.

Cast: one workspace, two boards, "Alpha" (cards that link) and "Beta" (cards linked to).
- ``admin``: workspace owner, admin of both boards.
- ``member``: member of both boards (the everyday viewer in leak tests).
- ``alpha_admin``: admin of Alpha, plain member of Beta.
- ``alpha_only``: workspace ADMIN, admin of Alpha, never a member of Beta.
"""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import CustomField, Issue, Project, ProjectMember, State, User, Workspace, WorkspaceMember

FIELDS_URL = "/api/workspaces/{slug}/projects/{project_id}/custom-fields/"
ISSUE_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/"


@pytest.fixture(autouse=True)
def eager_celery():
    """Run background jobs inline so the activity task runs in tests."""
    from plane.celery import app

    previous = app.conf.task_always_eager, app.conf.task_eager_propagates
    app.conf.task_always_eager, app.conf.task_eager_propagates = True, True
    yield
    app.conf.task_always_eager, app.conf.task_eager_propagates = previous


@pytest.fixture(autouse=True)
def _reset_throttle():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def make_user(label):
    uid = uuid4().hex[:8]
    user = User.objects.create(email=f"{label}-{uid}@example.com", username=f"{label}_{uid}", first_name=label.title())
    user.set_password("test-password")
    user.save()
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class Cast:
    def field(self, project, client=None, expect=201, **data):
        client = client or self.admin_client
        response = client.post(FIELDS_URL.format(slug=self.workspace.slug, project_id=project.id), data, format="json")
        assert response.status_code == expect, getattr(response, "data", None)
        return response.data

    def card(self, project, name, author=None, **fields):
        state = self.alpha_state if project.id == self.alpha.id else self.beta_state
        issue = Issue(name=name, project=project, workspace=self.workspace, state=state, **fields)
        issue.save(created_by_id=(author or self.admin).id)
        return issue

    def values(self, issue, client=None):
        client = client or self.admin_client
        url = ISSUE_URL.format(slug=self.workspace.slug, project_id=issue.project_id, issue_id=issue.id)
        response = client.get(url)
        assert response.status_code == 200, getattr(response, "data", None)
        return response.data["custom_fields"]

    def patch(self, issue, custom_fields, client=None, expect=204):
        client = client or self.admin_client
        url = ISSUE_URL.format(slug=self.workspace.slug, project_id=issue.project_id, issue_id=issue.id)
        response = client.patch(url, {"custom_fields": custom_fields}, format="json")
        assert response.status_code == expect, getattr(response, "data", None)
        return response

    def linked_ids(self, issue, field, client=None):
        return [card["id"] for card in self.values(issue, client).get(str(field["id"]), [])]

    def relation(self, two_way=False, source=None, target=None, name="Linked", **settings):
        source = source or self.alpha
        target = target or self.beta
        return self.field(
            source,
            name=name,
            field_type="relation",
            settings={"target_project_id": str(target.id), "two_way": two_way, **settings},
        )

    def rollup(self, relation, function, target_field_id=None, name=None, expect=201):
        settings = {"relation_field_id": relation["id"], "function": function}
        if target_field_id is not None:
            settings["target_field_id"] = target_field_id
        return self.field(
            self.alpha,
            name=name or f"R {function} {uuid4().hex[:4]}",
            field_type="rollup",
            settings=settings,
            expect=expect,
        )

    def mirror_of(self, relation):
        return CustomField.objects.get(pk=CustomField.objects.get(pk=relation["id"]).settings["mirror_field_id"])


@pytest.fixture
def cast(db):
    admin = make_user("admin")
    workspace = Workspace.objects.create(name="Links", owner=admin, slug=f"links-{uuid4().hex[:6]}")
    WorkspaceMember.objects.create(workspace=workspace, member=admin, role=20)
    alpha = Project.objects.create(name="Alpha", identifier="ALP", workspace=workspace, created_by=admin)
    beta = Project.objects.create(name="Beta", identifier="BET", workspace=workspace, created_by=admin)
    for project in (alpha, beta):
        ProjectMember.objects.create(project=project, member=admin, workspace=workspace, role=20)

    c = Cast()
    c.workspace, c.alpha, c.beta, c.admin = workspace, alpha, beta, admin
    c.alpha_state = State.objects.create(
        name="Todo", project=alpha, workspace=workspace, group="unstarted", default=True
    )
    c.beta_state = State.objects.create(name="Todo", project=beta, workspace=workspace, group="unstarted", default=True)

    roles = {
        "member": ((alpha, 15), (beta, 15), 15),
        "alpha_admin": ((alpha, 20), (beta, 15), 15),
        "alpha_only": ((alpha, 20), 20),
    }
    for label, spec in roles.items():
        *memberships, workspace_role = spec
        user = make_user(label)
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=workspace_role)
        for project, role in memberships:
            ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=role)
        setattr(c, label, user)
    for label in ("admin", "member", "alpha_admin", "alpha_only"):
        setattr(c, f"{label}_client", client_for(getattr(c, label)))
    return c
