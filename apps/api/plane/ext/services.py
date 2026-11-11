# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Validation, value writes, feature flags and role lookups for plane_ext."""

import datetime as dt
import uuid

from django.core.cache import cache
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError

from plane.db.models import ProjectMember, WorkspaceMember

from .models import (
    MULTI_CAPABLE_TYPES,
    ExtActivity,
    ExtFeatureFlag,
    ExtProjectBinding,
    ExtPropertyDefinition,
    ExtPropertyValue,
    PropertyType,
)

# ---------------------------------------------------------------------------------------------
# Feature flags (FR-EXT-080/081). A missing row means the default below.
# ---------------------------------------------------------------------------------------------
FLAG_DEFAULTS = {
    "ext.properties": True,
    "ext.sidebar": True,
    "ext.columns": True,
    "ext.embeds": True,
    "ext.footer": True,
    "ext.enforce_required": False,  # blocks leaving Backlog while a required property is empty
    "ext.activity_mirror_comment": False,
}
_FLAG_CACHE_SECONDS = 60


def _flag_cache_key(workspace_id):
    return f"plane_ext:flags:{workspace_id}"


def get_flags(workspace_id):
    cached = cache.get(_flag_cache_key(workspace_id))
    if cached is not None:
        return cached
    flags = dict(FLAG_DEFAULTS)
    for key, enabled in ExtFeatureFlag.objects.filter(workspace_id=workspace_id).values_list("key", "enabled"):
        if key in flags:
            flags[key] = enabled
    cache.set(_flag_cache_key(workspace_id), flags, _FLAG_CACHE_SECONDS)
    return flags


def is_enabled(workspace_id, key):
    return get_flags(workspace_id).get(key, False)


def set_flags(workspace_id, updates):
    unknown = sorted(set(updates) - set(FLAG_DEFAULTS))
    if unknown:
        raise ValidationError({"flags": [f"unknown flag: {k}" for k in unknown]})
    for key, enabled in updates.items():
        ExtFeatureFlag.objects.update_or_create(
            workspace_id=workspace_id, key=key, defaults={"enabled": bool(enabled)}
        )
    cache.delete(_flag_cache_key(workspace_id))
    return get_flags(workspace_id)


# ---------------------------------------------------------------------------------------------
# Roles — Plane CE: Admin 20, Member 15, Guest 5. Workspace admins act as project admins on
# projects they belong to, mirroring plane.app.permissions.base.allow_permission.
# ---------------------------------------------------------------------------------------------
def workspace_role(user, slug):
    return (
        WorkspaceMember.objects.filter(member=user, workspace__slug=slug, is_active=True)
        .values_list("role", flat=True)
        .first()
    )


def project_role(user, slug, project_id):
    role = (
        ProjectMember.objects.filter(member=user, workspace__slug=slug, project_id=project_id, is_active=True)
        .values_list("role", flat=True)
        .first()
    )
    if role is None:
        return None
    if workspace_role(user, slug) == 20:
        return 20
    return role


# ---------------------------------------------------------------------------------------------
# Value validation (FR-EXT-010/011/013)
# ---------------------------------------------------------------------------------------------
def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _uuid_list(values, field):
    out = []
    for v in values:
        try:
            out.append(uuid.UUID(str(v)))
        except (TypeError, ValueError):
            raise ValidationError({field: [f"not a valid id: {v}"]})
    return out


def is_empty(value):
    return value is None or value == "" or value == []


def clean_value(definition, value):
    """Return the typed column values for `value`, or raise ValidationError with field errors."""
    typ = definition.type
    if typ == PropertyType.TEXT:
        if not isinstance(value, str):
            raise ValidationError({"value": ["text expected"]})
        return {"value_text": value}
    if typ == PropertyType.DATE:
        parsed = parse_date(str(value)) if value else None
        if parsed is None:
            raise ValidationError({"value": ["date expected (YYYY-MM-DD)"]})
        return {"value_date": parsed}
    if typ == PropertyType.DATETIME:
        parsed = parse_datetime(str(value)) if value else None
        if parsed is None:
            raise ValidationError({"value": ["date-time expected (ISO 8601)"]})
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return {"value_datetime": parsed}
    if typ == PropertyType.DROPDOWN:
        ids = _uuid_list(_as_list(value), "option_ids")
        if len(ids) > 1 and not definition.is_multi:
            raise ValidationError({"option_ids": ["only one option allowed"]})
        valid = set(definition.options.filter(is_archived=False).values_list("id", flat=True))
        if any(i not in valid for i in ids):
            raise ValidationError({"option_ids": ["unknown option"]})
        return {"option_ids": ids}
    if typ == PropertyType.MEMBER:
        ids = _uuid_list(_as_list(value), "member_ids")
        if len(ids) > 1 and not definition.is_multi:
            raise ValidationError({"member_ids": ["only one member allowed"]})
        members = set(
            WorkspaceMember.objects.filter(
                workspace_id=definition.workspace_id, member_id__in=ids, is_active=True
            ).values_list("member_id", flat=True)
        )
        if any(i not in members for i in ids):
            raise ValidationError({"member_ids": ["not a workspace member"]})
        return {"member_ids": ids}
    raise ValidationError({"type": ["unsupported property type"]})


def serialize_value(row):
    """Public JSON shape of a stored value (also used for activity old/new)."""
    if row is None:
        return None
    typ = row.definition.type
    if typ == PropertyType.TEXT:
        return row.value_text
    if typ == PropertyType.DATE:
        return row.value_date.isoformat() if row.value_date else None
    if typ == PropertyType.DATETIME:
        return row.value_datetime.isoformat() if row.value_datetime else None
    ids = row.option_ids if typ == PropertyType.DROPDOWN else row.member_ids
    ids = [str(i) for i in ids]
    return ids if row.definition.is_multi else (ids[0] if ids else None)


def validate_definition_payload(data, instance=None):
    typ = data.get("type", instance.type if instance else None)
    if typ not in PropertyType.values:
        raise ValidationError({"type": [f"must be one of {', '.join(PropertyType.values)}"]})
    if instance is not None and "type" in data and data["type"] != instance.type and instance.values.exists():
        raise ValidationError({"type": ["cannot change the type of a property that has values"]})
    if data.get("is_multi") and typ not in MULTI_CAPABLE_TYPES:
        raise ValidationError({"is_multi": ["only dropdown and member properties can be multi-valued"]})


# ---------------------------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------------------------
def bound_definitions(project_id):
    return list(
        ExtPropertyDefinition.objects.filter(
            bindings__project_id=project_id,
            bindings__is_enabled=True,
            bindings__deleted_at__isnull=True,
            is_archived=False,
        )
        .order_by("bindings__sort_order")
        .prefetch_related("options")
    )


def issue_is_past_backlog(issue):
    return bool(issue.state_id) and issue.state.group not in ("backlog", "triage")


def write_value(issue, definition, value, actor):
    """Set or clear one value with an activity row. Clearing deletes the row (FR-EXT-013)."""
    if not ExtProjectBinding.objects.filter(
        project_id=issue.project_id, definition=definition, is_enabled=True
    ).exists():
        raise ValidationError({"definition_id": ["property is not bound to this project"]})
    with transaction.atomic():
        row = (
            ExtPropertyValue.objects.select_for_update()
            .select_related("definition")
            .filter(issue=issue, definition=definition)
            .first()
        )
        old = serialize_value(row)
        if is_empty(value):
            if definition.is_required and issue_is_past_backlog(issue):
                raise ValidationError({"value": [f"'{definition.name}' is required once work has started"]})
            if row is None:
                return None
            row.delete(soft=False)
            ExtActivity.objects.create(issue=issue, definition=definition, actor=actor, old_value=old, new_value=None)
            return None
        cols = clean_value(definition, value)
        if row is None:
            row = ExtPropertyValue(issue=issue, definition=definition)
        for field in ("value_text", "value_date", "value_datetime"):
            setattr(row, field, None)
        row.option_ids, row.member_ids = [], []
        for field, v in cols.items():
            setattr(row, field, v)
        row.save()
        new = serialize_value(row)
        if new != old:
            ExtActivity.objects.create(issue=issue, definition=definition, actor=actor, old_value=old, new_value=new)
        return row


def missing_required(issue):
    """Names of required bound properties with no value on `issue`."""
    required = [d for d in bound_definitions(issue.project_id) if d.is_required]
    if not required:
        return []
    have = set(
        ExtPropertyValue.objects.filter(issue=issue, definition__in=required).values_list("definition_id", flat=True)
    )
    return [d.name for d in required if d.id not in have]
