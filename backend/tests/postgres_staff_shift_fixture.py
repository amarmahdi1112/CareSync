"""Shared HTTP fixture for PostgreSQL child-state concurrency proofs."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi.testclient import TestClient


def clock_in_assigned_educator(
    client: TestClient,
    owner_headers: dict[str, str],
    *,
    facility_id: str,
    room_id: str,
) -> dict[str, str]:
    workspace = client.get("/api/v1/staff/workspace", headers=owner_headers)
    assert workspace.status_code == 200, workspace.text
    educator_role = next(role for role in workspace.json()["roles"] if role["key"] == "educator")
    invitation = client.post(
        "/api/v1/staff/invitations",
        headers=owner_headers,
        json={
            "email": f"postgres-concurrency-educator-{uuid4().hex}@example.test",
            "first_name": "Concurrency",
            "last_name": "Educator",
            "role_id": educator_role["id"],
            "assigned_facility_ids": [facility_id],
            "assigned_room_ids": [room_id],
        },
    )
    assert invitation.status_code == 201, invitation.text
    tokens = parse_qs(urlparse(invitation.json()["activation_url"]).fragment).get("token", [])
    assert len(tokens) == 1
    accepted = client.post(
        "/api/v1/auth/staff-activation/accept",
        json={"token": tokens[0], "password": "correct-password"},
    )
    assert accepted.status_code == 200, accepted.text
    headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    clocked_in = client.post(
        "/api/v1/staff/self/shifts/clock-in",
        headers=headers,
        json={
            "facility_id": facility_id,
            "room_id": room_id,
            "operation_id": str(uuid4()),
        },
    )
    assert clocked_in.status_code == 201, clocked_in.text
    return headers
