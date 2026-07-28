"""Read-only educator release-context projection for 0029B."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.basic.dependencies import BasicContextDependency
from app.api.dependencies import SessionDependency
from app.basic.family_release_context import (
    ReleaseContextInconsistentError,
    ReleaseContextReevaluationRequired,
    compose_release_context,
)
from app.basic.family_release_context_repository import (
    ReleaseContextRepositoryError,
    load_release_context_input,
)
from app.basic.family_release_context_schemas import ReleaseContextResponse

router = APIRouter(tags=["basic family release context"])


def _require_release_context_boundary(request: Request) -> None:
    if not getattr(
        request.app.state,
        "family_authority_release_context_enabled",
        False,
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "family_authority_release_context_unavailable"},
        )


def _strict_facility_id(request: Request) -> UUID:
    query_items = list(request.query_params.multi_items())
    if len(query_items) != 1 or query_items[0][0] != "facility_id":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_release_context_query"},
        )
    try:
        return UUID(query_items[0][1])
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_release_context_query"},
        ) from None


@router.get(
    "/children/{child_id}/release-context",
    response_model=ReleaseContextResponse,
)
async def family_release_context(
    child_id: UUID,
    request: Request,
    context: BasicContextDependency,
    session: SessionDependency,
) -> ReleaseContextResponse:
    """Return an expiring preparation projection; never authorize checkout."""

    _require_release_context_boundary(request)
    if "release:read" not in set(context.role.permissions or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required",
        )
    facility_id = _strict_facility_id(request)
    if await request.body():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "release_context_request_body_not_allowed"},
        )
    try:
        input_value = load_release_context_input(
            session,
            context,
            child_id=child_id,
            facility_id=facility_id,
        )
        return compose_release_context(input_value)
    except ReleaseContextRepositoryError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code},
        ) from None
    except (ReleaseContextInconsistentError, ReleaseContextReevaluationRequired):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "release_context_inconsistent"},
        ) from None
