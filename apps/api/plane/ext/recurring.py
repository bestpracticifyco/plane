# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Recurring work items: rule upkeep and spawning the next instance (flag ext.recurrence).

Triggers
  completed  the current item moves into a Completed-group state -> next instance now
  state      the current item moves into `trigger_state`        -> next instance now
  schedule   at `run_time` (workspace timezone) on the current item's due date -> next instance,
             whatever the current item's state; completing it earlier spawns immediately.
Each (rule, new due date) spawns at most once (ExtRecurrenceSpawn), so signals, the 5-minute tick
and retries can all call spawn() safely. New items go through Plane's IssueCreateSerializer and
fire the same activity/webhook tasks as the issue-create view, so the Governor sees them.
"""

import datetime as dt
import json
import logging
import zoneinfo

from crum import impersonate
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from plane.db.models import (
    Cycle,
    CycleIssue,
    Issue,
    IssueAssignee,
    IssueLabel,
    IssueLink,
    IssueSubscriber,
    ModuleIssue,
    State,
)

from . import recurrence
from .models import (
    COPY_FIELDS,
    ExtPropertyValue,
    ExtRecurrenceRule,
    ExtRecurrenceSpawn,
    RecurrenceTrigger,
)

log = logging.getLogger("plane.ext.recurring")
EDITABLE = (
    "schedule",
    "trigger",
    "trigger_state_id",
    "create_new",
    "new_state_id",
    "copy_fields",
    "end_count",
    "end_date",
    "resync_on_due_change",
    "run_time",
)


# ---------------------------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------------------------
def rule_json(r):
    issue = r.current_issue
    return {
        "id": str(r.id),
        "project_id": str(r.project_id),
        "issue_id": str(r.current_issue_id) if r.current_issue_id else None,
        "issue_name": issue.name if issue else None,
        "issue_sequence_id": issue.sequence_id if issue else None,
        "due": issue.target_date.isoformat() if issue and issue.target_date else None,
        "schedule": r.schedule,
        "summary": recurrence.summary(r.schedule),
        "anchor": r.anchor.isoformat(),
        "trigger": r.trigger,
        "trigger_state_id": str(r.trigger_state_id) if r.trigger_state_id else None,
        "create_new": r.create_new,
        "new_state_id": str(r.new_state_id) if r.new_state_id else None,
        "copy_fields": list(r.copy_fields),
        "end_count": r.end_count,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "occurrences": r.occurrences,
        "resync_on_due_change": r.resync_on_due_change,
        "run_time": r.run_time.strftime("%H:%M"),
        "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None,
        "next_due": _safe_next_due(r),
        "paused": r.paused,
        "last_spawned_at": r.last_spawned_at.isoformat() if r.last_spawned_at else None,
        "created_by": str(r.created_by_id) if r.created_by_id else None,
    }


def _safe_next_due(r):
    if r.schedule.get("freq") == "days_after" or not r.current_issue or not r.current_issue.target_date:
        return None
    try:
        return recurrence.next_after(r.schedule, r.current_issue.target_date, r.anchor).isoformat()
    except recurrence.ScheduleError:
        return None


# ---------------------------------------------------------------------------------------------
# Create / update / stop
# ---------------------------------------------------------------------------------------------
def _clean(issue, data, rule=None):
    out = {}
    for key in EDITABLE:
        if key in data:
            out[key] = data[key]
    if "schedule" in out or rule is None:
        try:
            out["schedule"] = recurrence.validate(data.get("schedule"))
        except recurrence.ScheduleError as e:
            raise ValidationError({"schedule": [str(e)]})
    if out.get("trigger", RecurrenceTrigger.COMPLETED) not in RecurrenceTrigger.values:
        raise ValidationError({"trigger": ["must be completed, state or schedule"]})
    for key in ("trigger_state_id", "new_state_id"):
        if out.get(key) and not State.objects.filter(id=out[key], project_id=issue.project_id).exists():
            raise ValidationError({key: ["not a state of this project"]})
    trigger = out.get("trigger", rule.trigger if rule else RecurrenceTrigger.COMPLETED)
    if trigger == RecurrenceTrigger.STATE and not out.get("trigger_state_id", rule and rule.trigger_state_id):
        raise ValidationError({"trigger_state_id": ["required when the trigger is a state"]})
    schedule = out.get("schedule", rule.schedule if rule else None)
    if trigger == RecurrenceTrigger.SCHEDULE and schedule and schedule["freq"] == "days_after":
        raise ValidationError({"trigger": ["'days after completion' repeats on completion, not on a schedule"]})
    if "copy_fields" in out:
        bad = sorted(set(out["copy_fields"]) - set(COPY_FIELDS))
        if bad:
            raise ValidationError({"copy_fields": [f"unknown: {', '.join(bad)}"]})
    if out.get("run_time"):
        try:
            out["run_time"] = dt.time.fromisoformat(str(out["run_time"]))
        except ValueError:
            raise ValidationError({"run_time": ["HH:MM expected"]})
    if out.get("end_date"):
        try:
            out["end_date"] = dt.date.fromisoformat(str(out["end_date"]))
        except ValueError:
            raise ValidationError({"end_date": ["YYYY-MM-DD expected"]})
    if out.get("end_count") is not None and int(out["end_count"]) < 1:
        raise ValidationError({"end_count": ["must be at least 1"]})
    return out


def upsert(issue, user, data):
    """Create or update the live rule for `issue`. An item without a due date gets the first
    occurrence from today as its due date (ClickUp: recurrence runs off the due date)."""
    rule = live_rule(issue)
    fields = _clean(issue, data, rule)
    with transaction.atomic():
        if issue.target_date is None:
            first = recurrence.first_on_or_after(fields.get("schedule") or rule.schedule, timezone.localdate())
            if fields.get("schedule", {}).get("freq") == "days_after":
                first = timezone.localdate()
            issue.target_date = first
            with impersonate(user):
                issue.save(update_fields=["target_date", "updated_at", "updated_by"])
        if rule is None:
            rule = ExtRecurrenceRule(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                current_issue=issue,
                anchor=issue.target_date,
            )
        for key, value in fields.items():
            setattr(rule, key, value)
        if "schedule" in fields:
            rule.anchor = issue.target_date
        rule.next_run_at = _run_at(rule, issue.target_date) if rule.trigger == RecurrenceTrigger.SCHEDULE else None
        with impersonate(user):
            rule.save()
    return rule


def live_rule(issue):
    return (
        ExtRecurrenceRule.objects.filter(current_issue=issue, ended_at__isnull=True)
        .select_related("current_issue")
        .first()
    )


def stop(rule):
    rule.ended_at = timezone.now()
    rule.next_run_at = None
    rule.save(update_fields=["ended_at", "next_run_at", "updated_at"])


def skip_next(rule):
    """Move the live item to the following period without creating anything."""
    issue = rule.current_issue
    if issue is None or issue.target_date is None or rule.schedule["freq"] == "days_after":
        raise ValidationError({"rule": ["nothing to skip"]})
    new_due = recurrence.next_after(rule.schedule, issue.target_date, rule.anchor)
    _move_dates(issue, new_due)
    issue._ext_spawning = True
    issue.save(update_fields=["start_date", "target_date", "updated_at"])
    if rule.trigger == RecurrenceTrigger.SCHEDULE:
        rule.next_run_at = _run_at(rule, new_due)
        rule.save(update_fields=["next_run_at", "updated_at"])


def on_due_date_changed(issue):
    """'Sync recurrence to due date': the schedule follows a manual due-date change."""
    rule = live_rule(issue)
    if rule is None or not rule.resync_on_due_change or issue.target_date is None:
        return
    rule.anchor = issue.target_date
    if rule.schedule.get("freq") == "monthly" and rule.schedule.get("mode") == "same_day":
        rule.schedule = {**rule.schedule, "day": issue.target_date.day}
    if rule.schedule.get("freq") == "weekly" and len(rule.schedule.get("weekdays", [])) == 1:
        rule.schedule = {**rule.schedule, "weekdays": [issue.target_date.weekday()]}
    if rule.trigger == RecurrenceTrigger.SCHEDULE:
        rule.next_run_at = _run_at(rule, issue.target_date)
    rule.save(update_fields=["anchor", "schedule", "next_run_at", "updated_at"])


# ---------------------------------------------------------------------------------------------
# Spawning
# ---------------------------------------------------------------------------------------------
def _tz(rule):
    try:
        return zoneinfo.ZoneInfo(rule.workspace.timezone or "UTC")
    except zoneinfo.ZoneInfoNotFoundError:
        return zoneinfo.ZoneInfo("UTC")


def _run_at(rule, due):
    return dt.datetime.combine(due, rule.run_time, tzinfo=_tz(rule))


def _move_dates(issue, new_due, old_due=None):
    old_due = old_due or issue.target_date
    if issue.start_date and old_due:
        issue.start_date = new_due - (old_due - issue.start_date)
    issue.target_date = new_due


def _is_done(issue):
    return issue.state_id and State.all_state_objects.filter(id=issue.state_id, group="completed").exists()


def trigger_matches(rule, issue):
    if rule.trigger == RecurrenceTrigger.STATE:
        return issue.state_id is not None and issue.state_id == rule.trigger_state_id
    return bool(_is_done(issue))  # completed, and early completion of a schedule item


def spawn(rule_id, reason, completed_on=None):
    """Create (or reuse) the next instance of a series. Returns the new live issue or None."""
    with transaction.atomic():
        rule = (
            ExtRecurrenceRule.objects.select_for_update(of=("self",))
            .select_related("current_issue", "workspace", "project", "created_by")
            .filter(id=rule_id, ended_at__isnull=True)
            .first()
        )
        if rule is None or rule.paused:
            return None
        cur = rule.current_issue
        if cur is None or cur.deleted_at or cur.archived_at or rule.project.archived_at:
            return None
        base = cur.target_date or rule.anchor
        if rule.schedule["freq"] == "days_after":
            new_due = (completed_on or timezone.localdate()) + dt.timedelta(days=rule.schedule["days"])
        else:
            new_due = recurrence.next_after(rule.schedule, base, rule.anchor)
            if rule.trigger == RecurrenceTrigger.SCHEDULE:  # after downtime: no instances in the past
                today = timezone.localdate(timezone=_tz(rule))
                while new_due < today:
                    new_due = recurrence.next_after(rule.schedule, new_due, rule.anchor)
        if (rule.end_date and new_due > rule.end_date) or (rule.end_count and rule.occurrences >= rule.end_count):
            rule.ended_at = timezone.now()
            rule.next_run_at = None
            rule.save(update_fields=["ended_at", "next_run_at", "updated_at"])
            return None
        try:
            with transaction.atomic():
                record = ExtRecurrenceSpawn.objects.create(rule=rule, period_key=new_due.isoformat(), reason=reason)
        except IntegrityError:
            return None  # this period was already spawned
        with impersonate(rule.created_by):
            new = _copy(rule, cur, new_due) if rule.create_new else _reuse(rule, cur, new_due)
        record.issue = new
        record.save(update_fields=["issue", "updated_at"])
        rule.current_issue = new
        rule.occurrences += 1
        rule.last_spawned_at = timezone.now()
        rule.next_run_at = _run_at(rule, new_due) if rule.trigger == RecurrenceTrigger.SCHEDULE else None
        rule.save(update_fields=["current_issue", "occurrences", "last_spawned_at", "next_run_at", "updated_at"])
        if rule.create_new:
            transaction.on_commit(lambda: _announce(rule, new))
    return new


def _reuse(rule, issue, new_due):
    state_id = rule.new_state_id or _default_state_id(issue.project_id)
    _move_dates(issue, new_due)
    issue.state_id = state_id
    issue._ext_spawning = True  # not a manual due-date change: no re-anchoring
    issue.save()
    return issue


def _default_state_id(project_id):
    return (
        State.objects.filter(project_id=project_id, default=True).values_list("id", flat=True).first()
        or State.objects.filter(project_id=project_id, group="backlog").values_list("id", flat=True).first()
    )


def _copy(rule, src, new_due, parent_id=None, old_due=None):
    """Copy `src` to a new item due `new_due`, with the fields the rule selects."""
    from plane.app.serializers import IssueCreateSerializer

    want = set(rule.copy_fields)
    old_due = old_due or src.target_date
    start = (new_due - (old_due - src.start_date)) if (src.start_date and old_due) else None
    data = {
        "name": src.name,
        "state_id": str(rule.new_state_id or _default_state_id(src.project_id)),
        "target_date": new_due.isoformat(),
        "start_date": start.isoformat() if start else None,
        "description_html": src.description_html if "description" in want else "<p></p>",
        "priority": src.priority if "priority" in want else "none",
    }
    if "estimate" in want and src.estimate_point_id:
        data["estimate_point"] = str(src.estimate_point_id)
    if parent_id:
        data["parent_id"] = str(parent_id)
    elif "parent" in want and src.parent_id:
        data["parent_id"] = str(src.parent_id)
    top_level = parent_id is None
    if "assignees" in want if top_level else "sub_item_assignees" in want:
        data["assignee_ids"] = [
            str(a) for a in IssueAssignee.objects.filter(issue=src).values_list("assignee_id", flat=True)
        ]
    if "labels" in want:
        data["label_ids"] = [str(x) for x in IssueLabel.objects.filter(issue=src).values_list("label_id", flat=True)]
    serializer = IssueCreateSerializer(
        data=data,
        context={"project_id": src.project_id, "workspace_id": src.workspace_id, "default_assignee_id": None},
    )
    serializer.is_valid(raise_exception=True)
    new = serializer.save()
    project_id, workspace_id = src.project_id, src.workspace_id
    if "modules" in want:
        ModuleIssue.objects.bulk_create(
            [
                ModuleIssue(module_id=m, issue=new, project_id=project_id, workspace_id=workspace_id)
                for m in ModuleIssue.objects.filter(issue=src, module__archived_at__isnull=True).values_list(
                    "module_id", flat=True
                )
            ],
            ignore_conflicts=True,
        )
    if "cycle" in want and top_level:
        cycle = Cycle.objects.filter(
            project_id=project_id, start_date__date__lte=new_due, end_date__date__gte=new_due, archived_at__isnull=True
        ).first()
        if cycle:
            CycleIssue.objects.create(cycle=cycle, issue=new, project_id=project_id, workspace_id=workspace_id)
    if "links" in want:
        IssueLink.objects.bulk_create(
            [
                IssueLink(
                    issue=new,
                    title=x.title,
                    url=x.url,
                    metadata=x.metadata,
                    project_id=project_id,
                    workspace_id=workspace_id,
                )
                for x in IssueLink.objects.filter(issue=src)
            ]
        )
    if "subscribers" in want:
        IssueSubscriber.objects.bulk_create(
            [
                IssueSubscriber(issue=new, subscriber_id=s, project_id=project_id, workspace_id=workspace_id)
                for s in IssueSubscriber.objects.filter(issue=src).values_list("subscriber_id", flat=True)
            ],
            ignore_conflicts=True,
        )
    if "properties" in want:
        for v in ExtPropertyValue.objects.filter(issue=src, definition__is_archived=False):
            ExtPropertyValue.objects.create(
                definition_id=v.definition_id,
                issue=new,
                value_text=v.value_text,
                value_date=v.value_date,
                value_datetime=v.value_datetime,
                option_ids=v.option_ids,
                member_ids=v.member_ids,
            )
    if "sub_items" in want and top_level:
        for child in Issue.issue_objects.filter(parent=src).order_by("sequence_id"):
            if child.target_date and "remap_sub_item_dates" in want and src.target_date:
                child_due = new_due + (child.target_date - src.target_date)
            else:
                child_due = child.target_date
            if child_due is None:
                child_due = new_due
            _copy(rule, child, child_due, parent_id=new.id, old_due=child.target_date or child_due)
    return new


def _announce(rule, issue):
    """The issue-create view's side effects: activity feed, notifications, webhooks (Governor)."""
    from plane.bgtasks.issue_activities_task import issue_activity
    from plane.bgtasks.webhook_task import model_activity

    actor = str(rule.created_by_id) if rule.created_by_id else None
    payload = {"name": issue.name, "source": "plane_ext.recurrence", "rule_id": str(rule.id)}
    origin = getattr(settings, "WEB_URL", None)
    issue_activity.delay(
        type="issue.activity.created",
        requested_data=json.dumps(payload, cls=DjangoJSONEncoder),
        actor_id=actor,
        issue_id=str(issue.id),
        project_id=str(issue.project_id),
        current_instance=None,
        epoch=int(timezone.now().timestamp()),
        notification=True,
        origin=origin,
    )
    model_activity.delay(
        model_name="issue",
        model_id=str(issue.id),
        requested_data=payload,
        current_instance=None,
        actor_id=actor,
        slug=rule.workspace.slug,
        origin=origin,
    )


# ---------------------------------------------------------------------------------------------
# Periodic sweep (plane.ext.tasks.tick)
# ---------------------------------------------------------------------------------------------
def due_rules(now=None):
    """Schedule rules whose run time has passed, plus completion rules whose live item is already
    done (state changed by a bulk update, which sends no signal)."""
    from plane.ext.services import is_enabled

    now = now or timezone.now()
    out = []
    live = ExtRecurrenceRule.objects.filter(ended_at__isnull=True, paused=False).select_related("current_issue")
    for r in live.filter(trigger=RecurrenceTrigger.SCHEDULE, next_run_at__lte=now):
        if is_enabled(r.workspace_id, "ext.recurrence"):
            out.append((r.id, "schedule"))
    for r in live.exclude(trigger=RecurrenceTrigger.SCHEDULE).exclude(current_issue__isnull=True):
        if is_enabled(r.workspace_id, "ext.recurrence") and trigger_matches(r, r.current_issue):
            out.append((r.id, "sweep"))
    return out


def run_due(now=None):
    spawned = 0
    for rule_id, reason in due_rules(now):
        try:
            spawned += int(spawn(rule_id, reason) is not None)
        except Exception:  # noqa: BLE001 — one bad rule must not stop the others
            log.exception("plane_ext recurrence spawn failed", extra={"rule_id": str(rule_id)})
    return spawned
