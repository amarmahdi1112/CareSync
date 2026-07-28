#!/usr/bin/env bash
set -euo pipefail

# The backend lives one level below the rebuild root. Clean the whole rebuild,
# because macOS writes AppleDouble sidecars beside frontend and documentation
# files on the T7 volume as well as beside Python files.
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
find "$project_root" -type f -name '._*' -delete
