# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

""""Linked from": the index follows every save, and each viewer sees only sources they may see."""

import pytest
from django.core.management import call_command

from plane.db.models import Issue
from plane.sharing.models import AccessLevel, ShareTarget
from plane.shortcuts.models import CardBodyLink
from plane.shortcuts.service import card_ids_in

from .conftest import ISSUE_URL, SECRET, add_shortcut, block, body, card, restrict, url


def targets_of(issue):
    return {str(i) for i in CardBodyLink.objects.filter(source_id=issue.id).values_list("target_id", flat=True)}


def backlinks(cast, client, issue, expect=200):
    response = client.get(url(cast, f"cards/{issue.id}/backlinks/"))
    assert response.status_code == expect, response.content
    return response


def patch_body(cast, client, issue, html):
    response = client.patch(
        ISSUE_URL.format(slug=cast.workspace.slug, project_id=issue.project_id, issue_id=issue.id),
        {"description_html": html},
        format="json",
    )
    assert response.status_code in (200, 204), response.content


@pytest.mark.django_db
class TestIndex:
    def test_parse(self):
        a, b = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
        html = f"{block(a)}<p>x</p>{block(b)}{block(a)}<card-link-component data-card-id='nope'></card-link-component>"
        assert card_ids_in(html) == [a, b]
        assert card_ids_in("") == [] and card_ids_in(None) == []

    def test_made_on_create(self, links):
        assert targets_of(links.source) == {
            str(links.beta_open.id),
            str(links.beta_secret.id),
            str(links.gamma_card.id),
        }

    def test_follows_edits_through_the_app(self, links):
        patch_body(links, links.owner_client, links.source, body(links.beta_open.id))
        assert targets_of(links.source) == {str(links.beta_open.id)}
        patch_body(links, links.owner_client, links.source, "<p>No links now</p>")
        assert targets_of(links.source) == set()

    def test_link_to_itself_is_ignored(self, links):
        own = card(links, "Self")
        own.description_html = body(own.id)
        own.save()
        assert targets_of(own) == set()

    def test_rebuild_command(self, links):
        CardBodyLink.objects.all().delete()
        Issue.objects.filter(pk=links.beta_open.pk).update(description_html=body(links.source.id))
        call_command("rebuild_card_links")
        assert targets_of(links.source) == {
            str(links.beta_open.id),
            str(links.beta_secret.id),
            str(links.gamma_card.id),
        }
        assert targets_of(links.beta_open) == {str(links.source.id)}


@pytest.mark.django_db
class TestLinkedFrom:
    def test_lists_blocks_and_shortcuts(self, links):
        shortcut = add_shortcut(links, links.both_client, links.alpha, links.beta_open.id).data["id"]
        rows = backlinks(links, links.both_client, links.beta_open).data["results"]
        assert {(r["id"], r["kind"]) for r in rows} == {(str(links.source.id), "link"), (shortcut, "shortcut")}

    def test_sources_the_viewer_cannot_see_are_left_out(self, links):
        # outsider is on Beta only: sees the target, not the Alpha source.
        response = backlinks(links, links.outsider_client, links.beta_open)
        assert response.data["results"] == []
        assert b"Alpha source" not in response.content

    def test_restricted_source_is_left_out(self, links):
        restrict(links, issue=links.source, shares=[(ShareTarget.MEMBER, links.friend, AccessLevel.VIEW)])
        assert backlinks(links, links.both_client, links.beta_open).data["results"] == []
        assert [r["id"] for r in backlinks(links, links.owner_client, links.beta_open).data["results"]] == [
            str(links.source.id)
        ]

    def test_private_board_source_is_left_out(self, links):
        hidden_source = card(links, f"Gamma source {SECRET}", project=links.gamma, description_html=body(links.beta_open.id))
        response = backlinks(links, links.both_client, links.beta_open)
        assert str(hidden_source.id) not in {r["id"] for r in response.data["results"]}
        assert SECRET.encode() not in response.content

    def test_target_out_of_reach_is_not_found(self, links):
        backlinks(links, links.both_client, links.beta_secret, expect=404)
        backlinks(links, links.both_client, links.gamma_card, expect=404)
        backlinks(links, links.insider_client, links.beta_open, expect=404)

    def test_someone_elses_draft_is_not_found(self, links):
        draft = card(links, "A draft", project=links.beta, is_draft=True)
        backlinks(links, links.both_client, draft, expect=404)
        assert links.both_client.get(url(links, f"cards/{draft.id}/shortcut/")).status_code == 404

    def test_deleted_source_drops_out(self, links):
        links.source.delete()
        assert backlinks(links, links.both_client, links.beta_open).data["results"] == []
