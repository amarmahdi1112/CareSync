"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import create_api_router
from app.basic.staff_screening_vault import (
    StaffScreeningEvidenceRuntimeStatus,
    staff_screening_evidence_runtime_status,
)
from app.core.config import Settings, get_settings
from app.core.evidence_upload_limit import EvidenceUploadLimitMiddleware
from app.db.session import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated application instance for runtime or tests."""

    resolved_settings = settings or get_settings()
    database = Database(resolved_settings)

    @asynccontextmanager
    async def lifespan(running_application: FastAPI) -> AsyncIterator[None]:
        database.assert_basic_runtime_identity()
        public_job_catalog_outbox_enabled = database.has_public_job_catalog_outbox()
        admissions_decision_spine_enabled = database.has_admissions_decision_spine()
        live_room_presence_safety_board_present = (
            database.has_live_room_presence_safety_board()
        )
        kernel_present = database.has_family_authority_kernel()
        vault_present = kernel_present and database.has_family_evidence_vault()
        activation_present = vault_present and database.has_family_authority_activation()
        release_context_present = (
            activation_present and database.has_family_authority_release_context()
        )
        release_checkout_foundation_present = database.has_family_release_checkout_foundation(
            release_context_present=release_context_present
        )
        release_checkout_enabled = bool(
            release_checkout_foundation_present and database.has_family_release_checkout_runtime()
        )
        staff_screening_pathways_enabled = database.has_staff_screening_pathways()
        staff_screening_evidence_status = (
            staff_screening_evidence_runtime_status(resolved_settings)
            if staff_screening_pathways_enabled
            else StaffScreeningEvidenceRuntimeStatus(state="unavailable")
        )
        staff_screening_evidence_upload_available = bool(
            staff_screening_pathways_enabled and staff_screening_evidence_status.available
        )
        driver_vehicle_registry_enabled = database.has_driver_vehicle_registry()
        billing_ledger_present = database.has_billing_ledger()
        billing_manual_boundary_present = bool(
            billing_ledger_present and database.has_billing_manual_activation_boundary()
        )
        transport_command_boundary_present = bool(
            resolved_settings.database_type == "postgres"
            and not resolved_settings.database_read_only
            and not resolved_settings.enable_advanced_routes
            and database.has_transport_registry_commands()
        )
        transport_registry_commands_enabled = bool(
            resolved_settings.database_type == "postgres"
            and not resolved_settings.database_read_only
            and not resolved_settings.enable_advanced_routes
            and driver_vehicle_registry_enabled
            and transport_command_boundary_present
        )
        transport_registry_evidence_identity_available = bool(
            transport_registry_commands_enabled
            and database.transport_evidence_ingest_runtime_available()
        )
        transport_registry_evidence_pipeline_available = bool(
            transport_registry_evidence_identity_available
            and staff_screening_evidence_status.available
        )
        transport_registry_evidence_ingest_available = bool(
            transport_registry_evidence_identity_available
            and transport_registry_evidence_pipeline_available
        )
        # The current ORM projection contains the A1 evidence-object identity.
        # A partial 0029A schema must fail closed before any query can reference
        # the not-yet-present column.
        running_application.state.family_authority_enabled = bool(kernel_present and vault_present)
        running_application.state.public_job_catalog_outbox_enabled = (
            public_job_catalog_outbox_enabled
        )
        running_application.state.admissions_decision_spine_enabled = (
            admissions_decision_spine_enabled
        )
        room_presence_foundation_enabled = bool(
            live_room_presence_safety_board_present
            and not resolved_settings.database_read_only
            and not resolved_settings.enable_advanced_routes
        )
        running_application.state.live_room_presence_safety_board_foundation_enabled = (
            room_presence_foundation_enabled
        )
        # Completion is tenant-specific and is established only by the
        # notification-suppressed release-reconciliation receipt.  Never expose
        # a process-global "enabled" claim before that per-tenant check.
        running_application.state.live_room_presence_safety_board_enabled = False
        running_application.state.family_evidence_vault_enabled = bool(vault_present)
        running_application.state.family_authority_activation_enabled = bool(activation_present)
        running_application.state.family_authority_release_context_enabled = bool(
            release_context_present
        )
        running_application.state.family_release_checkout_foundation_present = (
            release_checkout_foundation_present
        )
        running_application.state.family_release_checkout_enabled = release_checkout_enabled
        running_application.state.staff_screening_pathways_enabled = (
            staff_screening_pathways_enabled
        )
        running_application.state.staff_screening_evidence_runtime_status = (
            staff_screening_evidence_status
        )
        running_application.state.staff_screening_evidence_upload_available = (
            staff_screening_evidence_upload_available
        )
        running_application.state.driver_vehicle_registry_enabled = driver_vehicle_registry_enabled
        running_application.state.billing_ledger_enabled = bool(
            billing_ledger_present
            and (
                resolved_settings.billing_mode in {"shadow", "sandbox"}
                or (
                    resolved_settings.billing_mode == "manual"
                    and billing_manual_boundary_present
                    and resolved_settings.billing_manual_target_is_private_local
                )
            )
            and not resolved_settings.enable_advanced_routes
        )
        running_application.state.billing_ledger_writes_enabled = bool(
            billing_ledger_present
            and resolved_settings.database_type == "postgres"
            and (
                (
                    resolved_settings.billing_mode == "sandbox"
                    and resolved_settings.billing_sandbox_target_is_disposable
                )
                or (
                    resolved_settings.billing_mode == "manual"
                    and billing_manual_boundary_present
                    and resolved_settings.billing_manual_target_is_private_local
                )
            )
            and not resolved_settings.enable_advanced_routes
            and not resolved_settings.database_read_only
        )
        running_application.state.billing_manual_boundary_present = (
            billing_manual_boundary_present
        )
        running_application.state.transport_registry_commands_enabled = (
            transport_registry_commands_enabled
        )
        running_application.state.transport_registry_evidence_ingest_available = (
            transport_registry_evidence_ingest_available
        )
        running_application.state.transport_registry_evidence_pipeline_available = (
            transport_registry_evidence_pipeline_available
        )
        running_application.state.transport_evidence_session_factory = (
            database.transport_evidence_session_factory
            if transport_registry_evidence_ingest_available
            else None
        )
        yield
        database.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description=(
            "CareSync Basic REST API"
            if not resolved_settings.enable_advanced_routes
            else "Private CareSync compatibility REST API"
        ),
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = database
    application.add_middleware(
        EvidenceUploadLimitMiddleware,
        api_prefix=resolved_settings.api_prefix,
        file_limit=resolved_settings.family_evidence_max_bytes,
        staff_screening_file_limit=resolved_settings.staff_screening_document_max_bytes,
    )

    @application.middleware("http")
    async def private_child_record_responses(request: Request, call_next):
        response = await call_next(request)
        relative_path = request.url.path.removeprefix(resolved_settings.api_prefix)
        private_prefixes = (
            "/families",
            "/billing",
            "/children",
            "/enrollments",
            "/admissions",
            "/room-rosters",
            "/room-placement",
            "/child-record-readiness",
            "/childcare-commands",
            "/consent-policies",
            "/attendance/release-check-out",
            "/ai/name-matches",
            "/marketplace/screening",
            "/marketplace/applications",
            "/ats/applications",
            "/staff/self/transport-registry",
            "/staff/transport-registry",
            "/room-safety",
            "/staff/self/room-presence",
            "/staff/self/room-safety",
        )
        if relative_path.startswith(private_prefixes):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Vary"] = "Authorization, X-Organization-ID"
        return response

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_origin_regex=resolved_settings.extension_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(
        create_api_router(enable_advanced_routes=resolved_settings.enable_advanced_routes),
        prefix=resolved_settings.api_prefix,
    )
    # The legacy compatibility API owns its local upload workflow. CareSync
    # Basic profile photos are delivered by authenticated tenant-scoped routes;
    # exposing a Basic media directory would bypass those access controls.
    if resolved_settings.enable_advanced_routes:
        uploads_directory = resolved_settings.database_path.parent / "uploads"
        uploads_directory.mkdir(parents=True, exist_ok=True)
        application.mount("/uploads", StaticFiles(directory=uploads_directory), name="uploads")

    @application.get("/", tags=["system"])
    def root() -> dict[str, str]:
        return {
            "service": resolved_settings.app_name,
            "version": resolved_settings.app_version,
            "docs": "/docs",
        }

    return application


app = create_app()
