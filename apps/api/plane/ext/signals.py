# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Required-property guard (FR-EXT-012) and required-module guard (FR-EXT-012a).

When the workspace flag `ext.enforce_required` is on, a work item may not move out of the
Backlog/Triage group while a required bound property is empty. When `ext.require_module` is on,
it may not move out while its project has modules and the item is in none of them. Implemented as a pre_save
receiver on Plane's Issue model, so no upstream file changes. The guard only runs for
user-initiated saves (a request user is present) to avoid breaking background tasks.
"""

from crum import get_current_user
from django.db.models.signals import pre_save
from django.dispatch import receiver
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, State

from . import services


@receiver(pre_save, sender=Issue, dispatch_uid="plane_ext_required_property_guard")
def required_property_guard(sender, instance, **kwargs):
    if instance._state.adding or not instance.has_changed("state_id") or not instance.state_id:
        return
    user = get_current_user()
    if user is None or user.is_anonymous:
        return
    check_props = services.is_enabled(instance.workspace_id, "ext.enforce_required")
    check_module = services.is_enabled(instance.workspace_id, "ext.require_module")
    if not (check_props or check_module):
        return
    groups = dict(State.objects.filter(id__in=[instance.old_values.get("state_id"), instance.state_id]).values_list("id", "group"))
    leaving_backlog = groups.get(instance.old_values.get("state_id")) in ("backlog", "triage", None)
    entering_work = groups.get(instance.state_id) not in ("backlog", "triage")
    if leaving_backlog and entering_work:
        errors = []
        if check_module and services.needs_module(instance):
            errors.append("Add this work item to a module (its Function) first")
        missing = services.missing_required(instance) if check_props else []
        if missing:
            errors.append(f"Set required properties first: {', '.join(missing)}")
        if errors:
            raise ValidationError({"state_id": errors})
