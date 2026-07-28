"""Read-only integrity and compatibility checks for the legacy CareSync database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

DATABASE_FILENAME = "caresync.db"
REQUIRED_TABLES = {
    "attendance_sessions",
    "audit_reports",
    "batch_uploads",
    "child_funding",
    "child_violations",
    "children",
    "claim_reports",
    "claims",
    "daycare_violations",
    "emergency_contacts",
    "families",
    "funding_sources",
    "generated_claim_reports",
    "generated_claims",
    "guardians",
    "invoice_allocations",
    "invoice_line_items",
    "invoices",
    "organizations",
    "payments",
    "permissions",
    "persons",
    "provider_settings",
    "rate_schedules",
    "role_permissions",
    "roles",
    "scheduled_attendance",
    "users",
}


def inspect_database(path: Path) -> dict[str, Any]:
    if path.name != DATABASE_FILENAME:
        raise ValueError(f"Database filename must remain {DATABASE_FILENAME!r}")
    if not path.is_file():
        raise FileNotFoundError(path)

    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        schema_rows = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        table_names = {name for name, _ in schema_rows}
        schema_text = "\n".join(f"{name}\0{sql}" for name, sql in schema_rows)

    missing_tables = sorted(REQUIRED_TABLES - table_names)
    unexpected_tables = sorted(table_names - REQUIRED_TABLES)
    return {
        "database_filename": path.name,
        "size_bytes": path.stat().st_size,
        "integrity": integrity,
        "foreign_key_error_count": foreign_key_errors,
        "table_count": len(table_names),
        "missing_tables": missing_tables,
        "unexpected_tables": unexpected_tables,
        "schema_sha256": hashlib.sha256(schema_text.encode("utf-8")).hexdigest(),
        "compatible": integrity == "ok" and not missing_tables,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    report = inspect_database(args.database)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
