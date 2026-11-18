# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Project-level access: the people x projects matrix, its batch edits, and pending project grants.

Plane CE rules are kept exactly (plane.app.views.project.member.ProjectMemberViewSet):
workspace Admin -> project Admin only; workspace Guest -> project Guest only; workspace Member -> any.
Removal deactivates the ProjectMember row (is_active=False), as upstream does.
"""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from plane.db.models import Project, ProjectMember, User, WorkspaceMember

from .models import ExtAccessLog, ExtPendingProjectGrant

ROLES = (20, 15, 5)


def allowed_project_roles(workspace_role):
    if workspace_role == 20:
        return {20}
    if workspace_role == 5:
        return {5}
    return set(ROLES)


def matrix(ws):
    projects = list(
        Project.objects.filter(workspace=ws)
        .order_by("name")
        .values("id", "identifier", "name", "network", "archived_at")
    )
    people = list(
        WorkspaceMember.objects.filter(workspace=ws, is_active=True, member__is_bot=False)
        .select_related("member")
        .order_by("member__display_name", "member__email")
    )
    cells = {}
    for member_id, project_id, role in ProjectMember.objects.filter(
        workspace=ws, is_active=True, member__isnull=False
    ).values_list("member_id", "project_id", "role"):
        cells.setdefault(str(member_id), {})[str(project_id)] = role
    pending = ExtPendingProjectGrant.objects.filter(workspace=ws).order_by("email")
    return {
        "projects": [
            {
                "id": str(p["id"]),
                "identifier": p["identifier"],
                "name": p["name"],
                "is_private": p["network"] == 0,
                "is_archived": p["archived_at"] is not None,
            }
            for p in projects
        ],
        "people": [
            {
                "id": str(wm.member_id),
                "email": wm.member.email,
                "display_name": wm.member.display_name,
                "workspace_role": wm.role,
            }
            for wm in people
        ],
        "cells": cells,
        "pending": [{"email": g.email, "project_id": str(g.project_id), "role": g.role} for g in pending],
    }


def _role_errors(ws, cells):
    """Validate a batch before anything is written. Returns per-cell error strings."""
    errors = []
    member_ids = {str(c.get("member_id")) for c in cells}
    project_ids = {str(c.get("project_id")) for c in cells}
    ws_roles = {
        str(m): r
        for m, r in WorkspaceMember.objects.filter(workspace=ws, is_active=True, member_id__in=member_ids).values_list(
            "member_id", "role"
        )
    }
    known_projects = {
        str(p) for p in Project.objects.filter(workspace=ws, id__in=project_ids).values_list("id", flat=True)
    }
    for c in cells:
        m, p, role = str(c.get("member_id")), str(c.get("project_id")), c.get("role")
        if m not in ws_roles:
            errors.append(f"{m}: not an active workspace member")
        elif p not in known_projects:
            errors.append(f"{p}: not a project in this workspace")
        elif role is not None and role not in allowed_project_roles(ws_roles[m]):
            errors.append(f"{m} in {p}: role {role} is not allowed for workspace role {ws_roles[m]}")
    return errors


def apply_cells(ws, actor, cells):
    """Apply [{member_id, project_id, role|None}] atomically. Returns the number of changed cells."""
    if not isinstance(cells, list) or not cells:
        raise ValidationError({"cells": ["a non-empty list is required"]})
    errors = _role_errors(ws, cells)
    if any(str(c.get("member_id")) == str(actor.id) for c in cells):
        errors.append("You cannot change your own project access here")
    if errors:
        raise ValidationError({"cells": errors})
    changed = 0
    with transaction.atomic():
        for c in cells:
            changed += _apply_one(ws, actor, str(c["member_id"]), str(c["project_id"]), c.get("role"))
        _check_admins_remain(ws, {str(c["project_id"]) for c in cells})
    return changed


def _apply_one(ws, actor, member_id, project_id, role):
    pm = ProjectMember.objects.filter(workspace=ws, project_id=project_id, member_id=member_id).first()
    old = pm.role if pm is not None and pm.is_active else None
    if old == role:
        return 0
    if role is None:
        pm.is_active = False
        pm.save(update_fields=["is_active", "updated_at"])
    elif pm is None:
        ProjectMember(workspace=ws, project_id=project_id, member_id=member_id, role=role).save()
    else:
        pm.role, pm.is_active = role, True
        pm.save(update_fields=["role", "is_active", "updated_at"])
    ExtAccessLog.objects.create(
        workspace=ws, project_id=project_id, member_id=member_id, actor=actor, old_role=old, new_role=role
    )
    return 1


def _check_admins_remain(ws, project_ids):
    with_admin = set(
        str(p)
        for p in ProjectMember.objects.filter(
            workspace=ws, project_id__in=project_ids, is_active=True, role=20
        ).values_list("project_id", flat=True)
    )
    orphaned = sorted(project_ids - with_admin)
    if orphaned:
        names = Project.objects.filter(id__in=orphaned).values_list("identifier", flat=True)
        raise ValidationError({"cells": [f"{n}: a project must keep at least one Admin" for n in names]})


# ---------------------------------------------------------------------------------------------
# Pending grants: "when this email joins, put them in these projects"
# ---------------------------------------------------------------------------------------------
def set_grants(ws, actor, email, grants):
    email = (email or "").strip().lower()
    if "@" not in email:
        raise ValidationError({"email": ["a valid email is required"]})
    if not isinstance(grants, list):
        raise ValidationError({"grants": ["a list is required"]})
    project_ids = {str(g.get("project_id")) for g in grants}
    known = {str(p) for p in Project.objects.filter(workspace=ws, id__in=project_ids).values_list("id", flat=True)}
    bad = [p for p in project_ids if p not in known] + [
        str(g.get("role")) for g in grants if g.get("role") not in ROLES
    ]
    if bad:
        raise ValidationError({"grants": [f"invalid: {b}" for b in bad]})
    with transaction.atomic():
        ExtPendingProjectGrant.objects.filter(workspace=ws, email=email).delete(soft=False)
        ExtPendingProjectGrant.objects.bulk_create(
            [
                ExtPendingProjectGrant(workspace=ws, email=email, project_id=g["project_id"], role=g["role"])
                for g in grants
            ]
        )
    user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        apply_grants_for(ws, user, actor=actor)


def apply_grants_for(ws, user, actor=None):
    """Turn pending grants into ProjectMember rows once `user` is an active workspace member.

    The project role is capped to what the workspace role allows (Admin -> 20, Guest -> 5).
    """
    wm = WorkspaceMember.objects.filter(workspace=ws, member=user, is_active=True).first()
    if wm is None:
        return 0
    grants = list(ExtPendingProjectGrant.objects.filter(workspace=ws, email__iexact=user.email))
    if not grants:
        return 0
    allowed = allowed_project_roles(wm.role)
    applied = 0
    with transaction.atomic():
        for g in grants:
            role = g.role if g.role in allowed else next(iter(allowed))  # Admin/Guest allow exactly one role
            applied += _apply_one(ws, actor, str(user.id), str(g.project_id), role)
        ExtPendingProjectGrant.objects.filter(id__in=[g.id for g in grants]).delete(soft=False)
    return applied


def apply_all_pending():
    """Periodic sweep: upstream joins workspaces with bulk_create, which sends no post_save signal."""
    applied = 0
    for g in (
        ExtPendingProjectGrant.objects.select_related("workspace")
        .distinct("workspace_id", "email")
        .order_by("workspace_id", "email")
    ):
        user = User.objects.filter(email__iexact=g.email).first()
        if user is not None:
            applied += apply_grants_for(g.workspace, user)
    return applied
