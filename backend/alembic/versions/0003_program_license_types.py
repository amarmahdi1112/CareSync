"""Constrain facility programs to the Daycare and OSC licence categories.

Revision ID: 0003_program_license_types
Revises: 0002_verification_foundation
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_program_license_types"
down_revision = "0002_verification_foundation"
branch_labels = None
depends_on = None

DAYCARE = "daycare"
OUT_OF_SCHOOL_CARE = "out_of_school_care"
CANONICAL_TYPES = (DAYCARE, OUT_OF_SCHOOL_CARE)
DAYCARE_VARIANTS = (
    "child care",
    "childcare",
    "day care",
    DAYCARE,
)
OUT_OF_SCHOOL_CARE_VARIANTS = (
    "oosc",
    "osc",
    "out of school",
    "out of school care",
    "out-of-school care",
    "out-of-school-care",
    OUT_OF_SCHOOL_CARE,
)


def _set_postgres_rls(*, enabled: bool) -> None:
    """Keep the existing tenant policy while permitting an owner-run backfill."""

    if op.get_bind().dialect.name != "postgresql":
        return
    if enabled:
        op.execute('ALTER TABLE "facility_programs" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "facility_programs" FORCE ROW LEVEL SECURITY')
    else:
        op.execute('ALTER TABLE "facility_programs" DISABLE ROW LEVEL SECURITY')


def _programs_table() -> sa.TableClause:
    return sa.table(
        "facility_programs",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("facility_id", sa.Uuid()),
        sa.column("program_type", sa.String(length=100)),
    )


def _normalize_known_variants(programs: sa.TableClause) -> None:
    normalized_type = sa.func.lower(sa.func.trim(programs.c.program_type))
    op.execute(
        programs.update()
        .where(normalized_type.in_(DAYCARE_VARIANTS))
        .values(program_type=DAYCARE)
    )
    op.execute(
        programs.update()
        .where(normalized_type.in_(OUT_OF_SCHOOL_CARE_VARIANTS))
        .values(program_type=OUT_OF_SCHOOL_CARE)
    )


def _assert_all_types_are_known(programs: sa.TableClause) -> None:
    invalid = (
        op.get_bind()
        .execute(
            sa.select(programs.c.id, programs.c.program_type)
            .where(
                sa.or_(
                    programs.c.program_type.is_(None),
                    programs.c.program_type.not_in(CANONICAL_TYPES),
                )
            )
            .order_by(programs.c.id)
            .limit(10)
        )
        .mappings()
        .all()
    )
    if not invalid:
        return
    examples = ", ".join(
        f"{row['id']}={row['program_type']!r}" for row in invalid
    )
    raise RuntimeError(
        "Program licence migration cannot continue because existing program_type values "
        f"cannot be classified safely ({examples}). Set each row to 'daycare' or "
        "'out_of_school_care', then rerun the migration; no rows were deleted or merged."
    )


def _assert_one_type_per_facility(programs: sa.TableClause) -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.select(
                programs.c.organization_id,
                programs.c.facility_id,
                programs.c.program_type,
                sa.func.count().label("row_count"),
            )
            .group_by(
                programs.c.organization_id,
                programs.c.facility_id,
                programs.c.program_type,
            )
            .having(sa.func.count() > 1)
            .limit(10)
        )
        .mappings()
        .all()
    )
    if not duplicates:
        return
    examples = ", ".join(
        f"organization={row['organization_id']} facility={row['facility_id']} "
        f"type={row['program_type']} rows={row['row_count']}"
        for row in duplicates
    )
    raise RuntimeError(
        "Program licence migration cannot continue because duplicate facility program "
        f"types remain after normalization ({examples}). Resolve each facility to one "
        "row per licence type before rerunning; no rows were deleted or merged."
    )


def upgrade() -> None:
    programs = _programs_table()
    _set_postgres_rls(enabled=False)
    try:
        _normalize_known_variants(programs)
        _assert_all_types_are_known(programs)
        _assert_one_type_per_facility(programs)
    finally:
        _set_postgres_rls(enabled=True)

    with op.batch_alter_table("facility_programs") as batch_op:
        batch_op.alter_column(
            "program_type",
            existing_type=sa.String(length=100),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_programs_program_type",
            "program_type IN ('daycare','out_of_school_care')",
        )
        batch_op.create_unique_constraint(
            "uq_programs_facility_type",
            ["organization_id", "facility_id", "program_type"],
        )


def downgrade() -> None:
    with op.batch_alter_table("facility_programs") as batch_op:
        batch_op.drop_constraint("uq_programs_facility_type", type_="unique")
        batch_op.drop_constraint("ck_programs_program_type", type_="check")
        batch_op.alter_column(
            "program_type",
            existing_type=sa.String(length=100),
            nullable=True,
        )
