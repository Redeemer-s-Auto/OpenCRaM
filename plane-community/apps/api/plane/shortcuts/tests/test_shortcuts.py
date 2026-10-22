# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shortcut cards: making them, where they go, and what each viewer is told."""

import datetime as dt
import uuid

import pytest
from django.db import transaction

from plane.db.models import Issue
from plane.shortcuts.models import SHORTCUT_NAME, CardShortcut
from plane.utils.issue_templates import snapshot_issue

from .conftest import SECRET, add_shortcut, card, url


def project_shortcuts(cast, client, project):
    response = client.get(url(cast, f"projects/{project.id}/shortcuts/"))
    assert response.status_code == 200, response.content
    return response


@pytest.mark.django_db
class TestMakeShortcut:
    def test_member_of_both_boards_adds_one(self, links):
        response = add_shortcut(links, links.both_client, links.alpha, links.beta_open.id)
        issue = Issue.objects.get(pk=response.data["id"])
        assert issue.project_id == links.alpha.id and issue.name == SHORTCUT_NAME
        assert CardShortcut.objects.get(issue=issue).target_id == links.beta_open.id
        assert response.data["target"]["status"] == "visible"
        assert response.data["target"]["card"]["name"] == "Beta open target"

    def test_cannot_point_at_a_card_you_cannot_see_and_error_says_nothing(self, links):
        hidden = add_shortcut(links, links.insider_client, links.alpha, links.beta_open.id, expect=400)
        missing = add_shortcut(links, links.insider_client, links.alpha, uuid.uuid4(), expect=400)
        assert hidden.data == missing.data
        secret = add_shortcut(links, links.both_client, links.alpha, links.beta_secret.id, expect=400)
        assert secret.data == missing.data
        assert not CardShortcut.objects.exists()

    def test_not_a_member_of_the_destination_board(self, links):
        add_shortcut(links, links.outsider_client, links.alpha, links.beta_open.id, expect=403)

    def test_guest_cannot_add(self, links):
        from plane.db.models import ProjectMember

        ProjectMember.objects.filter(project=links.alpha, member=links.both).update(role=5)
        add_shortcut(links, links.both_client, links.alpha, links.beta_open.id, expect=403)

    def test_private_destination_board_is_not_found(self, links):
        response = links.both_client.post(
            url(links, f"projects/{links.gamma.id}/shortcuts/"), {"target_id": str(links.beta_open.id)}, format="json"
        )
        assert response.status_code in (403, 404)

    def test_no_shortcut_to_a_shortcut(self, links):
        first = add_shortcut(links, links.both_client, links.alpha, links.beta_open.id)
        add_shortcut(links, links.both_client, links.beta, first.data["id"], expect=400)

    def test_as_a_sub_card(self, links):
        parent = card(links, "Alpha parent")
        response = add_shortcut(links, links.both_client, links.alpha, links.beta_open.id, parent_id=str(parent.id))
        assert str(Issue.objects.get(pk=response.data["id"]).parent_id) == str(parent.id)


@pytest.mark.django_db
class TestWhatViewersAreTold:
    @pytest.fixture
    def shortcut(self, links):
        # Owner (admin) puts a shortcut to the restricted Beta card on Alpha.
        response = add_shortcut(links, links.owner_client, links.alpha, links.beta_secret.id)
        return Issue.objects.get(pk=response.data["id"])

    def test_board_list_endpoint(self, links, shortcut):
        insider = project_shortcuts(links, links.insider_client, links.alpha)
        assert insider.data["results"] == {str(shortcut.id): {"status": "hidden"}}
        assert SECRET.encode() not in insider.content and str(links.beta_secret.id).encode() not in insider.content
        owner = project_shortcuts(links, links.owner_client, links.alpha)
        assert owner.data["results"][str(shortcut.id)]["card"]["id"] == str(links.beta_secret.id)

    def test_single_card_endpoint(self, links, shortcut):
        response = links.insider_client.get(url(links, f"cards/{shortcut.id}/shortcut/"))
        assert response.status_code == 200
        assert response.data == {"is_shortcut": True, "target": {"status": "hidden"}}
        plain = links.insider_client.get(url(links, f"cards/{links.source.id}/shortcut/"))
        assert plain.data == {"is_shortcut": False, "target": None}
        # The shortcut card itself out of reach (outsider is not on Alpha): 404.
        assert links.outsider_client.get(url(links, f"cards/{shortcut.id}/shortcut/")).status_code == 404

    def test_card_tree_and_page_list(self, links, shortcut):
        tree = links.insider_client.get(url(links, "card-tree/"), {"project_id": str(links.alpha.id)})
        assert tree.status_code == 200
        row = next(r for r in tree.data["results"] if str(r["id"]) == str(shortcut.id))
        assert row["shortcut"] == {"status": "hidden"} and row["name"] == SHORTCUT_NAME
        plain = next(r for r in tree.data["results"] if str(r["id"]) == str(links.source.id))
        assert plain["shortcut"] is None
        pages = links.insider_client.get(url(links, f"projects/{links.alpha.id}/page-list/"))
        assert pages.status_code == 200
        row = next(r for r in pages.data["results"] if str(r["id"]) == str(shortcut.id))
        assert row["shortcut"] == {"status": "hidden"}
        for response in (tree, pages):
            assert SECRET.encode() not in response.content
            assert str(links.beta_secret.id).encode() not in response.content
        owner_tree = links.owner_client.get(url(links, "card-tree/"), {"project_id": str(links.alpha.id)})
        row = next(r for r in owner_tree.data["results"] if str(r["id"]) == str(shortcut.id))
        assert row["shortcut"]["status"] == "visible"

    def test_board_issue_list_shows_the_neutral_name(self, links, shortcut):
        response = links.insider_client.get(f"/api/workspaces/{links.workspace.slug}/projects/{links.alpha.id}/issues/")
        assert response.status_code == 200
        assert SECRET.encode() not in response.content
        assert str(links.beta_secret.id).encode() not in response.content


@pytest.mark.django_db
class TestRemovedTarget:
    def test_soft_deleted_target(self, links):
        response = add_shortcut(links, links.owner_client, links.alpha, links.beta_open.id)
        shortcut_id = response.data["id"]
        links.beta_open.delete()
        both = links.both_client.get(url(links, f"cards/{shortcut_id}/shortcut/"))
        assert both.data["target"] == {"status": "removed"}
        insider = links.insider_client.get(url(links, f"cards/{shortcut_id}/shortcut/"))
        assert insider.data["target"] == {"status": "hidden"}

    def test_hard_deleted_target(self, links):
        response = add_shortcut(links, links.owner_client, links.alpha, links.beta_open.id)
        Issue.all_objects.filter(pk=links.beta_open.id).delete()
        info = links.both_client.get(url(links, f"cards/{response.data['id']}/shortcut/"))
        assert info.status_code == 200
        assert info.data["target"] == {"status": "removed"}
        tree = links.both_client.get(url(links, "card-tree/"), {"project_id": str(links.alpha.id)})
        assert tree.status_code == 200

    def test_deleting_the_shortcut_card_keeps_the_target(self, links):
        response = add_shortcut(links, links.owner_client, links.alpha, links.beta_open.id)
        Issue.objects.get(pk=response.data["id"]).delete()
        assert Issue.objects.filter(pk=links.beta_open.id).exists()
        assert project_shortcuts(links, links.owner_client, links.alpha).data["results"] == {}


@pytest.mark.django_db
class TestCopies:
    def test_templates_leave_shortcut_sub_cards_out(self, links):
        parent = card(links, "Parent")
        child = card(links, "Real child", parent=parent)
        add_shortcut(links, links.owner_client, links.alpha, links.beta_open.id, parent_id=str(parent.id))
        data = snapshot_issue(parent)
        assert [node["name"] for node in data["sub_items"]] == [child.name]

    def test_repeats_leave_shortcut_sub_cards_out(self, links):
        from plane.recurrence.copier import make_copy

        parent = card(links, "Repeat me", author=links.author)
        card(links, "Real child", parent=parent, author=links.author)
        add_shortcut(links, links.owner_client, links.alpha, links.beta_open.id, parent_id=str(parent.id))
        with transaction.atomic():
            copy = make_copy(parent, dt.timedelta(days=1), links.author)
        names = list(Issue.issue_objects.filter(parent_id=copy.id).values_list("name", flat=True))
        assert names == ["Real child"]

    def test_link_blocks_are_copied_by_templates(self, links):
        data = snapshot_issue(links.source)
        assert str(links.beta_secret.id) in data["description_html"]
