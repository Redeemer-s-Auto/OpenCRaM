# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for custom fields in the public API (/api/v1/) and webhooks."""

import json
from uuid import uuid4

import pytest
from rest_framework import status

from plane.api.serializers import IssueSerializer
from plane.bgtasks.issue_activities_task import update_issue_activity
from plane.db.models import CustomField, Issue, Project, ProjectMember, State, User, WorkspaceMember
from plane.utils.custom_fields import display_value, set_values, validate_values


@pytest.fixture(autouse=True)
def _reset_api_key_throttle():
    """These tests make many calls with the shared test API key. Reset the
    rate-limit counter so they do not push later test files over the limit."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Board", identifier="BRD", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20, is_active=True)
    return project


@pytest.fixture
def state(db, workspace, project):
    return State.objects.create(name="Todo", project=project, workspace=workspace, group="backlog", default=True)


def base(workspace, project):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}"


def _id(data):
    return str(data["id"])


@pytest.mark.contract
@pytest.mark.django_db
class TestCustomFieldsPublicAPI:
    def test_field_crud_with_api_key(self, api_key_client, workspace, project):
        url = f"{base(workspace, project)}/custom-fields/"
        response = api_key_client.post(url, {"name": "RO number", "field_type": "text"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        field_id = _id(response.data)

        assert [f["name"] for f in api_key_client.get(url).data] == ["RO number"]

        detail = f"{url}{field_id}/"
        assert api_key_client.patch(detail, {"name": "RO #"}, format="json").data["name"] == "RO #"
        assert api_key_client.post(f"{detail}archive/").data["archived_at"] is not None
        assert api_key_client.delete(f"{detail}archive/").data["archived_at"] is None
        assert api_key_client.delete(detail, {}, format="json").status_code == 400
        assert api_key_client.delete(detail, {"confirm_name": "RO #"}, format="json").status_code == 204

    def test_work_item_values_round_trip(self, api_key_client, workspace, project, state):
        fields_url = f"{base(workspace, project)}/custom-fields/"
        ro = _id(api_key_client.post(fields_url, {"name": "RO", "field_type": "text"}, format="json").data)
        amount = _id(api_key_client.post(fields_url, {"name": "Amount", "field_type": "money"}, format="json").data)

        issues_url = f"{base(workspace, project)}/issues/"
        response = api_key_client.post(
            issues_url,
            {"name": "Brake job", "state": str(state.id), "custom_fields": {ro: "10432", amount: 121400}},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        issue_id = _id(response.data)
        assert response.data["custom_fields"] == {ro: "10432", amount: 121400}

        detail = f"{issues_url}{issue_id}/"
        assert api_key_client.get(detail).data["custom_fields"] == {ro: "10432", amount: 121400}

        response = api_key_client.patch(detail, {"custom_fields": {amount: 99900}}, format="json")
        assert response.status_code == 200, response.data
        assert api_key_client.get(detail).data["custom_fields"][amount] == 99900

        bad = api_key_client.patch(detail, {"custom_fields": {amount: "lots"}}, format="json")
        assert bad.status_code == 400

        # Look a card up by its RO number.
        other = api_key_client.post(issues_url, {"name": "Other", "custom_fields": {ro: "20001"}}, format="json")
        assert other.status_code == 201
        found = api_key_client.get(
            issues_url, {"custom_field_filters": json.dumps({f"customfield_{ro}__exact": "10432"})}
        )
        assert found.status_code == 200, found.data
        assert [r["name"] for r in found.data["results"]] == ["Brake job"]

        ordered = api_key_client.get(issues_url, {"order_by": f"-custom_field__{amount}"})
        assert [r["name"] for r in ordered.data["results"]] == ["Brake job", "Other"]

        bad_filter = api_key_client.get(issues_url, {"custom_field_filters": "{not json"})
        assert bad_filter.status_code == 400

    def test_hub_card_flow(self, api_key_client, workspace, project, state):
        """The hub's only door: create a card with a page body, fields and an outside id,
        find it again by that id or by its identifier, update it, and read it back."""
        fields_url = f"{base(workspace, project)}/custom-fields/"
        ro = _id(api_key_client.post(fields_url, {"name": "RO", "field_type": "text"}, format="json").data)
        when = _id(
            api_key_client.post(
                fields_url,
                {"name": "Call-back", "field_type": "date", "settings": {"include_time": True}},
                format="json",
            ).data
        )
        issues_url = f"{base(workspace, project)}/issues/"
        created = api_key_client.post(
            issues_url,
            {
                "name": "Call client back",
                "state": str(state.id),
                "description_html": "<p>Asked about the brake quote.</p>",
                "external_source": "crm",
                "external_id": "lead-42",
                "custom_fields": {ro: "10432", when: "2026-10-22T14:30:00-05:00"},
            },
            format="json",
        )
        assert created.status_code == 201, created.data
        assert created.data["custom_fields"] == {ro: "10432", when: "2026-10-22T19:30:00Z"}
        assert "brake quote" in created.data["description_html"]

        # Find it by the outside id.
        found = api_key_client.get(issues_url, {"external_source": "crm", "external_id": "lead-42"})
        assert found.status_code == 200
        assert found.data["custom_fields"][ro] == "10432"

        # Find it by its identifier (BRD-<n>).
        by_identifier = api_key_client.get(
            f"/api/v1/workspaces/{workspace.slug}/issues/BRD-{created.data['sequence_id']}/"
        )
        assert by_identifier.status_code == 200, by_identifier.data
        assert by_identifier.data["custom_fields"][ro] == "10432"

        # Update the body and one field together; the other field stays.
        detail = f"{issues_url}{_id(created.data)}/"
        updated = api_key_client.patch(
            detail,
            {"description_html": "<p>Called back, booked Thursday.</p>", "custom_fields": {ro: "10433"}},
            format="json",
        )
        assert updated.status_code == 200, updated.data
        after = api_key_client.get(detail).data
        assert after["custom_fields"] == {ro: "10433", when: "2026-10-22T19:30:00Z"}
        assert "booked Thursday" in after["description_html"]

        # ?fields= keeps or drops custom_fields like any other field.
        slim = api_key_client.get(issues_url, {"fields": "id,name,custom_fields"})
        assert slim.data["results"][0]["custom_fields"][ro] == "10433"
        slimmer = api_key_client.get(issues_url, {"fields": "id,name"})
        assert "custom_fields" not in slimmer.data["results"][0]

    def test_field_of_other_project_ignored_in_filters(self, api_key_client, workspace, project, create_user):
        other = Project.objects.create(name="Other", identifier="OTH", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=other, member=create_user, workspace=workspace, role=20, is_active=True)
        foreign = _id(
            api_key_client.post(
                f"{base(workspace, other)}/custom-fields/", {"name": "X", "field_type": "text"}, format="json"
            ).data
        )
        response = api_key_client.get(
            f"{base(workspace, project)}/issues/",
            {"custom_field_filters": json.dumps({f"customfield_{foreign}__exact": "x"})},
        )
        assert response.status_code == 400


@pytest.mark.contract
@pytest.mark.django_db
class TestWebhookAndActivity:
    def _field(self, project, **kw):
        return CustomField.objects.create(project=project, **kw)

    def test_webhook_payload_has_custom_fields(self, workspace, project, state, create_user):
        """Webhooks serialize work items with plane.api IssueSerializer."""
        field = self._field(project, name="Amount", field_type="money")
        issue = Issue.objects.create(name="Card", project=project, workspace=workspace, state=state)
        set_values(issue, validate_values(project.id, {str(field.id): 5000}))
        data = IssueSerializer(issue, context={"expand": ["labels", "assignees"]}).data
        assert data["custom_fields"] == {str(field.id): 5000}

    def test_activity_records_field_change(self, workspace, project, state, create_user):
        field = self._field(project, name="Amount", field_type="money")
        issue = Issue.objects.create(name="Card", project=project, workspace=workspace, state=state)
        set_values(issue, validate_values(project.id, {str(field.id): 5000}))
        before = json.dumps({"custom_fields": {str(field.id): 5000}})
        set_values(issue, validate_values(project.id, {str(field.id): 121400}))

        activities = []
        update_issue_activity(
            requested_data=json.dumps({"custom_fields": {str(field.id): 121400}}),
            current_instance=before,
            issue_id=str(issue.id),
            project_id=str(project.id),
            workspace_id=str(workspace.id),
            actor_id=str(create_user.id),
            issue_activities=activities,
            epoch=0,
        )
        assert len(activities) == 1
        assert activities[0].field == "custom_field"
        assert activities[0].old_value == "$50.00"
        assert activities[0].new_value == "$1,214.00"
        assert activities[0].comment == "updated Amount to"


@pytest.mark.unit
@pytest.mark.django_db
class TestDisplayValue:
    def test_display_values(self, workspace, project, create_user):
        money = CustomField.objects.create(project=project, name="M", field_type="money")
        assert display_value(money, 121400) == "$1,214.00"
        assert display_value(money, -5) == "-$0.05"
        assert display_value(money, None) == ""
        check = CustomField.objects.create(project=project, name="C", field_type="checkbox")
        assert display_value(check, True) == "Yes"
        sel = CustomField.objects.create(
            project=project, name="S", field_type="select", options=[{"id": "a", "name": "A-Tech", "color": ""}]
        )
        assert display_value(sel, "a") == "A-Tech"
        user = User.objects.create(
            email=f"p-{uuid4().hex[:6]}@example.com", username=uuid4().hex[:8], display_name="pat"
        )
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
        person = CustomField.objects.create(project=project, name="P", field_type="person")
        assert display_value(person, [str(user.id)]) == "pat"
