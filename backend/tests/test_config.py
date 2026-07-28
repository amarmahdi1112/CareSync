from pathlib import Path

from app.core.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
    )


def test_scheduler_engine_version_defaults_to_v3(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SCHEDULER_ENGINE_VERSION", raising=False)

    settings = _settings(tmp_path)

    assert settings.scheduler_engine_version == "v3"
    assert settings.database_path.name == "caresync.db"
    assert settings.database_name == "caresync"


def test_scheduler_engine_version_accepts_deprecated_v2_rollback(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SCHEDULER_ENGINE_VERSION", "v2")

    settings = _settings(tmp_path)

    assert settings.scheduler_engine_version == "v2"
    assert settings.database_path.name == "caresync.db"
    assert settings.database_name == "caresync"


def test_local_frontend_origins_include_legacy_and_redesign(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    assert "http://127.0.0.1:5173" in settings.allowed_origins
    assert "http://127.0.0.1:5174" in settings.allowed_origins
