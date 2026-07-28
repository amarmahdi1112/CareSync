"""Normal verified child-release command boundary."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.basic.dependencies import BasicContextDependency
from app.api.dependencies import SessionDependency
from app.basic.family_release_checkout_schemas import (
    ReleaseCheckoutCommand,
    ReleaseCheckoutResponse,
)
from app.basic.family_release_checkout_service import (
    ReleaseCheckoutServiceError,
    release_checkout,
)
from app.basic.room_safety import foundation_enabled

router = APIRouter(prefix="/attendance", tags=["basic verified release"])

PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Authorization, X-Organization-ID",
}

# The shared command spine predates this endpoint and some of its exceptions
# carry internal reconciliation fields.  Nothing from those exception bodies
# crosses this boundary.  Only these stable product codes are public here.
_COMMAND_SPINE_ERROR_STATUS = {
    "operation_reused": status.HTTP_409_CONFLICT,
    "operation_finalized_absent": status.HTTP_409_CONFLICT,
    "release_checkout_operation_not_found": status.HTTP_404_NOT_FOUND,
}


def _bounded_command_spine_error(error: HTTPException) -> HTTPException:
    detail = error.detail
    code = detail.get("code") if isinstance(detail, dict) else None
    if isinstance(code, str) and code in _COMMAND_SPINE_ERROR_STATUS:
        public_code = code
    elif error.status_code == status.HTTP_404_NOT_FOUND:
        # Actor-private receipt lookup deliberately makes a foreign operation
        # indistinguishable from an operation that does not exist.
        public_code = "release_checkout_operation_not_found"
    else:
        public_code = "family_authority_release_checkout_unavailable"
    return HTTPException(
        status_code=_COMMAND_SPINE_ERROR_STATUS.get(
            public_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
        detail={"code": public_code},
        headers=PRIVATE_HEADERS,
    )


def _require_release_checkout_boundary(request: Request) -> None:
    if not getattr(request.app.state, "family_release_checkout_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "family_authority_release_checkout_unavailable"},
            headers=PRIVATE_HEADERS,
        )


@router.post(
    "/release-check-out",
    response_model=ReleaseCheckoutResponse,
)
def normal_verified_release_checkout(
    payload: ReleaseCheckoutCommand,
    request: Request,
    response: Response,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ReleaseCheckoutResponse:
    """Commit or exactly replay one normal, verified release."""

    _require_release_checkout_boundary(request)
    try:
        result = release_checkout(
            session,
            context,
            payload,
            writable=not request.app.state.settings.database_read_only,
            room_safety_active=foundation_enabled(request),
        )
    except ReleaseCheckoutServiceError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code},
            headers=PRIVATE_HEADERS,
        ) from None
    except HTTPException as error:
        raise _bounded_command_spine_error(error) from None
    for header, value in PRIVATE_HEADERS.items():
        response.headers[header] = value
    return result
