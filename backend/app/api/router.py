"""Build the explicit Basic or compatibility API surface."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router


def create_api_router(*, enable_advanced_routes: bool = False) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    if not enable_advanced_routes:
        from app.api.basic.router import basic_router

        router.include_router(basic_router)
        return router

    # Compatibility endpoints are kept intact for the original private app and
    # extension backend.  They are absent from the default Basic OpenAPI.
    from app.api.v1.ai import router as ai_router
    from app.api.v1.auth import router as auth_router
    from app.api.v1.claim_imports import router as claim_imports_router
    from app.api.v1.claim_reports import router as claim_reports_router
    from app.api.v1.claims import router as claims_router
    from app.api.v1.csv_imports import router as csv_imports_router
    from app.api.v1.families import router as families_router
    from app.api.v1.invoicing import router as invoicing_router
    from app.api.v1.organization import router as organization_router
    from app.api.v1.resources import router as resources_router
    from app.api.v1.scheduling import router as scheduling_router
    from app.api.v1.signatures import router as signatures_router

    router.include_router(ai_router)
    router.include_router(auth_router)
    router.include_router(families_router)
    router.include_router(invoicing_router)
    router.include_router(organization_router)
    router.include_router(claims_router)
    router.include_router(claim_reports_router)
    router.include_router(claim_imports_router)
    router.include_router(csv_imports_router)
    router.include_router(scheduling_router)
    router.include_router(signatures_router)
    router.include_router(resources_router)
    return router


# Kept for import compatibility. Runtime applications call the factory above.
api_router = create_api_router()
