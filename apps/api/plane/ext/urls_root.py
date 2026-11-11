# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Root URLconf: /api/ext/v1/ in front of upstream's URLconf (re-exported unchanged)."""

from django.urls import include, path

from plane.urls import handler404, urlpatterns as core_urlpatterns  # noqa: F401

urlpatterns = [path("api/ext/v1/", include("plane.ext.urls")), *core_urlpatterns]
