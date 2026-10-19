# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared fixtures for sharing-rule tests.

Cast: one workspace, two projects ("Alpha" and "Beta").
- ``owner``: workspace owner + admin (always sees everything).
- ``author``: Alpha member who creates the restricted items.
- ``insider``: Alpha member NOT on the share list (must see nothing).
- ``friend``: Alpha member named on the share list.
- ``outsider``: Beta member only.
"""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import Issue, Page, Project, ProjectMember, ProjectPage, State, User, Workspace, WorkspaceMember
from plane.sharing.models import AccessLevel, ItemRestriction, ItemShare, ShareTarget


@pytest.fixture(autouse=True)
def eager_celery():
    """Run background jobs inline so activity, notification and webhook paths run in tests."""
    from plane.celery import app

    previous = app.conf.task_always_eager, app.conf.task_eager_propagates
    app.conf.task_always_eager, app.conf.task_eager_propagates = True, True
    yield
    app.conf.task_always_eager, app.conf.task_eager_propagates = previous


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


@pytest.fixture
def cast(db):
    owner = make_user("owner")
    workspace = Workspace.objects.create(name="Share Test", owner=owner, slug=f"share-{uuid4().hex[:6]}")
    WorkspaceMember.objects.create(workspace=workspace, member=owner, role=20)

    alpha = Project.objects.create(name="Alpha", identifier="ALP", workspace=workspace, created_by=owner)
    beta = Project.objects.create(name="Beta", identifier="BET", workspace=workspace, created_by=owner)
    for project in (alpha, beta):
        ProjectMember.objects.create(project=project, member=owner, workspace=workspace, role=20)

    people = {"owner": owner}
    for label, project in (("author", alpha), ("insider", alpha), ("friend", alpha), ("outsider", beta)):
        user = make_user(label)
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
        ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=15)
        people[label] = user

    state = State.objects.create(name="Todo", project=alpha, workspace=workspace, group="unstarted", default=True)

    class Cast:
        pass

    c = Cast()
    c.workspace, c.alpha, c.beta, c.state = workspace, alpha, beta, state
    for label, user in people.items():
        setattr(c, label, user)
        setattr(c, f"{label}_client", client_for(user))
    return c


def make_issue(cast, name, author=None, **fields):
    issue = Issue(name=name, project=cast.alpha, workspace=cast.workspace, state=cast.state, **fields)
    issue.save(created_by_id=(author or cast.author).id)
    return issue


def make_page(cast, name, author=None):
    author = author or cast.author
    page = Page(name=name, workspace=cast.workspace, owned_by=author)
    page.save(created_by_id=author.id)
    ProjectPage.objects.create(project=cast.alpha, page=page, workspace=cast.workspace)
    return page


def restrict(cast, issue=None, page=None, shares=()):
    """Restrict an item. ``shares`` = iterable of (target_type, target, level)."""
    ItemRestriction.objects.create(workspace=cast.workspace, issue=issue, page=page)
    for target_type, target, level in shares:
        fields = {
            ShareTarget.MEMBER: {"member": target},
            ShareTarget.PROJECT: {"project": target},
            ShareTarget.GROUP: {"group": target},
            ShareTarget.WORKSPACE: {},
        }[target_type]
        ItemShare.objects.create(
            workspace=cast.workspace, issue=issue, page=page, target_type=target_type, level=level, **fields
        )


@pytest.fixture
def secret_issue(cast):
    """Restricted work item shared with ``friend`` only (Can view)."""
    issue = make_issue(cast, "Secret work item TOPSECRET")
    restrict(cast, issue=issue, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
    return issue


@pytest.fixture
def open_issue(cast):
    return make_issue(cast, "Open work item")


@pytest.fixture
def secret_page(cast):
    page = make_page(cast, "Secret page TOPSECRET")
    restrict(cast, page=page, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
    return page
