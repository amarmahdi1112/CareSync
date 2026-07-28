"""Idempotent helpers for the user notification ledger."""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from sqlalchemy import insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.basic.models import (
    MembershipRoomAssignment,
    NotificationDelivery,
    OrganizationMembership,
    PushSubscription,
    Role,
    UserNotification,
    UserNotificationPreference,
    UserRealtimeEvent,
)

# Notification actions are server-authored navigation capabilities, not arbitrary URLs.
# Keep this list aligned with the exact web and staff-app destinations emitted by the
# Basic API.  Each client may translate a known destination into its own equivalent
# screen, but no client should ever be asked to follow an unregistered path.
_EXACT_NOTIFICATION_ACTION_PATHS = frozenset(
    {
        "/attendance",
        "/billing",
        "/dashboard",
        "/incidents",
        "/jobs",
        "/medications",
        "/rooms",
        "/settings",
        "/shifts",
        "/shifts/time-off",
        "/staff",
        "/staff-rota",
        "/staff/schedule",
        "/staff/self/exchange/open-shift-activity",
        "/staff/self/exchange/open-shifts",
        "/staff/self/exchange/swaps",
        "/today",
        "/transport-registry",
    }
)
_RECORD_NOTIFICATION_ACTION_PATH = re.compile(
    r"/(?:children|families)/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_APPLICATION_NOTIFICATION_ACTION_PATH = re.compile(
    r"/jobs/applications/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_ADMISSION_NOTIFICATION_ACTION_PATH = re.compile(
    r"/admissions/applications/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_EXACT_NOTIFICATION_ACTION_ENTITY_TYPES = {
    "/attendance": frozenset({"attendance_day"}),
    "/billing": frozenset(
        {
            "billing_account",
            "billing_rate_plan",
            "billing_agreement",
            "billing_invoice",
            "billing_payment",
            "billing_allocation",
            "billing_credit",
        }
    ),
    "/dashboard": frozenset({"organization"}),
    "/incidents": frozenset({"incident_record"}),
    "/jobs": frozenset({"application", "credential", "interview", "offer"}),
    "/medications": frozenset({"medication_plan"}),
    "/rooms": frozenset(
        {"enrollment", "room", "room_operational_exception"}
    ),
    "/settings": frozenset({"user"}),
    "/shifts": frozenset({"staff_schedule"}),
    "/shifts/time-off": frozenset({"staff_time_off"}),
    "/staff": frozenset({"organization_membership"}),
    "/staff-rota": frozenset(
        {
            "staff_availability",
            "staff_open_shift",
            "staff_open_shift_engagement",
            "staff_rotation_pattern",
            "staff_schedule",
            "staff_shift_swap",
            "staff_substitute_profile",
            "staff_time_off",
        }
    ),
    "/staff/schedule": frozenset({"staff_open_shift", "staff_schedule"}),
    "/staff/self/exchange/open-shift-activity": frozenset(
        {"staff_open_shift", "staff_open_shift_engagement"}
    ),
    "/staff/self/exchange/open-shifts": frozenset({"staff_open_shift"}),
    "/staff/self/exchange/swaps": frozenset({"staff_shift_swap"}),
    "/today": frozenset({"application", "organization_membership"}),
    "/transport-registry": frozenset({"transport_registry"}),
}


def validate_notification_action_path(action_path: str | None) -> None:
    """Reject destinations outside CareSync's closed internal-route contract."""

    if action_path is None:
        return
    if action_path in _EXACT_NOTIFICATION_ACTION_PATHS:
        return
    if _RECORD_NOTIFICATION_ACTION_PATH.fullmatch(action_path):
        return
    if _APPLICATION_NOTIFICATION_ACTION_PATH.fullmatch(action_path):
        return
    if _ADMISSION_NOTIFICATION_ACTION_PATH.fullmatch(action_path):
        return
    raise ValueError("Notification action path must be a supported internal destination")


def validate_notification_action(
    *,
    organization_id: UUID | None,
    action_path: str | None,
    action_entity_type: str | None,
    action_entity_id: UUID | None,
) -> None:
    """Require one complete, tenant-bound and internally routable work-item action."""

    components = (action_path, action_entity_type, action_entity_id)
    if all(value is None for value in components):
        return
    if organization_id is None or any(value is None for value in components):
        raise ValueError("Notification actions must be complete and organization-bound")
    validate_notification_action_path(action_path)

    allowed_types = _EXACT_NOTIFICATION_ACTION_ENTITY_TYPES.get(action_path)
    record_match = _RECORD_NOTIFICATION_ACTION_PATH.fullmatch(action_path)
    application_match = _APPLICATION_NOTIFICATION_ACTION_PATH.fullmatch(action_path)
    admission_match = _ADMISSION_NOTIFICATION_ACTION_PATH.fullmatch(action_path)
    if record_match:
        record_kind, record_id = action_path.strip("/").split("/")
        expected_type = "child" if record_kind == "children" else "family"
        allowed_types = frozenset({expected_type})
        if action_entity_type == expected_type and str(action_entity_id) != record_id.lower():
            raise ValueError("Notification record action must identify its path resource")
    elif application_match:
        allowed_types = frozenset({"application", "interview", "offer"})
        path_application_id = action_path.rsplit("/", 1)[1]
        if (
            action_entity_type == "application"
            and str(action_entity_id) != path_application_id.lower()
        ):
            raise ValueError("Notification application action must identify its path resource")
    elif admission_match:
        allowed_types = frozenset({"admission_application"})
        path_application_id = action_path.rsplit("/", 1)[1]
        if (
            action_entity_type == "admission_application"
            and str(action_entity_id) != path_application_id.lower()
        ):
            raise ValueError(
                "Notification admission action must identify its path resource"
            )
    if allowed_types is None or action_entity_type not in allowed_types:
        raise ValueError("Notification action entity is not valid for its destination")


def emit_user_realtime_event(
    session: Session,
    *,
    user_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID | None,
    organization_id: UUID | None = None,
    payload: dict | None = None,
    event_id: UUID | None = None,
) -> UserRealtimeEvent:
    """Append a PII-free user-private invalidation event."""

    value = UserRealtimeEvent(
        id=event_id or uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    session.add(value)
    return value


def _category_enabled(preference: UserNotificationPreference | None, category: str) -> bool:
    if preference is None:
        return True
    if not preference.push_enabled:
        return False
    field = {
        "hiring": "hiring_enabled",
        "credential": "credential_enabled",
        "assignment": "assignment_enabled",
        "operations": "operations_enabled",
    }.get(category)
    return True if field is None else bool(getattr(preference, field))


def _generic_push_payload(notification: UserNotification) -> dict[str, str]:
    """Return the complete OS payload data contract; ledger prose never leaves the server."""

    return {
        "type": "notification",
        "notification_id": str(notification.id),
        "category": notification.category,
        "severity": notification.severity,
    }


def enqueue_notification_push(session: Session, notification: UserNotification) -> None:
    """Idempotently enqueue active endpoints without exposing their addresses to API callers."""

    session.flush()
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        # PostgreSQL inserts are bridged by the AFTER INSERT trigger. Existing
        # notifications already own their outbox rows, so retrying a business
        # operation requires no cross-recipient SELECT here.
        return

    existing_event = session.scalar(
        select(UserRealtimeEvent.id).where(UserRealtimeEvent.id == notification.id)
    )
    if existing_event is None:
        emit_user_realtime_event(
            session,
            event_id=notification.id,
            user_id=notification.user_id,
            organization_id=notification.organization_id,
            event_type="notification.created",
            entity_type="notification",
            entity_id=notification.id,
            payload={"source": "notification_ledger"},
        )
    preference = session.get(UserNotificationPreference, notification.user_id)
    statement = select(PushSubscription).where(
        PushSubscription.user_id == notification.user_id,
        PushSubscription.status == "active",
    )
    if notification.organization_id is not None:
        statement = statement.where(
            or_(
                PushSubscription.organization_id.is_(None),
                PushSubscription.organization_id == notification.organization_id,
            )
        )
    subscriptions = list(session.scalars(statement))
    for subscription in subscriptions:
        exists = session.scalar(
            select(NotificationDelivery.id).where(
                NotificationDelivery.notification_id == notification.id,
                NotificationDelivery.subscription_id == subscription.id,
            )
        )
        if exists is not None:
            continue
        session.add(
            NotificationDelivery(
                notification_id=notification.id,
                subscription_id=subscription.id,
                user_id=notification.user_id,
                organization_id=notification.organization_id,
                payload=_generic_push_payload(notification),
                status=(
                    "pending"
                    if _category_enabled(preference, notification.category)
                    else "suppressed"
                ),
            )
        )


def notify_user(
    session: Session,
    *,
    user_id: UUID,
    event_key: str,
    category: str,
    severity: str,
    title: str,
    body: str,
    organization_id: UUID | None = None,
    action_path: str | None = None,
    action_entity_type: str | None = None,
    action_entity_id: UUID | None = None,
) -> UserNotification | None:
    validate_notification_action(
        organization_id=organization_id,
        action_path=action_path,
        action_entity_type=action_entity_type,
        action_entity_id=action_entity_id,
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        notification_id = uuid4()
        statement = (
            insert(UserNotification)
            .values(
                id=notification_id,
                user_id=user_id,
                organization_id=organization_id,
                event_key=event_key,
                category=category,
                severity=severity,
                title=title,
                body=body,
                action_path=action_path,
                action_entity_type=action_entity_type,
                action_entity_id=action_entity_id,
            )
            .inline()
        )
        try:
            with session.begin_nested():
                session.execute(statement)
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            if getattr(diagnostic, "constraint_name", None) == (
                "uq_user_notifications_event"
            ):
                return None
            raise
        return UserNotification(
            id=notification_id,
            user_id=user_id,
            organization_id=organization_id,
            event_key=event_key,
            category=category,
            severity=severity,
            title=title,
            body=body,
            action_path=action_path,
            action_entity_type=action_entity_type,
            action_entity_id=action_entity_id,
        )
    existing = session.scalar(
        select(UserNotification).where(
            UserNotification.user_id == user_id,
            UserNotification.event_key == event_key,
        )
    )
    if existing is not None:
        enqueue_notification_push(session, existing)
        return existing
    value = UserNotification(
        id=uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        event_key=event_key,
        category=category,
        severity=severity,
        title=title,
        body=body,
        action_path=action_path,
        action_entity_type=action_entity_type,
        action_entity_id=action_entity_id,
    )
    session.add(value)
    enqueue_notification_push(session, value)
    return value


def notify_organization_hiring_managers(
    session: Session,
    *,
    organization_id: UUID,
    event_key: str,
    title: str,
    body: str,
    action_path: str,
    action_entity_type: str,
    action_entity_id: UUID,
    severity: str = "info",
) -> None:
    notify_organization_members(
        session,
        organization_id=organization_id,
        permission_keys={"ats:read", "ats:manage", "ats:hire"},
        event_key=event_key,
        category="hiring",
        title=title,
        body=body,
        action_path=action_path,
        action_entity_type=action_entity_type,
        action_entity_id=action_entity_id,
        severity=severity,
    )


def notify_organization_members(
    session: Session,
    *,
    organization_id: UUID,
    permission_keys: set[str],
    event_key: str,
    category: str,
    title: str,
    body: str,
    action_path: str,
    action_entity_type: str,
    action_entity_id: UUID,
    severity: str = "info",
    facility_id: UUID | None = None,
    room_id: UUID | None = None,
    organization_wide_only: bool = False,
    exclude_user_ids: set[UUID] | None = None,
) -> None:
    """Notify active members holding any requested fixed permission."""

    rows = session.execute(
        select(OrganizationMembership, Role)
        .join(
            Role,
            (Role.organization_id == OrganizationMembership.organization_id)
            & (Role.id == OrganizationMembership.role_id),
        )
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == "active",
        )
    )
    for membership, role in rows:
        if membership.user_id in (exclude_user_ids or set()):
            continue
        if not permission_keys.intersection(role.permissions or []):
            continue
        if organization_wide_only and role.key not in {"owner", "administrator"}:
            continue
        if (facility_id is not None or room_id is not None) and role.key not in {
            "owner",
            "administrator",
        }:
            assignment_filters = [
                MembershipRoomAssignment.organization_id == organization_id,
                MembershipRoomAssignment.membership_id == membership.id,
                MembershipRoomAssignment.is_active.is_(True),
            ]
            if facility_id is not None:
                assignment_filters.append(MembershipRoomAssignment.facility_id == facility_id)
            if room_id is not None:
                assignment_filters.append(MembershipRoomAssignment.room_id == room_id)
            assignment = session.scalar(
                select(MembershipRoomAssignment.id).where(*assignment_filters)
            )
            if assignment is None:
                continue
        notify_user(
            session,
            user_id=membership.user_id,
            organization_id=organization_id,
            event_key=f"{event_key}:{membership.user_id}",
            category=category,
            severity=severity,
            title=title,
            body=body,
            action_path=action_path,
            action_entity_type=action_entity_type,
            action_entity_id=action_entity_id,
        )
