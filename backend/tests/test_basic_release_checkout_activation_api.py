"""Acceptance coverage for the explicit 0035 facility activation workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.basic.models import (
    AuditEvent,
    ChildcareCommandReceipt,
    FacilityReleaseCheckoutActivation,
    RealtimeEvent,
)
from app.basic.release_checkout_activation import _activation_command_available
from tests.test_basic_family_release_context_api import (
    _check_in_child,
    _client,
    _clock_in,
    _educator,
    _facility_tree,
    _family_child_and_enrollment,
    _register,
)

REVISION = "0035_release_checkout_activation"
CONFIRMATION = "ACTIVATE VERIFIED RELEASE CHECKOUT"


def test_postgres_activation_probe_uses_valid_current_user_keyword() -> None:
    class _Dialect:
        name = "postgresql"

    class _Bind:
        dialect = _Dialect()

    class _Session:
        bind = _Bind()

        def get_bind(self):
            return self.bind

        def scalar(self, statement, _parameters):
            rendered = str(statement)
            assert "pg_catalog.current_user" not in rendered
            assert "has_function_privilege(current_user" in rendered
            return True

    assert _activation_command_available(_Session(), runtime_enabled=True) is True


def _command(auth: dict, facility_id: str, operation_id: str | None = None) -> dict:
    return {
        "schema_version": "release-checkout-activation-command-v1",
        "organization_id": auth["user"]["organization_id"],
        "facility_id": facility_id,
        "client_operation_id": operation_id or str(uuid4()),
        "activation_policy_version": "normal_verified_release_v1",
        "authority_records_reviewed": True,
        "verification_workflow_reviewed": True,
        "legacy_checkout_closure_understood": True,
        "irreversible_activation_understood": True,
        "confirmation_text": CONFIRMATION,
    }


def _activate_runtime(application) -> None:
    application.state.family_release_checkout_foundation_present = True
    application.state.family_release_checkout_enabled = True


def test_status_is_private_explicit_and_never_auto_activates(tmp_path, monkeypatch) -> None:
    client, application, _ = _client(tmp_path, monkeypatch, revision=REVISION)
    with client:
        _activate_runtime(application)
        auth, headers = _register(client, suffix="activation-status")
        facility, _, _ = _facility_tree(client, headers)
        response = client.get(
            f"/api/v1/facilities/{facility['id']}/release-checkout-activation",
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
        body = response.json()
        assert body["organization_id"] == auth["user"]["organization_id"]
        assert body["facility_id"] == facility["id"]
        assert body["activated"] is False
        assert body["legacy_checkout_allowed"] is True
        assert body["can_activate"] is True
        assert body["confirmation_text"] == CONFIRMATION
        assert all(item["satisfied"] for item in body["prerequisites"])

        with application.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(FacilityReleaseCheckoutActivation)
            ) == 0


def test_activation_is_one_way_exactly_retryable_and_emits_one_signal(
    tmp_path,
    monkeypatch,
) -> None:
    client, application, _ = _client(tmp_path, monkeypatch, revision=REVISION)
    with client:
        _activate_runtime(application)
        auth, headers = _register(client, suffix="activation-commit")
        facility, _, rooms = _facility_tree(client, headers)
        operation_id = str(uuid4())
        payload = _command(auth, facility["id"], operation_id)
        path = f"/api/v1/facilities/{facility['id']}/release-checkout-activation"

        first = client.post(path, headers=headers, json=payload)
        replay = client.post(path, headers=headers, json=payload)

        assert first.status_code == 200, first.text
        assert replay.status_code == 200, replay.text
        assert first.headers["cache-control"] == "private, no-store"
        assert first.json()["replayed"] is False
        assert replay.json()["replayed"] is True
        assert replay.json()["receipt"] == first.json()["receipt"]
        assert first.json()["status"]["activated"] is True
        assert first.json()["status"]["legacy_checkout_allowed"] is False
        assert first.json()["status"]["can_activate"] is False
        assert first.json()["receipt"]["client_operation_id"] == operation_id
        assert first.json()["receipt"]["action_route"] == "/settings?section=facility"

        organization_id = UUID(auth["user"]["organization_id"])
        facility_id = UUID(facility["id"])
        with application.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count())
                .select_from(FacilityReleaseCheckoutActivation)
                .where(
                    FacilityReleaseCheckoutActivation.organization_id == organization_id,
                    FacilityReleaseCheckoutActivation.facility_id == facility_id,
                )
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(ChildcareCommandReceipt)
                .where(
                    ChildcareCommandReceipt.organization_id == organization_id,
                    ChildcareCommandReceipt.command_type
                    == "facility.release_checkout.activate",
                )
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.organization_id == organization_id,
                    AuditEvent.action == "facility.release_checkout.activated",
                )
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(RealtimeEvent)
                .where(
                    RealtimeEvent.organization_id == organization_id,
                    RealtimeEvent.event_type
                    == "facility.release_checkout.activated",
                )
            ) == 1

        _, child = _family_child_and_enrollment(
            client,
            headers,
            facility,
            rooms[0],
        )
        _clock_in(client, headers, facility["id"])
        _check_in_child(client, headers, child["id"], facility["id"])
        legacy_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        )
        assert legacy_checkout.status_code == 409
        assert legacy_checkout.json()["detail"]["code"] == (
            "verified_release_checkout_required"
        )

        second_operation = client.post(
            path,
            headers=headers,
            json=_command(auth, facility["id"]),
        )
        assert second_operation.status_code == 409
        assert second_operation.json()["detail"]["code"] == (
            "release_activation_already_active"
        )
        assert second_operation.headers["cache-control"] == "private, no-store"


def test_activation_requires_completed_authority_records_for_open_children(
    tmp_path,
    monkeypatch,
) -> None:
    client, application, _ = _client(tmp_path, monkeypatch, revision=REVISION)
    with client:
        _activate_runtime(application)
        auth, headers = _register(client, suffix="activation-readiness")
        facility, _, rooms = _facility_tree(client, headers)
        _family_child_and_enrollment(client, headers, facility, rooms[0])
        path = f"/api/v1/facilities/{facility['id']}/release-checkout-activation"

        status_response = client.get(path, headers=headers)
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["open_enrollment_children"] == 1
        assert status_body["release_ready_children"] == 0
        assert status_body["children_needing_authority_review"] == 1
        assert status_body["can_activate"] is False
        assert next(
            item
            for item in status_body["prerequisites"]
            if item["code"] == "authority_records_complete"
        )["satisfied"] is False

        activation = client.post(
            path,
            headers=headers,
            json=_command(auth, facility["id"]),
        )
        assert activation.status_code == 409
        assert activation.json()["detail"]["code"] == (
            "release_activation_authority_records_incomplete"
        )
        with application.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(FacilityReleaseCheckoutActivation)
            ) == 0


def test_activation_requires_privileged_role_and_exact_tenant_facility(
    tmp_path,
    monkeypatch,
) -> None:
    client, application, _ = _client(tmp_path, monkeypatch, revision=REVISION)
    with client:
        _activate_runtime(application)
        auth, owner_headers = _register(client, suffix="activation-scope")
        facility, _, rooms = _facility_tree(client, owner_headers)
        educator_headers, _ = _educator(
            client,
            owner_headers,
            facility_id=facility["id"],
            room_id=rooms[0]["id"],
            suffix="activation",
        )
        path = f"/api/v1/facilities/{facility['id']}/release-checkout-activation"

        forbidden = client.get(path, headers=educator_headers)
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"]["code"] == "release_activation_forbidden"
        assert forbidden.headers["cache-control"] == "private, no-store"

        other_auth, other_headers = _register(client, suffix="activation-other-tenant")
        foreign = client.get(path, headers=other_headers)
        assert foreign.status_code == 404
        assert foreign.json()["detail"]["code"] == "release_activation_facility_not_found"

        mismatched_payload = _command(auth, facility["id"])
        mismatched_payload["facility_id"] = str(uuid4())
        mismatch = client.post(path, headers=owner_headers, json=mismatched_payload)
        assert mismatch.status_code == 422
        assert mismatch.json()["detail"]["code"] == (
            "release_activation_facility_mismatch"
        )

        wrong_organization = _command(other_auth, facility["id"])
        scope = client.post(path, headers=owner_headers, json=wrong_organization)
        assert scope.status_code == 403
        assert scope.json()["detail"]["code"] == "release_activation_scope_mismatch"


def test_activation_rejects_incomplete_confirmation_and_read_only_database(
    tmp_path,
    monkeypatch,
) -> None:
    client, application, _ = _client(tmp_path, monkeypatch, revision=REVISION)
    with client:
        _activate_runtime(application)
        auth, headers = _register(client, suffix="activation-confirmation")
        facility, _, _ = _facility_tree(client, headers)
        path = f"/api/v1/facilities/{facility['id']}/release-checkout-activation"
        payload = _command(auth, facility["id"])
        payload["irreversible_activation_understood"] = False

        incomplete = client.post(path, headers=headers, json=payload)
        assert incomplete.status_code == 422

        application.state.settings.database_read_only = True
        status_response = client.get(path, headers=headers)
        assert status_response.status_code == 200
        assert status_response.json()["database_writable"] is False
        assert status_response.json()["can_activate"] is False
        blocked = client.post(path, headers=headers, json=_command(auth, facility["id"]))
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == (
            "release_activation_database_read_only"
        )
