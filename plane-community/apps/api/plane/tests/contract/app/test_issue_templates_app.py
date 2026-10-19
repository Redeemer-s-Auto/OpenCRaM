# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Card templates: manage, save from a card, create cards (with sub-cards) from a template."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import (
    CustomField,
    Issue,
    IssueLabel,
    IssueTemplate,
    Label,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)
from plane.utils.custom_fields import values_for_issues

BASE = "/api/workspaces/{slug}/projects/{project_id}"


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Board", identifier="TPL", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def states(db, workspace, project):
    todo = State.objects.create(name="Todo", project=project, workspace=workspace, group="unstarted", default=True)
    doing = State.objects.create(name="Doing", project=project, workspace=workspace, group="started")
    return todo, doing


@pytest.fixture
def label(db, workspace, project):
    return Label.objects.create(name="Brakes", project=project, workspace=workspace)


def _member(workspace, project, role):
    user = User.objects.create(email=f"u-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:10])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=max(role, 5))
    ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _url(workspace, project, tail=""):
    return BASE.format(slug=workspace.slug, project_id=project.id) + tail


@pytest.mark.contract
@pytest.mark.django_db
class TestIssueTemplates:
    def test_member_manages_templates_guest_cannot(self, workspace, project):
        member = _member(workspace, project, 15)
        guest = _member(workspace, project, 5)
        url = _url(workspace, project, "/work-item-templates/")
        created = member.post(url, {"name": "Comeback", "data": {"name": "Comeback: "}}, format="json")
        assert created.status_code == 201, created.data
        tid = created.data["id"]
        assert member.patch(f"{url}{tid}/", {"name": "Comeback check"}, format="json").data["name"] == "Comeback check"
        assert [t["name"] for t in member.get(url).data] == ["Comeback check"]
        assert member.post(url, {"name": "comeback CHECK"}, format="json").status_code == 400
        assert guest.get(url).status_code == 403
        assert guest.post(url, {"name": "X"}, format="json").status_code == 403
        assert member.delete(f"{url}{tid}/").status_code == 204
        assert member.get(url).data == []

    def test_use_creates_card_and_sub_cards(self, session_client, workspace, project, states, label):
        todo, doing = states
        amount = CustomField.objects.create(project=project, name="Amount", field_type="money")
        role = CustomField.objects.create(
            project=project, name="Role", field_type="select", options=[{"id": "a", "name": "A-Tech", "color": ""}]
        )
        data = {
            "name": "Comeback",
            "description_html": '<ul data-type="taskList"><li data-checked="false"><p>Road test</p></li></ul>',
            "priority": "high",
            "state_id": str(doing.id),
            "label_ids": [str(label.id)],
            "custom_fields": {str(amount.id): 0, str(role.id): "a"},
            "sub_items": [
                {"name": "Inspect", "custom_fields": {str(role.id): "a"}, "sub_items": [{"name": "Photos"}]},
                {"name": "Call client"},
            ],
        }
        url = _url(workspace, project, "/work-item-templates/")
        tid = session_client.post(url, {"name": "Comeback", "data": data}, format="json").data["id"]

        used = session_client.post(f"{url}{tid}/use/", {"name": "Comeback - 10432"}, format="json")
        assert used.status_code == 201, used.data
        assert used.data["created_count"] == 4
        top = Issue.objects.get(pk=used.data["id"])
        assert top.name == "Comeback - 10432"
        assert top.priority == "high" and top.state_id == doing.id
        assert "Road test" in top.description_html
        assert list(IssueLabel.objects.filter(issue=top).values_list("label_id", flat=True)) == [label.id]
        assert values_for_issues([top.id])[str(top.id)] == {str(amount.id): 0, str(role.id): "a"}

        children = list(Issue.objects.filter(parent=top).order_by("sequence_id"))
        assert [c.name for c in children] == ["Inspect", "Call client"]
        assert values_for_issues([children[0].id])[str(children[0].id)] == {str(role.id): "a"}
        grand = Issue.objects.get(parent=children[0])
        assert grand.name == "Photos"

        # Without a name, the template's own title is used.
        again = session_client.post(f"{url}{tid}/use/", {}, format="json")
        assert Issue.objects.get(pk=again.data["id"]).name == "Comeback"

    def test_use_skips_things_that_no_longer_exist(self, session_client, workspace, project, states, label):
        todo, doing = states
        gone_field = CustomField.objects.create(project=project, name="Gone", field_type="text")
        role = CustomField.objects.create(
            project=project, name="Role", field_type="select", options=[{"id": "a", "name": "A", "color": ""}]
        )
        url = _url(workspace, project, "/work-item-templates/")
        tid = session_client.post(
            url,
            {
                "name": "T",
                "data": {
                    "name": "Card",
                    "state_id": str(doing.id),
                    "label_ids": [str(label.id)],
                    "custom_fields": {str(gone_field.id): "x", str(role.id): "a"},
                },
            },
            format="json",
        ).data["id"]
        # The board changes after the template was saved.
        CustomField.all_objects.filter(pk=gone_field.id).delete()
        role.options = [{"id": "b", "name": "B", "color": ""}]
        role.save()
        doing.delete()
        label.delete()

        used = session_client.post(f"{url}{tid}/use/", {}, format="json")
        assert used.status_code == 201, used.data
        card = Issue.objects.get(pk=used.data["id"])
        assert card.state_id != doing.id
        assert values_for_issues([card.id]).get(str(card.id), {}) == {}

    def test_save_as_template_from_card(self, session_client, workspace, project, states, label):
        todo, _ = states
        f = CustomField.objects.create(project=project, name="RO", field_type="text")
        create = session_client.post(
            _url(workspace, project, "/issues/"),
            {
                "name": "Brake job",
                "description_html": "<p>Steps</p>",
                "label_ids": [str(label.id)],
                "custom_fields": {str(f.id): "10432"},
            },
            format="json",
        )
        parent_id = create.data["id"]
        session_client.post(
            _url(workspace, project, "/issues/"), {"name": "Sub", "parent_id": parent_id}, format="json"
        )

        save_url = _url(workspace, project, f"/issues/{parent_id}/save-as-template/")
        saved = session_client.post(save_url, {"name": "Brake template", "include_sub_items": True}, format="json")
        assert saved.status_code == 201, saved.data
        data = saved.data["data"]
        assert data["name"] == "Brake job" and "Steps" in data["description_html"]
        assert data["label_ids"] == [str(label.id)]
        assert data["custom_fields"] == {str(f.id): "10432"}
        assert [s["name"] for s in data["sub_items"]] == ["Sub"]

        without = session_client.post(save_url, {"include_sub_items": False}, format="json")
        assert without.status_code == 201
        assert without.data["name"] == "Brake job"  # defaults to the card title
        assert without.data["data"]["sub_items"] == []
        third = session_client.post(save_url, {"include_sub_items": False}, format="json")
        assert third.data["name"] == "Brake job (2)"

    def test_bad_template_data_refused(self, session_client, workspace, project):
        url = _url(workspace, project, "/work-item-templates/")
        too_deep = {
            "name": "a",
            "sub_items": [{"name": "b", "sub_items": [{"name": "c", "sub_items": [{"name": "d"}]}]}],
        }
        too_many = {"name": "a", "sub_items": [{"name": f"s{i}"} for i in range(60)]}
        for data in [too_deep, too_many, {"sub_items": [{"name": ""}]}, "nope"]:
            response = session_client.post(url, {"name": f"T{uuid4().hex[:4]}", "data": data}, format="json")
            assert response.status_code == 400, data

    def test_templates_are_per_board(self, session_client, workspace, project, create_user):
        other = Project.objects.create(name="Other", identifier="OTH", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=other, member=create_user, workspace=workspace, role=20)
        tid = session_client.post(
            _url(workspace, project, "/work-item-templates/"), {"name": "Only here"}, format="json"
        ).data["id"]
        assert session_client.get(_url(workspace, other, "/work-item-templates/")).data == []
        response = session_client.post(_url(workspace, other, f"/work-item-templates/{tid}/use/"), {}, format="json")
        assert response.status_code == 404
        assert IssueTemplate.objects.count() == 1


@pytest.mark.contract
@pytest.mark.django_db
def test_templates_never_copy_linked_card_fields(session_client, workspace, project):
    """Relation and rollup fields point at specific cards; a template must not copy them."""
    relation = CustomField.objects.create(project=project, name="Linked", field_type="relation")
    rollup = CustomField.objects.create(project=project, name="Total", field_type="rollup")
    text = CustomField.objects.create(project=project, name="Note", field_type="text")
    response = session_client.post(
        _url(workspace, project, "/work-item-templates/"),
        {
            "name": "T",
            "data": {
                "name": "Card",
                "custom_fields": {str(relation.id): [str(uuid4())], str(rollup.id): 5, str(text.id): "keep"},
            },
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["data"]["custom_fields"] == {str(text.id): "keep"}
