from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.config import Settings
from app.main import create_app


def test_family_registration_is_documented_and_write_guarded(tmp_path) -> None:
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
        id=uuid4(),
        organization_id=uuid4(),
        first_name="Test",
        last_name="User",
        email="test@example.com",
    )
    payload = {
        "primary_guardian": {
            "first_name": "Primary",
            "last_name": "Guardian",
            "email": "guardian@example.com",
            "cell_phone": "555-0100",
        },
        "children": [
            {
                "first_name": "Child",
                "last_name": "Guardian",
                "date_of_birth": "2022-01-01",
                "start_date": "2026-01-01",
            }
        ],
        "consents": {},
    }

    with TestClient(application) as client:
        paths = client.get("/openapi.json").json()["paths"]
        response = client.post("/api/v1/families", json=payload)

    assert "/api/v1/families" in paths
    assert response.status_code == 409
