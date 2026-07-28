"""Legacy tests explicitly exercise the compatibility API surface."""

import os

os.environ.setdefault("ENABLE_ADVANCED_ROUTES", "true")


def _guard_disposable_postgres_target() -> None:
    """Fail before collection if opt-in destructive tests target retained state."""

    host = os.getenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1").strip().lower()
    for port_env in (
        "BASIC_POSTGRES_TEST_PORT",
        "BASIC_POSTGRES_MIGRATION_TEST_PORT",
    ):
        raw_port = os.getenv(port_env)
        if not raw_port:
            continue
        try:
            port = int(raw_port)
        except ValueError as error:
            raise RuntimeError(
                f"{port_env} must be an integer for a disposable local cluster"
            ) from error
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError(
                "Opt-in PostgreSQL tests may run only against a disposable loopback cluster"
            )
        if port in {5432, 5433, 5434} or not 1 <= port <= 65535:
            raise RuntimeError(
                "Opt-in PostgreSQL tests refuse local retained ports 5432, 5433, and 5434"
            )


_guard_disposable_postgres_target()
