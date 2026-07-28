"""Runnable, disabled-by-default push outbox worker."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from sqlalchemy import select

from app.basic.models import User
from app.basic.push import DeliveryBatchResult, build_push_provider, deliver_pending_push_for_user
from app.basic.security import set_rls_user
from app.core.config import Settings
from app.db.session import Database


def run_once(
    database: Database,
    settings: Settings,
    *,
    batch_size: int = 50,
) -> dict[str, int | bool]:
    provider = build_push_provider(settings)
    if provider is None:
        return {
            "provider_disabled": True,
            "users_checked": 0,
            "selected": 0,
            "accepted": 0,
            "sent": 0,
            "retried": 0,
            "dead": 0,
            "invalidated": 0,
            "errors": 0,
        }
    with database.session_factory() as session:
        user_ids = list(
            session.scalars(select(User.id).where(User.is_active.is_(True)).order_by(User.id))
        )
        session.rollback()
    totals = {
        "provider_disabled": False,
        "users_checked": len(user_ids),
        "selected": 0,
        "accepted": 0,
        "sent": 0,
        "retried": 0,
        "dead": 0,
        "invalidated": 0,
        "errors": 0,
    }
    for user_id in user_ids:
        try:
            with database.session_factory() as session:
                set_rls_user(session, user_id)
                result: DeliveryBatchResult = deliver_pending_push_for_user(
                    session,
                    user_id=user_id,
                    provider=provider,
                    limit=batch_size,
                )
        except Exception:
            totals["errors"] += 1
            continue
        for key, value in asdict(result).items():
            if key == "provider_disabled":
                continue
            totals[key] += int(value)
    return totals


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CareSync push notification outbox worker")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Process one bounded pass and exit")
    mode.add_argument(
        "--poll",
        type=float,
        metavar="SECONDS",
        help="Continuously poll; remote delivery still requires explicit provider configuration",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.batch_size < 1 or args.batch_size > 250:
        raise SystemExit("--batch-size must be between 1 and 250")
    if args.poll is not None and not 1 <= args.poll <= 3600:
        raise SystemExit("--poll must be between 1 and 3600 seconds")
    settings = Settings()
    database = Database(settings)
    try:
        database.assert_basic_runtime_identity()
        while True:
            result = run_once(database, settings, batch_size=args.batch_size)
            print(json.dumps(result, sort_keys=True), flush=True)
            if args.once or result["provider_disabled"]:
                return 0
            time.sleep(args.poll)
    except KeyboardInterrupt:
        return 0
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
