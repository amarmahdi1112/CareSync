#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly releases_root="/srv/caresync/releases"
readonly current_link="/srv/caresync/current"
readonly backup_root="/var/backups/caresync"
readonly runtime_root="/var/lib/caresync"
readonly environment_file="/etc/caresync/backend.env"
readonly secret_root="/etc/caresync/secrets"
readonly expected_revision="0042_billing_policy_recert"
readonly maximum_archive_bytes=$((512 * 1024 * 1024))
readonly service_name="caresync-api.service"
readonly push_service_name="caresync-push-worker.service"

release_sha="${1:-}"
expected_archive_sha="${2:-}"
if [[ ! "$release_sha" =~ ^[0-9a-f]{40}$ ]] ||
   [[ ! "$expected_archive_sha" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Invalid CareSync deployment identity." >&2
  exit 64
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo "CareSync activation must run as root." >&2
  exit 77
fi

exec 9>/run/lock/caresync-deploy.lock
if ! flock -n 9; then
  echo "Another CareSync deployment is active." >&2
  exit 75
fi

work_root="$(mktemp -d /srv/caresync/.deploy.XXXXXXXX)"
archive_path="$work_root/release.tar.gz"
stage_path="$work_root/release"
release_path="$releases_root/$release_sha"
previous_target=""
backup_path=""
migration_started=0
api_was_active=0
push_was_active=0

cleanup() {
  rm -rf -- "$work_root"
}

restore_database() {
  local dump_path="$1"
  systemctl stop "$service_name" "$push_service_name" 2>/dev/null || true
  runuser -u postgres -- dropdb --if-exists --force caresync || return 1
  runuser -u postgres -- createdb --template=template0 --encoding=UTF8 caresync ||
    return 1
  runuser -u postgres -- pg_restore \
    --exit-on-error \
    --no-owner \
    --role=postgres \
    --dbname=caresync \
    < "$dump_path"
}

bind_runtime_passwords() {
  local app_password transport_password
  app_password="$(tr -d '\n' < "$secret_root/app-db-password")" || return 1
  transport_password="$(tr -d '\n' < "$secret_root/transport-db-password")" ||
    return 1
  if [[ ! "$app_password" =~ ^[0-9a-f]{64}$ ]] ||
     [[ ! "$transport_password" =~ ^[0-9a-f]{64}$ ]] ||
     [[ "$app_password" == "$transport_password" ]]; then
    echo "CareSync database credentials are invalid." >&2
    return 1
  fi
  {
    printf "ALTER ROLE caresync_basic_app PASSWORD '%s';\n" "$app_password"
    printf "ALTER ROLE caresync_transport_evidence_ingest PASSWORD '%s';\n" \
      "$transport_password"
  } | runuser -u postgres -- psql \
      --no-psqlrc \
      --set=ON_ERROR_STOP=1 \
      --dbname=caresync \
      >/dev/null
}

certify_local_health() {
  local attempt
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 3 http://127.0.0.1:8001/api/v1/health |
        python3 -c '
import json, sys
value = json.load(sys.stdin)
database = value.get("database") or {}
raise SystemExit(
    0 if value.get("status") == "ok"
    and database.get("connected") is True
    and database.get("database_name") == "caresync"
    else 1
)
'; then
      return 0
    fi
    sleep 2 || return 1
  done
  return 1
}

recover_failed_deployment() {
  local exit_status=$?
  local recovery_failed=0
  # ERR is inherited by command substitutions and pipeline subshells under
  # `set -E`. Let the parent shell perform recovery exactly once.
  if (( BASH_SUBSHELL > 0 )); then
    return "$exit_status"
  fi
  trap - ERR
  set +e
  echo "CareSync deployment failed; attempting certified recovery." >&2
  systemctl stop "$push_service_name" "$service_name" 2>/dev/null || true
  if systemctl is-active --quiet "$service_name" ||
     systemctl is-active --quiet "$push_service_name"; then
    recovery_failed=1
  fi
  if [[ "$migration_started" -eq 1 && "$recovery_failed" -eq 0 ]]; then
    if [[ -z "$backup_path" || ! -s "$backup_path/database.dump" ]] ||
       ! restore_database "$backup_path/database.dump"; then
      recovery_failed=1
    elif [[ -n "$previous_target" &&
            -f "$previous_target/backend/scripts/bootstrap_basic_runtime_role.sql" ]]; then
      if ! runuser -u postgres -- psql \
          --no-psqlrc \
          --set=ON_ERROR_STOP=1 \
          --dbname=caresync \
          --file="$previous_target/backend/scripts/bootstrap_basic_runtime_role.sql" \
          >/dev/null ||
         ! bind_runtime_passwords; then
        recovery_failed=1
      fi
    fi
  fi
  if [[ -n "$previous_target" && -d "$previous_target" ]]; then
    if ! ln -sfn "$previous_target" "$current_link.rollback" ||
       ! mv -Tf "$current_link.rollback" "$current_link" ||
       ! systemctl daemon-reload; then
      recovery_failed=1
    fi
    if [[ "$api_was_active" -eq 1 && "$recovery_failed" -eq 0 ]]; then
      if ! systemctl start "$service_name" || ! certify_local_health; then
        recovery_failed=1
      fi
    fi
    if [[ "$push_was_active" -eq 1 && "$recovery_failed" -eq 0 ]] &&
       ! systemctl start "$push_service_name"; then
      recovery_failed=1
    fi
  elif ! rm -f -- "$current_link"; then
    recovery_failed=1
  fi
  cleanup
  if [[ "$recovery_failed" -ne 0 ]]; then
    echo "FATAL: CareSync automatic recovery could not certify the prior state; the API remains stopped for operator recovery." >&2
    systemctl stop "$push_service_name" "$service_name" 2>/dev/null || true
    exit 71
  fi
  echo "CareSync pre-deployment state was restored and certified." >&2
  exit "$exit_status"
}

trap cleanup EXIT

# Read at most one byte beyond the bound, then verify the CI-provided digest.
head -c "$((maximum_archive_bytes + 1))" > "$archive_path"
archive_size="$(stat -c %s "$archive_path")"
if (( archive_size < 1024 || archive_size > maximum_archive_bytes )); then
  echo "CareSync release archive has an invalid size." >&2
  exit 65
fi
actual_archive_sha="$(sha256sum "$archive_path" | awk '{print $1}')"
if [[ "$actual_archive_sha" != "$expected_archive_sha" ]]; then
  echo "CareSync release archive digest mismatch." >&2
  exit 65
fi

/usr/local/lib/caresync/validate-release-archive.py "$archive_path" "$release_sha"
mkdir -p "$stage_path"
tar --extract \
  --gzip \
  --file="$archive_path" \
  --directory="$stage_path" \
  --no-same-owner \
  --no-same-permissions

manifest_origin="$(
  python3 - "$stage_path/release-manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["production_origin"])
PY
)"
configured_origin="$(tr -d '\n' < /etc/caresync/production-origin)"
if [[ "$manifest_origin" != "$configured_origin" ]]; then
  echo "CareSync release origin does not match this host." >&2
  exit 65
fi

if [[ -e "$release_path" ]]; then
  active_target="$(readlink -f "$current_link" 2>/dev/null || true)"
  if [[ "$active_target" == "$release_path" ]]; then
    installed_sha="$(
      python3 - "$release_path/release-manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("git_sha", ""))
PY
    )"
    if [[ "$installed_sha" != "$release_sha" ]]; then
      echo "An incompatible release already owns this SHA." >&2
      exit 65
    fi
    rm -rf -- "$stage_path"
    if ! certify_local_health; then
      echo "The requested release is already active but is not healthy." >&2
      exit 70
    fi
    echo "CareSync release $release_sha is already active and healthy."
    exit 0
  else
    # A failed pre-activation attempt may have left a partial directory. It is
    # not trusted merely because its name is a commit SHA; rebuild it from the
    # newly verified archive.
    rm -rf -- "$release_path"
    mv -- "$stage_path" "$release_path"
  fi
else
  mv -- "$stage_path" "$release_path"
fi

export UV_PROJECT_ENVIRONMENT="$release_path/backend/.venv"
export UV_CACHE_DIR="/var/cache/caresync/uv"
cd "$release_path/backend"
/usr/local/bin/uv sync --frozen --no-dev --python /usr/bin/python3.12
"$release_path/backend/.venv/bin/python" -m compileall -q \
  "$release_path/backend/app"

installed_revision="$(
  "$release_path/backend/.venv/bin/python" - <<'PY'
from alembic.config import Config
from alembic.script import ScriptDirectory
heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
print(",".join(heads))
PY
)"
if [[ "$installed_revision" != "$expected_revision" ]]; then
  echo "CareSync release contains an unapproved migration head." >&2
  exit 65
fi

chown -R root:caresync "$release_path"
find "$release_path" -type d -exec chmod 0755 {} +
find "$release_path" -type f -exec chmod 0644 {} +
find "$release_path/backend/.venv/bin" -type f -exec chmod 0755 {} +
find "$release_path/deploy/scripts" -type f -name '*.sh' -exec chmod 0755 {} +

expected_ocr_requirements_sha="$(
  sha256sum "$release_path/backend/scripts/ocr-requirements.txt" | awk '{print $1}'
)"
installed_ocr_requirements_sha="$(
  cat /opt/caresync/ocr/requirements.sha256 2>/dev/null || true
)"
if [[ ! -x /opt/caresync/ocr/.venv/bin/python ||
      ! -f /opt/caresync/ocr/requirements.sha256 ||
      "$installed_ocr_requirements_sha" != "$expected_ocr_requirements_sha" ]]; then
  rm -rf /opt/caresync/ocr/.venv
  python3.12 -m venv /opt/caresync/ocr/.venv
  /opt/caresync/ocr/.venv/bin/python -m pip install --disable-pip-version-check \
    --upgrade pip
  /opt/caresync/ocr/.venv/bin/python -m pip install --disable-pip-version-check \
    "paddlepaddle==3.3.1" \
    --requirement "$release_path/backend/scripts/ocr-requirements.txt"
  sha256sum "$release_path/backend/scripts/ocr-requirements.txt" |
    awk '{print $1}' > /opt/caresync/ocr/requirements.sha256
fi
/opt/caresync/ocr/.venv/bin/python - <<'PY'
import cv2
import fitz
import paddle
import paddleocr
assert int(cv2.__version__.split(".", 1)[0]) >= 5
PY

if [[ -L "$current_link" ]]; then
  previous_target="$(readlink -f "$current_link")"
fi
if systemctl is-active --quiet "$service_name"; then
  api_was_active=1
fi
if systemctl is-active --quiet "$push_service_name"; then
  push_was_active=1
fi
# Only failures from this point forward need service/database recovery. Archive,
# dependency, and release-shape failures above must never disturb the active
# release.
trap recover_failed_deployment ERR
systemctl stop "$push_service_name" "$service_name" 2>/dev/null || true

backup_path="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)-before-$release_sha"
mkdir -p "$backup_path"
chmod 0700 "$backup_path"
runuser -u postgres -- pg_dump \
  --format=custom \
  --dbname=caresync \
  > "$backup_path/database.dump"
runuser -u postgres -- pg_dumpall --globals-only \
  > "$backup_path/cluster-roles.sql"
tar -C "$runtime_root/vault" -czf "$backup_path/private-vaults.tar.gz" \
  family staff
pg_restore --list "$backup_path/database.dump" >/dev/null
(
  cd "$backup_path"
  sha256sum database.dump cluster-roles.sql private-vaults.tar.gz \
    > SHA256SUMS
)

migration_started=1
runuser -u postgres -- bash -c '
  set -euo pipefail
  backend="$1"
  cd "$backend"
  exec env \
    PYTHONPATH="$backend" \
    ENVIRONMENT=production \
    DATABASE_TYPE=postgres \
    DATABASE_HOST=/var/run/postgresql \
    DATABASE_PORT=5432 \
    DATABASE_NAME=caresync \
    DATABASE_USER=postgres \
    DATABASE_PASSWORD= \
    DATABASE_SSL=false \
    DATABASE_READ_ONLY=false \
    CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true \
    "$backend/.venv/bin/alembic" -c "$backend/alembic.ini" \
      upgrade 0042_billing_policy_recert
' _ "$release_path/backend"

runuser -u postgres -- psql \
  --no-psqlrc \
  --set=ON_ERROR_STOP=1 \
  --dbname=caresync \
  --file="$release_path/backend/scripts/bootstrap_basic_runtime_role.sql" \
  >/dev/null
bind_runtime_passwords

persisted_revision="$(
  runuser -u postgres -- psql \
    --no-psqlrc \
    --tuples-only \
    --no-align \
    --dbname=caresync \
    --command='SELECT version_num FROM public.alembic_version'
)"
if [[ "$persisted_revision" != "$expected_revision" ]]; then
  echo "CareSync database did not reach its certified revision." >&2
  exit 70
fi

ln -sfn "$release_path" "$current_link.next"
mv -Tf "$current_link.next" "$current_link"
systemctl daemon-reload
systemctl restart "$service_name"

if ! certify_local_health; then
  journalctl -u "$service_name" --no-pager -n 40 >&2 || true
  echo "CareSync failed its post-deploy health gate." >&2
  exit 70
fi

nginx -t
systemctl reload nginx

if systemctl is-enabled --quiet "$push_service_name" 2>/dev/null; then
  systemctl restart "$push_service_name"
fi

find "$releases_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
  sort -nr |
  awk 'NR > 5 {sub(/^[^ ]+ /, ""); print}' |
  while IFS= read -r old_release; do
    if [[ "$old_release" != "$release_path" &&
          "$old_release" != "$previous_target" ]]; then
      rm -rf -- "$old_release"
    fi
  done
find "$backup_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
  sort -nr |
  awk 'NR > 7 {sub(/^[^ ]+ /, ""); print}' |
  xargs -r rm -rf --

trap - ERR
echo "CareSync release $release_sha is healthy."
