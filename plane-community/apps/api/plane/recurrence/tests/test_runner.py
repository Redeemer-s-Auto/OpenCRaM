# Copyright (c) 2026 OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""The repeat job: copies, idempotency, catch-up, stopping."""

import datetime as dt

import pytest
from rest_framework import status

from plane.db.models import (
    CustomField,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueLabel,
    Label,
    ProjectMember,
    State,
)
from plane.recurrence import tasks
from plane.recurrence.models import RepeatOccurrence, RepeatRule
from plane.recurrence.tests.conftest import make_rule
from plane.sharing.models import AccessLevel, ItemRestriction, ShareTarget
from plane.utils.custom_fields import set_values, validate_values, values_for_issues

from .conftest import NOW, make_issue, restrict

UTC = dt.timezone.utc


def copies_of(rule):
    return Issue.issue_objects.filter(repeat_occurrence__rule=rule)


@pytest.mark.unit
class TestIdempotency:
    def test_running_twice_makes_one_copy(self, cast, template):
        rule = make_rule(cast, template)
        assert tasks.run_rule(rule.id, NOW) is not None
        assert tasks.run_rule(rule.id, NOW) is None
        assert copies_of(rule).count() == 1
        rule.refresh_from_db()
        assert rule.created_count == 1
        assert rule.next_run_at == dt.datetime(2026, 10, 20, 6, 0, tzinfo=UTC)

    def test_beat_task_twice_makes_one_copy(self, cast, template, frozen_clock):
        rule = make_rule(cast, template, next_run_at=dt.datetime(2026, 10, 1, 6, 0, tzinfo=UTC))
        tasks.run_due_repeats()
        tasks.run_due_repeats()
        assert copies_of(rule).count() == 1
        assert RepeatOccurrence.objects.filter(rule=rule).count() == 1

    def test_slot_already_recorded_is_not_copied_again(self, cast, template):
        """A restart after the copy was committed finds the slot and only moves the rule on."""
        rule = make_rule(cast, template)
        RepeatOccurrence.objects.create(rule=rule, scheduled_for=rule.next_run_at)
        assert tasks.run_rule(rule.id, NOW) is None
        assert copies_of(rule).count() == 0
        rule.refresh_from_db()
        assert rule.next_run_at > NOW

    def test_not_due_does_nothing(self, cast, template):
        rule = make_rule(cast, template, next_run_at=NOW + dt.timedelta(minutes=5))
        assert tasks.run_rule(rule.id, NOW) is None
        assert copies_of(rule).count() == 0


@pytest.mark.unit
class TestCatchUp:
    def test_missed_days_make_one_copy_for_the_newest_slot(self, cast, template, frozen_clock):
        rule = make_rule(cast, template, next_run_at=dt.datetime(2026, 10, 14, 6, 0, tzinfo=UTC))
        copy = tasks.run_rule(rule.id, NOW)
        assert copies_of(rule).count() == 1
        occurrence = RepeatOccurrence.objects.get(rule=rule)
        assert occurrence.scheduled_for == dt.datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
        assert occurrence.issue_id == copy.id
        rule.refresh_from_db()
        assert rule.next_run_at == dt.datetime(2026, 10, 20, 6, 0, tzinfo=UTC)
        # A second pass the same morning (the beat job reads the frozen clock) makes nothing more.
        tasks.run_due_repeats()
        assert copies_of(rule).count() == 1

    def test_finished_rule_turns_off(self, cast, template):
        rule = make_rule(cast, template, max_count=1)
        tasks.run_rule(rule.id, NOW)
        rule.refresh_from_db()
        assert rule.is_active is False and rule.next_run_at is None
        assert "Finished" in rule.stop_reason

    def test_end_date_turns_off(self, cast, template):
        rule = make_rule(cast, template, end_date=dt.date(2026, 10, 19))
        tasks.run_rule(rule.id, NOW)
        rule.refresh_from_db()
        assert rule.is_active is False
        assert copies_of(rule).count() == 1


@pytest.mark.unit
class TestCopyContents:
    def test_copy_carries_card_contents(self, cast, template, django_capture_on_commit_callbacks):
        done = State.objects.create(name="Done", project=cast.alpha, workspace=cast.workspace, group="completed")
        template.state = done
        template.start_date = dt.date(2026, 10, 1)
        template.target_date = dt.date(2026, 10, 3)
        template.save()
        label = Label.objects.create(name="Numbers", project=cast.alpha, workspace=cast.workspace)
        IssueLabel.objects.create(issue=template, label=label, project=cast.alpha, workspace=cast.workspace)
        IssueAssignee.objects.create(issue=template, assignee=cast.friend, project=cast.alpha, workspace=cast.workspace)
        text = CustomField.objects.create(name="Total", field_type="text", project=cast.alpha, workspace=cast.workspace)
        set_values(template, validate_values(cast.alpha.id, {str(text.id): "pending"}))
        child = make_issue(cast, "Sub step one", parent=template)
        grandchild = make_issue(cast, "Sub step deep", parent=child)
        make_issue(cast, "Sub step two", parent=template)

        rule = make_rule(cast, template)  # start 2026-10-01, run day 2026-10-19 => dates move 18 days
        with django_capture_on_commit_callbacks(execute=True):
            copy = tasks.run_rule(rule.id, NOW)

        copy = Issue.issue_objects.get(pk=copy.id)
        assert copy.id != template.id
        assert copy.name == "Weekly numbers"
        assert "Fill in the numbers" in copy.description_html
        assert copy.priority == "high"
        assert copy.state_id == cast.state.id  # the project's default state, not "Done"
        assert copy.created_by_id == cast.author.id
        assert copy.start_date == dt.date(2026, 10, 19)
        assert copy.target_date == dt.date(2026, 10, 21)
        assert set(IssueLabel.objects.filter(issue=copy).values_list("label_id", flat=True)) == {label.id}
        assert set(IssueAssignee.objects.filter(issue=copy).values_list("assignee_id", flat=True)) == {cast.friend.id}
        assert values_for_issues([copy.id])[str(copy.id)] == {str(text.id): "pending"}

        children = Issue.issue_objects.filter(parent=copy)
        assert sorted(children.values_list("name", flat=True)) == ["Sub step one", "Sub step two"]
        child_copy = children.get(name="Sub step one")
        assert child_copy.id != child.id
        assert Issue.issue_objects.filter(parent=child_copy, name=grandchild.name).count() == 1
        # The template and its sub-items are untouched.
        assert Issue.issue_objects.filter(parent=template).count() == 2

        assert IssueActivity.objects.filter(issue=copy, verb="created", actor=cast.author).exists()

    def test_linked_card_fields_are_not_copied(self, cast, template):
        from plane.db.models import CustomFieldValue

        relation = CustomField.objects.create(
            name="Linked", field_type="relation", project=cast.alpha, workspace=cast.workspace
        )
        note = CustomField.objects.create(name="Note", field_type="text", project=cast.alpha, workspace=cast.workspace)
        CustomFieldValue.objects.create(
            issue=template, field=relation, project=cast.alpha, workspace=cast.workspace, value=[str(template.id)]
        )
        set_values(template, validate_values(cast.alpha.id, {str(note.id): "keep"}))
        copy = tasks.run_rule(make_rule(cast, template).id, NOW)
        assert values_for_issues([copy.id])[str(copy.id)] == {str(note.id): "keep"}

    def test_editing_the_template_changes_future_copies_only(self, cast, template):
        rule = make_rule(cast, template)
        first = tasks.run_rule(rule.id, NOW)
        template.name = "Weekly numbers v2"
        template.save()
        second = tasks.run_rule(rule.id, NOW + dt.timedelta(days=1))
        assert Issue.issue_objects.get(pk=first.id).name == "Weekly numbers"
        assert Issue.issue_objects.get(pk=second.id).name == "Weekly numbers v2"


@pytest.mark.unit
class TestSharing:
    def test_restricted_template_makes_restricted_copies(self, cast, template):
        restrict(cast, issue=template, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
        rule = make_rule(cast, template)
        copy = tasks.run_rule(rule.id, NOW)
        assert ItemRestriction.objects.filter(issue=copy).exists()
        url = f"/api/workspaces/{cast.workspace.slug}/projects/{cast.alpha.id}/issues/{copy.id}/"
        assert cast.insider_client.get(url).status_code == status.HTTP_404_NOT_FOUND
        assert cast.friend_client.get(url).status_code == status.HTTP_200_OK
        assert cast.author_client.get(url).status_code == status.HTTP_200_OK

    def test_sub_items_the_owner_cannot_see_are_left_out(self, cast, template):
        make_issue(cast, "Visible step", parent=template)
        hidden = make_issue(cast, "Owner-only step", parent=template, author=cast.owner)
        restrict(cast, issue=hidden)  # nobody on the list: only its creator and admins see it
        rule = make_rule(cast, template)
        copy = tasks.run_rule(rule.id, NOW)
        assert list(Issue.issue_objects.filter(parent=copy).values_list("name", flat=True)) == ["Visible step"]


@pytest.mark.unit
class TestStops:
    def test_owner_left_the_project(self, cast, template):
        rule = make_rule(cast, template)
        ProjectMember.objects.filter(project=cast.alpha, member=cast.author).update(is_active=False)
        assert tasks.run_rule(rule.id, NOW) is None
        rule.refresh_from_db()
        assert rule.is_active is False and "no longer" in rule.stop_reason
        assert copies_of(rule).count() == 0

    def test_owner_lost_edit_access_to_a_restricted_card(self, cast, template):
        rule = make_rule(cast, template, created_by=cast.friend)
        restrict(cast, issue=template, shares=[(ShareTarget.MEMBER, cast.friend, AccessLevel.VIEW)])
        assert tasks.run_rule(rule.id, NOW) is None
        rule.refresh_from_db()
        assert rule.is_active is False and "can no longer edit" in rule.stop_reason

    def test_deleted_template(self, cast, template):
        rule = make_rule(cast, template)
        template.delete()
        assert tasks.run_rule(rule.id, NOW) is None
        rule.refresh_from_db()
        assert rule.is_active is False and "deleted" in rule.stop_reason

    def test_one_broken_rule_does_not_stop_the_others(self, cast, template, monkeypatch, frozen_clock):
        other = make_issue(cast, "Other")
        bad = make_rule(cast, template)
        good = make_rule(cast, other)
        real = tasks.make_copy

        def flaky(issue, delta, actor):
            if issue.id == template.id:
                raise RuntimeError("boom")
            return real(issue, delta, actor)

        monkeypatch.setattr(tasks, "make_copy", flaky)
        assert tasks.run_due_repeats() == 1
        assert copies_of(good).count() == 1
        assert RepeatOccurrence.objects.filter(rule=bad).count() == 0  # rolled back, retried next run
        assert RepeatRule.objects.get(pk=bad.pk).next_run_at == NOW + tasks.RETRY_AFTER  # tried again in an hour


@pytest.mark.unit
def test_job_is_on_the_beat_schedule():
    from plane.celery import app

    entries = [entry["task"] for entry in app.conf.beat_schedule.values()]
    assert "plane.recurrence.tasks.run_due_repeats" in entries
    app.loader.import_default_modules()
    assert "plane.recurrence.tasks.run_due_repeats" in app.tasks


@pytest.mark.django_db(transaction=True)
def test_two_workers_at_once_make_one_copy(cast, template):
    """Two workers pick up the same due rule at the same moment: one copy."""
    import threading

    from django.db import connection

    rule = make_rule(cast, template)
    barrier = threading.Barrier(2)
    results = []

    def worker():
        try:
            barrier.wait(timeout=10)
            results.append(tasks.run_rule(rule.id, NOW))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert len([r for r in results if r is not None]) == 1
    assert copies_of(rule).count() == 1
    assert RepeatOccurrence.objects.filter(rule=rule).count() == 1
