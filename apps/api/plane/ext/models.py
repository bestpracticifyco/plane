# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""plane_ext data model (PRD Appendix C).

Sidecar tables only: every foreign key points into Plane's tables and none adds a column to them.
All models inherit Plane's BaseModel (UUID pk, audit fields, soft delete).
"""

import datetime as dt

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from plane.db.models import BaseModel


class PropertyType(models.TextChoices):
    DROPDOWN = "dropdown", "Dropdown"
    TEXT = "text", "Text"
    DATE = "date", "Date"
    MEMBER = "member", "Member"
    DATETIME = "datetime", "Date-time"


MULTI_CAPABLE_TYPES = {PropertyType.DROPDOWN, PropertyType.MEMBER}


class ExtPropertyDefinition(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="ext_property_definitions")
    name = models.CharField(max_length=120)
    key = models.SlugField(max_length=64)
    description = models.TextField(blank=True, default="")
    help_text = models.CharField(max_length=255, blank=True, default="")
    type = models.CharField(max_length=16, choices=PropertyType.choices)
    is_multi = models.BooleanField(default=False)
    is_required = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True)
    sort_order = models.FloatField(default=65535)
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "plane_ext_property_definitions"
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "key"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_definition_unique_workspace_key",
            )
        ]
        indexes = [models.Index(fields=["workspace", "is_archived"], name="plane_ext_def_ws_archived")]


class ExtPropertyOption(BaseModel):
    definition = models.ForeignKey(ExtPropertyDefinition, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=120)
    color = models.CharField(max_length=16, blank=True, default="")
    sort_order = models.FloatField(default=65535)
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "plane_ext_property_options"
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "name"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_option_unique_definition_name",
            )
        ]


class ExtProjectBinding(BaseModel):
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="ext_bindings")
    definition = models.ForeignKey(ExtPropertyDefinition, on_delete=models.CASCADE, related_name="bindings")
    sort_order = models.FloatField(default=65535)
    is_enabled = models.BooleanField(default=True)
    show_on_card = models.BooleanField(default=False)

    class Meta:
        db_table = "plane_ext_project_bindings"
        ordering = ("sort_order",)
        constraints = [
            models.UniqueConstraint(
                fields=["project", "definition"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_binding_unique_project_definition",
            )
        ]


class ExtPropertyValue(BaseModel):
    definition = models.ForeignKey(ExtPropertyDefinition, on_delete=models.CASCADE, related_name="values")
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="ext_values")
    value_text = models.TextField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    option_ids = ArrayField(models.UUIDField(), default=list, blank=True)
    member_ids = ArrayField(models.UUIDField(), default=list, blank=True)

    class Meta:
        db_table = "plane_ext_property_values"
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "issue"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_value_unique_definition_issue",
            )
        ]
        indexes = [
            models.Index(fields=["issue"], name="plane_ext_value_issue"),
            GinIndex(fields=["option_ids"], name="plane_ext_value_option_gin"),
            GinIndex(fields=["member_ids"], name="plane_ext_value_member_gin"),
        ]


class ExtActivity(BaseModel):
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="ext_activity")
    definition = models.ForeignKey(ExtPropertyDefinition, on_delete=models.CASCADE, related_name="activity")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ext_activity"
    )
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "plane_ext_activity"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["issue", "created_at"], name="plane_ext_activity_issue_ts")]


class ExtFeatureFlag(BaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="ext_feature_flags")
    key = models.CharField(max_length=64)
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "plane_ext_feature_flags"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "key"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_flag_unique_workspace_key",
            )
        ]


class ExtColumnPreference(BaseModel):
    """Which ext properties a user shows as List/Spreadsheet columns in a project (FR-EXT-021)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ext_column_prefs")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="ext_column_prefs")
    definition_ids = ArrayField(models.UUIDField(), default=list, blank=True)

    class Meta:
        db_table = "plane_ext_column_preferences"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "project"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_colpref_unique_user_project",
            )
        ]


class ExtHandoffToken(BaseModel):
    """Issuance record of short-lived tokens handed to embedded Governor pages (FR-EXT-061)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ext_handoff_tokens")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="ext_handoff_tokens")
    jti = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "plane_ext_handoff_tokens"


class ExtPendingProjectGrant(BaseModel):
    """Projects a person should land in when they join the workspace (access matrix "invite to projects").

    Plane CE invites carry only a workspace role; these rows are applied when the WorkspaceMember appears
    (signal for .create(), periodic sweep for upstream's bulk_create join paths) and then deleted.
    """

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="ext_pending_grants")
    email = models.CharField(max_length=255)
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="ext_pending_grants")
    role = models.PositiveSmallIntegerField(default=15)

    class Meta:
        db_table = "plane_ext_pending_project_grants"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "email", "project"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_grant_unique_email_project",
            )
        ]


class ExtAccessLog(BaseModel):
    """Every project-membership change made through the access matrix (who, what, before, after)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="ext_access_log")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="ext_access_log")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ext_access_changes")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ext_access_actions"
    )
    old_role = models.PositiveSmallIntegerField(null=True)
    new_role = models.PositiveSmallIntegerField(null=True)

    class Meta:
        db_table = "plane_ext_access_log"
        ordering = ("-created_at",)


class RecurrenceTrigger(models.TextChoices):
    COMPLETED = "completed", "When completed"
    STATE = "state", "When it reaches a state"
    SCHEDULE = "schedule", "On schedule"


COPY_FIELDS = (
    "description",
    "assignees",
    "labels",
    "modules",
    "cycle",
    "priority",
    "estimate",
    "properties",
    "sub_items",
    "sub_item_assignees",
    "remap_sub_item_dates",
    "links",
    "subscribers",
    "parent",
)


def default_copy_fields():
    return list(COPY_FIELDS)


class ExtRecurrenceRule(BaseModel):
    """One repeating series. `current_issue` is the live instance; spawning moves it forward."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="ext_recurrence_rules")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="ext_recurrence_rules")
    current_issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, related_name="ext_recurrence")
    schedule = models.JSONField()  # see plane.ext.recurrence
    anchor = models.DateField()  # first due date of the series; fixes interval phase
    trigger = models.CharField(max_length=16, choices=RecurrenceTrigger.choices, default=RecurrenceTrigger.COMPLETED)
    trigger_state = models.ForeignKey("db.State", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    create_new = models.BooleanField(default=True)  # False: reuse the same item (reset state, move dates)
    new_state = models.ForeignKey("db.State", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    copy_fields = ArrayField(models.CharField(max_length=32), default=default_copy_fields, blank=True)
    end_count = models.PositiveIntegerField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    occurrences = models.PositiveIntegerField(default=0)
    resync_on_due_change = models.BooleanField(default=False)
    run_time = models.TimeField(default=dt.time(6, 0))  # workspace timezone
    next_run_at = models.DateTimeField(null=True, blank=True)  # schedule trigger only
    paused = models.BooleanField(default=False)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_spawned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "plane_ext_recurrence_rules"
        constraints = [
            models.UniqueConstraint(
                fields=["current_issue"],
                condition=Q(deleted_at__isnull=True, ended_at__isnull=True),
                name="plane_ext_recurrence_one_live_rule_per_item",
            )
        ]
        indexes = [models.Index(fields=["trigger", "next_run_at"], name="plane_ext_recur_due")]


class ExtRecurrenceSpawn(BaseModel):
    """Idempotency record: one row per (rule, period). A re-run for the same period is a no-op."""

    rule = models.ForeignKey(ExtRecurrenceRule, on_delete=models.CASCADE, related_name="spawns")
    period_key = models.CharField(max_length=32)  # the new due date, ISO
    issue = models.ForeignKey("db.Issue", on_delete=models.SET_NULL, null=True, related_name="+")
    reason = models.CharField(max_length=16)  # completed | state | schedule | sweep

    class Meta:
        db_table = "plane_ext_recurrence_spawns"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "period_key"],
                condition=Q(deleted_at__isnull=True),
                name="plane_ext_recurrence_spawn_once",
            )
        ]
