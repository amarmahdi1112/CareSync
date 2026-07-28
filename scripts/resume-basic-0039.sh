#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Kept as a separate, deliberately named recovery entry point so ordinary
# startup can never accidentally accept the old retained revision. The release
# orchestrator reopens every prepared artifact and asks the Python contract to
# prove that retained 0039 is still the exact captured source before it removes
# the fence or restores LOGIN.
exec /bin/bash "$ROOT/scripts/basic-release.sh" _resume-0039 "$@"
