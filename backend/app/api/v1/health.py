"""Application and database health endpoints."""

from fastapi import APIRouter, Request

from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    database_health = DatabaseHealth.model_validate(request.app.state.database.health())
    settings = request.app.state.settings
    is_healthy = database_health.connected and database_health.integrity in {"ok", "not_applicable"}
    return HealthResponse(
        status="ok" if is_healthy else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        database=database_health,
        staff_screening_evidence_upload=getattr(
            getattr(
                request.app.state,
                "staff_screening_evidence_runtime_status",
                None,
            ),
            "state",
            "unavailable",
        ),
    )
