"""Add user-owned notification ledger and fixed preferences.

Revision ID: 0021_user_notifications
Revises: 0020_hiring_contracts
Create Date: 2026-07-16
"""

from __future__ import annotations

from alembic import op
from app.basic.models import UserNotification, UserNotificationPreference

revision = "0021_user_notifications"
down_revision = "0020_hiring_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    UserNotification.__table__.create(bind, checkfirst=True)
    UserNotificationPreference.__table__.create(bind, checkfirst=True)
    if bind.dialect.name != "postgresql":
        return
    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    organization = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    for table in ("user_notifications", "user_notification_preferences"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "user_notifications_read" ON "user_notifications" FOR SELECT '
        f"USING (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "user_notifications_update" ON "user_notifications" FOR UPDATE '
        f"USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "user_notifications_insert" ON "user_notifications" FOR INSERT '
        f"WITH CHECK (user_id = {user} OR organization_id = {organization})"
    )
    op.execute(
        'CREATE POLICY "user_notification_preferences_owner" '
        'ON "user_notification_preferences" FOR ALL '
        f"USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE user_notifications,
              user_notification_preferences TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    UserNotificationPreference.__table__.drop(op.get_bind(), checkfirst=True)
    UserNotification.__table__.drop(op.get_bind(), checkfirst=True)
