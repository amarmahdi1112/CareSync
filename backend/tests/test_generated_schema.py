"""Schema-generation parity checks."""

from app.models.generated_legacy import Base

EXPECTED_TABLES = {
    "activity_logs",
    "child_ai_messages",
    "child_funding",
    "children",
    "claim_generation_configurations",
    "credit_applications",
    "credit_notes",
    "daycare_pricing",
    "emergency_contacts",
    "families",
    "funding_sources",
    "generated_claim_reports",
    "generated_claims",
    "guardians",
    "imported_claims",
    "invoice_allocations",
    "invoice_line_items",
    "invoice_templates",
    "invoices",
    "letterheads",
    "milestone_templates",
    "notifications",
    "organization_members",
    "organizations",
    "payments",
    "permissions",
    "portfolio_entries",
    "portfolio_images",
    "portfolios",
    "provider_settings",
    "rate_schedules",
    "recurring_invoices",
    "role_permissions",
    "roles",
    "scheduled_attendance",
    "signatures",
    "staff_education",
    "staff_profiles",
    "universal_prompts",
    "users",
}


def test_generated_models_cover_live_postgres_schema() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
