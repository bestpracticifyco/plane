# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
"""PRD acceptance criteria for plane_ext (FR-EXT-001, 002, 004, 011, 012, 014, 022, 050, 080, 081)."""

import pytest

from plane.ext import services
from plane.ext.models import ExtActivity, ExtPropertyValue

pytestmark = pytest.mark.django_db


def create_def(client, base, **body):
    r = client.post(f"{base}/properties/", body, format="json")
    assert r.status_code == 201, r.data
    return r.data


@pytest.fixture
def frequency(client_for, people, base):
    return create_def(
        client_for(people["admin"]), base, name="Frequency", type="dropdown", options=["Weekly", "Monthly", "Quarterly"]
    )


@pytest.fixture
def bound(client_for, people, base, project, frequency):
    r = client_for(people["admin"]).put(
        f"{base}/projects/{project.id}/bindings/", [frequency["id"]], format="json"
    )
    assert r.status_code == 200, r.data
    return frequency


def opt(defn, name):
    return next(o["id"] for o in defn["options"] if o["name"] == name)


def test_health_is_public(client):
    assert client.get("/api/ext/v1/health/").json()["status"] == "ok"


def test_ac_001_admin_creates_definition_with_generated_key(frequency, client_for, people, base):
    assert frequency["key"] == "frequency"
    listed = client_for(people["member"]).get(f"{base}/properties/").data
    assert [d["key"] for d in listed] == ["frequency"]


def test_only_workspace_admin_creates_definitions(client_for, people, base):
    r = client_for(people["member"]).post(f"{base}/properties/", {"name": "X", "type": "text"}, format="json")
    assert r.status_code == 403
    r = client_for(people["outsider"]).get(f"{base}/properties/")
    assert r.status_code == 403


def test_is_multi_rejected_for_text(client_for, people, base):
    r = client_for(people["admin"]).post(f"{base}/properties/", {"name": "Note", "type": "text", "is_multi": True}, format="json")
    assert r.status_code == 400


def test_ac_002_only_bound_projects_accept_values(client_for, people, base, project, issue, frequency):
    url = f"{base}/projects/{project.id}/work-items/{issue.id}/values/{frequency['id']}/"
    r = client_for(people["member"]).patch(url, {"value": opt(frequency, "Monthly")}, format="json")
    assert r.status_code == 400  # not bound yet


def test_member_sets_value_and_activity_is_recorded(client_for, people, base, project, issue, bound):
    url = f"{base}/projects/{project.id}/work-items/{issue.id}/values/{bound['id']}/"
    r = client_for(people["member"]).patch(url, {"value": opt(bound, "Monthly")}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["value"] == opt(bound, "Monthly")
    act = ExtActivity.objects.get(issue=issue)
    assert act.old_value is None and act.new_value == opt(bound, "Monthly") and act.actor == people["member"]
    got = client_for(people["guest"]).get(f"{base}/projects/{project.id}/work-items/{issue.id}/values/").data
    assert got == {bound["id"]: opt(bound, "Monthly")}


def test_ac_022_guest_cannot_write(client_for, people, base, project, issue, bound):
    url = f"{base}/projects/{project.id}/work-items/{issue.id}/values/{bound['id']}/"
    r = client_for(people["guest"]).patch(url, {"value": opt(bound, "Monthly")}, format="json")
    assert r.status_code == 403


def test_ac_011_unknown_option_rejected(client_for, people, base, project, issue, bound):
    url = f"{base}/projects/{project.id}/work-items/{issue.id}/values/{bound['id']}/"
    r = client_for(people["member"]).patch(url, {"value": "00000000-0000-0000-0000-000000000000"}, format="json")
    assert r.status_code == 400
    assert "unknown option" in str(r.data)


def test_member_property_rejects_non_member(client_for, people, base, project, issue):
    admin = client_for(people["admin"])
    owner = create_def(admin, base, name="Reviewer", type="member")
    admin.put(f"{base}/projects/{project.id}/bindings/", [owner["id"]], format="json")
    url = f"{base}/projects/{project.id}/work-items/{issue.id}/values/{owner['id']}/"
    assert admin.patch(url, {"value": str(people["outsider"].id)}, format="json").status_code == 400
    assert admin.patch(url, {"value": str(people["member"].id)}, format="json").status_code == 200


def test_ac_004_archive_keeps_values(client_for, people, base, project, issue, bound):
    admin = client_for(people["admin"])
    admin.patch(f"{base}/projects/{project.id}/work-items/{issue.id}/values/{bound['id']}/", {"value": opt(bound, "Weekly")}, format="json")
    assert admin.delete(f"{base}/properties/{bound['id']}/").status_code == 204
    assert admin.get(f"{base}/properties/").data == []
    assert len(admin.get(f"{base}/properties/?include_archived=true").data) == 1
    assert ExtPropertyValue.objects.filter(issue=issue).count() == 1


def test_clear_deletes_row(client_for, people, base, project, issue, bound):
    member = client_for(people["member"])
    url = f"{base}/projects/{project.id}/work-items/{issue.id}/values/{bound['id']}/"
    member.patch(url, {"value": opt(bound, "Weekly")}, format="json")
    assert member.delete(url).status_code == 204
    assert not ExtPropertyValue.objects.filter(issue=issue).exists()


def test_ac_012_required_blocks_leaving_backlog(client_for, people, base, project, issue, states, bound, ws):
    from crum import impersonate
    from rest_framework.exceptions import ValidationError

    admin = client_for(people["admin"])
    admin.patch(f"{base}/properties/{bound['id']}/", {"is_required": True}, format="json")
    services.set_flags(ws.id, {"ext.enforce_required": True})
    issue.refresh_from_db()
    issue.state = states["started"]
    with impersonate(people["member"]), pytest.raises(ValidationError):
        issue.save()
    admin.patch(f"{base}/projects/{project.id}/work-items/{issue.id}/values/{bound['id']}/", {"value": opt(bound, "Monthly")}, format="json")
    issue.refresh_from_db()
    issue.state = states["started"]
    with impersonate(people["member"]):
        issue.save()  # now allowed


def test_required_guard_off_by_default(people, issue, states, bound):
    from crum import impersonate

    issue.state = states["started"]
    with impersonate(people["member"]):
        issue.save()


def test_ac_014_bulk_is_atomic(client_for, people, base, project, issue, bound):
    member = client_for(people["member"])
    good = {"issue_id": str(issue.id), "definition_id": bound["id"], "value": opt(bound, "Monthly")}
    bad = {"issue_id": str(issue.id), "definition_id": bound["id"], "value": "not-a-uuid"}
    r = member.post(f"{base}/values/bulk/", {"values": [good, bad]}, format="json")
    assert r.status_code == 400
    assert not ExtPropertyValue.objects.exists()
    assert member.post(f"{base}/values/bulk/", {"values": [good]}, format="json").status_code == 200


def test_ac_081_disabled_flag_returns_404_and_keeps_data(client_for, people, base, ws, bound):
    services.set_flags(ws.id, {"ext.properties": False})
    assert client_for(people["admin"]).get(f"{base}/properties/").status_code == 404
    services.set_flags(ws.id, {"ext.properties": True})
    assert len(client_for(people["admin"]).get(f"{base}/properties/").data) == 1


def test_flags_patch_requires_instance_admin(client_for, people, base):
    assert client_for(people["admin"]).patch(f"{base}/flags/", {"ext.footer": False}, format="json").status_code == 403


def test_column_preferences_round_trip(client_for, people, base, project, bound):
    guest = client_for(people["guest"])
    url = f"{base}/projects/{project.id}/columns/"
    assert guest.put(url, {"definition_ids": [bound["id"], "00000000-0000-0000-0000-000000000000"]}, format="json").data == {
        "definition_ids": [bound["id"]]
    }
    assert guest.get(url).data == {"definition_ids": [bound["id"]]}


def test_handoff_token_is_short_lived(client_for, people, base, settings):
    import jwt

    r = client_for(people["member"]).post(f"{base}/handoff/")
    assert r.status_code == 200, r.data
    claims = jwt.decode(r.data["token"], settings.PLANE_EXT["HANDOFF_SIGNING_KEY"], algorithms=["HS256"])
    assert claims["ws"] == "bp-accounting" and claims["role"] == 15 and claims["exp"] - claims["iat"] <= 300
