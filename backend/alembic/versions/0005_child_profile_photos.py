"""Add tenant-protected normalized child profile photos.

Revision ID: 0005_child_profile_photos
Revises: 0004_staff_access
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_child_profile_photos"
down_revision = "0004_staff_access"
branch_labels = None
depends_on = None


def _create_rls() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    org_setting = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    op.execute('ALTER TABLE "child_profile_photos" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "child_profile_photos" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "child_profile_photos_tenant" ON "child_profile_photos" '
        f"USING (organization_id = {org_setting}) "
        f"WITH CHECK (organization_id = {org_setting})"
    )


def upgrade() -> None:
    op.create_table(
        "child_profile_photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("image_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg','image/webp')",
            name="ck_child_profile_photos_content_type",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_child_profile_photos_size"),
        sa.CheckConstraint(
            "width > 0 AND height > 0",
            name="ck_child_profile_photos_dimensions",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "child_id"],
            ["children.organization_id", "children.id"],
            name="fk_child_profile_photos_org_child",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_child_profile_photos_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "child_id",
            name="uq_child_profile_photos_org_child",
        ),
    )
    op.create_index(
        op.f("ix_child_profile_photos_organization_id"),
        "child_profile_photos",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_child_profile_photos_child_id"),
        "child_profile_photos",
        ["child_id"],
        unique=False,
    )
    _create_rls()


def downgrade() -> None:
    op.drop_table("child_profile_photos")
