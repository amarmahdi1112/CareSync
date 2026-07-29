#!/usr/bin/env bash
#
# Build the immutable CareSync production release consumed by the restricted
# server-side deploy receiver. The frontend must already be built; this script
# packages only deployable source/assets and deliberately excludes local state.

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"

die() {
  printf 'build-release: %s\n' "$*" >&2
  exit 1
}

[[ $# -eq 2 ]] || die "usage: $0 OUTPUT_TAR_GZ REVISION"

OUTPUT_PATH="$1"
REVISION="$2"
PRODUCTION_ORIGIN="${PRODUCTION_ORIGIN:-}"

[[ "${REVISION}" =~ ^[0-9a-f]{40}$ ]] \
  || die "REVISION must be a lowercase 40-character Git commit SHA"
[[ -n "${PRODUCTION_ORIGIN}" ]] || die "PRODUCTION_ORIGIN is required"

NORMALIZED_ORIGIN="$(
  python3 - "${PRODUCTION_ORIGIN}" <<'PY'
import sys
from urllib.parse import urlsplit

value = sys.argv[1]
if value != value.strip() or any(character.isspace() for character in value):
    raise SystemExit("PRODUCTION_ORIGIN must not contain whitespace")

parsed = urlsplit(value)
if (
    parsed.scheme != "https"
    or not parsed.hostname
    or parsed.username is not None
    or parsed.password is not None
    or parsed.query
    or parsed.fragment
    or parsed.path not in {"", "/"}
):
    raise SystemExit(
        "PRODUCTION_ORIGIN must be an absolute HTTPS origin without credentials, "
        "a path, query, or fragment"
    )

try:
    parsed.port
except ValueError as error:
    raise SystemExit(f"PRODUCTION_ORIGIN has an invalid port: {error}") from error

print(value.rstrip("/"))
PY
)" || die "invalid PRODUCTION_ORIGIN"

OUTPUT_PATH="$(
  python3 - "${OUTPUT_PATH}" <<'PY'
import os
import sys

print(os.path.abspath(os.path.expanduser(sys.argv[1])))
PY
)"

case "${OUTPUT_PATH}" in
  "${REPOSITORY_ROOT}"/*)
    die "OUTPUT_TAR_GZ must be outside the repository"
    ;;
esac

readonly ACTUAL_REVISION="$(git -C "${REPOSITORY_ROOT}" rev-parse HEAD)"
[[ "${ACTUAL_REVISION}" == "${REVISION}" ]] \
  || die "REVISION does not match the checked-out commit"

for required_path in \
  backend/app \
  backend/alembic \
  backend/scripts \
  backend/alembic.ini \
  backend/pyproject.toml \
  backend/uv.lock \
  frontend-redesign/dist \
  frontend-redesign/package.json \
  frontend-redesign/package-lock.json \
  deploy; do
  [[ -e "${REPOSITORY_ROOT}/${required_path}" ]] \
    || die "required release input is missing: ${required_path}"
done

SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(
  git -C "${REPOSITORY_ROOT}" show -s --format=%ct "${REVISION}"
)}"
[[ "${SOURCE_DATE_EPOCH}" =~ ^[0-9]+$ ]] \
  || die "SOURCE_DATE_EPOCH must be a non-negative integer"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/caresync-release.XXXXXX")"
readonly WORK_DIR
readonly PAYLOAD_DIR="${WORK_DIR}/payload"

cleanup() {
  rm -rf -- "${WORK_DIR}"
}
trap cleanup EXIT

mkdir -p \
  "${PAYLOAD_DIR}/backend" \
  "${PAYLOAD_DIR}/frontend-redesign" \
  "$(dirname -- "${OUTPUT_PATH}")"

cp -R "${REPOSITORY_ROOT}/backend/app" "${PAYLOAD_DIR}/backend/app"
cp -R "${REPOSITORY_ROOT}/backend/alembic" "${PAYLOAD_DIR}/backend/alembic"
cp -R "${REPOSITORY_ROOT}/backend/scripts" "${PAYLOAD_DIR}/backend/scripts"
cp "${REPOSITORY_ROOT}/backend/alembic.ini" "${PAYLOAD_DIR}/backend/alembic.ini"
cp "${REPOSITORY_ROOT}/backend/pyproject.toml" "${PAYLOAD_DIR}/backend/pyproject.toml"
cp "${REPOSITORY_ROOT}/backend/uv.lock" "${PAYLOAD_DIR}/backend/uv.lock"
cp -R \
  "${REPOSITORY_ROOT}/frontend-redesign/dist" \
  "${PAYLOAD_DIR}/frontend-redesign/dist"
cp \
  "${REPOSITORY_ROOT}/frontend-redesign/package.json" \
  "${PAYLOAD_DIR}/frontend-redesign/package.json"
cp \
  "${REPOSITORY_ROOT}/frontend-redesign/package-lock.json" \
  "${PAYLOAD_DIR}/frontend-redesign/package-lock.json"
cp -R "${REPOSITORY_ROOT}/deploy" "${PAYLOAD_DIR}/deploy"

# Build/test runs can create ignored bytecode beside Python source. Strip it
# from the private staging tree, then fail closed if any bytecode survived.
find "${PAYLOAD_DIR}" -type d -name '__pycache__' -prune \
  -exec rm -rf -- {} +
find "${PAYLOAD_DIR}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

# A release must never acquire workstation state merely because it exists next
# to source. Reject surprising payload types and secret/runtime file names.
if find "${PAYLOAD_DIR}" -type l -print -quit | grep -q .; then
  die "release payload contains a symbolic link"
fi
if find "${PAYLOAD_DIR}" \( \
  -type d -name '__pycache__' -o \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) \
\) -print -quit | grep -q .; then
  die "release payload contains Python bytecode"
fi
if find "${PAYLOAD_DIR}" -type f \( \
  -iname '.env' -o \
  -iname '.env.*' -o \
  -iname '*.db' -o \
  -iname '*.sqlite' -o \
  -iname '*.sqlite3' -o \
  -iname '*.log' -o \
  -iname '*.pid' -o \
  -iname 'screenlog.*' \
\) -print -quit | grep -q .; then
  die "release payload contains a forbidden local-state file"
fi

CARESYNC_PAYLOAD_DIR="${PAYLOAD_DIR}" \
REVISION="${REVISION}" \
PRODUCTION_ORIGIN="${NORMALIZED_ORIGIN}" \
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH}" \
python3 <<'PY'
import datetime
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["CARESYNC_PAYLOAD_DIR"])
epoch = int(os.environ["SOURCE_DATE_EPOCH"])
file_count = 0
content_tree = hashlib.sha256()

for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
    if path.is_file():
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).digest()
        encoded_path = relative.encode("utf-8")
        content_tree.update(len(encoded_path).to_bytes(4, "big"))
        content_tree.update(encoded_path)
        content_tree.update(digest)
        file_count += 1

manifest = {
    "schema": "caresync-release-v1",
    "application": "CareSync",
    "git_sha": os.environ["REVISION"],
    "database_revision": "0043_org_wide_room_presence",
    "built_at": datetime.datetime.fromtimestamp(
        epoch, tz=datetime.timezone.utc
    ).isoformat().replace("+00:00", "Z"),
    "production_origin": os.environ["PRODUCTION_ORIGIN"],
    "runtime": {
        "node": "22",
        "python": "3.12",
        "uv": "0.9.27",
    },
    "file_count": file_count,
    "content_tree_sha256": content_tree.hexdigest(),
}

(root / "release-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

CARESYNC_PAYLOAD_DIR="${PAYLOAD_DIR}" \
OUTPUT_PATH="${OUTPUT_PATH}" \
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH}" \
python3 <<'PY'
import gzip
import os
import stat
import tarfile
from pathlib import Path

root = Path(os.environ["CARESYNC_PAYLOAD_DIR"])
output = Path(os.environ["OUTPUT_PATH"])
epoch = int(os.environ["SOURCE_DATE_EPOCH"])
temporary_output = output.with_name(f".{output.name}.tmp")

try:
    with temporary_output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
                    relative = path.relative_to(root).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = epoch
                    info.pax_headers = {}
                    if info.isdir():
                        info.mode = 0o755
                        archive.addfile(info)
                    elif info.isfile():
                        executable = bool(path.stat().st_mode & stat.S_IXUSR)
                        info.mode = 0o755 if executable else 0o644
                        with path.open("rb") as source:
                            archive.addfile(info, source)
                    else:
                        raise SystemExit(
                            f"unsupported release payload entry type: {relative}"
                        )
    os.replace(temporary_output, output)
finally:
    temporary_output.unlink(missing_ok=True)
PY

ARTIFACT_SHA256="$(
  python3 - "${OUTPUT_PATH}" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"

printf 'release_path=%s\n' "${OUTPUT_PATH}"
printf 'release_revision=%s\n' "${REVISION}"
printf 'release_sha256=%s\n' "${ARTIFACT_SHA256}"
