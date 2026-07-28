"""Foundation-level application tests."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_preserves_legacy_database_names(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "CareSync Private",
        "version": "0.1.0",
        "database": {
            "connected": True,
            "integrity": "ok",
            "database_name": "caresync",
            "database_filename": "caresync.db",
        },
        "staff_screening_evidence_upload": "unavailable",
    }


def test_rejects_renamed_sqlite_database(tmp_path) -> None:
    try:
        Settings(_env_file=None, database_path=tmp_path / "renamed.db")
    except ValueError as error:
        assert "caresync.db" in str(error)
    else:
        raise AssertionError("A renamed database should be rejected")


def test_basic_does_not_mount_legacy_uploads(tmp_path) -> None:
    application = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_path=tmp_path / "caresync.db",
            enable_advanced_routes=False,
        )
    )

    assert all(getattr(route, "path", None) != "/uploads" for route in application.routes)
