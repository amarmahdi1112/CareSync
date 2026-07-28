"""Bind the stable private transport credential to its restricted DB role.

The launcher creates the credential in an owner-only runtime directory.  This
helper reads it without following links, converts it to a PostgreSQL SCRAM
verifier, and updates only the dedicated evidence-ingest login.  The plaintext
credential is never placed in command-line arguments, SQL, or output.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import re
from pathlib import Path

import psycopg
from psycopg import sql

from scripts.basic_runtime_secrets import (
    SECRET_DIRECTORY_NAME,
    TRANSPORT_INGEST_PASSWORD_FILE,
    RuntimeSecretError,
    _directory_flags,
    _read_secret,
    _require_private_directory,
)

DATABASE_NAME = "caresync"
TRANSPORT_ROLE = "caresync_transport_evidence_ingest"
SCRAM_ITERATIONS = 4096
_SCRAM_PATTERN = re.compile(
    r"^SCRAM-SHA-256\$(?P<iterations>[1-9][0-9]*):"
    r"(?P<salt>[A-Za-z0-9+/]+={0,2})\$"
    r"(?P<stored>[A-Za-z0-9+/]+={0,2}):"
    r"(?P<server>[A-Za-z0-9+/]+={0,2})$"
)


class RuntimeCredentialError(RuntimeError):
    """Raised when the local role credential cannot be configured safely."""


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _scram_verifier(
    password: str,
    *,
    salt: bytes | None = None,
    iterations: int = SCRAM_ITERATIONS,
) -> str:
    """Return PostgreSQL's SCRAM-SHA-256 verifier for the ASCII runtime token."""

    if not password.isascii() or not password:
        raise RuntimeCredentialError("Transport credential must be non-empty ASCII")
    if iterations < SCRAM_ITERATIONS:
        raise RuntimeCredentialError("SCRAM iteration count is too small")
    resolved_salt = salt if salt is not None else os.urandom(16)
    if len(resolved_salt) < 16:
        raise RuntimeCredentialError("SCRAM salt is too small")
    salted = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("ascii"),
        resolved_salt,
        iterations,
    )
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    return f"SCRAM-SHA-256${iterations}:{_b64(resolved_salt)}${_b64(stored_key)}:{_b64(server_key)}"


def _verifier_matches(password: str, verifier: str | None) -> bool:
    if verifier is None:
        return False
    match = _SCRAM_PATTERN.fullmatch(verifier)
    if match is None:
        return False
    try:
        iterations = int(match.group("iterations"))
        salt = base64.b64decode(match.group("salt"), validate=True)
    except (ValueError, TypeError):
        return False
    candidate = _scram_verifier(password, salt=salt, iterations=iterations)
    return hmac.compare_digest(candidate, verifier)


def _transport_password(runtime_directory: Path) -> str:
    if not runtime_directory.is_absolute():
        raise RuntimeCredentialError("Runtime directory must be absolute")
    try:
        runtime_descriptor = os.open(runtime_directory, _directory_flags())
    except OSError as exc:
        raise RuntimeCredentialError("Runtime directory is absent or unsafe") from exc
    try:
        _require_private_directory(runtime_descriptor, "Runtime directory")
        secret_descriptor = os.open(
            SECRET_DIRECTORY_NAME,
            _directory_flags(),
            dir_fd=runtime_descriptor,
        )
        try:
            _require_private_directory(secret_descriptor, "Runtime secret directory")
            password_descriptor = os.open(
                TRANSPORT_INGEST_PASSWORD_FILE,
                os.O_RDONLY
                | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
                | (os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0),
                dir_fd=secret_descriptor,
            )
            try:
                return _read_secret(
                    password_descriptor,
                    "transport evidence credential",
                )
            finally:
                os.close(password_descriptor)
        finally:
            os.close(secret_descriptor)
    except (OSError, RuntimeSecretError) as exc:
        raise RuntimeCredentialError("Transport evidence credential is absent or unsafe") from exc
    finally:
        os.close(runtime_descriptor)


def configure_transport_role_credential(
    *,
    runtime_directory: Path,
    host: str,
    port: int,
    database: str,
    migration_user: str,
) -> None:
    """Install the stable verifier on the exact restricted transport login."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeCredentialError("Credential configuration requires a loopback database")
    if not 1 <= port <= 65535:
        raise RuntimeCredentialError("Database port is invalid")
    if database != DATABASE_NAME:
        raise RuntimeCredentialError(f"Database name must remain {DATABASE_NAME!r}")
    if not migration_user or migration_user == TRANSPORT_ROLE:
        raise RuntimeCredentialError("Migration user is invalid")

    password = _transport_password(runtime_directory)
    try:
        with (
            psycopg.connect(
                host=host,
                port=port,
                dbname=database,
                user=migration_user,
                connect_timeout=5,
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                    SELECT current_user, executor.rolsuper, target.rolcanlogin,
                           target.rolsuper, target.rolinherit, target.rolcreaterole,
                           target.rolcreatedb, target.rolreplication,
                           target.rolbypassrls, target.rolpassword
                    FROM pg_catalog.pg_authid AS target
                    JOIN pg_catalog.pg_roles AS executor
                      ON executor.rolname=current_user
                    WHERE target.rolname=%s
                    """,
                (TRANSPORT_ROLE,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeCredentialError("Restricted transport evidence role is absent")
            (
                current_user,
                executor_superuser,
                can_login,
                target_superuser,
                inherits,
                can_create_role,
                can_create_database,
                can_replicate,
                bypasses_rls,
                existing_verifier,
            ) = row
            if str(current_user) != migration_user or not bool(executor_superuser):
                raise RuntimeCredentialError(
                    "Credential configuration requires the local migration owner"
                )
            if (
                not bool(can_login)
                or bool(target_superuser)
                or bool(inherits)
                or bool(can_create_role)
                or bool(can_create_database)
                or bool(can_replicate)
                or bool(bypasses_rls)
            ):
                raise RuntimeCredentialError(
                    "Restricted transport evidence role has an unsafe identity"
                )
            if _verifier_matches(password, str(existing_verifier or "")):
                return
            verifier = _scram_verifier(password)
            cursor.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(TRANSPORT_ROLE),
                    sql.Literal(verifier),
                )
            )
    except RuntimeCredentialError:
        raise
    except psycopg.Error as exc:
        raise RuntimeCredentialError(
            "Restricted transport evidence credential could not be configured"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configure the private CareSync transport-evidence login."
    )
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--database", default=DATABASE_NAME)
    parser.add_argument("--migration-user", required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    configure_transport_role_credential(
        runtime_directory=arguments.runtime_directory,
        host=arguments.host,
        port=arguments.port,
        database=arguments.database,
        migration_user=arguments.migration_user,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
