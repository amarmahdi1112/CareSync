"""Legacy-compatible password and JWT authentication."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.auth import Role, User


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


def find_user_by_email(session: Session, email: str) -> User | None:
    statement = (
        select(User)
        .where(User.email == email.strip().lower())
        .options(selectinload(User.role).selectinload(Role.permissions))
    )
    return session.scalar(statement)


def find_user_by_id(session: Session, user_id: str) -> User | None:
    statement = (
        select(User)
        .where(User.id == UUID(user_id))
        .options(selectinload(User.role).selectinload(Role.permissions))
    )
    return session.scalar(statement)


def authenticate(session: Session, email: str, password: str) -> User:
    user = find_user_by_email(session, email)
    password_matches = bool(
        user
        and user.password
        and bcrypt.checkpw(password.encode("utf-8"), user.password.encode("utf-8"))
    )
    if not user or not password_matches:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    return user


def create_access_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "userId": str(user.id),
        "email": user.email,
        "role": user.role.name,
        "organizationId": str(user.organization_id) if user.organization_id else None,
        "iat": now,
        "exp": now + _token_lifetime(settings.jwt_expires_in),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
