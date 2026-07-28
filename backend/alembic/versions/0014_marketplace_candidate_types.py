"""Add certified educator and student marketplace paths.

Revision ID: 0014_marketplace_candidate_types
Revises: 0013_marketplace_onboarding
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_marketplace_candidate_types"
down_revision = "0013_marketplace_onboarding"
branch_labels = None
depends_on = None

PROFILE_COLUMNS = (
    ("candidate_type", sa.String(30)),
    ("institution", sa.String(180)),
    ("program", sa.String(180)),
    ("expected_graduation_date", sa.Date()),
    ("onboarding_completed_at", sa.DateTime(timezone=True)),
)
ATS_COLUMNS = PROFILE_COLUMNS[:4]


def _constraints(table_name: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_check_constraints(table_name)
        if item.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    existing = {item["name"] for item in sa.inspect(bind).get_columns("marketplace_profiles")}
    missing = [(name, type_) for name, type_ in PROFILE_COLUMNS if name not in existing]
    profile_constraints = _constraints("marketplace_profiles")
    with op.batch_alter_table("marketplace_profiles") as batch:
        for name, type_ in missing:
            batch.add_column(sa.Column(name, type_, nullable=True))
        if "ck_marketplace_profiles_candidate_type" not in profile_constraints:
            batch.create_check_constraint(
                "ck_marketplace_profiles_candidate_type",
                "candidate_type IS NULL OR candidate_type IN ('certified_educator','student')",
            )
        if "ck_marketplace_profiles_student_no_certificate" not in profile_constraints:
            batch.create_check_constraint(
                "ck_marketplace_profiles_student_no_certificate",
                "candidate_type <> 'student' OR (certification_type IS NULL AND "
                "certification_number IS NULL AND certification_expiry_date IS NULL AND "
                "certification_provenance IS NULL)",
            )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("marketplace_profiles")}
    if "ix_marketplace_profiles_candidate_type" not in indexes:
        op.create_index(
            "ix_marketplace_profiles_candidate_type", "marketplace_profiles", ["candidate_type"]
        )
    ats_existing = {item["name"] for item in sa.inspect(bind).get_columns("ats_candidates")}
    ats_constraints = _constraints("ats_candidates")
    with op.batch_alter_table("ats_candidates") as batch:
        for name, type_ in ATS_COLUMNS:
            if name not in ats_existing:
                batch.add_column(sa.Column(name, type_, nullable=True))
        if "ck_ats_candidates_candidate_type" not in ats_constraints:
            batch.create_check_constraint(
                "ck_ats_candidates_candidate_type",
                "candidate_type IS NULL OR candidate_type IN ('certified_educator','student')",
            )
    state_constraints = _constraints("marketplace_onboarding_states")
    with op.batch_alter_table("marketplace_onboarding_states") as batch:
        if "ck_marketplace_onboarding_step" in state_constraints:
            batch.drop_constraint("ck_marketplace_onboarding_step", type_="check")
        batch.create_check_constraint(
            "ck_marketplace_onboarding_step",
            "current_step IN ('candidate_type','certificate','student_details',"
            "'work_experience','review','complete')",
        )
    op.execute(
        "UPDATE marketplace_onboarding_states SET current_step = 'candidate_type' "
        "WHERE status = 'not_started'"
    )


def downgrade() -> None:
    bind = op.get_bind()
    ats_existing = {item["name"] for item in sa.inspect(bind).get_columns("ats_candidates")}
    with op.batch_alter_table("ats_candidates") as batch:
        if "ck_ats_candidates_candidate_type" in _constraints("ats_candidates"):
            batch.drop_constraint("ck_ats_candidates_candidate_type", type_="check")
        for name, _ in ATS_COLUMNS:
            if name in ats_existing:
                batch.drop_column(name)
    op.execute(
        "UPDATE marketplace_onboarding_states SET current_step = 'certificate' "
        "WHERE current_step IN ('candidate_type','student_details')"
    )
    with op.batch_alter_table("marketplace_onboarding_states") as batch:
        batch.drop_constraint("ck_marketplace_onboarding_step", type_="check")
        batch.create_check_constraint(
            "ck_marketplace_onboarding_step",
            "current_step IN ('certificate','work_experience','review','complete')",
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("marketplace_profiles")}
    if "ix_marketplace_profiles_candidate_type" in indexes:
        op.drop_index("ix_marketplace_profiles_candidate_type", table_name="marketplace_profiles")
    existing = {item["name"] for item in sa.inspect(bind).get_columns("marketplace_profiles")}
    with op.batch_alter_table("marketplace_profiles") as batch:
        if "ck_marketplace_profiles_student_no_certificate" in _constraints("marketplace_profiles"):
            batch.drop_constraint("ck_marketplace_profiles_student_no_certificate", type_="check")
        if "ck_marketplace_profiles_candidate_type" in _constraints("marketplace_profiles"):
            batch.drop_constraint("ck_marketplace_profiles_candidate_type", type_="check")
        for name, _ in PROFILE_COLUMNS:
            if name in existing:
                batch.drop_column(name)
