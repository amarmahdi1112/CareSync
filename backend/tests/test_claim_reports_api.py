from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_claim_report_routes_are_documented(tmp_path) -> None:
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

    assert "/api/v1/claim-reports" in paths
    assert "/api/v1/claim-reports/{report_id}" in paths
    assert "/api/v1/claim-imports/parse" in paths
    assert "/api/v1/claim-imports/batches" in paths
    assert "/api/v1/claim-imports/batches/{batch_id}" in paths
