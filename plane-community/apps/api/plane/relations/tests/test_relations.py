# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Relation fields: links, two-way sync, field changes, and deleted cards."""

import pytest
from rest_framework.exceptions import ValidationError

from plane.db.models import CustomField, Issue, IssueActivity
from plane.relations.models import CardLink
from plane.utils.custom_fields import build_filter_q, order_queryset

from .conftest import FIELDS_URL


def fid(field):
    return str(field["id"])


@pytest.mark.django_db
class TestOneWayRelation:
    def test_link_read_unlink_clear(self, cast):
        rel = cast.relation()
        assert rel["settings"]["target_project_id"] == str(cast.beta.id)
        a1 = cast.card(cast.alpha, "A1")
        b1, b2 = cast.card(cast.beta, "First"), cast.card(cast.beta, "Second")

        cast.patch(a1, {fid(rel): [str(b1.id), str(b2.id)]})
        shown = cast.values(a1)[fid(rel)]
        assert [c["id"] for c in shown] == [str(b1.id), str(b2.id)]
        assert shown[0]["name"] == "First" and shown[0]["project_identifier"] == "BET"
        assert shown[0]["sequence_id"] == b1.sequence_id

        # Sending the read shape back (objects) is fine and changes nothing.
        cast.patch(a1, {fid(rel): shown})
        assert cast.linked_ids(a1, rel) == [str(b1.id), str(b2.id)]

        cast.patch(a1, {fid(rel): [str(b2.id)]})
        assert cast.linked_ids(a1, rel) == [str(b2.id)]
        cast.patch(a1, {fid(rel): None})
        assert fid(rel) not in cast.values(a1)
        assert not CardLink.objects.exists()

    def test_target_must_be_a_card_on_the_target_board(self, cast):
        rel = cast.relation()
        a1, a2 = cast.card(cast.alpha, "A1"), cast.card(cast.alpha, "A2")
        response = cast.patch(a1, {fid(rel): [str(a2.id)]}, expect=400)
        assert "cannot be linked" in str(response.data)
        cast.patch(a1, {fid(rel): ["not-an-id"]}, expect=400)

    def test_members_cannot_make_relation_fields(self, cast):
        cast.field(
            cast.alpha,
            client=cast.member_client,
            expect=403,
            name="Nope",
            field_type="relation",
            settings={"target_project_id": str(cast.beta.id)},
        )

    def test_target_board_is_required_and_fixed(self, cast):
        cast.field(cast.alpha, expect=400, name="No target", field_type="relation", settings={})
        rel = cast.relation()
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id) + f"{fid(rel)}/"
        response = cast.admin_client.patch(url, {"settings": {"target_project_id": str(cast.alpha.id)}}, format="json")
        assert response.status_code == 400
        # Renaming keeps the target.
        response = cast.admin_client.patch(url, {"name": "Renamed"}, format="json")
        assert response.status_code == 200 and response.data["settings"]["target_project_id"] == str(cast.beta.id)

    def test_target_board_must_be_one_you_belong_to(self, cast):
        # alpha_only is a workspace admin but not on Beta.
        cast.field(
            cast.alpha,
            client=cast.alpha_only_client,
            expect=400,
            name="X",
            field_type="relation",
            settings={"target_project_id": str(cast.beta.id)},
        )
        cast.field(
            cast.alpha,
            client=cast.alpha_admin_client,
            name="Ok",
            field_type="relation",
            settings={"target_project_id": str(cast.beta.id)},
        )

    def test_formulas_cannot_read_relations(self, cast):
        cast.relation(name="Linked")
        cast.field(
            cast.alpha,
            expect=400,
            name="F",
            field_type="formula",
            settings={"expression": 'prop("Linked")', "result_type": "text"},
        )

    def test_no_filter_or_sort_on_linked_fields(self, cast):
        rel = cast.relation()
        field = CustomField.objects.get(pk=rel["id"])
        with pytest.raises(ValidationError):
            build_filter_q(f"customfield_{field.id}__isnull", "true", {str(field.id): field})
        assert order_queryset(Issue.objects.all(), f"custom_field__{field.id}") == (None, None)

    def test_activity_names_no_cards(self, cast):
        rel = cast.relation(name="Linked")
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "Hidden name XYZZY")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        rows = IssueActivity.objects.filter(issue_id=a1.id, field="custom_field")
        assert rows.count() == 1
        row = rows.get()
        assert "XYZZY" not in (row.old_value or "") + (row.new_value or "") + (row.comment or "")
        assert "Linked" in row.comment


@pytest.mark.django_db
class TestTwoWay:
    def test_mirror_made_on_target_board_and_synced_both_ways(self, cast):
        rel = cast.relation(two_way=True, mirror_name="Linked from Alpha")
        mirror = cast.mirror_of(rel)
        assert mirror.project_id == cast.beta.id and mirror.name == "Linked from Alpha"
        assert mirror.settings["is_mirror"] and mirror.settings["mirror_field_id"] == fid(rel)
        assert mirror.settings["target_project_id"] == str(cast.alpha.id)

        a1, a2 = cast.card(cast.alpha, "A1"), cast.card(cast.alpha, "A2")
        b1, b2 = cast.card(cast.beta, "B1"), cast.card(cast.beta, "B2")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        assert cast.linked_ids(b1, {"id": mirror.id}) == [str(a1.id)]

        # Writing from the other side shows up on the first side.
        cast.patch(b2, {str(mirror.id): [str(a1.id), str(a2.id)]})
        assert sorted(cast.linked_ids(a1, rel)) == sorted([str(b1.id), str(b2.id)])
        assert cast.linked_ids(a2, rel) == [str(b2.id)]
        # Stored once, under the primary field.
        assert CardLink.objects.filter(field_id=rel["id"]).count() == 3
        assert not CardLink.objects.filter(field_id=mirror.id).exists()

        cast.patch(b2, {str(mirror.id): [str(a2.id)]})
        assert cast.linked_ids(a1, rel) == [str(b1.id)]

    def test_default_mirror_name_is_the_source_board_and_unique(self, cast):
        cast.field(cast.beta, name="Alpha", field_type="text")
        rel = cast.relation(two_way=True)
        assert cast.mirror_of(rel).name == "Alpha (2)"

    def test_two_way_needs_admin_of_target(self, cast):
        response = cast.alpha_admin_client.post(
            FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id),
            {"name": "L", "field_type": "relation", "settings": {"target_project_id": str(cast.beta.id), "two_way": True}},
            format="json",
        )
        assert response.status_code == 400 and "admin of the target board" in str(response.data)

    def test_two_way_link_needs_edit_on_the_other_card(self, cast):
        rel = cast.relation(two_way=True)
        guest_card = cast.card(cast.beta, "B1")
        a1 = cast.card(cast.alpha, "A1", author=cast.member)
        # Make member a guest on Beta: can see nothing they did not make, cannot edit.
        from plane.db.models import ProjectMember, Project

        ProjectMember.objects.filter(project=cast.beta, member=cast.member).update(role=5)
        Project.objects.filter(pk=cast.beta.pk).update(guest_view_all_features=True)
        cast.patch(a1, {fid(rel): [str(guest_card.id)]}, client=cast.member_client, expect=400)
        # One-way relations only need to see the card.
        one_way = cast.relation(name="One way")
        cast.patch(a1, {fid(one_way): [str(guest_card.id)]}, client=cast.member_client)

    def test_turn_two_way_off_then_on(self, cast):
        rel = cast.relation(two_way=True)
        mirror = cast.mirror_of(rel)
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id) + f"{fid(rel)}/"

        response = cast.admin_client.patch(url, {"settings": {"two_way": False}}, format="json")
        assert response.status_code == 200 and response.data["settings"]["mirror_field_id"] is None
        assert not CustomField.all_objects.filter(pk=mirror.id).exists()
        assert cast.linked_ids(a1, rel) == [str(b1.id)]

        response = cast.admin_client.patch(url, {"settings": {"two_way": True}}, format="json")
        assert response.status_code == 200
        new_mirror = cast.mirror_of(rel)
        assert cast.linked_ids(b1, {"id": new_mirror.id}) == [str(a1.id)]

    def test_mirror_side_cannot_turn_two_way_off(self, cast):
        rel = cast.relation(two_way=True)
        mirror = cast.mirror_of(rel)
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.beta.id) + f"{mirror.id}/"
        response = cast.admin_client.patch(url, {"settings": {"two_way": False}}, format="json")
        assert response.status_code == 400

    def test_deleting_primary_hands_links_to_mirror(self, cast):
        rel = cast.relation(two_way=True, name="Linked")
        mirror = cast.mirror_of(rel)
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id) + f"{fid(rel)}/"
        assert cast.admin_client.delete(url, {"confirm_name": "Linked"}, format="json").status_code == 204

        mirror.refresh_from_db()
        assert not mirror.settings["is_mirror"] and not mirror.settings["two_way"]
        assert cast.linked_ids(b1, {"id": mirror.id}) == [str(a1.id)]
        # Still writable as a one-way relation.
        a2 = cast.card(cast.alpha, "A2")
        cast.patch(b1, {str(mirror.id): [str(a1.id), str(a2.id)]})
        assert cast.linked_ids(b1, {"id": mirror.id}) == [str(a1.id), str(a2.id)]

    def test_deleting_mirror_makes_primary_one_way(self, cast):
        rel = cast.relation(two_way=True)
        mirror = cast.mirror_of(rel)
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.beta.id) + f"{mirror.id}/"
        assert cast.admin_client.delete(url, {"confirm_name": mirror.name}, format="json").status_code == 204
        field = CustomField.objects.get(pk=rel["id"])
        assert field.settings["two_way"] is False and field.settings["mirror_field_id"] is None
        assert cast.linked_ids(a1, rel) == [str(b1.id)]

    def test_same_board_two_way(self, cast):
        rel = cast.relation(two_way=True, target=cast.alpha, name="Blocks", mirror_name="Blocked by")
        mirror = cast.mirror_of(rel)
        assert mirror.project_id == cast.alpha.id
        a1, a2 = cast.card(cast.alpha, "A1"), cast.card(cast.alpha, "A2")
        cast.patch(a1, {fid(rel): [str(a2.id)]})
        values = cast.values(a2)
        assert [c["id"] for c in values[str(mirror.id)]] == [str(a1.id)]
        assert fid(rel) not in values


@pytest.mark.django_db
class TestDeletedAndArchived:
    def test_deleted_card_drops_out_is_kept_and_comes_back(self, cast):
        rel = cast.relation()
        a1, b1, b2 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1"), cast.card(cast.beta, "B2")
        cast.patch(a1, {fid(rel): [str(b1.id), str(b2.id)]})
        b1.delete()
        assert cast.linked_ids(a1, rel) == [str(b2.id)]
        # Saving what you see does not drop the link to the deleted card.
        cast.patch(a1, {fid(rel): [str(b2.id), str(cast.card(cast.beta, "B3").id)]})
        assert CardLink.objects.filter(to_issue_id=b1.id).exists()
        Issue.all_objects.filter(pk=b1.pk).update(deleted_at=None)
        assert str(b1.id) in cast.linked_ids(a1, rel)

    def test_hard_deleted_card_removes_the_link(self, cast):
        rel = cast.relation()
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        Issue.all_objects.filter(pk=b1.pk).delete()
        assert not CardLink.objects.exists()
        assert fid(rel) not in cast.values(a1)

    def test_archived_relation_field_hides_values(self, cast):
        rel = cast.relation()
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id) + f"{fid(rel)}/archive/"
        assert cast.admin_client.post(url).status_code == 200
        assert fid(rel) not in cast.values(a1)
        assert cast.admin_client.delete(url).status_code == 200
        assert cast.linked_ids(a1, rel) == [str(b1.id)]
