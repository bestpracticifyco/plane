# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Access matrix endpoints (workspace Admin only): who is in which project, with which role."""

from rest_framework.response import Response

from . import access
from .models import ExtAccessLog
from .views import ADMIN, ExtBaseView


class AccessMatrixEndpoint(ExtBaseView):
    flag = None  # an admin tool, available whether or not hardening is on

    def get(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, ADMIN)
        return Response(access.matrix(ws))

    def put(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, ADMIN)
        changed = access.apply_cells(ws, request.user, request.data.get("cells"))
        return Response({"changed": changed, **access.matrix(ws)})


class AccessGrantEndpoint(ExtBaseView):
    """PUT {email, grants: [{project_id, role}]} replaces the projects pre-assigned to an invitee.
    If the person is already a workspace member, the grants are applied straight away."""

    flag = None

    def put(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, ADMIN)
        access.set_grants(ws, request.user, request.data.get("email"), request.data.get("grants", []))
        return Response(access.matrix(ws))


class AccessLogEndpoint(ExtBaseView):
    flag = None

    def get(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, ADMIN)
        rows = ExtAccessLog.objects.filter(workspace=ws).select_related("project", "member", "actor")[:200]
        return Response(
            [
                {
                    "at": r.created_at.isoformat(),
                    "project": r.project.identifier,
                    "member": r.member.email,
                    "actor": r.actor.email if r.actor else None,
                    "old_role": r.old_role,
                    "new_role": r.new_role,
                }
                for r in rows
            ]
        )
