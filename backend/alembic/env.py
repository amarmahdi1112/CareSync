"""Alembic environment for the isolated CareSync Basic schema."""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, event, pool
from sqlalchemy.engine import URL, Connection, make_url

from alembic import context
from app.basic.models import BasicBase
from app.core.config import Settings
from app.db.sqlite_functions import register_sqlite_functions


def _remove_appledouble_revision_sidecars() -> None:
    """Keep macOS metadata from being interpreted as executable revisions."""

    versions = Path(__file__).resolve().parent / "versions"
    for sidecar in versions.glob("._*.py"):
        sidecar.unlink(missing_ok=True)


_remove_appledouble_revision_sidecars()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = BasicBase.metadata

_PROTECTED_LOCAL_POSTGRES_PORTS = frozenset({5432, 5433, 5434})
_PROTECTED_TARGET_OPT_IN = "CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET"


def _explicit_url() -> str | None:
    """Return a caller-supplied Alembic URL before consulting app settings.

    Programmatic migration checks use ``Config.set_main_option`` to point at a
    disposable database.  Ignoring that value can silently redirect a safety
    check to the retained development database loaded from ``.env``.
    """

    value = config.get_main_option("sqlalchemy.url")
    if value is None or not value.strip():
        return None
    return value.strip()


def _target_url() -> str:
    settings = Settings()
    explicit = _explicit_url()
    if explicit is not None:
        rendered = explicit.replace("%%", "%")
    else:
        value = settings.database_url
        rendered = value.render_as_string(hide_password=False) if isinstance(value, URL) else value
        rendered = str(rendered)

    parsed = make_url(rendered)
    if parsed.get_backend_name() == "postgresql":
        host = parsed.host or ""
        # A local PostgreSQL URL without an explicit port resolves to 5432.
        effective_port = parsed.port or 5432
        is_protected_local_target = (
            host in {"", "localhost", "127.0.0.1", "::1"}
            and effective_port in _PROTECTED_LOCAL_POSTGRES_PORTS
        )
    else:
        is_protected_local_target = False

    if is_protected_local_target and settings.environment == "test":
        raise RuntimeError(
            "Refusing to run a test migration against a protected local PostgreSQL "
            "port; test migrations must use a disposable target outside ports "
            "5432, 5433, and 5434."
        )
    if is_protected_local_target and os.environ.get(_PROTECTED_TARGET_OPT_IN) != "true":
        raise RuntimeError(
            "Refusing to run Alembic against a protected local PostgreSQL port. "
            f"Set {_PROTECTED_TARGET_OPT_IN}=true only for a deliberate retained-"
            "database migration, or configure an explicit disposable target outside "
            "ports 5432, 5433, and 5434."
        )
    return rendered


def _url() -> str:
    # _explicit_url() already removes ConfigParser's doubled percent signs.
    # Both Alembic call sites below consume this value directly, so re-escaping
    # it would corrupt percent-encoded libpq query parameters such as a Unix
    # socket directory.
    return _target_url()


def _safe_target() -> str:
    parsed = make_url(_target_url())
    if parsed.get_backend_name() == "sqlite":
        return f"sqlite:{parsed.database}"
    return (
        f"{parsed.get_backend_name()}://{parsed.username or ''}@{parsed.host or ''}:"
        f"{parsed.port or ''}/{parsed.database or ''}"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        if context.get_context().dialect.name == "postgresql":
            # Keep offline artifacts faithful to the online trust boundary.
            # SET LOCAL is deliberately transaction-scoped, so a generated SQL
            # script cannot leave a caller's session on a surprising path.
            context.execute("SET LOCAL search_path TO public, pg_catalog")
        context.run_migrations()


def run_migrations_online() -> None:
    config.print_stdout(f"CareSync Basic migration target: {_safe_target()}")
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        if not isinstance(supplied_connection, Connection):
            raise RuntimeError(
                "Alembic caller-owned connection must be a SQLAlchemy Connection"
            )
        if supplied_connection.in_transaction() is False:
            raise RuntimeError(
                "Alembic caller-owned connection must already own the migration transaction"
            )
        if supplied_connection.dialect.name == "postgresql":
            supplied_connection.exec_driver_sql(
                "SET LOCAL search_path TO public, pg_catalog"
            )
        context.configure(
            connection=supplied_connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    if make_url(configuration["sqlalchemy.url"]).get_backend_name() == "sqlite":
        event.listen(
            connectable,
            "connect",
            lambda dbapi_connection, _record: register_sqlite_functions(
                dbapi_connection
            ),
        )
    with connectable.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Never let a role-local "$user" schema capture unqualified
            # revision objects. public is the deliberate creation target;
            # pg_catalog remains the only trusted implicit dependency schema.
            # This must share the explicit committing transaction with the
            # migration. A standalone SET would trigger SQLAlchemy autobegin,
            # and closing the connection would roll the migration back.
            connection.exec_driver_sql("SET LOCAL search_path TO public, pg_catalog")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
