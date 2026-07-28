#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${CARESYNC_REBUILD_RUNTIME:-$HOME/Library/Application Support/CareSync Private Rebuild}"
PGDATA="${CARESYNC_REBUILD_PGDATA:-$RUNTIME_DIR/postgres-data}"
PG_BIN="${CARESYNC_PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"

pid_file="$RUNTIME_DIR/pids/backend.pid"
if [[ -f "$pid_file" ]]; then
  pid="$(<"$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
  fi
  rm -f "$pid_file"
fi

if [[ -f "$PGDATA/PG_VERSION" ]] && "$PG_BIN/pg_isready" -h 127.0.0.1 -p 5433 -q; then
  "$PG_BIN/pg_ctl" -D "$PGDATA" stop -m fast
fi

echo "Retained legacy backend and 5433 clone stopped. Original 5432 and Basic 5434 were not changed."
