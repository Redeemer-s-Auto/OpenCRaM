# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Percent, phone, email and status fields.

They are stored as the number, text and dropdown types with ``settings["format"]``, so filters,
sort and rollups treat them like those types. The API also takes the short names.
"""

import pytest

from plane.db.models import CustomField
from plane.relations.tests.conftest import *  # noqa: F401,F403  (the cast of users and boards)

QUERY_URL = "/api/workspaces/{slug}/inline-views/query/"
FIELD_URL = "/api/workspaces/{slug}/projects/{project_id}/custom-fields/{pk}/"


def fid(field):
    return str(field["id"])


def query(cast, **body):
    body.setdefault("source", {"type": "project", "project_id": str(cast.alpha.id)})
    return cast.admin_client.post(QUERY_URL.format(slug=cast.workspace.slug), body, format="json")


def bad_value(cast, card, field, value):
    response = cast.patch(card, {fid(field): value}, expect=400)
    assert fid(field) in str(response.data)


# ---------------------------------------------------------------- the short names


@pytest.mark.parametrize(
    "short, base, fmt",
    [("percent", "number", "percent"), ("phone", "text", "phone"), ("email", "text", "email"), ("status", "select", "status")],
)
def test_short_names_make_base_type_with_a_format(cast, short, base, fmt):
    field = cast.field(cast.alpha, name=f"My {short}", field_type=short)
    assert field["field_type"] == base and field["settings"]["format"] == fmt
    assert CustomField.objects.get(pk=field["id"]).settings["format"] == fmt


def test_base_type_with_a_format_works_too(cast):
    field = cast.field(cast.alpha, name="Mobile", field_type="text", settings={"format": "phone"})
    assert field["settings"] == {"format": "phone"}


def test_a_format_must_fit_the_type(cast):
    cast.field(cast.alpha, name="Odd", field_type="number", settings={"format": "email"}, expect=400)
    cast.field(cast.alpha, name="Odd2", field_type="money", settings={"format": "percent"}, expect=400)
    cast.field(cast.alpha, name="Odd3", field_type="text", settings={"format": "bogus"}, expect=400)


def test_the_format_survives_a_settings_edit_and_cannot_change(cast):
    field = cast.field(cast.alpha, name="Done by", field_type="percent", settings={"decimals": 1})
    url = FIELD_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id, pk=field["id"])
    response = cast.admin_client.patch(url, {"settings": {"decimals": 2}}, format="json")
    assert response.status_code == 200 and response.data["settings"] == {"decimals": 2, "format": "percent"}
    response = cast.admin_client.patch(url, {"settings": {"format": "phone"}}, format="json")
    assert response.data["settings"]["format"] == "percent"
    assert cast.admin_client.patch(url, {"field_type": "phone"}, format="json").status_code == 400


# ---------------------------------------------------------------- percent


def test_percent_keeps_the_number_and_filters_and_rolls_up_like_a_number(cast):
    done = cast.field(cast.beta, name="Done", field_type="percent")
    one, two = cast.card(cast.beta, "One"), cast.card(cast.beta, "Two")
    cast.patch(one, {fid(done): 40})
    cast.patch(two, {fid(done): 100.5})
    assert cast.values(one)[fid(done)] == 40 and cast.values(two)[fid(done)] == 100.5
    bad_value(cast, one, done, "lots")
    big = cast.admin_client.post(
        QUERY_URL.format(slug=cast.workspace.slug),
        {
            "source": {"type": "project", "project_id": str(cast.beta.id)},
            "custom_field_filters": {f"customfield_{fid(done)}__gt": 50},
        },
        format="json",
    )
    assert [c["name"] for c in big.data["results"]] == ["Two"]
    rel = cast.relation()
    total = cast.rollup(rel, "sum", fid(done))
    start = cast.card(cast.alpha, "Start")
    cast.patch(start, {fid(rel): [str(one.id), str(two.id)]})
    assert cast.values(start)[fid(total)] == 140.5


# ---------------------------------------------------------------- phone


@pytest.fixture
def phone(cast):
    return cast.field(cast.alpha, name="Phone", field_type="phone")


@pytest.mark.parametrize("number", ["(512) 555-0134", "+1 512 555 0134", "512.555.0134 ext. 12", "555-0134 x9", "+15125550134"])
def test_phone_numbers_are_saved_as_typed(cast, phone, number):
    card = cast.card(cast.alpha, "Call")
    cast.patch(card, {fid(phone): f"  {number}  "})
    assert cast.values(card)[fid(phone)] == number


@pytest.mark.parametrize("number", ["call me", "12345", "1234567890123456789", "555-0134 x", "5125550134; DROP", "<b>5125550134</b>"])
def test_bad_phone_numbers_are_refused(cast, phone, number):
    bad_value(cast, cast.card(cast.alpha, "Call"), phone, number)


def test_phone_filters_like_text(cast, phone):
    a, b = cast.card(cast.alpha, "A"), cast.card(cast.alpha, "B")
    cast.patch(a, {fid(phone): "(512) 555-0134"})
    cast.patch(b, {fid(phone): "(214) 555-0199"})
    found = query(cast, custom_field_filters={f"customfield_{fid(phone)}__icontains": "214"})
    assert [c["name"] for c in found.data["results"]] == ["B"]


def test_clearing_a_phone_number(cast, phone):
    card = cast.card(cast.alpha, "Call")
    cast.patch(card, {fid(phone): "555-0134"})
    cast.patch(card, {fid(phone): ""})
    assert fid(phone) not in cast.values(card)


# ---------------------------------------------------------------- email


@pytest.fixture
def email(cast):
    return cast.field(cast.alpha, name="Email", field_type="email")


def test_email_is_trimmed_and_lowercased(cast, email):
    card = cast.card(cast.alpha, "Mail")
    cast.patch(card, {fid(email): "  Ann.Smith@Example.COM "})
    assert cast.values(card)[fid(email)] == "ann.smith@example.com"


@pytest.mark.parametrize("address", ["nope", "a@b", "two@@example.com", "a b@example.com", "x" * 250 + "@example.com"])
def test_bad_emails_are_refused(cast, email, address):
    bad_value(cast, cast.card(cast.alpha, "Mail"), email, address)


def test_email_filter(cast, email):
    a, b = cast.card(cast.alpha, "A"), cast.card(cast.alpha, "B")
    cast.patch(a, {fid(email): "ann@example.com"})
    cast.patch(b, {fid(email): "bob@shop.example"})
    found = query(cast, custom_field_filters={f"customfield_{fid(email)}__icontains": "shop"})
    assert [c["name"] for c in found.data["results"]] == ["B"]


def test_plain_text_fields_are_not_checked_like_phone_or_email(cast):
    note = cast.field(cast.alpha, name="Note", field_type="text")
    card = cast.card(cast.alpha, "Note")
    cast.patch(card, {fid(note): "call me maybe"})
    assert cast.values(card)[fid(note)] == "call me maybe"


# ---------------------------------------------------------------- status


def test_a_status_field_starts_with_three_grouped_options(cast):
    status = cast.field(cast.alpha, name="Stage", field_type="status")
    assert [(o["name"], o["group"]) for o in status["options"]] == [
        ("Not started", "todo"),
        ("In progress", "in_progress"),
        ("Done", "complete"),
    ]


def test_a_board_can_have_two_status_fields_each_with_its_own_value(cast):
    stage = cast.field(cast.alpha, name="Stage", field_type="status")
    approval = cast.field(
        cast.alpha,
        name="Approval",
        field_type="status",
        options=[
            {"name": "Waiting", "group": "todo"},
            {"name": "Approved", "group": "complete", "color": "#00aa00"},
            {"name": "Declined", "group": "complete"},
        ],
    )
    card = cast.card(cast.alpha, "Job")
    cast.patch(card, {fid(stage): stage["options"][1]["id"], fid(approval): approval["options"][2]["id"]})
    values = cast.values(card)
    assert values[fid(stage)] == stage["options"][1]["id"] and values[fid(approval)] == approval["options"][2]["id"]
    assert [o["group"] for o in approval["options"]] == ["todo", "complete", "complete"]


def test_status_value_must_be_one_of_its_options(cast):
    stage = cast.field(cast.alpha, name="Stage", field_type="status")
    bad_value(cast, cast.card(cast.alpha, "Job"), stage, "not-an-option")


def test_a_status_group_must_be_known(cast):
    cast.field(cast.alpha, name="Stage", field_type="status", options=[{"name": "X", "group": "later"}], expect=400)


def test_options_of_a_plain_dropdown_have_no_group(cast):
    drop = cast.field(cast.alpha, name="Kind", field_type="select", options=[{"name": "A", "group": "complete"}])
    assert "group" not in drop["options"][0]


def test_status_filters_and_sorts_like_a_dropdown(cast):
    stage = cast.field(cast.alpha, name="Stage", field_type="status")
    a, b = cast.card(cast.alpha, "A"), cast.card(cast.alpha, "B")
    cast.patch(a, {fid(stage): stage["options"][2]["id"]})
    cast.patch(b, {fid(stage): stage["options"][0]["id"]})
    found = query(cast, custom_field_filters={f"customfield_{fid(stage)}__exact": stage["options"][2]["id"]})
    assert [c["name"] for c in found.data["results"]] == ["A"]
    ordered = query(cast, order_by=f"custom_field__{fid(stage)}")
    assert [c["name"] for c in ordered.data["results"]] == ["B", "A"]


def test_renaming_a_status_option_keeps_the_value(cast):
    stage = cast.field(cast.alpha, name="Stage", field_type="status")
    card = cast.card(cast.alpha, "Job")
    cast.patch(card, {fid(stage): stage["options"][0]["id"]})
    url = FIELD_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id, pk=stage["id"])
    options = [{**o} for o in stage["options"]]
    options[0]["name"] = "Not begun"
    response = cast.admin_client.patch(url, {"options": options}, format="json")
    assert response.status_code == 200 and response.data["options"][0]["group"] == "todo"
    assert cast.values(card)[fid(stage)] == stage["options"][0]["id"]
