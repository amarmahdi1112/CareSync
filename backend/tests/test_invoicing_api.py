import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.invoicing import _validate_invoice_dates
from app.core.config import Settings
from app.main import create_app


def test_invoicing_read_routes_are_documented(tmp_path) -> None:
    application = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_path=tmp_path / "caresync.db",
            database_name="caresync",
            database_read_only=True,
        )
    )

    with TestClient(application) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/invoicing/invoices" in paths
    assert "/api/v1/invoicing/invoices/dashboard" in paths
    assert "/api/v1/invoicing/invoices/analytics" in paths
    assert "/api/v1/invoicing/settings" in paths
    assert "/api/v1/invoicing/prefill/{family_id}" in paths
    assert "/api/v1/invoicing/billing-runs/preview" in paths
    assert "/api/v1/invoicing/invoices/bulk-generate" in paths
    assert "/api/v1/invoicing/credits" in paths
    assert "/api/v1/invoicing/parent-portion-tracker" in paths


def test_invoice_dates_reject_invalid_chronology() -> None:
    with pytest.raises(HTTPException, match="Due date cannot be before"):
        _validate_invoice_dates({"issue_date": "2026-08-01", "due_date": "2026-07-31"})

    with pytest.raises(HTTPException, match="Billing period end cannot be before"):
        _validate_invoice_dates(
            {
                "issue_date": "2026-07-01",
                "due_date": "2026-07-31",
                "period_start": "2026-07-31",
                "period_end": "2026-07-01",
            }
        )
