# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Card shortcut fixtures, on top of the sharing cast.

Boards: Alpha (ALP), Beta (BET), and Gamma (GAM, a private board only ``owner`` is on).
People (from the sharing cast, plus ``both``):
- ``owner``: workspace owner/admin, on Alpha, Beta and Gamma.
- ``author``, ``insider``, ``friend``: Alpha only.
- ``outsider``: Beta only.
- ``both``: member of Alpha and Beta.

Cards made by ``links``:
- ``beta_open``: an open Beta card.
- ``beta_secret``: a restricted Beta card nobody is shared on (owner sees it as admin).
- ``gamma_card``: a card on the private board.
- ``source``: an Alpha card whose body links to all three.
"""

import pytest

from plane.db.models import Issue, Project, ProjectMember, State, WorkspaceMember
from plane.sharing.tests.conftest import cast, client_for, eager_celery, make_user, restrict  # noqa: F401

SECRET = "TOPSECRET"
ISSUE_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/"


@pytest.fixture(autouse=True)
def _reset_throttle():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def block(card_id):
    return f'<card-link-component data-card-id="{card_id}"></card-link-component>'


def body(*card_ids):
    return "<p>See:</p>" + "".join(block(i) for i in card_ids)


def card(cast, name, project=None, author=None, **fields):
    project = project or cast.alpha
    state = State.objects.filter(project=project, default=True).first()
    issue = Issue(name=name, project=project, workspace=cast.workspace, state=state, **fields)
    issue.save(created_by_id=(author or cast.owner).id)
    return issue


def url(cast, path):
    return f"/api/workspaces/{cast.workspace.slug}/{path}"


def resolve(cast, client, ids):
    response = client.post(url(cast, "card-links/resolve/"), {"ids": [str(i) for i in ids]}, format="json")
    assert response.status_code == 200, response.content
    return response


def add_shortcut(cast, client, project, target, expect=201, **extra):
    response = client.post(
        url(cast, f"projects/{project.id}/shortcuts/"), {"target_id": str(target), **extra}, format="json"
    )
    assert response.status_code == expect, response.content
    return response


@pytest.fixture
def links(cast):
    State.objects.create(name="Todo", project=cast.beta, workspace=cast.workspace, group="unstarted", default=True)
    gamma = Project.objects.create(
        name="Gamma", identifier="GAM", workspace=cast.workspace, created_by=cast.owner, is_private=True
    )
    ProjectMember.objects.create(project=gamma, member=cast.owner, workspace=cast.workspace, role=20)
    State.objects.create(name="Todo", project=gamma, workspace=cast.workspace, group="unstarted", default=True)
    both = make_user("both")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=both, role=15)
    for project in (cast.alpha, cast.beta):
        ProjectMember.objects.create(project=project, member=both, workspace=cast.workspace, role=15)
    cast.gamma, cast.both, cast.both_client = gamma, both, client_for(both)

    cast.beta_open = card(cast, "Beta open target", project=cast.beta)
    cast.beta_secret = card(cast, f"Beta secret {SECRET}", project=cast.beta)
    restrict(cast, issue=cast.beta_secret)
    cast.gamma_card = card(cast, f"Gamma private {SECRET}", project=gamma)
    cast.source = card(
        cast,
        "Alpha source",
        description_html=body(cast.beta_open.id, cast.beta_secret.id, cast.gamma_card.id),
    )
    return cast
