"""Public Basic API surface."""

from fastapi import APIRouter

from app.api.basic.admissions import router as admissions_router
from app.api.basic.admissions_decisions import router as admissions_decisions_router
from app.api.basic.ats import router as ats_router
from app.api.basic.attendance import router as attendance_router
from app.api.basic.auth import router as auth_router
from app.api.basic.billing import router as billing_router
from app.api.basic.care import router as care_router
from app.api.basic.child_record_readiness import router as child_record_readiness_router
from app.api.basic.childcare import router as childcare_router
from app.api.basic.childcare_command_receipts import router as childcare_command_receipts_router
from app.api.basic.family_authority import router as family_authority_router
from app.api.basic.family_release_checkout import router as family_release_checkout_router
from app.api.basic.family_release_context import router as family_release_context_router
from app.api.basic.incidents import router as incidents_router
from app.api.basic.marketplace import employer_router as employer_marketplace_router
from app.api.basic.marketplace import router as marketplace_router
from app.api.basic.marketplace_onboarding import router as marketplace_onboarding_router
from app.api.basic.marketplace_personal import router as marketplace_personal_router
from app.api.basic.marketplace_realtime import router as marketplace_realtime_router
from app.api.basic.medications import router as medications_router
from app.api.basic.name_matching import router as name_matching_router
from app.api.basic.notification_realtime import router as notification_realtime_router
from app.api.basic.notifications import router as notifications_router
from app.api.basic.organization import router as organization_router
from app.api.basic.realtime import router as realtime_router
from app.api.basic.release_checkout_activation import (
    router as release_checkout_activation_router,
)
from app.api.basic.room_placements import router as room_placements_router
from app.api.basic.room_safety import manager_router as room_safety_manager_router
from app.api.basic.room_safety import self_router as room_safety_self_router
from app.api.basic.staff import router as staff_router
from app.api.basic.staff_exchange import manager_router as staff_exchange_router
from app.api.basic.staff_exchange import self_router as self_exchange_router
from app.api.basic.staff_operations import router as staff_operations_router
from app.api.basic.staff_schedules import manager_router as staff_schedules_router
from app.api.basic.staff_schedules import self_router as self_schedules_router
from app.api.basic.staff_screening import candidate_router as staff_screening_candidate_router
from app.api.basic.staff_screening import employer_router as staff_screening_employer_router
from app.api.basic.staff_workforce import manager_router as staff_workforce_router
from app.api.basic.staff_workforce import self_router as self_workforce_router
from app.api.basic.transport_registry import manager_router as transport_registry_manager_router
from app.api.basic.transport_registry import self_router as transport_registry_self_router

basic_router = APIRouter()
basic_router.include_router(auth_router)
basic_router.include_router(billing_router)
basic_router.include_router(admissions_router)
basic_router.include_router(admissions_decisions_router)
basic_router.include_router(organization_router)
basic_router.include_router(room_placements_router)
basic_router.include_router(room_safety_manager_router)
basic_router.include_router(room_safety_self_router)
basic_router.include_router(child_record_readiness_router)
basic_router.include_router(childcare_command_receipts_router)
basic_router.include_router(family_authority_router)
basic_router.include_router(family_release_context_router)
basic_router.include_router(family_release_checkout_router)
basic_router.include_router(release_checkout_activation_router)
basic_router.include_router(realtime_router)
basic_router.include_router(childcare_router)
basic_router.include_router(attendance_router)
basic_router.include_router(care_router)
basic_router.include_router(medications_router)
basic_router.include_router(name_matching_router)
basic_router.include_router(notifications_router)
basic_router.include_router(notification_realtime_router)
basic_router.include_router(marketplace_router)
basic_router.include_router(marketplace_realtime_router)
basic_router.include_router(marketplace_onboarding_router)
basic_router.include_router(marketplace_personal_router)
basic_router.include_router(staff_screening_candidate_router)
basic_router.include_router(employer_marketplace_router)
basic_router.include_router(staff_screening_employer_router)
basic_router.include_router(incidents_router)
basic_router.include_router(staff_router)
basic_router.include_router(staff_operations_router)
basic_router.include_router(staff_schedules_router)
basic_router.include_router(self_schedules_router)
basic_router.include_router(staff_workforce_router)
basic_router.include_router(self_workforce_router)
basic_router.include_router(staff_exchange_router)
basic_router.include_router(self_exchange_router)
basic_router.include_router(ats_router)
basic_router.include_router(transport_registry_self_router)
basic_router.include_router(transport_registry_manager_router)
