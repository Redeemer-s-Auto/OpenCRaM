# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""One-unit fixtures: the sharing cast plus a person in both projects and nested cards.

Tree used by most tests (Alpha = ALP, Beta = BET)::

    ALP root            (open)
      ALP child         (open)
        BET grandchild  (open, lives in Beta: a cross-project child)
    ALP secret          (restricted, shared with friend only)
      ALP under secret  (open)
"""

import pytest

from plane.db.models import Issue, ProjectMember, State, WorkspaceMember
from plane.sharing.models import AccessLevel, ShareTarget
from plane.sharing.tests.conftest import cast, client_for, eager_celery, make_user, restrict  # noqa: F401


def card(cast, name, project=None, parent=None, author=None):
    project = project or cast.alpha
    state = cast.state if project == cast.alpha else cast.beta_state
    issue = Issue(name=name, project=project, workspace=cast.workspace, state=state, parent=parent)
    issue.save(created_by_id=(author or cast.author).id)
    return issue


@pytest.fixture
def world(cast):
    cast.beta_state = State.objects.create(
        name="Todo", project=cast.beta, workspace=cast.workspace, group="unstarted", default=True
    )
    both = make_user("both")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=both, role=15)
    for project in (cast.alpha, cast.beta):
        ProjectMember.objects.create(project=project, member=both, workspace=cast.workspace, role=15)
    cast.both, cast.both_client = both, client_for(both)

    cast.root = card(cast, "ALP root")
    cast.child = card(cast, "ALP child", parent=cast.root)
    cast.grandchild = card(cast, "BET grandchild", project=cast.beta, parent=cast.child, author=both)
    cast.secret = card(cast, "ALP secret TOPSECRET")
    restrict(cast, issue=cast.secret, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
    cast.under_secret = card(cast, "ALP under secret", parent=cast.secret)
    return cast
