"""Static release guards for caller-owned migrations and strong restore identity."""

from __future__ import annotations

from pathlib import Path

STAGING_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = STAGING_ROOT / "backend"


def test_alembic_accepts_only_an_existing_caller_owned_transaction() -> None:
    source = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")

    supplied = source.index('config.attributes.get("connection")')
    transaction_guard = source.index("supplied_connection.in_transaction()", supplied)
    configure = source.index("connection=supplied_connection", transaction_guard)
    migrate = source.index("context.run_migrations()", configure)
    engine_fallback = source.index("engine_from_config(", migrate)

    assert supplied < transaction_guard < configure < migrate < engine_fallback
    assert "caller-owned connection must be a SQLAlchemy Connection" in source
    assert "caller-owned connection must already own the migration transaction" in source
    assert "SET LOCAL search_path TO public, pg_catalog" in source


def test_restore_cli_exposes_the_existing_strong_target_attestation() -> None:
    source = (BACKEND_ROOT / "scripts" / "restore_database.py").read_text(
        encoding="utf-8"
    )

    assert '"--expected-data-directory"' in source
    assert '"--expected-system-identifier"' in source
    assert '"--require-empty-target"' in source
    assert "expected_data_directory=args.expected_data_directory" in source
    assert "expected_system_identifier=args.expected_system_identifier" in source
    assert "require_empty_target=args.require_empty_target" in source
    assert '"systemIdentifier": target_attestation["systemIdentifier"]' in source
    assert '"dataDirectory": target_attestation["dataDirectory"]' in source
