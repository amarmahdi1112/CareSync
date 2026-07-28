"""Organization-scoped saved claim report reads."""

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import Base

router = APIRouter(prefix="/claim-reports", tags=["claim reports"])
tables = Base.metadata.tables


def _organization_id(current_user: CurrentUser) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An organization is required for claim reports",
        )
    return current_user.organization_id


def _notes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
    return [str(value)]


def _claim_payload(row) -> dict:
    return {
        "childId": row["child_id"],
        "childName": row["child_name"],
        "ageInYears": row["age_in_years"],
        "ageInMonths": row["age_in_months"],
        "careCategory": row["care_category"],
        "behavioralProfile": row["behavioral_profile"],
        "isProrated": row["is_prorated"],
        "enrollmentDate": row["enrollment_date"],
        "projectedHours": row["projected_hours"],
        "projectedAttendanceDays": row["projected_attendance_days"],
        "baseHoursBeforeProration": row["base_hours_before_proration"],
        "notes": _notes(row["notes"]),
        "calculationDetails": {
            "totalBusinessDays": row["total_business_days"],
            "schoolBreakDays": row["school_break_days"],
            "regularSchoolDays": row["regular_school_days"],
            "averageHoursPerDay": row["average_hours_per_day"],
            "capacityLimitedDays": row["capacity_limited_days"],
        },
    }


def _report_payload(row, claims: list[dict] | None = None) -> dict:
    return {
        "id": row["id"],
        "reportName": row["report_name"],
        "created_at": row["created_at"],
        "createdBy": row["created_by"] or "system",
        "description": row["description"],
        "report": {
            "targetMonth": row["target_month"],
            "targetYear": row["target_year"],
            "totalChildrenProcessed": row["total_children_processed"],
            "totalProjectedHours": row["total_projected_hours"],
            "averageHoursPerChild": row["average_hours_per_child"],
            "fullTimeChildren": row["full_time_children"],
            "schoolAgeChildren": row["school_age_children"],
            "proratedChildren": row["prorated_children"],
            "claims": claims or [],
        },
    }


@router.get("")
def list_claim_reports(current_user: CurrentUser, session: SessionDependency) -> list[dict]:
    reports = tables["generated_claim_reports"]
    rows = session.execute(
        select(reports)
        .where(reports.c.organization_id == _organization_id(current_user))
        .order_by(reports.c.created_at.desc())
    ).mappings()
    return [_report_payload(row) for row in rows]


@router.get("/{report_id}")
def get_claim_report(
    report_id: UUID,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict:
    reports = tables["generated_claim_reports"]
    claims = tables["generated_claims"]
    row = (
        session.execute(
            select(reports).where(
                reports.c.id == report_id,
                reports.c.organization_id == _organization_id(current_user),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim report not found")
    claim_rows = session.execute(
        select(claims).where(claims.c.report_id == report_id).order_by(claims.c.child_name.asc())
    ).mappings()
    return _report_payload(row, [_claim_payload(claim) for claim in claim_rows])
