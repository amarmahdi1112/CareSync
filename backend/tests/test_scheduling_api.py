from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select

from app.api.dependencies import get_current_user
from app.api.v1.scheduling import _alberta_holidays, _edmonton_school_calendar
from app.core.config import Settings
from app.main import create_app
from app.models.generated_legacy import Base
from app.schemas.scheduling import ScheduleGenerationRequest


def _scheduler_application(tmp_path, *, scheduler_engine_version: str | None = None):
    organization_id = uuid4()
    settings_values = {
        "_env_file": None,
        "environment": "test",
        "database_path": tmp_path / "caresync.db",
        "database_name": "caresync",
        "database_read_only": False,
    }
    if scheduler_engine_version is not None:
        settings_values["scheduler_engine_version"] = scheduler_engine_version
    application = create_app(
        Settings(**settings_values)  # type: ignore[arg-type]
    )
    application.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        organization_id=organization_id
    )
    application.state.test_organization_id = organization_id
    with application.state.database.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE organizations (id TEXT PRIMARY KEY, system_preferences TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE families (id CHAR(32) PRIMARY KEY, organization_id CHAR(32) NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE children (id CHAR(32) PRIMARY KEY, family_id CHAR(32) NOT NULL, "
            "date_of_birth DATE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE scheduled_attendance ("
            "id CHAR(32) PRIMARY KEY, child_id VARCHAR(255) NOT NULL, "
            "batch_id VARCHAR(100) NOT NULL, date DATE NOT NULL, mode VARCHAR(20) NOT NULL, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, is_locked BOOLEAN NOT NULL DEFAULT 0, "
            '"startTime1" VARCHAR(10), "endTime1" VARCHAR(10), '
            '"startTime2" VARCHAR(10), "endTime2" VARCHAR(10), '
            "source_claim_batch_id VARCHAR(100))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE imported_claims ("
            "id CHAR(32) PRIMARY KEY, organization_id CHAR(32) NOT NULL, "
            "import_batch_id VARCHAR(100) NOT NULL, child_name VARCHAR(255) NOT NULL, "
            "matched_child_id CHAR(32), date_of_birth DATE)"
        )
    return application


def _schedule_body() -> dict:
    return {
        "openDays": ["2024-01-15", "2024-01-16", "2024-01-17"],
        "capacity": 10,
        "operatingHours": {"start": 7, "end": 18},
        "seed": "api-scheduler",
        "children": [
            {
                "id": "child-1",
                "name": "Child One",
                "familyId": "family-1",
                "careType": "Daycare",
                "totalClaimedHours": 20,
            }
        ],
    }


def test_default_v3_schedule_generation_accepts_camel_case(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=_schedule_body())

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["total_entries"] > 0
    assert payload["entries"][0]["child_id"] == "child-1"
    assert payload["entries"][0]["child_name"] == "Child One"
    assert payload["seed"] == "api-scheduler"
    assert payload["stats"]["completion_percentage"] == 100
    assert payload["algorithm_version"] == "3.0-isolated-adapter"
    assert payload["persisted"] is False


def test_deprecated_v2_rollback_still_generates_a_schedule(tmp_path) -> None:
    application = _scheduler_application(tmp_path, scheduler_engine_version="v2")

    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=_schedule_body())

    assert response.status_code == 200, response.text
    assert response.json()["algorithm_version"] == "2.1-safety"
    assert response.json()["stats"]["completion_percentage"] == 100


def test_v3_schedule_generation_returns_exact_legacy_contract(tmp_path) -> None:
    application = _scheduler_application(tmp_path)

    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=_schedule_body())

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["algorithm_version"] == "3.0-isolated-adapter"
    assert payload["stats"]["completion_percentage"] == 100
    assert payload["stats"]["total_hours_scheduled"] == 20
    assert payload["entries"][0]["child_name"] == "Child One"
    assert payload["persisted"] is False


def test_v3_schedule_reports_decimal_claim_normalization(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    body = _schedule_body()
    body["children"][0]["totalClaimedHours"] = 0.125

    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 200, response.text
    payload = response.json()
    warning = next(
        item
        for item in payload["warnings"]
        if item["code"] == "V3_CLAIM_NORMALIZED_TO_FIVE_MINUTES"
    )
    assert "source=0.125h" in warning["message"]
    assert payload["stats"]["completion_percentage"] == 100


def test_v3_schedule_rejects_unsupported_hard_override(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    body = _schedule_body()
    body["childTimeOverrides"] = [
        {
            "childIdentifier": "child-1",
            "startTime1": "08:00",
            "endTime1": "09:00",
        }
    ]

    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 422
    assert "does not support child_time_overrides" in response.json()["detail"]


def test_v3_incomplete_persist_request_returns_diagnostic_without_writes(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    attendance_table = Base.metadata.tables["scheduled_attendance"]
    engine = application.state.database.engine
    body = _schedule_body()
    body["children"][0]["totalClaimedHours"] = 40

    body["persist"] = True
    with TestClient(application) as client:
        diagnostic = client.post("/api/v1/schedules/generate", json=body)

    assert diagnostic.status_code == 200, diagnostic.text
    payload = diagnostic.json()
    assert payload["persisted"] is False
    assert payload["persisted_entries"] == 0
    assert payload["stats"]["completion_percentage"] < 100
    assert any(
        warning["code"] == "V3_INCOMPLETE_NOT_PERSISTABLE"
        for warning in payload["warnings"]
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(attendance_table)) == 0


def test_v3_realism_rollback_at_exact_total_cannot_be_persisted(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    family_id = uuid4()
    child_id = uuid4()
    engine = application.state.database.engine
    family_table = Base.metadata.tables["families"]
    child_table = Base.metadata.tables["children"]
    attendance_table = Base.metadata.tables["scheduled_attendance"]
    with engine.begin() as connection:
        connection.execute(
            insert(family_table),
            {"id": family_id, "organization_id": application.state.test_organization_id},
        )
        connection.execute(insert(child_table), {"id": child_id, "family_id": family_id})

    body = _schedule_body()
    body["openDays"] = ["2024-01-15", "2024-01-16"]
    body["children"][0]["id"] = str(child_id)
    body["children"][0]["familyId"] = str(family_id)
    body["children"][0]["totalClaimedHours"] = 250 / 12
    body["persist"] = True
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["stats"]["completion_percentage"] == 100
    assert payload["persisted"] is False
    assert payload["persisted_entries"] == 0
    assert any(
        warning["code"] == "V3_DAYCARE_REALISM_NOT_PERSISTABLE"
        for warning in payload["warnings"]
    )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(attendance_table)) == 0


def test_v3_audit_runtime_failure_returns_safe_500(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    application = _scheduler_application(tmp_path)

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("sensitive internal audit detail")

    monkeypatch.setattr("app.api.v1.scheduling.execute_v3_schedule", fail_audit)
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=_schedule_body())

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "V3 scheduling failed its independent safety audit; nothing was persisted"
    )


def test_schedule_generation_persists_the_batch_atomically(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    family_id = uuid4()
    child_id = uuid4()
    engine = application.state.database.engine
    family_table = Base.metadata.tables["families"]
    child_table = Base.metadata.tables["children"]
    attendance_table = Base.metadata.tables["scheduled_attendance"]
    with engine.begin() as connection:
        connection.execute(
            insert(family_table),
            {"id": family_id, "organization_id": application.state.test_organization_id},
        )
        connection.execute(insert(child_table), {"id": child_id, "family_id": family_id})

    body = _schedule_body()
    body["children"][0]["id"] = str(child_id)
    body["children"][0]["familyId"] = str(family_id)
    body["persist"] = True
    body["sourceClaimBatchId"] = "claim-source-1"
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["persisted"] is True
    assert payload["persisted_entries"] == payload["stats"]["total_entries"]
    assert all(entry.get("id") for entry in payload["entries"])
    with engine.connect() as connection:
        saved_count = connection.scalar(select(func.count()).select_from(attendance_table))
        source_batch = connection.scalar(select(attendance_table.c.source_claim_batch_id))
    assert saved_count == payload["persisted_entries"]
    assert source_batch == "claim-source-1"

    with TestClient(application) as client:
        delete_response = client.delete(
            f"/api/v1/schedules/{payload['batch_id']}", params={"confirm": True}
        )
    assert delete_response.status_code == 204
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(attendance_table)) == 0


def test_v3_split_osc_schedule_persists_both_blocks(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    family_id = uuid4()
    child_id = uuid4()
    engine = application.state.database.engine
    family_table = Base.metadata.tables["families"]
    child_table = Base.metadata.tables["children"]
    attendance_table = Base.metadata.tables["scheduled_attendance"]
    with engine.begin() as connection:
        connection.execute(
            insert(family_table),
            {"id": family_id, "organization_id": application.state.test_organization_id},
        )
        connection.execute(insert(child_table), {"id": child_id, "family_id": family_id})

    body = _schedule_body()
    body["openDays"] = ["2024-01-15"]
    body["children"][0].update(
        {
            "id": str(child_id),
            "familyId": str(family_id),
            "careType": "OSC",
            "totalClaimedHours": 4,
        }
    )
    body["persist"] = True
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 200, response.text
    assert response.json()["persisted"] is True
    assert response.json()["stats"]["completion_percentage"] == 100
    with engine.connect() as connection:
        saved = connection.execute(select(attendance_table)).mappings().one()
    assert (saved["startTime1"], saved["endTime1"]) == ("07:00", "08:30")
    assert (saved["startTime2"], saved["endTime2"]) == ("15:30", "18:00")


def test_schedule_persistence_honors_the_write_guard(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    application.state.settings.database_read_only = True
    body = _schedule_body()
    body["persist"] = True
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 409


def test_schedule_persists_unmatched_import_as_claim_only_child(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    claim_id = uuid4()
    batch_id = "claim-only-source"
    imported_table = Base.metadata.tables["imported_claims"]
    attendance_table = Base.metadata.tables["scheduled_attendance"]
    engine = application.state.database.engine
    with engine.begin() as connection:
        connection.execute(
            insert(imported_table),
            {
                "id": claim_id,
                "organization_id": application.state.test_organization_id,
                "import_batch_id": batch_id,
                "child_name": "Imported Child",
                "matched_child_id": None,
            },
        )

    body = _schedule_body()
    body["children"][0]["id"] = f"imported-claim:{claim_id}"
    body["children"][0]["name"] = "Imported Child"
    body["children"][0]["familyId"] = f"imported-batch:{batch_id}"
    body["persist"] = True
    body["sourceClaimBatchId"] = batch_id
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)
        schedule_rows = client.get(
            "/api/v1/resources/scheduled_attendance",
            params={"batch_id": response.json().get("batch_id", "")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["persisted"] is True
    assert schedule_rows.status_code == 200, schedule_rows.text
    assert schedule_rows.json()[0]["child_name"] == "Imported Child"
    with engine.connect() as connection:
        child_identifier = connection.scalar(select(attendance_table.c.child_id))
    assert child_identifier == f"imported-claim:{claim_id}"


def test_schedule_splits_anchored_duplicate_with_contradictory_dob(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    batch_id = "anchored-identity-conflict"
    claim_id = uuid4()
    anchor_id = uuid4()
    child_id = uuid4()
    family_id = uuid4()
    imported_table = Base.metadata.tables["imported_claims"]
    children_table = Base.metadata.tables["children"]
    families_table = Base.metadata.tables["families"]
    engine = application.state.database.engine
    with engine.begin() as connection:
        connection.execute(
            insert(families_table),
            {
                "id": family_id,
                "organization_id": application.state.test_organization_id,
            },
        )
        connection.execute(
            insert(children_table),
            {
                "id": child_id,
                "family_id": family_id,
                "date_of_birth": date(2014, 11, 6),
            },
        )
        connection.execute(
            insert(imported_table),
            [
                {
                    "id": anchor_id,
                    "organization_id": application.state.test_organization_id,
                    "import_batch_id": batch_id,
                    "child_name": "Fatima Mohamed",
                    "matched_child_id": child_id,
                    "date_of_birth": date(2014, 11, 6),
                },
                {
                    "id": claim_id,
                    "organization_id": application.state.test_organization_id,
                    "import_batch_id": batch_id,
                    "child_name": "Faxima Mohamed",
                    "matched_child_id": child_id,
                    "date_of_birth": date(2013, 11, 6),
                },
            ],
        )

    body = _schedule_body()
    body["children"][0]["id"] = f"imported-claim:{claim_id}"
    body["children"][0]["name"] = "Faxima Mohamed"
    body["children"][0]["familyId"] = f"imported-batch:{batch_id}"
    body["persist"] = True
    body["sourceClaimBatchId"] = batch_id
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 200, response.text
    assert response.json()["persisted"] is True


@pytest.mark.parametrize(
    ("include_sibling", "sibling_date_of_birth"),
    [(False, None), (True, date(2012, 11, 6))],
)
def test_schedule_does_not_split_unanchored_dob_mismatch(
    tmp_path,
    include_sibling: bool,
    sibling_date_of_birth: date | None,
) -> None:
    application = _scheduler_application(tmp_path)
    batch_id = "unanchored-identity-conflict"
    claim_id = uuid4()
    child_id = uuid4()
    family_id = uuid4()
    imported_table = Base.metadata.tables["imported_claims"]
    children_table = Base.metadata.tables["children"]
    families_table = Base.metadata.tables["families"]
    engine = application.state.database.engine
    with engine.begin() as connection:
        connection.execute(
            insert(families_table),
            {
                "id": family_id,
                "organization_id": application.state.test_organization_id,
            },
        )
        connection.execute(
            insert(children_table),
            {
                "id": child_id,
                "family_id": family_id,
                "date_of_birth": date(2014, 11, 6),
            },
        )
        rows = [
            {
                "id": claim_id,
                "organization_id": application.state.test_organization_id,
                "import_batch_id": batch_id,
                "child_name": "Unique Mismatch",
                "matched_child_id": child_id,
                "date_of_birth": date(2013, 11, 6),
            }
        ]
        if include_sibling:
            rows.append(
                {
                    "id": uuid4(),
                    "organization_id": application.state.test_organization_id,
                    "import_batch_id": batch_id,
                    "child_name": "Another Mismatch",
                    "matched_child_id": child_id,
                    "date_of_birth": sibling_date_of_birth,
                }
            )
        connection.execute(insert(imported_table), rows)

    body = _schedule_body()
    body["children"][0]["id"] = f"imported-claim:{claim_id}"
    body["children"][0]["familyId"] = f"imported-batch:{batch_id}"
    body["persist"] = True
    body["sourceClaimBatchId"] = batch_id
    with TestClient(application) as client:
        response = client.post("/api/v1/schedules/generate", json=body)

    assert response.status_code == 403, response.text


def test_schedule_generation_rejects_duplicates_invalid_times_and_closed_days(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    with TestClient(application) as client:
        duplicate_days = _schedule_body()
        duplicate_days["openDays"] = ["2024-01-15", "2024-01-15"]
        assert client.post("/api/v1/schedules/generate", json=duplicate_days).status_code == 422

        duplicate_children = _schedule_body()
        duplicate_children["children"] = [
            duplicate_children["children"][0],
            duplicate_children["children"][0],
        ]
        assert client.post("/api/v1/schedules/generate", json=duplicate_children).status_code == 422

        invalid_time = _schedule_body()
        invalid_time["children"][0]["preferences"] = {
            "startTime1": "09:00",
            "endTime1": "08:00",
        }
        assert client.post("/api/v1/schedules/generate", json=invalid_time).status_code == 422

        holiday = _schedule_body()
        holiday["openDays"] = ["2026-07-01"]
        response = client.post("/api/v1/schedules/generate", json=holiday)
        assert response.status_code == 422
        assert "closure dates" in response.json()["detail"]


def test_schedule_contract_rejects_non_finite_hours_and_partial_time_pairs() -> None:
    infinite = _schedule_body()
    infinite["children"][0]["totalClaimedHours"] = float("inf")
    with pytest.raises(ValueError):
        ScheduleGenerationRequest.model_validate(infinite)

    partial = _schedule_body()
    partial["childTimeOverrides"] = [{"childIdentifier": "child-1", "startTime1": "09:00"}]
    with pytest.raises(ValueError):
        ScheduleGenerationRequest.model_validate(partial)


def test_alberta_holidays_match_official_2026_dates() -> None:
    holidays = {item["name"]: item["date"] for item in _alberta_holidays(2026)}

    assert holidays == {
        "New Year's Day": "2026-01-01",
        "Alberta Family Day": "2026-02-16",
        "Good Friday": "2026-04-03",
        "Victoria Day": "2026-05-18",
        "Canada Day": "2026-07-01",
        "Labour Day": "2026-09-07",
        "Thanksgiving Day": "2026-10-12",
        "Remembrance Day": "2026-11-11",
        "Christmas Day": "2026-12-25",
    }


def test_optional_alberta_holidays_can_be_enabled() -> None:
    holidays = {item["name"]: item["date"] for item in _alberta_holidays(2026, True)}

    assert holidays["Easter Monday"] == "2026-04-06"
    assert holidays["Heritage Day"] == "2026-08-03"
    assert holidays["National Day for Truth and Reconciliation"] == "2026-09-30"
    assert holidays["Boxing Day"] == "2026-12-26"


def test_alberta_holidays_are_calculated_for_past_and_future_years() -> None:
    holidays_2025 = {item["name"]: item["date"] for item in _alberta_holidays(2025)}
    holidays_2027 = {item["name"]: item["date"] for item in _alberta_holidays(2027)}

    assert holidays_2025["Alberta Family Day"] == "2025-02-17"
    assert holidays_2025["Good Friday"] == "2025-04-18"
    assert holidays_2025["Thanksgiving Day"] == "2025-10-13"
    assert holidays_2027["Alberta Family Day"] == "2027-02-15"
    assert holidays_2027["Good Friday"] == "2027-03-26"
    assert holidays_2027["Thanksgiving Day"] == "2027-10-11"


def test_edmonton_2025_26_calendar_marks_post_instruction_june_weekdays() -> None:
    calendar_data = _edmonton_school_calendar(2026)

    assert calendar_data["academicYear"] == "2025-26"
    assert calendar_data["sourceDetail"] == (
        "Built-in coverage: June 24-30 weekdays after the last instruction day, "
        "June 23, 2026"
    )
    assert [item["date"] for item in calendar_data["automatic"]] == [
        "2026-06-24",
        "2026-06-25",
        "2026-06-26",
        "2026-06-29",
        "2026-06-30",
    ]


def test_school_calendar_api_returns_automatic_defaults_and_persists_exceptions(
    tmp_path,
) -> None:
    application = _scheduler_application(tmp_path)
    organization_table = Base.metadata.tables["organizations"]
    with application.state.database.engine.begin() as connection:
        connection.execute(
            insert(organization_table),
            {
                "id": application.state.test_organization_id,
                "system_preferences": "{}",
            },
        )

    with TestClient(application) as client:
        initial = client.get("/api/v1/schedules/school-calendar", params={"year": 2026})
        updated = client.patch(
            "/api/v1/schedules/school-calendar",
            json={
                "year": 2026,
                "customDays": [
                    {"date": "2026-06-12", "name": "School professional learning day"}
                ],
                "excludedAutomaticDays": ["2026-06-24"],
            },
        )
        reloaded = client.get("/api/v1/schedules/school-calendar", params={"year": 2026})

    assert initial.status_code == 200, initial.text
    assert initial.json()["hasOfficialDefaults"] is True
    assert len(initial.json()["automatic"]) == 5
    assert updated.status_code == 200, updated.text
    assert reloaded.status_code == 200, reloaded.text
    payload = reloaded.json()
    assert payload["excludedAutomaticDays"] == ["2026-06-24"]
    assert payload["custom"] == [
        {
            "date": "2026-06-12",
            "name": "School professional learning day",
            "kind": "custom",
        }
    ]
    assert [item["date"] for item in payload["effective"]] == [
        "2026-06-12",
        "2026-06-25",
        "2026-06-26",
        "2026-06-29",
        "2026-06-30",
    ]


def test_school_calendar_rejects_invalid_exceptions(tmp_path) -> None:
    application = _scheduler_application(tmp_path)
    with TestClient(application) as client:
        response = client.patch(
            "/api/v1/schedules/school-calendar",
            json={
                "year": 2026,
                "customDays": [],
                "excludedAutomaticDays": ["2026-06-23"],
            },
        )

    assert response.status_code == 422
    assert "Only automatic dates" in response.json()["detail"]
