# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Fixtures for plane_ext. These tests need the ext app installed, so they only run with
--ds=plane.ext.settings_test; under upstream's plane.settings.test they are skipped at collection."""

import uuid

import pytest
from django.conf import settings
from rest_framework.test import APIClient

if "plane.ext" not in settings.INSTALLED_APPS:
    collect_ignore_glob = ["test_*.py"]
else:
    from plane.db.models import Issue, Project, ProjectMember, State, User, Workspace, WorkspaceMember

    def _user(email):
        return User.objects.create(email=email, username=email.split("@")[0] + uuid.uuid4().hex[:6], is_active=True)

    @pytest.fixture
    def ws(db):
        owner = _user("owner@example.com")
        workspace = Workspace.objects.create(name="BP Accounting", slug="bp-accounting", owner=owner)
        WorkspaceMember.objects.create(workspace=workspace, member=owner, role=20)
        return workspace

    @pytest.fixture
    def people(ws):
        out = {"admin": ws.owner}
        for name, role in (("member", 15), ("guest", 5), ("outsider", None)):
            u = _user(f"{name}@example.com")
            if role:
                WorkspaceMember.objects.create(workspace=ws, member=u, role=role)
            out[name] = u
        return out

    @pytest.fixture
    def project(ws, people):
        p = Project.objects.create(name="Forbes Capital Solutions", identifier="FORBES", workspace=ws)
        for key, role in (("admin", 20), ("member", 15), ("guest", 5)):
            ProjectMember.objects.create(project=p, workspace=ws, member=people[key], role=role)
        return p

    @pytest.fixture
    def states(project):
        return {
            g: State.objects.create(name=g.title(), group=g, project=project, workspace=project.workspace)
            for g in ("backlog", "started")
        }

    @pytest.fixture
    def issue(project, states):
        return Issue.objects.create(name="Monthly close", project=project, workspace=project.workspace, state=states["backlog"])

    @pytest.fixture
    def client_for():
        def make(user):
            c = APIClient()
            c.force_authenticate(user=user)
            return c

        return make

    @pytest.fixture
    def base(ws):
        return f"/api/ext/v1/workspaces/{ws.slug}"
