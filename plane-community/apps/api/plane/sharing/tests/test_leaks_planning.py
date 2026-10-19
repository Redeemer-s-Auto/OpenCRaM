# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Leak tests for cycles, modules, analytics and exports.

Each test checks that ``insider`` gets no row, id, name or count that includes the
restricted item, and that ``author`` (or ``friend``) still sees it.
"""

import io
import json
import zipfile
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from plane.db.models import (
    AnalyticView,
    Cycle,
    CycleIssue,
    Intake,
    IntakeIssue,
    Issue,
    IssueLabel,
    Label,
    Module,
    ModuleIssue,
)
from plane.sharing.tests.conftest import make_issue

MARK = "TOPSECRET"


def ws(cast):
    return f"/api/workspaces/{cast.workspace.slug}"


def proj(cast):
    return f"{ws(cast)}/projects/{cast.alpha.id}"


def no_leak(response, *ids):
    assert response.status_code == 200, response.content
    body = response.content.decode()
    assert MARK not in body
    for item_id in ids:
        assert str(item_id) not in body


@pytest.fixture
def plan(cast, secret_issue):
    """Open parent + restricted child, both in one cycle and one module; the child has a secret label."""
    open_issue = make_issue(cast, "Open parent")
    Issue.objects.filter(pk=secret_issue.pk).update(parent=open_issue)
    label = Label.objects.create(name=f"Label {MARK}", project=cast.alpha, workspace=cast.workspace)
    IssueLabel.objects.create(issue=secret_issue, label=label, project=cast.alpha, workspace=cast.workspace)

    now = timezone.now()
    cycle = Cycle.objects.create(
        name="Sprint",
        project=cast.alpha,
        workspace=cast.workspace,
        owned_by=cast.author,
        start_date=now - timedelta(days=3),
        end_date=now + timedelta(days=3),
    )
    module = Module.objects.create(
        name="Release",
        project=cast.alpha,
        workspace=cast.workspace,
        start_date=(now - timedelta(days=3)).date(),
        target_date=(now + timedelta(days=3)).date(),
    )
    for issue in (open_issue, secret_issue):
        CycleIssue.objects.create(cycle=cycle, issue=issue, project=cast.alpha, workspace=cast.workspace)
        ModuleIssue.objects.create(module=module, issue=issue, project=cast.alpha, workspace=cast.workspace)

    class Plan:
        pass

    p = Plan()
    p.open, p.secret, p.cycle, p.module, p.label = open_issue, secret_issue, cycle, module, label
    return p


def by_id(rows, item_id):
    return next(row for row in rows if str(row["id"]) == str(item_id))


@pytest.mark.django_db
class TestCycles:
    def test_cycle_list_counts(self, cast, plan):
        url = f"{proj(cast)}/cycles/"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id)
        assert by_id(insider.data, plan.cycle.id)["total_issues"] == 1
        assert by_id(cast.author_client.get(url).data, plan.cycle.id)["total_issues"] == 2

    def test_cycle_retrieve_counts(self, cast, plan):
        url = f"{proj(cast)}/cycles/{plan.cycle.id}/"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id)
        assert insider.data["total_issues"] == 1
        assert insider.data["sub_issues"] == 0
        author = cast.author_client.get(url).data
        assert author["total_issues"] == 2 and author["sub_issues"] == 1

    def test_cycle_issue_list(self, cast, plan):
        url = f"{proj(cast)}/cycles/{plan.cycle.id}/cycle-issues/?per_page=50&cursor=50:0:0"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id)
        assert str(plan.open.id) in insider.content.decode()
        assert insider.data["total_count"] == 1
        open_row = next(row for row in insider.data["results"] if str(row["id"]) == str(plan.open.id))
        assert open_row["sub_issues_count"] == 0
        author = cast.author_client.get(url)
        assert MARK in author.content.decode() and author.data["total_count"] == 2

    def test_cycle_issue_add_skips_hidden(self, cast, plan):
        other = Cycle.objects.create(name="Next", project=cast.alpha, workspace=cast.workspace, owned_by=cast.author)
        url = f"{proj(cast)}/cycles/{other.id}/cycle-issues/"
        response = cast.insider_client.post(url, {"issues": [str(plan.secret.id)]}, format="json")
        assert response.status_code == 201
        assert CycleIssue.objects.get(issue=plan.secret).cycle_id == plan.cycle.id
        response = cast.author_client.post(url, {"issues": [str(plan.secret.id)]}, format="json")
        assert response.status_code == 201
        assert CycleIssue.objects.get(issue=plan.secret).cycle_id == other.id

    def test_cycle_progress(self, cast, plan):
        url = f"{proj(cast)}/cycles/{plan.cycle.id}/progress/"
        insider = cast.insider_client.get(url)
        no_leak(insider)
        assert insider.data["total_issues"] == 1 and insider.data["unstarted_issues"] == 1
        assert cast.author_client.get(url).data["total_issues"] == 2

    def test_cycle_analytics_and_burndown(self, cast, plan):
        url = f"{proj(cast)}/cycles/{plan.cycle.id}/analytics/?type=issues"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.label.id)
        today = str(timezone.now().date())
        assert insider.data["completion_chart"][today] == 1
        author = cast.author_client.get(url)
        assert MARK in author.content.decode()
        assert author.data["completion_chart"][today] == 2

    def test_archived_cycle(self, cast, plan):
        Cycle.objects.filter(pk=plan.cycle.pk).update(archived_at=timezone.now())
        list_url = f"{proj(cast)}/archived-cycles/"
        insider = cast.insider_client.get(list_url)
        no_leak(insider, plan.secret.id)
        assert by_id(insider.data, plan.cycle.id)["total_issues"] == 1
        assert by_id(cast.author_client.get(list_url).data, plan.cycle.id)["total_issues"] == 2

        detail_url = f"{proj(cast)}/archived-cycles/{plan.cycle.id}/"
        insider = cast.insider_client.get(detail_url)
        no_leak(insider, plan.secret.id, plan.label.id)
        assert insider.data["total_issues"] == 1 and insider.data["sub_issues"] == 0
        assert MARK in cast.author_client.get(detail_url).content.decode()

    def test_workspace_cycles(self, cast, plan):
        url = f"{ws(cast)}/cycles/"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id)
        assert by_id(insider.data, plan.cycle.id)["total_issues"] == 1
        assert by_id(cast.author_client.get(url).data, plan.cycle.id)["total_issues"] == 2

    def test_transfer_leaves_hidden_items_and_snapshot(self, cast, plan):
        new_cycle = Cycle.objects.create(
            name="Later", project=cast.alpha, workspace=cast.workspace, owned_by=cast.author
        )
        url = f"{proj(cast)}/cycles/{plan.cycle.id}/transfer-issues/"
        response = cast.insider_client.post(url, {"new_cycle_id": str(new_cycle.id)}, format="json")
        assert response.status_code == 200, response.content
        # The visible item moved; the hidden one stayed where it was.
        assert CycleIssue.objects.get(issue=plan.open).cycle_id == new_cycle.id
        assert CycleIssue.objects.get(issue=plan.secret).cycle_id == plan.cycle.id
        snapshot = Cycle.objects.get(pk=plan.cycle.pk).progress_snapshot
        assert snapshot["total_issues"] == 1
        assert MARK not in json.dumps(snapshot)


@pytest.mark.django_db
class TestModules:
    def test_module_list_counts(self, cast, plan):
        url = f"{proj(cast)}/modules/"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id)
        assert by_id(insider.data, plan.module.id)["total_issues"] == 1
        assert by_id(cast.author_client.get(url).data, plan.module.id)["total_issues"] == 2

    def test_module_retrieve(self, cast, plan):
        url = f"{proj(cast)}/modules/{plan.module.id}/"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id, plan.label.id)
        assert insider.data["total_issues"] == 1 and insider.data["sub_issues"] == 0
        today = str(timezone.now().date())
        assert insider.data["distribution"]["completion_chart"][today] == 1
        author = cast.author_client.get(url)
        assert MARK in author.content.decode()
        assert author.data["total_issues"] == 2 and author.data["sub_issues"] == 1

    def test_module_issue_list(self, cast, plan):
        url = f"{proj(cast)}/modules/{plan.module.id}/issues/?per_page=50&cursor=50:0:0"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id)
        assert insider.data["total_count"] == 1
        open_row = next(row for row in insider.data["results"] if str(row["id"]) == str(plan.open.id))
        assert open_row["sub_issues_count"] == 0
        assert cast.author_client.get(url).data["total_count"] == 2

    def test_module_issue_add_skips_hidden(self, cast, plan):
        other = Module.objects.create(name="Other", project=cast.alpha, workspace=cast.workspace)
        url = f"{proj(cast)}/modules/{other.id}/issues/"
        assert cast.insider_client.post(url, {"issues": [str(plan.secret.id)]}, format="json").status_code == 201
        assert not ModuleIssue.objects.filter(module=other, issue=plan.secret).exists()
        assert cast.author_client.post(url, {"issues": [str(plan.secret.id)]}, format="json").status_code == 201
        assert ModuleIssue.objects.filter(module=other, issue=plan.secret).exists()

    def test_archived_module(self, cast, plan):
        Module.objects.filter(pk=plan.module.pk).update(archived_at=timezone.now())
        list_url = f"{proj(cast)}/archived-modules/"
        insider = cast.insider_client.get(list_url)
        no_leak(insider, plan.secret.id)
        assert by_id(insider.data, plan.module.id)["total_issues"] == 1
        assert by_id(cast.author_client.get(list_url).data, plan.module.id)["total_issues"] == 2

        detail_url = f"{proj(cast)}/archived-modules/{plan.module.id}/"
        insider = cast.insider_client.get(detail_url)
        no_leak(insider, plan.secret.id, plan.label.id)
        assert insider.data["total_issues"] == 1
        assert MARK in cast.author_client.get(detail_url).content.decode()

    def test_workspace_modules(self, cast, plan):
        url = f"{ws(cast)}/modules/"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.secret.id)
        assert by_id(insider.data, plan.module.id)["total_issues"] == 1
        assert by_id(cast.author_client.get(url).data, plan.module.id)["total_issues"] == 2


@pytest.mark.django_db
class TestAnalytics:
    def test_analytics(self, cast, plan):
        url = f"{ws(cast)}/analytics/?x_axis=labels__id&y_axis=issue_count"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.label.id)
        assert insider.data["total"] == 1
        author = cast.author_client.get(url)
        assert author.data["total"] == 2 and MARK in author.content.decode()

    def test_saved_analytic(self, cast, plan):
        view = AnalyticView.objects.create(
            workspace=cast.workspace,
            name="Saved",
            query={"workspace__slug": cast.workspace.slug},
            query_dict={"x_axis": "labels__id", "y_axis": "issue_count"},
        )
        url = f"{ws(cast)}/saved-analytic-view/{view.id}/"
        insider = cast.insider_client.get(url)
        no_leak(insider, plan.label.id)
        assert insider.data["total"] == 1
        assert cast.author_client.get(url).data["total"] == 2

    def test_default_analytics(self, cast, plan):
        url = f"{ws(cast)}/default-analytics/"
        insider = cast.insider_client.get(url)
        no_leak(insider)
        assert insider.data["total_issues"] == 1
        assert cast.author_client.get(url).data["total_issues"] == 2

    def test_project_stats(self, cast, plan):
        url = f"{ws(cast)}/project-stats/?fields=total_issues&project_ids={cast.alpha.id}"
        insider = cast.insider_client.get(url)
        no_leak(insider)
        assert insider.data[0]["total_issues"] == 1
        assert cast.author_client.get(url).data[0]["total_issues"] == 2

    def test_advance_analytics(self, cast, plan, secret_page):
        url = f"{ws(cast)}/advance-analytics/?tab=work-items"
        insider = cast.insider_client.get(url)
        no_leak(insider)
        assert insider.data["total_work_items"]["count"] == 1
        assert cast.author_client.get(url).data["total_work_items"]["count"] == 2

        stats_url = f"{ws(cast)}/advance-analytics-stats/?type=work-items"
        insider_stats = cast.insider_client.get(stats_url)
        no_leak(insider_stats)
        alpha = next(row for row in insider_stats.data if str(row["project_id"]) == str(cast.alpha.id))
        assert alpha["un_started_work_items"] == 1

        charts_url = f"{ws(cast)}/advance-analytics-charts/?type=projects"
        insider_chart = {row["key"]: row["count"] for row in cast.insider_client.get(charts_url).data}
        author_chart = {row["key"]: row["count"] for row in cast.author_client.get(charts_url).data}
        assert insider_chart["work_items"] == 1 and author_chart["work_items"] == 2
        assert insider_chart["pages"] == author_chart["pages"] - 1

        custom_url = f"{ws(cast)}/advance-analytics-charts/?type=custom-work-items&x_axis=LABELS"
        no_leak(cast.insider_client.get(custom_url), plan.label.id)

    def test_project_advance_analytics(self, cast, plan):
        base = f"{proj(cast)}"
        insider = cast.insider_client.get(f"{base}/advance-analytics/?tab=work-items")
        no_leak(insider)
        assert insider.data["total_work_items"]["count"] == 1
        author = cast.author_client.get(f"{base}/advance-analytics/?tab=work-items")
        assert author.data["total_work_items"]["count"] == 2

        cycle_counts = cast.insider_client.get(f"{base}/advance-analytics/?tab=work-items&cycle_id={plan.cycle.id}")
        assert cycle_counts.data["total_work_items"]["count"] == 1

        custom = f"{base}/advance-analytics-charts/?type=custom-work-items&x_axis=LABELS&module_id={plan.module.id}"
        no_leak(cast.insider_client.get(custom), plan.label.id)
        assert MARK in cast.author_client.get(custom).content.decode()

    def test_analytics_export_email(self, cast, plan):
        sent = []
        with mock.patch(
            "plane.bgtasks.analytic_plot_export.send_export_email",
            side_effect=lambda email, slug, csv_buffer, rows: sent.append(rows),
        ):
            for client in (cast.insider_client, cast.author_client):
                response = client.post(
                    f"{ws(cast)}/export-analytics/", {"x_axis": "labels__id", "y_axis": "issue_count"}, format="json"
                )
                assert response.status_code == 200
        insider_rows, author_rows = sent
        assert MARK not in json.dumps(insider_rows, default=str)
        assert MARK in json.dumps(author_rows, default=str)

    def test_project_intake_count(self, cast, secret_issue):
        intake = Intake.objects.create(name="Intake", project=cast.alpha, workspace=cast.workspace, is_default=True)
        IntakeIssue.objects.create(
            intake=intake, issue=secret_issue, status=-2, project=cast.alpha, workspace=cast.workspace
        )
        url = f"{ws(cast)}/projects/"
        insider = by_id(cast.insider_client.get(url).data, cast.alpha.id)
        author = by_id(cast.author_client.get(url).data, cast.alpha.id)
        # Upstream multiplies this count by the member join, so only test zero vs non-zero.
        assert insider["intake_count"] == 0 and author["intake_count"] > 0


@pytest.mark.django_db
class TestIssueExport:
    def run_export(self, cast, client):
        captured = []

        def fake_upload(zip_buffer, workspace_id, token_id, slug):
            captured.append(zip_buffer.getvalue())

        with mock.patch("plane.bgtasks.export_task.upload_to_s3", side_effect=fake_upload):
            response = client.post(
                f"{ws(cast)}/export-issues/", {"provider": "json", "project": [str(cast.alpha.id)]}, format="json"
            )
        assert response.status_code == 200, response.content
        assert captured, "export did not run"
        with zipfile.ZipFile(io.BytesIO(captured[0])) as archive:
            return "".join(archive.read(name).decode() for name in archive.namelist())

    def test_export_leaves_out_hidden_items_and_links(self, cast, secret_issue):
        child = make_issue(cast, "Visible child", parent=secret_issue)
        insider = self.run_export(cast, cast.insider_client)
        assert MARK not in insider
        assert "Visible child" in insider
        secret_key = f"{cast.alpha.identifier}-{secret_issue.sequence_id}"
        rows = json.loads(insider)
        child_row = next(row for row in rows if row["name"] == child.name)
        assert child_row["parent"] == ""
        assert secret_key not in json.dumps([row for row in rows if row["name"] == child.name])

        author_rows = json.loads(self.run_export(cast, cast.author_client))
        assert any(MARK in row["name"] for row in author_rows)
        assert next(row for row in author_rows if row["name"] == child.name)["parent"] == secret_key

    def test_schema_export_has_no_restricted_links(self, cast, secret_issue):
        from plane.utils.exporters.schemas.issue import IssueExportSchema

        child = make_issue(cast, "Visible child", parent=secret_issue)
        rows = IssueExportSchema.serialize_queryset(Issue.issue_objects.filter(pk=child.pk), fields=["parent"])
        assert rows == [{"parent": ""}]
