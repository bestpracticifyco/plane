# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""plane_ext background work, run by Plane's own Celery worker and beat (PeriodicTask from migration 0003)."""

import datetime as dt

from celery import shared_task


@shared_task(name="plane.ext.tasks.tick")
def tick():
    """Every 5 minutes: pending project grants, scheduled recurrences, missed completion triggers."""
    from . import access, recurring

    return {"grants_applied": access.apply_all_pending(), "recurrences_spawned": recurring.run_due()}


@shared_task(name="plane.ext.tasks.spawn_recurrence", autoretry_for=(Exception,), retry_backoff=30, max_retries=5)
def spawn_recurrence(rule_id, reason, completed_on=None):
    from . import recurring

    day = dt.date.fromisoformat(completed_on) if completed_on else None
    issue = recurring.spawn(rule_id, reason, completed_on=day)
    return str(issue.id) if issue else None
