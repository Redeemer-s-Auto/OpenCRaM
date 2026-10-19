# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Formula fields: checked when saved, worked out on the server, kept up to date."""

import datetime
import json

import pytest

from plane.db.models import CustomField, Issue, Project, ProjectMember, State
from plane.utils import formula

FIELDS_URL = "/api/workspaces/{slug}/projects/{project_id}/custom-fields/"
ISSUES_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/"


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(name="Board", identifier="FRM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def state(db, workspace, project):
    return State.objects.create(name="Waiting", project=project, workspace=workspace, group="started", default=True)


def _field(client, workspace, project, **data):
    response = client.post(FIELDS_URL.format(slug=workspace.slug, project_id=project.id), data, format="json")
    return response


def _ok_field(client, workspace, project, **data):
    response = _field(client, workspace, project, **data)
    assert response.status_code == 201, response.data
    return json.loads(json.dumps(response.data, default=str))


def _card(client, workspace, project, **data):
    response = client.post(ISSUES_URL.format(slug=workspace.slug, project_id=project.id), data, format="json")
    assert response.status_code == 201, response.data
    return response.data


def _values(client, workspace, project, card_id):
    url = ISSUES_URL.format(slug=workspace.slug, project_id=project.id) + f"{card_id}/"
    return client.get(url).data["custom_fields"]


def _patch(client, workspace, project, card_id, data):
    url = ISSUES_URL.format(slug=workspace.slug, project_id=project.id) + f"{card_id}/"
    response = client.patch(url, data, format="json")
    assert response.status_code == 204, getattr(response, "data", None)


@pytest.mark.contract
@pytest.mark.django_db
class TestFormulaFields:
    def test_money_formula_follows_its_inputs(self, session_client, workspace, project, state):
        amount = _ok_field(session_client, workspace, project, name="Amount", field_type="money")
        total = _ok_field(
            session_client,
            workspace,
            project,
            name="With tax",
            field_type="formula",
            settings={"expression": 'prop("Amount") * 1.0825', "result_type": "money"},
        )
        card = _card(session_client, workspace, project, name="Job", custom_fields={amount["id"]: 100000})
        assert _values(session_client, workspace, project, card["id"])[total["id"]] == 108250

        _patch(session_client, workspace, project, card["id"], {"custom_fields": {amount["id"]: 20000}})
        assert _values(session_client, workspace, project, card["id"])[total["id"]] == 21650

        # Clearing the input empties the formula.
        _patch(session_client, workspace, project, card["id"], {"custom_fields": {amount["id"]: None}})
        assert total["id"] not in _values(session_client, workspace, project, card["id"])

    def test_formula_reads_built_in_properties(self, session_client, workspace, project, state):
        label = _ok_field(
            session_client,
            workspace,
            project,
            name="Headline",
            field_type="formula",
            settings={"expression": 'concat(upper(prop("Title")), " - ", prop("State"))', "result_type": "text"},
        )
        card = _card(session_client, workspace, project, name="Brake job", state_id=str(state.id))
        assert _values(session_client, workspace, project, card["id"])[label["id"]] == "BRAKE JOB - Waiting"
        _patch(session_client, workspace, project, card["id"], {"name": "AC job"})
        assert _values(session_client, workspace, project, card["id"])[label["id"]] == "AC JOB - Waiting"

    def test_date_and_checkbox_results_filter_and_sort(self, session_client, workspace, project, state):
        visit = _ok_field(session_client, workspace, project, name="Visit", field_type="date")
        follow = _ok_field(
            session_client,
            workspace,
            project,
            name="Follow up",
            field_type="formula",
            settings={"expression": 'dateAdd(prop("Visit"), 7, "days")', "result_type": "date"},
        )
        big = _ok_field(session_client, workspace, project, name="Hours", field_type="number")
        long_job = _ok_field(
            session_client,
            workspace,
            project,
            name="Long job",
            field_type="formula",
            settings={"expression": 'prop("Hours") >= 4', "result_type": "checkbox"},
        )
        a = _card(
            session_client, workspace, project, name="A", custom_fields={visit["id"]: "2026-10-01", big["id"]: 6}
        )
        _card(session_client, workspace, project, name="B", custom_fields={visit["id"]: "2026-10-20", big["id"]: 1})
        assert _values(session_client, workspace, project, a["id"])[follow["id"]] == "2026-10-08"

        url = ISSUES_URL.format(slug=workspace.slug, project_id=project.id)
        rows = session_client.get(
            url, {"filters": json.dumps({f"customfield_{follow['id']}__lt": "2026-10-15"})}
        ).data["results"]
        assert [r["name"] for r in rows] == ["A"]
        rows = session_client.get(
            url, {"filters": json.dumps({f"customfield_{long_job['id']}__exact": True})}
        ).data["results"]
        assert [r["name"] for r in rows] == ["A"]
        rows = session_client.get(url, {"order_by": f"-custom_field__{follow['id']}"}).data["results"]
        assert [r["name"] for r in rows] == ["B", "A"]

    def test_formula_values_cannot_be_written(self, session_client, workspace, project, state):
        f = _ok_field(
            session_client,
            workspace,
            project,
            name="Two",
            field_type="formula",
            settings={"expression": "1 + 1", "result_type": "number"},
        )
        card = _card(session_client, workspace, project, name="X", custom_fields={f["id"]: 99})
        assert _values(session_client, workspace, project, card["id"])[f["id"]] == 2

    def test_bad_formulas_are_refused(self, session_client, workspace, project):
        _ok_field(session_client, workspace, project, name="Amount", field_type="money")
        for settings in [
            {"expression": 'prop("Nope") + 1', "result_type": "number"},
            {"expression": "1 +", "result_type": "number"},
            {"expression": "eval(1)", "result_type": "number"},
            {"expression": "", "result_type": "number"},
            {"expression": "1", "result_type": "colour"},
            {"expression": 'prop("Self F") + 1', "result_type": "number"},
        ]:
            response = _field(session_client, workspace, project, name="Self F", field_type="formula", settings=settings)
            assert response.status_code == 400, settings

    def test_formula_loop_is_refused(self, session_client, workspace, project):
        a = _ok_field(
            session_client,
            workspace,
            project,
            name="A",
            field_type="formula",
            settings={"expression": "1", "result_type": "number"},
        )
        _ok_field(
            session_client,
            workspace,
            project,
            name="B",
            field_type="formula",
            settings={"expression": 'prop("A") + 1', "result_type": "number"},
        )
        url = FIELDS_URL.format(slug=workspace.slug, project_id=project.id) + f"{a['id']}/"
        response = session_client.patch(
            url, {"settings": {"expression": 'prop("B") + 1', "result_type": "number"}}, format="json"
        )
        assert response.status_code == 400

    def test_formulas_can_use_formulas(self, session_client, workspace, project, state):
        hours = _ok_field(session_client, workspace, project, name="Hours", field_type="number")
        labor = _ok_field(
            session_client,
            workspace,
            project,
            name="Labor",
            field_type="formula",
            settings={"expression": 'prop("Hours") * 165', "result_type": "money"},
        )
        # Made after "Total" would need it: order of creation must not matter.
        total = _ok_field(
            session_client,
            workspace,
            project,
            name="Total",
            field_type="formula",
            settings={"expression": 'prop("Labor") + 50', "result_type": "money"},
        )
        card = _card(session_client, workspace, project, name="Job", custom_fields={hours["id"]: 2})
        values = _values(session_client, workspace, project, card["id"])
        assert values[labor["id"]] == 33000
        assert values[total["id"]] == 38000

    def test_rename_keeps_formula_working(self, session_client, workspace, project, state):
        amount = _ok_field(session_client, workspace, project, name="Amount", field_type="money")
        double = _ok_field(
            session_client,
            workspace,
            project,
            name="Double",
            field_type="formula",
            settings={"expression": 'prop("Amount") * 2', "result_type": "money"},
        )
        card = _card(session_client, workspace, project, name="Job", custom_fields={amount["id"]: 500})
        url = FIELDS_URL.format(slug=workspace.slug, project_id=project.id) + f"{amount['id']}/"
        assert session_client.patch(url, {"name": "Price"}, format="json").status_code == 200
        assert CustomField.objects.get(pk=double["id"]).settings["expression"] == 'prop("Price") * 2'
        assert _values(session_client, workspace, project, card["id"])[double["id"]] == 1000

    def test_new_formula_fills_existing_cards(self, session_client, workspace, project, state):
        amount = _ok_field(session_client, workspace, project, name="Amount", field_type="money")
        card = _card(session_client, workspace, project, name="Job", custom_fields={amount["id"]: 1000})
        half = _ok_field(
            session_client,
            workspace,
            project,
            name="Half",
            field_type="formula",
            settings={"expression": 'prop("Amount") / 2', "result_type": "money"},
        )
        assert _values(session_client, workspace, project, card["id"])[half["id"]] == 500


@pytest.mark.unit
class TestFormulaLanguage:
    def run(self, text, props=None):
        props = props or {}
        return formula.evaluate(formula.parse(text), lambda name: props.get(name))

    def test_math_and_logic(self):
        from decimal import Decimal

        assert self.run("1 + 2 * 3") == Decimal(7)
        assert self.run("(1 + 2) * 3") == Decimal(9)
        assert self.run("10 / 0") is None
        assert self.run('if(prop("A") > 5, "big", "small")', {"A": Decimal(6)}) == "big"
        assert self.run("not true or false") is False
        assert self.run("and(true, 1 == 1)") is True
        assert self.run("round(2.345, 2)") == Decimal("2.35")

    def test_text_and_dates(self):
        assert self.run('concat("a", 1, true)') == "a1true"
        assert self.run('contains("Brake job", "BRAKE")') is True
        d = datetime.date(2026, 1, 31)
        assert self.run('dateAdd(prop("D"), 1, "month")', {"D": d}) == datetime.date(2026, 2, 28)
        assert self.run('dateBetween(prop("D"), dateSubtract(prop("D"), 10, "days"), "days")', {"D": d}) == 10

    def test_no_code_runs(self):
        for text in ["__import__('os')", "prop('a').__class__", "open('x')", "1; 2", "[1]"]:
            with pytest.raises(formula.FormulaError):
                formula.parse(text)
