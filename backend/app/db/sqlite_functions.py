"""Deterministic SQLite functions shared by runtime and Alembic connections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def caresync_local_date(timestamp_value: Any, timezone_name: Any) -> str:
    """Return an instant's IANA-local date; naive SQLite values mean UTC storage."""

    if not isinstance(timestamp_value, (str, datetime)):
        raise ValueError("timestamp is required")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("timezone is required")
    try:
        value = (
            timestamp_value
            if isinstance(timestamp_value, datetime)
            else datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        )
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=UTC)
        timezone = ZoneInfo(timezone_name)
    except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
        raise ValueError("invalid timestamp or IANA timezone") from error
    return value.astimezone(timezone).date().isoformat()


def register_sqlite_functions(dbapi_connection: Any) -> None:
    """Install the exact deterministic functions required by SQLite guards."""

    dbapi_connection.create_function(
        "caresync_local_date",
        2,
        caresync_local_date,
        deterministic=True,
    )
