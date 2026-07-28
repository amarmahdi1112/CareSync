#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "CareSync Rebuild now defaults to the clean Basic platform on PostgreSQL 5434."
exec "$ROOT/scripts/start-basic.sh" "$@"
