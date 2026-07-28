"""Atomic family guardian and emergency-contact replacement tests."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.basic.models import AuditEvent, BasicBase
from app.core.config import Settings
from app.main import create_app


def _client(tmp_path) -> tuple[TestClient, object]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="family-network-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "first_name": "Family",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _guardian(first_name: str, relationship: str = "Parent") -> dict:
    return {
        "first_name": first_name,
        "last_name": "Guardian",
        "relationship": relationship,
        "email": f"{first_name.lower()}@example.com",
        "cell_phone": "780-555-0100",
        "authorized_pickup": True,
    }


def _contact(first_name: str, relationship: str = "Aunt") -> dict:
    return {
        "first_name": first_name,
        "last_name": "Contact",
        "relationship": relationship,
        "cell_phone": "780-555-0199",
        "authorized_pickup": True,
    }


def _family(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    file_number: str,
) -> dict:
    response = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": name,
            "file_number": file_number,
            "primary_guardian": _guardian("Original Primary"),
            "secondary_guardian": _guardian("Original Secondary", "Grandparent"),
            "emergency_contacts": [
                _contact("Original One"),
                _contact("Original Two", "Uncle"),
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_family_patch_omits_replaces_and_removes_care_network_sections(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "network@example.com", "Network Child Care")
        headers = _headers(auth)
        family = _family(client, headers, "Network Family", "NET-001")
        primary = next(item for item in family["guardians"] if item["is_primary"])
        secondary = next(item for item in family["guardians"] if not item["is_primary"])
        original_contact_ids = {item["id"] for item in family["emergency_contacts"]}

        scalar_only = client.patch(
            f"/api/v1/families/{family['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": family["version"],
                "additional_notes": "Care network intentionally omitted",
            },
        )
        assert scalar_only.status_code == 200, scalar_only.text
        assert {item["id"] for item in scalar_only.json()["guardians"]} == {
            primary["id"],
            secondary["id"],
        }
        assert {
            item["id"] for item in scalar_only.json()["emergency_contacts"]
        } == original_contact_ids

        primary_replaced = client.put(
            f"/api/v1/families/{family['id']}/guardians/primary",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": scalar_only.json()["version"],
                "guardian": _guardian("Updated Primary", "Legal Guardian"),
            },
        )
        assert primary_replaced.status_code == 200, primary_replaced.text
        secondary_removed = client.put(
            f"/api/v1/families/{family['id']}/guardians/secondary",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": primary_replaced.json()["version"],
                "guardian": None,
            },
        )
        assert secondary_removed.status_code == 200, secondary_removed.text
        replaced = client.put(
            f"/api/v1/families/{family['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": secondary_removed.json()["version"],
                "emergency_contacts": [_contact("Replacement", "Trusted Neighbour")],
            },
        )
        assert replaced.status_code == 200, replaced.text
        replaced_data = replaced.json()
        assert len(replaced_data["guardians"]) == 1
        assert replaced_data["guardians"][0]["id"] != primary["id"]
        assert replaced_data["guardians"][0]["first_name"] == "Updated Primary"
        assert replaced_data["guardians"][0]["relationship"] == "Legal Guardian"
        assert len(replaced_data["emergency_contacts"]) == 1
        assert replaced_data["emergency_contacts"][0]["first_name"] == "Replacement"
        assert replaced_data["emergency_contacts"][0]["id"] not in original_contact_ids

        with application.state.database.session_factory() as session:
            actions = set(
                session.scalars(
                    select(AuditEvent.action).where(
                        AuditEvent.organization_id == UUID(auth["user"]["organization_id"]),
                        AuditEvent.entity_id == UUID(family["id"]),
                        AuditEvent.action.in_(
                            {
                                "family.guardian.primary.replaced",
                                "family.guardian.secondary.replaced",
                                "family.emergency_contacts.replaced",
                            }
                        ),
                    )
                )
            )
            assert actions == {
                "family.guardian.primary.replaced",
                "family.guardian.secondary.replaced",
                "family.emergency_contacts.replaced",
            }

        primary_removed = client.put(
            f"/api/v1/families/{family['id']}/guardians/primary",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": replaced_data["version"],
                "guardian": None,
            },
        )
        assert primary_removed.status_code == 200, primary_removed.text
        empty_removed = client.put(
            f"/api/v1/families/{family['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": primary_removed.json()["version"],
                "emergency_contacts": [],
            },
        )
        assert empty_removed.status_code == 200, empty_removed.text
        assert empty_removed.json()["guardians"] == []
        assert empty_removed.json()["emergency_contacts"] == []

        contact_added = client.put(
            f"/api/v1/families/{family['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": empty_removed.json()["version"],
                "emergency_contacts": [_contact("Temporary")],
            },
        )
        assert contact_added.status_code == 200, contact_added.text
        assert len(contact_added.json()["emergency_contacts"]) == 1
        null_removed = client.put(
            f"/api/v1/families/{family['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": contact_added.json()["version"],
                "emergency_contacts": [],
            },
        )
        assert null_removed.status_code == 200, null_removed.text
        assert null_removed.json()["emergency_contacts"] == []


def test_family_care_network_patch_is_tenant_scoped(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        first = _register(client, "first-network@example.com", "First Network")
        second = _register(client, "second-network@example.com", "Second Network")
        first_headers = _headers(first)
        second_headers = _headers(second)
        first_family = _family(client, first_headers, "First Family", "FIRST-001")
        second_family = _family(client, second_headers, "Second Family", "SECOND-001")

        foreign_patch = client.put(
            f"/api/v1/families/{first_family['id']}/guardians/primary",
            headers=second_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": first_family["version"],
                "guardian": _guardian("Foreign Edit"),
            },
        )
        assert foreign_patch.status_code == 404

        first_after = client.get(f"/api/v1/families/{first_family['id']}", headers=first_headers)
        second_after = client.get(f"/api/v1/families/{second_family['id']}", headers=second_headers)
        assert first_after.status_code == 200
        assert second_after.status_code == 200
        assert {item["first_name"] for item in first_after.json()["guardians"]} == {
            "Original Primary",
            "Original Secondary",
        }
        assert {item["first_name"] for item in second_after.json()["guardians"]} == {
            "Original Primary",
            "Original Secondary",
        }


def test_family_scalar_conflict_leaves_versioned_care_network_unchanged(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "atomic-network@example.com", "Atomic Network")
        headers = _headers(auth)
        _family(client, headers, "Existing Family", "DUPLICATE-001")
        target = _family(client, headers, "Atomic Family", "ATOMIC-001")
        target_guardian_ids = {item["id"] for item in target["guardians"]}
        target_contact_ids = {item["id"] for item in target["emergency_contacts"]}

        with application.state.database.session_factory() as session:
            audits_before = session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.organization_id == UUID(auth["user"]["organization_id"]),
                    AuditEvent.entity_id == UUID(target["id"]),
                    AuditEvent.action == "family.updated",
                )
            )

        conflict = client.patch(
            f"/api/v1/families/{target['id']}",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": target["version"],
                "name": "Should Roll Back",
                "file_number": "DUPLICATE-001",
            },
        )
        assert conflict.status_code == 409, conflict.text

        unchanged = client.get(f"/api/v1/families/{target['id']}", headers=headers)
        assert unchanged.status_code == 200, unchanged.text
        unchanged_data = unchanged.json()
        assert unchanged_data["name"] == "Atomic Family"
        assert unchanged_data["file_number"] == "ATOMIC-001"
        assert {item["id"] for item in unchanged_data["guardians"]} == target_guardian_ids
        assert {item["id"] for item in unchanged_data["emergency_contacts"]} == target_contact_ids
        assert {item["first_name"] for item in unchanged_data["guardians"]} == {
            "Original Primary",
            "Original Secondary",
        }

        with application.state.database.session_factory() as session:
            audits_after = session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.organization_id == UUID(auth["user"]["organization_id"]),
                    AuditEvent.entity_id == UUID(target["id"]),
                    AuditEvent.action == "family.updated",
                )
            )
        assert audits_after == audits_before

        invalid = client.put(
            f"/api/v1/families/{target['id']}/emergency-contacts",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": target["version"],
                "emergency_contacts": [
                    {
                        "first_name": "Missing",
                        "last_name": "Phone",
                        "relationship": "Friend",
                    }
                ],
            },
        )
        assert invalid.status_code == 422
        still_unchanged = client.get(f"/api/v1/families/{target['id']}", headers=headers)
        assert still_unchanged.json()["name"] == "Atomic Family"
