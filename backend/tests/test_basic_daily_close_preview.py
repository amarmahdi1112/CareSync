"""Read-only room daily-close preview acceptance coverage."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import event, func, select

from app.basic.models import (
    AttendanceDay,
    DailyCareRecord,
    IncidentRecord,
    MedicationAdministration,
    Role,
    Room,
)
from tests.test_basic_daily_care import (
    SERVICE_DATE,
    _check_in,
    _child,
    _client,
    _create_record,
    _facility_tree,
    _family,
    _headers,
    _instant,
    _invite_educator,
    _register,
)
from tests.test_basic_regulated_care import _active_plan


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _check_out(client, headers, child_id: str, facility_id: str, occurred_at: str) -> dict:
    response = client.post(
        "/api/v1/attendance/check-out",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "child_id": child_id,
            "facility_id": facility_id,
            "occurred_at": occurred_at,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _mark_absent(
    client,
    headers,
    child_id: str,
    facility_id: str,
    service_date: date,
) -> dict:
    response = client.put(
        "/api/v1/attendance/absence",
        headers=headers,
        json={
            "child_id": child_id,
            "facility_id": facility_id,
            "date": service_date.isoformat(),
            "reason": "Recorded absence fact",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_incident(
    client,
    headers,
    *,
    facility_id: str,
    room_id: str,
    attendance_day_id: str,
    occurred_at: str,
    summary: str,
) -> dict:
    response = client.post(
        "/api/v1/incidents",
        headers=headers,
        json={
            "facility_id": facility_id,
            "room_id": room_id,
            "attendance_day_id": attendance_day_id,
            "occurred_at": occurred_at,
            "category": "other",
            "severity": "minor",
            "summary": summary,
            "immediate_actions": "PRIVATE INCIDENT ACTION NARRATIVE",
            "medical_attention": "none",
            "parent_notification_status": "not_applicable",
            "authorities_contacted": [],
            "staff_present": ["Private Staff Name"],
            "client_operation_id": str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_daily_close_preview_returns_only_bounded_factual_rollups(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "close-owner@example.com", "Daily Close Centre")
        headers = _headers(auth)
        facility, program, rooms = _facility_tree(client, headers, "Daily Close")
        family = _family(client, headers, "Daily Close")
        present_child = _child(
            client,
            headers,
            family["id"],
            "Facts",
            facility,
            program,
            rooms[0],
        )
        absent_child = _child(
            client,
            headers,
            family["id"],
            "Absent",
            facility,
            program,
            rooms[0],
        )
        _child(
            client,
            headers,
            family["id"],
            "Unrecorded",
            facility,
            program,
            rooms[0],
        )

        day = _check_in(client, headers, present_child["id"], facility["id"], 8)
        _check_out(
            client,
            headers,
            present_child["id"],
            facility["id"],
            _instant(9),
        )
        _check_in(client, headers, present_child["id"], facility["id"], 10)
        _mark_absent(
            client,
            headers,
            absent_child["id"],
            facility["id"],
            SERVICE_DATE,
        )

        feeding = _create_record(
            client,
            headers,
            day["id"],
            "feeding",
            _instant(10, 10),
            {"kind": "snack", "intake": "most"},
            note="PRIVATE CARE NARRATIVE",
        )
        assert feeding.status_code == 201, feeding.text
        sleep = _create_record(
            client,
            headers,
            day["id"],
            "sleep",
            _instant(10, 20),
            {},
        )
        assert sleep.status_code == 201, sleep.text

        refused_plan = _active_plan(
            client,
            headers,
            facility["id"],
            present_child["id"],
        )
        refused = client.post(
            "/api/v1/medications/administrations",
            headers=headers,
            json={
                "medication_plan_id": refused_plan["id"],
                "attendance_day_id": day["id"],
                "outcome": "refused",
                "scheduled_for": "09:00",
                "occurred_at": _instant(10, 30),
                "reason": "PRIVATE MEDICATION REFUSAL REASON",
                "client_operation_id": str(uuid4()),
            },
        )
        assert refused.status_code == 201, refused.text
        omitted_plan = _active_plan(
            client,
            headers,
            facility["id"],
            present_child["id"],
        )
        omitted = client.post(
            "/api/v1/medications/administrations",
            headers=headers,
            json={
                "medication_plan_id": omitted_plan["id"],
                "attendance_day_id": day["id"],
                "outcome": "omitted",
                "scheduled_for": "09:00",
                "occurred_at": _instant(10, 35),
                "reason": "PRIVATE MEDICATION OMISSION REASON",
                "client_operation_id": str(uuid4()),
            },
        )
        assert omitted.status_code == 201, omitted.text

        _create_incident(
            client,
            headers,
            facility_id=facility["id"],
            room_id=rooms[0]["id"],
            attendance_day_id=day["id"],
            occurred_at=_instant(10, 40),
            summary="PRIVATE DRAFT INCIDENT SUMMARY",
        )
        review = _create_incident(
            client,
            headers,
            facility_id=facility["id"],
            room_id=rooms[0]["id"],
            attendance_day_id=day["id"],
            occurred_at=_instant(10, 45),
            summary="PRIVATE REVIEW INCIDENT SUMMARY",
        )
        submitted = client.post(
            f"/api/v1/incidents/{review['id']}/submit-review",
            headers=headers,
            json={
                "expected_version": review["version"],
                "client_operation_id": str(uuid4()),
            },
        )
        assert submitted.status_code == 200, submitted.text

        tracked_models = (
            AttendanceDay,
            DailyCareRecord,
            MedicationAdministration,
            IncidentRecord,
        )
        with application.state.database.session_factory() as session:
            before_counts = {
                model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in tracked_models
            }

        response = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
            headers=headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["pragma"] == "no-cache"
        body = response.json()
        by_name = {item["child_name"]: item for item in body["children"]}
        facts = by_name["Facts Daybook"]
        assert facts["profile_photo_url"] is None
        assert facts["attendance_state"] == "on_site"
        assert facts["currently_on_site"] is True
        assert _parse(facts["first_check_in_at"]) == _parse(_instant(8))
        assert _parse(facts["last_checkout_at"]) == _parse(_instant(9))
        expected_seconds = (_parse(_instant(9)) - _parse(_instant(8))).total_seconds() + (
            _parse(body["generated_at"]) - _parse(_instant(10))
        ).total_seconds()
        assert facts["accumulated_minutes"] == int(expected_seconds // 60)
        assert facts["care_counts"] == {
            "feeding": 1,
            "diaper": 0,
            "toilet": 0,
            "sleep": 1,
            "mood": 0,
            "activity": 0,
        }
        assert facts["open_sleep"] is True
        assert _parse(facts["most_recent_care_at"]) == _parse(_instant(10, 20))
        assert facts["medication_administration_counts"] == {
            "administered": 0,
            "refused": 1,
            "omitted": 1,
        }
        assert _parse(facts["most_recent_medication_at"]) == _parse(_instant(10, 35))
        assert facts["incident_status_counts"] == {
            "draft": 1,
            "under_review": 1,
            "finalized": 0,
        }
        assert _parse(facts["most_recent_incident_at"]) == _parse(_instant(10, 45))
        assert facts["attention_flags"] == [
            "open_sleep",
            "medication_refused",
            "medication_omitted",
            "incident_draft",
            "incident_under_review",
        ]

        absent = by_name["Absent Daybook"]
        assert absent["attendance_state"] == "no_show"
        assert absent["currently_on_site"] is False
        assert absent["first_check_in_at"] is None
        assert absent["accumulated_minutes"] == 0
        assert absent["attention_flags"] == []
        unrecorded = by_name["Unrecorded Daybook"]
        assert unrecorded["attendance_state"] == "not_recorded"
        assert unrecorded["attendance_day_id"] is None
        assert unrecorded["attention_flags"] == []

        assert body["totals"]["child_count"] == 3
        assert body["totals"]["attendance_state_counts"] == {
            "not_recorded": 1,
            "on_site": 1,
            "checked_out": 0,
            "no_show": 1,
        }
        assert body["totals"]["currently_on_site"] == 1
        assert body["totals"]["open_sleep"] == 1
        assert body["totals"]["care_counts"] == facts["care_counts"]
        assert (
            body["totals"]["medication_administration_counts"]
            == facts["medication_administration_counts"]
        )
        assert body["totals"]["incident_status_counts"] == facts["incident_status_counts"]

        serialized = json.dumps(body)
        for private_value in {
            "PRIVATE CARE NARRATIVE",
            "PRIVATE MEDICATION REFUSAL REASON",
            "PRIVATE MEDICATION OMISSION REASON",
            "PRIVATE DRAFT INCIDENT SUMMARY",
            "PRIVATE REVIEW INCIDENT SUMMARY",
            "PRIVATE INCIDENT ACTION NARRATIVE",
            "Private Staff Name",
            "Prescribed medication",
            "guardian",
            "compliance",
            "complete",
        }:
            assert private_value not in serialized

        with application.state.database.session_factory() as session:
            after_counts = {
                model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in tracked_models
            }
        assert after_counts == before_counts

        def preview_query_count() -> int:
            statements: list[str] = []

            def count_statement(*args) -> None:
                statements.append(str(args[2]))

            engine = application.state.database.engine
            event.listen(engine, "before_cursor_execute", count_statement)
            try:
                counted = client.get(
                    f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
                    headers=headers,
                    params={"date": SERVICE_DATE.isoformat()},
                )
            finally:
                event.remove(engine, "before_cursor_execute", count_statement)
            assert counted.status_code == 200, counted.text
            return len(statements)

        three_child_queries = preview_query_count()
        _child(
            client,
            headers,
            family["id"],
            "Additional",
            facility,
            program,
            rooms[0],
        )
        four_child_queries = preview_query_count()
        assert four_child_queries <= three_child_queries
        assert four_child_queries <= 16


def test_daily_close_preview_requires_every_permission_and_preserves_scope(tmp_path) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "close-scope-owner@example.com", "Close Scope Centre")
        owner_headers = _headers(auth)
        facility, program, rooms = _facility_tree(client, owner_headers, "Close Scope")
        family = _family(client, owner_headers, "Close Scope")
        historical_date = SERVICE_DATE - timedelta(days=1)
        historical_child = _child(
            client,
            owner_headers,
            family["id"],
            "Historical",
            facility,
            program,
            rooms[0],
            enrollment_start_date=historical_date.isoformat(),
        )
        _child(
            client,
            owner_headers,
            family["id"],
            "TodayOnly",
            facility,
            program,
            rooms[0],
        )
        _mark_absent(
            client,
            owner_headers,
            historical_child["id"],
            facility["id"],
            historical_date,
        )
        educator_headers = _invite_educator(
            client,
            owner_headers,
            facility["id"],
            rooms[0]["id"],
            "close-scope-educator@example.com",
        )

        current = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
            headers=educator_headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert current.status_code == 200, current.text
        assert {item["attendance_state"] for item in current.json()["children"]} == {"not_recorded"}
        outside_room = client.get(
            f"/api/v1/care/rooms/{rooms[1]['id']}/daily-close-preview",
            headers=educator_headers,
            params={"date": SERVICE_DATE.isoformat()},
        )
        assert outside_room.status_code == 404
        educator_historical = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
            headers=educator_headers,
            params={"date": historical_date.isoformat()},
        )
        assert educator_historical.status_code == 403

        owner_historical = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
            headers=owner_headers,
            params={"date": historical_date.isoformat()},
        )
        assert owner_historical.status_code == 200, owner_historical.text
        assert owner_historical.json()["totals"]["child_count"] == 1
        assert owner_historical.json()["children"][0]["child_name"] == "Historical Daybook"
        assert owner_historical.json()["children"][0]["attendance_state"] == "no_show"

        with application.state.database.session_factory() as session:
            educator_role = session.scalar(
                select(Role).where(
                    Role.organization_id == UUID(auth["user"]["organization_id"]),
                    Role.key == "educator",
                )
            )
            assert educator_role is not None
            original_permissions = list(educator_role.permissions)
        required_permissions = (
            "care:read",
            "child_safety:read",
            "medication:read",
            "incident:read",
        )
        for missing_permission in required_permissions:
            with application.state.database.session_factory() as session:
                educator_role = session.scalar(
                    select(Role).where(
                        Role.organization_id == UUID(auth["user"]["organization_id"]),
                        Role.key == "educator",
                    )
                )
                assert educator_role is not None
                educator_role.permissions = [
                    value for value in original_permissions if value != missing_permission
                ]
                session.commit()
            denied = client.get(
                f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
                headers=educator_headers,
                params={"date": SERVICE_DATE.isoformat()},
            )
            assert denied.status_code == 403
        with application.state.database.session_factory() as session:
            educator_role = session.scalar(
                select(Role).where(
                    Role.organization_id == UUID(auth["user"]["organization_id"]),
                    Role.key == "educator",
                )
            )
            assert educator_role is not None
            educator_role.permissions = original_permissions
            room = session.get(Room, UUID(rooms[0]["id"]))
            assert room is not None
            room.is_active = False
            session.commit()

        inactive_historical = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
            headers=owner_headers,
            params={"date": historical_date.isoformat()},
        )
        assert inactive_historical.status_code == 200, inactive_historical.text

        other_auth = _register(client, "close-other@example.com", "Other Close Centre")
        cross_tenant = client.get(
            f"/api/v1/care/rooms/{rooms[0]['id']}/daily-close-preview",
            headers=_headers(other_auth),
            params={"date": historical_date.isoformat()},
        )
        assert cross_tenant.status_code == 404
