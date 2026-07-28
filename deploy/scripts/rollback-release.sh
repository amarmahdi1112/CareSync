#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly releases_root="/srv/caresync/releases"
readonly current_link="/srv/caresync/current"
readonly backup_root="/var/backups/caresync"
readonly runtime_root="/var/lib/caresync"
readonly secret_root="/etc/caresync/secrets"
readonly service_name="caresync-api.service"
readonly push_service_name="caresync-push-worker.service"

target_sha="${1:-}"
recovery_set="${2:-}"
if [[ "$(id -u)" -ne 0 ]] || [[ ! "$target_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: sudo caresync-rollback-release <git-sha> [recovery-set-directory]" >&2
  exit 64
fi

target="$releases_root/$target_sha"
if [[ ! -f "$target/release-manifest.json" ||
      ! -x "$target/backend/.venv/bin/uvicorn" ||
      ! -f "$target/backend/scripts/bootstrap_basic_runtime_role.sql" ]]; then
  echo "The requested CareSync release is not installed." >&2
  exit 66
fi
target_revision="$(
  python3 - "$target/release-manifest.json" <<'PY'
import json
import re
import sys

revision = json.load(open(sys.argv[1], encoding="utf-8")).get("database_revision", "")
if not isinstance(revision, str) or not re.fullmatch(r"[0-9A-Za-z_]+", revision):
    raise SystemExit("The target release has an invalid database revision.")
print(revision)
PY
)"

exec 9>/run/lock/caresync-deploy.lock
if ! flock -n 9; then
  echo "Another CareSync deployment is active." >&2
  exit 75
fi

previous_target=""
if [[ -L "$current_link" ]]; then
  previous_target="$(readlink -f "$current_link")"
fi
if [[ -z "$previous_target" ||
      ! -d "$previous_target" ||
      ! -f "$previous_target/backend/scripts/bootstrap_basic_runtime_role.sql" ]]; then
  echo "The active CareSync release cannot be identified safely." >&2
  exit 66
fi

validate_vault_archive() {
  local archive_path="$1"
  python3 - "$archive_path" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], mode="r:gz") as archive:
    members = archive.getmembers()
    if not members:
        raise SystemExit("The vault archive is empty.")
    for member in members:
        path = PurePosixPath(member.name)
        if (
            not member.name
            or member.name.startswith("/")
            or path.is_absolute()
            or "." in path.parts
            or ".." in path.parts
            or not path.parts
            or path.parts[0] not in {"family", "staff"}
            or not (member.isfile() or member.isdir())
        ):
            raise SystemExit("The vault archive contains an unsafe object.")
PY
}

# Validate every operator-supplied recovery object before stopping a service or
# changing the active release. A typo or damaged set must be a no-op.
if [[ -n "$recovery_set" ]]; then
  recovery_set="$(readlink -f -- "$recovery_set")"
  case "$recovery_set" in
    "$backup_root"/*) ;;
    *)
      echo "Recovery set must be inside $backup_root." >&2
      exit 64
      ;;
  esac
  for required_file in \
    SHA256SUMS \
    database.dump \
    cluster-roles.sql \
    private-vaults.tar.gz; do
    if [[ ! -f "$recovery_set/$required_file" ]]; then
      echo "The recovery set is incomplete." >&2
      exit 66
    fi
  done
  (
    cd "$recovery_set"
    sha256sum --check --strict SHA256SUMS >/dev/null
  )
  pg_restore --list "$recovery_set/database.dump" >/dev/null
  validate_vault_archive "$recovery_set/private-vaults.tar.gz"
fi

api_was_active=0
push_was_active=0
database_mutated=0
vault_mutated=0
roles_mutated=0
safety_backup=""
staged_vault=""
if systemctl is-active --quiet "$service_name"; then
  api_was_active=1
fi
if systemctl is-active --quiet "$push_service_name"; then
  push_was_active=1
fi

restore_database() {
  local dump_path="$1"
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

install_vault_archive() {
  local archive_path="$1"
  local work_path
  work_path="$(mktemp -d "$runtime_root/.rollback-vault.XXXXXXXX")" || return 1
  staged_vault="$work_path"
  tar \
    --extract \
    --gzip \
    --file="$archive_path" \
    --directory="$work_path" \
    --no-same-owner \
    --no-same-permissions ||
    return 1
  [[ -d "$work_path/family" && -d "$work_path/staff" ]] || return 1
  rm -rf -- "$runtime_root/vault/family" "$runtime_root/vault/staff" || return 1
  mv -- "$work_path/family" "$runtime_root/vault/family" || return 1
  mv -- "$work_path/staff" "$runtime_root/vault/staff" || return 1
  rmdir -- "$work_path" || return 1
  staged_vault=""
  chown -R caresync:caresync "$runtime_root/vault" || return 1
  chmod -R go-rwx "$runtime_root/vault"
}

bind_runtime_roles() {
  local release_path="$1"
  local app_password transport_password
  runuser -u postgres -- psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname=caresync \
    --file="$release_path/backend/scripts/bootstrap_basic_runtime_role.sql" \
    >/dev/null ||
    return 1
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

recover_failed_rollback() {
  local exit_status=$?
  local recovery_failed=0
  # ERR is inherited by command substitutions and pipeline subshells under
  # `set -E`. Let the parent shell perform recovery exactly once.
  if (( BASH_SUBSHELL > 0 )); then
    return "$exit_status"
  fi
  trap - ERR
  set +e
  echo "CareSync rollback failed; attempting certified recovery." >&2
  systemctl stop "$push_service_name" "$service_name" 2>/dev/null || true
  if systemctl is-active --quiet "$service_name" ||
     systemctl is-active --quiet "$push_service_name"; then
    recovery_failed=1
  fi
  if [[ "$database_mutated" -eq 1 && "$recovery_failed" -eq 0 ]]; then
    if [[ -z "$safety_backup" || ! -s "$safety_backup/database.dump" ]] ||
       ! restore_database "$safety_backup/database.dump"; then
      recovery_failed=1
    fi
  fi
  if [[ "$roles_mutated" -eq 1 && "$recovery_failed" -eq 0 ]] &&
     ! bind_runtime_roles "$previous_target"; then
    recovery_failed=1
  fi
  if [[ "$vault_mutated" -eq 1 && "$recovery_failed" -eq 0 ]]; then
    if [[ -z "$safety_backup" ||
          ! -s "$safety_backup/private-vaults.tar.gz" ]] ||
       ! install_vault_archive "$safety_backup/private-vaults.tar.gz"; then
      recovery_failed=1
    fi
  fi
  if [[ -n "$staged_vault" && -d "$staged_vault" ]]; then
    rm -rf -- "$staged_vault" || recovery_failed=1
  fi
  if ! ln -sfn "$previous_target" "$current_link.recovery" ||
     ! mv -Tf "$current_link.recovery" "$current_link" ||
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
  if [[ "$recovery_failed" -ne 0 ]]; then
    echo "FATAL: CareSync automatic rollback recovery could not certify the prior state; the API remains stopped for operator recovery." >&2
    systemctl stop "$push_service_name" "$service_name" 2>/dev/null || true
    exit 71
  fi
  echo "CareSync pre-rollback state was restored and certified." >&2
  exit "$exit_status"
}

# From this point onward every failure restores the prior symlink, service
# state, and—when a recovery set is used—the pre-rollback database and vaults.
trap recover_failed_rollback ERR
systemctl stop "$push_service_name" "$service_name" 2>/dev/null || true

if [[ -n "$recovery_set" ]]; then
  safety_backup="$(
    mktemp -d "$backup_root/rollback-safety-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX"
  )"
  chmod 0700 "$safety_backup"
  runuser -u postgres -- pg_dump \
    --format=custom \
    --dbname=caresync \
    > "$safety_backup/database.dump"
  runuser -u postgres -- pg_dumpall --globals-only \
    > "$safety_backup/cluster-roles.sql"
  tar -C "$runtime_root/vault" \
    -czf "$safety_backup/private-vaults.tar.gz" \
    family staff
  pg_restore --list "$safety_backup/database.dump" >/dev/null
  validate_vault_archive "$safety_backup/private-vaults.tar.gz"
  (
    cd "$safety_backup"
    sha256sum database.dump cluster-roles.sql private-vaults.tar.gz \
      > SHA256SUMS
  )

  database_mutated=1
  restore_database "$recovery_set/database.dump"
  roles_mutated=1
  bind_runtime_roles "$target"
  vault_mutated=1
  install_vault_archive "$recovery_set/private-vaults.tar.gz"
else
  roles_mutated=1
  bind_runtime_roles "$target"
fi

persisted_revision="$(
  runuser -u postgres -- psql \
    --no-psqlrc \
    --tuples-only \
    --no-align \
    --dbname=caresync \
    --command='SELECT version_num FROM public.alembic_version'
)"
if [[ "$persisted_revision" != "$target_revision" ]]; then
  echo "The database revision does not match the requested release." >&2
  exit 70
fi

ln -sfn "$target" "$current_link.next"
mv -Tf "$current_link.next" "$current_link"
systemctl daemon-reload
systemctl restart "$service_name"

if ! certify_local_health; then
  journalctl -u "$service_name" --no-pager -n 40 >&2 || true
  echo "CareSync rollback target failed its health gate." >&2
  exit 70
fi

if [[ "$push_was_active" -eq 1 ]]; then
  systemctl start "$push_service_name"
fi
trap - ERR
echo "CareSync rolled back safely to $target_sha."
