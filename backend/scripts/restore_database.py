"""Restore a CareSync logical backup into an explicitly disposable PostgreSQL target.

This helper is intentionally incapable of targeting the original, legacy-clone, or
live-local ports. It exists to prove that a pre-migration backup is restorable; it
is not an in-place production restore command.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import stat
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

if __package__:
    from .darwin_durability import full_sync_fd
else:
    from darwin_durability import full_sync_fd

from alembic.config import Config
from sqlalchemy import MetaData, Table, func, select, text
from sqlalchemy.engine import Connection

from alembic import command
from app.core.config import BACKEND_ROOT, Settings
from app.db.session import Database
from scripts.backup_database import (
    BACKUP_FORMAT,
    BackupContractError,
    _json_line,
    _ordered_select,
    encode_value,
    verify_backup_artifacts,
)

PROTECTED_POSTGRES_PORTS = {5432, 5433, 5434}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class RestoreContractError(RuntimeError):
    """Raised when the disposable restore contract is not satisfied."""


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _assert_no_symlink_components(path: Path) -> None:
    absolute = _absolute_lexical(path)
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if os.path.lexists(cursor) and stat.S_ISLNK(cursor.lstat().st_mode):
            raise RestoreContractError(f"Private receipt path {path} contains a symbolic link")


def _ensure_private_receipt_directory(path: Path) -> None:
    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute)
    if os.path.lexists(absolute):
        details = absolute.lstat()
        if not stat.S_ISDIR(details.st_mode):
            raise RestoreContractError("Restore receipt parent is not a directory")
    else:
        missing: list[Path] = []
        cursor = absolute
        while not os.path.lexists(cursor):
            missing.append(cursor)
            parent = cursor.parent
            if parent == cursor:
                raise RestoreContractError("Restore receipt parent has no existing ancestor")
            cursor = parent
        if cursor.is_symlink() or not cursor.is_dir():
            raise RestoreContractError("Restore receipt parent has an unsafe ancestor")
        for directory in reversed(missing):
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError as error:
                raise RestoreContractError(
                    "Restore receipt parent changed while it was created"
                ) from error
            directory.chmod(0o700)
            directory_descriptor = _open_directory_no_follow(directory)
            parent_descriptor = _open_directory_no_follow(directory.parent)
            try:
                full_sync_fd(directory_descriptor)
                full_sync_fd(parent_descriptor)
            except OSError as error:
                raise RestoreContractError(
                    "Restore receipt parent could not be durably created"
                ) from error
            finally:
                os.close(directory_descriptor)
                os.close(parent_descriptor)
    details = absolute.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise RestoreContractError(
            "Restore receipt parent must be an owner-controlled mode 0700 directory"
        )


def _open_directory_no_follow(path: Path) -> int:
    absolute = _absolute_lexical(path)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise RestoreContractError("This platform cannot safely create a restore receipt")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    current = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        return current
    except OSError as error:
        os.close(current)
        raise RestoreContractError(
            "Restore receipt parent contains an unsafe path component"
        ) from error


def write_private_restore_receipt(path: Path, payload: dict[str, Any]) -> None:
    """Create a private durable receipt without following links or replacing a file."""

    absolute = _absolute_lexical(path)
    if absolute.name in {"", ".", ".."}:
        raise RestoreContractError("Restore receipt path is invalid")
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _ensure_private_receipt_directory(absolute.parent)
    parent_descriptor = _open_directory_no_follow(absolute.parent)
    created = False
    created_identity: tuple[int, int] | None = None
    try:
        parent_details = os.fstat(parent_descriptor)
        if (
            not stat.S_ISDIR(parent_details.st_mode)
            or stat.S_IMODE(parent_details.st_mode) != 0o700
            or parent_details.st_uid != os.geteuid()
        ):
            raise RestoreContractError(
                "Restore receipt parent must remain an owner-controlled mode 0700 directory"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(absolute.name, flags, 0o600, dir_fd=parent_descriptor)
        except FileExistsError as error:
            raise RestoreContractError(
                f"Refusing to replace existing restore receipt {absolute}"
            ) from error
        except OSError as error:
            raise RestoreContractError("Restore receipt could not be created safely") from error
        created = True
        try:
            opened_details = os.fstat(descriptor)
            created_identity = (opened_details.st_dev, opened_details.st_ino)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as destination:
                destination.write(serialized)
                destination.flush()
                full_sync_fd(destination.fileno())
                written_details = os.fstat(destination.fileno())
            details = os.stat(
                absolute.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(details.st_mode)
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 1
                or details.st_uid != os.geteuid()
                or (details.st_dev, details.st_ino)
                != created_identity
                or (written_details.st_dev, written_details.st_ino)
                != created_identity
            ):
                raise RestoreContractError(
                    "Restore receipt did not remain a private owner-controlled single-link file"
                )
            full_sync_fd(parent_descriptor)
        except BaseException:
            try:
                current = os.stat(
                    absolute.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if created_identity == (current.st_dev, current.st_ino):
                    os.unlink(absolute.name, dir_fd=parent_descriptor)
                    full_sync_fd(parent_descriptor)
            except OSError:
                pass
            raise
    finally:
        os.close(parent_descriptor)
    if not created:
        raise RestoreContractError("Restore receipt was not created")


def disposable_confirmation(settings: Settings) -> str:
    return f"{settings.database_host}:{settings.database_port}/{settings.database_name}"


def validate_disposable_target(settings: Settings, confirmation: str | None) -> None:
    if settings.database_type != "postgres":
        raise RestoreContractError("Restore verification requires PostgreSQL")
    if settings.database_host not in LOOPBACK_HOSTS:
        raise RestoreContractError("Restore target must be a loopback PostgreSQL server")
    if settings.database_port in PROTECTED_POSTGRES_PORTS:
        raise RestoreContractError(
            f"Port {settings.database_port} is protected and can never be a restore target"
        )
    expected = disposable_confirmation(settings)
    if confirmation != expected:
        raise RestoreContractError(
            "Disposable target confirmation is missing; set "
            f"CARESYNC_RESTORE_CONFIRM_DISPOSABLE={expected!r}"
        )


def decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or set(value) != {"$type", "value"}:
        return value
    kind = value["$type"]
    encoded = value["value"]
    if kind == "decimal":
        return Decimal(encoded)
    if kind == "uuid":
        return UUID(encoded)
    if kind == "datetime":
        return datetime.fromisoformat(encoded)
    if kind == "date":
        return date.fromisoformat(encoded)
    if kind == "time":
        return time.fromisoformat(encoded)
    if kind == "bytes":
        import base64

        return base64.b64decode(encoded, validate=True)
    if kind == "json":
        if not isinstance(encoded, (dict, list)):
            raise RestoreContractError("Encoded JSON backup value is malformed")
        return encoded
    if kind == "string":
        return str(encoded)
    raise RestoreContractError(f"Unsupported encoded value type {kind!r}")


def _target_role_preflight(connection: Connection) -> None:
    identity = (
        connection.execute(
            text(
                "SELECT role.rolsuper, role.rolbypassrls "
                "FROM pg_roles AS role WHERE role.rolname=current_user"
            )
        )
        .mappings()
        .one_or_none()
    )
    if identity is None or not (bool(identity["rolsuper"]) or bool(identity["rolbypassrls"])):
        raise RestoreContractError(
            "Disposable restore role must be superuser or BYPASSRLS so verification is complete"
        )


def _public_table_names(connection: Connection) -> list[str]:
    return list(
        connection.execute(
            text(
                "SELECT class.relname FROM pg_class AS class "
                "JOIN pg_namespace AS namespace ON namespace.oid=class.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND class.relkind IN ('r','p') ORDER BY class.relname"
            )
        ).scalars()
    )


def _prepare_empty_target(settings: Settings, revision: str) -> None:
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            _target_role_preflight(connection)
            existing = _public_table_names(connection)
        if existing:
            raise RestoreContractError(
                "--prepare-empty-target requires a database with no public tables"
            )
    finally:
        database.dispose()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, revision)


def _assert_target_schema(
    connection: Connection, expected_tables: list[str], expected_revisions: list[str]
) -> MetaData:
    connection.exec_driver_sql("SET LOCAL row_security = off")
    connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
    _target_role_preflight(connection)
    actual_tables = _public_table_names(connection)
    if actual_tables != expected_tables:
        raise RestoreContractError("Disposable target table inventory does not match the backup")
    metadata = MetaData()
    metadata.reflect(bind=connection)
    actual_revisions = (
        list(
            connection.execute(
                select(metadata.tables["alembic_version"].c.version_num).order_by(
                    metadata.tables["alembic_version"].c.version_num
                )
            ).scalars()
        )
        if "alembic_version" in metadata.tables
        else []
    )
    if actual_revisions != expected_revisions:
        raise RestoreContractError("Disposable target Alembic revision does not match the backup")
    return metadata


def _truncate_target(connection: Connection, metadata: MetaData) -> None:
    tables = [table for name, table in sorted(metadata.tables.items()) if name != "alembic_version"]
    if not tables:
        return
    quote = connection.dialect.identifier_preparer.quote
    names = ", ".join(f"public.{quote(table.name)}" for table in tables)
    connection.exec_driver_sql(f"TRUNCATE TABLE {names} RESTART IDENTITY")


def _assert_strong_target_attestation(
    connection: Connection,
    metadata: MetaData,
    settings: Settings,
    *,
    expected_data_directory: Path,
    expected_system_identifier: str,
    expected_revisions: list[str],
    require_empty_target: bool,
) -> dict[str, Any]:
    """Lock and re-attest the same transaction that may truncate the target."""

    quote = connection.dialect.identifier_preparer.quote
    locked_names = ", ".join(
        f"public.{quote(table.name)}" for _, table in sorted(metadata.tables.items())
    )
    connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
    if locked_names:
        connection.exec_driver_sql(f"LOCK TABLE {locked_names} IN ACCESS EXCLUSIVE MODE")

    identity = (
        connection.execute(
            text(
                "SELECT current_user AS role_name, current_database() AS database_name, "
                "COALESCE(host(inet_server_addr()),'') AS server_address, "
                "inet_server_port() AS server_port, "
                "current_setting('data_directory') AS data_directory"
            )
        )
        .mappings()
        .one()
    )
    system_identifier = str(
        connection.execute(
            text("SELECT system_identifier::text FROM pg_control_system()")
        ).scalar_one()
    )
    other_sessions = int(
        connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=current_database() "
                "AND backend_type='client backend' AND pid<>pg_backend_pid()"
            )
        ).scalar_one()
    )
    if identity["role_name"] != settings.database_user:
        raise RestoreContractError("Disposable target role identity is unexpected")
    if identity["database_name"] != settings.database_name:
        raise RestoreContractError("Disposable target database identity is unexpected")
    if identity["server_address"] not in {"127.0.0.1", "::1"}:
        raise RestoreContractError("Disposable target server address is not loopback")
    if identity["server_port"] != settings.database_port:
        raise RestoreContractError("Disposable target server port is unexpected")
    observed_directory = Path(os.path.abspath(str(identity["data_directory"])))
    expected_directory = Path(os.path.abspath(expected_data_directory.expanduser()))
    if observed_directory != expected_directory:
        raise RestoreContractError("Disposable target data directory is unexpected")
    if system_identifier != expected_system_identifier:
        raise RestoreContractError("Disposable target system identifier is unexpected")
    if other_sessions:
        raise RestoreContractError("Disposable target has another client session")

    unexpected_schemas = list(
        connection.execute(
            text(
                "SELECT namespace.nspname FROM pg_namespace AS namespace "
                "WHERE namespace.nspname NOT IN ('public','information_schema') "
                "AND namespace.nspname !~ '^pg_' "
                "ORDER BY namespace.nspname"
            )
        ).scalars()
    )
    if unexpected_schemas:
        raise RestoreContractError(
            "Disposable target contains a non-system schema outside public"
        )

    actual_tables = _public_table_names(connection)
    if actual_tables != sorted(metadata.tables):
        raise RestoreContractError("Disposable target table inventory changed before restore")
    version_table = metadata.tables.get("alembic_version")
    revision_rows = (
        list(
            connection.execute(
                select(version_table.c.version_num).order_by(version_table.c.version_num)
            ).scalars()
        )
        if version_table is not None
        else []
    )
    if revision_rows != expected_revisions:
        raise RestoreContractError(
            "Disposable target Alembic revision changed before restore"
        )
    counts = {
        name: int(connection.execute(select(func.count()).select_from(table)).scalar_one())
        for name, table in sorted(metadata.tables.items())
    }
    if require_empty_target and any(
        count for name, count in counts.items() if name != "alembic_version"
    ):
        raise RestoreContractError(
            "Disposable target contains application rows immediately before restore"
        )
    return {
        "roleName": identity["role_name"],
        "databaseName": identity["database_name"],
        "serverAddress": identity["server_address"],
        "serverPort": identity["server_port"],
        "dataDirectory": os.fspath(expected_directory),
        "systemIdentifier": system_identifier,
        "otherClientSessions": other_sessions,
        "alembicRevisions": revision_rows,
        "tableCounts": counts,
    }


def _flush_rows(connection: Connection, table: Table, rows: list[dict[str, Any]]) -> None:
    if rows:
        connection.execute(table.insert(), rows)
        rows.clear()


def _restore_rows(connection: Connection, metadata: MetaData, backup_path: Path) -> dict[str, int]:
    counts = {name: 0 for name in metadata.tables}
    active_table: Table | None = None
    pending: list[dict[str, Any]] = []
    with gzip.open(backup_path, "rt", encoding="utf-8") as source:
        next(source)
        for line in source:
            payload = json.loads(line)
            table_name = payload["table"]
            if table_name == "alembic_version":
                counts[table_name] += 1
                continue
            table = metadata.tables.get(table_name)
            if table is None:
                raise RestoreContractError(f"Backup contains unknown table {table_name!r}")
            if active_table is not None and active_table is not table:
                _flush_rows(connection, active_table, pending)
            active_table = table
            pending.append({key: decode_value(value) for key, value in payload["row"].items()})
            counts[table_name] += 1
            if len(pending) >= 500:
                _flush_rows(connection, table, pending)
    if active_table is not None:
        _flush_rows(connection, active_table, pending)
    return counts


def _reset_sequences(connection: Connection, metadata: MetaData) -> None:
    quote = connection.dialect.identifier_preparer.quote
    for table in metadata.sorted_tables:
        for column in table.columns:
            if column.autoincrement is not True:
                continue
            qualified = f"public.{quote(table.name)}"
            sequence = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": qualified, "column_name": column.name},
            ).scalar_one()
            if sequence is None:
                continue
            maximum = connection.exec_driver_sql(
                f"SELECT MAX({quote(column.name)}) FROM {qualified}"
            ).scalar_one()
            if maximum is None:
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
                    {"sequence_name": sequence},
                )
            else:
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), :maximum, true)"),
                    {"sequence_name": sequence, "maximum": maximum},
                )


def _verify_restored_rows(connection: Connection, metadata: MetaData) -> tuple[dict[str, int], str]:
    connection.exec_driver_sql("SET LOCAL row_security = off")
    counts: dict[str, int] = {}
    digest = hashlib.sha256()
    for table_name, table in sorted(metadata.tables.items()):
        count = 0
        for row in connection.execute(_ordered_select(table)).mappings():
            line = _json_line(
                {
                    "table": table_name,
                    "row": {key: encode_value(value) for key, value in row.items()},
                }
            )
            digest.update(line.encode())
            count += 1
        counts[table_name] = count
    return counts, digest.hexdigest()


def restore_and_verify(
    backup_path: Path,
    manifest_path: Path,
    *,
    prepare_empty_target: bool,
    receipt_path: Path | None,
    expected_data_directory: Path | None = None,
    expected_system_identifier: str | None = None,
    require_empty_target: bool = False,
    configured_settings: Settings | None = None,
) -> dict[str, Any]:
    artifacts = verify_backup_artifacts(backup_path, manifest_path)
    header = artifacts["header"]
    manifest = artifacts["manifest"]
    if header.get("format") != BACKUP_FORMAT or header.get("databaseType") != "postgres":
        raise RestoreContractError("Only PostgreSQL CareSync v2 backups can be restored")
    settings = configured_settings or Settings(database_read_only=False)
    validate_disposable_target(settings, os.environ.get("CARESYNC_RESTORE_CONFIRM_DISPOSABLE"))
    source = header.get("source") or {}
    if source.get("port") == settings.database_port:
        raise RestoreContractError("Restore target port matches the backup source port")
    revisions = header.get("alembicRevisions")
    if not isinstance(revisions, list) or len(revisions) != 1:
        raise RestoreContractError("Backup must name exactly one Alembic revision")
    if (expected_data_directory is None) != (expected_system_identifier is None):
        raise RestoreContractError(
            "Strong target attestation requires both data directory and system identifier"
        )
    if require_empty_target and expected_data_directory is None:
        raise RestoreContractError(
            "Empty-target enforcement requires strong target attestation"
        )
    if prepare_empty_target:
        _prepare_empty_target(settings, revisions[0])

    database = Database(settings)
    try:
        with database.engine.connect() as connection, connection.begin():
            metadata = _assert_target_schema(connection, header["tables"], revisions)
            target_attestation = None
            if expected_data_directory is not None and expected_system_identifier is not None:
                target_attestation = _assert_strong_target_attestation(
                    connection,
                    metadata,
                    settings,
                    expected_data_directory=expected_data_directory,
                    expected_system_identifier=expected_system_identifier,
                    expected_revisions=revisions,
                    require_empty_target=require_empty_target,
                )
            connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
            _truncate_target(connection, metadata)
            restored_counts = _restore_rows(connection, metadata, backup_path)
            if restored_counts != manifest["tableCounts"]:
                raise RestoreContractError("Rows read during restore do not match the manifest")
            _reset_sequences(connection, metadata)
        with (
            database.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as verification_connection,
            verification_connection.begin(),
        ):
            verification_connection.exec_driver_sql("SET TRANSACTION READ ONLY, DEFERRABLE")
            metadata = _assert_target_schema(verification_connection, header["tables"], revisions)
            verified_counts, verified_digest = _verify_restored_rows(
                verification_connection, metadata
            )
    except BackupContractError as error:
        raise RestoreContractError(str(error)) from error
    finally:
        database.dispose()

    if verified_counts != manifest["tableCounts"]:
        raise RestoreContractError("Restored target direct counts do not match the backup")
    if verified_digest != manifest["sha256Rows"]:
        raise RestoreContractError("Restored target row digest does not match the backup")
    result = {
        "format": "caresync-restore-verification-v1",
        "verifiedAt": datetime.now().astimezone().isoformat(),
        "backup": backup_path.name,
        "backupSha256": manifest["sha256Compressed"],
        "target": disposable_confirmation(settings),
        "alembicRevisions": revisions,
        "tableCounts": verified_counts,
        "totalRows": sum(verified_counts.values()),
        "sha256Rows": verified_digest,
    }
    if target_attestation is not None:
        result["strongTargetAttestation"] = {
            "performed": True,
            "targetWasEmpty": require_empty_target,
            "roleName": target_attestation["roleName"],
            "databaseName": target_attestation["databaseName"],
            "serverAddress": target_attestation["serverAddress"],
            "serverPort": target_attestation["serverPort"],
            "dataDirectory": target_attestation["dataDirectory"],
            "systemIdentifier": target_attestation["systemIdentifier"],
            "otherClientSessions": target_attestation["otherClientSessions"],
            "alembicRevisions": target_attestation["alembicRevisions"],
            "tableCounts": target_attestation["tableCounts"],
        }
    if receipt_path is not None:
        write_private_restore_receipt(receipt_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--prepare-empty-target", action="store_true")
    parser.add_argument(
        "--expected-data-directory",
        type=Path,
        help=(
            "Require the disposable target to retain this exact PostgreSQL "
            "data-directory identity through schema preparation and restore"
        ),
    )
    parser.add_argument(
        "--expected-system-identifier",
        help=(
            "Require the disposable target to retain this exact PostgreSQL "
            "system identifier through schema preparation and restore"
        ),
    )
    parser.add_argument(
        "--require-empty-target",
        action="store_true",
        help=(
            "Lock and prove every application table empty immediately before "
            "the restore writes any row"
        ),
    )
    args = parser.parse_args()
    result = restore_and_verify(
        args.backup,
        args.manifest,
        prepare_empty_target=args.prepare_empty_target,
        receipt_path=args.receipt,
        expected_data_directory=args.expected_data_directory,
        expected_system_identifier=args.expected_system_identifier,
        require_empty_target=args.require_empty_target,
    )
    print(
        "Disposable restore verified: "
        f"{result['totalRows']} rows across {len(result['tableCounts'])} tables"
    )


if __name__ == "__main__":
    main()
