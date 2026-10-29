# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Nothing about a hidden target reaches anyone through the other doors.

Link blocks store the card id only and shortcut cards are named "Shortcut", so the
public (v1) API, webhook payloads and the activity log carry no target title.
"""

import pytest
from rest_framework.test import APIClient

from plane.bgtasks.webhook_task import get_model_data
from plane.db.models import IssueActivity
from plane.db.models.api import APIToken

from .conftest import ISSUE_URL, SECRET, add_shortcut, body


@pytest.fixture
def setup(links):
    shortcut_id = add_shortcut(links, links.owner_client, links.alpha, links.beta_secret.id).data["id"]
    # The owner writes the links through the app, as a person would.
    response = links.owner_client.patch(
        ISSUE_URL.format(slug=links.workspace.slug, project_id=links.alpha.id, issue_id=links.source.id),
        {"description_html": body(links.beta_secret.id, links.gamma_card.id)},
        format="json",
    )
    assert response.status_code in (200, 204), response.content
    links.shortcut_id = shortcut_id
    return links


@pytest.fixture
def insider_key(links):
    client = APIClient()
    token = APIToken.objects.create(user=links.insider, label="insider key", token="insider-shortcuts-key-1")
    client.credentials(HTTP_X_API_KEY=token.token)
    return client


@pytest.mark.django_db
class TestOtherDoors:
    def test_v1_api(self, setup, insider_key):
        base = f"/api/v1/workspaces/{setup.workspace.slug}/projects/{setup.alpha.id}/issues/"
        for path in ("", f"{setup.shortcut_id}/", f"{setup.source.id}/"):
            response = insider_key.get(base + path)
            assert response.status_code == 200, response.content
            assert SECRET.encode() not in response.content
        shortcut = insider_key.get(f"{base}{setup.shortcut_id}/").data
        assert shortcut["name"] == "Shortcut"

    def test_webhook_payloads(self, setup):
        for issue_id in (setup.shortcut_id, str(setup.source.id)):
            payload = get_model_data("issue", issue_id)
            assert SECRET not in str(payload)
            assert "Beta secret" not in str(payload)

    def test_activity_log(self, setup):
        rows = IssueActivity.objects.filter(issue_id__in=[setup.shortcut_id, setup.source.id])
        assert rows.exists()
        for row in rows.values("old_value", "new_value", "comment"):
            assert SECRET not in str(row)

    def test_activity_endpoint_for_insider(self, setup):
        url = (
            f"/api/workspaces/{setup.workspace.slug}/projects/{setup.alpha.id}/issues/{setup.shortcut_id}/history/"
        )
        response = setup.insider_client.get(url, {"activity_type": "issue-property"})
        assert response.status_code == 200, response.content
        assert SECRET.encode() not in response.content
