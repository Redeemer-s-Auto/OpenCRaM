# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Synced blocks: one text on many pages, and who may read or change it."""

import pytest
from rest_framework.test import APIClient

from plane.db.models import ProjectMember, WorkspaceMember
from plane.sharing.models import ItemRestriction
from plane.synced_blocks.models import SyncedBlock

from .conftest import client_for, make_user

LIST_URL = "/api/workspaces/{slug}/synced-blocks/"
ONE_URL = "/api/workspaces/{slug}/synced-blocks/{id}/"
SECRET = "TOPSECRET"


def make(cast, client, home, html="<p>Hello</p>", expect=201):
    response = client.post(
        LIST_URL.format(slug=cast.workspace.slug),
        {"home_issue_id": str(home.id), "content_html": html},
        format="json",
    )
    assert response.status_code == expect, getattr(response, "data", None)
    return response.data


def get(cast, client, block_id):
    return client.get(ONE_URL.format(slug=cast.workspace.slug, id=block_id))


def patch(cast, client, block_id, html):
    return client.patch(ONE_URL.format(slug=cast.workspace.slug, id=block_id), {"content_html": html}, format="json")


@pytest.fixture
def home(cast):
    return cast.card(cast.alpha, "Home card")


def test_a_member_makes_a_block_and_every_copy_reads_the_same_text(cast, home):
    block = make(cast, cast.member_client, home)
    assert block["content_html"] == "<p>Hello</p>" and block["version"] == 1 and block["can_edit"] is True
    assert block["home"]["name"] == "Home card"
    # Two copies on two pages are two reads of one row.
    first = get(cast, cast.member_client, block["id"]).data
    second = get(cast, cast.admin_client, block["id"]).data
    assert first["content_html"] == second["content_html"] == "<p>Hello</p>"


def test_an_edit_in_one_copy_shows_in_every_copy(cast, home):
    block = make(cast, cast.member_client, home)
    response = patch(cast, cast.admin_client, block["id"], "<p>Changed</p>")
    assert response.status_code == 200 and response.data["version"] == 2
    seen = get(cast, cast.member_client, block["id"]).data
    assert seen["content_html"] == "<p>Changed</p>" and seen["version"] == 2


def test_empty_block_starts_with_an_empty_paragraph(cast, home):
    block = make(cast, cast.member_client, home, html="")
    assert block["content_html"] == "<p></p>"


def test_cannot_make_a_block_on_a_card_you_cannot_edit(cast):
    beta_card = cast.card(cast.beta, "Beta card")
    # alpha_only is not a member of Beta.
    make(cast, cast.alpha_only_client, beta_card, expect=403)


def test_cannot_make_a_block_on_an_unknown_card(cast):
    response = cast.member_client.post(
        LIST_URL.format(slug=cast.workspace.slug),
        {"home_issue_id": "00000000-0000-0000-0000-000000000000"},
        format="json",
    )
    assert response.status_code == 403


def test_text_is_hidden_from_someone_who_cannot_see_the_home_card(cast):
    secret_home = cast.card(cast.alpha, f"Secret home {SECRET}")
    block = make(cast, cast.admin_client, secret_home, html=f"<p>{SECRET}</p>")
    ItemRestriction.objects.create(workspace=cast.workspace, issue=secret_home)
    for client in (cast.member_client,):
        response = get(cast, client, block["id"])
        assert response.status_code == 403
        assert SECRET not in str(response.data) and response.data == {"error": "no_access"}
        assert patch(cast, client, block["id"], "<p>x</p>").status_code == 403
        assert client.delete(ONE_URL.format(slug=cast.workspace.slug, id=block["id"])).status_code == 403
    assert get(cast, cast.admin_client, block["id"]).status_code == 200


def test_picker_lists_only_readable_blocks(cast, home):
    secret_home = cast.card(cast.alpha, "Secret home")
    open_block = make(cast, cast.admin_client, home, html="<p>Open text</p>")
    hidden_block = make(cast, cast.admin_client, secret_home, html=f"<p>{SECRET}</p>")
    ItemRestriction.objects.create(workspace=cast.workspace, issue=secret_home)
    response = cast.member_client.get(LIST_URL.format(slug=cast.workspace.slug))
    ids = [row["id"] for row in response.data]
    assert open_block["id"] in ids and hidden_block["id"] not in ids
    assert SECRET not in str(response.data)
    found = cast.member_client.get(LIST_URL.format(slug=cast.workspace.slug), {"search": SECRET})
    assert found.data == []
    by_text = cast.member_client.get(LIST_URL.format(slug=cast.workspace.slug), {"search": "open"})
    assert [row["id"] for row in by_text.data] == [open_block["id"]]
    assert by_text.data[0]["snippet"] == "Open text"


def test_a_block_that_does_not_exist_looks_like_a_hidden_one(cast):
    response = get(cast, cast.member_client, "00000000-0000-0000-0000-000000000000")
    assert response.status_code == 403 and response.data == {"error": "no_access"}


def test_block_is_not_readable_through_another_workspace(cast, home):
    block = make(cast, cast.member_client, home)
    response = cast.member_client.get(ONE_URL.format(slug="no-such-workspace", id=block["id"]))
    assert response.status_code in (403, 404)
    assert "Hello" not in str(response.data)


def test_a_viewer_who_can_see_but_not_edit_gets_read_only(cast, home):
    cast.alpha.guest_view_all_features = True
    cast.alpha.save()
    guest = make_user("guest")
    WorkspaceMember.objects.create(workspace=cast.workspace, member=guest, role=5)
    ProjectMember.objects.create(project=cast.alpha, member=guest, workspace=cast.workspace, role=5)
    block = make(cast, cast.member_client, home)
    client = client_for(guest)
    read = get(cast, client, block["id"])
    assert read.status_code == 200 and read.data["can_edit"] is False
    assert patch(cast, client, block["id"], "<p>no</p>").status_code in (403,)
    assert get(cast, cast.member_client, block["id"]).data["content_html"] == "<p>Hello</p>"


def test_outsider_and_anonymous_get_nothing(cast, home):
    block = make(cast, cast.member_client, home)
    outsider = client_for(make_user("outsider"))
    assert get(cast, outsider, block["id"]).status_code == 403
    anonymous = APIClient().get(ONE_URL.format(slug=cast.workspace.slug, id=block["id"]))
    assert anonymous.status_code in (401, 403)


def test_script_is_cleaned_out_of_the_text(cast, home):
    block = make(cast, cast.member_client, home, html="<p>Hi</p><script>alert(1)</script>")
    assert "<script" not in block["content_html"]
    saved = patch(cast, cast.member_client, block["id"], "<p>Yo</p><script>alert(2)</script>")
    assert saved.status_code == 200 and "<script" not in saved.data["content_html"]


def test_a_synced_block_cannot_hold_another_synced_block(cast, home):
    nested = '<div data-block-type="synced-block" data-synced-id="x"></div>'
    make(cast, cast.member_client, home, html=nested, expect=400)
    block = make(cast, cast.member_client, home)
    assert patch(cast, cast.member_client, block["id"], nested).status_code == 400
    assert get(cast, cast.member_client, block["id"]).data["content_html"] == "<p>Hello</p>"


def test_bad_text_is_refused(cast, home):
    block = make(cast, cast.member_client, home)
    response = cast.member_client.patch(
        ONE_URL.format(slug=cast.workspace.slug, id=block["id"]), {"content_html": ["not text"]}, format="json"
    )
    assert response.status_code == 400
    missing = cast.member_client.patch(ONE_URL.format(slug=cast.workspace.slug, id=block["id"]), {}, format="json")
    assert missing.status_code == 400


def test_creator_or_admin_can_delete_others_cannot(cast, home):
    block = make(cast, cast.member_client, home)
    url = ONE_URL.format(slug=cast.workspace.slug, id=block["id"])
    other = cast.alpha_admin_client  # a board admin but only a workspace member
    assert other.delete(url).status_code == 403
    assert SyncedBlock.objects.filter(pk=block["id"]).exists()
    assert cast.member_client.delete(url).status_code == 204
    assert not SyncedBlock.objects.filter(pk=block["id"]).exists()
    assert get(cast, cast.member_client, block["id"]).status_code == 403
    again = make(cast, cast.member_client, home)
    assert cast.admin_client.delete(ONE_URL.format(slug=cast.workspace.slug, id=again["id"])).status_code == 204


def test_an_archived_home_card_still_shows_the_text(cast, home):
    from django.utils import timezone

    block = make(cast, cast.member_client, home)
    home.archived_at = timezone.now().date()
    home.save()
    assert get(cast, cast.member_client, block["id"]).status_code == 200


def test_a_deleted_home_card_hides_the_block(cast, home):
    block = make(cast, cast.member_client, home)
    home.delete()
    assert get(cast, cast.member_client, block["id"]).status_code == 403
