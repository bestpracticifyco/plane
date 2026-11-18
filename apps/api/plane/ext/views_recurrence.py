# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Recurring work items API (flag ext.recurrence). Project Members edit; Guests read."""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.db.models import ProjectMember

from . import recurrence, recurring
from .models import ExtRecurrenceRule
from .views import ADMIN, GUEST, MEMBER, ExtBaseView


class RecurrenceBase(ExtBaseView):
    flag = "ext.recurrence"


class ItemRecurrenceEndpoint(RecurrenceBase):
    def get(self, request, slug, project_id, issue_id):
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        rule = recurring.live_rule(self.issue(ws, project_id, issue_id))
        return Response(recurring.rule_json(rule) if rule else None)

    def put(self, request, slug, project_id, issue_id):
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, MEMBER)
        rule = recurring.upsert(self.issue(ws, project_id, issue_id), request.user, request.data)
        return Response(recurring.rule_json(rule))

    def delete(self, request, slug, project_id, issue_id):
        """'Don't repeat': ends the series; items already created stay."""
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, MEMBER)
        rule = recurring.live_rule(self.issue(ws, project_id, issue_id))
        if rule:
            recurring.stop(rule)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectRecurrenceEndpoint(RecurrenceBase):
    """issue_id -> short summary, for the 'Repeats' list/spreadsheet column."""

    def get(self, request, slug, project_id):
        self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        rules = ExtRecurrenceRule.objects.filter(
            project_id=project_id, ended_at__isnull=True, current_issue__isnull=False
        )
        return Response(
            {str(r.current_issue_id): ("Paused · " if r.paused else "") + recurrence.summary(r.schedule) for r in rules}
        )


class WorkspaceRecurrenceEndpoint(RecurrenceBase):
    """The 'Recurring' overview: live series in projects the caller belongs to (Admins: all)."""

    def get(self, request, slug):
        ws = self.workspace(slug)
        role = self.require_workspace_role(slug, GUEST)
        qs = ExtRecurrenceRule.objects.filter(workspace=ws, ended_at__isnull=True).select_related(
            "current_issue", "project", "workspace"
        )
        if role < ADMIN:
            mine = ProjectMember.objects.filter(member=request.user, workspace=ws, is_active=True).values("project_id")
            qs = qs.filter(project_id__in=mine)
        if request.query_params.get("project_id"):
            qs = qs.filter(project_id=request.query_params["project_id"])
        rows = []
        for r in qs.order_by("project__identifier", "current_issue__target_date"):
            row = recurring.rule_json(r)
            row["project_identifier"] = r.project.identifier
            rows.append(row)
        return Response(rows)


class RuleActionEndpoint(RecurrenceBase):
    ACTIONS = {"pause", "resume", "skip", "stop"}

    def post(self, request, slug, pk, action):
        ws = self.workspace(slug)
        rule = get_object_or_404(
            ExtRecurrenceRule.objects.select_related("current_issue", "workspace"),
            id=pk,
            workspace=ws,
            ended_at__isnull=True,
        )
        self.require_project_role(slug, rule.project_id, MEMBER)
        if action not in self.ACTIONS:
            raise ValidationError({"action": [f"one of {', '.join(sorted(self.ACTIONS))}"]})
        if action == "stop":
            recurring.stop(rule)
            return Response(status=status.HTTP_204_NO_CONTENT)
        if action == "skip":
            recurring.skip_next(rule)
        else:
            rule.paused = action == "pause"
            rule.save(update_fields=["paused", "updated_at"])
        rule.refresh_from_db()
        return Response(recurring.rule_json(rule))
