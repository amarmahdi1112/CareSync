#!/usr/bin/env python3
"""Privileged, fail-closed seeding of 0033 synthetic source attestations.

This command is intentionally unavailable through the API and cannot run as
``caresync_basic_app``.  It accepts only the exact disposable test posture
enforced by :class:`Settings` and attests existing rows for one allowlisted
organization; it does not create or alter operational childcare data.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.basic.models import (
    BillingSandboxSourceAttestation,
    Child,
    Enrollment,
    Facility,
    Family,
    Guardian,
    Organization,
    OrganizationMembership,
    Program,
    Role,
)
from app.core.config import Settings
from app.db.session import Database


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attest current rows in one disposable synthetic billing tenant"
    )
    parser.add_argument("--organization-id", type=UUID, required=True)
    parser.add_argument("--actor-user-id", type=UUID, required=True)
    return parser.parse_args()


def _fail(message: str) -> None:
    raise SystemExit(f"Refusing 0033 source attestation: {message}")


def main() -> None:
    arguments = _arguments()
    settings = Settings()
    organization_id: UUID = arguments.organization_id
    actor_user_id: UUID = arguments.actor_user_id
    if settings.billing_mode != "sandbox":
        _fail("BILLING_MODE must be sandbox")
    if not settings.billing_sandbox_target_is_disposable:
        _fail("target is not an explicitly attested disposable test database")
    if not settings.billing_organization_is_allowlisted(organization_id):
        _fail("organization is not in BILLING_SANDBOX_ORGANIZATION_IDS")

    database = Database(settings)
    try:
        if not database.has_billing_ledger():
            _fail("the complete 0033 catalog capability is unavailable")
        with database.session_factory() as session, session.begin():
            current_user = str(session.scalar(text("SELECT current_user")))
            if current_user == "caresync_basic_app":
                _fail("runtime role has no source-attestation authority")
            if settings.database_type == "postgres" and not bool(
                session.scalar(
                    text(
                        "SELECT has_table_privilege(current_user,"
                        "'public.billing_sandbox_source_attestations','INSERT')"
                    )
                )
            ):
                _fail("database identity lacks privileged attestation INSERT")
            if settings.database_type == "postgres":
                # Freeze actor authority and every source relation before the
                # first eligibility read. SHARE ROW EXCLUSIVE conflicts with
                # ordinary source/authority writes and concurrent seeders.
                session.execute(
                    text(
                        "LOCK TABLE public.organizations,public.organization_memberships,"
                        "public.roles,public.families,public.guardians,public.children,"
                        "public.enrollments,public.facilities,public.facility_programs "
                        "IN SHARE ROW EXCLUSIVE MODE"
                    )
                )

            organization = session.scalar(
                select(Organization).where(Organization.id == organization_id)
            )
            leadership = session.scalar(
                select(OrganizationMembership.id)
                .join(Role, Role.id == OrganizationMembership.role_id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id == actor_user_id,
                    OrganizationMembership.status == "active",
                    Role.organization_id == organization_id,
                    Role.key.in_(("owner", "administrator")),
                )
            )
            if organization is None or leadership is None:
                _fail("organization or active leadership actor does not exist")

            if settings.database_type == "postgres":
                session.execute(
                    text("SELECT set_config('app.billing_seed_mode','synthetic_fixture',true)")
                )
                session.execute(
                    text("SELECT set_config('app.current_organization_id',:value,true)"),
                    {"value": str(organization_id)},
                )
                session.execute(
                    text("SELECT set_config('app.current_user_id',:value,true)"),
                    {"value": str(actor_user_id)},
                )

            sources: list[tuple[str, UUID]] = [("organization", organization_id)]
            for source_type, model in (
                ("family", Family),
                ("guardian", Guardian),
                ("child", Child),
                ("enrollment", Enrollment),
                ("facility", Facility),
                ("program", Program),
            ):
                sources.extend(
                    (source_type, value)
                    for value in session.scalars(
                        select(model.id).where(model.organization_id == organization_id)
                    )
                )

            existing = set(
                session.execute(
                    select(
                        BillingSandboxSourceAttestation.source_type,
                        BillingSandboxSourceAttestation.source_id,
                    ).where(BillingSandboxSourceAttestation.organization_id == organization_id)
                )
            )
            now = datetime.now(UTC)
            inserted = 0
            # The organization root must flush before dependent attestations so
            # the database guard can prove their synthetic boundary.
            for source_type, source_id in sources:
                if (source_type, source_id) in existing:
                    continue
                session.add(
                    BillingSandboxSourceAttestation(
                        id=uuid4(),
                        organization_id=organization_id,
                        source_type=source_type,
                        source_id=source_id,
                        marker="TEST_SYNTHETIC_ONLY",
                        reason_code="disposable_test_fixture",
                        attested_by_user_id=actor_user_id,
                        attested_at=now,
                    )
                )
                session.flush()
                inserted += 1
        print(
            f"0033 synthetic source attestation complete: inserted={inserted} "
            f"total_sources={len(sources)} organization={organization_id}"
        )
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
