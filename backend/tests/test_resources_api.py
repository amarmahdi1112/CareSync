from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.config import Settings
from app.main import create_app


def test_resource_catalog_and_read_only_write_guard(tmp_path) -> None:
    application = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_path=tmp_path / "caresync.db",
            database_name="caresync",
            database_read_only=True,
        )
    )
    application.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        organization_id=uuid4()
    )
    with TestClient(application) as client:
        catalog = client.get("/api/v1/resources")
        blocked_write = client.post(
            "/api/v1/resources/families", json={"name": "Must not be created"}
        )
        unknown = client.get("/api/v1/resources/not_a_table")

    assert catalog.status_code == 200
    assert len(catalog.json()["resources"]) == 40
    assert "invoices" in catalog.json()["resources"]
    assert blocked_write.status_code == 409
    assert "disabled" in blocked_write.json()["detail"]
    assert unknown.status_code == 404
