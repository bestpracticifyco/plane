# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""/api/ext/v1/ endpoints (PRD Appendix D).

Authentication: Plane session cookie (web) or X-Api-Key personal token (Governor / scripts).
Authorisation reuses Plane's workspace and project roles (Admin 20, Member 15, Guest 5).
"""

import secrets
import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.api.rate_limit import ApiKeyRateThrottle
from plane.app.views.base import BaseAPIView
from plane.authentication.session import BaseSessionAuthentication
from plane.db.models import Issue, Project, Workspace
from plane.license.models import InstanceAdmin

from . import services
from .models import (
    ExtActivity,
    ExtColumnPreference,
    ExtHandoffToken,
    ExtProjectBinding,
    ExtPropertyDefinition,
    ExtPropertyOption,
    ExtPropertyValue,
)

ADMIN, MEMBER, GUEST = 20, 15, 5


# ---------------------------------------------------------------------------------------------
# Serialisation helpers (plain dicts keep the payloads explicit and stable for the Governor)
# ---------------------------------------------------------------------------------------------
def option_json(o):
    return {"id": str(o.id), "name": o.name, "color": o.color, "sort_order": o.sort_order, "is_archived": o.is_archived}


def definition_json(d, include_archived_options=False):
    options = [o for o in d.options.all() if include_archived_options or not o.is_archived]
    return {
        "id": str(d.id),
        "key": d.key,
        "name": d.name,
        "description": d.description,
        "help_text": d.help_text,
        "type": d.type,
        "is_multi": d.is_multi,
        "is_required": d.is_required,
        "default_value": d.default_value,
        "sort_order": d.sort_order,
        "is_archived": d.is_archived,
        "options": [option_json(o) for o in options],
    }


DEFINITION_FIELDS = ("name", "key", "description", "help_text", "type", "is_multi", "is_required", "default_value", "sort_order")


class ExtBaseView(BaseAPIView):
    """Session or API-key auth; API-key callers get Plane's API rate limit (FR-EXT-031/035)."""

    authentication_classes = [BaseSessionAuthentication, APIKeyAuthentication]
    flag = "ext.properties"

    def get_throttles(self):
        if self.request.headers.get("X-Api-Key"):
            return [ApiKeyRateThrottle()]
        return super().get_throttles()

    # -- lookups ------------------------------------------------------------------------------
    def workspace(self, slug):
        ws = get_object_or_404(Workspace, slug=slug)
        if self.flag and not services.is_enabled(ws.id, self.flag):
            raise NotFound("This capability is disabled for the workspace.")
        return ws

    def require_workspace_role(self, slug, minimum):
        role = services.workspace_role(self.request.user, slug)
        if role is None or role < minimum:
            raise PermissionDenied("You don't have the required permissions.")
        return role

    def require_project_role(self, slug, project_id, minimum):
        role = services.project_role(self.request.user, slug, project_id)
        if role is None or role < minimum:
            raise PermissionDenied("You don't have the required permissions.")
        return role

    def issue(self, ws, project_id, issue_id):
        return get_object_or_404(Issue.issue_objects.select_related("state"), id=issue_id, project_id=project_id, workspace=ws)


# ---------------------------------------------------------------------------------------------
# Health (no auth)
# ---------------------------------------------------------------------------------------------
class HealthEndpoint(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        cfg = getattr(settings, "PLANE_EXT", {})
        return Response({"status": "ok", "app": "plane_ext", "version": cfg.get("VERSION", "dev")})


# ---------------------------------------------------------------------------------------------
# Definitions and options (FR-EXT-001..006, 040)
# ---------------------------------------------------------------------------------------------
class DefinitionListEndpoint(ExtBaseView):
    def get(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, GUEST)
        include = request.query_params.get("include_archived") == "true"
        qs = ExtPropertyDefinition.objects.filter(workspace=ws).prefetch_related("options")
        if not include:
            qs = qs.filter(is_archived=False)
        return Response([definition_json(d, include) for d in qs])

    def post(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, ADMIN)
        data = {k: request.data[k] for k in DEFINITION_FIELDS if k in request.data}
        if not data.get("name"):
            raise ValidationError({"name": ["required"]})
        data.setdefault("key", _slugify_key(data["name"]))
        services.validate_definition_payload(data)
        if ExtPropertyDefinition.objects.filter(workspace=ws, key=data["key"]).exists():
            raise ValidationError({"key": ["already exists in this workspace"]})
        with transaction.atomic():
            d = ExtPropertyDefinition.objects.create(workspace=ws, **data)
            for i, opt in enumerate(request.data.get("options") or []):
                opt = {"name": opt} if isinstance(opt, str) else opt
                ExtPropertyOption.objects.create(
                    definition=d, name=opt["name"], color=opt.get("color", ""), sort_order=opt.get("sort_order", (i + 1) * 1000)
                )
        return Response(definition_json(d), status=status.HTTP_201_CREATED)


def _slugify_key(name):
    from django.utils.text import slugify

    return slugify(name).replace("-", "_")[:64] or f"prop_{uuid.uuid4().hex[:8]}"


class DefinitionDetailEndpoint(ExtBaseView):
    def get_definition(self, slug, pk):
        ws = self.workspace(slug)
        return get_object_or_404(ExtPropertyDefinition.objects.prefetch_related("options"), workspace=ws, id=pk)

    def get(self, request, slug, pk):
        self.require_workspace_role(slug, GUEST)
        return Response(definition_json(self.get_definition(slug, pk), include_archived_options=True))

    def patch(self, request, slug, pk):
        self.require_workspace_role(slug, ADMIN)
        d = self.get_definition(slug, pk)
        data = {k: request.data[k] for k in DEFINITION_FIELDS + ("is_archived",) if k in request.data}
        services.validate_definition_payload(data, instance=d)
        if "key" in data and ExtPropertyDefinition.objects.filter(workspace=d.workspace, key=data["key"]).exclude(id=d.id).exists():
            raise ValidationError({"key": ["already exists in this workspace"]})
        for k, v in data.items():
            setattr(d, k, v)
        d.save()
        return Response(definition_json(d))

    def delete(self, request, slug, pk):
        """DELETE archives (FR-EXT-004): values stay queryable with include_archived=true."""
        self.require_workspace_role(slug, ADMIN)
        d = self.get_definition(slug, pk)
        d.is_archived = True
        d.save(update_fields=["is_archived", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class OptionListEndpoint(ExtBaseView):
    def get(self, request, slug, pk):
        self.require_workspace_role(slug, GUEST)
        d = get_object_or_404(ExtPropertyDefinition, workspace=self.workspace(slug), id=pk)
        return Response([option_json(o) for o in d.options.all()])

    def post(self, request, slug, pk):
        self.require_workspace_role(slug, ADMIN)
        d = get_object_or_404(ExtPropertyDefinition, workspace=self.workspace(slug), id=pk)
        if d.type != "dropdown":
            raise ValidationError({"type": ["only dropdown properties have options"]})
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": ["required"]})
        if d.options.filter(name=name).exists():
            raise ValidationError({"name": ["already exists"]})
        o = ExtPropertyOption.objects.create(
            definition=d, name=name, color=request.data.get("color", ""), sort_order=request.data.get("sort_order", 65535)
        )
        return Response(option_json(o), status=status.HTTP_201_CREATED)


class OptionDetailEndpoint(ExtBaseView):
    def get_option(self, slug, pk, oid):
        return get_object_or_404(ExtPropertyOption, definition__workspace=self.workspace(slug), definition_id=pk, id=oid)

    def patch(self, request, slug, pk, oid):
        self.require_workspace_role(slug, ADMIN)
        o = self.get_option(slug, pk, oid)
        for k in ("name", "color", "sort_order", "is_archived"):
            if k in request.data:
                setattr(o, k, request.data[k])
        o.save()
        return Response(option_json(o))

    def delete(self, request, slug, pk, oid):
        """Options are archived, not deleted, while values may reference them (FR-EXT-003)."""
        self.require_workspace_role(slug, ADMIN)
        o = self.get_option(slug, pk, oid)
        o.is_archived = True
        o.save(update_fields=["is_archived", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------------------------
# Project bindings (FR-EXT-002, 041)
# ---------------------------------------------------------------------------------------------
def bindings_json(project_id):
    rows = ExtProjectBinding.objects.filter(project_id=project_id).select_related("definition").order_by("sort_order")
    return [
        {
            "definition_id": str(b.definition_id),
            "key": b.definition.key,
            "sort_order": b.sort_order,
            "is_enabled": b.is_enabled,
            "show_on_card": b.show_on_card,
        }
        for b in rows
        if not b.definition.is_archived
    ]


class BindingEndpoint(ExtBaseView):
    def get(self, request, slug, project_id):
        self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        return Response(bindings_json(project_id))

    def put(self, request, slug, project_id):
        """Replace the project's bound definitions and their order with the list in the body."""
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, ADMIN)
        project = get_object_or_404(Project, id=project_id, workspace=ws)
        items = request.data if isinstance(request.data, list) else request.data.get("bindings", [])
        wanted = {}
        for i, item in enumerate(items):
            item = {"definition_id": item} if isinstance(item, str) else item
            wanted[str(item["definition_id"])] = {
                "sort_order": item.get("sort_order", (i + 1) * 1000),
                "is_enabled": item.get("is_enabled", True),
                "show_on_card": item.get("show_on_card", False),
            }
        defs = set(
            str(i) for i in ExtPropertyDefinition.objects.filter(workspace=ws, id__in=list(wanted)).values_list("id", flat=True)
        )
        unknown = sorted(set(wanted) - defs)
        if unknown:
            raise ValidationError({"definition_id": [f"not a property of this workspace: {u}" for u in unknown]})
        with transaction.atomic():
            ExtProjectBinding.objects.filter(project=project).exclude(definition_id__in=list(wanted)).delete(soft=False)
            for def_id, attrs in wanted.items():
                ExtProjectBinding.objects.update_or_create(project=project, definition_id=def_id, defaults=attrs)
        return Response(bindings_json(project_id))


# ---------------------------------------------------------------------------------------------
# Values (FR-EXT-010..015, 042, 043, 050)
# ---------------------------------------------------------------------------------------------
def values_for_issues(issue_ids):
    out = {}
    for row in ExtPropertyValue.objects.filter(issue_id__in=issue_ids).select_related("definition"):
        out.setdefault(str(row.issue_id), {})[str(row.definition_id)] = services.serialize_value(row)
    return out


class IssueValuesEndpoint(ExtBaseView):
    def get(self, request, slug, project_id, issue_id):
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        issue = self.issue(ws, project_id, issue_id)
        return Response(values_for_issues([issue.id]).get(str(issue.id), {}))

    def put(self, request, slug, project_id, issue_id):
        """Upsert several values for one item atomically: body {definition_id: value, ...}."""
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, MEMBER)
        issue = self.issue(ws, project_id, issue_id)
        defs = {str(d.id): d for d in services.bound_definitions(project_id)}
        with transaction.atomic():
            for def_id, value in (request.data or {}).items():
                if def_id not in defs:
                    raise ValidationError({def_id: ["property is not bound to this project"]})
                services.write_value(issue, defs[def_id], value, request.user)
        return Response(values_for_issues([issue.id]).get(str(issue.id), {}))


class IssueValueDetailEndpoint(ExtBaseView):
    def _target(self, slug, project_id, issue_id, definition_id):
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, MEMBER)
        issue = self.issue(ws, project_id, issue_id)
        d = get_object_or_404(ExtPropertyDefinition.objects.prefetch_related("options"), workspace=ws, id=definition_id)
        return issue, d

    def patch(self, request, slug, project_id, issue_id, definition_id):
        issue, d = self._target(slug, project_id, issue_id, definition_id)
        row = services.write_value(issue, d, request.data.get("value"), request.user)
        return Response({"definition_id": str(d.id), "value": services.serialize_value(row)})

    def delete(self, request, slug, project_id, issue_id, definition_id):
        issue, d = self._target(slug, project_id, issue_id, definition_id)
        services.write_value(issue, d, None, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectValuesEndpoint(ExtBaseView):
    """All values of a project's items in one call, for List/Spreadsheet rendering."""

    MAX_ITEMS = 5000

    def get(self, request, slug, project_id):
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        ids = request.query_params.get("issue_ids")
        qs = Issue.issue_objects.filter(project_id=project_id, workspace=ws)
        if ids:
            qs = qs.filter(id__in=[i for i in ids.split(",") if i])
        issue_ids = list(qs.values_list("id", flat=True)[: self.MAX_ITEMS])
        return Response(values_for_issues(issue_ids))


class BulkValuesEndpoint(ExtBaseView):
    MAX = 500

    def post(self, request, slug):
        """Up to 500 {issue_id, definition_id, value} upserts, all-or-nothing (FR-EXT-014)."""
        ws = self.workspace(slug)
        rows = request.data.get("values") if isinstance(request.data, dict) else request.data
        if not isinstance(rows, list) or not rows:
            raise ValidationError({"values": ["a non-empty list is required"]})
        if len(rows) > self.MAX:
            raise ValidationError({"values": [f"at most {self.MAX} rows per call"]})
        issues = {
            str(i.id): i
            for i in Issue.issue_objects.select_related("state").filter(workspace=ws, id__in=[r.get("issue_id") for r in rows])
        }
        defs = {
            str(d.id): d
            for d in ExtPropertyDefinition.objects.prefetch_related("options").filter(
                workspace=ws, id__in=[r.get("definition_id") for r in rows]
            )
        }
        checked = set()
        with transaction.atomic():
            for n, r in enumerate(rows):
                issue, d = issues.get(str(r.get("issue_id"))), defs.get(str(r.get("definition_id")))
                if issue is None or d is None:
                    raise ValidationError({str(n): ["unknown issue_id or definition_id"]})
                if issue.project_id not in checked:
                    self.require_project_role(slug, issue.project_id, MEMBER)
                    checked.add(issue.project_id)
                try:
                    services.write_value(issue, d, r.get("value"), request.user)
                except ValidationError as e:
                    raise ValidationError({str(n): e.detail})
        return Response({"updated": len(rows)})


class ActivityEndpoint(ExtBaseView):
    def get(self, request, slug, project_id, issue_id):
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        issue = self.issue(ws, project_id, issue_id)
        rows = ExtActivity.objects.filter(issue=issue).select_related("definition", "actor")[:200]
        return Response(
            [
                {
                    "id": str(a.id),
                    "definition_id": str(a.definition_id),
                    "property": a.definition.name,
                    "actor": {"id": str(a.actor_id), "display_name": a.actor.display_name} if a.actor else None,
                    "old_value": a.old_value,
                    "new_value": a.new_value,
                    "created_at": a.created_at.isoformat(),
                }
                for a in rows
            ]
        )


# ---------------------------------------------------------------------------------------------
# Column preferences (FR-EXT-021, persisted server-side per user per project)
# ---------------------------------------------------------------------------------------------
class ColumnPreferenceEndpoint(ExtBaseView):
    flag = "ext.columns"

    def get(self, request, slug, project_id):
        self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        pref = ExtColumnPreference.objects.filter(user=request.user, project_id=project_id).first()
        return Response({"definition_ids": [str(i) for i in (pref.definition_ids if pref else [])]})

    def put(self, request, slug, project_id):
        ws = self.workspace(slug)
        self.require_project_role(slug, project_id, GUEST)
        ids = [str(i) for i in request.data.get("definition_ids", [])]
        valid = set(str(i) for i in ExtPropertyDefinition.objects.filter(workspace=ws, id__in=ids).values_list("id", flat=True))
        ids = [i for i in ids if i in valid]
        ExtColumnPreference.objects.update_or_create(user=request.user, project_id=project_id, defaults={"definition_ids": ids})
        return Response({"definition_ids": ids})


# ---------------------------------------------------------------------------------------------
# Schema export (FR-EXT-005), flags (FR-EXT-080/081), hand-off token (FR-EXT-061)
# ---------------------------------------------------------------------------------------------
class SchemaEndpoint(ExtBaseView):
    def get(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, MEMBER)
        defs = ExtPropertyDefinition.objects.filter(workspace=ws).prefetch_related("options")
        bindings = {}
        for b in ExtProjectBinding.objects.filter(project__workspace=ws).select_related("project", "definition"):
            bindings.setdefault(b.project.identifier, []).append(b.definition.key)
        return Response(
            {
                "ext_properties": [
                    {
                        "key": d.key,
                        "name": d.name,
                        "type": d.type,
                        "is_multi": d.is_multi,
                        "is_required": d.is_required,
                        "archived": d.is_archived,
                        "options": [o.name for o in d.options.all() if not o.is_archived],
                    }
                    for d in defs
                ],
                "bindings": bindings,
            }
        )


class FlagEndpoint(ExtBaseView):
    flag = None

    def get(self, request, slug):
        ws = self.workspace(slug)
        self.require_workspace_role(slug, GUEST)
        return Response(services.get_flags(ws.id))

    def patch(self, request, slug):
        ws = self.workspace(slug)
        if not InstanceAdmin.objects.filter(user=request.user).exists():
            raise PermissionDenied("Only instance admins can change feature flags.")
        return Response(services.set_flags(ws.id, dict(request.data)))


class HandoffEndpoint(ExtBaseView):
    flag = "ext.embeds"

    def post(self, request, slug):
        ws = self.workspace(slug)
        role = self.require_workspace_role(slug, GUEST)
        cfg = getattr(settings, "PLANE_EXT", {})
        key = cfg.get("HANDOFF_SIGNING_KEY")
        if not key:
            raise NotFound("Embedded pages are not configured on this instance.")
        now = timezone.now()
        exp = now + timedelta(seconds=cfg.get("HANDOFF_TOKEN_TTL_SECONDS", 300))
        jti = secrets.token_urlsafe(24)
        token = jwt.encode(
            {
                "sub": str(request.user.id),
                "email": request.user.email,
                "ws": ws.slug,
                "role": role,
                "jti": jti,
                "iat": int(now.timestamp()),
                "exp": int(exp.timestamp()),
                "iss": "plane_ext",
            },
            key,
            algorithm="HS256",
        )
        ExtHandoffToken.objects.create(user=request.user, workspace=ws, jti=jti, expires_at=exp)
        return Response({"token": token, "expires_at": exp.isoformat(), "governor_url": cfg.get("GOVERNOR_BASE_URL", "")})
