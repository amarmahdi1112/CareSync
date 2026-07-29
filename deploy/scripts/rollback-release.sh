#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly releases_root="/srv/caresync/releases"
readonly current_link="/srv/caresync/current"
readonly backup_root="/var/backups/caresync"
readonly runtime_root="/var/lib/caresync"
readonly secret_root="/etc/caresync/secrets"
readonly ocr_root="/opt/caresync/ocr"
readonly ocr_versions_root="$ocr_root/venvs"
readonly ocr_home="/var/lib/caresync/ocr-home"
readonly maintenance_flag="/run/caresync-maintenance"
readonly service_name="caresync-api.service"
readonly push_service_name="caresync-push-worker.service"
readonly recovery_budget_seconds=600

recovery_active=0
recovery_deadline=0
recovery_interrupted=0
recovery_core_certified=0
traffic_gate_mutated=0
live_mutation_started=0
configured_origin=""
production_hostname=""
api_initial_state=""
push_initial_state=""

target_sha="${1:-}"
recovery_set="${2:-}"
if [[ "$(id -u)" -ne 0 ]] || [[ ! "$target_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: sudo caresync-rollback-release <git-sha> [recovery-set-directory]" >&2
  exit 64
fi

target="$releases_root/$target_sha"
if [[ ! -d "$target" ||
      -L "$target" ||
      ! -f "$target/release-manifest.json" ||
      -L "$target/release-manifest.json" ||
      ! -x "$target/backend/.venv/bin/uvicorn" ||
      ! -f "$target/backend/scripts/bootstrap_basic_runtime_role.sql" ||
      ! -f "$target/backend/scripts/certify_ocr_runtime.py" ||
      ! -f "$target/backend/scripts/ocr-requirements-linux-x86_64-cp312.lock" ]]; then
  echo "The requested CareSync release is not installed." >&2
  exit 66
fi
target_ocr_lock="$target/backend/scripts/ocr-requirements-linux-x86_64-cp312.lock"
target_ocr_sha="$(sha256sum "$target_ocr_lock" | awk '{print $1}')"
target_ocr_candidate="$ocr_versions_root/lock-v1-$target_ocr_sha"
target_revision="$(
  python3 - "$target/release-manifest.json" "$target_sha" <<'PY'
import json
import re
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
revision = manifest.get("database_revision", "")
if (
    manifest.get("schema") != "caresync-release-v1"
    or manifest.get("git_sha") != sys.argv[2]
    or not isinstance(revision, str)
    or not re.fullmatch(r"[0-9A-Za-z_]+", revision)
):
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
previous_release_name="${previous_target##*/}"
if [[ -z "$previous_target" ||
      ! "$previous_release_name" =~ ^[0-9a-f]{40}$ ||
      "$previous_target" != "$releases_root/$previous_release_name" ||
      ! -d "$previous_target" ||
      -L "$previous_target" ||
      ! -f "$previous_target/release-manifest.json" ||
      -L "$previous_target/release-manifest.json" ||
      ! -f "$previous_target/backend/scripts/bootstrap_basic_runtime_role.sql" ]]; then
  echo "The active CareSync release cannot be identified safely." >&2
  exit 66
fi
previous_manifest_sha="$(
  python3 - "$previous_target/release-manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if manifest.get("schema") != "caresync-release-v1":
    raise SystemExit("The active CareSync release manifest is invalid.")
print(manifest.get("git_sha", ""))
PY
)"
if [[ "$previous_manifest_sha" != "$previous_release_name" ]]; then
  echo "The active CareSync release manifest does not match its path." >&2
  exit 66
fi
configured_origin="$(tr -d '\n' < /etc/caresync/production-origin)"
production_hostname="$(
  python3 - "$configured_origin" <<'PY'
import sys
from urllib.parse import urlsplit
parsed = urlsplit(sys.argv[1])
if parsed.scheme != "https" or not parsed.hostname:
    raise SystemExit("CareSync production origin is invalid")
print(parsed.hostname)
PY
)"
if [[ -e "$maintenance_flag" || -L "$maintenance_flag" ]]; then
  echo "CareSync is already in operator maintenance mode." >&2
  exit 66
fi
nginx -t

certify_target_ocr_runtime() {
  local active_ocr_target unsafe_path
  [[ -L "$ocr_root/.venv" ]] || return
  active_ocr_target="$(readlink -f -- "$ocr_root/.venv")" || return
  [[ "$active_ocr_target" == "$target_ocr_candidate" ]] || return
  [[ -d "$target_ocr_candidate" && ! -L "$target_ocr_candidate" ]] || return
  [[ "$(stat -c '%U:%G:%a' -- "$ocr_root")" == "root:caresync:750" ]] ||
    return
  [[ "$(stat -c '%U:%G:%a' -- "$ocr_versions_root")" == \
     "root:caresync:750" ]] || return
  [[ -f "$ocr_root/requirements.sha256" ]] || return
  [[ ! -L "$ocr_root/requirements.sha256" ]] || return
  cmp -s \
    <(printf '%s\n' "$target_ocr_sha") \
    "$ocr_root/requirements.sha256" ||
    return

  unsafe_path="$(
    find "$target_ocr_candidate" -xdev \
      \( \
        \( -type d \
           \( ! -user root -o ! -group caresync -o ! -perm -0050 -o \
              -perm /0027 \) \) -o \
        \( -type f \
           \( ! -user root -o ! -group caresync -o ! -perm -0040 -o \
              -perm /0027 \) \) -o \
        \( ! -type d ! -type f ! -type l \) \
      \) \
      -print -quit
  )" || return
  [[ -z "$unsafe_path" ]] || return
  unsafe_path="$(
    find "$target_ocr_candidate/bin" \
      -xdev -type f ! -perm -0050 -print -quit
  )" || return
  [[ -z "$unsafe_path" ]] || return

  runuser -u caresync -- test -x "$target_ocr_candidate/bin/python" ||
    return
  (
    cd "$ocr_home" || exit
    runuser -u caresync -- env \
      HOME="$ocr_home" \
      XDG_CACHE_HOME="$ocr_home/cache" \
      PADDLE_PDX_CACHE_HOME="$ocr_home/paddlex" \
      PADDLE_HOME="$ocr_home/paddle" \
      "$target_ocr_candidate/bin/python" -m pip check || exit
    runuser -u caresync -- env \
      HOME="$ocr_home" \
      XDG_CACHE_HOME="$ocr_home/cache" \
      PADDLE_PDX_CACHE_HOME="$ocr_home/paddlex" \
      PADDLE_HOME="$ocr_home/paddle" \
      "$target_ocr_candidate/bin/python" \
        "$target/backend/scripts/certify_ocr_runtime.py" \
        "$target_ocr_lock"
  )
}

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

if ! certify_target_ocr_runtime; then
  echo "Rollback refused: the target release does not match the active certified OCR runtime." >&2
  exit 66
fi

api_was_active=0
push_was_active=0
database_mutated=0
vault_mutated=0
roles_mutated=0
safety_backup=""
staged_vault=""
api_initial_state="$(
  systemctl show --property=ActiveState --value "$service_name"
)"
push_initial_state="$(
  systemctl show --property=ActiveState --value "$push_service_name"
)"
if [[ "$api_initial_state" == "active" ]]; then
  api_was_active=1
fi
if [[ "$push_initial_state" == "active" ]]; then
  push_was_active=1
fi

remaining_recovery_seconds() {
  local remaining=$((recovery_deadline - SECONDS))
  if (( remaining <= 0 )); then
    echo "CareSync rollback recovery exceeded its recovery budget." >&2
    return 124
  fi
  printf '%s\n' "$remaining"
}

run_bounded_recovery_command() {
  local remaining
  remaining="$(remaining_recovery_seconds)" || return
  timeout \
    --foreground \
    --signal=TERM \
    --kill-after=10s \
    "${remaining}s" \
    "$@"
}

run_maybe_bounded_command() {
  if [[ "$recovery_active" -eq 1 ]]; then
    run_bounded_recovery_command "$@"
  else
    "$@"
  fi
}

cleanup_temporary_release_links() {
  local temporary_link
  local cleanup_failed=0
  for temporary_link in "$current_link.next" "$current_link.recovery"; do
    if [[ -L "$temporary_link" ]]; then
      run_maybe_bounded_command rm -f -- "$temporary_link" ||
        cleanup_failed=1
    elif [[ -e "$temporary_link" ]]; then
      cleanup_failed=1
    fi
  done
  return "$cleanup_failed"
}

certify_services_inactive_during_recovery() {
  local api_state push_state
  api_state="$(
    run_bounded_recovery_command \
      systemctl show --property=ActiveState --value "$service_name"
  )" || return
  push_state="$(
    run_bounded_recovery_command \
      systemctl show --property=ActiveState --value "$push_service_name"
  )" || return
  [[ "$api_state" == "inactive" && "$push_state" == "inactive" ]]
}

fail_rollback_after_mutation() {
  local status="$1"
  shift
  echo "$*" >&2
  return "$status"
}

public_health_status() {
  curl \
    --noproxy '*' \
    --output /dev/null \
    --silent \
    --show-error \
    --max-time 10 \
    --resolve "${production_hostname}:443:127.0.0.1" \
    --write-out '%{http_code}' \
    "${configured_origin%/}/api/v1/health"
}

certify_traffic_gate_active() {
  [[ -f "$maintenance_flag" && ! -L "$maintenance_flag" ]] || return
  [[ "$(stat -c '%U:%G:%a' -- "$maintenance_flag")" == "root:root:644" ]] ||
    return
  [[ "$(public_health_status)" == "503" ]]
}

activate_traffic_gate() {
  local gate_next="${maintenance_flag}.next.$$"
  [[ ! -e "$maintenance_flag" && ! -L "$maintenance_flag" ]] || return
  traffic_gate_mutated=1
  run_maybe_bounded_command \
    install -o root -g root -m 0644 /dev/null "$gate_next" || return
  run_maybe_bounded_command \
    mv -Tf -- "$gate_next" "$maintenance_flag" || return
  certify_traffic_gate_active
}

deactivate_traffic_gate() {
  if [[ -L "$maintenance_flag" ]] ||
     [[ -e "$maintenance_flag" && ! -f "$maintenance_flag" ]]; then
    echo "The CareSync traffic gate has an unsafe type." >&2
    return 1
  fi
  run_maybe_bounded_command rm -f -- "$maintenance_flag" || return
  [[ ! -e "$maintenance_flag" && ! -L "$maintenance_flag" ]]
}

certify_public_health() {
  [[ "$(public_health_status)" == "200" ]]
}

restore_database() {
  local dump_path="$1"
  run_maybe_bounded_command \
    runuser -u postgres -- dropdb --if-exists --force caresync || return 1
  run_maybe_bounded_command \
    runuser -u postgres -- createdb \
      --template=template0 \
      --encoding=UTF8 \
      --owner=postgres \
      caresync ||
    return 1
  run_maybe_bounded_command runuser -u postgres -- pg_restore \
    --exit-on-error \
    --single-transaction \
    --no-owner \
    --role=postgres \
    --dbname=caresync \
    < "$dump_path"
}

install_vault_archive() {
  local archive_path="$1"
  local work_path
  work_path="$(
    run_maybe_bounded_command \
      mktemp -d "$runtime_root/.rollback-vault.XXXXXXXX"
  )" || return 1
  staged_vault="$work_path"
  run_maybe_bounded_command tar \
    --extract \
    --gzip \
    --file="$archive_path" \
    --directory="$work_path" \
    --no-same-owner \
    --no-same-permissions ||
    return 1
  [[ -d "$work_path/family" && -d "$work_path/staff" ]] || return 1
  run_maybe_bounded_command \
    rm -rf -- "$runtime_root/vault/family" "$runtime_root/vault/staff" ||
    return 1
  run_maybe_bounded_command \
    mv -- "$work_path/family" "$runtime_root/vault/family" || return 1
  run_maybe_bounded_command \
    mv -- "$work_path/staff" "$runtime_root/vault/staff" || return 1
  run_maybe_bounded_command rmdir -- "$work_path" || return 1
  staged_vault=""
  run_maybe_bounded_command \
    chown -R caresync:caresync "$runtime_root/vault" || return 1
  run_maybe_bounded_command chmod -R go-rwx "$runtime_root/vault"
}

bind_runtime_roles() {
  local release_path="$1"
  local app_password transport_password
  run_maybe_bounded_command runuser -u postgres -- psql \
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
  } | run_maybe_bounded_command \
        runuser -u postgres -- psql \
          --no-psqlrc \
          --set=ON_ERROR_STOP=1 \
          --dbname=caresync \
          >/dev/null
}

certify_local_health() {
  local attempt
  for attempt in $(seq 1 60); do
    if [[ "$recovery_active" -eq 1 ]] &&
       ! remaining_recovery_seconds >/dev/null; then
      return 1
    fi
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
  local exit_status="${1:-1}"
  local recovery_cause="${2:-ERR}"
  local recovery_failed=0
  local api_recovered_state=""
  local push_recovered_state=""
  local recovery_gate_certified=0
  # ERR is inherited by command substitutions and pipeline subshells under
  # `set -E`. Let the parent shell perform recovery exactly once.
  if (( BASH_SUBSHELL > 0 )); then
    return "$exit_status"
  fi
  if [[ "$recovery_active" -eq 1 ]]; then
    echo "FATAL: CareSync rollback recovery was interrupted recursively." >&2
    exit 71
  fi
  recovery_active=1
  recovery_deadline=$((SECONDS + recovery_budget_seconds))
  trap - ERR
  trap 'recovery_interrupted=1' INT TERM HUP
  set +e
  echo "CareSync rollback stopped by ${recovery_cause}; attempting certified recovery." >&2
  if [[ "$live_mutation_started" -eq 0 ]]; then
    if [[ "$traffic_gate_mutated" -eq 1 ]] &&
       ! deactivate_traffic_gate; then
      recovery_failed=1
    fi
    if ! run_bounded_recovery_command \
         rm -f -- "${maintenance_flag}.next.$$"; then
      recovery_failed=1
    fi
    api_recovered_state="$(
      run_bounded_recovery_command \
        systemctl show --property=ActiveState --value "$service_name"
    )" || recovery_failed=1
    push_recovered_state="$(
      run_bounded_recovery_command \
        systemctl show --property=ActiveState --value "$push_service_name"
    )" || recovery_failed=1
    if [[ "$api_recovered_state" != "$api_initial_state" ||
          "$push_recovered_state" != "$push_initial_state" ]]; then
      recovery_failed=1
    fi
    if [[ "$api_initial_state" == "active" &&
          "$recovery_failed" -eq 0 ]] &&
       ! certify_public_health; then
      recovery_failed=1
    fi
    if [[ "$recovery_failed" -ne 0 ]]; then
      echo "FATAL: CareSync could not certify rollback traffic-gate recovery; live services were not changed." >&2
      exit 71
    fi
    echo "CareSync rollback traffic-gate activation was reversed before live state changed." >&2
    trap - INT TERM HUP
    exit "$exit_status"
  fi
  if ! run_bounded_recovery_command \
      systemctl stop "$push_service_name" "$service_name" 2>/dev/null; then
    recovery_failed=1
  fi
  if [[ "$recovery_failed" -eq 0 ]] &&
     ! certify_services_inactive_during_recovery; then
    recovery_failed=1
  fi
  if [[ "$database_mutated" -eq 1 && "$recovery_failed" -eq 0 ]]; then
    if [[ -z "$safety_backup" ]] ||
       [[ ! -s "$safety_backup/database.dump" ]] ||
       [[ ! -s "$safety_backup/SHA256SUMS" ]] ||
       ! (
         cd "$safety_backup" &&
         run_bounded_recovery_command \
           sha256sum --check --strict SHA256SUMS >/dev/null
       ) ||
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
    run_bounded_recovery_command rm -rf -- "$staged_vault" ||
      recovery_failed=1
  fi
  if ! run_bounded_recovery_command \
       rm -f -- "${maintenance_flag}.next.$$"; then
    recovery_failed=1
  fi
  if ! cleanup_temporary_release_links; then
    recovery_failed=1
  fi
  if ! run_bounded_recovery_command \
       ln -sfn "$previous_target" "$current_link.recovery" ||
     ! run_bounded_recovery_command \
       mv -Tf "$current_link.recovery" "$current_link" ||
     ! run_bounded_recovery_command systemctl daemon-reload; then
    recovery_failed=1
  fi
  if [[ "$api_was_active" -eq 1 && "$recovery_failed" -eq 0 ]]; then
    if ! run_bounded_recovery_command systemctl start "$service_name" ||
       ! certify_local_health; then
      recovery_failed=1
    fi
  fi
  if [[ "$recovery_failed" -eq 0 ]]; then
    recovery_core_certified=1
  fi
  if [[ "$traffic_gate_mutated" -eq 1 &&
        "$recovery_failed" -eq 0 ]] &&
     ! deactivate_traffic_gate; then
    recovery_failed=1
  fi
  if [[ "$api_was_active" -eq 1 && "$recovery_failed" -eq 0 ]] &&
     ! certify_public_health; then
    recovery_failed=1
  fi
  if [[ "$push_was_active" -eq 1 && "$recovery_failed" -eq 0 ]] &&
     ! run_bounded_recovery_command systemctl start "$push_service_name"; then
    recovery_failed=1
  fi
  if [[ "$recovery_failed" -ne 0 ]]; then
    echo "FATAL: CareSync automatic rollback recovery could not fully certify the prior state; operator attention is required." >&2
    if certify_traffic_gate_active; then
      recovery_gate_certified=1
    else
      if [[ ! -e "$maintenance_flag" && ! -L "$maintenance_flag" ]]; then
        if activate_traffic_gate && certify_traffic_gate_active; then
          recovery_gate_certified=1
        fi
      fi
    fi
    if [[ "$recovery_gate_certified" -eq 0 &&
          "$recovery_core_certified" -eq 1 &&
          "$api_was_active" -eq 1 ]]; then
      echo "CareSync restored the prior API locally, but could not certify a public maintenance fence; the restored API was left running for operator attention." >&2
      exit 72
    fi
    run_bounded_recovery_command \
      systemctl stop "$push_service_name" "$service_name" 2>/dev/null || true
    exit 71
  fi
  echo "CareSync pre-rollback state was restored and certified." >&2
  if [[ "$recovery_interrupted" -eq 1 ]]; then
    echo "A terminal signal was deferred until rollback recovery completed." >&2
  fi
  trap - INT TERM HUP
  exit "$exit_status"
}

# From this point onward every failure restores the prior symlink, service
# state, and—when a recovery set is used—the pre-rollback database and vaults.
trap 'recover_failed_rollback "$?" ERR' ERR
trap 'recover_failed_rollback 130 INT' INT
trap 'recover_failed_rollback 143 TERM' TERM
trap 'recover_failed_rollback 129 HUP' HUP
activate_traffic_gate
live_mutation_started=1
systemctl stop "$push_service_name" "$service_name" 2>/dev/null
if systemctl is-active --quiet "$service_name" ||
   systemctl is-active --quiet "$push_service_name"; then
  fail_rollback_after_mutation 70 \
    "CareSync services did not stop before rollback."
fi

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
  fail_rollback_after_mutation 70 \
    "The database revision does not match the requested release."
fi

ln -sfn "$target" "$current_link.next"
mv -Tf "$current_link.next" "$current_link"
systemctl daemon-reload
systemctl restart "$service_name"

if ! certify_local_health; then
  journalctl -u "$service_name" --no-pager -n 40 >&2 || true
  fail_rollback_after_mutation 70 \
    "CareSync rollback target failed its health gate."
fi

trap - ERR INT TERM HUP
post_commit_failed=0
if ! rm -f -- "${maintenance_flag}.next.$$"; then
  echo "CareSync rollback committed, but traffic-gate staging cleanup failed." >&2
  post_commit_failed=1
fi
if ! cleanup_temporary_release_links; then
  echo "CareSync rollback committed, but release-link staging cleanup failed." >&2
  post_commit_failed=1
fi
if ! deactivate_traffic_gate; then
  echo "CareSync rollback committed, but its public traffic gate did not reopen." >&2
  post_commit_failed=1
elif ! certify_public_health; then
  echo "CareSync rollback is healthy locally, but public health failed." >&2
  post_commit_failed=1
fi
if [[ "$post_commit_failed" -eq 0 && "$push_was_active" -eq 1 ]] &&
   ! systemctl start "$push_service_name"; then
  echo "CareSync rollback committed, but the push worker did not restart." >&2
  post_commit_failed=1
fi
if [[ "$post_commit_failed" -ne 0 ]]; then
  exit 72
fi
echo "CareSync rolled back safely to $target_sha."
