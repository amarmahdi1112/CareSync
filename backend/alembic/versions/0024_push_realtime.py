"""Add user-private realtime and push delivery outbox.

Revision ID: 0024_push_realtime
Revises: 0023_atomic_offer_send
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.basic.models import (
    NotificationDelivery,
    PushSubscription,
    UserRealtimeEvent,
    UserRealtimeTicket,
)

revision = "0024_push_realtime"
down_revision = "0023_atomic_offer_send"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    preference_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("user_notification_preferences")
    }
    if "push_enabled" not in preference_columns:
        op.add_column(
            "user_notification_preferences",
            sa.Column(
                "push_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
            ),
        )
    for table_name, constraint_name in (
        ("realtime_tickets", "ck_realtime_tickets_auth_version"),
        (
            "marketplace_realtime_tickets",
            "ck_marketplace_realtime_tickets_auth_version",
        ),
    ):
        columns = {
            column["name"] for column in sa.inspect(bind).get_columns(table_name)
        }
        if "auth_version" in columns:
            continue
        op.add_column(
            table_name,
            sa.Column("auth_version", sa.Integer(), nullable=True),
        )
        op.execute(
            sa.text(
                f'UPDATE "{table_name}" SET auth_version = '
                f'(SELECT users.auth_version FROM users WHERE users.id = "{table_name}".user_id)'
            )
        )
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column("auth_version", existing_type=sa.Integer(), nullable=False)
            batch.create_check_constraint(constraint_name, "auth_version > 0")
    PushSubscription.__table__.create(bind, checkfirst=False)
    NotificationDelivery.__table__.create(bind, checkfirst=False)
    UserRealtimeEvent.__table__.create(bind, checkfirst=False)
    UserRealtimeTicket.__table__.create(bind, checkfirst=False)
    if bind.dialect.name != "postgresql":
        return

    user = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
    organization = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    for table in (
        "notification_push_subscriptions",
        "notification_deliveries",
        "user_realtime_events",
        "user_realtime_tickets",
    ):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')

    op.execute(
        'CREATE POLICY "push_subscriptions_owner_select" '
        'ON "notification_push_subscriptions" FOR SELECT '
        f"USING (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "push_subscriptions_owner_insert" '
        'ON "notification_push_subscriptions" FOR INSERT '
        f"WITH CHECK (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "push_subscriptions_owner_update" '
        'ON "notification_push_subscriptions" FOR UPDATE '
        f"USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "push_subscriptions_address_transfer_select" '
        'ON "notification_push_subscriptions" FOR SELECT '
        "USING (status IN ('active','revoked') "
        "AND (status = 'active' OR delivery_address IS NULL) "
        "AND transport = NULLIF(current_setting('app.push_transfer_transport', true), '') "
        "AND address_digest = NULLIF(current_setting('app.push_transfer_digest', true), ''))"
    )
    op.execute(
        'CREATE POLICY "push_subscriptions_address_transfer" '
        'ON "notification_push_subscriptions" FOR UPDATE '
        "USING (status = 'active' "
        "AND transport = NULLIF(current_setting('app.push_transfer_transport', true), '') "
        "AND address_digest = NULLIF(current_setting('app.push_transfer_digest', true), '')) "
        "WITH CHECK (status = 'revoked' AND delivery_address IS NULL "
        "AND web_push_public_key IS NULL AND web_push_auth_secret IS NULL "
        "AND transport = NULLIF(current_setting('app.push_transfer_transport', true), '') "
        "AND address_digest = NULLIF(current_setting('app.push_transfer_digest', true), ''))"
    )
    op.execute(
        'CREATE POLICY "notification_deliveries_owner_select" '
        'ON "notification_deliveries" FOR SELECT '
        f"USING (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "notification_deliveries_context_insert" '
        'ON "notification_deliveries" FOR INSERT '
        f"WITH CHECK (user_id = {user} OR organization_id = {organization})"
    )
    op.execute(
        'CREATE POLICY "notification_deliveries_owner_update" '
        'ON "notification_deliveries" FOR UPDATE '
        f"USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    transfer_subscription = (
        "EXISTS (SELECT 1 FROM public.notification_push_subscriptions AS transfer "
        "WHERE transfer.id = subscription_id AND transfer.status = 'active' "
        "AND transfer.transport = "
        "NULLIF(current_setting('app.push_transfer_transport', true), '') "
        "AND transfer.address_digest = "
        "NULLIF(current_setting('app.push_transfer_digest', true), ''))"
    )
    op.execute(
        'CREATE POLICY "notification_deliveries_address_transfer_select" '
        'ON "notification_deliveries" FOR SELECT '
        f"USING ({transfer_subscription})"
    )
    op.execute(
        'CREATE POLICY "notification_deliveries_address_transfer_update" '
        'ON "notification_deliveries" FOR UPDATE '
        f"USING ({transfer_subscription}) "
        "WITH CHECK (status = 'cancelled' AND cancelled_at IS NOT NULL "
        "AND claimed_at IS NULL AND lease_expires_at IS NULL "
        f"AND {transfer_subscription})"
    )
    op.execute(
        'CREATE POLICY "user_realtime_events_owner_select" '
        'ON "user_realtime_events" FOR SELECT '
        f"USING (user_id = {user})"
    )
    op.execute(
        'CREATE POLICY "user_realtime_events_context_insert" '
        'ON "user_realtime_events" FOR INSERT '
        f"WITH CHECK (user_id = {user} OR organization_id = {organization})"
    )
    op.execute(
        'CREATE POLICY "user_realtime_tickets_owner" '
        'ON "user_realtime_tickets" FOR ALL '
        f"USING (user_id = {user}) WITH CHECK (user_id = {user})"
    )
    op.execute(
        """
        CREATE FUNCTION public.user_notification_enqueue_trigger() RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = pg_catalog
        AS $trigger$
        DECLARE
          actor_user_id uuid :=
            NULLIF(pg_catalog.current_setting('app.current_user_id', true), '')::uuid;
          actor_organization_id uuid :=
            NULLIF(pg_catalog.current_setting('app.current_organization_id', true), '')::uuid;
        BEGIN
          IF NEW.user_id IS DISTINCT FROM actor_user_id
             AND (NEW.organization_id IS NULL
                  OR NEW.organization_id IS DISTINCT FROM actor_organization_id)
          THEN
            RAISE insufficient_privilege USING MESSAGE = 'Notification context unavailable';
          END IF;

          PERFORM pg_catalog.set_config(
            'app.current_user_id', NEW.user_id::text, true
          );
          BEGIN
            INSERT INTO public.user_realtime_events
              (id, user_id, organization_id, event_type, entity_type, entity_id,
               occurred_at, payload)
            VALUES
              (NEW.id, NEW.user_id, NEW.organization_id, 'notification.created',
               'notification', NEW.id, NEW.created_at,
               pg_catalog.jsonb_build_object('source', 'notification_ledger'))
            ON CONFLICT (id) DO NOTHING;

            INSERT INTO public.notification_deliveries
              (id, notification_id, subscription_id, user_id, organization_id, payload,
               status, attempt_count, available_at, created_at, updated_at)
            SELECT
              pg_catalog.gen_random_uuid(), NEW.id, subscription.id,
              NEW.user_id, NEW.organization_id,
              pg_catalog.jsonb_build_object(
                'type', 'notification',
                'notification_id', NEW.id::text,
                'category', NEW.category,
                'severity', NEW.severity
              ),
              CASE
                WHEN COALESCE(preference.push_enabled, true)
                 AND CASE NEW.category
                   WHEN 'hiring' THEN COALESCE(preference.hiring_enabled, true)
                   WHEN 'credential' THEN COALESCE(preference.credential_enabled, true)
                   WHEN 'assignment' THEN COALESCE(preference.assignment_enabled, true)
                   WHEN 'operations' THEN COALESCE(preference.operations_enabled, true)
                   ELSE true
                 END
                THEN 'pending' ELSE 'suppressed'
              END,
              0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM public.notification_push_subscriptions AS subscription
            LEFT JOIN public.user_notification_preferences AS preference
              ON preference.user_id = NEW.user_id
            WHERE subscription.user_id = NEW.user_id
              AND subscription.status = 'active'
              AND (
                NEW.organization_id IS NULL
                OR subscription.organization_id IS NULL
                OR subscription.organization_id = NEW.organization_id
              )
            ON CONFLICT (notification_id, subscription_id) DO NOTHING;
          EXCEPTION WHEN OTHERS THEN
            PERFORM pg_catalog.set_config(
              'app.current_user_id', COALESCE(actor_user_id::text, ''), true
            );
            RAISE;
          END;
          PERFORM pg_catalog.set_config(
            'app.current_user_id', COALESCE(actor_user_id::text, ''), true
          );
          RETURN NEW;
        END
        $trigger$
        """
    )
    op.execute(
        "CREATE TRIGGER user_notifications_push_realtime "
        "AFTER INSERT ON public.user_notifications "
        "FOR EACH ROW EXECUTE FUNCTION public.user_notification_enqueue_trigger()"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.user_notification_enqueue_trigger() FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caresync_basic_app') THEN
            GRANT SELECT, INSERT, UPDATE ON TABLE notification_push_subscriptions,
              notification_deliveries, user_realtime_tickets TO caresync_basic_app;
            GRANT SELECT, INSERT ON TABLE user_realtime_events TO caresync_basic_app;
            GRANT USAGE, SELECT ON SEQUENCE user_realtime_events_sequence_id_seq
              TO caresync_basic_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS user_notifications_push_realtime ON user_notifications")
        op.execute("DROP FUNCTION IF EXISTS public.user_notification_enqueue_trigger()")
    UserRealtimeTicket.__table__.drop(bind, checkfirst=False)
    UserRealtimeEvent.__table__.drop(bind, checkfirst=False)
    NotificationDelivery.__table__.drop(bind, checkfirst=False)
    PushSubscription.__table__.drop(bind, checkfirst=False)
    for table_name, constraint_name in (
        ("realtime_tickets", "ck_realtime_tickets_auth_version"),
        (
            "marketplace_realtime_tickets",
            "ck_marketplace_realtime_tickets_auth_version",
        ),
    ):
        columns = {
            column["name"] for column in sa.inspect(bind).get_columns(table_name)
        }
        if "auth_version" not in columns:
            continue
        with op.batch_alter_table(table_name) as batch:
            batch.drop_constraint(constraint_name, type_="check")
            batch.drop_column("auth_version")
    preference_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("user_notification_preferences")
    }
    if "push_enabled" in preference_columns:
        op.drop_column("user_notification_preferences", "push_enabled")
