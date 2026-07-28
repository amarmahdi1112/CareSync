"""Licensed Daycare/OSC program contracts and tenant-boundary tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.basic.models import BasicBase
from app.core.config import Settings
from app.main import create_app


def _client(tmp_path) -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="program-type-test-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application)


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "first_name": "Program",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _facility(client: TestClient, headers: dict[str, str], name: str) -> dict:
    response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={"name": name, "licensed_capacity": 80},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _program(
    client: TestClient,
    headers: dict[str, str],
    facility_id: str,
    *,
    name: str,
    program_type: str,
) -> object:
    return client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility_id,
            "name": name,
            "program_type": program_type,
            "capacity": 40,
        },
    )


def test_facility_supports_one_daycare_and_one_osc_program(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        owner = _register(client, "dual@example.com", "Dual Licence Child Care")
        headers = _headers(owner)
        facility = _facility(client, headers, "Dual Licence Centre")
        other_facility = _facility(client, headers, "Second Centre")

        daycare = _program(
            client,
            headers,
            facility["id"],
            name="Daycare Program",
            program_type="daycare",
        )
        assert daycare.status_code == 201, daycare.text
        assert daycare.json()["program_type"] == "daycare"

        osc = _program(
            client,
            headers,
            facility["id"],
            name="OSC Program",
            program_type="out_of_school_care",
        )
        assert osc.status_code == 201, osc.text
        assert osc.json()["program_type"] == "out_of_school_care"

        listed = client.get(
            f"/api/v1/programs?facility_id={facility['id']}", headers=headers
        )
        assert listed.status_code == 200, listed.text
        assert {item["program_type"] for item in listed.json()} == {
            "daycare",
            "out_of_school_care",
        }

        duplicate_daycare = _program(
            client,
            headers,
            facility["id"],
            name="Another Daycare Program",
            program_type="daycare",
        )
        assert duplicate_daycare.status_code == 409, duplicate_daycare.text
        assert "licence type" in duplicate_daycare.json()["detail"]

        same_type_at_other_facility = _program(
            client,
            headers,
            other_facility["id"],
            name="Second Daycare Program",
            program_type="daycare",
        )
        assert same_type_at_other_facility.status_code == 201

        conflicting_patch = client.patch(
            f"/api/v1/programs/{osc.json()['id']}",
            headers=headers,
            json={"program_type": "daycare"},
        )
        assert conflicting_patch.status_code == 409, conflicting_patch.text


def test_program_type_contract_rejects_missing_null_and_noncanonical_values(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        owner = _register(client, "types@example.com", "Typed Child Care")
        headers = _headers(owner)
        facility = _facility(client, headers, "Typed Centre")

        missing = client.post(
            "/api/v1/programs",
            headers=headers,
            json={"facility_id": facility["id"], "name": "Missing Type"},
        )
        assert missing.status_code == 422

        for index, invalid_type in enumerate(
            (None, "preschool", "other", "osc", "Daycare"), start=1
        ):
            invalid = client.post(
                "/api/v1/programs",
                headers=headers,
                json={
                    "facility_id": facility["id"],
                    "name": f"Invalid Type {index}",
                    "program_type": invalid_type,
                },
            )
            assert invalid.status_code == 422, invalid.text

        daycare = _program(
            client,
            headers,
            facility["id"],
            name="Valid Daycare",
            program_type="daycare",
        )
        assert daycare.status_code == 201, daycare.text

        for invalid_patch in ({"program_type": None}, {"program_type": "preschool"}):
            response = client.patch(
                f"/api/v1/programs/{daycare.json()['id']}",
                headers=headers,
                json=invalid_patch,
            )
            assert response.status_code == 422, response.text


def test_program_type_uniqueness_and_ids_remain_tenant_scoped(tmp_path) -> None:
    client = _client(tmp_path)
    with client:
        first = _register(client, "first-programs@example.com", "First Child Care")
        second = _register(client, "second-programs@example.com", "Second Child Care")
        first_headers = _headers(first)
        second_headers = _headers(second)
        first_facility = _facility(client, first_headers, "First Centre")
        second_facility = _facility(client, second_headers, "Second Centre")

        first_program = _program(
            client,
            first_headers,
            first_facility["id"],
            name="First Daycare",
            program_type="daycare",
        )
        second_program = _program(
            client,
            second_headers,
            second_facility["id"],
            name="Second Daycare",
            program_type="daycare",
        )
        assert first_program.status_code == 201, first_program.text
        assert second_program.status_code == 201, second_program.text

        foreign_list = client.get(
            f"/api/v1/programs?facility_id={first_facility['id']}",
            headers=second_headers,
        )
        assert foreign_list.status_code == 404
        foreign_patch = client.patch(
            f"/api/v1/programs/{first_program.json()['id']}",
            headers=second_headers,
            json={"name": "Cross-tenant rename"},
        )
        assert foreign_patch.status_code == 404

        second_list = client.get("/api/v1/programs", headers=second_headers)
        assert second_list.status_code == 200
        assert [item["id"] for item in second_list.json()] == [second_program.json()["id"]]
