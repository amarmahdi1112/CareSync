#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_PROJECT_ENVIRONMENT="${CARESYNC_VENV_PATH:-$HOME/Library/Caches/CareSync-Private-Rebuild/.venv}"
export PYTHONPATH="$project_root${PYTHONPATH:+:$PYTHONPATH}"

cd "$project_root"
# External APFS/exFAT volumes can create AppleDouble files beside edited Python
# migrations. Alembic treats every ``*.py`` in versions as executable source,
# so a ``._*.py`` resource fork can brick startup before env.py is reached.
find "$project_root/alembic/versions" -maxdepth 1 -type f -name '._*.py' -delete
exec uv "$@"
