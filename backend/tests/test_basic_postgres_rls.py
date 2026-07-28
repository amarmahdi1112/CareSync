"""Opt-in PostgreSQL proof for runtime-role isolation.

The test is skipped unless BASIC_POSTGRES_TEST_PORT points to an explicitly
disposable, already migrated database with the runtime grants applied.
"""

from __future__ import annotations

import os
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.main import create_app

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
if TEST_PORT and int(TEST_PORT) in {5432, 5433, 5434}:
    raise RuntimeError(
        "BASIC_POSTGRES_TEST_PORT must never target the existing 5432/5433/5434 databases"
    )
pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-password",
            "first_name": "RLS",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_runtime_role_is_non_superuser_and_rls_filters_cross_tenant(tmp_path) -> None:
    del tmp_path
    host = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
    database = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=host,
        database_port=int(TEST_PORT or "0"),
        database_user="caresync_basic_app",
        database_password="",
        database_name=database,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-rls-test-secret-at-least-32-bytes",
    )
    application = create_app(settings)
    identifier = uuid4().hex
    with TestClient(application) as client:
        marketplace = client.post(
            "/api/v1/marketplace/auth/register",
            json={
                "email": f"rls-marketplace-{identifier}@example.com",
                "password": "correct-password",
                "first_name": "RLS",
                "last_name": "Candidate",
            },
        )
        assert marketplace.status_code == 201, marketplace.text
        assert marketplace.json()["organization_membership_created"] is False
        assert marketplace.json()["profile"]["discoverable"] is False
        assert marketplace.json()["profile"]["city"] == ""
        marketplace_headers = {"Authorization": f"Bearer {marketplace.json()['access_token']}"}
        personal = client.patch(
            "/api/v1/marketplace/personal-profile",
            headers=marketplace_headers,
            json={"date_of_birth": "1995-02-10", "phone": "+1 780 555 0144"},
        )
        assert personal.status_code == 200 and personal.json()["profile_complete"] is True
        photo_bytes = BytesIO()
        Image.new("RGB", (200, 150), "blue").save(photo_bytes, "PNG")
        photo = client.put(
            "/api/v1/marketplace/personal-profile/photo",
            headers=marketplace_headers,
            files={"file": ("candidate.png", photo_bytes.getvalue(), "image/png")},
        )
        assert photo.status_code == 201, photo.text
        assert (
            client.get(
                "/api/v1/marketplace/personal-profile/photo", headers=marketplace_headers
            ).status_code
            == 200
        )
        first = _register(
            client,
            f"rls-one-{identifier}@example.com",
            f"RLS Tenant One {identifier}",
        )
        second = _register(
            client,
            f"rls-two-{identifier}@example.com",
            f"RLS Tenant Two {identifier}",
        )
        for registration in (first, second):
            assert registration["user"]["email_verification_status"] == "verified"
            assert registration["user"]["email_verified_at"] is not None
            assert registration["user"]["email_verification_method"] == "temporary_auto_approval"
        first_headers = {"Authorization": f"Bearer {first['access_token']}"}
        organization = client.get("/api/v1/organization", headers=first_headers)
        assert organization.status_code == 200, organization.text
        assert organization.json()["verification_status"] == "verified"
        assert organization.json()["verified_at"] is not None
        assert organization.json()["verification_method"] == "temporary_auto_approval"
        facility = client.post(
            "/api/v1/facilities",
            headers=first_headers,
            json={
                "name": "RLS Verified Centre",
                "license_number": "AB-RLS-VERIFY-001",
                "licensed_capacity": 24,
            },
        )
        assert facility.status_code == 201, facility.text
        assert facility.json()["verification_status"] == "verified"
        assert facility.json()["verified_at"] is not None
        assert facility.json()["verification_method"] == "temporary_auto_approval"
        private_family = client.post(
            "/api/v1/families",
            headers=first_headers,
            json={
                "client_operation_id": str(uuid4()),
                "name": "Tenant One Private Family",
            },
        )
        assert private_family.status_code == 201, private_family.text
        private_child = client.post(
            "/api/v1/children",
            headers=first_headers,
            json={
                "client_operation_id": str(uuid4()),
                "family_id": private_family.json()["id"],
                "first_name": "Private",
                "last_name": "Photo",
                "date_of_birth": "2023-01-01",
            },
        )
        assert private_child.status_code == 201, private_child.text
        image = BytesIO()
        Image.new("RGB", (24, 24), "blue").save(image, format="PNG")
        private_photo = client.put(
            f"/api/v1/children/{private_child.json()['id']}/photo",
            headers=first_headers,
            files={"file": ("private.png", image.getvalue(), "image/png")},
        )
        assert private_photo.status_code == 200, private_photo.text

    runtime_url = URL.create(
        "postgresql+psycopg",
        username="caresync_basic_app",
        host=host,
        port=int(TEST_PORT or "0"),
        database=database,
    )
    engine = create_engine(runtime_url)
    first_user = UUID(first["user"]["id"])
    second_user = UUID(second["user"]["id"])
    first_org = UUID(first["user"]["organization_id"])
    second_org = UUID(second["user"]["organization_id"])
    with engine.connect() as connection:
        role_flags = connection.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        assert role_flags == (False, False, False, False)
        program_rls_flags = connection.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE oid = 'facility_programs'::regclass"
            )
        ).one()
        assert program_rls_flags == (True, True)
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE schemaname = current_schema() "
                    "AND tablename = 'facility_programs' "
                    "AND policyname = 'facility_programs_tenant'"
                )
            ).scalar_one()
            == 1
        )
        photo_rls_flags = connection.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE oid = 'child_profile_photos'::regclass"
            )
        ).one()
        assert photo_rls_flags == (True, True)
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE schemaname = current_schema() "
                    "AND tablename = 'child_profile_photos' "
                    "AND policyname = 'child_profile_photos_tenant'"
                )
            ).scalar_one()
            == 1
        )
        assert connection.execute(
            text(
                "SELECT has_table_privilege(current_user, 'child_profile_photos', "
                "'SELECT,INSERT,UPDATE,DELETE')"
            )
        ).scalar_one()
        for table_name in ("daily_care_records", "daily_care_record_events"):
            rls_flags = connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE oid = CAST(:table_name AS regclass)"
                ),
                {"table_name": table_name},
            ).one()
            assert rls_flags == (True, True)
        care_policies = set(
            connection.execute(
                text(
                    "SELECT policyname FROM pg_policies "
                    "WHERE schemaname = current_schema() "
                    "AND tablename IN ('daily_care_records','daily_care_record_events')"
                )
            ).scalars()
        )
        assert care_policies == {
            "daily_care_records_tenant",
            "daily_care_record_events_select",
            "daily_care_record_events_insert",
        }
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            assert connection.execute(
                text("SELECT has_table_privilege(current_user, 'daily_care_records', :privilege)"),
                {"privilege": privilege},
            ).scalar_one()
        assert not connection.execute(
            text("SELECT has_table_privilege(current_user, 'daily_care_records', 'DELETE')")
        ).scalar_one()
        for privilege in ("SELECT", "INSERT"):
            assert connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'daily_care_record_events', :privilege)"
                ),
                {"privilege": privilege},
            ).scalar_one()
        for privilege in ("UPDATE", "DELETE"):
            assert not connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, "
                    "'daily_care_record_events', :privilege)"
                ),
                {"privilege": privilege},
            ).scalar_one()
        regulated_projection_tables = (
            "medication_plans",
            "medication_administrations",
            "incident_records",
        )
        regulated_event_tables = (
            "medication_plan_events",
            "medication_administration_events",
            "incident_record_events",
        )
        for table_name in (*regulated_projection_tables, *regulated_event_tables):
            assert connection.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity "
                    "FROM pg_class WHERE oid = CAST(:table_name AS regclass)"
                ),
                {"table_name": table_name},
            ).scalar_one()
        for table_name in regulated_projection_tables:
            assert set(
                connection.execute(
                    text(
                        "SELECT policyname FROM pg_policies "
                        "WHERE schemaname = current_schema() AND tablename = :table_name"
                    ),
                    {"table_name": table_name},
                ).scalars()
            ) == {f"{table_name}_tenant"}
            for privilege in ("SELECT", "INSERT", "UPDATE"):
                assert connection.execute(
                    text("SELECT has_table_privilege(current_user, :table_name, :privilege)"),
                    {"table_name": table_name, "privilege": privilege},
                ).scalar_one()
            assert not connection.execute(
                text("SELECT has_table_privilege(current_user, :table_name, 'DELETE')"),
                {"table_name": table_name},
            ).scalar_one()
        for table_name in regulated_event_tables:
            assert set(
                connection.execute(
                    text(
                        "SELECT policyname FROM pg_policies "
                        "WHERE schemaname = current_schema() AND tablename = :table_name"
                    ),
                    {"table_name": table_name},
                ).scalars()
            ) == {f"{table_name}_select", f"{table_name}_insert"}
            for privilege in ("SELECT", "INSERT"):
                assert connection.execute(
                    text("SELECT has_table_privilege(current_user, :table_name, :privilege)"),
                    {"table_name": table_name, "privilege": privilege},
                ).scalar_one()
            for privilege in ("UPDATE", "DELETE"):
                assert not connection.execute(
                    text("SELECT has_table_privilege(current_user, :table_name, :privilege)"),
                    {"table_name": table_name, "privilege": privilege},
                ).scalar_one()
        transaction = connection.begin_nested()
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(first_user)},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(first_org)},
        )
        visible_orgs = set(connection.execute(text("SELECT id FROM organizations")).scalars())
        assert visible_orgs == {first_org}
        assert (
            connection.execute(
                text("SELECT id FROM organizations WHERE id = :id"), {"id": second_org}
            ).first()
            is None
        )
        visible_families = list(connection.execute(text("SELECT name FROM families")).scalars())
        assert visible_families == ["Tenant One Private Family"]
        assert (
            connection.execute(text("SELECT count(*) FROM child_profile_photos")).scalar_one() == 1
        )
        transaction.rollback()

        transaction = connection.begin_nested()
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(second_user)},
        )
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(second_org)},
        )
        assert (
            connection.execute(text("SELECT count(*) FROM child_profile_photos")).scalar_one() == 0
        )
        transaction.rollback()

        transaction = connection.begin_nested()
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(first_org)},
        )
        with pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "INSERT INTO organizations "
                    "(id,name,status,timezone,preferences,created_at,updated_at) "
                    "VALUES (:id,'Forbidden','draft','America/Edmonton','{}',now(),now())"
                ),
                {"id": second_org},
            )
        transaction.rollback()
    engine.dispose()
