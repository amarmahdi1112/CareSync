"""Administrator-operated, exact-retry admissions decision lifecycle."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jwt
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, func, or_, select

from app.api.basic.common import (
    commit_in_context,
    ensure_writable,
    flush_or_conflict,
    lock_client_operation,
)
from app.api.basic.dependencies import (
    AdmissionsDecideContext,
    AdmissionsManageContext,
    AdmissionsReadContext,
    BasicContext,
)
from app.api.dependencies import SessionDependency
from app.basic.admissions_decision_schemas import (
    AdmissionAllowedAction,
    AdmissionApplicationCorrect,
    AdmissionApplicationCreate,
    AdmissionApplicationStatus,
    AdmissionApplicationUpdate,
    AdmissionApplicationVersionCommand,
    AdmissionChildProjection,
    AdmissionCommittedVersions,
    AdmissionContactProjection,
    AdmissionConversionCandidateReview,
    AdmissionConversionChildCandidate,
    AdmissionConversionFamilyCandidate,
    AdmissionConversionProjection,
    AdmissionCurrentLane,
    AdmissionDetail,
    AdmissionDirectoryResponse,
    AdmissionLaneDirectory,
    AdmissionLaneFacility,
    AdmissionLaneProgram,
    AdmissionListItem,
    AdmissionOfferAccept,
    AdmissionOfferIssue,
    AdmissionOfferProjection,
    AdmissionOfferVersionCommand,
    AdmissionPipelineCounts,
    AdmissionPreferenceInput,
    AdmissionPreferenceProjection,
    AdmissionReplayReceipt,
    AdmissionTimelineEvent,
    AdmissionWaitlistEnter,
    AdmissionWaitlistItem,
    AdmissionWaitlistProjection,
    AdmissionWaitlistResponse,
    AdmissionWaitlistVersionCommand,
    AdmissionWorkspaceLane,
    AdmissionWorkspaceResponse,
)
from app.basic.childcare_commands import begin_command, record_command
from app.basic.models import (
    AdmissionApplication,
    AdmissionApplicationEvent,
    AdmissionApplicationPreference,
    AdmissionConversionLink,
    AdmissionOffer,
    AdmissionWaitlistEntry,
    Child,
    ChildcareCommandReceipt,
    Enrollment,
    Facility,
    Family,
    Guardian,
    Program,
    RealtimeEvent,
)
from app.basic.notifications import notify_organization_members
from app.basic.security import audit

router = APIRouter(prefix="/admissions", tags=["admissions decisions"])

_TERMINAL = frozenset({"accepted", "declined", "withdrawn"})
_CORRECTABLE = frozenset(
    {"submitted", "under_review", "waitlisted", "offered"}
)
_REFERENCE_PATTERN = re.compile(r"[^A-Z0-9]")
_OPEN_ENROLLMENT_STATUSES = ("pending", "active", "paused")
_CONVERSION_REVIEW_PURPOSE = "caresync.admission.conversion.review.v1"
_CONVERSION_REVIEW_LIFETIME = timedelta(minutes=10)
_MAX_CONVERSION_CANDIDATES = 50


@dataclass(frozen=True)
class _ConversionLockSet:
    """Canonical childcare rows held for one acceptance transaction."""

    families: dict[UUID, Family]
    children: dict[UUID, Child]


def _require_capability(request: Request) -> None:
    if not bool(
        getattr(request.app.state, "admissions_decision_spine_enabled", True)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "admissions_decision_spine_unavailable",
                "message": "The admissions decision spine is not installed.",
            },
        )


def _normalized_name(first_name: str, last_name: str) -> str:
    return " ".join(
        " ".join((first_name, last_name)).casefold().split()
    )


def _normalized_telephone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _sql_normalized_telephone(column: Any) -> Any:
    value = func.coalesce(column, "")
    for character in (" ", "-", "(", ")", "+", ".", "/"):
        value = func.replace(value, character, "")
    return value


def _age_group(birth_date: Any, *, today: Any) -> str:
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    if today.day < birth_date.day:
        months -= 1
    if months <= 19:
        return "Infant"
    if months <= 36:
        return "Toddler"
    if months <= 77:
        return "Preschool"
    return "School-Age"


def _local_today(timezone_name: str) -> Any:
    try:
        return datetime.now(UTC).astimezone(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        raise HTTPException(
            status_code=422,
            detail="Timezone must be corrected before changing child records",
        ) from None


def _validate_child_date_of_birth(
    context: BasicContext,
    payload: AdmissionApplicationCreate
    | AdmissionApplicationUpdate
    | AdmissionApplicationCorrect,
) -> None:
    if payload.child.date_of_birth > _local_today(context.organization.timezone):
        raise HTTPException(
            status_code=422,
            detail="date_of_birth cannot be in the future",
        )


def _conversion_snapshot_digest(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _conversion_candidate_state(
    session: SessionDependency,
    application: AdmissionApplication,
) -> tuple[
    list[AdmissionConversionFamilyCandidate],
    list[AdmissionConversionChildCandidate],
    dict[str, Any],
]:
    child_statement = (
        select(Child)
        .where(
            Child.organization_id == application.organization_id,
            Child.date_of_birth == application.child_date_of_birth,
            func.lower(func.trim(Child.first_name))
            == application.child_first_name.strip().lower(),
            func.lower(func.trim(Child.last_name))
            == application.child_last_name.strip().lower(),
        )
        .order_by(Child.id)
        .limit(_MAX_CONVERSION_CANDIDATES + 1)
        .execution_options(populate_existing=True)
    )
    children = list(session.scalars(child_statement))

    guardian_filters = []
    if application.contact_normalized_email:
        guardian_filters.append(
            func.lower(func.trim(Guardian.email))
            == application.contact_normalized_email
        )
    if application.contact_normalized_telephone:
        guardian_filters.append(
            or_(
                _sql_normalized_telephone(Guardian.cell_phone)
                == application.contact_normalized_telephone,
                _sql_normalized_telephone(Guardian.home_phone)
                == application.contact_normalized_telephone,
                _sql_normalized_telephone(Guardian.work_phone)
                == application.contact_normalized_telephone,
            )
        )
    guardians: list[Guardian] = []
    if guardian_filters:
        guardian_statement = (
            select(Guardian)
            .where(
                Guardian.organization_id == application.organization_id,
                Guardian.retired_at.is_(None),
                or_(*guardian_filters),
            )
            .order_by(Guardian.id)
            .limit(_MAX_CONVERSION_CANDIDATES + 1)
            .execution_options(populate_existing=True)
        )
        guardians = list(session.scalars(guardian_statement))

    if (
        len(children) > _MAX_CONVERSION_CANDIDATES
        or len(guardians) > _MAX_CONVERSION_CANDIDATES
    ):
        raise _conflict(
            "admission_candidate_set_too_large",
            "The possible duplicate set is too large for safe conversion review.",
        )

    family_reasons: dict[UUID, set[str]] = {}
    for child in children:
        family_reasons.setdefault(child.family_id, set()).add(
            "child_name_and_date_of_birth"
        )
    for guardian in guardians:
        reasons = family_reasons.setdefault(guardian.family_id, set())
        if (
            application.contact_normalized_email
            and guardian.email.strip().casefold()
            == application.contact_normalized_email
        ):
            reasons.add("primary_contact_email")
        if application.contact_normalized_telephone and any(
            _normalized_telephone(value or "")
            == application.contact_normalized_telephone
            for value in (
                guardian.cell_phone,
                guardian.home_phone,
                guardian.work_phone,
            )
        ):
            reasons.add("primary_contact_telephone")
    if len(family_reasons) > _MAX_CONVERSION_CANDIDATES:
        raise _conflict(
            "admission_candidate_set_too_large",
            "The possible duplicate set is too large for safe conversion review.",
        )

    family_ids = sorted(family_reasons, key=str)
    family_statement = (
        select(Family)
        .where(
            Family.organization_id == application.organization_id,
            Family.id.in_(family_ids),
        )
        .order_by(Family.id)
        .execution_options(populate_existing=True)
    )
    families = list(session.scalars(family_statement)) if family_ids else []
    if len(families) != len(family_ids):
        raise _conflict(
            "admission_candidate_set_changed",
            "A possible duplicate family changed during conversion review.",
        )

    child_ids = [child.id for child in children]
    enrollment_statement = (
        select(Enrollment)
        .where(
            Enrollment.organization_id == application.organization_id,
            Enrollment.child_id.in_(child_ids),
            Enrollment.status.in_(_OPEN_ENROLLMENT_STATUSES),
        )
        .order_by(Enrollment.child_id, Enrollment.id)
        .execution_options(populate_existing=True)
    )
    open_child_ids = (
        {enrollment.child_id for enrollment in session.scalars(enrollment_statement)}
        if child_ids
        else set()
    )

    family_candidates = [
        AdmissionConversionFamilyCandidate(
            id=family.id,
            display_label=family.name,
            version=family.version,
            status=family.status,
            match_reasons=sorted(family_reasons[family.id]),
        )
        for family in families
    ]
    child_candidates = [
        AdmissionConversionChildCandidate(
            id=child.id,
            family_id=child.family_id,
            display_label=(
                f"{child.first_name} {child.last_name} · "
                f"{child.date_of_birth.isoformat()}"
            ),
            version=child.version,
            is_active=child.is_active,
            match_reasons=sorted(
                {
                    "child_name_and_date_of_birth",
                    *family_reasons.get(child.family_id, set()),
                }
            ),
            has_open_enrollment=child.id in open_child_ids,
        )
        for child in children
    ]
    snapshot = {
        "families": [
            {"id": str(candidate.id), "version": candidate.version}
            for candidate in family_candidates
        ],
        "children": [
            {
                "id": str(candidate.id),
                "family_id": str(candidate.family_id),
                "version": candidate.version,
                "has_open_enrollment": candidate.has_open_enrollment,
            }
            for candidate in child_candidates
        ],
    }
    return family_candidates, child_candidates, snapshot


def _lock_conversion_resources(
    session: SessionDependency,
    application: AdmissionApplication,
    offer: AdmissionOffer,
    family_candidates: list[AdmissionConversionFamilyCandidate],
    child_candidates: list[AdmissionConversionChildCandidate],
) -> _ConversionLockSet:
    """Acquire the canonical lifecycle lock order after ID-only discovery.

    Admission rows are already locked before this helper runs and no canonical
    childcare command touches them.  Shared childcare resources are then held
    by class and stable UUID in the same order as child/enrollment commands:
    Family -> Child -> Facility -> Enrollment -> Program.

    Guardian matches need no independent row lock.  Every canonical guardian
    writer locks its Family first, so the Family locks below stabilize those
    match facts while avoiding an extra resource class in the shared order.
    """

    organization_id = application.organization_id
    family_ids = sorted(
        {candidate.id for candidate in family_candidates},
        key=str,
    )
    child_ids = sorted(
        {candidate.id for candidate in child_candidates},
        key=str,
    )

    # Discover all row identities before taking the first shared childcare
    # lock.  Later statements only acquire this fixed set by resource class.
    enrollment_snapshots = (
        list(
            session.scalars(
                select(Enrollment)
                .where(
                    Enrollment.organization_id == organization_id,
                    Enrollment.child_id.in_(child_ids),
                    Enrollment.status.in_(_OPEN_ENROLLMENT_STATUSES),
                )
                .order_by(Enrollment.id)
            )
        )
        if child_ids
        else []
    )
    enrollment_ids = sorted(
        {enrollment.id for enrollment in enrollment_snapshots},
        key=str,
    )
    facility_ids = sorted(
        {
            offer.facility_id,
            *(enrollment.facility_id for enrollment in enrollment_snapshots),
        },
        key=str,
    )

    families = (
        {
            row.id: row
            for row in session.scalars(
                select(Family)
                .where(
                    Family.organization_id == organization_id,
                    Family.id.in_(family_ids),
                )
                .order_by(Family.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        }
        if family_ids
        else {}
    )
    if set(families) != set(family_ids):
        raise _conflict(
            "admission_review_stale",
            "A possible duplicate Family changed. Refresh candidates.",
        )

    children = (
        {
            row.id: row
            for row in session.scalars(
                select(Child)
                .where(
                    Child.organization_id == organization_id,
                    Child.id.in_(child_ids),
                )
                .order_by(Child.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        }
        if child_ids
        else {}
    )
    if set(children) != set(child_ids) or any(
        children[candidate.id].family_id != candidate.family_id
        for candidate in child_candidates
        if candidate.id in children
    ):
        raise _conflict(
            "admission_review_stale",
            "A possible duplicate Child changed. Refresh candidates.",
        )

    facilities = {
        row.id: row
        for row in session.scalars(
            select(Facility)
            .where(
                Facility.organization_id == organization_id,
                Facility.id.in_(facility_ids),
            )
            .order_by(Facility.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    if set(facilities) != set(facility_ids):
        raise _conflict(
            "admission_review_stale",
            "A related Facility changed. Refresh candidates.",
        )

    enrollments = (
        {
            row.id: row
            for row in session.scalars(
                select(Enrollment)
                .where(
                    Enrollment.organization_id == organization_id,
                    Enrollment.id.in_(enrollment_ids),
                )
                .order_by(Enrollment.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        }
        if enrollment_ids
        else {}
    )
    if set(enrollments) != set(enrollment_ids):
        raise _conflict(
            "admission_review_stale",
            "A possible duplicate Enrollment changed. Refresh candidates.",
        )

    program = session.scalar(
        select(Program)
        .where(
            Program.organization_id == organization_id,
            Program.id == offer.program_id,
        )
        .order_by(Program.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    facility = facilities.get(offer.facility_id)
    if (
        facility is None
        or facility.status != "active"
        or program is None
        or program.facility_id != facility.id
        or not program.is_active
    ):
        raise _conflict(
            "admission_lane_unavailable",
            "Select an active facility and program before continuing.",
            facility_id=str(offer.facility_id),
            program_id=str(offer.program_id),
        )
    return _ConversionLockSet(families=families, children=children)


def _conversion_review_token(
    request: Request,
    application: AdmissionApplication,
    offer: AdmissionOffer,
    snapshot: dict[str, Any],
) -> tuple[str, datetime]:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + _CONVERSION_REVIEW_LIFETIME
    token = jwt.encode(
        {
            "purpose": _CONVERSION_REVIEW_PURPOSE,
            "organization_id": str(application.organization_id),
            "application_id": str(application.id),
            "application_version": application.version,
            "offer_id": str(offer.id),
            "offer_version": offer.version,
            "candidate_snapshot_digest": _conversion_snapshot_digest(snapshot),
            "iat": issued_at,
            "exp": expires_at,
        },
        request.app.state.settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_at


def _decode_conversion_review_token(request: Request, token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            request.app.state.settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise _conflict(
            "admission_review_expired",
            "The duplicate review expired. Refresh candidates before accepting.",
        ) from None
    except (jwt.PyJWTError, TypeError, ValueError):
        raise _conflict(
            "admission_review_invalid",
            "The duplicate review proof is invalid.",
        ) from None
    if payload.get("purpose") != _CONVERSION_REVIEW_PURPOSE:
        raise _conflict(
            "admission_review_invalid",
            "The duplicate review proof is invalid.",
        )
    return payload


def _reference(application_id: UUID) -> str:
    suffix = _REFERENCE_PATTERN.sub("", application_id.hex.upper())[:12]
    return f"ADM-{suffix}"


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Admission application not found")


def _conflict(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message, **extra},
    )


def _application(
    session: SessionDependency,
    organization_id: UUID,
    application_id: UUID,
    *,
    lock: bool = False,
) -> AdmissionApplication:
    statement = select(AdmissionApplication).where(
        AdmissionApplication.organization_id == organization_id,
        AdmissionApplication.id == application_id,
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise _not_found()
    return value


def _require_application_version(
    application: AdmissionApplication, expected_version: int
) -> None:
    if application.version != expected_version:
        raise _conflict(
            "admission_version_conflict",
            "The admission application changed. Reload before retrying.",
            record_kind="application",
            record_id=str(application.id),
            expected_version=expected_version,
            current_version=application.version,
        )


def _require_waitlist_version(
    waitlist: AdmissionWaitlistEntry, expected_version: int
) -> None:
    if waitlist.version != expected_version:
        raise _conflict(
            "admission_version_conflict",
            "The waitlist entry changed. Reload before retrying.",
            record_kind="waitlist",
            record_id=str(waitlist.id),
            expected_version=expected_version,
            current_version=waitlist.version,
        )


def _require_offer_version(offer: AdmissionOffer, expected_version: int) -> None:
    if offer.version != expected_version:
        raise _conflict(
            "admission_version_conflict",
            "The admission offer changed. Reload before retrying.",
            record_kind="offer",
            record_id=str(offer.id),
            expected_version=expected_version,
            current_version=offer.version,
        )


def _require_state(
    application: AdmissionApplication,
    allowed: set[str] | frozenset[str],
    command: str,
) -> None:
    if application.status not in allowed:
        raise _conflict(
            "admission_transition_invalid",
            "The command is not valid from the current application state.",
            command=command,
            current_status=application.status,
        )


def _active_lane(
    session: SessionDependency,
    organization_id: UUID,
    facility_id: UUID,
    program_id: UUID,
) -> tuple[Facility, Program]:
    lanes = _lock_active_lanes(
        session,
        organization_id,
        [(facility_id, program_id)],
    )
    return lanes[(facility_id, program_id)]


def _lock_active_lanes(
    session: SessionDependency,
    organization_id: UUID,
    lane_ids: list[tuple[UUID, UUID]],
) -> dict[tuple[UUID, UUID], tuple[Facility, Program]]:
    """Lock lane rows by class and UUID, never by caller/rank order."""

    unique_lanes = sorted(set(lane_ids), key=lambda value: (str(value[0]), str(value[1])))
    facility_ids = sorted({value[0] for value in unique_lanes}, key=str)
    program_ids = sorted({value[1] for value in unique_lanes}, key=str)
    facilities = {
        facility.id: facility
        for facility in session.scalars(
            select(Facility)
            .where(
                Facility.organization_id == organization_id,
                Facility.id.in_(facility_ids),
            )
            .order_by(Facility.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    programs = {
        program.id: program
        for program in session.scalars(
            select(Program)
            .where(
                Program.organization_id == organization_id,
                Program.id.in_(program_ids),
            )
            .order_by(Program.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    lanes: dict[tuple[UUID, UUID], tuple[Facility, Program]] = {}
    for lane in unique_lanes:
        selected_facility = facilities.get(lane[0])
        selected_program = programs.get(lane[1])
        if (
            selected_facility is None
            or selected_facility.status != "active"
            or selected_program is None
            or not selected_program.is_active
            or selected_program.facility_id != selected_facility.id
        ):
            raise _conflict(
                "admission_lane_unavailable",
                "Select an active facility and program before continuing.",
                facility_id=str(lane[0]),
                program_id=str(lane[1]),
            )
        lanes[lane] = (selected_facility, selected_program)
    return lanes


def _current_preferences(
    session: SessionDependency,
    application: AdmissionApplication,
) -> list[AdmissionApplicationPreference]:
    return list(
        session.scalars(
            select(AdmissionApplicationPreference)
            .where(
                AdmissionApplicationPreference.organization_id
                == application.organization_id,
                AdmissionApplicationPreference.application_id == application.id,
                AdmissionApplicationPreference.retired_at.is_(None),
            )
            .order_by(AdmissionApplicationPreference.rank)
        )
    )


def _replace_preferences(
    session: SessionDependency,
    application: AdmissionApplication,
    preferences: list[AdmissionPreferenceInput],
    *,
    actor_user_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
) -> None:
    _lock_active_lanes(
        session,
        application.organization_id,
        [
            (preference.facility_id, preference.program_id)
            for preference in preferences
        ],
    )
    for preference in _current_preferences(session, application):
        preference.current_rank = None
        preference.current_lane_key = None
        preference.retired_by_user_id = actor_user_id
        preference.retired_operation_id = operation_id
        preference.retired_at = occurred_at
    session.flush()
    for value in preferences:
        session.add(
            AdmissionApplicationPreference(
                id=uuid4(),
                organization_id=application.organization_id,
                application_id=application.id,
                rank=value.rank,
                current_rank=value.rank,
                current_lane_key=f"{value.facility_id}:{value.program_id}",
                facility_id=value.facility_id,
                program_id=value.program_id,
                requested_start_date=value.desired_start_date,
                application_version=application.version,
                created_by_user_id=actor_user_id,
                created_operation_id=operation_id,
                created_at=occurred_at,
            )
        )


def _latest_waitlist(
    session: SessionDependency,
    application: AdmissionApplication,
    *,
    lock: bool = False,
) -> AdmissionWaitlistEntry | None:
    statement = (
        select(AdmissionWaitlistEntry)
        .where(
            AdmissionWaitlistEntry.organization_id == application.organization_id,
            AdmissionWaitlistEntry.application_id == application.id,
        )
        .order_by(
            AdmissionWaitlistEntry.priority_at.desc(),
            AdmissionWaitlistEntry.id.desc(),
        )
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _current_waitlist(
    session: SessionDependency,
    application: AdmissionApplication,
    *,
    lock: bool = False,
) -> AdmissionWaitlistEntry | None:
    statement = select(AdmissionWaitlistEntry).where(
        AdmissionWaitlistEntry.organization_id == application.organization_id,
        AdmissionWaitlistEntry.current_application_id == application.id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _latest_offer(
    session: SessionDependency,
    application: AdmissionApplication,
    *,
    lock: bool = False,
) -> AdmissionOffer | None:
    statement = (
        select(AdmissionOffer)
        .where(
            AdmissionOffer.organization_id == application.organization_id,
            AdmissionOffer.application_id == application.id,
        )
        .order_by(AdmissionOffer.issued_at.desc(), AdmissionOffer.id.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _current_offer(
    session: SessionDependency,
    application: AdmissionApplication,
    *,
    lock: bool = False,
) -> AdmissionOffer | None:
    statement = select(AdmissionOffer).where(
        AdmissionOffer.organization_id == application.organization_id,
        AdmissionOffer.open_application_id == application.id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def _conversion(
    session: SessionDependency, application: AdmissionApplication
) -> AdmissionConversionLink | None:
    return session.scalar(
        select(AdmissionConversionLink).where(
            AdmissionConversionLink.organization_id == application.organization_id,
            AdmissionConversionLink.application_id == application.id,
        )
    )


def _close_waitlist(
    waitlist: AdmissionWaitlistEntry,
    *,
    reason: str,
    actor_user_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
) -> None:
    waitlist.status = "closed"
    waitlist.current_application_id = None
    waitlist.version += 1
    waitlist.closure_reason = reason
    waitlist.closed_at = occurred_at
    waitlist.updated_at = occurred_at
    waitlist.updated_by_user_id = actor_user_id
    waitlist.last_operation_id = operation_id


def _event(
    session: SessionDependency,
    application: AdmissionApplication,
    *,
    command: str,
    from_status: str | None,
    reason_code: str | None,
    actor_user_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
) -> None:
    session.add(
        AdmissionApplicationEvent(
            id=uuid4(),
            organization_id=application.organization_id,
            application_id=application.id,
            application_version=application.version,
            command=command,
            from_status=from_status,
            to_status=application.status,
            reason_code=reason_code,
            actor_user_id=actor_user_id,
            client_operation_id=operation_id,
            occurred_at=occurred_at,
        )
    )


def _realtime(
    session: SessionDependency,
    application: AdmissionApplication,
    *,
    event_type: str,
    entity_type: Literal[
        "admission_application", "admission_waitlist", "admission_offer"
    ],
    entity_id: UUID,
    occurred_at: datetime,
) -> None:
    session.add(
        RealtimeEvent(
            id=uuid4(),
            organization_id=application.organization_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            occurred_at=occurred_at,
            payload={
                "application_id": str(application.id),
                "application_version": application.version,
                "operation_id": str(application.last_operation_id),
                "refresh_required": True,
            },
        )
    )


def _record(
    session: SessionDependency,
    application: AdmissionApplication,
    context: BasicContext,
    *,
    request_hash: str,
    client_operation_id: UUID,
    command_type: str,
    target_type: Literal[
        "admission_application", "admission_waitlist", "admission_offer"
    ],
    target_id: UUID,
    committed_version: int,
    operator_reason_code: str | None = None,
) -> None:
    record_command(
        session,
        organization_id=application.organization_id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=command_type,
        target_type=target_type,
        target_id=target_id,
        request_hash=request_hash,
        committed_version=committed_version,
        outcome={
            "action_route": f"/admissions/applications/{application.id}",
            "application_id": str(application.id),
        },
    )
    audit_details = {
        "application_id": str(application.id),
        "application_version": application.version,
        "operation_id": str(client_operation_id),
    }
    if operator_reason_code is not None:
        audit_details["operator_reason_code"] = operator_reason_code
    audit(
        session,
        organization_id=application.organization_id,
        actor_user_id=context.user.id,
        action=command_type,
        entity_type=target_type,
        entity_id=target_id,
        details=audit_details,
    )


def _begin(
    session: SessionDependency,
    context: BasicContext,
    *,
    client_operation_id: UUID,
    command_type: str,
    target_type: str,
    target_scope: UUID | str,
    intent: dict[str, Any],
) -> tuple[str, UUID | None]:
    request_hash, receipt = begin_command(
        session,
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        client_operation_id=client_operation_id,
        command_type=command_type,
        target_type=target_type,
        target_scope=target_scope,
        intent=intent,
    )
    if receipt is None:
        return request_hash, None
    application_id = receipt.outcome.get("application_id")
    if application_id is None and receipt.target_type == "admission_application":
        application_id = receipt.target_id
    try:
        return request_hash, UUID(str(application_id))
    except (TypeError, ValueError):
        raise _conflict(
            "admission_receipt_incoherent",
            "The committed admission receipt cannot be reconciled.",
        ) from None


def _waitlist_position(
    session: SessionDependency, waitlist: AdmissionWaitlistEntry
) -> int | None:
    if waitlist.status not in {"active", "offered"}:
        return None
    return int(
        session.scalar(
            select(func.count())
            .select_from(AdmissionWaitlistEntry)
            .where(
                AdmissionWaitlistEntry.organization_id == waitlist.organization_id,
                AdmissionWaitlistEntry.facility_id == waitlist.facility_id,
                AdmissionWaitlistEntry.program_id == waitlist.program_id,
                AdmissionWaitlistEntry.status.in_(("active", "offered")),
                or_(
                    AdmissionWaitlistEntry.priority_at < waitlist.priority_at,
                    and_(
                        AdmissionWaitlistEntry.priority_at == waitlist.priority_at,
                        AdmissionWaitlistEntry.id <= waitlist.id,
                    ),
                ),
            )
        )
        or 0
    )


def _waitlist_positions(
    session: SessionDependency,
    organization_id: UUID,
    entry_ids: list[UUID],
) -> dict[UUID, int]:
    if not entry_ids:
        return {}
    ranked = (
        select(
            AdmissionWaitlistEntry.id.label("entry_id"),
            func.row_number()
            .over(
                partition_by=(
                    AdmissionWaitlistEntry.facility_id,
                    AdmissionWaitlistEntry.program_id,
                ),
                order_by=(
                    AdmissionWaitlistEntry.priority_at,
                    AdmissionWaitlistEntry.id,
                ),
            )
            .label("position"),
        )
        .where(
            AdmissionWaitlistEntry.organization_id == organization_id,
            AdmissionWaitlistEntry.status.in_(("active", "offered")),
        )
        .subquery()
    )
    return {
        entry_id: int(position)
        for entry_id, position in session.execute(
            select(ranked.c.entry_id, ranked.c.position).where(
                ranked.c.entry_id.in_(entry_ids)
            )
        ).tuples()
    }


def _allowed_actions(status_value: str) -> list[AdmissionAllowedAction]:
    mapping: dict[str, list[AdmissionAllowedAction]] = {
        "draft": ["update", "submit"],
        "submitted": ["start_review", "correct", "withdraw"],
        "under_review": [
            "correct",
            "enter_waitlist",
            "decline",
            "withdraw",
            "issue_offer",
        ],
        "waitlisted": [
            "correct",
            "reopen_review",
            "decline",
            "withdraw",
            "issue_offer",
        ],
        "offered": [
            "withdraw_offer",
            "decline_offer",
            "withdraw",
            "accept_and_convert",
        ],
    }
    return mapping.get(status_value, [])


def _names(
    session: SessionDependency,
    organization_id: UUID,
) -> tuple[dict[UUID, str], dict[UUID, str]]:
    facilities = {
        facility_id: name
        for facility_id, name in session.execute(
            select(Facility.id, Facility.name).where(
                Facility.organization_id == organization_id
            )
        ).tuples()
    }
    programs = {
        program_id: name
        for program_id, name in session.execute(
            select(Program.id, Program.name).where(
                Program.organization_id == organization_id
            )
        ).tuples()
    }
    return facilities, programs


def _detail(
    session: SessionDependency,
    application: AdmissionApplication,
    *,
    replayed: bool = False,
    replay_operation_id: UUID | None = None,
) -> AdmissionDetail:
    replay_receipt: ChildcareCommandReceipt | None = None
    if replay_operation_id is not None:
        replay_receipt = session.scalar(
            select(ChildcareCommandReceipt).where(
                ChildcareCommandReceipt.organization_id
                == application.organization_id,
                ChildcareCommandReceipt.client_operation_id
                == replay_operation_id,
            )
        )
        if replay_receipt is None or replay_receipt.outcome.get(
            "application_id"
        ) != str(application.id):
            raise _conflict(
                "admission_receipt_incoherent",
                "The committed admission replay receipt cannot be reconciled.",
            )
    facilities, programs = _names(session, application.organization_id)
    preferences = _current_preferences(session, application)
    waitlist = _latest_waitlist(session, application)
    offer = _latest_offer(session, application)
    conversion = _conversion(session, application)
    event_rows = list(
        session.scalars(
            select(AdmissionApplicationEvent)
            .where(
                AdmissionApplicationEvent.organization_id
                == application.organization_id,
                AdmissionApplicationEvent.application_id == application.id,
            )
            .order_by(AdmissionApplicationEvent.application_version.desc())
            .limit(200)
        )
    )
    event_rows.reverse()
    timeline_total = int(
        session.scalar(
            select(func.count())
            .select_from(AdmissionApplicationEvent)
            .where(
                AdmissionApplicationEvent.organization_id
                == application.organization_id,
                AdmissionApplicationEvent.application_id == application.id,
            )
        )
        or 0
    )
    waitlist_projection = (
        AdmissionWaitlistProjection(
            id=waitlist.id,
            status=waitlist.status,
            version=waitlist.version,
            facility_id=waitlist.facility_id,
            facility_name=facilities.get(waitlist.facility_id, "Unavailable facility"),
            program_id=waitlist.program_id,
            program_name=programs.get(waitlist.program_id, "Unavailable program"),
            requested_start_date=waitlist.requested_start_date,
            priority_at=waitlist.priority_at,
            position=_waitlist_position(session, waitlist),
            closure_reason=waitlist.closure_reason,
            created_at=waitlist.created_at,
            updated_at=waitlist.updated_at,
            closed_at=waitlist.closed_at,
        )
        if waitlist is not None
        else None
    )
    offer_projection = (
        AdmissionOfferProjection(
            id=offer.id,
            status=offer.status,
            version=offer.version,
            facility_id=offer.facility_id,
            facility_name=facilities.get(offer.facility_id, "Unavailable facility"),
            program_id=offer.program_id,
            program_name=programs.get(offer.program_id, "Unavailable program"),
            proposed_start_date=offer.proposed_start_date,
            respond_by_date=offer.respond_by_date,
            prior_application_status=offer.prior_application_status,
            issued_at=offer.issued_at,
            withdrawn_at=offer.withdrawn_at,
            declined_at=offer.declined_at,
            accepted_at=offer.accepted_at,
        )
        if offer is not None
        else None
    )
    return AdmissionDetail(
        id=application.id,
        organization_id=application.organization_id,
        reference=application.reference,
        source=application.source,
        status=application.status,
        version=application.version,
        child=AdmissionChildProjection(
            first_name=application.child_first_name,
            last_name=application.child_last_name,
            date_of_birth=application.child_date_of_birth,
        ),
        contact=AdmissionContactProjection(
            first_name=application.contact_first_name,
            last_name=application.contact_last_name,
            relationship=application.contact_relationship,
            email=application.contact_email,
            telephone=application.contact_telephone,
        ),
        internal_note=application.internal_note,
        preferences=[
            AdmissionPreferenceProjection(
                id=preference.id,
                rank=preference.rank,
                facility_id=preference.facility_id,
                facility_name=facilities.get(
                    preference.facility_id, "Unavailable facility"
                ),
                program_id=preference.program_id,
                program_name=programs.get(
                    preference.program_id, "Unavailable program"
                ),
                requested_start_date=preference.requested_start_date,
                application_version=preference.application_version,
            )
            for preference in preferences
        ],
        waitlist=waitlist_projection,
        offer=offer_projection,
        conversion=(
            AdmissionConversionProjection(
                id=conversion.id,
                resolution_mode=conversion.resolution_mode,
                family_id=conversion.family_id,
                child_id=conversion.child_id,
                enrollment_id=conversion.enrollment_id,
                converted_at=conversion.converted_at,
            )
            if conversion is not None
            else None
        ),
        timeline=[
            AdmissionTimelineEvent(
                id=event.id,
                application_version=event.application_version,
                command=event.command,
                from_status=event.from_status,
                to_status=event.to_status,
                reason_code=event.reason_code,
                actor_user_id=event.actor_user_id,
                client_operation_id=event.client_operation_id,
                occurred_at=event.occurred_at,
            )
            for event in event_rows
        ],
        timeline_total=timeline_total,
        allowed_actions=_allowed_actions(application.status),
        committed_versions=AdmissionCommittedVersions(
            application=application.version,
            waitlist=waitlist.version if waitlist is not None else None,
            offer=offer.version if offer is not None else None,
        ),
        replayed=replayed,
        replay_receipt=(
            AdmissionReplayReceipt(
                command_type=replay_receipt.command_type,
                target_type=replay_receipt.target_type,
                target_id=replay_receipt.target_id,
                committed_version=replay_receipt.committed_version,
            )
            if replay_receipt is not None
            else None
        ),
        created_at=application.created_at,
        updated_at=application.updated_at,
        submitted_at=application.submitted_at,
        review_started_at=application.review_started_at,
        terminal_at=application.terminal_at,
    )


def _apply_intake(
    application: AdmissionApplication,
    payload: AdmissionApplicationCreate
    | AdmissionApplicationUpdate
    | AdmissionApplicationCorrect,
) -> None:
    application.child_first_name = payload.child.first_name
    application.child_last_name = payload.child.last_name
    application.child_normalized_name = _normalized_name(
        payload.child.first_name, payload.child.last_name
    )
    application.child_date_of_birth = payload.child.date_of_birth
    contact = payload.primary_contact
    application.contact_first_name = contact.first_name
    application.contact_last_name = contact.last_name
    application.contact_relationship = contact.relationship
    application.contact_email = str(contact.email) if contact.email is not None else None
    application.contact_normalized_email = (
        str(contact.email).casefold() if contact.email is not None else None
    )
    application.contact_telephone = contact.telephone
    application.contact_normalized_telephone = (
        _normalized_telephone(contact.telephone)
        if contact.telephone is not None
        else None
    )
    application.internal_note = payload.internal_note


def _list_items(
    session: SessionDependency,
    applications: list[AdmissionApplication],
) -> list[AdmissionListItem]:
    if not applications:
        return []
    organization_id = applications[0].organization_id
    application_ids = [application.id for application in applications]

    ranked_preferences = (
        select(
            AdmissionApplicationPreference.application_id,
            AdmissionApplicationPreference.facility_id,
            AdmissionApplicationPreference.program_id,
            func.count()
            .over(partition_by=AdmissionApplicationPreference.application_id)
            .label("preference_count"),
            func.row_number()
            .over(
                partition_by=AdmissionApplicationPreference.application_id,
                order_by=(
                    AdmissionApplicationPreference.rank,
                    AdmissionApplicationPreference.id,
                ),
            )
            .label("preference_row"),
        )
        .where(
            AdmissionApplicationPreference.organization_id == organization_id,
            AdmissionApplicationPreference.application_id.in_(application_ids),
            AdmissionApplicationPreference.retired_at.is_(None),
        )
        .subquery()
    )
    preferences = {
        application_id: (
            facility_id,
            program_id,
            int(preference_count),
        )
        for application_id, facility_id, program_id, preference_count in session.execute(
            select(
                ranked_preferences.c.application_id,
                ranked_preferences.c.facility_id,
                ranked_preferences.c.program_id,
                ranked_preferences.c.preference_count,
            ).where(ranked_preferences.c.preference_row == 1)
        ).tuples()
    }
    waitlists = {
        application_id: (facility_id, program_id)
        for application_id, facility_id, program_id in session.execute(
            select(
                AdmissionWaitlistEntry.current_application_id,
                AdmissionWaitlistEntry.facility_id,
                AdmissionWaitlistEntry.program_id,
            ).where(
                AdmissionWaitlistEntry.organization_id == organization_id,
                AdmissionWaitlistEntry.current_application_id.in_(application_ids),
            )
        ).tuples()
        if application_id is not None
    }
    ranked_offers = (
        select(
            AdmissionOffer.application_id,
            AdmissionOffer.facility_id,
            AdmissionOffer.program_id,
            AdmissionOffer.status,
            func.row_number()
            .over(
                partition_by=AdmissionOffer.application_id,
                order_by=(AdmissionOffer.issued_at.desc(), AdmissionOffer.id.desc()),
            )
            .label("offer_row"),
        )
        .where(
            AdmissionOffer.organization_id == organization_id,
            AdmissionOffer.application_id.in_(application_ids),
        )
        .subquery()
    )
    offers = {
        application_id: (facility_id, program_id, offer_status)
        for application_id, facility_id, program_id, offer_status in session.execute(
            select(
                ranked_offers.c.application_id,
                ranked_offers.c.facility_id,
                ranked_offers.c.program_id,
                ranked_offers.c.status,
            ).where(ranked_offers.c.offer_row == 1)
        ).tuples()
    }

    items: list[AdmissionListItem] = []
    for application in applications:
        preference = preferences.get(application.id)
        waitlist = waitlists.get(application.id)
        offer = offers.get(application.id)
        current_offer = offer if offer is not None and offer[2] == "open" else None
        lane = current_offer or waitlist or preference
        items.append(
            AdmissionListItem(
                id=application.id,
                reference=application.reference,
                status=application.status,
                version=application.version,
                source=application.source,
                preference_count=preference[2] if preference is not None else 0,
                submitted_at=application.submitted_at,
                updated_at=application.updated_at,
                current_lane=(
                    AdmissionCurrentLane(
                        facility_id=lane[0],
                        program_id=lane[1],
                    )
                    if lane is not None
                    else None
                ),
                offer_status=offer[2] if offer is not None else None,
            )
        )
    return items


@router.get("/workspace", response_model=AdmissionWorkspaceResponse)
def admissions_workspace(
    request: Request,
    context: AdmissionsReadContext,
    session: SessionDependency,
) -> AdmissionWorkspaceResponse:
    _require_capability(request)
    counts = Counter(
        {
            str(state): int(count)
            for state, count in session.execute(
                select(AdmissionApplication.status, func.count())
                .where(
                    AdmissionApplication.organization_id == context.organization.id
                )
                .group_by(AdmissionApplication.status)
            )
        }
    )
    status_order = (
        "draft",
        "submitted",
        "under_review",
        "waitlisted",
        "offered",
        "accepted",
        "declined",
        "withdrawn",
    )
    applications_by_status = {
        lane_status: list(
            session.scalars(
                select(AdmissionApplication)
                .where(
                    AdmissionApplication.organization_id == context.organization.id,
                    AdmissionApplication.status == lane_status,
                )
                .order_by(
                    AdmissionApplication.updated_at.desc(),
                    AdmissionApplication.id,
                )
                .limit(25)
            )
        )
        for lane_status in status_order
    }
    displayed_applications = [
        application
        for lane_status in status_order
        for application in applications_by_status[lane_status]
    ]
    displayed_items = {
        item.id: item for item in _list_items(session, displayed_applications)
    }
    waitlist_lanes = int(
        session.scalar(
            select(func.count()).select_from(
                select(
                    AdmissionWaitlistEntry.facility_id,
                    AdmissionWaitlistEntry.program_id,
                )
                .where(
                    AdmissionWaitlistEntry.organization_id
                    == context.organization.id,
                    AdmissionWaitlistEntry.status.in_(("active", "offered")),
                )
                .distinct()
                .subquery()
            )
        )
        or 0
    )
    return AdmissionWorkspaceResponse(
        counts=AdmissionPipelineCounts(
            **{state: counts[state] for state in status_order}
        ),
        lanes=[
            AdmissionWorkspaceLane(
                status=lane_status,
                count=counts[lane_status],
                applications=[
                    displayed_items[application.id]
                    for application in applications_by_status[lane_status]
                ],
            )
            for lane_status in status_order
        ],
        waitlist_lane_count=waitlist_lanes,
    )


@router.get("/lane-directory", response_model=AdmissionLaneDirectory)
def admission_lane_directory(
    request: Request,
    context: AdmissionsReadContext,
    session: SessionDependency,
) -> AdmissionLaneDirectory:
    """Return only active admissions lanes; never expose rooms or child rosters."""

    _require_capability(request)
    rows = session.execute(
        select(Facility, Program)
        .join(
            Program,
            and_(
                Program.organization_id == Facility.organization_id,
                Program.facility_id == Facility.id,
            ),
        )
        .where(
            Facility.organization_id == context.organization.id,
            Facility.status == "active",
            Program.is_active.is_(True),
        )
        .order_by(
            func.lower(Facility.name),
            Facility.id,
            func.lower(Program.name),
            Program.id,
        )
    )
    facilities: dict[UUID, AdmissionLaneFacility] = {}
    for facility, program in rows:
        projection = facilities.get(facility.id)
        if projection is None:
            projection = AdmissionLaneFacility(
                id=facility.id,
                name=facility.name,
                programs=[],
            )
            facilities[facility.id] = projection
        projection.programs.append(
            AdmissionLaneProgram(
                id=program.id,
                name=program.name,
                program_type=program.program_type,
            )
        )
    return AdmissionLaneDirectory(facilities=list(facilities.values()))


@router.get("/applications", response_model=AdmissionDirectoryResponse)
def admission_directory(
    request: Request,
    context: AdmissionsReadContext,
    session: SessionDependency,
    application_status: Annotated[
        AdmissionApplicationStatus | None, Query(alias="status")
    ] = None,
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=16,
            pattern=r"^[A-Za-z0-9-]+$",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdmissionDirectoryResponse:
    _require_capability(request)
    filters = [AdmissionApplication.organization_id == context.organization.id]
    if application_status is not None:
        filters.append(AdmissionApplication.status == application_status)
    if search is not None:
        filters.append(
            func.upper(AdmissionApplication.reference).like(
                f"%{search.strip().upper()}%"
            )
        )
    total = int(
        session.scalar(
            select(func.count()).select_from(AdmissionApplication).where(*filters)
        )
        or 0
    )
    applications = list(
        session.scalars(
            select(AdmissionApplication)
            .where(*filters)
            .order_by(AdmissionApplication.updated_at.desc(), AdmissionApplication.id)
            .limit(limit)
            .offset(offset)
        )
    )
    items = _list_items(session, applications)
    return AdmissionDirectoryResponse(
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/applications/{application_id}", response_model=AdmissionDetail)
def admission_detail(
    application_id: UUID,
    request: Request,
    response: Response,
    context: AdmissionsReadContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    response.headers["Cache-Control"] = "private, no-store"
    return _detail(
        session, _application(session, context.organization.id, application_id)
    )


@router.get("/waitlist", response_model=AdmissionWaitlistResponse)
def admission_waitlist(
    request: Request,
    context: AdmissionsReadContext,
    session: SessionDependency,
    facility_id: UUID | None = None,
    program_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdmissionWaitlistResponse:
    _require_capability(request)
    filters = [
        AdmissionWaitlistEntry.organization_id == context.organization.id,
        AdmissionWaitlistEntry.status.in_(("active", "offered")),
    ]
    if facility_id is not None:
        filters.append(AdmissionWaitlistEntry.facility_id == facility_id)
    if program_id is not None:
        filters.append(AdmissionWaitlistEntry.program_id == program_id)
    total = int(
        session.scalar(
            select(func.count()).select_from(AdmissionWaitlistEntry).where(*filters)
        )
        or 0
    )
    rows = list(
        session.scalars(
            select(AdmissionWaitlistEntry)
            .where(*filters)
            .order_by(
                AdmissionWaitlistEntry.facility_id,
                AdmissionWaitlistEntry.program_id,
                AdmissionWaitlistEntry.priority_at,
                AdmissionWaitlistEntry.id,
            )
            .limit(limit)
            .offset(offset)
        )
    )
    application_ids = [row.application_id for row in rows]
    applications = {
        item.id: item
        for item in session.scalars(
            select(AdmissionApplication).where(
                AdmissionApplication.organization_id == context.organization.id,
                AdmissionApplication.id.in_(application_ids),
            )
        )
    } if application_ids else {}
    positions = _waitlist_positions(
        session,
        context.organization.id,
        [row.id for row in rows],
    )
    return AdmissionWaitlistResponse(
        items=[
            AdmissionWaitlistItem(
                entry_id=row.id,
                application_id=row.application_id,
                application_reference=applications[row.application_id].reference,
                status=row.status,
                version=row.version,
                facility_id=row.facility_id,
                program_id=row.program_id,
                desired_start_date=row.requested_start_date,
                priority_at=row.priority_at,
                position=positions[row.id],
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/applications",
    response_model=AdmissionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_admission_application(
    payload: AdmissionApplicationCreate,
    request: Request,
    response: Response,
    context: AdmissionsManageContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type="admission.application.create",
        target_type="admission_application",
        target_scope="create",
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if replay_application_id is not None:
        response.status_code = status.HTTP_200_OK
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    _validate_child_date_of_birth(context, payload)
    occurred_at = datetime.now(UTC)
    application_id = uuid4()
    contact = payload.primary_contact
    application = AdmissionApplication(
        id=application_id,
        organization_id=context.organization.id,
        reference=_reference(application_id),
        source="administrator_entry",
        status="draft",
        version=1,
        child_first_name=payload.child.first_name,
        child_last_name=payload.child.last_name,
        child_normalized_name=_normalized_name(
            payload.child.first_name, payload.child.last_name
        ),
        child_date_of_birth=payload.child.date_of_birth,
        contact_first_name=contact.first_name,
        contact_last_name=contact.last_name,
        contact_relationship=contact.relationship,
        contact_email=str(contact.email) if contact.email is not None else None,
        contact_normalized_email=(
            str(contact.email).casefold() if contact.email is not None else None
        ),
        contact_telephone=contact.telephone,
        contact_normalized_telephone=(
            _normalized_telephone(contact.telephone)
            if contact.telephone is not None
            else None
        ),
        internal_note=payload.internal_note,
        created_by_user_id=context.user.id,
        updated_by_user_id=context.user.id,
        created_operation_id=payload.client_operation_id,
        last_operation_id=payload.client_operation_id,
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    session.add(application)
    flush_or_conflict(session, "Admission reference already exists")
    _replace_preferences(
        session,
        application,
        payload.preferences,
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _event(
        session,
        application,
        command="admission.application.create",
        from_status=None,
        reason_code="create",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type="admission.application.created",
        entity_type="admission_application",
        entity_id=application.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type="admission.application.create",
        target_type="admission_application",
        target_id=application.id,
        committed_version=application.version,
    )
    commit_in_context(session, context, "Admission application conflicts")
    response.headers["Cache-Control"] = "private, no-store"
    return _detail(session, application)


@router.post(
    "/applications/{application_id}/update", response_model=AdmissionDetail
)
def update_admission_application(
    application_id: UUID,
    payload: AdmissionApplicationUpdate,
    request: Request,
    response: Response,
    context: AdmissionsManageContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type="admission.application.update",
        target_type="admission_application",
        target_scope=application_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    _validate_child_date_of_birth(context, payload)
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    _require_application_version(application, payload.expected_application_version)
    _require_state(application, {"draft"}, "admission.application.update")
    occurred_at = datetime.now(UTC)
    from_status = application.status
    application.version += 1
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    _apply_intake(application, payload)
    _replace_preferences(
        session,
        application,
        payload.preferences,
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _event(
        session,
        application,
        command="admission.application.update",
        from_status=from_status,
        reason_code="updated",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type="admission.application.updated",
        entity_type="admission_application",
        entity_id=application.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type="admission.application.update",
        target_type="admission_application",
        target_id=application.id,
        committed_version=application.version,
    )
    commit_in_context(session, context, "Admission application update conflicts")
    response.headers["Cache-Control"] = "private, no-store"
    return _detail(session, application)


def _simple_application_transition(
    *,
    application_id: UUID,
    payload: AdmissionApplicationVersionCommand,
    request: Request,
    context: BasicContext,
    session: SessionDependency,
    command_type: str,
    allowed_states: set[str],
    next_status: str,
    reason_code: str,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="admission_application",
        target_scope=application_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    _require_application_version(application, payload.expected_application_version)
    _require_state(application, allowed_states, command_type)
    occurred_at = datetime.now(UTC)
    from_status = application.status
    waitlist = _current_waitlist(session, application, lock=True)
    offer = _current_offer(session, application, lock=True)
    if next_status == "declined" and waitlist is not None:
        _close_waitlist(
            waitlist,
            reason="application_declined",
            actor_user_id=context.user.id,
            operation_id=payload.client_operation_id,
            occurred_at=occurred_at,
        )
    if next_status == "withdrawn":
        if waitlist is not None:
            _close_waitlist(
                waitlist,
                reason="application_withdrawn",
                actor_user_id=context.user.id,
                operation_id=payload.client_operation_id,
                occurred_at=occurred_at,
            )
        if offer is not None:
            offer.status = "withdrawn"
            offer.open_application_id = None
            offer.version += 1
            offer.withdrawn_at = occurred_at
            offer.updated_at = occurred_at
            offer.updated_by_user_id = context.user.id
            offer.last_operation_id = payload.client_operation_id
    application.status = next_status
    application.version += 1
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    if next_status == "submitted":
        application.submitted_at = occurred_at
    if next_status == "under_review":
        application.review_started_at = occurred_at
    if next_status in _TERMINAL:
        application.terminal_at = occurred_at
    _event(
        session,
        application,
        command=command_type,
        from_status=from_status,
        reason_code=reason_code,
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type=command_type,
        entity_type="admission_application",
        entity_id=application.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="admission_application",
        target_id=application.id,
        committed_version=application.version,
        operator_reason_code=payload.reason_code,
    )
    if next_status == "submitted":
        notify_organization_members(
            session,
            organization_id=application.organization_id,
            permission_keys={"admissions:decide"},
            event_key=f"admission-submitted:{application.id}:{application.version}",
            category="operations",
            severity="info",
            title="Admission application submitted",
            body="An admission application is ready for review.",
            action_path=f"/admissions/applications/{application.id}",
            action_entity_type="admission_application",
            action_entity_id=application.id,
        )
    commit_in_context(session, context, "Admission transition conflicts")
    return _detail(session, application)


@router.post(
    "/applications/{application_id}/submit", response_model=AdmissionDetail
)
def submit_admission_application(
    application_id: UUID,
    payload: AdmissionApplicationVersionCommand,
    request: Request,
    context: AdmissionsManageContext,
    session: SessionDependency,
) -> AdmissionDetail:
    return _simple_application_transition(
        application_id=application_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        command_type="admission.application.submit",
        allowed_states={"draft"},
        next_status="submitted",
        reason_code="submitted",
    )


@router.post(
    "/applications/{application_id}/review/start", response_model=AdmissionDetail
)
def start_admission_review(
    application_id: UUID,
    payload: AdmissionApplicationVersionCommand,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    return _simple_application_transition(
        application_id=application_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        command_type="admission.application.review.start",
        allowed_states={"submitted"},
        next_status="under_review",
        reason_code="review_started",
    )


@router.post(
    "/applications/{application_id}/decline", response_model=AdmissionDetail
)
def decline_admission_application(
    application_id: UUID,
    payload: AdmissionApplicationVersionCommand,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    return _simple_application_transition(
        application_id=application_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        command_type="admission.application.decline",
        allowed_states={"under_review", "waitlisted"},
        next_status="declined",
        reason_code="provider_declined",
    )


@router.post(
    "/applications/{application_id}/withdraw", response_model=AdmissionDetail
)
def withdraw_admission_application(
    application_id: UUID,
    payload: AdmissionApplicationVersionCommand,
    request: Request,
    context: AdmissionsManageContext,
    session: SessionDependency,
) -> AdmissionDetail:
    return _simple_application_transition(
        application_id=application_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        command_type="admission.application.withdraw",
        allowed_states={"submitted", "under_review", "waitlisted", "offered"},
        next_status="withdrawn",
        reason_code="family_withdrawn",
    )


@router.post(
    "/applications/{application_id}/correct", response_model=AdmissionDetail
)
def correct_admission_application(
    application_id: UUID,
    payload: AdmissionApplicationCorrect,
    request: Request,
    response: Response,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type="admission.application.correct",
        target_type="admission_application",
        target_scope=application_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    _validate_child_date_of_birth(context, payload)
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    _require_application_version(application, payload.expected_application_version)
    _require_state(application, _CORRECTABLE, "admission.application.correct")
    if _current_offer(session, application, lock=True) is not None:
        raise _conflict(
            "admission_offer_withdrawal_required",
            "Withdraw the open offer before correcting material intake facts.",
        )
    occurred_at = datetime.now(UTC)
    from_status = application.status
    waitlist = _current_waitlist(session, application, lock=True)
    if waitlist is not None:
        _close_waitlist(
            waitlist,
            reason="facts_changed",
            actor_user_id=context.user.id,
            operation_id=payload.client_operation_id,
            occurred_at=occurred_at,
        )
    application.status = "under_review"
    application.version += 1
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    application.review_started_at = application.review_started_at or occurred_at
    _apply_intake(application, payload)
    _replace_preferences(
        session,
        application,
        payload.preferences,
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _event(
        session,
        application,
        command="admission.application.correct",
        from_status=from_status,
        reason_code="facts_changed",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type="admission.application.corrected",
        entity_type="admission_application",
        entity_id=application.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type="admission.application.correct",
        target_type="admission_application",
        target_id=application.id,
        committed_version=application.version,
    )
    commit_in_context(session, context, "Admission correction conflicts")
    response.headers["Cache-Control"] = "private, no-store"
    return _detail(session, application)


@router.post(
    "/applications/{application_id}/waitlist", response_model=AdmissionDetail
)
def enter_admission_waitlist(
    application_id: UUID,
    payload: AdmissionWaitlistEnter,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type="admission.waitlist.enter",
        target_type="admission_waitlist",
        target_scope=application_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    _require_application_version(application, payload.expected_application_version)
    _require_state(application, {"under_review"}, "admission.waitlist.enter")
    _active_lane(
        session,
        context.organization.id,
        payload.facility_id,
        payload.program_id,
    )
    if _current_waitlist(session, application, lock=True) is not None:
        raise _conflict(
            "admission_waitlist_already_current",
            "The application already has a current waitlist entry.",
        )
    occurred_at = datetime.now(UTC)
    from_status = application.status
    waitlist = AdmissionWaitlistEntry(
        id=uuid4(),
        organization_id=application.organization_id,
        application_id=application.id,
        current_application_id=application.id,
        facility_id=payload.facility_id,
        program_id=payload.program_id,
        requested_start_date=payload.desired_start_date,
        status="active",
        version=1,
        priority_at=occurred_at,
        created_by_user_id=context.user.id,
        updated_by_user_id=context.user.id,
        last_operation_id=payload.client_operation_id,
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    session.add(waitlist)
    application.status = "waitlisted"
    application.version += 1
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    _event(
        session,
        application,
        command="admission.waitlist.enter",
        from_status=from_status,
        reason_code="waitlisted",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type="admission.waitlist.entered",
        entity_type="admission_waitlist",
        entity_id=waitlist.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type="admission.waitlist.enter",
        target_type="admission_waitlist",
        target_id=waitlist.id,
        committed_version=waitlist.version,
        operator_reason_code=payload.reason_code,
    )
    commit_in_context(session, context, "Waitlist entry conflicts")
    return _detail(session, application)


@router.post(
    "/applications/{application_id}/waitlist/reopen-review",
    response_model=AdmissionDetail,
)
def reopen_admission_review(
    application_id: UUID,
    payload: AdmissionWaitlistVersionCommand,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type="admission.waitlist.reopen_review",
        target_type="admission_waitlist",
        target_scope=application_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    _require_application_version(application, payload.expected_application_version)
    _require_state(
        application, {"waitlisted"}, "admission.waitlist.reopen_review"
    )
    waitlist = _current_waitlist(session, application, lock=True)
    if waitlist is None or waitlist.status != "active":
        raise _conflict(
            "admission_waitlist_not_current",
            "A current active waitlist entry is required.",
        )
    _require_waitlist_version(waitlist, payload.expected_waitlist_version)
    occurred_at = datetime.now(UTC)
    _close_waitlist(
        waitlist,
        reason="review_reopened",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    application.status = "under_review"
    application.version += 1
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    _event(
        session,
        application,
        command="admission.waitlist.reopen_review",
        from_status="waitlisted",
        reason_code="review_reopened",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type="admission.waitlist.closed",
        entity_type="admission_waitlist",
        entity_id=waitlist.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type="admission.waitlist.reopen_review",
        target_type="admission_waitlist",
        target_id=waitlist.id,
        committed_version=waitlist.version,
        operator_reason_code=payload.reason_code,
    )
    commit_in_context(session, context, "Waitlist reopen conflicts")
    return _detail(session, application)


@router.post(
    "/applications/{application_id}/offers", response_model=AdmissionDetail
)
def issue_admission_offer(
    application_id: UUID,
    payload: AdmissionOfferIssue,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type="admission.offer.issue",
        target_type="admission_offer",
        target_scope=application_id,
        intent=payload.model_dump(exclude={"client_operation_id"}),
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    _require_application_version(application, payload.expected_application_version)
    _require_state(
        application, {"under_review", "waitlisted"}, "admission.offer.issue"
    )
    _active_lane(
        session,
        context.organization.id,
        payload.facility_id,
        payload.program_id,
    )
    if _current_offer(session, application, lock=True) is not None:
        raise _conflict(
            "admission_offer_already_open",
            "The application already has an open offer.",
        )
    waitlist = _current_waitlist(session, application, lock=True)
    if application.status == "under_review" and (
        payload.expected_waitlist_version is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "admission_waitlist_version_not_applicable",
                "message": "A review-lane offer has no waitlist version.",
            },
        )
    if application.status == "waitlisted" and (
        waitlist is None
        or waitlist.status != "active"
        or waitlist.facility_id != payload.facility_id
        or waitlist.program_id != payload.program_id
    ):
        raise _conflict(
            "admission_offer_waitlist_lane_mismatch",
            "A waitlisted application must be offered its current lane.",
        )
    if application.status == "waitlisted":
        if payload.expected_waitlist_version is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "admission_waitlist_version_required",
                    "message": "The current waitlist version is required.",
                },
            )
        assert waitlist is not None
        _require_waitlist_version(waitlist, payload.expected_waitlist_version)
    occurred_at = datetime.now(UTC)
    prior_status = application.status
    if waitlist is not None:
        waitlist.status = "offered"
        waitlist.version += 1
        waitlist.updated_at = occurred_at
        waitlist.updated_by_user_id = context.user.id
        waitlist.last_operation_id = payload.client_operation_id
    offer = AdmissionOffer(
        id=uuid4(),
        organization_id=application.organization_id,
        application_id=application.id,
        open_application_id=application.id,
        facility_id=payload.facility_id,
        program_id=payload.program_id,
        proposed_start_date=payload.proposed_start_date,
        respond_by_date=payload.respond_by_date,
        prior_application_status=prior_status,
        status="open",
        version=1,
        issued_by_user_id=context.user.id,
        updated_by_user_id=context.user.id,
        last_operation_id=payload.client_operation_id,
        issued_at=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    session.add(offer)
    application.status = "offered"
    application.version += 1
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    _event(
        session,
        application,
        command="admission.offer.issue",
        from_status=prior_status,
        reason_code="offer_issued",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type="admission.offer.issued",
        entity_type="admission_offer",
        entity_id=offer.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type="admission.offer.issue",
        target_type="admission_offer",
        target_id=offer.id,
        committed_version=offer.version,
        operator_reason_code=payload.reason_code,
    )
    commit_in_context(session, context, "Admission offer conflicts")
    return _detail(session, application)


def _close_offer(
    *,
    application_id: UUID,
    offer_id: UUID,
    payload: AdmissionOfferVersionCommand,
    request: Request,
    context: BasicContext,
    session: SessionDependency,
    decline: bool,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    command_type = (
        "admission.offer.decline" if decline else "admission.offer.withdraw"
    )
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="admission_offer",
        target_scope=offer_id,
        intent={
            **payload.model_dump(exclude={"client_operation_id"}),
            "application_id": application_id,
        },
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session, context.organization.id, replay_application_id
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    _require_application_version(application, payload.expected_application_version)
    _require_state(application, {"offered"}, command_type)
    offer = session.scalar(
        select(AdmissionOffer)
        .where(
            AdmissionOffer.organization_id == context.organization.id,
            AdmissionOffer.id == offer_id,
            AdmissionOffer.application_id == application.id,
        )
        .with_for_update()
    )
    if offer is None or offer.status != "open":
        raise _conflict(
            "admission_offer_not_open", "The selected admission offer is not open."
        )
    _require_offer_version(offer, payload.expected_offer_version)
    occurred_at = datetime.now(UTC)
    waitlist = _current_waitlist(session, application, lock=True)
    offer.status = "declined" if decline else "withdrawn"
    offer.open_application_id = None
    offer.version += 1
    offer.updated_at = occurred_at
    offer.updated_by_user_id = context.user.id
    offer.last_operation_id = payload.client_operation_id
    if decline:
        offer.declined_at = occurred_at
        application.status = "declined"
        application.terminal_at = occurred_at
        if waitlist is not None:
            _close_waitlist(
                waitlist,
                reason="offer_declined",
                actor_user_id=context.user.id,
                operation_id=payload.client_operation_id,
                occurred_at=occurred_at,
            )
    else:
        offer.withdrawn_at = occurred_at
        application.status = offer.prior_application_status
        if offer.prior_application_status == "waitlisted":
            if waitlist is None or waitlist.status != "offered":
                raise _conflict(
                    "admission_waitlist_offer_incoherent",
                    "The preserved waitlist priority cannot be restored.",
                )
            waitlist.status = "active"
            waitlist.version += 1
            waitlist.updated_at = occurred_at
            waitlist.updated_by_user_id = context.user.id
            waitlist.last_operation_id = payload.client_operation_id
    application.version += 1
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    _event(
        session,
        application,
        command=command_type,
        from_status="offered",
        reason_code="offer_declined" if decline else "offer_withdrawn",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type=command_type,
        entity_type="admission_offer",
        entity_id=offer.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="admission_offer",
        target_id=offer.id,
        committed_version=offer.version,
        operator_reason_code=payload.reason_code,
    )
    commit_in_context(session, context, "Admission offer close conflicts")
    return _detail(session, application)


@router.post(
    "/applications/{application_id}/offers/{offer_id}/withdraw",
    response_model=AdmissionDetail,
)
def withdraw_admission_offer(
    application_id: UUID,
    offer_id: UUID,
    payload: AdmissionOfferVersionCommand,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    return _close_offer(
        application_id=application_id,
        offer_id=offer_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        decline=False,
    )


@router.post(
    "/applications/{application_id}/offers/{offer_id}/decline",
    response_model=AdmissionDetail,
)
def decline_admission_offer(
    application_id: UUID,
    offer_id: UUID,
    payload: AdmissionOfferVersionCommand,
    request: Request,
    context: AdmissionsManageContext,
    session: SessionDependency,
) -> AdmissionDetail:
    return _close_offer(
        application_id=application_id,
        offer_id=offer_id,
        payload=payload,
        request=request,
        context=context,
        session=session,
        decline=True,
    )


@router.get(
    "/applications/{application_id}/conversion-candidates",
    response_model=AdmissionConversionCandidateReview,
)
def admission_conversion_candidates(
    application_id: UUID,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionConversionCandidateReview:
    _require_capability(request)
    application = _application(session, context.organization.id, application_id)
    existing_conversion = _conversion(session, application)
    if existing_conversion is not None:
        raise _conflict(
            "admission_already_converted",
            "This application has already been converted.",
            conversion_id=str(existing_conversion.id),
        )
    _require_state(
        application,
        {"offered"},
        "admission.offer.accept_and_convert",
    )
    offer = _current_offer(session, application)
    if offer is None or offer.status != "open":
        raise _conflict(
            "admission_offer_not_open",
            "An open admission offer is required for conversion review.",
        )
    families, children, snapshot = _conversion_candidate_state(
        session,
        application,
    )
    review_token, expires_at = _conversion_review_token(
        request,
        application,
        offer,
        snapshot,
    )
    return AdmissionConversionCandidateReview(
        application_id=application.id,
        application_version=application.version,
        offer_id=offer.id,
        offer_version=offer.version,
        families=families,
        children=children,
        review_token=review_token,
        expires_at=expires_at,
    )


@router.post(
    "/applications/{application_id}/offers/{offer_id}/accept-and-convert",
    response_model=AdmissionDetail,
)
def accept_admission_offer(
    application_id: UUID,
    offer_id: UUID,
    payload: AdmissionOfferAccept,
    request: Request,
    context: AdmissionsDecideContext,
    session: SessionDependency,
) -> AdmissionDetail:
    _require_capability(request)
    ensure_writable(request)
    command_type = "admission.offer.accept_and_convert"
    request_hash, replay_application_id = _begin(
        session,
        context,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="admission_offer",
        target_scope=offer_id,
        intent={
            **payload.model_dump(exclude={"client_operation_id"}),
            "application_id": application_id,
        },
    )
    if replay_application_id is not None:
        return _detail(
            session,
            _application(
                session,
                context.organization.id,
                replay_application_id,
            ),
            replayed=True,
            replay_operation_id=payload.client_operation_id,
        )
    application = _application(
        session, context.organization.id, application_id, lock=True
    )
    existing_conversion = _conversion(session, application)
    if existing_conversion is not None:
        raise _conflict(
            "admission_already_converted",
            "This application has already been converted.",
            conversion_id=str(existing_conversion.id),
            family_id=str(existing_conversion.family_id),
            child_id=str(existing_conversion.child_id),
            enrollment_id=str(existing_conversion.enrollment_id),
        )
    _require_application_version(application, payload.expected_application_version)
    _require_state(application, {"offered"}, command_type)
    offer = session.scalar(
        select(AdmissionOffer)
        .where(
            AdmissionOffer.organization_id == context.organization.id,
            AdmissionOffer.id == offer_id,
            AdmissionOffer.application_id == application.id,
        )
        .with_for_update()
    )
    if offer is None or offer.status != "open":
        raise _conflict(
            "admission_offer_not_open",
            "The selected admission offer is not open.",
        )
    _require_offer_version(offer, payload.expected_offer_version)
    waitlist = _current_waitlist(session, application, lock=True)

    review = _decode_conversion_review_token(request, payload.review_token)
    expected_review_identity = {
        "organization_id": str(application.organization_id),
        "application_id": str(application.id),
        "application_version": application.version,
        "offer_id": str(offer.id),
        "offer_version": offer.version,
    }
    if any(
        review.get(field) != value
        for field, value in expected_review_identity.items()
    ):
        raise _conflict(
            "admission_review_stale",
            "The application or offer changed. Refresh duplicate candidates.",
        )
    discovered_families, discovered_children, _ = _conversion_candidate_state(
        session,
        application,
    )
    locked_resources = _lock_conversion_resources(
        session,
        application,
        offer,
        discovered_families,
        discovered_children,
    )
    family_candidates, child_candidates, current_snapshot = (
        _conversion_candidate_state(session, application)
    )
    if review.get("candidate_snapshot_digest") != _conversion_snapshot_digest(
        current_snapshot
    ):
        raise _conflict(
            "admission_review_stale",
            "Possible duplicate records changed. Refresh candidates before accepting.",
        )
    reviewed_families = {candidate.id: candidate for candidate in family_candidates}
    reviewed_children = {candidate.id: candidate for candidate in child_candidates}
    occurred_at = datetime.now(UTC)
    local_today = _local_today(context.organization.timezone)

    family: Family
    child: Child
    if payload.resolution_mode == "create_family_and_child":
        if (reviewed_families or reviewed_children) and not (
            payload.confirmed_distinct_person and payload.distinct_person_reason
        ):
            raise _conflict(
                "admission_distinct_confirmation_required",
                "Confirm why this applicant is distinct from every reviewed candidate.",
            )
        family_operation_id = uuid5(
            payload.client_operation_id,
            "admission-conversion-family-create",
        )
        family_hash, family_receipt = begin_command(
            session,
            organization_id=application.organization_id,
            actor_user_id=context.user.id,
            client_operation_id=family_operation_id,
            command_type="family.create",
            target_type="family",
            target_scope="create",
            intent={"admission_application_id": application.id},
        )
        if family_receipt is not None:
            raise _conflict(
                "admission_nested_receipt_incoherent",
                "A nested Family command already exists without the acceptance receipt.",
            )
        family = Family(
            id=uuid5(family_operation_id, "family"),
            organization_id=application.organization_id,
            name=f"{application.contact_last_name} Family",
            status="active",
            version=1,
            photo_consent=False,
            field_trip_consent=False,
            emergency_medical_consent=False,
        )
        session.add(family)
        record_command(
            session,
            organization_id=application.organization_id,
            actor_user_id=context.user.id,
            client_operation_id=family_operation_id,
            command_type="family.create",
            target_type="family",
            target_id=family.id,
            request_hash=family_hash,
            committed_version=family.version,
            outcome={"action_route": f"/families/{family.id}"},
        )
        session.add(
            Guardian(
                id=uuid5(family_operation_id, "primary-guardian"),
                organization_id=application.organization_id,
                family_id=family.id,
                first_name=application.contact_first_name,
                last_name=application.contact_last_name,
                relationship=application.contact_relationship,
                email=application.contact_email or "",
                cell_phone=application.contact_telephone or "",
                is_primary=True,
                authorized_pickup=False,
                created_operation_id=family_operation_id,
            )
        )
        audit(
            session,
            organization_id=application.organization_id,
            actor_user_id=context.user.id,
            action="family.created",
            entity_type="family",
            entity_id=family.id,
            details={
                "operation_id": str(family_operation_id),
                "admission_application_id": str(application.id),
            },
        )
        session.add(
            RealtimeEvent(
                id=uuid4(),
                organization_id=application.organization_id,
                event_type="family.created",
                entity_type="family",
                entity_id=family.id,
                occurred_at=occurred_at,
                payload={"version": family.version, "refresh_required": True},
            )
        )
        session.flush()
    else:
        if payload.family_id not in reviewed_families:
            raise _conflict(
                "admission_candidate_not_reviewed",
                "The selected Family is not in the current duplicate review.",
            )
        family = locked_resources.families.get(payload.family_id)
        if family is None:
            raise _conflict(
                "admission_review_stale",
                "The selected Family is no longer available.",
            )
        if family.version != payload.expected_family_version:
            raise _conflict(
                "admission_version_conflict",
                "The selected Family changed. Refresh duplicate candidates.",
                record_kind="family",
                record_id=str(family.id),
                expected_version=payload.expected_family_version,
                current_version=family.version,
            )
        if family.status != "active":
            raise _conflict(
                "admission_family_not_active",
                "Only an active Family can receive an accepted application.",
            )

    if payload.resolution_mode in {
        "create_family_and_child",
        "reuse_family_create_child",
    }:
        child_operation_id = uuid5(
            payload.client_operation_id,
            "admission-conversion-child-create",
        )
        child_hash, child_receipt = begin_command(
            session,
            organization_id=application.organization_id,
            actor_user_id=context.user.id,
            client_operation_id=child_operation_id,
            command_type="child.create",
            target_type="child",
            target_scope="create",
            intent={
                "admission_application_id": application.id,
                "family_id": family.id,
            },
        )
        if child_receipt is not None:
            raise _conflict(
                "admission_nested_receipt_incoherent",
                "A nested Child command already exists without the acceptance receipt.",
            )
        child = Child(
            id=uuid5(child_operation_id, "child"),
            organization_id=application.organization_id,
            family_id=family.id,
            first_name=application.child_first_name,
            last_name=application.child_last_name,
            date_of_birth=application.child_date_of_birth,
            age_group=_age_group(
                application.child_date_of_birth,
                today=local_today,
            ),
            is_active=True,
            version=1,
        )
        session.add(child)
        record_command(
            session,
            organization_id=application.organization_id,
            actor_user_id=context.user.id,
            client_operation_id=child_operation_id,
            command_type="child.create",
            target_type="child",
            target_id=child.id,
            request_hash=child_hash,
            committed_version=child.version,
            outcome={"action_route": f"/children/{child.id}"},
        )
        audit(
            session,
            organization_id=application.organization_id,
            actor_user_id=context.user.id,
            action="child.created",
            entity_type="child",
            entity_id=child.id,
            details={
                "operation_id": str(child_operation_id),
                "admission_application_id": str(application.id),
            },
        )
        session.add(
            RealtimeEvent(
                id=uuid4(),
                organization_id=application.organization_id,
                event_type="child.created",
                entity_type="child",
                entity_id=child.id,
                occurred_at=occurred_at,
                payload={"version": child.version, "refresh_required": True},
            )
        )
        session.flush()
    else:
        if payload.child_id not in reviewed_children:
            raise _conflict(
                "admission_candidate_not_reviewed",
                "The selected Child is not in the current duplicate review.",
            )
        child = locked_resources.children.get(payload.child_id)
        if child is None:
            raise _conflict(
                "admission_review_stale",
                "The selected Child is no longer available.",
            )
        if child.version != payload.expected_child_version:
            raise _conflict(
                "admission_version_conflict",
                "The selected Child changed. Refresh duplicate candidates.",
                record_kind="child",
                record_id=str(child.id),
                expected_version=payload.expected_child_version,
                current_version=child.version,
            )
        if child.family_id != family.id:
            raise _conflict(
                "admission_child_family_mismatch",
                "The selected Child does not belong to the reviewed Family.",
            )
        if not child.is_active:
            raise _conflict(
                "admission_child_not_active",
                "Only an active Child can receive a new Enrollment.",
            )
        if reviewed_children[child.id].has_open_enrollment:
            raise _conflict(
                "open_enrollment_exists",
                "The selected Child already has an open Enrollment.",
                child_id=str(child.id),
            )

    enrollment_operation_id = uuid5(
        payload.client_operation_id,
        "admission-conversion-enrollment-create",
    )
    enrollment_hash, enrollment_receipt = begin_command(
        session,
        organization_id=application.organization_id,
        actor_user_id=context.user.id,
        client_operation_id=enrollment_operation_id,
        command_type="enrollment.create",
        target_type="enrollment",
        target_scope=child.id,
        intent={
            "facility_id": offer.facility_id,
            "start_date": offer.proposed_start_date,
        },
    )
    if enrollment_receipt is not None:
        raise _conflict(
            "admission_nested_receipt_incoherent",
            "A nested Enrollment command already exists without the acceptance receipt.",
        )
    if offer.proposed_start_date < child.date_of_birth:
        raise _conflict(
            "admission_enrollment_date_invalid",
            "The offered start date cannot precede the child's date of birth.",
        )
    existing_enrollment = session.scalar(
        select(Enrollment.id)
        .where(
            Enrollment.organization_id == application.organization_id,
            Enrollment.child_id == child.id,
            Enrollment.status.in_(_OPEN_ENROLLMENT_STATUSES),
        )
    )
    if existing_enrollment is not None:
        raise _conflict(
            "open_enrollment_exists",
            "The selected Child already has an open Enrollment.",
            child_id=str(child.id),
        )
    enrollment = Enrollment(
        id=uuid5(enrollment_operation_id, "enrollment"),
        organization_id=application.organization_id,
        child_id=child.id,
        facility_id=offer.facility_id,
        program_id=None,
        room_id=None,
        placement_effective_date=None,
        start_date=offer.proposed_start_date,
        status="pending",
        version=1,
    )
    session.add(enrollment)
    record_command(
        session,
        organization_id=application.organization_id,
        actor_user_id=context.user.id,
        client_operation_id=enrollment_operation_id,
        command_type="enrollment.create",
        target_type="enrollment",
        target_id=enrollment.id,
        request_hash=enrollment_hash,
        committed_version=enrollment.version,
        facility_id=enrollment.facility_id,
        outcome={
            "action_route": (
                f"/children/{child.id}?enrollment_id={enrollment.id}"
            )
        },
    )
    audit(
        session,
        organization_id=application.organization_id,
        actor_user_id=context.user.id,
        action="enrollment.created",
        entity_type="enrollment",
        entity_id=enrollment.id,
        facility_id=enrollment.facility_id,
        details={
            "operation_id": str(enrollment_operation_id),
            "admission_application_id": str(application.id),
        },
    )
    session.add(
        RealtimeEvent(
            id=uuid4(),
            organization_id=application.organization_id,
            event_type="enrollment.created",
            entity_type="enrollment",
            entity_id=enrollment.id,
            occurred_at=occurred_at,
            payload={"version": enrollment.version, "refresh_required": True},
        )
    )
    session.flush()

    # Nested Family/Child/Enrollment commands each bind the transaction-local
    # operation setting to their own deterministic operation ID.  Restore the
    # parent acceptance operation before writing the admissions head so the
    # deferred 0039 provenance guard can attest one coherent command bundle.
    lock_client_operation(
        session,
        application.organization_id,
        payload.client_operation_id,
    )

    conversion = AdmissionConversionLink(
        id=uuid5(payload.client_operation_id, "admission-conversion"),
        organization_id=application.organization_id,
        application_id=application.id,
        offer_id=offer.id,
        family_id=family.id,
        child_id=child.id,
        enrollment_id=enrollment.id,
        resolution_mode=payload.resolution_mode,
        acceptance_operation_id=payload.client_operation_id,
        review_proof_digest=hashlib.sha256(
            payload.review_token.encode("utf-8")
        ).hexdigest(),
        converted_by_user_id=context.user.id,
        converted_at=occurred_at,
    )
    session.add(conversion)
    flush_or_conflict(session, "Admission conversion conflicts with existing data")

    offer.status = "accepted"
    offer.open_application_id = None
    offer.version += 1
    offer.accepted_at = occurred_at
    offer.updated_at = occurred_at
    offer.updated_by_user_id = context.user.id
    offer.last_operation_id = payload.client_operation_id
    session.flush()

    if waitlist is not None:
        if waitlist.status != "offered":
            raise _conflict(
                "admission_waitlist_offer_incoherent",
                "The offer's waitlist entry is no longer coherent.",
            )
        _close_waitlist(
            waitlist,
            reason="application_accepted",
            actor_user_id=context.user.id,
            operation_id=payload.client_operation_id,
            occurred_at=occurred_at,
        )
    application.status = "accepted"
    application.version += 1
    application.terminal_at = occurred_at
    application.updated_at = occurred_at
    application.updated_by_user_id = context.user.id
    application.last_operation_id = payload.client_operation_id
    _event(
        session,
        application,
        command=command_type,
        from_status="offered",
        reason_code="offer_accepted",
        actor_user_id=context.user.id,
        operation_id=payload.client_operation_id,
        occurred_at=occurred_at,
    )
    _realtime(
        session,
        application,
        event_type="admission.offer.accepted",
        entity_type="admission_offer",
        entity_id=offer.id,
        occurred_at=occurred_at,
    )
    _record(
        session,
        application,
        context,
        request_hash=request_hash,
        client_operation_id=payload.client_operation_id,
        command_type=command_type,
        target_type="admission_offer",
        target_id=offer.id,
        committed_version=offer.version,
        operator_reason_code=payload.reason_code,
    )
    notify_organization_members(
        session,
        organization_id=application.organization_id,
        permission_keys={"admissions:decide"},
        event_key=f"admission-converted:{application.id}:{application.version}",
        category="operations",
        severity="info",
        title="Admission conversion completed",
        body="An accepted application is ready for placement review.",
        action_path=f"/admissions/applications/{application.id}",
        action_entity_type="admission_application",
        action_entity_id=application.id,
        exclude_user_ids={context.user.id},
    )
    commit_in_context(session, context, "Admission conversion conflicts")
    return _detail(session, application)
