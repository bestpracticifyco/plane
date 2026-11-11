# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""plane_ext data model (PRD Appendix C).

Sidecar tables only: every foreign key points into Plane's tables and none adds a column to them.
All models inherit Plane's BaseModel (UUID pk, audit fields, soft delete).
"""

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
