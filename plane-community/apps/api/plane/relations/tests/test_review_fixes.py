# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Edge cases found in review: webhooks, two-way edit rights, odd input, private boards."""

import json

import pytest

from plane.db.models import CustomField, Issue, Project, ProjectMember, WorkspaceMember
from plane.relations.models import CardLink
from plane.relations.service import drop_linked_values

from .conftest import FIELDS_URL, client_for, make_user


def fid(field):
    return str(field["id"])


@pytest.mark.django_db
class TestWebhooks:
    def test_linked_values_never_reach_webhooks(self, cast, monkeypatch):
        from plane.bgtasks import webhook_task

        sent = []
        monkeypatch.setattr(webhook_task.webhook_activity, "delay", lambda **kw: sent.append(kw))
        text = cast.field(cast.alpha, name="Note", field_type="text")
        rel = cast.relation()
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "Linked SECRETNAME")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        current = json.dumps({"custom_fields": cast.values(a1)})
        webhook_task.model_activity(
            model_name="issue",
            model_id=str(a1.id),
            requested_data={"custom_fields": {**cast.values(a1), fid(text): "hello"}},
            current_instance=current,
            actor_id=str(cast.admin.id),
            slug=cast.workspace.slug,
        )
        assert sent, "the text change is still reported"
        assert "SECRETNAME" not in str(sent) and str(b1.id) not in str(sent)
        assert sent[0]["new_value"] == {fid(text): "hello"}

    def test_drop_linked_values_keeps_other_fields(self, cast):
        text = cast.field(cast.alpha, name="Note", field_type="text")
        rel = cast.relation()
        assert drop_linked_values({fid(text): "x", fid(rel): [{"id": "y"}]}) == {fid(text): "x"}
        assert drop_linked_values(None) is None


@pytest.mark.django_db
class TestTwoWayEditRights:
    @pytest.fixture
    def view_only(self, cast):
        """member becomes a guest on Beta who may see every card but change none."""
        ProjectMember.objects.filter(project=cast.beta, member=cast.member).update(role=5)
        Project.objects.filter(pk=cast.beta.pk).update(guest_view_all_features=True)

    def test_view_only_cannot_remove_a_two_way_link(self, cast, view_only):
        rel = cast.relation(two_way=True)
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        cast.patch(a1, {fid(rel): None}, client=cast.member_client, expect=400)
        assert CardLink.objects.filter(to_issue_id=b1.id).exists()

    def test_refused_link_on_create_makes_no_card(self, cast, view_only):
        rel = cast.relation(two_way=True)
        b1 = cast.card(cast.beta, "B1")
        before = Issue.objects.filter(project=cast.alpha).count()
        response = cast.member_client.post(
            f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/issues/",
            {"name": "New", "custom_fields": {fid(rel): [str(b1.id)]}},
            format="json",
        )
        assert response.status_code == 400
        assert Issue.objects.filter(project=cast.alpha).count() == before

    def test_turning_two_way_off_needs_target_admin(self, cast):
        rel = cast.relation(two_way=True)
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id) + f"{fid(rel)}/"
        response = cast.alpha_admin_client.patch(url, {"settings": {"two_way": False}}, format="json")
        assert response.status_code == 400
        assert CustomField.objects.get(pk=rel["id"]).settings["mirror_field_id"]

    def test_two_way_false_as_text_is_false(self, cast):
        rel = cast.relation(two_way="false")
        assert rel["settings"]["two_way"] is False and rel["settings"]["mirror_field_id"] is None


@pytest.mark.django_db
class TestOddInput:
    def test_rollup_survives_its_target_changing_type(self, cast):
        hours = cast.field(cast.beta, name="Hours", field_type="number")
        calc = cast.field(
            cast.beta,
            name="Calc",
            field_type="formula",
            settings={"expression": 'prop("Hours") * 2', "result_type": "number"},
        )
        rel = cast.relation()
        b1, a1 = cast.card(cast.beta, "B1"), cast.card(cast.alpha, "A1")
        cast.patch(b1, {fid(hours): 3})
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        total = cast.rollup(rel, "sum", fid(calc))
        assert cast.values(a1)[fid(total)] == 6
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.beta.id) + f"{fid(calc)}/"
        response = cast.admin_client.patch(
            url, {"settings": {"expression": 'concat("x", prop("Hours"))', "result_type": "text"}}, format="json"
        )
        assert response.status_code == 200, response.data
        values = cast.values(a1)  # no error for the whole card
        assert fid(total) not in values

    def test_picker_search_with_unusual_digits(self, cast):
        rel = cast.relation()
        url = FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.alpha.id) + f"{fid(rel)}/link-candidates/"
        assert cast.admin_client.get(url, {"search": "²"}).status_code == 200
        b1 = cast.card(cast.beta, "B1")
        assert [c["id"] for c in cast.admin_client.get(url, {"search": str(b1.sequence_id)}).data] == [str(b1.id)]

    def test_link_to_a_card_that_moved_boards_is_kept(self, cast):
        rel = cast.relation()
        a1, b1 = cast.card(cast.alpha, "A1"), cast.card(cast.beta, "B1")
        cast.patch(a1, {fid(rel): [str(b1.id)]})
        Issue.objects.filter(pk=b1.pk).update(project=cast.alpha)
        assert fid(rel) not in cast.values(a1)
        cast.patch(a1, {fid(rel): None})
        assert CardLink.objects.filter(to_issue_id=b1.id).exists()


@pytest.mark.django_db
class TestPrivateSourceBoard:
    def test_mirror_hides_a_private_source_board(self, cast):
        Project.objects.filter(pk=cast.alpha.pk).update(is_private=True)
        rel = cast.relation(two_way=True)
        mirror = cast.mirror_of(rel)
        assert mirror.name == "Linked cards"

        # Someone on Beta only sees the mirror field but not which board it points at.
        beta_only = make_user("beta_only")
        WorkspaceMember.objects.create(workspace=cast.workspace, member=beta_only, role=15)
        ProjectMember.objects.create(project=cast.beta, member=beta_only, workspace=cast.workspace, role=15)
        response = client_for(beta_only).get(FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.beta.id))
        assert response.status_code == 200
        shown = next(f for f in response.data if str(f["id"]) == str(mirror.id))
        assert shown["settings"]["target_project_id"] is None
        assert str(cast.alpha.id) not in str(response.data) and "Alpha" not in str(response.data)

        # Members of both still see it.
        admin_view = cast.admin_client.get(FIELDS_URL.format(slug=cast.workspace.slug, project_id=cast.beta.id))
        shown = next(f for f in admin_view.data if str(f["id"]) == str(mirror.id))
        assert shown["settings"]["target_project_id"] == str(cast.alpha.id)
