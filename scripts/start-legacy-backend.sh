#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${CARESYNC_REBUILD_RUNTIME:-$HOME/Library/Application Support/CareSync Private Rebuild}"
PGDATA="${CARESYNC_REBUILD_PGDATA:-$RUNTIME_DIR/postgres-data}"
PG_BIN="${CARESYNC_PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
VENV_PATH="${CARESYNC_REBUILD_VENV:-$HOME/Library/Caches/CareSync-Private-Rebuild/.venv}"

mkdir -p "$RUNTIME_DIR/logs" "$RUNTIME_DIR/pids"
if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
  echo "The retained legacy PostgreSQL clone is missing at: $PGDATA" >&2
  exit 1
fi

if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p 5433 -q; then
  "$PG_BIN/pg_ctl" -D "$PGDATA" -l "$RUNTIME_DIR/logs/postgres.log" \
    -o "-p 5433 -h 127.0.0.1" start
fi

while IFS= read -r pid; do
  [[ -n "$pid" ]] || continue
  kill "$pid" 2>/dev/null || true
done < <(lsof -nP -tiTCP:3002 -sTCP:LISTEN 2>/dev/null || true)

(
  cd "$ROOT/backend"
  CARESYNC_VENV_PATH="$VENV_PATH" \
  APP_NAME="CareSync Legacy Compatibility" \
  PORT=3002 \
  DATABASE_TYPE=postgres \
  DATABASE_HOST=127.0.0.1 \
  DATABASE_PORT=5433 \
  DATABASE_NAME=caresync \
  DATABASE_READ_ONLY=false \
  ENABLE_ADVANCED_ROUTES=true \
    nohup ./scripts/uv.sh run uvicorn app.main:app --host 127.0.0.1 --port 3002 \
      >"$RUNTIME_DIR/logs/backend.log" 2>&1 &
  echo $! >"$RUNTIME_DIR/pids/backend.pid"
)

echo "Legacy compatibility backend started on 3002 against the retained 5433 clone."
echo "Run ./scripts/start-rebuild.sh to return to CareSync Basic."
