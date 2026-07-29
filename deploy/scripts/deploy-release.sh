#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly releases_root="/srv/caresync/releases"
readonly current_link="/srv/caresync/current"
readonly backup_root="/var/backups/caresync"
readonly runtime_root="/var/lib/caresync"
readonly environment_file="/etc/caresync/backend.env"
readonly secret_root="/etc/caresync/secrets"
readonly ocr_root="/opt/caresync/ocr"
readonly ocr_versions_root="$ocr_root/venvs"
readonly ocr_home="/var/lib/caresync/ocr-home"
readonly maintenance_flag="/run/caresync-maintenance"
readonly expected_revision="0043_org_wide_room_presence"
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
api_initial_state=""
push_initial_state=""
api_pre_gate_state=""
push_pre_gate_state=""
first_activation=0
recovery_active=0
recovery_database_restored=0
recovery_core_certified=0
recovery_deadline=0
ocr_candidate_stage=""
ocr_candidate=""
ocr_expected_hash_file="$work_root/ocr-requirements.sha256.expected"
ocr_previous_hash_backup="$work_root/ocr-requirements.sha256.previous"
ocr_previous_hash_present=0
ocr_previous_runtime_kind=""
ocr_previous_runtime_target=""
ocr_previous_runtime_identity=""
ocr_legacy_rollback=""
ocr_mutated=0
recovery_interrupted=0
release_already_active=0
traffic_gate_mutated=0
live_mutation_started=0
production_hostname=""
readonly recovery_budget_seconds=600

cleanup() {
  local cleanup_failed=0
  local temporary_link
  if [[ -n "${ocr_candidate_stage:-}" &&
        -d "${ocr_candidate_stage:-}" ]]; then
    if [[ "${recovery_active:-0}" -eq 1 ]]; then
      if ! run_bounded_recovery_command rm -rf -- "$ocr_candidate_stage"; then
        cleanup_failed=1
      fi
    else
      if ! rm -rf -- "$ocr_candidate_stage"; then
        cleanup_failed=1
      fi
    fi
  fi
  if [[ -n "${ocr_root:-}" ]]; then
    if [[ "${recovery_active:-0}" -eq 1 ]]; then
      if ! run_bounded_recovery_command \
          rm -f -- "$ocr_root/.venv.next.$$" \
                    "$ocr_root/.venv.rollback.$$" \
                    "$ocr_root/.requirements.sha256.next.$$" \
                    "$ocr_root/.requirements.sha256.rollback.$$" \
                    "${maintenance_flag}.next.$$"; then
        cleanup_failed=1
      fi
    elif ! rm -f -- "$ocr_root/.venv.next.$$" \
                       "$ocr_root/.venv.rollback.$$" \
                       "$ocr_root/.requirements.sha256.next.$$" \
                       "$ocr_root/.requirements.sha256.rollback.$$" \
                       "${maintenance_flag}.next.$$"; then
      cleanup_failed=1
    fi
  fi
  for temporary_link in "$current_link.next" "$current_link.rollback"; do
    if [[ -L "$temporary_link" ]]; then
      if [[ "${recovery_active:-0}" -eq 1 ]]; then
        if ! run_bounded_recovery_command rm -f -- "$temporary_link"; then
          cleanup_failed=1
        fi
      elif ! rm -f -- "$temporary_link"; then
        cleanup_failed=1
      fi
    elif [[ -e "$temporary_link" ]]; then
      cleanup_failed=1
    fi
  done
  if [[ "${recovery_active:-0}" -eq 1 ]]; then
    if ! run_bounded_recovery_command rm -rf -- "$work_root"; then
      cleanup_failed=1
    fi
  else
    if ! rm -rf -- "$work_root"; then
      cleanup_failed=1
    fi
  fi
  return "$cleanup_failed"
}

abort_before_mutation() {
  local exit_status="$1"
  local signal_name="$2"
  trap - INT TERM HUP
  echo "CareSync deployment stopped by ${signal_name} before activation." >&2
  exit "$exit_status"
}

remaining_recovery_seconds() {
  local remaining=$((recovery_deadline - SECONDS))
  if (( remaining <= 0 )); then
    echo "CareSync recovery exceeded its ${recovery_budget_seconds}-second budget." >&2
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

fail_deployment_after_mutation() {
  local status="$1"
  shift
  echo "$*" >&2
  return "$status"
}

restore_database() {
  local dump_path="$1"
  run_bounded_recovery_command \
    systemctl stop "$service_name" "$push_service_name" 2>/dev/null || return 1
  run_bounded_recovery_command \
    runuser -u postgres -- dropdb --if-exists --force caresync || return 1
  run_bounded_recovery_command \
    runuser -u postgres -- createdb \
      --template=template0 \
      --encoding=UTF8 \
      --owner=postgres \
      caresync ||
    return 1
  run_bounded_recovery_command runuser -u postgres -- pg_restore \
    --exit-on-error \
    --single-transaction \
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
  } | run_maybe_bounded_command \
        runuser -u postgres -- psql \
          --no-psqlrc \
          --set=ON_ERROR_STOP=1 \
          --dbname=caresync \
          >/dev/null
}

certify_first_activation_security_baseline() {
  run_maybe_bounded_command runuser -u postgres -- psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname=postgres \
    >/dev/null <<'SQL'
DO $certify_first_activation$
DECLARE
  database_oid oid;
  database_owner oid;
  database_allows_connections boolean;
  database_connection_limit integer;
  app_role oid;
  command_owner_role oid;
  ingest_role oid;
BEGIN
  SELECT oid,datdba,datallowconn,datconnlimit
    INTO database_oid,database_owner,
         database_allows_connections,database_connection_limit
    FROM pg_catalog.pg_database
   WHERE datname='caresync';
  SELECT oid INTO app_role
    FROM pg_catalog.pg_authid
   WHERE rolname='caresync_basic_app';
  SELECT oid INTO command_owner_role
    FROM pg_catalog.pg_authid
   WHERE rolname='caresync_transport_command_owner';
  SELECT oid INTO ingest_role
    FROM pg_catalog.pg_authid
   WHERE rolname='caresync_transport_evidence_ingest';

  IF database_oid IS NULL
     OR database_owner<>(
       SELECT oid FROM pg_catalog.pg_roles WHERE rolname='postgres'
     )
     OR NOT database_allows_connections
     OR database_connection_limit<>-1
     OR app_role IS NULL
     OR command_owner_role IS NULL
     OR ingest_role IS NULL THEN
    RAISE EXCEPTION 'first-activation database or role identity is incomplete';
  END IF;

  IF 3<>(
    SELECT count(*)
      FROM pg_catalog.pg_authid AS identity
      JOIN pg_catalog.pg_roles AS configuration
        ON configuration.oid=identity.oid
     WHERE identity.rolname IN (
       'caresync_basic_app',
       'caresync_transport_command_owner',
       'caresync_transport_evidence_ingest'
     )
       AND NOT identity.rolsuper
       AND NOT identity.rolinherit
       AND NOT identity.rolcreaterole
       AND NOT identity.rolcreatedb
       AND NOT identity.rolreplication
       AND NOT identity.rolbypassrls
       AND identity.rolconnlimit=-1
       AND identity.rolvaliduntil IS NULL
       AND identity.rolcanlogin=(
         identity.rolname IN (
           'caresync_basic_app',
           'caresync_transport_evidence_ingest'
         )
       )
       AND (
         (
           identity.rolname IN (
             'caresync_basic_app',
             'caresync_transport_evidence_ingest'
           )
           AND identity.rolpassword IS NOT NULL
           AND configuration.rolconfig=
             ARRAY['search_path=public, pg_catalog']::text[]
         )
         OR (
           identity.rolname='caresync_transport_command_owner'
           AND identity.rolpassword IS NULL
           AND configuration.rolconfig IS NULL
         )
       )
  ) THEN
    RAISE EXCEPTION 'first-activation role attributes differ from provisioned baseline';
  END IF;

  IF 3<>(
    SELECT count(*)
      FROM pg_catalog.pg_roles
     WHERE pg_catalog.left(rolname,9)='caresync_'
       AND rolname IN (
         'caresync_basic_app',
         'caresync_transport_command_owner',
         'caresync_transport_evidence_ingest'
       )
  ) OR EXISTS (
    SELECT 1
      FROM pg_catalog.pg_roles
     WHERE pg_catalog.left(rolname,9)='caresync_'
       AND rolname NOT IN (
         'caresync_basic_app',
         'caresync_transport_command_owner',
         'caresync_transport_evidence_ingest'
       )
  ) THEN
    RAISE EXCEPTION 'first-activation CareSync role inventory differs from provisioned baseline';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM pg_catalog.pg_auth_members AS membership
      JOIN pg_catalog.pg_roles AS granted_role
        ON granted_role.oid=membership.roleid
      JOIN pg_catalog.pg_roles AS member_role
        ON member_role.oid=membership.member
     WHERE granted_role.rolname IN (
             'caresync_basic_app',
             'caresync_transport_command_owner',
             'caresync_transport_evidence_ingest'
           )
        OR member_role.rolname IN (
             'caresync_basic_app',
             'caresync_transport_command_owner',
             'caresync_transport_evidence_ingest'
           )
  ) THEN
    RAISE EXCEPTION 'first-activation role memberships differ from provisioned baseline';
  END IF;

  IF EXISTS (
    SELECT 1
      FROM pg_catalog.pg_db_role_setting AS setting
      JOIN pg_catalog.pg_roles AS role ON role.oid=setting.setrole
     WHERE role.rolname IN (
       'caresync_basic_app',
       'caresync_transport_command_owner',
       'caresync_transport_evidence_ingest'
     )
       AND setting.setdatabase<>0
  ) THEN
    RAISE EXCEPTION 'first-activation database-specific role settings are present';
  END IF;

  IF 5<>(
    SELECT count(*)
      FROM pg_catalog.aclexplode(
        COALESCE(
          (SELECT datacl FROM pg_catalog.pg_database WHERE oid=database_oid),
          pg_catalog.acldefault('d',database_owner)
        )
      ) AS privilege
     WHERE (
       privilege.grantee=database_owner
       AND privilege.privilege_type IN ('CONNECT','CREATE','TEMPORARY')
       AND NOT privilege.is_grantable
     ) OR (
       privilege.grantee IN (app_role,ingest_role)
       AND privilege.privilege_type='CONNECT'
       AND NOT privilege.is_grantable
       AND privilege.grantor=database_owner
     )
  ) OR 5<>(
    SELECT count(*)
      FROM pg_catalog.aclexplode(
        COALESCE(
          (SELECT datacl FROM pg_catalog.pg_database WHERE oid=database_oid),
          pg_catalog.acldefault('d',database_owner)
        )
      )
  ) THEN
    RAISE EXCEPTION 'first-activation database ACL differs from provisioned baseline';
  END IF;
END
$certify_first_activation$;
SQL
  run_maybe_bounded_command runuser -u postgres -- psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname=caresync \
    >/dev/null <<'SQL'
DO $certify_first_activation_contents$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid=relation.relnamespace
     WHERE namespace.nspname='public'
       AND relation.relkind IN ('r','p')
  ) THEN
    RAISE EXCEPTION 'first-activation database contents are not empty';
  END IF;
END
$certify_first_activation_contents$;
SQL
}

restore_first_activation_security_baseline() {
  run_bounded_recovery_command runuser -u postgres -- psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname=caresync \
    >/dev/null <<'SQL'
DO $restore_first_activation_roles$
DECLARE
  role_to_restore record;
BEGIN
  -- The database was already recreated from the sealed pre-deploy dump.  Clear
  -- every dependency in that database, then recreate the complete CareSync
  -- role inventory.  Re-creation restores catalog defaults such as a NULL
  -- validity deadline as well as removing memberships and role settings.
  FOR role_to_restore IN
    SELECT role.rolname
      FROM pg_catalog.pg_roles AS role
     WHERE pg_catalog.left(role.rolname,9)='caresync_'
     ORDER BY role.rolname
  LOOP
    EXECUTE pg_catalog.format(
      'REASSIGN OWNED BY %I TO postgres',
      role_to_restore.rolname
    );
    EXECUTE pg_catalog.format(
      'DROP OWNED BY %I',
      role_to_restore.rolname
    );
    EXECUTE pg_catalog.format(
      'DROP ROLE %I',
      role_to_restore.rolname
    );
  END LOOP;
END
$restore_first_activation_roles$;

CREATE ROLE caresync_basic_app
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS
  CONNECTION LIMIT -1;
ALTER ROLE caresync_basic_app SET search_path = public, pg_catalog;

CREATE ROLE caresync_transport_command_owner
  NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS
  CONNECTION LIMIT -1;

CREATE ROLE caresync_transport_evidence_ingest
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS
  CONNECTION LIMIT -1;
ALTER ROLE caresync_transport_evidence_ingest
  SET search_path = public, pg_catalog;

ALTER DATABASE caresync
  ALLOW_CONNECTIONS true
  CONNECTION LIMIT -1;
ALTER DATABASE caresync OWNER TO postgres;
REVOKE ALL PRIVILEGES ON DATABASE caresync FROM PUBLIC;
REVOKE ALL PRIVILEGES ON DATABASE caresync
  FROM caresync_basic_app,
       caresync_transport_command_owner,
       caresync_transport_evidence_ingest;
GRANT CONNECT ON DATABASE caresync TO caresync_basic_app;
GRANT CONNECT ON DATABASE caresync TO caresync_transport_evidence_ingest;
SQL
  bind_runtime_passwords || return
  certify_first_activation_security_baseline
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

normalize_ocr_runtime_permissions() {
  local runtime_path="$1"
  chown -R root:caresync "$runtime_path" || return
  chmod -R u=rwX,g=rX,o= "$runtime_path" || return
  find "$runtime_path/bin" -type f -exec chmod 0750 {} + || return
}

certify_ocr_shared_directory() {
  local directory_path="$1"
  local expected_metadata="$2"
  [[ -d "$directory_path" && ! -L "$directory_path" ]] || return
  [[ "$(stat -c '%U:%G:%a' -- "$directory_path")" == "$expected_metadata" ]]
}

certify_ocr_runtime_permissions() {
  local runtime_path="$1"
  local resolved_runtime unsafe_path
  resolved_runtime="$(readlink -f -- "$runtime_path")" || return
  case "$resolved_runtime" in
    "$ocr_versions_root"/lock-v1-*) ;;
    *) return 1 ;;
  esac
  [[ -d "$resolved_runtime" && ! -L "$resolved_runtime" ]] || return
  [[ "$(stat -c '%U:%G:%a' -- "$ocr_root")" == "root:caresync:750" ]] ||
    return
  [[ "$(stat -c '%U:%G:%a' -- "$ocr_versions_root")" == \
     "root:caresync:750" ]] || return

  unsafe_path="$(
    find "$resolved_runtime" -xdev \
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
    find "$resolved_runtime/bin" -xdev -type f ! -perm -0050 -print -quit
  )" || return
  [[ -z "$unsafe_path" ]]
}

validate_ocr_runtime() {
  local runtime_path="$1"
  certify_ocr_runtime_permissions "$runtime_path" || return
  runuser -u caresync -- test -x "$runtime_path/bin/python" || return
  (
    cd "$ocr_home" || exit
    runuser -u caresync -- env \
      HOME="$ocr_home" \
      XDG_CACHE_HOME="$ocr_home/cache" \
      PADDLE_PDX_CACHE_HOME="$ocr_home/paddlex" \
      PADDLE_HOME="$ocr_home/paddle" \
      "$runtime_path/bin/python" -m pip check || exit
    runuser -u caresync -- env \
      HOME="$ocr_home" \
      XDG_CACHE_HOME="$ocr_home/cache" \
      PADDLE_PDX_CACHE_HOME="$ocr_home/paddlex" \
      PADDLE_HOME="$ocr_home/paddle" \
      "$runtime_path/bin/python" \
        "$release_path/backend/scripts/certify_ocr_runtime.py" \
        "$ocr_lock_path"
  )
}

capture_ocr_runtime_baseline() {
  local resolved_target
  if [[ -L "$ocr_root/.venv" ]]; then
    ocr_previous_runtime_kind="symlink"
    ocr_previous_runtime_target="$(readlink -- "$ocr_root/.venv")" || return
    resolved_target="$(readlink -f -- "$ocr_root/.venv")" || return
    case "$resolved_target" in
      "$ocr_versions_root"/*) ;;
      *)
        echo "The active CareSync OCR symlink points outside its version store." >&2
        return 1
        ;;
    esac
    [[ -d "$resolved_target" ]] || return
  elif [[ -e "$ocr_root/.venv" ]]; then
    if [[ ! -d "$ocr_root/.venv" ]]; then
      echo "The CareSync OCR runtime path has an unsupported type." >&2
      return 1
    fi
    ocr_previous_runtime_kind="directory"
    ocr_previous_runtime_identity="$(
      stat -c '%d:%i' -- "$ocr_root/.venv"
    )" || return
    ocr_legacy_rollback="$ocr_versions_root/legacy-before-${release_sha}-$$"
    [[ ! -e "$ocr_legacy_rollback" && ! -L "$ocr_legacy_rollback" ]] || return
  else
    ocr_previous_runtime_kind="absent"
  fi

  if [[ -L "$ocr_root/requirements.sha256" ]]; then
    echo "The CareSync OCR requirements identity must not be a symlink." >&2
    return 1
  elif [[ -e "$ocr_root/requirements.sha256" ]]; then
    if [[ ! -f "$ocr_root/requirements.sha256" ]]; then
      echo "The CareSync OCR requirements identity has an unsupported type." >&2
      return 1
    fi
    cp -a -- "$ocr_root/requirements.sha256" "$ocr_previous_hash_backup" ||
      return
    ocr_previous_hash_present=1
  else
    ocr_previous_hash_present=0
  fi
}

certify_ocr_runtime_baseline() {
  local current_identity
  case "$ocr_previous_runtime_kind" in
    symlink)
      [[ -L "$ocr_root/.venv" ]] || return
      [[ "$(readlink -- "$ocr_root/.venv")" == \
         "$ocr_previous_runtime_target" ]] || return
      ;;
    directory)
      [[ -d "$ocr_root/.venv" && ! -L "$ocr_root/.venv" ]] || return
      current_identity="$(stat -c '%d:%i' -- "$ocr_root/.venv")" || return
      [[ "$current_identity" == "$ocr_previous_runtime_identity" ]] || return
      ;;
    absent)
      [[ ! -e "$ocr_root/.venv" && ! -L "$ocr_root/.venv" ]] || return
      ;;
    *)
      return 1
      ;;
  esac

  if [[ "$ocr_previous_hash_present" -eq 1 ]]; then
    [[ -f "$ocr_previous_hash_backup" ]] || return
    [[ -f "$ocr_root/requirements.sha256" ]] || return
    [[ ! -L "$ocr_root/requirements.sha256" ]] || return
    cmp -s -- "$ocr_previous_hash_backup" "$ocr_root/requirements.sha256" ||
      return
  else
    [[ ! -e "$ocr_root/requirements.sha256" &&
       ! -L "$ocr_root/requirements.sha256" ]] || return
  fi
}

ocr_runtime_matches_expected() {
  local active_target
  [[ -L "$ocr_root/.venv" ]] || return
  active_target="$(readlink -f -- "$ocr_root/.venv")" || return
  [[ "$active_target" == "$ocr_candidate" ]] || return
  [[ -f "$ocr_root/requirements.sha256" ]] || return
  [[ ! -L "$ocr_root/requirements.sha256" ]] || return
  cmp -s -- "$ocr_expected_hash_file" "$ocr_root/requirements.sha256" ||
    return
  validate_ocr_runtime "$ocr_root/.venv"
}

activate_ocr_runtime() {
  local pointer_next="$ocr_root/.venv.next.$$"
  local hash_next="$ocr_root/.requirements.sha256.next.$$"

  if ocr_runtime_matches_expected; then
    return 0
  fi
  certify_ocr_runtime_baseline || return
  ocr_mutated=1

  if [[ "$ocr_previous_runtime_kind" == "directory" ]]; then
    mv -T -- "$ocr_root/.venv" "$ocr_legacy_rollback" || return
  fi
  rm -f -- "$pointer_next" "$hash_next" || return
  ln -s -- "$ocr_candidate" "$pointer_next" || return
  mv -Tf -- "$pointer_next" "$ocr_root/.venv" || return

  cp -- "$ocr_expected_hash_file" "$hash_next" || return
  chown root:root "$hash_next" || return
  chmod 0644 "$hash_next" || return
  mv -Tf -- "$hash_next" "$ocr_root/requirements.sha256" || return
  ocr_runtime_matches_expected
}

restore_ocr_runtime_baseline() {
  local pointer_rollback="$ocr_root/.venv.rollback.$$"
  local hash_rollback="$ocr_root/.requirements.sha256.rollback.$$"
  local current_identity

  case "$ocr_previous_runtime_kind" in
    symlink)
      if [[ -e "$ocr_root/.venv" && ! -L "$ocr_root/.venv" ]]; then
        echo "CareSync OCR recovery found an unexpected runtime object." >&2
        return 1
      fi
      if [[ ! -L "$ocr_root/.venv" ]] ||
         [[ "$(readlink -- "$ocr_root/.venv")" != \
            "$ocr_previous_runtime_target" ]]; then
        run_bounded_recovery_command rm -f -- "$pointer_rollback" || return
        run_bounded_recovery_command \
          ln -s -- "$ocr_previous_runtime_target" "$pointer_rollback" ||
          return
        run_bounded_recovery_command \
          mv -Tf -- "$pointer_rollback" "$ocr_root/.venv" || return
      fi
      ;;
    directory)
      if [[ -d "$ocr_legacy_rollback" &&
            ! -L "$ocr_legacy_rollback" ]]; then
        if [[ -e "$ocr_root/.venv" && ! -L "$ocr_root/.venv" ]]; then
          echo "CareSync OCR recovery will not replace an unexpected directory." >&2
          return 1
        fi
        run_bounded_recovery_command rm -f -- "$ocr_root/.venv" || return
        run_bounded_recovery_command \
          mv -T -- "$ocr_legacy_rollback" "$ocr_root/.venv" || return
      else
        [[ -d "$ocr_root/.venv" && ! -L "$ocr_root/.venv" ]] || return
        current_identity="$(stat -c '%d:%i' -- "$ocr_root/.venv")" || return
        [[ "$current_identity" == "$ocr_previous_runtime_identity" ]] || return
      fi
      ;;
    absent)
      if [[ -e "$ocr_root/.venv" && ! -L "$ocr_root/.venv" ]]; then
        echo "CareSync OCR recovery will not remove an unexpected object." >&2
        return 1
      fi
      run_bounded_recovery_command rm -f -- "$ocr_root/.venv" || return
      ;;
    *)
      return 1
      ;;
  esac

  if [[ "$ocr_previous_hash_present" -eq 1 ]]; then
    [[ -f "$ocr_previous_hash_backup" ]] || return
    if [[ -e "$ocr_root/requirements.sha256" &&
          ! -f "$ocr_root/requirements.sha256" ]] ||
       [[ -L "$ocr_root/requirements.sha256" ]]; then
      echo "CareSync OCR recovery found an unsafe requirements identity." >&2
      return 1
    fi
    run_bounded_recovery_command rm -f -- "$hash_rollback" || return
    run_bounded_recovery_command \
      cp -a -- "$ocr_previous_hash_backup" "$hash_rollback" || return
    run_bounded_recovery_command \
      mv -Tf -- "$hash_rollback" "$ocr_root/requirements.sha256" || return
  else
    if [[ -L "$ocr_root/requirements.sha256" ]] ||
       [[ -e "$ocr_root/requirements.sha256" &&
          ! -f "$ocr_root/requirements.sha256" ]]; then
      echo "CareSync OCR recovery will not remove an unsafe requirements identity." >&2
      return 1
    fi
    if [[ -f "$ocr_root/requirements.sha256" ]]; then
      cmp -s -- "$ocr_expected_hash_file" "$ocr_root/requirements.sha256" ||
        return
      run_bounded_recovery_command \
        rm -f -- "$ocr_root/requirements.sha256" || return
    fi
  fi
  certify_ocr_runtime_baseline
}

certify_first_activation_recovery() {
  if [[ "$first_activation" -ne 1 ]] ||
     [[ -n "$previous_target" ]] ||
     [[ -e "$current_link" ]] ||
     [[ -L "$current_link" ]] ||
     [[ "$api_was_active" -ne 0 ]] ||
     [[ "$push_was_active" -ne 0 ]] ||
     [[ "$api_initial_state" != "inactive" ]] ||
     [[ "$push_initial_state" != "inactive" ]]; then
    echo "First-activation recovery geometry is not the captured baseline." >&2
    return 1
  fi
  if ! certify_services_inactive_during_recovery; then
    echo "First-activation recovery left a service active." >&2
    return 1
  fi
  run_bounded_recovery_command \
    runuser -u postgres -- pg_isready --dbname=caresync --quiet || return
  certify_first_activation_security_baseline || return
  if [[ "$migration_started" -eq 1 ]]; then
    if [[ "$recovery_database_restored" -ne 1 ]] ||
       [[ -z "$backup_path" ]] ||
       [[ ! -s "$backup_path/database.dump" ]] ||
       [[ ! -s "$backup_path/SHA256SUMS" ]]; then
      echo "First-activation database restoration lacks sealed evidence." >&2
      return 1
    fi
    (
      cd "$backup_path" || exit
      run_bounded_recovery_command \
        sha256sum --check --strict SHA256SUMS >/dev/null
    ) || return
  fi
}

recover_failed_deployment() {
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
    echo "FATAL: CareSync recovery was interrupted recursively." >&2
    exit 71
  fi
  recovery_active=1
  recovery_deadline=$((SECONDS + recovery_budget_seconds))
  trap - ERR
  trap 'recovery_interrupted=1' INT TERM HUP
  set +e
  echo "CareSync deployment stopped by ${recovery_cause}; attempting certified recovery." >&2
  if [[ "$live_mutation_started" -eq 0 ]]; then
    if [[ "$traffic_gate_mutated" -eq 1 ]] &&
       ! deactivate_traffic_gate; then
      recovery_failed=1
    fi
    if ! cleanup; then
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
      echo "FATAL: CareSync could not certify recovery from traffic-gate activation; live services were not changed." >&2
      exit 71
    fi
    echo "CareSync traffic-gate activation was reversed before live state changed." >&2
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
  if [[ "$migration_started" -eq 1 && "$recovery_failed" -eq 0 ]]; then
    if [[ -z "$backup_path" ]] ||
       [[ ! -s "$backup_path/database.dump" ]] ||
       [[ ! -s "$backup_path/SHA256SUMS" ]] ||
       ! (
         cd "$backup_path" &&
         run_bounded_recovery_command \
           sha256sum --check --strict SHA256SUMS >/dev/null
       ) ||
       ! restore_database "$backup_path/database.dump"; then
      recovery_failed=1
    else
      recovery_database_restored=1
    fi
    if [[ "$recovery_failed" -eq 0 && "$first_activation" -eq 1 ]]; then
      if ! restore_first_activation_security_baseline; then
        recovery_failed=1
      fi
    elif [[ -n "$previous_target" &&
            "$recovery_failed" -eq 0 &&
            -f "$previous_target/backend/scripts/bootstrap_basic_runtime_role.sql" ]]; then
      if ! run_bounded_recovery_command runuser -u postgres -- psql \
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
  if [[ "$ocr_mutated" -eq 1 ]] &&
     ! restore_ocr_runtime_baseline; then
    recovery_failed=1
  fi
  if [[ -n "$previous_target" && -d "$previous_target" ]]; then
    if ! run_bounded_recovery_command \
         ln -sfn "$previous_target" "$current_link.rollback" ||
       ! run_bounded_recovery_command \
         mv -Tf "$current_link.rollback" "$current_link" ||
       ! run_bounded_recovery_command systemctl daemon-reload; then
      recovery_failed=1
    fi
    if [[ "$api_was_active" -eq 1 && "$recovery_failed" -eq 0 ]]; then
      if ! run_bounded_recovery_command systemctl start "$service_name" ||
         ! certify_local_health; then
        recovery_failed=1
      fi
    fi
  else
    if [[ -e "$current_link" ]] || [[ -L "$current_link" ]]; then
      if [[ -d "$current_link" && ! -L "$current_link" ]] ||
         ! run_bounded_recovery_command rm -f -- "$current_link"; then
        recovery_failed=1
      fi
    fi
    if [[ "$recovery_failed" -eq 0 ]] &&
       ! certify_first_activation_recovery; then
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
  if ! cleanup; then
    recovery_failed=1
  fi
  if [[ "$recovery_failed" -ne 0 ]]; then
    echo "FATAL: CareSync automatic recovery could not fully certify the prior state; operator attention is required." >&2
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
  if [[ "$first_activation" -eq 1 ]]; then
    echo "CareSync first-activation baseline was restored and certified." >&2
  else
    echo "CareSync pre-deployment state was restored and certified." >&2
  fi
  if [[ "$recovery_interrupted" -eq 1 ]]; then
    echo "A terminal signal was deferred until CareSync recovery completed." >&2
  fi
  trap - INT TERM HUP
  exit "$exit_status"
}

trap cleanup EXIT
trap 'abort_before_mutation 130 INT' INT
trap 'abort_before_mutation 143 TERM' TERM
trap 'abort_before_mutation 129 HUP' HUP

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
production_hostname="$(
  python3 - "$configured_origin" <<'PY'
import sys
from urllib.parse import urlsplit
print(urlsplit(sys.argv[1]).hostname or "")
PY
)"
if [[ -z "$production_hostname" ]]; then
  echo "CareSync production hostname is invalid." >&2
  exit 65
fi
if [[ -e "$maintenance_flag" || -L "$maintenance_flag" ]]; then
  echo "CareSync is already in operator maintenance mode." >&2
  exit 66
fi

if [[ -L "$current_link" ]]; then
  previous_target="$(readlink -f "$current_link" 2>/dev/null || true)"
  previous_release_name="${previous_target##*/}"
  if [[ -z "$previous_target" ]] ||
     [[ ! "$previous_release_name" =~ ^[0-9a-f]{40}$ ]] ||
     [[ "$previous_target" != "$releases_root/$previous_release_name" ]] ||
     [[ ! -d "$previous_target" ]] ||
     [[ ! -f "$previous_target/release-manifest.json" ]] ||
     [[ ! -f "$previous_target/backend/scripts/bootstrap_basic_runtime_role.sql" ]]; then
    echo "The active CareSync release cannot be identified safely." >&2
    exit 66
  fi
  previous_manifest_sha="$(
    python3 - "$previous_target/release-manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("git_sha", ""))
PY
  )"
  if [[ "$previous_manifest_sha" != "$previous_release_name" ]]; then
    echo "The active CareSync release manifest does not match its path." >&2
    exit 66
  fi
elif [[ -e "$current_link" ]]; then
  echo "The CareSync current path is not an approved release symlink." >&2
  exit 66
else
  first_activation=1
fi

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
if [[ "$first_activation" -eq 1 ]] &&
   { [[ "$api_initial_state" != "inactive" ]] ||
     [[ "$push_initial_state" != "inactive" ]]; }; then
  echo "First activation requires both CareSync services to be inactive." >&2
  exit 66
fi

if [[ -e "$release_path" ]]; then
  if [[ "$previous_target" == "$release_path" ]]; then
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
    release_already_active=1
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

cd "$release_path/backend"
if [[ "$release_already_active" -eq 0 ]]; then
  export UV_PROJECT_ENVIRONMENT="$release_path/backend/.venv"
  export UV_CACHE_DIR="/var/cache/caresync/uv"
  /usr/local/bin/uv sync --frozen --no-dev --python /usr/bin/python3.12
  "$release_path/backend/.venv/bin/python" -m compileall -q \
    "$release_path/backend/app"
fi

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

if [[ "$release_already_active" -eq 0 ]]; then
  chown -R root:caresync "$release_path"
  find "$release_path" -type d -exec chmod 0755 {} +
  find "$release_path" -type f -exec chmod 0644 {} +
  find "$release_path/backend/.venv/bin" -type f -exec chmod 0755 {} +
  find "$release_path/deploy/scripts" -type f -name '*.sh' -exec chmod 0755 {} +
fi

readonly ocr_lock_path="$release_path/backend/scripts/ocr-requirements-linux-x86_64-cp312.lock"
expected_ocr_requirements_sha="$(
  sha256sum "$ocr_lock_path" | awk '{print $1}'
)"
ocr_candidate="$ocr_versions_root/lock-v1-$expected_ocr_requirements_sha"
printf '%s\n' "$expected_ocr_requirements_sha" > "$ocr_expected_hash_file"

if [[ "$first_activation" -eq 1 ]]; then
  install -d -o root -g caresync -m 0750 "$ocr_root" "$ocr_versions_root"
  install -d -o caresync -g caresync -m 0700 \
    "$ocr_home" \
    "$ocr_home/cache" \
    "$ocr_home/paddlex" \
    "$ocr_home/paddle"
elif ! certify_ocr_shared_directory "$ocr_root" "root:caresync:750" ||
     ! certify_ocr_shared_directory \
       "$ocr_versions_root" "root:caresync:750" ||
     ! certify_ocr_shared_directory "$ocr_home" "caresync:caresync:700" ||
     ! certify_ocr_shared_directory \
       "$ocr_home/cache" "caresync:caresync:700" ||
     ! certify_ocr_shared_directory \
       "$ocr_home/paddlex" "caresync:caresync:700" ||
     ! certify_ocr_shared_directory \
       "$ocr_home/paddle" "caresync:caresync:700"; then
  echo "The active CareSync OCR directory geometry is not certified." >&2
  exit 65
fi
if [[ -L "$ocr_candidate" ]] ||
   [[ -e "$ocr_candidate" && ! -d "$ocr_candidate" ]]; then
  echo "The content-addressed CareSync OCR candidate has an unsafe type." >&2
  exit 65
elif [[ -d "$ocr_candidate" ]]; then
  if ! validate_ocr_runtime "$ocr_candidate"; then
    echo "The content-addressed CareSync OCR candidate is invalid." >&2
    exit 65
  fi
else
  ocr_candidate_stage="$(
    mktemp -d \
      "$ocr_versions_root/.candidate-lock-v1-${expected_ocr_requirements_sha}.XXXXXXXX"
  )"
  python3.12 -m venv "$ocr_candidate_stage"
  timeout \
    --foreground \
    --signal=TERM \
    --kill-after=30s \
    2400s \
    "$ocr_candidate_stage/bin/python" -m pip install \
      --disable-pip-version-check \
      --no-input \
      --only-binary=:all: \
      --require-hashes \
      --requirement "$ocr_lock_path"
  "$ocr_candidate_stage/bin/python" -m pip check
  normalize_ocr_runtime_permissions "$ocr_candidate_stage"
  validate_ocr_runtime "$ocr_candidate_stage"
  mv -T -- "$ocr_candidate_stage" "$ocr_candidate"
  ocr_candidate_stage=""
fi
capture_ocr_runtime_baseline

api_pre_gate_state="$(
  systemctl show --property=ActiveState --value "$service_name"
)"
push_pre_gate_state="$(
  systemctl show --property=ActiveState --value "$push_service_name"
)"
if [[ "$api_pre_gate_state" != "$api_initial_state" ||
      "$push_pre_gate_state" != "$push_initial_state" ]]; then
  echo "CareSync service state changed during deployment preflight." >&2
  exit 66
fi
if [[ "$release_already_active" -eq 1 ]] &&
   ocr_runtime_matches_expected; then
  if certify_local_health; then
    echo "CareSync release $release_sha is already active and healthy."
    exit 0
  fi
  echo "The requested release is active but unhealthy; entering controlled repair." >&2
fi
if [[ "$first_activation" -eq 1 ]]; then
  certify_first_activation_security_baseline
fi
nginx -t
# Only failures from this point forward need service/database recovery. Archive,
# dependency, and release-shape failures above must never disturb the active
# release.
trap 'recover_failed_deployment "$?" ERR' ERR
trap 'recover_failed_deployment 130 INT' INT
trap 'recover_failed_deployment 143 TERM' TERM
trap 'recover_failed_deployment 129 HUP' HUP
activate_traffic_gate
live_mutation_started=1
systemctl stop "$push_service_name" "$service_name" 2>/dev/null
if systemctl is-active --quiet "$service_name" ||
   systemctl is-active --quiet "$push_service_name"; then
  fail_deployment_after_mutation 70 \
    "CareSync services did not stop before backup."
fi

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
      upgrade 0043_org_wide_room_presence
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
  fail_deployment_after_mutation 70 \
    "CareSync database did not reach its certified revision."
fi

activate_ocr_runtime

ln -sfn "$release_path" "$current_link.next"
mv -Tf "$current_link.next" "$current_link"
systemctl daemon-reload
systemctl restart "$service_name"

if ! certify_local_health; then
  journalctl -u "$service_name" --no-pager -n 40 >&2 || true
  fail_deployment_after_mutation 70 \
    "CareSync failed its post-deploy health gate."
fi

trap - ERR INT TERM HUP
post_commit_failed=0
if ! deactivate_traffic_gate; then
  echo "CareSync is healthy, but its public traffic gate did not reopen." >&2
  post_commit_failed=1
elif ! certify_public_health; then
  echo "CareSync is healthy locally, but public health certification failed." >&2
  post_commit_failed=1
fi
if ! systemctl reload nginx; then
  echo "CareSync is healthy, but nginx did not reload." >&2
  post_commit_failed=1
fi

if [[ "$post_commit_failed" -eq 0 ]] &&
   systemctl is-enabled --quiet "$push_service_name" 2>/dev/null; then
  if ! systemctl restart "$push_service_name"; then
    echo "CareSync is healthy, but the push worker did not restart." >&2
    post_commit_failed=1
  fi
fi

if ! (
  find "$releases_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
    sort -nr |
    awk 'NR > 5 {sub(/^[^ ]+ /, ""); print}' |
    while IFS= read -r old_release; do
      if [[ "$old_release" != "$release_path" &&
            "$old_release" != "$previous_target" ]]; then
        rm -rf -- "$old_release"
      fi
    done
); then
  echo "CareSync is healthy, but old release pruning needs attention." >&2
fi
if ! (
  find "$backup_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
    sort -nr |
    awk 'NR > 7 {sub(/^[^ ]+ /, ""); print}' |
    xargs -r rm -rf --
); then
  echo "CareSync is healthy, but old backup pruning needs attention." >&2
fi

if [[ "$post_commit_failed" -ne 0 ]]; then
  echo "CareSync core activation committed with a post-commit service warning." >&2
  exit 72
fi
echo "CareSync release $release_sha is healthy."
