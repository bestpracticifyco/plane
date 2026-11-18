# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Project-level access: hardening flag, access matrix, pending project grants."""

import pytest
from django.test import Client
from rest_framework.exceptions import ValidationError

from plane.db.models import Project, ProjectMember, User, WorkspaceMember
from plane.ext import access, services
from plane.ext.models import ExtAccessLog, ExtPendingProjectGrant

pytestmark = pytest.mark.django_db


def _role(project, user):
    pm = ProjectMember.objects.filter(project=project, member=user, is_active=True).first()
    return pm.role if pm else None


@pytest.fixture
def other(ws, people):
    p = Project.objects.create(name="Imagine Beauty", identifier="IMAGINE", workspace=ws)
    ProjectMember.objects.create(project=p, workspace=ws, member=people["admin"], role=20)
    return p


# -- hardening -------------------------------------------------------------------------------
def test_new_projects_are_private_only_when_hardening_is_on(ws):
    assert Project.objects.create(name="A", identifier="A", workspace=ws).network == 2
    services.set_flags(ws.id, {"ext.access_hardening": True})
    assert Project.objects.create(name="B", identifier="B", workspace=ws, network=2).network == 0


def test_project_role_cannot_exceed_workspace_role(ws, people, project):
    services.set_flags(ws.id, {"ext.access_hardening": True})
    pm = ProjectMember.objects.get(project=project, member=people["guest"])
    pm.role = 20  # what api/v1 projects/<id>/members/ would allow
    with pytest.raises(ValidationError):
        pm.save()
    pm.role = 5
    pm.save()


@pytest.mark.parametrize("path", ["estimates/", "analytics/", "default-analytics/", "project-stats/"])
def test_workspace_aggregates_are_admin_only_under_hardening(ws, people, path):
    url = f"/api/workspaces/{ws.slug}/{path}"
    member, admin = Client(), Client()
    member.force_login(people["member"])
    admin.force_login(people["admin"])
    assert member.get(url).status_code != 403  # flag off: upstream behaviour
    services.set_flags(ws.id, {"ext.access_hardening": True})
    assert member.get(url).status_code == 403
    assert admin.get(url).status_code != 403


# -- matrix ----------------------------------------------------------------------------------
def test_matrix_lists_people_projects_and_roles(client_for, people, base, project, other):
    data = client_for(people["admin"]).get(f"{base}/access/").data
    assert {p["identifier"] for p in data["projects"]} == {"FORBES", "IMAGINE"}
    assert data["cells"][str(people["member"].id)] == {str(project.id): 15}
    assert {p["email"] for p in data["people"]} == {"owner@example.com", "member@example.com", "guest@example.com"}


def test_matrix_is_workspace_admin_only(client_for, people, base):
    assert client_for(people["member"]).get(f"{base}/access/").status_code == 403


def test_matrix_add_change_remove_with_log(client_for, people, base, project, other):
    admin = client_for(people["admin"])
    m = str(people["member"].id)
    r = admin.put(
        f"{base}/access/",
        {
            "cells": [
                {"member_id": m, "project_id": str(other.id), "role": 5},
                {"member_id": m, "project_id": str(project.id), "role": None},
            ]
        },
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["changed"] == 2
    assert _role(other, people["member"]) == 5 and _role(project, people["member"]) is None
    admin.put(
        f"{base}/access/", {"cells": [{"member_id": m, "project_id": str(project.id), "role": 20}]}, format="json"
    )
    assert _role(project, people["member"]) == 20  # reactivated with the new role
    log = list(ExtAccessLog.objects.order_by("created_at").values_list("old_role", "new_role"))
    assert log == [(None, 5), (15, None), (None, 20)]


def test_matrix_enforces_upstream_role_rules_atomically(client_for, people, base, project, other):
    admin = client_for(people["admin"])
    g = str(people["guest"].id)
    r = admin.put(
        f"{base}/access/",
        {
            "cells": [
                {"member_id": str(people["member"].id), "project_id": str(other.id), "role": 15},
                {"member_id": g, "project_id": str(other.id), "role": 15},  # workspace Guest -> Guest only
            ]
        },
        format="json",
    )
    assert r.status_code == 400
    assert _role(other, people["member"]) is None  # nothing applied


def test_matrix_keeps_one_admin_and_not_self(client_for, people, base, project, ws):
    admin = client_for(people["admin"])
    r = admin.put(
        f"{base}/access/",
        {"cells": [{"member_id": str(people["admin"].id), "project_id": str(project.id), "role": None}]},
        format="json",
    )
    assert r.status_code == 400  # own access
    second = User.objects.create(email="md@example.com", username="md2")
    WorkspaceMember.objects.create(workspace=ws, member=second, role=20)
    ProjectMember.objects.filter(project=project, member=people["admin"]).update(role=15)
    ProjectMember.objects.create(project=project, workspace=ws, member=second, role=20)
    r = admin.put(
        f"{base}/access/",
        {"cells": [{"member_id": str(second.id), "project_id": str(project.id), "role": None}]},
        format="json",
    )
    assert r.status_code == 400 and "at least one Admin" in str(r.data)


# -- pending grants --------------------------------------------------------------------------
def test_grants_apply_when_the_invitee_joins(
    client_for, people, base, ws, project, other, django_capture_on_commit_callbacks
):
    admin = client_for(people["admin"])
    r = admin.put(
        f"{base}/access/grants/",
        {"email": "Imran@Example.com", "grants": [{"project_id": str(other.id), "role": 15}]},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["pending"] == [{"email": "imran@example.com", "project_id": str(other.id), "role": 15}]
    imran = User.objects.create(email="imran@example.com", username="imran")
    with django_capture_on_commit_callbacks(execute=True):
        WorkspaceMember.objects.create(workspace=ws, member=imran, role=15)  # invite accepted
    assert _role(other, imran) == 15 and _role(project, imran) is None
    assert not ExtPendingProjectGrant.objects.exists()


def test_bulk_join_is_picked_up_by_the_sweep(ws, people, other):
    access.set_grants(ws, people["admin"], "guest2@example.com", [{"project_id": str(other.id), "role": 15}])
    u = User.objects.create(email="guest2@example.com", username="guest2")
    WorkspaceMember.objects.bulk_create([WorkspaceMember(workspace=ws, member=u, role=5)])  # upstream join path
    assert _role(other, u) is None
    assert access.apply_all_pending() == 1
    assert _role(other, u) == 5  # capped to the workspace Guest role


def test_grants_for_existing_member_apply_immediately(ws, people, other):
    access.set_grants(ws, people["admin"], "member@example.com", [{"project_id": str(other.id), "role": 15}])
    assert _role(other, people["member"]) == 15
