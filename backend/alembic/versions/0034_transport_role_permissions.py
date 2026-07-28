"""Backfill transport-registry permissions for existing organization leaders.

Revision ID: 0034_transport_role_permissions
Revises: 0033_billing_ledger
Create Date: 2026-07-22

New organizations already receive these permissions from the application role
templates.  This revision closes the upgrade gap for owner and administrator
roles that were created before the transport registry existed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "0034_transport_role_permissions"
down_revision = "0033_billing_ledger"
branch_labels = None
depends_on = None

ROLE_PERMISSION_BACKUP_TABLE = "billing_0033_role_permission_backups"
TRANSPORT_PERMISSIONS = ("transport:read", "transport:manage")
LEADER_ROLE_KEYS = ("owner", "administrator")


def _permission_list(value: Any) -> list[str]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if decoded is None:
        return []
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise RuntimeError("0034 refused invalid role permission data")
    return decoded


def _write_permissions(
    bind: sa.engine.Connection,
    *,
    role_id: Any,
    permissions: Iterable[str],
) -> None:
    encoded = json.dumps(sorted(set(permissions)))
    statement = (
        "UPDATE roles SET permissions=CAST(:permissions AS json) WHERE id=:role_id"
        if bind.dialect.name == "postgresql"
        else "UPDATE roles SET permissions=:permissions WHERE id=:role_id"
    )
    bind.execute(sa.text(statement), {"permissions": encoded, "role_id": role_id})


def _backfill_transport_permissions(bind: sa.engine.Connection) -> None:
    """Add permissions to roles captured by the immediately preceding release."""

    roles = bind.execute(
        sa.text(
            "SELECT role.id,role.key,role.permissions FROM roles AS role "
            f"JOIN {ROLE_PERMISSION_BACKUP_TABLE} AS backup ON backup.role_id=role.id "
            "WHERE role.key IN ('owner','administrator') "
            "ORDER BY role.organization_id,role.id"
        )
    ).mappings()
    for role in roles:
        existing = set(_permission_list(role["permissions"]))
        _write_permissions(
            bind,
            role_id=role["id"],
            permissions=existing.union(TRANSPORT_PERMISSIONS),
        )


def _remove_attributed_transport_permissions(bind: sa.engine.Connection) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT role.id,role.permissions,backup.permissions AS backup_permissions "
            f"FROM {ROLE_PERMISSION_BACKUP_TABLE} AS backup "
            "JOIN roles AS role ON role.id=backup.role_id "
            "WHERE role.key IN ('owner','administrator') ORDER BY role.id"
        )
    ).mappings()
    for row in rows:
        permissions = set(_permission_list(row["permissions"]))
        original_permissions = set(_permission_list(row["backup_permissions"]))
        for permission in TRANSPORT_PERMISSIONS:
            if permission not in original_permissions:
                permissions.discard(permission)
        _write_permissions(bind, role_id=row["id"], permissions=permissions)


def _set_postgres_role_rls(*, enabled: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    action = "ENABLE" if enabled else "DISABLE"
    op.execute(f"ALTER TABLE public.roles {action} ROW LEVEL SECURITY")
    if enabled:
        op.execute("ALTER TABLE public.roles FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    bind = op.get_bind()
    _set_postgres_role_rls(enabled=False)
    try:
        _backfill_transport_permissions(bind)
    finally:
        _set_postgres_role_rls(enabled=True)


def downgrade() -> None:
    bind = op.get_bind()
    _set_postgres_role_rls(enabled=False)
    try:
        _remove_attributed_transport_permissions(bind)
    finally:
        _set_postgres_role_rls(enabled=True)
