"""Phase 2B medication and incident workflow acceptance tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.basic.models import (
    AuditEvent,
    IncidentRecordEvent,
    MedicationAdministrationEvent,
    MedicationPlanEvent,
    Role,
)
from tests.test_basic_daily_care import (
    SERVICE_DATE,
    _check_in,
    _child,
    _client,
    _facility_tree,
    _family,
    _headers,
    _instant,
    _invite_educator,
    _register,
)


def _plan_payload(facility_id: str, child_id: str, operation_id: str) -> dict:
    return {
        "facility_id": facility_id,
        "child_id": child_id,
        "medication_name": "Prescribed medication",
        "dosage": "5 mL",
        "route": "oral",
        "label_directions": "Use exactly as written on the original pharmacy label.",
        "scheduled_times": ["09:00"],
        "as_needed": False,
        "start_date": SERVICE_DATE.isoformat(),
        "end_date": SERVICE_DATE.isoformat(),
        "medication_kind": "non_emergency",
        "storage_method": "locked_inaccessible",
        "storage_instructions": "Locked cabinet inaccessible to children.",
        "client_operation_id": operation_id,
    }


def _active_plan(client, headers, facility_id: str, child_id: str) -> dict:
    created = client.post(
        "/api/v1/medications/plans",
        headers=headers,
        json=_plan_payload(facility_id, child_id, str(uuid4())),
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    authorized = client.post(
        f"/api/v1/medications/plans/{plan['id']}/authorization",
        headers=headers,
        json={
            "guardian_id": plan["eligible_guardians"][0]["id"],
            "signed_authorization_reference": f"paper-{plan['id']}",
            "authorization_signed_at": _instant(7),
            "valid_until": SERVICE_DATE.isoformat(),
            "expected_version": plan["version"],
            "client_operation_id": str(uuid4()),
        },
    )
    assert authorized.status_code == 200, authorized.text
    activated = client.post(
        f"/api/v1/medications/plans/{plan['id']}/activate",
        headers=headers,
        json={
            "original_labelled_container_confirmed": True,
            "label_directions_confirmed": True,
            "expected_version": authorized.json()["version"],
            "client_operation_id": str(uuid4()),
        },
    )
    assert activated.status_code == 200, activated.text
    return activated.json()


def test_written_authorization_activation_and_medication_ledger(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "medication-owner@example.com", "Medication Centre")
        headers = _headers(auth)
        facility, program, rooms = _facility_tree(client, headers, "Medication")
        family = _family(client, headers, "Medication")
        child = _child(
            client,
            headers,
            family["id"],
            "Safiya",
            facility,
            program,
            rooms[0],
        )
        day = _check_in(client, headers, child["id"], facility["id"])
        replay_actor_headers = _invite_educator(
            client,
            headers,
            facility["id"],
            rooms[0]["id"],
            "medication-replay-educator@example.com",
        )

        plan_operation = str(uuid4())
        plan_payload = _plan_payload(facility["id"], child["id"], plan_operation)
        created = client.post("/api/v1/medications/plans", headers=headers, json=plan_payload)
        assert created.status_code == 201, created.text
        assert created.headers["cache-control"] == "private, no-store"
        plan = created.json()
        assert plan["status"] == "draft"
        assert plan["authorization_status"] == "not_recorded"
        assert plan["signed_authorization_required"] is True
        assert plan["authorization_is_current"] is False
        assert len(plan["eligible_guardians"]) == 1

        changed_replay = dict(plan_payload)
        changed_replay["dosage"] = "10 mL"
        assert (
            client.post(
                "/api/v1/medications/plans", headers=headers, json=changed_replay
            ).status_code
            == 409
        )
        cannot_activate = client.post(
            f"/api/v1/medications/plans/{plan['id']}/activate",
            headers=headers,
            json={
                "original_labelled_container_confirmed": True,
                "label_directions_confirmed": True,
                "expected_version": plan["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert cannot_activate.status_code == 409

        authorization = client.post(
            f"/api/v1/medications/plans/{plan['id']}/authorization",
            headers=headers,
            json={
                "guardian_id": plan["eligible_guardians"][0]["id"],
                "signed_authorization_reference": "paper-record-MED-001",
                "authorization_signed_at": _instant(7),
                "valid_until": SERVICE_DATE.isoformat(),
                "expected_version": plan["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert authorization.status_code == 200, authorization.text
        plan = authorization.json()
        assert plan["authorization_status"] == "verified"
        assert plan["authorization_is_current"] is True

        activated = client.post(
            f"/api/v1/medications/plans/{plan['id']}/activate",
            headers=headers,
            json={
                "original_labelled_container_confirmed": True,
                "label_directions_confirmed": True,
                "expected_version": plan["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert activated.status_code == 200, activated.text
        plan = activated.json()
        assert plan["status"] == "active"
        assert plan["original_labelled_container_verified_at"] is not None

        replaced_authorization = client.post(
            f"/api/v1/medications/plans/{plan['id']}/authorization",
            headers=headers,
            json={
                "guardian_id": plan["eligible_guardians"][0]["id"],
                "signed_authorization_reference": "paper-record-MED-001-reissued",
                "authorization_signed_at": _instant(7, 5),
                "valid_until": SERVICE_DATE.isoformat(),
                "expected_version": plan["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert replaced_authorization.status_code == 200, replaced_authorization.text
        plan = replaced_authorization.json()
        assert plan["status"] == "draft"
        assert plan["original_labelled_container_verified_at"] is None
        reactivated = client.post(
            f"/api/v1/medications/plans/{plan['id']}/activate",
            headers=headers,
            json={
                "original_labelled_container_confirmed": True,
                "label_directions_confirmed": True,
                "expected_version": plan["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert reactivated.status_code == 200, reactivated.text
        plan = reactivated.json()

        administration_operation = str(uuid4())
        administration_payload = {
            "medication_plan_id": plan["id"],
            "attendance_day_id": day["id"],
            "outcome": "administered",
            "scheduled_for": "09:00",
            "occurred_at": _instant(9),
            "amount": "5 mL",
            "note": "Administered from original labelled container.",
            "client_operation_id": administration_operation,
        }
        administered = client.post(
            "/api/v1/medications/administrations",
            headers=headers,
            json=administration_payload,
        )
        assert administered.status_code == 201, administered.text
        assert administered.headers["cache-control"] == "private, no-store"
        record = administered.json()
        assert record["scheduled_for"] == "09:00"
        assert record["plan_snapshot"]["dosage"] == "5 mL"
        assert record["plan_snapshot"]["plan_version"] == plan["version"]
        foreign_actor_replay = client.post(
            "/api/v1/medications/administrations",
            headers=replay_actor_headers,
            json=administration_payload,
        )
        assert foreign_actor_replay.status_code == 404

        changed_administration = dict(administration_payload)
        changed_administration.update(
            {"outcome": "omitted", "amount": None, "reason": "Not available"}
        )
        assert (
            client.post(
                "/api/v1/medications/administrations",
                headers=headers,
                json=changed_administration,
            ).status_code
            == 409
        )
        duplicate = dict(administration_payload)
        duplicate["client_operation_id"] = str(uuid4())
        assert (
            client.post(
                "/api/v1/medications/administrations", headers=headers, json=duplicate
            ).status_code
            == 409
        )

        with application.state.database.session_factory() as session:
            educator_role = session.scalar(select(Role).where(Role.key == "educator"))
            assert educator_role is not None
            if "medication:correct" not in educator_role.permissions:
                educator_role.permissions = [
                    *educator_role.permissions,
                    "medication:correct",
                ]
            session.commit()
        correction_operation = str(uuid4())
        correction_payload = {
            "medication_plan_id": plan["id"],
            "attendance_day_id": day["id"],
            "outcome": "refused",
            "scheduled_for": "09:00",
            "occurred_at": _instant(9, 5),
            "reason": "Child refused the labelled dose.",
            "note": "Parent notification initiated.",
            "correction_reason": "Original entry selected the wrong outcome.",
            "expected_version": record["version"],
            "client_operation_id": correction_operation,
        }
        correction = client.put(
            f"/api/v1/medications/administrations/{record['id']}/correction",
            headers=replay_actor_headers,
            json=correction_payload,
        )
        assert correction.status_code == 200, correction.text
        record = correction.json()
        assert record["outcome"] == "refused"
        assert record["was_corrected"] is True
        with application.state.database.session_factory() as session:
            educator_role = session.scalar(select(Role).where(Role.key == "educator"))
            assert educator_role is not None
            educator_role.permissions = [
                permission
                for permission in educator_role.permissions
                if permission != "medication:correct"
            ]
            if "medication:correct_own" not in educator_role.permissions:
                educator_role.permissions = [
                    *educator_role.permissions,
                    "medication:correct_own",
                ]
            session.commit()
        unauthorized_correction_replay = client.put(
            f"/api/v1/medications/administrations/{record['id']}/correction",
            headers=replay_actor_headers,
            json=correction_payload,
        )
        assert unauthorized_correction_replay.status_code == 404

        history = client.get(
            f"/api/v1/medications/administrations/{record['id']}/history",
            headers=headers,
        )
        assert history.status_code == 200, history.text
        assert [item["event_type"] for item in history.json()] == ["recorded", "corrected"]

        stranded_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": _instant(8, 30),
            },
        )
        assert stranded_checkout.status_code == 409
        assert "medication" in stranded_checkout.json()["detail"].lower()

        voided = client.post(
            f"/api/v1/medications/administrations/{record['id']}/void",
            headers=headers,
            json={
                "reason": "Duplicate paper transcription.",
                "expected_version": record["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert voided.status_code == 200, voided.text
        assert voided.json()["voided_at"] is not None

        replacement = dict(administration_payload)
        replacement.update(
            {
                "outcome": "omitted",
                "amount": None,
                "reason": "Medication was unavailable; parent notified.",
                "client_operation_id": str(uuid4()),
            }
        )
        replaced = client.post(
            "/api/v1/medications/administrations", headers=headers, json=replacement
        )
        assert replaced.status_code == 201, replaced.text

        revoked = client.post(
            f"/api/v1/medications/plans/{plan['id']}/revoke-authorization",
            headers=headers,
            json={
                "reason": "Parent withdrew the separate written authorization.",
                "expected_version": plan["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["authorization_status"] == "revoked"
        blocked_after_revocation = dict(replacement)
        blocked_after_revocation.update(
            {"scheduled_for": None, "client_operation_id": str(uuid4())}
        )
        assert (
            client.post(
                "/api/v1/medications/administrations",
                headers=headers,
                json=blocked_after_revocation,
            ).status_code
            == 409
        )

        with application.state.database.session_factory() as session:
            assert len(list(session.scalars(select(MedicationPlanEvent)))) == 6
            assert len(list(session.scalars(select(MedicationAdministrationEvent)))) == 4
            audits = list(
                session.scalars(select(AuditEvent).where(AuditEvent.action.like("medication.%")))
            )
            audit_text = " ".join(str(item.details) for item in audits)
            assert "paper-record-MED-001" not in audit_text
            assert "paper-record-MED-001-reissued" not in audit_text
            assert "5 mL" not in audit_text


def test_incident_draft_review_finalize_and_manual_external_tracking(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "incident-owner@example.com", "Incident Centre")
        headers = _headers(auth)
        facility, program, rooms = _facility_tree(client, headers, "Incident")
        family = _family(client, headers, "Incident")
        child = _child(
            client,
            headers,
            family["id"],
            "Idris",
            facility,
            program,
            rooms[0],
        )
        day = _check_in(client, headers, child["id"], facility["id"])
        replay_actor_headers = _invite_educator(
            client,
            headers,
            facility["id"],
            rooms[0]["id"],
            "incident-replay-educator@example.com",
        )

        context = client.get(
            f"/api/v1/incidents/rooms/{rooms[0]['id']}/context",
            headers=headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert context.status_code == 200, context.text
        assert context.headers["cache-control"] == "private, no-store"
        assert context.json()["attendance_options"] == [
            {
                "attendance_day_id": day["id"],
                "child_id": child["id"],
                "child_name": "Idris Daybook",
                "attendance_state": "on_site",
            }
        ]

        operation_id = str(uuid4())
        draft_payload = {
            "facility_id": facility["id"],
            "room_id": rooms[0]["id"],
            "attendance_day_id": day["id"],
            "occurred_at": _instant(10),
            "category": "injury",
            "severity": "serious",
            "summary": "Observed injury requiring documented follow-up.",
            "immediate_actions": "Provided first aid and monitored the child.",
            "medical_attention": "first_aid",
            "parent_notification_status": "notified",
            "parent_notified_at": _instant(10, 5),
            "parent_notification_notes": "Reached the primary guardian by phone.",
            "authorities_contacted": ["emergency_services"],
            "staff_present": ["Care Owner", "Room Educator"],
            "client_operation_id": operation_id,
        }
        created = client.post("/api/v1/incidents", headers=headers, json=draft_payload)
        assert created.status_code == 201, created.text
        assert created.headers["cache-control"] == "private, no-store"
        incident = created.json()
        assert incident["status"] == "draft"
        assert incident["child_id"] == child["id"]
        assert incident["external_submission_performed_by_caresync"] is False
        foreign_actor_replay = client.post(
            "/api/v1/incidents",
            headers=replay_actor_headers,
            json=draft_payload,
        )
        assert foreign_actor_replay.status_code == 404

        changed_replay = dict(draft_payload)
        changed_replay["summary"] = "Changed content"
        assert (
            client.post("/api/v1/incidents", headers=headers, json=changed_replay).status_code
            == 409
        )

        with application.state.database.session_factory() as session:
            educator_role = session.scalar(select(Role).where(Role.key == "educator"))
            assert educator_role is not None
            if "incident:update" not in educator_role.permissions:
                educator_role.permissions = [
                    *educator_role.permissions,
                    "incident:update",
                ]
            session.commit()
        update_operation = str(uuid4())
        update_payload = {
            **{
                key: value
                for key, value in draft_payload.items()
                if key
                not in {
                    "facility_id",
                    "room_id",
                    "attendance_day_id",
                    "client_operation_id",
                }
            },
            "summary": "Reviewed injury facts requiring documented follow-up.",
            "reason": "Clarified the factual summary.",
            "expected_version": incident["version"],
            "client_operation_id": update_operation,
        }
        updated = client.put(
            f"/api/v1/incidents/{incident['id']}",
            headers=replay_actor_headers,
            json=update_payload,
        )
        assert updated.status_code == 200, updated.text
        incident = updated.json()
        with application.state.database.session_factory() as session:
            educator_role = session.scalar(select(Role).where(Role.key == "educator"))
            assert educator_role is not None
            educator_role.permissions = [
                permission
                for permission in educator_role.permissions
                if permission != "incident:update"
            ]
            if "incident:update_own" not in educator_role.permissions:
                educator_role.permissions = [
                    *educator_role.permissions,
                    "incident:update_own",
                ]
            session.commit()
        unauthorized_update_replay = client.put(
            f"/api/v1/incidents/{incident['id']}",
            headers=replay_actor_headers,
            json=update_payload,
        )
        assert unauthorized_update_replay.status_code == 404

        submitted = client.post(
            f"/api/v1/incidents/{incident['id']}/submit-review",
            headers=headers,
            json={
                "expected_version": incident["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert submitted.status_code == 200, submitted.text
        incident = submitted.json()
        assert incident["status"] == "under_review"

        finalized = client.post(
            f"/api/v1/incidents/{incident['id']}/finalize",
            headers=headers,
            json={
                "reportability_assessment": "critical",
                "reviewer_note": "Internal review complete; external reporting is required.",
                "expected_version": incident["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert finalized.status_code == 200, finalized.text
        incident = finalized.json()
        assert incident["status"] == "finalized"
        assert incident["external_report_status"] == "pending"
        assert (
            incident["reporting_timeline"]
            == "as_soon_as_possible_no_later_than_24_hours"
        )

        report_operation = str(uuid4())
        report_payload = {
            "reported_at": datetime.now(UTC).isoformat(),
            "confirmation_reference": "ALB-CONFIRM-001",
            "submission_channel": "child_care_connect_then_portal",
            "submitted_by_name": "Licensed program director",
            "expected_version": incident["version"],
            "client_operation_id": report_operation,
        }
        reported = client.post(
            f"/api/v1/incidents/{incident['id']}/external-report",
            headers=headers,
            json=report_payload,
        )
        assert reported.status_code == 200, reported.text
        incident = reported.json()
        assert incident["external_report_status"] == "recorded"
        assert incident["external_submission_performed_by_caresync"] is False

        changed_report_replay = dict(report_payload)
        changed_report_replay["confirmation_reference"] = "DIFFERENT"
        assert (
            client.post(
                f"/api/v1/incidents/{incident['id']}/external-report",
                headers=headers,
                json=changed_report_replay,
            ).status_code
            == 409
        )

        cannot_edit = client.put(
            f"/api/v1/incidents/{incident['id']}",
            headers=headers,
            json={
                **{
                    key: value
                    for key, value in draft_payload.items()
                    if key
                    not in {
                        "facility_id",
                        "room_id",
                        "attendance_day_id",
                        "client_operation_id",
                    }
                },
                "reason": "Attempted late edit.",
                "expected_version": incident["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert cannot_edit.status_code == 409

        history = client.get(
            f"/api/v1/incidents/{incident['id']}/history", headers=headers
        )
        assert history.status_code == 200, history.text
        assert [item["event_type"] for item in history.json()] == [
            "drafted",
            "updated",
            "submitted_for_review",
            "finalized",
            "external_report_recorded",
        ]
        listed = client.get("/api/v1/incidents", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()["incidents"][0]["id"] == incident["id"]

        stranded_checkout = client.post(
            "/api/v1/attendance/check-out",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "child_id": child["id"],
                "facility_id": facility["id"],
                "occurred_at": _instant(9, 30),
            },
        )
        assert stranded_checkout.status_code == 409
        assert "incident" in stranded_checkout.json()["detail"].lower()

        with application.state.database.session_factory() as session:
            assert len(list(session.scalars(select(IncidentRecordEvent)))) == 5
            audits = list(
                session.scalars(select(AuditEvent).where(AuditEvent.action.like("incident.%")))
            )
            audit_text = " ".join(str(item.details) for item in audits)
            assert "ALB-CONFIRM-001" not in audit_text
            assert "Reviewed injury facts" not in audit_text


def test_educator_is_fail_closed_to_assigned_room_and_privileged_transitions(
    tmp_path,
) -> None:
    client, _ = _client(tmp_path)
    with client:
        auth = _register(client, "scope-owner@example.com", "Regulated Scope Centre")
        owner_headers = _headers(auth)
        facility, program, rooms = _facility_tree(client, owner_headers, "Scope")
        family = _family(client, owner_headers, "Scope")
        assigned_child = _child(
            client,
            owner_headers,
            family["id"],
            "Assigned",
            facility,
            program,
            rooms[0],
        )
        outside_child = _child(
            client,
            owner_headers,
            family["id"],
            "Outside",
            facility,
            program,
            rooms[1],
        )
        assigned_day = _check_in(
            client, owner_headers, assigned_child["id"], facility["id"]
        )
        outside_day = _check_in(
            client, owner_headers, outside_child["id"], facility["id"]
        )
        assigned_plan = _active_plan(
            client, owner_headers, facility["id"], assigned_child["id"]
        )
        outside_plan = _active_plan(
            client, owner_headers, facility["id"], outside_child["id"]
        )
        educator_headers = _invite_educator(
            client,
            owner_headers,
            facility["id"],
            rooms[0]["id"],
            "regulated-educator@example.com",
        )

        visible_day = client.get(
            f"/api/v1/medications/rooms/{rooms[0]['id']}/day",
            headers=educator_headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert visible_day.status_code == 200, visible_day.text
        assert visible_day.json()["children"][0]["plans"][0]["id"] == assigned_plan["id"]
        assert (
            client.get(
                f"/api/v1/medications/rooms/{rooms[1]['id']}/day",
                headers=educator_headers,
                params={"date": SERVICE_DATE.isoformat()},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/medications/plans/{outside_plan['id']}",
                headers=educator_headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/v1/medications/plans",
                headers=educator_headers,
                json=_plan_payload(
                    facility["id"], assigned_child["id"], str(uuid4())
                ),
            ).status_code
            == 403
        )
        outside_administration = client.post(
            "/api/v1/medications/administrations",
            headers=educator_headers,
            json={
                "medication_plan_id": outside_plan["id"],
                "attendance_day_id": outside_day["id"],
                "outcome": "administered",
                "scheduled_for": "09:00",
                "occurred_at": _instant(9),
                "amount": "5 mL",
                "client_operation_id": str(uuid4()),
            },
        )
        assert outside_administration.status_code == 404

        visible_administration = client.post(
            "/api/v1/medications/administrations",
            headers=educator_headers,
            json={
                "medication_plan_id": assigned_plan["id"],
                "attendance_day_id": assigned_day["id"],
                "outcome": "administered",
                "scheduled_for": "09:00",
                "occurred_at": _instant(9),
                "amount": "5 mL",
                "client_operation_id": str(uuid4()),
            },
        )
        assert visible_administration.status_code == 201, visible_administration.text
        assert visible_administration.json()["staff_initials_snapshot"] == "RE"

        assert (
            client.get(
                f"/api/v1/incidents/rooms/{rooms[1]['id']}/context",
                headers=educator_headers,
                params={"date": SERVICE_DATE.isoformat()},
            ).status_code
            == 404
        )
        incident = client.post(
            "/api/v1/incidents",
            headers=educator_headers,
            json={
                "facility_id": facility["id"],
                "room_id": rooms[0]["id"],
                "attendance_day_id": assigned_day["id"],
                "occurred_at": _instant(10),
                "category": "other",
                "severity": "minor",
                "summary": "Assigned room fact.",
                "immediate_actions": "Observed and documented.",
                "medical_attention": "none",
                "parent_notification_status": "not_applicable",
                "authorities_contacted": [],
                "staff_present": ["Room Educator"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert incident.status_code == 201, incident.text
        submitted = client.post(
            f"/api/v1/incidents/{incident.json()['id']}/submit-review",
            headers=educator_headers,
            json={
                "expected_version": incident.json()["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert submitted.status_code == 200, submitted.text
        assert (
            client.post(
                f"/api/v1/incidents/{incident.json()['id']}/finalize",
                headers=educator_headers,
                json={
                    "reportability_assessment": "not_reportable",
                    "reviewer_note": "Educator must not finalize.",
                    "expected_version": submitted.json()["version"],
                    "client_operation_id": str(uuid4()),
                },
            ).status_code
            == 403
        )
