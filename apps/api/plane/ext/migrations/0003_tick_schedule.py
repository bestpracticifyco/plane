# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Register plane.ext.tasks.tick with Plane's Celery beat (DatabaseScheduler), every 5 minutes.

A PeriodicTask row instead of an entry in plane/celery.py keeps upstream files untouched.
"""

from django.db import migrations

TASK_NAME = "plane-ext-tick"


def create(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    every, _ = IntervalSchedule.objects.get_or_create(every=5, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME, defaults={"task": "plane.ext.tasks.tick", "interval": every, "enabled": True}
    )


def remove(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("plane_ext", "0002_access"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(create, remove)]
