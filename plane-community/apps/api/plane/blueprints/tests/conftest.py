# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Blueprint tests reuse the sharing-rule cast and add a fully designed board.

Cast (from plane.sharing.tests.conftest): workspace owner (admin), Alpha and Beta
boards; author / insider / friend on Alpha, outsider on Beta. Here ``author`` is
made an admin of Alpha so it can save blueprints.
"""

import datetime as dt
from uuid import uuid4

import pytest

from plane.db.models import (
    IssueLabel,
    IssueTemplate,
    IssueView,
    Label,
    ProjectMember,
    ProjectUserProperty,
    State,
    Workspace,
    WorkspaceMember,
)
from plane.sharing.tests.conftest import (  # noqa: F401  (fixtures and helpers)
    cast,
    client_for,
    eager_celery,
    make_issue,
    make_user,
    restrict,
)

BP_URL = "/api/workspaces/{slug}/blueprints/"
FIELDS_URL = "/api/workspaces/{slug}/projects/{project_id}/custom-fields/"


@pytest.fixture(autouse=True)
def _reset_throttle():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def bp_url(cast, suffix=""):
    return BP_URL.format(slug=cast.workspace.slug) + suffix


def add_field(cast, project, client=None, **data):
    client = client or cast.owner_client
    response = client.post(FIELDS_URL.format(slug=cast.workspace.slug, project_id=project.id), data, format="json")
    assert response.status_code == 201, getattr(response, "data", None)
    return response.data


class Board:
    """Ids of everything on the designed board, for the checks."""


@pytest.fixture
def board(cast):
    """Alpha with a full design: states, labels, every kind of field, a view, a layout, a template, cards."""
    alpha = cast.alpha
    ProjectMember.objects.filter(project=alpha, member=cast.author).update(role=20)
    # The author also works on Beta, so a relation from Alpha to Beta can be remade by them.
    ProjectMember.objects.create(project=cast.beta, member=cast.author, workspace=cast.workspace, role=15)
    alpha.cycle_view = True
    alpha.module_view = False
    alpha.description = "Board for tracking call-backs"
    alpha.logo_props = {"in_use": "emoji", "emoji": {"value": "128203"}}
    alpha.save()

    b = Board()
    b.todo = cast.state
    b.waiting = State.objects.create(name="Waiting", project=alpha, workspace=cast.workspace, group="started", color="#F59E0B")
    b.done = State.objects.create(name="Done", project=alpha, workspace=cast.workspace, group="completed", color="#46A758")
    b.parent_label = Label.objects.create(name="Area", project=alpha, workspace=cast.workspace, color="#111111")
    b.child_label = Label.objects.create(
        name="Front", project=alpha, workspace=cast.workspace, color="#222222", parent=b.parent_label
    )

    b.text = add_field(cast, alpha, name="Reference", field_type="text")
    b.amount = add_field(cast, alpha, name="Amount", field_type="money")
    b.hours = add_field(cast, alpha, name="Hours", field_type="number", settings={"decimals": 1})
    b.kind = add_field(
        cast,
        alpha,
        name="Kind",
        field_type="select",
        options=[{"name": "Call", "color": "#ff0000"}, {"name": "Visit", "color": "#00ff00"}],
    )
    b.owner = add_field(cast, alpha, name="Owner", field_type="person")
    b.total = add_field(
        cast,
        alpha,
        name="Total",
        field_type="formula",
        settings={"expression": 'prop("Amount") + prop("Hours") * 165', "result_type": "money"},
    )
    b.related = add_field(
        cast,
        alpha,
        name="Related",
        field_type="relation",
        settings={"target_project_id": str(alpha.id), "two_way": True, "mirror_name": "Related from"},
    )
    b.beta_link = add_field(
        cast, alpha, name="Beta cards", field_type="relation", settings={"target_project_id": str(cast.beta.id)}
    )
    b.related_hours = add_field(
        cast,
        alpha,
        name="Related hours",
        field_type="rollup",
        settings={"relation_field_id": b.related["id"], "target_field_id": b.hours["id"], "function": "sum"},
    )
    b.related_count = add_field(
        cast,
        alpha,
        name="Related count",
        field_type="rollup",
        settings={"relation_field_id": b.related["id"], "function": "count"},
    )
    b.kind_call = b.kind["options"][0]["id"]

    b.view = IssueView.objects.create(
        workspace=cast.workspace,
        project=alpha,
        name="Waiting calls",
        filters={"state": [str(b.waiting.id)], "labels": [str(b.child_label.id)], "assignees": [str(cast.friend.id)]},
        query={},
        display_filters={"layout": "kanban", "group_by": "state", "order_by": f"custom_field__{b.amount['id']}"},
        display_properties={f"customfield_{b.amount['id']}": True, f"cardfield_{b.kind['id']}": True, "priority": True},
        rich_filters={"and": [{f"customfield_{b.kind['id']}__in": b.kind_call}]},
        owned_by=cast.author,
        access=1,
    )
    prop, _ = ProjectUserProperty.objects.get_or_create(user=cast.author, project=alpha, workspace=cast.workspace)
    prop.display_filters = {"layout": "gallery", "order_by": "-created_at"}
    prop.display_properties = {f"customfield_{b.total['id']}": True, "state": True}
    prop.save()

    from plane.utils.issue_templates import clean_template_data

    b.template = IssueTemplate.objects.create(
        project=alpha,
        workspace=cast.workspace,
        name="New call-back",
        data=clean_template_data(
            alpha.id,
            {
                "name": "Call back",
                "description_html": "<p>Ask how it went</p>",
                "priority": "high",
                "state_id": str(b.waiting.id),
                "label_ids": [str(b.child_label.id)],
                "custom_fields": {b.kind["id"]: b.kind_call, b.hours["id"]: 2},
                "sub_items": [{"name": "Log the answer"}],
            },
        ),
    )

    b.card = make_issue(
        cast,
        "Sample card",
        description_html=(
            '<p>Phone the client</p><mention-component entity_identifier="'
            + str(cast.friend.id)
            + '" entity_name="user_mention"></mention-component><p>mail person@example.org</p>'
        ),
    )
    IssueLabel.objects.create(issue=b.card, label=b.parent_label, project=alpha, workspace=cast.workspace)
    b.hidden_card = make_issue(cast, "Hidden card SECRETNAME")
    from plane.sharing.models import AccessLevel, ShareTarget

    restrict(cast, issue=b.hidden_card, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
    from plane.recurrence.models import RepeatRule

    RepeatRule.objects.create(
        workspace=cast.workspace,
        project=alpha,
        issue=b.card,
        frequency="weekly",
        weekdays=[0, 3],
        time_of_day=dt.time(7, 30),
        timezone="America/Chicago",
        start_date=dt.date(2026, 10, 1),
        created_by=cast.author,
    )
    return b


@pytest.fixture
def second_workspace(db):
    owner = make_user("church")
    workspace = Workspace.objects.create(name="Second", owner=owner, slug=f"second-{uuid4().hex[:6]}")
    WorkspaceMember.objects.create(workspace=workspace, member=owner, role=20)

    class W:
        pass

    w = W()
    w.workspace, w.owner, w.client = workspace, owner, client_for(owner)
    return w
