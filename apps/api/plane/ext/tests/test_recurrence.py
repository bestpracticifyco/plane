# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Recurring work items: rules, triggers, copying, idempotency, permissions."""

import datetime as dt

import pytest
from crum import impersonate
from django.utils import timezone

from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueLink,
    Label,
    Module,
    ModuleIssue,
    ProjectMember,
    State,
)
from plane.ext import recurring, services, tasks
from plane.ext.models import ExtPropertyValue, ExtRecurrenceRule, ExtRecurrenceSpawn

pytestmark = pytest.mark.django_db
D = dt.date
FOURTH_SUNDAY = {"freq": "monthly", "mode": "nth_weekday", "nth": 4, "weekday": 6}


@pytest.fixture(autouse=True)
def _wiring(ws, monkeypatch):
    services.set_flags(ws.id, {"ext.recurrence": True})
    monkeypatch.setattr(recurring, "_announce", lambda rule, issue: None)  # Celery side effects
    monkeypatch.setattr(tasks.spawn_recurrence, "delay", lambda *a: tasks.spawn_recurrence.run(*a))


@pytest.fixture
def done(project):
    return State.objects.create(name="Delivered", group="completed", project=project, workspace=project.workspace)


@pytest.fixture
def todo(project):
    return State.objects.create(
        name="To Do", group="unstarted", project=project, workspace=project.workspace, default=True
    )


@pytest.fixture
def item(issue, people, project, todo):
    issue.target_date, issue.start_date = D(2026, 11, 22), D(2026, 11, 19)
    issue.save()
    IssueAssignee.objects.create(issue=issue, assignee=people["member"], project=project, workspace=project.workspace)
    label = Label.objects.create(name="type:recurring", project=project, workspace=project.workspace)
    IssueLabel.objects.create(issue=issue, label=label, project=project, workspace=project.workspace)
    module = Module.objects.create(name="General Ledger", project=project, workspace=project.workspace)
    ModuleIssue.objects.create(issue=issue, module=module, project=project, workspace=project.workspace)
    IssueLink.objects.create(issue=issue, url="https://example.com/close", project=project, workspace=project.workspace)
    return issue


def _complete(issue, state, user, capture):
    issue.refresh_from_db()
    issue.state = state
    with impersonate(user), capture(execute=True):
        issue.save()


def _url(base, project, issue):
    return f"{base}/projects/{project.id}/work-items/{issue.id}/recurrence/"


def test_put_creates_rule_and_get_summarises(client_for, people, base, project, item):
    r = client_for(people["member"]).put(_url(base, project, item), {"schedule": FOURTH_SUNDAY}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["summary"] == "Monthly · 4th Sunday" and r.data["next_due"] == "2026-12-27"
    got = client_for(people["guest"]).get(_url(base, project, item)).data
    assert got["trigger"] == "completed" and got["create_new"] is True


def test_guest_cannot_edit_and_flag_gates(client_for, people, base, project, item, ws):
    assert (
        client_for(people["guest"])
        .put(_url(base, project, item), {"schedule": FOURTH_SUNDAY}, format="json")
        .status_code
        == 403
    )
    services.set_flags(ws.id, {"ext.recurrence": False})
    assert client_for(people["member"]).get(_url(base, project, item)).status_code == 404


def test_item_without_due_date_gets_first_occurrence(people, issue):
    rule = recurring.upsert(issue, people["member"], {"schedule": {"freq": "monthly", "mode": "first_day"}})
    issue.refresh_from_db()
    assert issue.target_date.day == 1 and issue.target_date >= timezone.localdate() and rule.anchor == issue.target_date


def test_completion_creates_the_next_item_with_selected_fields(
    people, project, item, done, todo, django_capture_on_commit_callbacks
):
    ExtPropertyValue.objects.create(definition_id=_frequency(project), issue=item, value_text="close")
    child = Issue.objects.create(
        name="Bank recs",
        project=project,
        workspace=project.workspace,
        parent=item,
        target_date=D(2026, 11, 20),
        state=todo,
    )
    rule = recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY})
    _complete(item, done, people["member"], django_capture_on_commit_callbacks)
    rule.refresh_from_db()
    new = rule.current_issue
    assert new.id != item.id and new.name == item.name and new.state_id == todo.id
    assert (new.target_date, new.start_date) == (D(2026, 12, 27), D(2026, 12, 24))  # start offset kept
    assert list(IssueAssignee.objects.filter(issue=new).values_list("assignee_id", flat=True)) == [people["member"].id]
    assert IssueLabel.objects.filter(issue=new).count() == 1 and ModuleIssue.objects.filter(issue=new).count() == 1
    assert IssueLink.objects.filter(issue=new).count() == 1
    assert ExtPropertyValue.objects.get(issue=new).value_text == "close"
    sub = Issue.objects.get(parent=new)
    assert sub.name == "Bank recs" and sub.target_date == D(2026, 12, 25)  # remapped like its parent
    assert Issue.objects.get(id=child.id).parent_id == item.id  # the original stays put
    assert rule.occurrences == 1 and ExtRecurrenceSpawn.objects.get(rule=rule).reason == "completed"


def _frequency(project):
    from plane.ext.models import ExtPropertyDefinition

    return ExtPropertyDefinition.objects.create(workspace=project.workspace, key="note", name="Note", type="text").id


def test_each_period_spawns_once(people, item):
    rule = recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY})
    first = recurring.spawn(rule.id, "completed")
    ExtRecurrenceRule.objects.filter(id=rule.id).update(current_issue=item)  # replay against the old item
    assert first is not None and recurring.spawn(rule.id, "sweep") is None
    assert Issue.issue_objects.filter(name=item.name).count() == 2


def test_copy_options_are_respected(people, item):
    rule = recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY, "copy_fields": ["description"]})
    new = recurring.spawn(rule.id, "completed")
    assert not IssueAssignee.objects.filter(issue=new).exists() and not IssueLabel.objects.filter(issue=new).exists()


def test_reuse_resets_state_and_moves_dates(people, item, done, todo):
    rule = recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY, "create_new": False})
    item.state = done
    item.save()
    assert recurring.spawn(rule.id, "completed").id == item.id
    item.refresh_from_db()
    assert item.state_id == todo.id and (item.start_date, item.target_date) == (D(2026, 12, 24), D(2026, 12, 27))
    rule.refresh_from_db()
    assert rule.anchor == D(2026, 11, 22)  # not re-anchored by its own date move


def test_state_trigger_and_days_after(people, project, item, states, django_capture_on_commit_callbacks):
    rule = recurring.upsert(
        item,
        people["member"],
        {
            "schedule": {"freq": "days_after", "days": 3},
            "trigger": "state",
            "trigger_state_id": str(states["started"].id),
        },
    )
    _complete(item, states["started"], people["member"], django_capture_on_commit_callbacks)
    rule.refresh_from_db()
    assert rule.current_issue.target_date == timezone.localdate() + dt.timedelta(days=3)


def test_schedule_trigger_runs_once_at_run_time(people, item):
    rule = recurring.upsert(
        item, people["member"], {"schedule": {"freq": "daily"}, "trigger": "schedule", "run_time": "06:00"}
    )
    assert rule.next_run_at.date() == D(2026, 11, 22)
    at = rule.next_run_at + dt.timedelta(minutes=1)
    with _today(D(2026, 11, 22)):
        assert recurring.run_due(at) == 1
        assert recurring.run_due(at) == 0  # next run is tomorrow
    rule.refresh_from_db()
    assert rule.current_issue.target_date == D(2026, 11, 23)


def test_schedule_after_downtime_creates_no_past_items(people, item):
    rule = recurring.upsert(item, people["member"], {"schedule": {"freq": "daily"}, "trigger": "schedule"})
    with _today(D(2026, 12, 10)):
        recurring.run_due(timezone.now() + dt.timedelta(days=60))
    rule.refresh_from_db()
    assert rule.current_issue.target_date == D(2026, 12, 10) and rule.occurrences == 1


def test_end_after_count_and_pause_and_skip(people, item):
    rule = recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY, "end_count": 1})
    assert recurring.spawn(rule.id, "completed") is not None
    assert recurring.spawn(rule.id, "completed") is None
    rule.refresh_from_db()
    assert rule.ended_at is not None

    other = Issue.objects.create(
        name="Payroll", project=item.project, workspace=item.workspace, target_date=D(2026, 11, 22)
    )
    r2 = recurring.upsert(other, people["member"], {"schedule": FOURTH_SUNDAY})
    r2.paused = True
    r2.save()
    assert recurring.spawn(r2.id, "completed") is None
    recurring.skip_next(r2)
    other.refresh_from_db()
    assert other.target_date == D(2026, 12, 27)


def test_sweep_catches_bulk_completed_items(people, item, done):
    rule = recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY})
    Issue.objects.filter(id=item.id).update(state=done)  # bulk update: no signal
    assert recurring.run_due() == 1
    rule.refresh_from_db()
    assert rule.current_issue_id != item.id


def test_archived_project_does_not_recur(people, item, project):
    rule = recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY})
    project.archived_at = timezone.now()
    project.save()
    assert recurring.spawn(rule.id, "completed") is None


def test_resync_on_due_date_change(people, item, django_capture_on_commit_callbacks):
    rule = recurring.upsert(
        item,
        people["member"],
        {"schedule": {"freq": "monthly", "mode": "same_day", "day": 22}, "resync_on_due_change": True},
    )
    item.refresh_from_db()
    item.target_date = D(2026, 11, 25)
    with impersonate(people["member"]):
        item.save()
    rule.refresh_from_db()
    assert rule.schedule["day"] == 25 and rule.anchor == D(2026, 11, 25)


def test_overview_respects_project_membership(client_for, people, base, project, item):
    recurring.upsert(item, people["member"], {"schedule": FOURTH_SUNDAY})
    assert len(client_for(people["member"]).get(f"{base}/recurrence/").data) == 1
    ProjectMember.objects.filter(project=project, member=people["member"]).update(is_active=False)
    assert client_for(people["member"]).get(f"{base}/recurrence/").data == []
    assert client_for(people["guest"]).get(f"{base}/projects/{project.id}/recurrence/").data == {
        str(item.id): "Monthly · 4th Sunday"
    }


def test_validation_errors(client_for, people, base, project, item):
    member = client_for(people["member"])
    assert member.put(_url(base, project, item), {"schedule": {"freq": "hourly"}}, format="json").status_code == 400
    bad = {"schedule": {"freq": "days_after", "days": 2}, "trigger": "schedule"}
    assert member.put(_url(base, project, item), bad, format="json").status_code == 400
    assert (
        member.put(
            _url(base, project, item), {"schedule": FOURTH_SUNDAY, "trigger": "state"}, format="json"
        ).status_code
        == 400
    )


class _today:
    """Freeze timezone.localdate() for the downtime/next-run logic."""

    def __init__(self, day):
        self.day = day

    def __enter__(self):
        import plane.ext.recurring as mod

        self._orig = mod.timezone.localdate
        mod.timezone.localdate = lambda *a, **k: self.day
        return self

    def __exit__(self, *exc):
        import plane.ext.recurring as mod

        mod.timezone.localdate = self._orig


def test_rule_actions_and_stop(client_for, people, base, project, item):
    member = client_for(people["member"])
    rule = member.put(_url(base, project, item), {"schedule": FOURTH_SUNDAY}, format="json").data
    act = lambda name: member.post(f"{base}/recurrence/{rule['id']}/{name}/")  # noqa: E731
    assert act("pause").data["paused"] is True
    assert act("resume").data["paused"] is False
    assert act("skip").data["due"] == "2026-12-27"
    assert act("bogus").status_code == 400
    assert client_for(people["guest"]).post(f"{base}/recurrence/{rule['id']}/pause/").status_code == 403
    assert member.delete(_url(base, project, item)).status_code == 204
    assert member.get(_url(base, project, item)).data is None
    assert act("pause").status_code == 404  # ended series


def test_repeats_column_preference_round_trips(client_for, people, base, project):
    from plane.ext.views import REPEATS_COLUMN_ID

    url = f"{base}/projects/{project.id}/columns/"
    assert client_for(people["guest"]).put(url, {"definition_ids": [REPEATS_COLUMN_ID]}, format="json").data == {
        "definition_ids": [REPEATS_COLUMN_ID]
    }
