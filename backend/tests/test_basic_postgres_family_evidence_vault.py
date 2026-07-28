"""Opt-in PostgreSQL proofs for the 0029A1 private evidence vault."""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Barrier, Thread
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.main import create_app
from tests.test_basic_family_evidence_vault import _clean_scan, _scan, _upload
from tests.test_basic_postgres_family_authority_api import (
    _family,
    _register,
    _role_headers,
)

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
TEST_HOST = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
TEST_DATABASE = os.getenv("BASIC_POSTGRES_TEST_DATABASE", "caresync")
RUNTIME_ROLE = "caresync_basic_app"
CURRENT_REVISION = "0029A1_family_evidence_vault"

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


def _url(user: str) -> URL:
    port = int(TEST_PORT or "0")
    assert TEST_HOST in {"127.0.0.1", "localhost", "::1"}
    assert port not in {5432, 5433, 5434}, "Retained CareSync ports are forbidden"
    return URL.create(
        "postgresql+psycopg",
        username=user,
        host=TEST_HOST,
        port=port,
        database=TEST_DATABASE,
    )


def _settings(vault_path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=TEST_HOST,
        database_port=int(TEST_PORT or "0"),
        database_user=RUNTIME_ROLE,
        database_password="",
        database_name=TEST_DATABASE,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        family_evidence_vault_path=vault_path,
        jwt_secret="postgres-family-evidence-vault-secret-32-bytes",
    )


@dataclass(frozen=True)
class VaultHarness:
    admin: Engine
    application: object
    client: TestClient
    settings: Settings


@pytest.fixture
def vault_harness(tmp_path, monkeypatch) -> VaultHarness:
    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", _clean_scan)
    admin = create_engine(_url("postgres"))
    with admin.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            CURRENT_REVISION
        )
    settings = _settings(tmp_path / "vault")
    application = create_app(settings)
    with TestClient(application) as client:
        yield VaultHarness(admin, application, client, settings)
    admin.dispose()


def _direct_review(
    admin: Engine,
    *,
    organization_id: UUID,
    family_id: UUID,
    evidence_id: UUID,
    actor_user_id: UUID,
    epistemic_status: str,
) -> DBAPIError:
    operation_id = uuid4()
    with pytest.raises(DBAPIError) as raised, admin.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.current_organization_id',:value,true)"),
            {"value": str(organization_id)},
        )
        connection.execute(
            text("SELECT set_config('app.current_user_id',:value,true)"),
            {"value": str(actor_user_id)},
        )
        connection.execute(
            text("SELECT set_config('app.current_childcare_operation_id',:value,true)"),
            {"value": str(operation_id)},
        )
        connection.execute(
            text(
                "INSERT INTO childcare_command_receipts "
                "(id,organization_id,client_operation_id,command_type,target_type,target_id,"
                "request_hash,actor_user_id,committed_version,outcome) VALUES "
                "(:id,:organization_id,:operation_id,'family.authority.evidence.review',"
                "'authority_evidence',:target_id,:request_hash,:actor_user_id,2,"
                "jsonb_build_object('action_route',CAST(:action_route AS text)))"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "operation_id": operation_id,
                "target_id": evidence_id,
                "request_hash": uuid4().hex * 2,
                "actor_user_id": actor_user_id,
                "action_route": (f"/families/{family_id}?authority_evidence_id={evidence_id}"),
            },
        )
        connection.execute(
            text(
                "INSERT INTO family_authority_evidence_assessments "
                "(id,organization_id,family_id,evidence_id,version_number,decision,"
                "assessed_epistemic_status,actor_user_id,created_operation_id) VALUES "
                "(:id,:organization_id,:family_id,:evidence_id,2,'reviewed',"
                ":epistemic_status,:actor_user_id,:operation_id)"
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "family_id": family_id,
                "evidence_id": evidence_id,
                "epistemic_status": epistemic_status,
                "actor_user_id": actor_user_id,
                "operation_id": operation_id,
            },
        )
    return raised.value


def test_postgres_vault_catalog_rls_grants_and_trigger_functions() -> None:
    admin = create_engine(_url("postgres"))
    try:
        with admin.connect() as connection:
            assert dict(
                connection.execute(
                    text(
                        "SELECT relname,(relrowsecurity AND relforcerowsecurity) "
                        "FROM pg_class WHERE relname IN "
                        "('family_authority_evidence_objects',"
                        "'family_authority_evidence_object_assessments')"
                    )
                )
                .tuples()
                .all()
            ) == {
                "family_authority_evidence_objects": True,
                "family_authority_evidence_object_assessments": True,
            }
            triggers = set(
                connection.execute(
                    text(
                        "SELECT relation.relname,trigger.tgname,procedure.proname "
                        "FROM pg_trigger trigger "
                        "JOIN pg_class relation ON relation.oid=trigger.tgrelid "
                        "JOIN pg_proc procedure ON procedure.oid=trigger.tgfoid "
                        "WHERE NOT trigger.tgisinternal"
                    )
                )
            )
            assert {
                (
                    "family_authority_evidence_assessments",
                    "trg_family_authority_evidence_assessments_review_guard",
                    "caresync_family_evidence_review_guard",
                ),
                (
                    "family_authority_evidence_objects",
                    "trg_family_authority_evidence_objects_write_guard",
                    "caresync_family_evidence_object_write_guard",
                ),
                (
                    "family_authority_evidence_object_assessments",
                    "trg_family_authority_evidence_object_assessments_invariant",
                    "caresync_family_evidence_object_invariant",
                ),
            } <= triggers
            assert connection.scalar(
                text(
                    "SELECT has_table_privilege(:role,"
                    "'family_authority_evidence_objects','SELECT,INSERT')"
                ),
                {"role": RUNTIME_ROLE},
            )
            assert connection.scalar(
                text(
                    "SELECT has_column_privilege(:role,"
                    "'family_authority_evidence_objects','status','UPDATE')"
                ),
                {"role": RUNTIME_ROLE},
            )
            assert not connection.scalar(
                text(
                    "SELECT has_column_privilege(:role,"
                    "'family_authority_evidence_objects','storage_reference','UPDATE')"
                ),
                {"role": RUNTIME_ROLE},
            )
            assert not connection.scalar(
                text(
                    "SELECT has_table_privilege(:role,'family_authority_evidence_objects','DELETE')"
                ),
                {"role": RUNTIME_ROLE},
            )
            for signature in (
                "caresync_family_evidence_object_write_guard()",
                "caresync_family_evidence_object_invariant()",
                "caresync_family_evidence_object_link_guard()",
                "caresync_family_evidence_review_guard()",
            ):
                assert not connection.scalar(
                    text("SELECT has_function_privilege(:role,:signature,'EXECUTE')"),
                    {"role": RUNTIME_ROLE, "signature": f"public.{signature}"},
                )
    finally:
        admin.dispose()


def test_postgres_upload_and_scan_exact_replay_return_persisted_receipts(
    vault_harness: VaultHarness,
) -> None:
    client = vault_harness.client
    _, owner_headers = _register(client, "A1ReceiptReplay")
    family = _family(client, owner_headers, label="A1 Receipt Replay")

    upload_operation = str(uuid4())
    uploaded = _upload(
        client,
        owner_headers,
        family["id"],
        operation_id=upload_operation,
    )
    assert uploaded.status_code == 201, uploaded.text
    upload_replay = _upload(
        client,
        owner_headers,
        family["id"],
        operation_id=upload_operation,
    )
    assert upload_replay.status_code == 201, upload_replay.text
    assert upload_replay.json() == {**uploaded.json(), "replayed": True}

    object_id = uploaded.json()["resource"]["id"]
    scan_operation = str(uuid4())
    scanned = _scan(
        client,
        owner_headers,
        family["id"],
        object_id,
        scan_operation,
    )
    assert scanned.status_code == 200, scanned.text
    scan_replay = _scan(
        client,
        owner_headers,
        family["id"],
        object_id,
        scan_operation,
    )
    assert scan_replay.status_code == 200, scan_replay.text
    assert scan_replay.json() == {**scanned.json(), "replayed": True}


def test_postgres_review_guard_enforces_maker_checker_epistemic_and_uploader(
    vault_harness: VaultHarness,
) -> None:
    admin, client = vault_harness.admin, vault_harness.client
    auth, owner_headers = _register(client, "A1ReviewGuard")
    organization_id = UUID(auth["user"]["organization_id"])
    owner_id = UUID(auth["user"]["id"])
    family = _family(client, owner_headers, label="A1 Review Guard")
    family_id = UUID(family["id"])
    administrator_id, administrator_headers = _role_headers(
        admin,
        client,
        organization_id=organization_id,
        role_key="administrator",
    )

    attestation = client.post(
        f"/api/v1/families/{family_id}/authority/evidence",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "evidence_kind": "guardian_attestation",
            "source_label": "direct PostgreSQL review guard",
        },
    )
    assert attestation.status_code == 201, attestation.text
    attestation_id = UUID(attestation.json()["resource"]["id"])
    api_self_review = client.post(
        f"/api/v1/families/{family_id}/authority/evidence/{attestation_id}/review",
        headers=owner_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_version": 1,
            "assessed_epistemic_status": "reported",
        },
    )
    assert api_self_review.status_code == 409, api_self_review.text
    assert api_self_review.json()["detail"]["code"] == "maker_checker_required"
    self_review = _direct_review(
        admin,
        organization_id=organization_id,
        family_id=family_id,
        evidence_id=attestation_id,
        actor_user_id=owner_id,
        epistemic_status="reported",
    )
    assert self_review.orig.diag.constraint_name == ("ck_authority_evidence_maker_checker")
    false_observation = _direct_review(
        admin,
        organization_id=organization_id,
        family_id=family_id,
        evidence_id=attestation_id,
        actor_user_id=administrator_id,
        epistemic_status="document_observed",
    )
    assert false_observation.orig.diag.constraint_name == (
        "ck_authority_evidence_review_epistemic_kind"
    )
    reviewed = client.post(
        f"/api/v1/families/{family_id}/authority/evidence/{attestation_id}/review",
        headers=administrator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "expected_version": 1,
            "assessed_epistemic_status": "reported",
        },
    )
    assert reviewed.status_code == 200, reviewed.text

    uploaded = _upload(client, owner_headers, str(family_id))
    assert uploaded.status_code == 201, uploaded.text
    object_id = uploaded.json()["resource"]["id"]
    assert _scan(client, owner_headers, str(family_id), object_id).status_code == 200
    document = client.post(
        f"/api/v1/families/{family_id}/authority/evidence",
        headers=administrator_headers,
        json={
            "client_operation_id": str(uuid4()),
            "evidence_kind": "custody_document",
            "source_label": "uploader separation",
            "evidence_object_id": object_id,
        },
    )
    assert document.status_code == 201, document.text
    uploader_review = _direct_review(
        admin,
        organization_id=organization_id,
        family_id=family_id,
        evidence_id=UUID(document.json()["resource"]["id"]),
        actor_user_id=owner_id,
        epistemic_status="document_observed",
    )
    assert uploader_review.orig.diag.constraint_name == ("ck_authority_evidence_maker_checker")
    assert "uploader cannot approve" in str(uploader_review.orig)


def test_postgres_concurrent_object_binding_has_one_typed_winner(
    vault_harness: VaultHarness,
) -> None:
    first_client = vault_harness.client
    auth, headers = _register(first_client, "A1BindRace")
    family = _family(first_client, headers, label="A1 Bind Race")
    family_id = family["id"]
    uploaded = _upload(first_client, headers, family_id)
    object_id = uploaded.json()["resource"]["id"]
    assert _scan(first_client, headers, family_id, object_id).status_code == 200
    barrier = Barrier(3)
    responses = []
    failures: list[BaseException] = []
    second_application = create_app(vault_harness.settings)

    with TestClient(second_application, raise_server_exceptions=False) as second_client:

        def bind(client: TestClient) -> None:
            try:
                barrier.wait(timeout=5)
                responses.append(
                    client.post(
                        f"/api/v1/families/{family_id}/authority/evidence",
                        headers=headers,
                        json={
                            "client_operation_id": str(uuid4()),
                            "evidence_kind": "custody_document",
                            "source_label": "single-use race",
                            "evidence_object_id": object_id,
                        },
                    )
                )
            except BaseException as error:  # pragma: no cover - diagnostic capture
                failures.append(error)

        threads = [
            Thread(target=bind, args=(first_client,), daemon=True),
            Thread(target=bind, args=(second_client,), daemon=True),
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=15)

    assert not failures
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(response.status_code for response in responses) == [201, 409]
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()["detail"]["code"] == "evidence_object_already_bound"
    organization_id = UUID(auth["user"]["organization_id"])
    with vault_harness.admin.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM family_authority_evidence "
                    "WHERE organization_id=:organization_id AND evidence_object_id=:object_id"
                ),
                {"organization_id": organization_id, "object_id": UUID(object_id)},
            )
            == 1
        )
