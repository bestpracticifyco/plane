# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
from django.apps import AppConfig


class PlaneExtConfig(AppConfig):
    name = "plane.ext"
    label = "plane_ext"
    verbose_name = "Plane extensions (Best Practicify)"

    def ready(self):
        from . import signals  # noqa: F401  (registers the required-property guard)
