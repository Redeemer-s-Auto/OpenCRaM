# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rollup fields: every function, settings checks, and fresh values after changes."""

import datetime

import pytest

from plane.db.models import CustomField
from plane.relations.service import compute_rollup

from .conftest import FIELDS_URL


def fid(field):
    return str(field["id"])


@pytest.fixture
def board(cast):
    """Alpha card ``a1`` links three Beta cards with assorted values; ``a2`` links nothing."""
    beta = cast.beta
    amount = cast.field(beta, name="Amount", field_type="money")
    hours = cast.field(beta, name="Hours", field_type="number")
    due = cast.field(beta, name="Due", field_type="date")
    done = cast.field(beta, name="Done", field_type="checkbox")
    tags = cast.field(
        beta, name="Tags", field_type="multi_select", options=[{"name": "Red"}, {"name": "Blue"}, {"name": "Green"}]
    )
    note = cast.field(beta, name="Note", field_type="text")
    red, blue = (o["id"] for o in tags["options"][:2])

    b1 = cast.card(beta, "Bravo", target_date=datetime.date(2026, 11, 2))
    b2 = cast.card(beta, "Alpha card", target_date=datetime.date(2026, 10, 30))
    b3 = cast.card(beta, "Charlie")
    cast.patch(
        b1,
        {fid(amount): 1000, fid(hours): 2, fid(due): "2026-10-05", fid(done): True, fid(tags): [red], fid(note): "x"},
    )
    cast.patch(
        b2,
        {fid(amount): 2501, fid(hours): 3.5, fid(due): "2026-10-01", fid(done): False, fid(tags): [red, blue]},
    )
    rel = cast.relation(name="Parts")
    a1, a2 = cast.card(cast.alpha, "A1"), cast.card(cast.alpha, "A2")
    cast.patch(a1, {fid(rel): [str(b1.id), str(b2.id), str(b3.id)]})

    class Board:
        pass

    b = Board()
    b.amount, b.hours, b.due, b.done, b.tags, b.note, b.rel = amount, hours, due, done, tags, note, rel
    b.a1, b.a2, b.b1, b.b2, b.b3 = a1, a2, b1, b2, b3
    return b


@pytest.mark.django_db
class TestRollupFunctions:
    @pytest.mark.parametrize(
        "function,target,expected,result_type",
        [
            ("count", None, 3, "number"),
            ("count_empty", "amount", 1, "number"),
            ("count_not_empty", "amount", 2, "number"),
            ("count_not_empty", "note", 1, "number"),
            ("sum", "amount", 3501, "money"),
            ("avg", "amount", 1751, "money"),  # 1750.5 cents rounds half up
            ("min", "amount", 1000, "money"),
            ("max", "amount", 2501, "money"),
            ("sum", "hours", 5.5, "number"),
            ("avg", "hours", 2.75, "number"),
            ("earliest", "due", "2026-10-01", "date"),
            ("latest", "due", "2026-10-05", "date"),
            ("unique", "tags", ["Red", "Blue"], "list"),
            ("percent_checked", "done", 33.333333, "percent"),
            ("earliest", "@due_date", "2026-10-30", "date"),
            ("unique", "@title", ["Bravo", "Alpha card", "Charlie"], "list"),
            ("count_empty", "@due_date", 1, "number"),
        ],
    )
    def test_function(self, cast, board, function, target, expected, result_type):
        target_id = None if target is None else (target if target.startswith("@") else fid(getattr(board, target)))
        rollup = cast.rollup(board.rel, function, target_id)
        assert rollup["settings"]["result_type"] == result_type
        assert cast.values(board.a1)[fid(rollup)] == expected

    def test_no_links(self, cast, board):
        count = cast.rollup(board.rel, "count")
        total = cast.rollup(board.rel, "sum", fid(board.amount))
        values = cast.values(board.a2)
        assert values[fid(count)] == 0
        assert fid(total) not in values

    def test_sum_of_empty_values_is_zero(self):
        assert compute_rollup("sum", ["x"], {"x": None}, None, False) == 0
        assert compute_rollup("avg", ["x"], {"x": None}, None, False) is None
        assert compute_rollup("percent_checked", [], {}, None, False) is None

    def test_date_times_compare_with_dates(self):
        values = {"a": "2026-10-01T23:00:00Z", "b": "2026-10-02"}
        assert compute_rollup("earliest", ["a", "b"], values, None, False) == "2026-10-01T23:00:00Z"
        assert compute_rollup("latest", ["a", "b"], values, None, False) == "2026-10-02"


@pytest.mark.django_db
class TestRollupSettings:
    def test_bad_settings_refused(self, cast, board):
        cast.rollup(board.rel, "sum", fid(board.note), expect=400)  # text cannot be summed
        cast.rollup(board.rel, "earliest", fid(board.hours), expect=400)
        cast.rollup(board.rel, "percent_checked", fid(board.amount), expect=400)
        cast.rollup(board.rel, "median", fid(board.amount), expect=400)
        cast.rollup(board.rel, "sum", "@title", expect=400)
        cast.rollup(board.rel, "count_empty", None, expect=400)  # needs a target
        # A field on the wrong board.
        alpha_amount = cast.field(cast.alpha, name="Local", field_type="money")
        cast.rollup(board.rel, "sum", fid(alpha_amount), expect=400)
        # A rollup of a rollup.
        inner = cast.field(
            cast.beta,
            name="Inner rel",
            field_type="relation",
            settings={"target_project_id": str(cast.alpha.id)},
        )
        inner_rollup = cast.field(
            cast.beta,
            name="Inner count",
            field_type="rollup",
            settings={"relation_field_id": inner["id"], "function": "count"},
        )
        cast.rollup(board.rel, "sum", fid(inner_rollup), expect=400)
        # The relation must be on the same board.
        cast.field(
            cast.alpha,
            expect=400,
            name="Bad",
            field_type="rollup",
            settings={"relation_field_id": inner["id"], "function": "count"},
        )

    def test_rollup_values_cannot_be_written(self, cast, board):
        rollup = cast.rollup(board.rel, "count")
        cast.patch(board.a1, {fid(rollup): 99})
        assert cast.values(board.a1)[fid(rollup)] == 3

    def test_rollup_needs_membership_of_linked_board_for_its_fields(self, cast, board):
        # alpha_only (admin of Alpha, not on Beta) cannot read Beta field ids through a rollup.
        response = cast.alpha_only_client.post(
            FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id),
            {
                "name": "Peek",
                "field_type": "rollup",
                "settings": {
                    "relation_field_id": fid(board.rel),
                    "function": "sum",
                    "target_field_id": fid(board.amount),
                },
            },
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestRollupStaysCurrent:
    def test_follows_linked_card_changes(self, cast, board):
        total = cast.rollup(board.rel, "sum", fid(board.amount))
        assert cast.values(board.a1)[fid(total)] == 3501

        cast.patch(board.b1, {fid(board.amount): 5000})  # a linked card's value changes
        assert cast.values(board.a1)[fid(total)] == 7501

        cast.patch(board.a1, {fid(board.rel): [str(board.b1.id), str(board.b3.id)]})  # unlink b2
        assert cast.values(board.a1)[fid(total)] == 5000

        board.b1.delete()  # linked card deleted
        assert cast.values(board.a1)[fid(total)] == 0

    def test_archived_or_deleted_target_empties_the_rollup(self, cast, board):
        total = cast.rollup(board.rel, "sum", fid(board.amount), name="Total")
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.beta.id) + f"{fid(board.amount)}/"
        assert cast.admin_client.post(url + "archive/").status_code == 200
        assert fid(total) not in cast.values(board.a1)
        assert cast.admin_client.delete(url + "archive/").status_code == 200
        assert cast.values(board.a1)[fid(total)] == 3501
        assert cast.admin_client.delete(url, {"confirm_name": "Amount"}, format="json").status_code == 204
        assert fid(total) not in cast.values(board.a1)

    def test_deleted_relation_empties_the_rollup(self, cast, board):
        count = cast.rollup(board.rel, "count")
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id) + f"{fid(board.rel)}/"
        assert cast.admin_client.delete(url, {"confirm_name": "Parts"}, format="json").status_code == 204
        assert fid(count) not in cast.values(board.a1)
        assert CustomField.objects.filter(pk=count["id"]).exists()

    def test_rollup_through_the_mirror_side(self, cast, board):
        rel = cast.relation(two_way=True, name="Two way")
        mirror = cast.mirror_of(rel)
        cast.patch(board.a1, {fid(rel): [str(board.b1.id)]})
        cast.patch(board.a2, {fid(rel): [str(board.b1.id)]})
        response = cast.admin_client.post(
            FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.beta.id),
            {
                "name": "Linked count",
                "field_type": "rollup",
                "settings": {"relation_field_id": str(mirror.id), "function": "count"},
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert cast.values(board.b1)[str(response.data["id"])] == 2
