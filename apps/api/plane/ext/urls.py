# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""Routes under /api/ext/v1/ (PRD Appendix D)."""

from django.urls import path

from . import views

WS = "workspaces/<str:slug>"
PRJ = WS + "/projects/<uuid:project_id>"
ITEM = PRJ + "/work-items/<uuid:issue_id>"

urlpatterns = [
    path("health/", views.HealthEndpoint.as_view(), name="ext-health"),
    path(f"{WS}/properties/", views.DefinitionListEndpoint.as_view(), name="ext-definitions"),
    path(f"{WS}/properties/<uuid:pk>/", views.DefinitionDetailEndpoint.as_view(), name="ext-definition"),
    path(f"{WS}/properties/<uuid:pk>/options/", views.OptionListEndpoint.as_view(), name="ext-options"),
    path(f"{WS}/properties/<uuid:pk>/options/<uuid:oid>/", views.OptionDetailEndpoint.as_view(), name="ext-option"),
    path(f"{WS}/values/bulk/", views.BulkValuesEndpoint.as_view(), name="ext-values-bulk"),
    path(f"{WS}/schema/", views.SchemaEndpoint.as_view(), name="ext-schema"),
    path(f"{WS}/flags/", views.FlagEndpoint.as_view(), name="ext-flags"),
    path(f"{WS}/handoff/", views.HandoffEndpoint.as_view(), name="ext-handoff"),
    path(f"{PRJ}/bindings/", views.BindingEndpoint.as_view(), name="ext-bindings"),
    path(f"{PRJ}/values/", views.ProjectValuesEndpoint.as_view(), name="ext-project-values"),
    path(f"{PRJ}/columns/", views.ColumnPreferenceEndpoint.as_view(), name="ext-columns"),
    path(f"{ITEM}/values/", views.IssueValuesEndpoint.as_view(), name="ext-values"),
    path(f"{ITEM}/values/<uuid:definition_id>/", views.IssueValueDetailEndpoint.as_view(), name="ext-value"),
    path(f"{ITEM}/activity/", views.ActivityEndpoint.as_view(), name="ext-activity"),
]
