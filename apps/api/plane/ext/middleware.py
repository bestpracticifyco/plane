# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Close Plane CE's cross-project leaks for non-admins when `ext.access_hardening` is on.

These upstream endpoints aggregate over every project in the workspace without checking project
membership, so a Member of one private project would see counts and names from all the others:
analytics (legacy and default), saved analytic views, project stats, analytics export, and workspace
estimates. Workspace Admins keep them; everyone else gets 403. The membership-aware advanced-analytics
endpoints are left alone. Registered in plane.settings.bp, so no upstream file changes.
"""

import re

from django.http import JsonResponse

from . import services

_BLOCKED = re.compile(
    r"^/api/workspaces/(?P<slug>[^/]+)/"
    r"(analytics|analytic-view|saved-analytic-view|export-analytics|default-analytics|project-stats|estimates)/"
)


class AccessHardeningMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        m = _BLOCKED.match(request.path)
        if m is not None:
            user = getattr(request, "user", None)
            slug = m.group("slug")
            if (
                user is not None
                and user.is_authenticated
                and services.is_enabled_for_slug(slug, "ext.access_hardening")
                and (services.workspace_role(user, slug) or 0) < 20
            ):
                return JsonResponse({"error": "Workspace analytics are limited to workspace admins."}, status=403)
        return self.get_response(request)
