#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/basic-runtime.sh
source "$ROOT/scripts/lib/basic-runtime.sh"

basic_reexec_with_state_change_lock "$0" "$@"

# Stopping is allowed while a release fence exists; stopping must never remove
# or rewrite that fence. Prove the protected cluster identity before signaling
# PostgreSQL, and refuse an indeterminate half-started server.
basic_require_runtime_layout
POSTGRES_READY=false
if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
  basic_verify_retained_identity
  POSTGRES_READY=true
elif "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  basic_fail \
    "CareSync PostgreSQL is running but not ready enough to prove identity; refusing to stop it"
  exit 1
fi

basic_quiesce_application

if [[ "$POSTGRES_READY" == "true" ]]; then
  basic_assert_no_database_clients
  basic_stop_retained_postgres
  if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_fail "CareSync retained PostgreSQL still reports ready after stop"
    exit 1
  fi
fi

echo "CareSync Basic services stopped. Original 5432 and legacy clone 5433 were not changed."
