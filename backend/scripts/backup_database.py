"""Create and verify a complete, transactionally consistent CareSync backup.

PostgreSQL backups deliberately run with ``row_security=off``. PostgreSQL then
raises an error instead of returning a policy-filtered subset when the caller
cannot bypass FORCE RLS. The backup identity must therefore be a separately
authorized maintenance identity, never the CareSync runtime role.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import stat
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import MetaData, Table, func, select, text
from sqlalchemy.engine import Connection

from app.core.config import Settings
from app.db.session import Database

BACKUP_FORMAT = "caresync-logical-backup-v2"
DEFAULT_RUNTIME_DIRECTORY = Path(
    os.getenv(
        "CARESYNC_BASIC_RUNTIME",
        Path.home() / "Library/Application Support/CareSync Basic",
    )
)
DEFAULT_BACKUP_DIRECTORY = Path(
    os.getenv(
        "CARESYNC_BASIC_BACKUP_DIRECTORY",
        DEFAULT_RUNTIME_DIRECTORY / "backups",
    )
)


class BackupContractError(RuntimeError):
    """Raised when a backup cannot prove completeness or integrity."""


def encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, UUID):
        return {"$type": "uuid", "value": str(value)}
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"$type": "time", "value": value.isoformat()}
    if isinstance(value, bytes):
        return {"$type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (dict, list)):
        return {"$type": "json", "value": value}
    return {"$type": "string", "value": str(value)}


def _json_line(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n"


def _ordered_select(table: Table):
    ordering = list(table.primary_key.columns)
    if not ordering:
        raise BackupContractError(
            f"Table {table.name!r} has no primary key; deterministic backup is unsafe"
        )
    return select(table).order_by(*ordering)


def _postgres_visibility_preflight(connection: Connection) -> dict[str, Any]:
    connection.exec_driver_sql("SET TRANSACTION READ ONLY, DEFERRABLE")
    connection.exec_driver_sql("SET LOCAL row_security = off")
    connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
    identity = (
        connection.execute(
            text(
                "SELECT current_user AS role_name, role.rolsuper, role.rolbypassrls "
                "FROM pg_roles AS role WHERE role.rolname=current_user"
            )
        )
        .mappings()
        .one_or_none()
    )
    if identity is None:
        raise BackupContractError("Unable to identify the PostgreSQL backup role")
    if not (bool(identity["rolsuper"]) or bool(identity["rolbypassrls"])):
        raise BackupContractError(
            "PostgreSQL backup role cannot bypass FORCE RLS; refusing a partial backup"
        )
    table_names = list(
        connection.execute(
            text(
                "SELECT class.relname FROM pg_class AS class "
                "JOIN pg_namespace AS namespace ON namespace.oid=class.relnamespace "
                "WHERE namespace.nspname='public' "
                "AND class.relkind IN ('r','p') ORDER BY class.relname"
            )
        ).scalars()
    )
    if not table_names:
        raise BackupContractError("PostgreSQL public schema contains no tables")
    revision_rows: list[str] = []
    if "alembic_version" in table_names:
        revision_rows = list(
            connection.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).scalars()
        )
    return {
        "tableNames": table_names,
        "alembicRevisions": revision_rows,
        "snapshot": str(connection.execute(text("SELECT txid_current_snapshot()")).scalar_one()),
        "visibilityMode": "row_security_off_complete",
    }


def _reflect_snapshot(
    connection: Connection, database_kind: str
) -> tuple[MetaData, dict[str, Any]]:
    visibility: dict[str, Any]
    if database_kind == "postgres":
        visibility = _postgres_visibility_preflight(connection)
    else:
        visibility = {
            "tableNames": [],
            "alembicRevisions": [],
            "snapshot": "sqlite-read-transaction",
            "visibilityMode": "sqlite-whole-file",
        }
    metadata = MetaData()
    metadata.reflect(bind=connection)
    reflected = sorted(metadata.tables)
    if not reflected:
        raise BackupContractError("Configured database contains no tables")
    if database_kind == "postgres" and reflected != visibility["tableNames"]:
        raise BackupContractError(
            "PostgreSQL catalog/reflection table mismatch; refusing an incomplete backup"
        )
    visibility["tableNames"] = reflected
    if database_kind != "postgres" and "alembic_version" in metadata.tables:
        visibility["alembicRevisions"] = list(
            connection.execute(
                select(metadata.tables["alembic_version"].c.version_num).order_by(
                    metadata.tables["alembic_version"].c.version_num
                )
            ).scalars()
        )
    return metadata, visibility


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_private_mode(path: Path, expected: int) -> None:
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise BackupContractError(
            f"Backup path {path} has mode {actual:04o}; required mode is {expected:04o}"
        )


def verify_backup_artifacts(backup_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Re-read both artifacts and fail closed on any digest/count mismatch."""

    _require_private_mode(backup_path.parent, 0o700)
    _require_private_mode(backup_path, 0o600)
    _require_private_mode(manifest_path, 0o600)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackupContractError("Backup manifest is missing or invalid") from error
    if manifest.get("format") != BACKUP_FORMAT:
        raise BackupContractError("Unsupported backup manifest format")
    if manifest.get("backup") != backup_path.name:
        raise BackupContractError("Backup manifest names a different artifact")
    if _sha256_file(backup_path) != manifest.get("sha256Compressed"):
        raise BackupContractError("Compressed backup SHA-256 mismatch")

    all_lines_digest = hashlib.sha256()
    row_lines_digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    header: dict[str, Any] | None = None
    try:
        with gzip.open(backup_path, "rt", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                encoded = line.encode()
                all_lines_digest.update(encoded)
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as error:
                    raise BackupContractError(
                        f"Backup JSON is invalid at line {line_number}"
                    ) from error
                if line_number == 1:
                    header = payload.get("header")
                    if not isinstance(header, dict) or header.get("format") != BACKUP_FORMAT:
                        raise BackupContractError("Backup header is missing or unsupported")
                    continue
                table_name = payload.get("table")
                if not isinstance(table_name, str) or not isinstance(payload.get("row"), dict):
                    raise BackupContractError(f"Backup row is malformed at line {line_number}")
                row_lines_digest.update(encoded)
                counts[table_name] += 1
    except (OSError, EOFError) as error:
        raise BackupContractError("Backup gzip stream is corrupt") from error
    if header is None:
        raise BackupContractError("Backup is empty")
    expected_tables = header.get("tables")
    if not isinstance(expected_tables, list) or any(
        not isinstance(table, str) for table in expected_tables
    ):
        raise BackupContractError("Backup table inventory is invalid")
    actual_counts = {table: counts.get(table, 0) for table in expected_tables}
    if set(counts) - set(expected_tables):
        raise BackupContractError("Backup contains a row for an undeclared table")
    if actual_counts != manifest.get("tableCounts"):
        raise BackupContractError("Backup row counts do not match the manifest")
    if sum(actual_counts.values()) != manifest.get("totalRows"):
        raise BackupContractError("Backup total row count does not match the manifest")
    if all_lines_digest.hexdigest() != manifest.get("sha256UncompressedJsonLines"):
        raise BackupContractError("Uncompressed backup SHA-256 mismatch")
    if row_lines_digest.hexdigest() != manifest.get("sha256Rows"):
        raise BackupContractError("Backup row-stream SHA-256 mismatch")
    if header.get("directTableCounts") != actual_counts:
        raise BackupContractError("Snapshot-direct counts do not match exported rows")
    return {"header": header, "manifest": manifest, "tableCounts": actual_counts}


def create_backup(output_directory: Path) -> tuple[Path, Path]:
    settings = Settings(database_read_only=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_directory.chmod(0o700)
    _require_private_mode(output_directory, 0o700)
    database = Database(settings)
    database_kind = settings.database_type
    backup_path = output_directory / f"caresync-{database_kind}-{timestamp}.json.gz"
    temporary_backup = output_directory / f".{backup_path.name}.partial-{os.getpid()}"
    all_lines_digest = hashlib.sha256()
    row_lines_digest = hashlib.sha256()
    table_counts: dict[str, int] = {}

    try:
        with database.engine.connect() as raw_connection:
            connection = (
                raw_connection.execution_options(isolation_level="REPEATABLE READ")
                if database_kind == "postgres"
                else raw_connection
            )
            with connection.begin():
                metadata, visibility = _reflect_snapshot(connection, database_kind)
                direct_counts = {
                    table_name: int(
                        connection.execute(select(func.count()).select_from(table)).scalar_one()
                    )
                    for table_name, table in sorted(metadata.tables.items())
                }
                header = {
                    "format": BACKUP_FORMAT,
                    "databaseName": settings.database_name,
                    "databaseType": database_kind,
                    "createdAt": datetime.now().astimezone().isoformat(),
                    "tables": sorted(metadata.tables),
                    "directTableCounts": direct_counts,
                    "alembicRevisions": visibility["alembicRevisions"],
                    "visibilityMode": visibility["visibilityMode"],
                    "snapshot": visibility["snapshot"],
                    "source": {
                        "host": settings.database_host if database_kind == "postgres" else None,
                        "port": settings.database_port if database_kind == "postgres" else None,
                    },
                }
                with gzip.open(
                    temporary_backup, "wt", encoding="utf-8", compresslevel=9
                ) as destination:
                    line = _json_line({"header": header})
                    destination.write(line)
                    all_lines_digest.update(line.encode())
                    for table_name, table in sorted(metadata.tables.items()):
                        count = 0
                        for row in connection.execute(_ordered_select(table)).mappings():
                            payload = {
                                "table": table_name,
                                "row": {key: encode_value(value) for key, value in row.items()},
                            }
                            line = _json_line(payload)
                            destination.write(line)
                            encoded = line.encode()
                            all_lines_digest.update(encoded)
                            row_lines_digest.update(encoded)
                            count += 1
                        if count != direct_counts[table_name]:
                            raise BackupContractError(
                                f"Snapshot row-count mismatch for table {table_name!r}"
                            )
                        table_counts[table_name] = count
        temporary_backup.chmod(0o600)
        _require_private_mode(temporary_backup, 0o600)
        os.replace(temporary_backup, backup_path)
        backup_path.chmod(0o600)
        _require_private_mode(backup_path, 0o600)
        manifest_path = backup_path.with_suffix(".manifest.json")
        temporary_manifest = output_directory / f".{manifest_path.name}.partial-{os.getpid()}"
        manifest = {
            "format": BACKUP_FORMAT,
            "backup": backup_path.name,
            "sha256Compressed": _sha256_file(backup_path),
            "sha256UncompressedJsonLines": all_lines_digest.hexdigest(),
            "sha256Rows": row_lines_digest.hexdigest(),
            "tableCounts": table_counts,
            "totalRows": sum(table_counts.values()),
        }
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_manifest.chmod(0o600)
        _require_private_mode(temporary_manifest, 0o600)
        os.replace(temporary_manifest, manifest_path)
        manifest_path.chmod(0o600)
        _require_private_mode(manifest_path, 0o600)
        verify_backup_artifacts(backup_path, manifest_path)
        return backup_path, manifest_path
    except Exception:
        temporary_backup.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)
        candidate_manifest = backup_path.with_suffix(".manifest.json")
        candidate_manifest.unlink(missing_ok=True)
        (output_directory / f".{candidate_manifest.name}.partial-{os.getpid()}").unlink(
            missing_ok=True
        )
        raise
    finally:
        database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_BACKUP_DIRECTORY,
    )
    parser.add_argument(
        "--verify",
        nargs=2,
        metavar=("BACKUP", "MANIFEST"),
        type=Path,
        help="verify existing artifacts instead of creating a backup",
    )
    args = parser.parse_args()
    if args.verify:
        verify_backup_artifacts(*args.verify)
        print("Backup artifacts verified")
        return
    backup, manifest = create_backup(args.output_directory)
    print(f"Backup created: {backup}")
    print(f"Manifest created: {manifest}")


if __name__ == "__main__":
    main()
