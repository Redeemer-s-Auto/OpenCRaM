# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for custom fields in the app API.

Covers: field create / edit / reorder / archive / delete, saving and reading
values on work items, per-type validation, filters and sort, and the rule that
values follow the visibility of their work item.
"""

import json
from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    CustomField,
    CustomFieldValue,
    Issue,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
)

FIELDS_URL = "/api/workspaces/{slug}/projects/{project_id}/custom-fields/"
FIELD_URL = FIELDS_URL + "{pk}/"
ISSUES_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/"
ISSUE_URL = ISSUES_URL + "{pk}/"


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Board", identifier="BRD", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def state(db, workspace, project):
    return State.objects.create(name="Todo", project=project, workspace=workspace, group="backlog", default=True)


def _user(workspace, project, role, prefix):
    unique_id = uuid4().hex[:8]
    user = User.objects.create(
        email=f"{prefix}-{unique_id}@example.com",
        username=f"{prefix}_{unique_id}",
        first_name=prefix.title(),
        last_name="User",
        display_name=f"{prefix}{unique_id}",
    )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=role)
    return user


@pytest.fixture
def member(db, workspace, project):
    return _user(workspace, project, 15, "member")


@pytest.fixture
def guest(db, workspace, project):
    return _user(workspace, project, 5, "guest")


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_issue(name, project, state, author):
    issue = Issue(name=name, project=project, workspace=project.workspace, state=state)
    issue.save(created_by_id=author.id)
    return issue


def _create_field(client, workspace, project, **data):
    response = client.post(FIELDS_URL.format(slug=workspace.slug, project_id=project.id), data, format="json")
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return json.loads(json.dumps(response.data, default=str))


def _patch_values(client, workspace, project, issue, values):
    return client.patch(
        ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=issue.id),
        {"custom_fields": values},
        format="json",
    )


def _rows(data):
    """Flatten list / paginated / grouped issue responses into a list of rows."""
    if isinstance(data, list):
        return data
    results = data.get("results", data)
    if isinstance(results, list):
        return results
    rows = []
    for group in results.values():
        rows.extend(group.get("results", []) if isinstance(group, dict) else group)
    return rows


def _list(client, workspace, project, **params):
    response = client.get(ISSUES_URL.format(slug=workspace.slug, project_id=project.id), params)
    assert response.status_code == status.HTTP_200_OK, response.data
    return {str(row["id"]): row for row in _rows(response.data)}


@pytest.mark.contract
@pytest.mark.django_db
class TestCustomFieldDefinitions:
    def test_admin_creates_every_type(self, session_client, workspace, project):
        for field_type in [c for c, _ in CustomField.FieldType.choices]:
            data = {"name": f"Field {field_type}", "field_type": field_type}
            if field_type in ("select", "multi_select", "label"):
                data["options"] = [{"name": "One"}, {"name": "Two", "color": "#EE0000"}]
            if field_type == "formula":
                data["settings"] = {"expression": "1 + 1", "result_type": "number"}
            field = _create_field(session_client, workspace, project, **data)
            assert field["field_type"] == field_type
            if field_type in ("select", "multi_select", "label"):
                assert [o["name"] for o in field["options"]] == ["One", "Two"]
                assert all(o["id"] for o in field["options"])
        response = session_client.get(FIELDS_URL.format(slug=workspace.slug, project_id=project.id))
        assert len(response.data) == len(CustomField.FieldType.choices)
        # Newest goes last.
        orders = [f["sort_order"] for f in response.data]
        assert orders == sorted(orders)

    def test_member_cannot_create_but_can_read(self, member, workspace, project, session_client):
        _create_field(session_client, workspace, project, name="RO number", field_type="text")
        client = _client(member)
        url = FIELDS_URL.format(slug=workspace.slug, project_id=project.id)
        assert client.post(url, {"name": "X", "field_type": "text"}, format="json").status_code == 403
        assert client.get(url).status_code == 200

    def test_duplicate_name_and_bad_type_rejected(self, session_client, workspace, project):
        _create_field(session_client, workspace, project, name="Amount", field_type="money")
        url = FIELDS_URL.format(slug=workspace.slug, project_id=project.id)
        assert session_client.post(url, {"name": "amount", "field_type": "text"}, format="json").status_code == 400
        assert session_client.post(url, {"name": "Y", "field_type": "nope"}, format="json").status_code == 400
        assert session_client.post(url, {"name": "", "field_type": "text"}, format="json").status_code == 400

    def test_type_cannot_change_and_name_can(self, session_client, workspace, project):
        field = _create_field(session_client, workspace, project, name="Vehicle", field_type="text")
        url = FIELD_URL.format(slug=workspace.slug, project_id=project.id, pk=field["id"])
        assert session_client.patch(url, {"field_type": "number"}, format="json").status_code == 400
        response = session_client.patch(url, {"name": "Vehicle (year make model)"}, format="json")
        assert response.status_code == 200
        assert response.data["name"] == "Vehicle (year make model)"

    def test_reorder(self, session_client, workspace, project):
        a = _create_field(session_client, workspace, project, name="A", field_type="text")
        b = _create_field(session_client, workspace, project, name="B", field_type="text")
        c = _create_field(session_client, workspace, project, name="C", field_type="text")
        url = FIELDS_URL.format(slug=workspace.slug, project_id=project.id) + "reorder/"
        response = session_client.post(url, {"field_ids": [c["id"], a["id"], b["id"]]}, format="json")
        assert response.status_code == 200
        assert [f["name"] for f in response.data] == ["C", "A", "B"]
        bad = session_client.post(url, {"field_ids": [str(uuid4())]}, format="json")
        assert bad.status_code == 400

    def test_archive_hides_field_and_keeps_values(self, session_client, workspace, project, state, create_user):
        field = _create_field(session_client, workspace, project, name="RO number", field_type="text")
        issue = _make_issue("Card", project, state, create_user)
        assert _patch_values(session_client, workspace, project, issue, {field["id"]: "10432"}).status_code == 204

        archive_url = FIELD_URL.format(slug=workspace.slug, project_id=project.id, pk=field["id"]) + "archive/"
        assert session_client.post(archive_url).status_code == 200
        fields_url = FIELDS_URL.format(slug=workspace.slug, project_id=project.id)
        assert session_client.get(fields_url).data == []
        assert len(session_client.get(fields_url, {"archived": "true"}).data) == 1
        assert _list(session_client, workspace, project)[str(issue.id)]["custom_fields"] == {}
        # Archived fields refuse new values.
        assert _patch_values(session_client, workspace, project, issue, {field["id"]: "1"}).status_code == 400
        assert CustomFieldValue.objects.filter(field_id=field["id"]).count() == 1

        assert session_client.delete(archive_url).status_code == 200
        assert _list(session_client, workspace, project)[str(issue.id)]["custom_fields"] == {field["id"]: "10432"}

    def test_delete_needs_confirm_name(self, session_client, workspace, project, state, create_user):
        field = _create_field(session_client, workspace, project, name="Call-back date", field_type="date")
        issue = _make_issue("Card", project, state, create_user)
        _patch_values(session_client, workspace, project, issue, {field["id"]: "2026-10-22"})
        url = FIELD_URL.format(slug=workspace.slug, project_id=project.id, pk=field["id"])

        response = session_client.delete(url, {}, format="json")
        assert response.status_code == 400
        assert response.data["code"] == "confirm_name_required"
        assert session_client.delete(url, {"confirm_name": "wrong"}, format="json").status_code == 400

        assert session_client.delete(url, {"confirm_name": "Call-back date"}, format="json").status_code == 204
        assert not CustomField.all_objects.filter(pk=field["id"]).exists()
        assert not CustomFieldValue.all_objects.filter(field_id=field["id"]).exists()

    def test_member_cannot_delete_or_archive(self, session_client, member, workspace, project):
        field = _create_field(session_client, workspace, project, name="X", field_type="text")
        client = _client(member)
        url = FIELD_URL.format(slug=workspace.slug, project_id=project.id, pk=field["id"])
        assert client.delete(url, {"confirm_name": "X"}, format="json").status_code == 403
        assert client.post(url + "archive/").status_code == 403

    def test_removing_an_option_clears_its_values(self, session_client, workspace, project, state, create_user):
        field = _create_field(
            session_client,
            workspace,
            project,
            name="Tech role",
            field_type="select",
            options=[{"name": "A"}, {"name": "B"}],
        )
        a, b = field["options"]
        one = _make_issue("One", project, state, create_user)
        two = _make_issue("Two", project, state, create_user)
        _patch_values(session_client, workspace, project, one, {field["id"]: a["id"]})
        _patch_values(session_client, workspace, project, two, {field["id"]: b["id"]})

        url = FIELD_URL.format(slug=workspace.slug, project_id=project.id, pk=field["id"])
        renamed = {**a, "name": "Lead"}
        assert session_client.patch(url, {"options": [renamed]}, format="json").status_code == 200

        rows = _list(session_client, workspace, project)
        assert rows[str(one.id)]["custom_fields"] == {field["id"]: a["id"]}
        assert rows[str(two.id)]["custom_fields"] == {}
        assert CustomFieldValue.objects.get(field_id=field["id"]).value_text == "Lead"


@pytest.mark.contract
@pytest.mark.django_db
class TestCustomFieldValues:
    @pytest.fixture
    def fields(self, session_client, workspace, project):
        make = lambda **d: _create_field(session_client, workspace, project, **d)  # noqa: E731
        return {
            "text": make(name="RO number", field_type="text"),
            "long_text": make(name="Notes", field_type="long_text"),
            "number": make(name="Mileage", field_type="number"),
            "money": make(name="Amount", field_type="money"),
            "date": make(name="Call-back date", field_type="date"),
            "datetime": make(name="Visit time", field_type="date", settings={"include_time": True}),
            "checkbox": make(name="Approved", field_type="checkbox"),
            "select": make(name="Tech role", field_type="select", options=[{"name": "A"}, {"name": "B"}]),
            "multi": make(name="Ministry", field_type="multi_select", options=[{"name": "X"}, {"name": "Y"}]),
            "label": make(name="Tags", field_type="label"),
            "person": make(name="Owner", field_type="person"),
            "people": make(name="Helpers", field_type="person", settings={"multiple": True}),
            "url": make(name="Link", field_type="url"),
        }

    def test_save_and_read_every_type(self, session_client, workspace, project, state, create_user, member, fields):
        issue = _make_issue("Card", project, state, create_user)
        f = {k: v["id"] for k, v in fields.items()}
        sel_b = fields["select"]["options"][1]["id"]
        multi_ids = [o["id"] for o in fields["multi"]["options"]]
        values = {
            f["text"]: "  10432 ",
            f["long_text"]: "Line one\nLine two",
            f["number"]: "45210.5",
            f["money"]: 121400,
            f["date"]: "2026-10-22",
            f["datetime"]: "2026-10-22T14:30:00Z",
            f["checkbox"]: True,
            f["select"]: sel_b,
            f["multi"]: multi_ids,
            f["label"]: ["Brakes", {"name": "Urgent", "color": "#EE0000"}],
            f["person"]: [str(member.id)],
            f["people"]: [str(member.id), str(create_user.id)],
            f["url"]: "example.com/ro/10432",
        }
        response = _patch_values(session_client, workspace, project, issue, values)
        assert response.status_code == 204, response.data

        detail = session_client.get(ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=issue.id))
        got = detail.data["custom_fields"]
        assert got[f["text"]] == "10432"
        assert got[f["long_text"]] == "Line one\nLine two"
        assert got[f["number"]] == 45210.5
        assert got[f["money"]] == 121400
        assert got[f["date"]] == "2026-10-22"
        assert got[f["datetime"]] == "2026-10-22T14:30:00Z"
        assert got[f["checkbox"]] is True
        assert got[f["select"]] == sel_b
        assert got[f["multi"]] == multi_ids
        assert got[f["url"]] == "https://example.com/ro/10432"
        assert got[f["people"]] == [str(member.id), str(create_user.id)]

        # Label names became options on the field.
        label_field = CustomField.objects.get(pk=f["label"])
        assert [o["name"] for o in label_field.options] == ["Brakes", "Urgent"]
        assert got[f["label"]] == [o["id"] for o in label_field.options]

        # The list endpoint carries the same values.
        assert _list(session_client, workspace, project)[str(issue.id)]["custom_fields"] == got

        # null clears one field and leaves the rest.
        assert _patch_values(session_client, workspace, project, issue, {f["text"]: None}).status_code == 204
        detail = session_client.get(ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=issue.id))
        assert f["text"] not in detail.data["custom_fields"]
        assert detail.data["custom_fields"][f["money"]] == 121400

    @pytest.mark.parametrize(
        "key,bad",
        [
            ("text", "x" * 1001),
            ("text", {"a": 1}),
            ("number", "twelve"),
            ("money", 12.5),
            ("money", "12.50"),
            ("date", "22/10/2026"),
            ("checkbox", "maybe"),
            ("select", "not-an-option"),
            ("multi", ["not-an-option"]),
            ("person", [str(uuid4())]),
            ("url", "javascript:alert(1)"),
            ("url", "ftp://example.com"),
        ],
    )
    def test_bad_values_rejected(self, session_client, workspace, project, state, create_user, fields, key, bad):
        issue = _make_issue("Card", project, state, create_user)
        response = _patch_values(session_client, workspace, project, issue, {fields[key]["id"]: bad})
        assert response.status_code == 400, response.data
        assert not CustomFieldValue.objects.filter(issue=issue).exists()

    def test_single_person_field_takes_one(
        self, session_client, workspace, project, state, create_user, member, fields
    ):
        issue = _make_issue("Card", project, state, create_user)
        response = _patch_values(
            session_client, workspace, project, issue, {fields["person"]["id"]: [str(member.id), str(create_user.id)]}
        )
        assert response.status_code == 400

    def test_field_from_other_project_rejected(self, session_client, workspace, project, state, create_user):
        other = Project.objects.create(name="Other", identifier="OTH", workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(project=other, member=create_user, workspace=workspace, role=20)
        foreign = _create_field(session_client, workspace, other, name="Foreign", field_type="text")
        issue = _make_issue("Card", project, state, create_user)
        assert _patch_values(session_client, workspace, project, issue, {foreign["id"]: "x"}).status_code == 400
        assert _patch_values(session_client, workspace, project, issue, {"not-a-uuid": "x"}).status_code == 400

    def test_create_card_with_values(self, session_client, workspace, project, state, fields):
        response = session_client.post(
            ISSUES_URL.format(slug=workspace.slug, project_id=project.id),
            {"name": "New card", "custom_fields": {fields["money"]["id"]: 64000}},
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["custom_fields"] == {fields["money"]["id"]: 64000}

    def test_whole_map_round_trip_skips_unchanged(
        self, session_client, workspace, project, state, create_user, member, fields
    ):
        """The screen sends the whole map back. Unchanged keys are skipped, even if
        they would fail a check today (here: a person who left the workspace)."""
        issue = _make_issue("Card", project, state, create_user)
        person, money = fields["person"]["id"], fields["money"]["id"]
        _patch_values(session_client, workspace, project, issue, {person: [str(member.id)], money: 100})
        WorkspaceMember.objects.filter(member=member).update(is_active=False)
        response = _patch_values(session_client, workspace, project, issue, {person: [str(member.id)], money: 200})
        assert response.status_code == 204, response.data
        detail = session_client.get(ISSUE_URL.format(slug=workspace.slug, project_id=project.id, pk=issue.id))
        assert detail.data["custom_fields"][money] == 200
        # A changed value is still checked.
        bad = _patch_values(session_client, workspace, project, issue, {person: [str(member.id), str(uuid4())]})
        assert bad.status_code == 400

    def test_guest_member_cannot_write_values(self, guest, workspace, project, state, create_user, fields):
        issue = _make_issue("Card", project, state, create_user)
        response = _patch_values(_client(guest), workspace, project, issue, {fields["text"]["id"]: "x"})
        assert response.status_code == 403


@pytest.mark.contract
@pytest.mark.django_db
class TestCustomFieldFilterAndSort:
    @pytest.fixture
    def setup(self, session_client, workspace, project, state, create_user):
        money = _create_field(session_client, workspace, project, name="Amount", field_type="money")
        date = _create_field(session_client, workspace, project, name="Call-back", field_type="date")
        role = _create_field(
            session_client,
            workspace,
            project,
            name="Role",
            field_type="select",
            options=[{"name": "Lead"}, {"name": "Helper"}],
        )
        done = _create_field(session_client, workspace, project, name="Done", field_type="checkbox")
        tags = _create_field(session_client, workspace, project, name="Tags", field_type="label")
        text = _create_field(session_client, workspace, project, name="RO", field_type="text")
        lead, helper = role["options"]
        cards = {}
        for name, amount, day, opt, checked, tag, ro in [
            ("low", 5000, "2026-10-20", lead, False, "Brakes", "R-100"),
            ("mid", 50000, "2026-10-25", helper, True, "AC", "R-200"),
            ("high", 500000, None, None, True, None, "X-300"),
        ]:
            card = _make_issue(name, project, state, create_user)
            values = {money["id"]: amount, done["id"]: checked, text["id"]: ro}
            if day:
                values[date["id"]] = day
            if opt:
                values[role["id"]] = opt["id"]
            if tag:
                values[tags["id"]] = [tag]
            assert _patch_values(session_client, workspace, project, card, values).status_code == 204
            cards[name] = str(card.id)
        _make_issue("empty", project, state, create_user)
        return {"money": money, "date": date, "role": role, "done": done, "tags": tags, "text": text, "cards": cards}

    def _names(self, client, workspace, project, filters=None, **params):
        if filters is not None:
            params["filters"] = json.dumps(filters)
        rows = _list(client, workspace, project, **params)
        return {row["name"] for row in rows.values()}

    def test_filters(self, session_client, workspace, project, setup):
        k = lambda name, lookup: f"customfield_{setup[name]['id']}__{lookup}"  # noqa: E731
        names = lambda f: self._names(session_client, workspace, project, f)  # noqa: E731
        assert names({k("money", "gte"): 50000}) == {"mid", "high"}
        assert names({k("money", "range"): "1000,60000"}) == {"low", "mid"}
        assert names({k("date", "lt"): "2026-10-22"}) == {"low"}
        assert names({k("date", "isnull"): True}) == {"high", "empty"}
        lead_id = setup["role"]["options"][0]["id"]
        assert names({k("role", "exact"): lead_id}) == {"low"}
        assert names({k("done", "exact"): True}) == {"mid", "high"}
        assert names({k("done", "exact"): False}) == {"low", "empty"}
        brakes = CustomField.objects.get(pk=setup["tags"]["id"]).options[0]["id"]
        assert names({k("tags", "in"): [brakes]}) == {"low"}
        assert names({k("tags", "exact"): brakes}) == {"low"}
        assert names({k("text", "icontains"): "r-"}) == {"low", "mid"}
        assert names({"or": [{k("money", "lt"): 10000}, {k("done", "exact"): True}]}) == {"low", "mid", "high"}

    def test_bad_filters_rejected(self, session_client, workspace, project, setup):
        url = ISSUES_URL.format(slug=workspace.slug, project_id=project.id)
        for filters in [
            {f"customfield_{setup['money']['id']}__icontains": "5"},  # lookup not allowed for money
            {f"customfield_{uuid4()}__exact": "x"},  # unknown field
            {"customfield_nope": "x"},
            {f"customfield_{setup['money']['id']}__gt": "lots"},
        ]:
            response = session_client.get(url, {"filters": json.dumps(filters)})
            assert response.status_code == 400, (filters, response.status_code)

    def test_relative_date_filter(self, session_client, workspace, project, state, create_user):
        from django.utils import timezone as tz
        import datetime

        field = _create_field(session_client, workspace, project, name="Call-back", field_type="date")
        today = tz.localdate()
        for name, offset in [("past", -3), ("today", 0), ("soon", 5), ("later", 30)]:
            card = _make_issue(name, project, state, create_user)
            day = (today + datetime.timedelta(days=offset)).isoformat()
            _patch_values(session_client, workspace, project, card, {field["id"]: day})
        key = f"customfield_{field['id']}"
        assert self._names(session_client, workspace, project, {f"{key}__lt": "@today"}) == {"past"}
        assert self._names(session_client, workspace, project, {f"{key}__range": "@today,@today+7"}) == {
            "today",
            "soon",
        }

    def test_sort(self, session_client, workspace, project, setup):
        def order(param):
            response = session_client.get(
                ISSUES_URL.format(slug=workspace.slug, project_id=project.id), {"order_by": param}
            )
            assert response.status_code == 200
            return [row["name"] for row in _rows(response.data)]

        money = setup["money"]["id"]
        assert order(f"custom_field__{money}") == ["low", "mid", "high", "empty"]
        assert order(f"-custom_field__{money}") == ["high", "mid", "low", "empty"]
        # Dropdowns sort by option order (Lead before Helper); empty last.
        assert order(f"custom_field__{setup['role']['id']}")[:2] == ["low", "mid"]
        # Unknown ids fall back to the default order instead of failing.
        assert len(order(f"custom_field__{uuid4()}")) == 4
        assert len(order("custom_field__not-a-uuid")) == 4


@pytest.mark.contract
@pytest.mark.django_db
class TestCustomFieldVisibility:
    """Values follow their work item: if a user cannot see the card, they cannot see its values."""

    def test_restricted_guest_sees_only_own_card_values(
        self, session_client, guest, workspace, project, state, create_user
    ):
        field = _create_field(session_client, workspace, project, name="Amount", field_type="money")
        own = _make_issue("Guest card", project, state, guest)
        other = _make_issue("Owner card", project, state, create_user)
        _patch_values(session_client, workspace, project, own, {field["id"]: 100})
        _patch_values(session_client, workspace, project, other, {field["id"]: 999900})

        client = _client(guest)
        rows = _list(client, workspace, project)
        assert str(other.id) not in rows
        assert rows[str(own.id)]["custom_fields"] == {field["id"]: 100}

        # Filtering on the value does not reveal the hidden card either.
        filters = json.dumps({f"customfield_{field['id']}__gte": 999900})
        assert _list(client, workspace, project, filters=filters) == {}

        # Nor does the by-id list endpoint.
        response = client.get(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/list/", {"issues": f"{own.id},{other.id}"}
        )
        assert {str(r["id"]) for r in response.data} == {str(own.id)}

    def test_non_member_cannot_read_fields(self, session_client, workspace, project):
        _create_field(session_client, workspace, project, name="Amount", field_type="money")
        outsider = User.objects.create(email="outsider@example.com", username="outsider")
        WorkspaceMember.objects.create(workspace=workspace, member=outsider, role=15)
        response = _client(outsider).get(FIELDS_URL.format(slug=workspace.slug, project_id=project.id))
        assert response.status_code == 403
