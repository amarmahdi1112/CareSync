"""Candidate-private personal identity and normalized profile photo endpoints."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.basic.common import commit_or_conflict, ensure_writable
from app.api.basic.dependencies import BasicUser
from app.api.dependencies import SessionDependency
from app.basic.candidate_profiles import missing_profile_fields
from app.basic.models import MarketplaceProfile, MarketplaceProfilePhoto, User
from app.basic.notifications import emit_user_realtime_event
from app.basic.profile_photos import normalize_profile_photo
from app.basic.security import create_access_token, normalize_email, verify_password
from app.basic.verification import apply_temporary_email_approval

router = APIRouter(
    prefix="/marketplace/personal-profile", tags=["candidate marketplace personal profile"]
)


class PersonalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=30)


class EmailChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_email: str = Field(min_length=3, max_length=320)
    current_password: str = Field(min_length=1, max_length=128)


def _photo_row(photo: MarketplaceProfilePhoto | None) -> dict | None:
    if photo is None:
        return None
    return {
        "url": "/api/v1/marketplace/personal-profile/photo",
        "content_type": photo.content_type,
        "size_bytes": photo.size_bytes,
        "width": photo.width,
        "height": photo.height,
        "sha256": photo.sha256,
        "original_filename": photo.original_filename,
        "updated_at": photo.updated_at,
    }


def _self_row(session, user: User, profile: MarketplaceProfile) -> dict:
    photo = session.get(MarketplaceProfilePhoto, user.id)
    missing = missing_profile_fields(user, profile)
    return {
        "user_id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "email_verified_at": user.email_verified_at,
        "email_verification_method": user.email_verification_method,
        "date_of_birth": profile.date_of_birth,
        "phone": profile.phone,
        "profile_photo": _photo_row(photo),
        "profile_complete": not missing,
        "missing_profile_fields": missing,
    }


def _profile(session, user_id):
    value = session.get(MarketplaceProfile, user_id)
    if value is None:
        raise HTTPException(404, "Marketplace profile not found")
    return value


@router.get("")
def get_personal_profile(user: BasicUser, session: SessionDependency):
    return _self_row(session, user, _profile(session, user.id))


@router.patch("")
def update_personal_profile(
    payload: PersonalUpdate,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    if not payload.model_fields_set:
        raise HTTPException(422, "Provide date_of_birth or phone")
    profile = _profile(session, user.id)
    if "date_of_birth" in payload.model_fields_set:
        if payload.date_of_birth is not None:
            today = date.today()
            if payload.date_of_birth > today or payload.date_of_birth.year < today.year - 100:
                raise HTTPException(422, "Date of birth must be a valid past date")
        profile.date_of_birth = payload.date_of_birth
    if "phone" in payload.model_fields_set:
        phone = payload.phone.strip() if payload.phone else None
        if phone and not re.fullmatch(r"\+?[0-9 ()\-.xX]{7,30}", phone):
            raise HTTPException(422, "Phone number format is invalid")
        profile.phone = phone
    emit_user_realtime_event(
        session,
        user_id=user.id,
        event_type="marketplace.profile_updated",
        entity_type="marketplace_profile",
        entity_id=user.id,
        payload={"source": "personal_profile"},
    )
    commit_or_conflict(session)
    return _self_row(session, user, profile)


@router.post("/email")
def change_email(
    payload: EmailChange,
    request: Request,
    user: BasicUser,
    session: SessionDependency,
):
    ensure_writable(request)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    email = normalize_email(payload.new_email)
    owner = session.scalar(select(User.id).where(User.email == email, User.id != user.id))
    if owner is not None:
        raise HTTPException(409, "Email already registered")
    changed = email != user.email
    if changed:
        user.email = email
        user.auth_version += 1
        apply_temporary_email_approval(user, decided_at=datetime.now(UTC))
        emit_user_realtime_event(
            session,
            user_id=user.id,
            event_type="marketplace.email_changed",
            entity_type="user",
            entity_id=user.id,
            payload={"source": "personal_profile"},
        )
        commit_or_conflict(session, "Email already registered")
    return {
        "email": user.email,
        "email_verified_at": user.email_verified_at,
        "email_verification_method": user.email_verification_method,
        "access_token": create_access_token(user, request.app.state.settings),
        "token_type": "bearer",
        "changed": changed,
    }


@router.put("/photo", status_code=201)
def put_photo(
    request: Request,
    user: BasicUser,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
):
    ensure_writable(request)
    _profile(session, user.id)
    normalized = normalize_profile_photo(file, request.app.state.settings)
    photo = session.get(MarketplaceProfilePhoto, user.id)
    created = photo is None
    if photo is None:
        photo = MarketplaceProfilePhoto(user_id=user.id)
        session.add(photo)
    photo.image_bytes = normalized.image_bytes
    photo.content_type = normalized.content_type
    photo.size_bytes = normalized.size_bytes
    photo.width = normalized.width
    photo.height = normalized.height
    photo.sha256 = normalized.sha256
    photo.original_filename = normalized.original_filename
    emit_user_realtime_event(
        session,
        user_id=user.id,
        event_type="marketplace.photo_updated",
        entity_type="marketplace_profile_photo",
        entity_id=user.id,
        payload={"source": "personal_profile"},
    )
    commit_or_conflict(session)
    return {**_photo_row(photo), "created": created}


@router.get("/photo", response_class=Response)
def get_photo(request: Request, user: BasicUser, session: SessionDependency):
    photo = session.get(MarketplaceProfilePhoto, user.id)
    if photo is None:
        raise HTTPException(404, "Candidate photo not found")
    etag = f'"{photo.sha256}"'
    headers = {
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if etag in {value.strip() for value in request.headers.get("if-none-match", "").split(",")}:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=photo.image_bytes, media_type=photo.content_type, headers=headers)


@router.delete("/photo", status_code=204)
def delete_photo(request: Request, user: BasicUser, session: SessionDependency):
    ensure_writable(request)
    photo = session.get(MarketplaceProfilePhoto, user.id)
    if photo is None:
        raise HTTPException(404, "Candidate photo not found")
    session.delete(photo)
    emit_user_realtime_event(
        session,
        user_id=user.id,
        event_type="marketplace.photo_deleted",
        entity_type="marketplace_profile_photo",
        entity_id=user.id,
        payload={"source": "personal_profile"},
    )
    commit_or_conflict(session)
    return Response(status_code=204)
