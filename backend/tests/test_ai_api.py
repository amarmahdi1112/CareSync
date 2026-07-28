from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.config import Settings
from app.main import create_app


def test_ai_routes_are_documented_and_write_guarded(tmp_path) -> None:
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
    child_id = uuid4()
    with TestClient(application) as client:
        paths = client.get("/openapi.json").json()["paths"]
        response = client.post(
            f"/api/v1/ai/children/{child_id}/messages",
            json={"message": "Development summary"},
        )

    assert "/api/v1/ai/children/{child_id}/messages" in paths
    assert "/api/v1/ai/invoice-agent" in paths
    assert response.status_code == 409
