"""Authentication, tenant-context and immutable audit helpers for Basic."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.basic.models import AuditEvent, OrganizationMembership, Role, User
from app.core.config import Settings

OWNER_PERMISSIONS = [
    "organization:manage",
    "facility:read",
    "facility:manage",
    "childcare:read",
    "childcare:manage",
    "care_roster:read",
    "attendance:read",
    "attendance:record",
    "attendance:correct",
    "release:read",
    "release:checkout",
    "care:read",
    "care:record",
    "care:correct",
    "care:void",
    "child_safety:read",
    "medication:read",
    "medication:manage",
    "medication:record",
    "medication:correct",
    "medication:void",
    "incident:read",
    "incident:create",
    "incident:update",
    "incident:review",
    "incident:external_report",
    "staff:manage",
    "staff:manage_educators",
    "ats:read",
    "ats:manage",
    "ats:hire",
    "admissions:read",
    "admissions:manage",
    "admissions:decide",
    "transport:read",
    "transport:manage",
    "billing:read",
    "billing:manage",
    "billing:issue",
    "billing:payments",
    "billing:adjust",
    "billing:close",
    "billing:recover",
    "shift:clock",
    "audit:read",
    "settings:manage",
]
ADMINISTRATOR_PERMISSIONS = [
    "facility:read",
    "facility:manage",
    "childcare:read",
    "childcare:manage",
    "care_roster:read",
    "attendance:read",
    "attendance:record",
    "attendance:correct",
    "release:read",
    "release:checkout",
    "care:read",
    "care:record",
    "care:correct",
    "care:void",
    "child_safety:read",
    "medication:read",
    "medication:manage",
    "medication:record",
    "medication:correct",
    "medication:void",
    "incident:read",
    "incident:create",
    "incident:update",
    "incident:review",
    "incident:external_report",
    "staff:manage_educators",
    "ats:read",
    "ats:manage",
    "ats:hire",
    "admissions:read",
    "admissions:manage",
    "admissions:decide",
    "transport:read",
    "transport:manage",
    "billing:read",
    "billing:manage",
    "billing:issue",
    "billing:payments",
    "billing:recover",
    "shift:clock",
]
EDUCATOR_PERMISSIONS = [
    "facility:read",
    "care_roster:read",
    "attendance:read",
    "attendance:record",
    "release:read",
    "release:checkout",
    "care:read",
    "care:record",
    "care:correct_own",
    "child_safety:read",
    "medication:read",
    "medication:record",
    "medication:correct_own",
    "incident:read",
    "incident:create",
    "incident:update_own",
    "shift:clock",
]
SYSTEM_ROLE_TEMPLATES = {
    "owner": (
        "Owner",
        "Organization owner with full Basic access",
        OWNER_PERMISSIONS,
    ),
    "administrator": (
        "Administrator",
        "Organization-wide operational access and educator administration",
        ADMINISTRATOR_PERMISSIONS,
    ),
    "educator": (
        "Educator",
        "Assigned-room care roster and attendance recording",
        EDUCATOR_PERMISSIONS,
    ),
}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _token_lifetime(value: str) -> timedelta:
    suffix = value[-1:].lower()
    amount = int(value[:-1] if suffix in {"m", "h", "d"} else value)
    if suffix == "m":
        return timedelta(minutes=amount)
    if suffix == "h":
        return timedelta(hours=amount)
    if suffix == "d":
        return timedelta(days=amount)
    return timedelta(seconds=amount)


def create_access_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "userId": str(user.id),
        "authVersion": user.auth_version,
        "iat": now,
        "exp": now + _token_lifetime(settings.jwt_expires_in),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> tuple[UUID, int]:
    payload = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])
    return (
        UUID(str(payload.get("sub") or payload["userId"])),
        int(payload["authVersion"]),
    )


def create_one_time_token(organization_id: UUID, challenge_id: UUID) -> tuple[str, str]:
    """Return an opaque URL token and its storage-safe digest."""

    token = f"{organization_id}.{challenge_id}.{secrets.token_urlsafe(32)}"
    return token, hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_one_time_token(token: str) -> tuple[UUID, UUID, str]:
    try:
        organization_value, challenge_value, secret = token.split(".", 2)
        if len(secret) < 32:
            raise ValueError
        organization_id = UUID(organization_value)
        challenge_id = UUID(challenge_value)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Invalid one-time token") from None
    return (
        organization_id,
        challenge_id,
        hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )


def token_digest_matches(stored: str, presented: str) -> bool:
    return hmac.compare_digest(stored, presented)


def set_rls_user(session: Session, user_id: UUID) -> None:
    """Set transaction-local identity for PostgreSQL membership policies."""

    # Keep the authenticated principal available to domain idempotency checks
    # on every dialect; PostgreSQL additionally mirrors it into the RLS GUC.
    session.info["rls_user_id"] = user_id
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(user_id)},
        )


def set_rls_organization(session: Session, organization_id: UUID) -> None:
    """Set transaction-local tenant identity for PostgreSQL RLS policies."""

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_organization_id', :value, true)"),
            {"value": str(organization_id)},
        )


def audit(
    session: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    facility_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        facility_id=facility_id,
        details=details or {},
    )
    session.add(event)
    return event


def membership_role(session: Session, membership: OrganizationMembership) -> Role | None:
    return session.scalar(
        select(Role).where(
            Role.id == membership.role_id,
            Role.organization_id == membership.organization_id,
        )
    )
