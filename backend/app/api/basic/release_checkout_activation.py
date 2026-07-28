"""Owner/administrator boundary for one-way verified-release facility activation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.basic.dependencies import BasicContextDependency
from app.api.dependencies import SessionDependency
from app.basic.release_checkout_activation import (
    ReleaseCheckoutActivationError,
    activate_release_checkout,
    activation_status,
)
from app.basic.release_checkout_activation_schemas import (
    ReleaseCheckoutActivationCommand,
    ReleaseCheckoutActivationResponse,
    ReleaseCheckoutActivationStatus,
)

router = APIRouter(prefix="/facilities", tags=["basic release activation"])

PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Authorization, X-Organization-ID",
}


def _private(response: Response) -> None:
    for header, value in PRIVATE_HEADERS.items():
        response.headers[header] = value


def _require_privileged_actor(context: BasicContextDependency) -> None:
    if context.role.key not in {"owner", "administrator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "release_activation_forbidden"},
            headers=PRIVATE_HEADERS,
        )


def _bounded_command_error(error: HTTPException) -> HTTPException:
    detail = error.detail
    code = detail.get("code") if isinstance(detail, dict) else None
    public_codes = {
        "operation_reused": status.HTTP_409_CONFLICT,
        "operation_finalized_absent": status.HTTP_409_CONFLICT,
    }
    public_code = (
        code if isinstance(code, str) and code in public_codes else "release_activation_unavailable"
    )
    return HTTPException(
        status_code=public_codes.get(
            public_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
        detail={"code": public_code},
        headers=PRIVATE_HEADERS,
    )


@router.get(
    "/{facility_id}/release-checkout-activation",
    response_model=ReleaseCheckoutActivationStatus,
)
def get_release_checkout_activation_status(
    facility_id: UUID,
    request: Request,
    response: Response,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ReleaseCheckoutActivationStatus:
    _require_privileged_actor(context)
    try:
        result = activation_status(
            session,
            context,
            facility_id=facility_id,
            foundation_present=bool(
                getattr(
                    request.app.state,
                    "family_release_checkout_foundation_present",
                    False,
                )
            ),
            runtime_enabled=bool(
                getattr(request.app.state, "family_release_checkout_enabled", False)
            ),
            database_writable=not request.app.state.settings.database_read_only,
        )
    except ReleaseCheckoutActivationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code},
            headers=PRIVATE_HEADERS,
        ) from None
    _private(response)
    return result


@router.post(
    "/{facility_id}/release-checkout-activation",
    response_model=ReleaseCheckoutActivationResponse,
)
def activate_facility_release_checkout(
    facility_id: UUID,
    payload: ReleaseCheckoutActivationCommand,
    request: Request,
    response: Response,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ReleaseCheckoutActivationResponse:
    _require_privileged_actor(context)
    if payload.facility_id != facility_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "release_activation_facility_mismatch"},
            headers=PRIVATE_HEADERS,
        )
    try:
        result = activate_release_checkout(
            session,
            context,
            payload,
            foundation_present=bool(
                getattr(
                    request.app.state,
                    "family_release_checkout_foundation_present",
                    False,
                )
            ),
            runtime_enabled=bool(
                getattr(request.app.state, "family_release_checkout_enabled", False)
            ),
            database_writable=not request.app.state.settings.database_read_only,
        )
    except ReleaseCheckoutActivationError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code},
            headers=PRIVATE_HEADERS,
        ) from None
    except HTTPException as error:
        raise _bounded_command_error(error) from None
    _private(response)
    return result
