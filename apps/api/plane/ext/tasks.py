# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""plane_ext periodic work, run by Plane's own Celery beat (PeriodicTask row from migration 0003)."""

from celery import shared_task


@shared_task(name="plane.ext.tasks.tick")
def tick():
    from . import access

    return {"grants_applied": access.apply_all_pending()}
