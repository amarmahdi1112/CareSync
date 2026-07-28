"""REST replacement for legacy authentication and user-administration workflows."""

import secrets
from datetime import date, timedelta
from uuid import uuid4

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.auth import Permission, Role, User
from app.models.organization import Organization
from app.schemas.auth import (
    AuthResponse,
    InviteUserRequest,
    LoginRequest,
    PasswordChangeRequest,
    PermissionResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    RoleResponse,
    UserAccessUpdateRequest,
    UserResponse,
)
from app.services.auth import authenticate, create_access_token, find_user_by_email, find_user_by_id

router = APIRouter(prefix="/auth", tags=["authentication"])


def _ensure_writable(request: Request) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )


def _load_user(session: SessionDependency, user_id: str) -> User:
    user = find_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, session: SessionDependency) -> AuthResponse:
    user = authenticate(session, payload.email, payload.password)
    token = create_access_token(user, request.app.state.settings)
    return AuthResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, session: SessionDependency
) -> AuthResponse:
    _ensure_writable(request)
    _validate_password(payload.password)
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email"
        )
    if find_user_by_email(session, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    role = session.scalar(select(Role).where(Role.name == "Administrator"))
    if role is None:
        role = session.get(Role, 2)
    if role is None:
        role = session.scalar(select(Role).order_by(Role.id))
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No default role configured"
        )
    organization = Organization(
        id=uuid4(),
        name="My Organization",
        organization_type="daycare",
        status="pending",
        primary_contact_name=f"{payload.first_name} {payload.last_name}".strip(),
        email=email,
        phone="",
        street_address="",
        city="",
        province="Alberta",
        postal_code="",
        country="Canada",
        license_number="PENDING",
        licensed_capacity=0,
        opening_time="07:00",
        closing_time="18:00",
        age_groups_served="[]",
        programs_offered="[]",
        subscription_plan="trial",
        trial_ends_at=date.today() + timedelta(days=14),
        email_verified=False,
        license_verified=False,
    )
    user = User(
        id=uuid4(),
        email=email,
        password=_hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        role_id=role.id,
        organization_id=organization.id,
        provider="local",
        is_active=True,
    )
    session.add_all([organization, user])
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    user = _load_user(session, str(user.id))
    token = create_access_token(user, request.app.state.settings)
    return AuthResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: ProfileUpdateRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> UserResponse:
    _ensure_writable(request)
    values = payload.model_dump(exclude_none=True)
    if "email" in values:
        values["email"] = values["email"].strip().lower()
        existing = find_user_by_email(session, values["email"])
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    for key, value in values.items():
        setattr(current_user, key, value.strip() if isinstance(value, str) else value)
    session.commit()
    return UserResponse.model_validate(_load_user(session, str(current_user.id)))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> None:
    _ensure_writable(request)
    _validate_password(payload.new_password)
    if not current_user.password or not bcrypt.checkpw(
        payload.current_password.encode("utf-8"), current_user.password.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect"
        )
    current_user.password = _hash_password(payload.new_password)
    session.commit()


@router.get("/roles", response_model=list[RoleResponse])
def roles(_: CurrentUser, session: SessionDependency) -> list[Role]:
    statement = select(Role).options(selectinload(Role.permissions)).order_by(Role.id)
    return list(session.scalars(statement).unique())


@router.get("/permissions", response_model=list[PermissionResponse])
def permissions(_: CurrentUser, session: SessionDependency) -> list[Permission]:
    return list(session.scalars(select(Permission).order_by(Permission.id)))


@router.get("/users", response_model=list[UserResponse])
def organization_users(current_user: CurrentUser, session: SessionDependency) -> list[User]:
    if current_user.organization_id is None:
        return [current_user]
    statement = (
        select(User)
        .where(User.organization_id == current_user.organization_id)
        .options(selectinload(User.role).selectinload(Role.permissions))
        .order_by(User.created_at)
    )
    return list(session.scalars(statement).unique())


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def invite_user(
    payload: InviteUserRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> UserResponse:
    _ensure_writable(request)
    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization required")
    email = payload.email.strip().lower()
    if find_user_by_email(session, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists"
        )
    if session.get(Role, payload.role_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    temporary_password = secrets.token_urlsafe(16)
    user = User(
        id=uuid4(),
        email=email,
        password=_hash_password(temporary_password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        role_id=payload.role_id,
        organization_id=current_user.organization_id,
        provider="local",
        is_active=True,
    )
    session.add(user)
    session.commit()
    return UserResponse.model_validate(_load_user(session, str(user.id)))


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user_access(
    user_id: str,
    payload: UserAccessUpdateRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> UserResponse:
    _ensure_writable(request)
    user = _load_user(session, user_id)
    if user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.role_id is not None:
        if session.get(Role, payload.role_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        user.role_id = payload.role_id
    if payload.is_active is not None:
        if user.id == current_user.id and not payload.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot deactivate your own account",
            )
        user.is_active = payload.is_active
    session.commit()
    return UserResponse.model_validate(_load_user(session, user_id))
