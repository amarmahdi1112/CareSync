"""REST scheduling endpoints."""

import calendar
import json
from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Request, status
from sqlalchemy import String, cast, delete, exists, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, SessionDependency
from app.domain.scheduling import (
    ChildPreferences,
    ChildProfile,
    ChildTimeOverride,
    OperatingHours,
    SchedulerConfig,
    SchedulerEngine,
)
from app.domain.scheduling.imported_identity import may_use_claim_only_identity
from app.domain.scheduling.v3 import execute_v3_schedule
from app.models.generated_legacy import Base
from app.schemas.scheduling import ScheduleGenerationRequest

router = APIRouter(prefix="/schedules", tags=["scheduling"])
organizations = Base.metadata.tables["organizations"]
children = Base.metadata.tables["children"]
families = Base.metadata.tables["families"]
scheduled_attendance = Base.metadata.tables["scheduled_attendance"]
imported_claims = Base.metadata.tables["imported_claims"]
IMPORTED_CLAIM_PREFIX = "imported-claim:"


# School calendars are policy data, not facility closures. Keep the official
# baseline separate so an organization can add local PD days or explicitly
# exclude a baseline date without modifying the source definition.
_EDMONTON_REGULAR_SCHOOL_CALENDARS: dict[int, dict[str, Any]] = {
    2026: {
        "academic_year": "2025-26",
        "source": "Edmonton regular-school calendars (2025-26) — June ending dates",
        "source_detail": (
            "Built-in coverage: June 24-30 weekdays after the last instruction day, "
            "June 23, 2026"
        ),
        "days": (
            ("2026-06-24", "No regular classes after last instruction day"),
            ("2026-06-25", "Summer break"),
            ("2026-06-26", "Summer break"),
            ("2026-06-29", "Summer break"),
            ("2026-06-30", "Summer break"),
        ),
    }
}


def _edmonton_school_calendar(year: int) -> dict[str, Any]:
    definition = _EDMONTON_REGULAR_SCHOOL_CALENDARS.get(year)
    if definition is None:
        return {
            "academicYear": None,
            "source": "No built-in Edmonton regular-school calendar for this year",
            "sourceDetail": "Add and save school-off dates manually.",
            "automatic": [],
        }
    return {
        "academicYear": definition["academic_year"],
        "source": definition["source"],
        "sourceDetail": definition["source_detail"],
        "automatic": [
            {"date": value, "name": name, "kind": "automatic"}
            for value, name in definition["days"]
        ],
    }


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _easter_sunday(year: int) -> date:
    """Gregorian Easter calculation valid for the years supported by the scheduler."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    month_carry = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * month_carry) // 451
    month = (h + month_carry - 7 * m + 114) // 31
    day = (h + month_carry - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _alberta_holidays(year: int, include_optional: bool = False) -> list[dict[str, Any]]:
    may_25 = date(year, 5, 25)
    victoria_day = may_25 - timedelta(days=(may_25.weekday() - calendar.MONDAY) % 7 or 7)
    canada_day = date(year, 7, 1)
    if canada_day.weekday() == calendar.SUNDAY:
        canada_day = date(year, 7, 2)
    easter = _easter_sunday(year)
    holidays = [
        (date(year, 1, 1), "New Year's Day", "statutory"),
        (_nth_weekday(year, 2, calendar.MONDAY, 3), "Alberta Family Day", "statutory"),
        (easter - timedelta(days=2), "Good Friday", "statutory"),
        (victoria_day, "Victoria Day", "statutory"),
        (canada_day, "Canada Day", "statutory"),
        (_nth_weekday(year, 9, calendar.MONDAY, 1), "Labour Day", "statutory"),
        (_nth_weekday(year, 10, calendar.MONDAY, 2), "Thanksgiving Day", "statutory"),
        (date(year, 11, 11), "Remembrance Day", "statutory"),
        (date(year, 12, 25), "Christmas Day", "statutory"),
    ]
    if include_optional:
        holidays.extend(
            [
                (easter + timedelta(days=1), "Easter Monday", "optional"),
                (_nth_weekday(year, 8, calendar.MONDAY, 1), "Heritage Day", "optional"),
                (date(year, 9, 30), "National Day for Truth and Reconciliation", "optional"),
                (date(year, 12, 26), "Boxing Day", "optional"),
            ]
        )
    return [
        {"date": holiday.isoformat(), "name": name, "kind": kind}
        for holiday, name, kind in sorted(holidays)
    ]


def _system_preferences(current_user: CurrentUser, session: SessionDependency) -> dict:
    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization required")
    raw = session.scalar(
        select(organizations.c.system_preferences).where(
            organizations.c.id == current_user.organization_id
        )
    )
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


@router.get("/closures")
def schedule_closures(
    current_user: CurrentUser,
    session: SessionDependency,
    year: int = Query(..., ge=2000, le=2100),
) -> dict[str, Any]:
    preferences = _system_preferences(current_user, session)
    scheduler = preferences.get("scheduler_closures") or {}
    include_optional = bool(scheduler.get("include_optional_holidays", False))
    custom = [
        item
        for item in (scheduler.get("custom_days") or [])
        if str(item.get("date", "")).startswith(f"{year}-")
    ]
    return {
        "year": year,
        "province": "AB",
        "statutory": _alberta_holidays(year, include_optional),
        "custom": custom,
        "includeOptionalHolidays": include_optional,
    }


@router.get("/school-calendar")
def schedule_school_calendar(
    current_user: CurrentUser,
    session: SessionDependency,
    year: int = Query(..., ge=2000, le=2100),
) -> dict[str, Any]:
    baseline = _edmonton_school_calendar(year)
    automatic = baseline["automatic"]
    automatic_dates = {item["date"] for item in automatic}
    preferences = _system_preferences(current_user, session)
    scheduler = preferences.get("scheduler_school_calendar") or {}
    custom = [
        {
            "date": str(item["date"]),
            "name": str(item.get("name") or "School off"),
            "kind": "custom",
        }
        for item in (scheduler.get("custom_days") or [])
        if isinstance(item, dict)
        and str(item.get("date", "")).startswith(f"{year}-")
    ]
    excluded = sorted(
        value
        for value in {str(item) for item in (scheduler.get("excluded_automatic_days") or [])}
        if value.startswith(f"{year}-") and value in automatic_dates
    )
    effective_by_date = {
        item["date"]: item for item in automatic if item["date"] not in set(excluded)
    }
    effective_by_date.update({item["date"]: item for item in custom})
    return {
        "year": year,
        "jurisdiction": "Edmonton, Alberta",
        **baseline,
        "custom": sorted(custom, key=lambda item: item["date"]),
        "excludedAutomaticDays": excluded,
        "effective": sorted(effective_by_date.values(), key=lambda item: item["date"]),
        "hasOfficialDefaults": bool(automatic),
    }


@router.patch("/school-calendar")
def update_schedule_school_calendar(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )
    try:
        year = int(payload.get("year"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="School calendar year must be between 2000 and 2100",
        ) from exc
    if not 2000 <= year <= 2100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="School calendar year must be between 2000 and 2100",
        )

    baseline = _edmonton_school_calendar(year)
    automatic_dates = {item["date"] for item in baseline["automatic"]}
    custom_days: list[dict[str, str]] = []
    seen_custom: set[str] = set()
    for item in payload.get("customDays") or []:
        try:
            value = str(item["date"])
            parsed = date.fromisoformat(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each custom school-off day needs a valid ISO date",
            ) from exc
        if parsed.year != year:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Custom school-off dates must be in the requested calendar year",
            )
        if value in automatic_dates or value in seen_custom:
            continue
        seen_custom.add(value)
        custom_days.append(
            {"date": value, "name": str(item.get("name") or "School off")}
        )

    excluded: list[str] = []
    for raw_value in payload.get("excludedAutomaticDays") or []:
        value = str(raw_value)
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Excluded automatic school-off days must use valid ISO dates",
            ) from exc
        if parsed.year != year or value not in automatic_dates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only automatic dates in the requested year can be excluded",
            )
        if value not in excluded:
            excluded.append(value)

    preferences = _system_preferences(current_user, session)
    existing = preferences.get("scheduler_school_calendar") or {}
    other_custom = [
        item
        for item in (existing.get("custom_days") or [])
        if isinstance(item, dict)
        and not str(item.get("date", "")).startswith(f"{year}-")
    ]
    other_excluded = [
        str(item)
        for item in (existing.get("excluded_automatic_days") or [])
        if not str(item).startswith(f"{year}-")
    ]
    preferences["scheduler_school_calendar"] = {
        "custom_days": [*other_custom, *custom_days],
        "excluded_automatic_days": [*other_excluded, *excluded],
    }
    session.execute(
        update(organizations)
        .where(organizations.c.id == current_user.organization_id)
        .values(system_preferences=json.dumps(preferences))
    )
    session.commit()
    return schedule_school_calendar(current_user, session, year)


@router.patch("/closures")
def update_schedule_closures(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict[str, Any]:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )
    preferences = _system_preferences(current_user, session)
    custom_days = payload.get("customDays") or []
    for item in custom_days:
        try:
            date.fromisoformat(str(item["date"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each custom closure needs a valid ISO date",
            ) from exc
    preferences["scheduler_closures"] = {
        "include_optional_holidays": bool(payload.get("includeOptionalHolidays", False)),
        "custom_days": custom_days,
    }
    session.execute(
        update(organizations)
        .where(organizations.c.id == current_user.organization_id)
        .values(system_preferences=json.dumps(preferences))
    )
    session.commit()
    return schedule_closures(
        current_user,
        session,
        int(payload.get("year") or date.today().year),
    )


@router.post("/generate", response_model=None)
def generate_schedule(
    body: ScheduleGenerationRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict[str, Any]:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The authenticated user must belong to an organization",
        )
    preferences = _system_preferences(current_user, session)
    closure_policy = preferences.get("scheduler_closures") or {}
    include_optional = bool(closure_policy.get("include_optional_holidays", False))
    years = {date.fromisoformat(value).year for value in body.open_days}
    closed_dates = {
        item["date"] for year in years for item in _alberta_holidays(year, include_optional)
    }
    closed_dates.update(
        str(item.get("date"))
        for item in (closure_policy.get("custom_days") or [])
        if item.get("date")
    )
    conflicts = sorted(set(body.open_days) & closed_dates)
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Open days include statutory or daycare closure dates: {', '.join(conflicts)}"
            ),
        )
    config = SchedulerConfig(
        open_days=tuple(body.open_days),
        capacity=body.capacity,
        operating_hours=OperatingHours(body.operating_hours.start, body.operating_hours.end),
        school_off_days=tuple(body.school_off_days),
        daily_capacity_min=body.daily_capacity_min,
        daily_capacity_max=body.daily_capacity_max,
        enable_predictions=body.enable_predictions,
        enable_fairness_optimization=body.enable_fairness_optimization,
        enable_sibling_coherence=body.enable_sibling_coherence,
        enable_audit_trail=body.enable_audit_trail,
        max_iterations=body.max_iterations,
        seed=body.seed,
        child_time_overrides=tuple(
            ChildTimeOverride(
                item.child_identifier,
                tuple(item.days_of_week),
                item.start_time_1,
                item.end_time_1,
                item.start_time_2,
                item.end_time_2,
            )
            for item in body.child_time_overrides
        ),
    )
    profiles = []
    for item in body.children:
        preferences = None
        if item.preferences:
            source = item.preferences
            preferences = ChildPreferences(
                preferred_arrival_time=source.preferred_arrival_time,
                preferred_departure_time=source.preferred_departure_time,
                preferred_days=tuple(source.preferred_days),
                excluded_days=tuple(source.excluded_days),
                start_time_1=source.start_time_1,
                end_time_1=source.end_time_1,
                start_time_2=source.start_time_2,
                end_time_2=source.end_time_2,
                friend_ids=tuple(source.friend_ids),
                avoid_child_ids=tuple(source.avoid_child_ids),
            )
        profiles.append(
            ChildProfile(
                item.id,
                item.name,
                item.family_id,
                item.care_type,  # type: ignore[arg-type]
                item.total_claimed_hours,
                item.enrollment_date,
                preferences,
            )
        )
    engine_version = request.app.state.settings.scheduler_engine_version
    try:
        result = (
            execute_v3_schedule(config, profiles)
            if engine_version == "v3"
            else SchedulerEngine(config, profiles).execute()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        if engine_version != "v3":
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="V3 scheduling failed its independent safety audit; nothing was persisted",
        ) from exc
    payload = asdict(result)
    payload["persisted"] = False
    payload["persisted_entries"] = 0
    if not body.persist:
        return payload
    if engine_version == "v3" and (
        result.stats.completion_percentage != 100
        or any(warning.severity == "critical" for warning in result.warnings)
    ):
        return payload
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )

    requested_uuid_ids: set[UUID] = set()
    requested_imported_claim_ids: set[UUID] = set()
    for item in body.children:
        try:
            if item.id.startswith(IMPORTED_CLAIM_PREFIX):
                requested_imported_claim_ids.add(UUID(item.id.removeprefix(IMPORTED_CLAIM_PREFIX)))
            else:
                requested_uuid_ids.add(UUID(item.id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Persisted schedules require an existing child ID or a valid imported-claim ID"
                ),
            ) from exc
    owned_ids = {
        str(value)
        for value in session.scalars(
            select(children.c.id)
            .select_from(children.join(families, children.c.family_id == families.c.id))
            .where(
                families.c.organization_id == current_user.organization_id,
                children.c.id.in_(requested_uuid_ids),
            )
        )
    }
    if owned_ids != {str(value) for value in requested_uuid_ids}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Every persisted schedule child must belong to the current organization",
        )
    if requested_imported_claim_ids:
        if not body.source_claim_batch_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Claim-only schedule participants require a source import batch",
            )
        batch_identity_rows = list(
            session.execute(
                select(
                    imported_claims.c.id,
                    imported_claims.c.matched_child_id,
                    imported_claims.c.date_of_birth.label("claim_date_of_birth"),
                    children.c.date_of_birth.label("matched_child_date_of_birth"),
                )
                .select_from(
                    imported_claims.outerjoin(
                        children,
                        children.c.id == imported_claims.c.matched_child_id,
                    )
                )
                .where(
                    imported_claims.c.organization_id == current_user.organization_id,
                    imported_claims.c.import_batch_id == body.source_claim_batch_id,
                )
            ).mappings()
        )
        group_sizes: dict[UUID, int] = {}
        exact_dob_anchors: set[UUID] = set()
        rows_by_id = {row["id"]: row for row in batch_identity_rows}
        for row in batch_identity_rows:
            matched_child_id = row["matched_child_id"]
            if matched_child_id is None:
                continue
            group_sizes[matched_child_id] = group_sizes.get(matched_child_id, 0) + 1
            if (
                row["claim_date_of_birth"] is not None
                and row["claim_date_of_birth"] == row["matched_child_date_of_birth"]
            ):
                exact_dob_anchors.add(matched_child_id)
        owned_imported_claim_ids = {
            claim_id
            for claim_id in requested_imported_claim_ids
            if (row := rows_by_id.get(claim_id)) is not None
            and may_use_claim_only_identity(
                matched_child_id=row["matched_child_id"],
                claim_date_of_birth=row["claim_date_of_birth"],
                matched_child_date_of_birth=row["matched_child_date_of_birth"],
                matched_group_size=group_sizes.get(row["matched_child_id"], 0),
                has_exact_dob_anchor=row["matched_child_id"] in exact_dob_anchors,
            )
        }
        if owned_imported_claim_ids != requested_imported_claim_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Every claim-only schedule participant must be unmatched or an anchored "
                    "duplicate with a contradictory birth date in the current organization's "
                    "selected import batch"
                ),
            )

    entry_ids = [uuid4() for _ in result.entries]
    values = [
        {
            "id": entry_id,
            "child_id": entry.child_id,
            "batch_id": result.batch_id,
            "date": date.fromisoformat(entry.date),
            "mode": "OVERRIDE",
            "is_locked": False,
            "startTime1": entry.start_time,
            "endTime1": entry.end_time,
            "startTime2": entry.start_time_2,
            "endTime2": entry.end_time_2,
            "source_claim_batch_id": body.source_claim_batch_id,
        }
        for entry_id, entry in zip(entry_ids, result.entries, strict=True)
    ]
    try:
        for start in range(0, len(values), 1_000):
            session.execute(insert(scheduled_attendance), values[start : start + 1_000])
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The schedule could not be saved because a database constraint failed",
        ) from exc
    for entry_payload, entry_id in zip(payload["entries"], entry_ids, strict=True):
        entry_payload["id"] = str(entry_id)
    payload["persisted"] = True
    payload["persisted_entries"] = len(values)
    return payload


def _owned_schedule_condition(organization_id: UUID):
    return or_(
        exists(
            select(1)
            .select_from(children.join(families, children.c.family_id == families.c.id))
            .where(
                func.replace(cast(children.c.id, String), "-", "")
                == func.replace(cast(scheduled_attendance.c.child_id, String), "-", ""),
                families.c.organization_id == organization_id,
            )
        ),
        exists(
            select(1).where(
                imported_claims.c.organization_id == organization_id,
                imported_claims.c.import_batch_id == scheduled_attendance.c.source_claim_batch_id,
                func.replace(cast(imported_claims.c.id, String), "-", "")
                == func.replace(
                    func.replace(
                        cast(scheduled_attendance.c.child_id, String), IMPORTED_CLAIM_PREFIX, ""
                    ),
                    "-",
                    "",
                ),
                scheduled_attendance.c.child_id.startswith(IMPORTED_CLAIM_PREFIX),
            )
        ),
    )


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_batch(
    batch_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    confirm: bool = False,
) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )
    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization required")
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Schedule batch deletion requires confirm=true",
        )
    session.execute(
        delete(scheduled_attendance).where(
            scheduled_attendance.c.batch_id == batch_id,
            _owned_schedule_condition(current_user.organization_id),
        )
    )
    session.commit()
