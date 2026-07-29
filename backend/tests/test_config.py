from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

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


def test_postgres_unix_socket_is_encoded_as_libpq_query_parameters(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        database_type="postgres",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_host="/var/run/postgresql",
        database_port=5432,
        database_user="postgres",
        database_password="",
    )

    database_url = settings.database_url

    assert isinstance(database_url, URL)
    rendered = database_url.render_as_string(hide_password=False)
    parsed = make_url(rendered)
    engine = create_engine(database_url)
    try:
        _args, connection_parameters = engine.dialect.create_connect_args(database_url)
    finally:
        engine.dispose()

    assert parsed.database == "caresync"
    assert parsed.host is None
    assert parsed.port is None
    assert parsed.query["host"] == "/var/run/postgresql"
    assert parsed.query["port"] == "5432"
    assert connection_parameters["dbname"] == "caresync"
    assert connection_parameters["host"] == "/var/run/postgresql"
    assert connection_parameters["port"] == "5432"
