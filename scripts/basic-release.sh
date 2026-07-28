#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/basic-runtime.sh
source "$ROOT/scripts/lib/basic-runtime.sh"

BACKUP_USER="${CARESYNC_BASIC_BACKUP_USER:-$MIGRATION_USER}"
BACKUP_PASSWORD="${CARESYNC_BASIC_BACKUP_PASSWORD:-}"
FAMILY_EVIDENCE_VAULT_PATH="$RUNTIME_DIR/private-family-authority-vault"
STAFF_SCREENING_VAULT_PATH="$RUNTIME_DIR/private-staff-screening-vault"
RUNTIME_SECRET_DIRECTORY="$RUNTIME_DIR/secrets"

# EXIT cleanup runs after prepare_release's dynamic local scope is gone on
# Bash 3.2. Preserve its exact recovery state in uniquely named script globals
# so explicit returns and unguarded `set -e` exits have identical cleanup.
PREPARE_CLEANUP_RUN_DIRECTORY=""
PREPARE_CLEANUP_RETAINED_FENCED=false
PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
PREPARE_CLEANUP_CANDIDATE_SEALED=false
PREPARE_CLEANUP_FENCE_CREATED=false

usage() {
  cat >&2 <<EOF
Usage:
  scripts/basic-release.sh prepare [--clone-port HIGH_PORT]
  scripts/basic-release.sh commit --receipt CANDIDATE_RECEIPT --confirm "$CARESYNC_RELEASE_COMMIT_PHRASE"
  scripts/basic-release.sh rollback --receipt CANDIDATE_RECEIPT \\
    --commit-receipt COMMIT_RECEIPT \\
    --finalization-receipt FINALIZATION_RECEIPT \\
    --confirm "$CARESYNC_RELEASE_ROLLBACK_PHRASE"
  scripts/basic-release.sh rollback --receipt CANDIDATE_RECEIPT \\
    --confirm "$CARESYNC_RELEASE_ROLLBACK_PHRASE"

prepare is non-promoting: it leaves the retained runtime fenced at exact 0039.
commit consumes that immutable receipt and is the only retained 0039-to-0042
migration path. Recovery at unchanged 0039 uses scripts/resume-basic-0039.sh.
The first rollback form is for a finalized commit and requires both finalized
receipts. The second is intent-only recovery after an interrupted commit: omit
both finalized-receipt flags, and the run must contain its exact durable
commit-attempt intent. Both forms restore the receipt-bound rehearsed physical
backup, quarantine the changed tree, and never invoke an Alembic downgrade.
EOF
}

backend_env() {
  local host="$1"
  local port="$2"
  local user="$3"
  local password="$4"
  shift 4
  local execution_root="${RELEASE_EXECUTION_ROOT:-$ROOT}"
  local release_probe_password=""
  if [[ -n "${RELEASE_PROBE_CREDENTIAL:-}" ]] && \
     [[ -f "$RELEASE_PROBE_CREDENTIAL" ]] && \
     [[ ! -L "$RELEASE_PROBE_CREDENTIAL" ]]; then
    release_probe_password="$(<"$RELEASE_PROBE_CREDENTIAL")" || return
  fi
  (
    cd "$execution_root/backend"
    CARESYNC_VENV_PATH="$VENV_PATH" \
    CARESYNC_PG_BIN="$PG_BIN" \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=development \
    DATABASE_TYPE=postgres \
    DATABASE_HOST="$host" \
    DATABASE_PORT="$port" \
    DATABASE_USER="$user" \
    DATABASE_PASSWORD="$password" \
    DATABASE_NAME="$DATABASE_NAME" \
    DATABASE_READ_ONLY=false \
    ENABLE_ADVANCED_ROUTES=false \
    CARESYNC_RELEASE_PROBE_PASSWORD="$release_probe_password" \
      /bin/bash ./scripts/uv.sh run "$@"
  )
}

durable_ensure_private_directory() {
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py ensure-private-directory \
      --path "$1" || return
}

durable_publish_private_file() {
  local source="$1"
  local destination="$2"
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py durable-publish-private-file \
      --source "$source" \
      --destination "$destination" || return
  if [[ -e "$source" ]] || [[ -L "$source" ]] || \
     [[ -L "$destination" ]] || [[ ! -f "$destination" ]] || \
     [[ "$(stat -f '%u' "$destination")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$destination")" != "600" ]] || \
     [[ "$(stat -f '%l' "$destination")" != "1" ]]; then
    basic_fail "Durable private-file publication postconditions failed"
    return
  fi
}

durable_replace_private_file() {
  local source="$1"
  local destination="$2"
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py durable-replace-private-file \
      --source "$source" \
      --destination "$destination" || return
  if [[ -e "$source" ]] || [[ -L "$source" ]] || \
     [[ -L "$destination" ]] || [[ ! -f "$destination" ]] || \
     [[ "$(stat -f '%u' "$destination")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$destination")" != "600" ]] || \
     [[ "$(stat -f '%l' "$destination")" != "1" ]]; then
    basic_fail "Durable private-file replacement postconditions failed"
    return
  fi
}

durable_rename_private_fence_no_replace() {
  local source="$1"
  local destination="$2"
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py durable-rename-private-fence \
      --source "$source" \
      --destination "$destination" || return
  if [[ -e "$source" ]] || [[ -L "$source" ]] || \
     [[ -L "$destination" ]] || [[ ! -d "$destination" ]] || \
     [[ "$(stat -f '%u' "$destination")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$destination")" != "700" ]]; then
    basic_fail "Durable private-fence rename postconditions failed"
    return
  fi
}

durability_barrier_private_tree() {
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py durability-barrier-private-tree \
      --path "$1" || return
}

durability_barrier_private_file() {
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py durability-barrier-private-file \
      --path "$1" || return
}

require_release_probe_credential() {
  local credential="$1"
  if [[ -L "$credential" ]] || [[ ! -f "$credential" ]] || \
     [[ "$(stat -f '%u' "$credential")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$credential")" != "600" ]] || \
     [[ "$(stat -f '%l' "$credential")" != "1" ]] || \
     [[ ! "$(<"$credential")" =~ ^[0-9a-f]{64}$ ]]; then
    basic_fail "Controlled-health probe credential is missing or unsafe"
    return
  fi
}

create_release_probe_credential() {
  local run_directory="$1"
  local credential="$run_directory/controlled-health-probe.credential"
  if [[ -e "$credential" ]] || [[ -L "$credential" ]]; then
    require_release_probe_credential "$credential" || return
    return
  fi
  local pending="$run_directory/.controlled-health-probe.pending.$$.$RANDOM"
  if ! (
    set -o noclobber
    "$VENV_PATH/bin/python" -c \
      'import secrets; print(secrets.token_hex(32))' >"$pending"
  ); then
    basic_fail "Could not generate the controlled-health probe credential"
    return
  fi
  chmod 600 "$pending" || return
  require_release_probe_credential "$pending" || return
  durable_publish_private_file "$pending" "$credential" || return
  require_release_probe_credential "$credential" || return
}

configure_release_probe() {
  local credential="$1"
  local port="${2:-$PGPORT}"
  require_release_probe_credential "$credential" || return
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X \
    -h 127.0.0.1 -p "$port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    --set="probe_password=$(<"$credential")" \
    --set="database_name=$DATABASE_NAME" \
    -f "${RELEASE_EXECUTION_ROOT:-$ROOT}/backend/scripts/configure_basic_release_probe.sql" \
    >/dev/null || return
  require_release_probe_contract nologin "$port" || return
  require_release_probe_read_scope closed "$port" || return
}

release_psql_scalar() {
  local port="$1"
  local sql="$2"
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "$sql" || return
}

require_release_probe_contract() {
  local expected_login="${1:-nologin}"
  local port="${2:-$PGPORT}"
  local state
  state="$(release_psql_scalar "$port" "
    SELECT concat_ws('|',
      CASE WHEN role.rolcanlogin THEN 'login' ELSE 'nologin' END,
      role.rolsuper::text, role.rolinherit::text, role.rolcreaterole::text,
      role.rolcreatedb::text, role.rolreplication::text,
      role.rolbypassrls::text,
      COALESCE((
        SELECT auth.rolpassword LIKE 'SCRAM-SHA-256\$%'
        FROM pg_catalog.pg_authid auth
        WHERE auth.oid=role.oid
      ),false)::text,
      (SELECT string_agg(setting,',' ORDER BY setting)
       FROM unnest(role.rolconfig) AS setting),
      (SELECT count(*)::text FROM pg_catalog.pg_auth_members membership
       WHERE membership.member=role.oid OR membership.roleid=role.oid),
      (SELECT count(*)::text FROM pg_catalog.pg_database database
       WHERE database.datdba=role.oid),
      (SELECT count(*)::text
       FROM pg_catalog.pg_class object
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=object.relnamespace
       WHERE namespace.nspname='public' AND object.relowner=role.oid),
      (SELECT count(*)::text FROM pg_catalog.pg_namespace namespace
       WHERE namespace.nspowner=role.oid),
      (SELECT count(*)::text
       FROM pg_catalog.pg_proc function
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=function.pronamespace
       WHERE namespace.nspname='public' AND function.proowner=role.oid),
      has_database_privilege(role.rolname,current_database(),'CONNECT')::text,
      has_database_privilege(role.rolname,current_database(),'CREATE')::text,
      has_schema_privilege(role.rolname,'public','USAGE')::text,
      has_schema_privilege(role.rolname,'public','CREATE')::text,
      (SELECT count(*)::text
       FROM pg_catalog.pg_class object
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=object.relnamespace
       WHERE namespace.nspname='public'
         AND object.relkind IN ('r','p','v','m','f')
         AND has_table_privilege(
           role.rolname,object.oid,
           'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
         )),
      (SELECT count(*)::text
       FROM pg_catalog.pg_attribute attribute
       JOIN pg_catalog.pg_class object
         ON object.oid=attribute.attrelid
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=object.relnamespace
       WHERE namespace.nspname='public'
         AND attribute.attnum>0 AND NOT attribute.attisdropped
         AND has_column_privilege(
           role.rolname,object.oid,attribute.attnum,
           'INSERT,UPDATE,REFERENCES'
         )),
      (SELECT count(*)::text
       FROM pg_catalog.pg_class object
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=object.relnamespace
       WHERE namespace.nspname='public'
         AND object.relkind='S'
         AND CASE
           WHEN object.relkind='S' THEN
             has_sequence_privilege(
               role.rolname,object.oid,'USAGE,UPDATE'
             )
           ELSE false
         END),
      (SELECT count(*)::text
       FROM pg_catalog.pg_proc function
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=function.pronamespace
       WHERE namespace.nspname='public'
         AND function.prosecdef
         AND has_function_privilege(role.rolname,function.oid,'EXECUTE')),
      (SELECT count(*)::text
       FROM pg_catalog.pg_default_acl defaults
       CROSS JOIN LATERAL pg_catalog.aclexplode(defaults.defaclacl) grant_entry
       WHERE grant_entry.grantee=role.oid)
    )
    FROM pg_catalog.pg_roles role
    WHERE role.rolname='$RELEASE_PROBE_USER'
  ")" || return
  if [[ "$state" != \
    "$expected_login|false|false|false|false|false|false|true|default_transaction_read_only=on,lock_timeout=2s,search_path=pg_catalog, public,statement_timeout=15s|0|0|0|0|0|true|false|true|false|0|0|0|0|0" ]]; then
    basic_fail \
      "Controlled-health probe has effective write, ownership, membership, or escalation capability"
    return
  fi
}

release_probe_read_scope_state() {
  local port="${1:-$PGPORT}"
  release_psql_scalar "$port" "
    SELECT concat_ws('|',
      (SELECT count(*)::text
       FROM pg_catalog.pg_class relation
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=relation.relnamespace
       CROSS JOIN LATERAL pg_catalog.aclexplode(
         COALESCE(
           relation.relacl,
           pg_catalog.acldefault(
             CASE WHEN relation.relkind='S' THEN 's'::\"char\"
                  ELSE 'r'::\"char\" END,
             relation.relowner
           )
         )
       ) grant_entry
       WHERE namespace.nspname='public'
         AND grant_entry.grantee=role.oid),
      (SELECT count(*)::text
       FROM pg_catalog.pg_attribute attribute
       JOIN pg_catalog.pg_class relation
         ON relation.oid=attribute.attrelid
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=relation.relnamespace
       CROSS JOIN LATERAL pg_catalog.aclexplode(
         COALESCE(
           attribute.attacl,
           pg_catalog.acldefault('c',relation.relowner)
         )
       ) grant_entry
       WHERE namespace.nspname='public'
         AND attribute.attnum>0
         AND NOT attribute.attisdropped
         AND grant_entry.grantee=role.oid),
      (SELECT count(*)::text
       FROM pg_catalog.pg_attribute attribute
       JOIN pg_catalog.pg_class relation
         ON relation.oid=attribute.attrelid
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=relation.relnamespace
       WHERE namespace.nspname='public'
         AND relation.relkind IN ('r','p','v','m','f')
         AND attribute.attnum>0
         AND NOT attribute.attisdropped),
      (SELECT count(*)::text
       FROM pg_catalog.pg_attribute attribute
       JOIN pg_catalog.pg_class relation
         ON relation.oid=attribute.attrelid
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=relation.relnamespace
       CROSS JOIN LATERAL pg_catalog.aclexplode(
         COALESCE(
           attribute.attacl,
           pg_catalog.acldefault('c',relation.relowner)
         )
       ) grant_entry
       WHERE namespace.nspname='public'
         AND attribute.attnum>0
         AND NOT attribute.attisdropped
         AND grant_entry.grantee=role.oid
         AND (
           relation.relkind NOT IN ('r','p','v','m','f')
           OR grant_entry.privilege_type<>'SELECT'
           OR grant_entry.is_grantable
         )),
      (SELECT count(*)::text
       FROM pg_catalog.pg_attribute attribute
       JOIN pg_catalog.pg_class relation
         ON relation.oid=attribute.attrelid
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=relation.relnamespace
       WHERE namespace.nspname='public'
         AND relation.relkind IN ('r','p','v','m','f')
         AND attribute.attnum>0
         AND NOT attribute.attisdropped
         AND NOT EXISTS (
           SELECT 1
           FROM pg_catalog.aclexplode(
             COALESCE(
               attribute.attacl,
               pg_catalog.acldefault('c',relation.relowner)
             )
           ) grant_entry
           WHERE grant_entry.grantee=role.oid
             AND grant_entry.privilege_type='SELECT'
             AND NOT grant_entry.is_grantable
         )),
      (SELECT count(*)::text
       FROM pg_catalog.pg_proc function
       JOIN pg_catalog.pg_namespace namespace
         ON namespace.oid=function.pronamespace
       CROSS JOIN LATERAL pg_catalog.aclexplode(
         COALESCE(
           function.proacl,
           pg_catalog.acldefault('f',function.proowner)
         )
       ) grant_entry
       WHERE namespace.nspname='public'
         AND grant_entry.grantee=role.oid)
    )
    FROM pg_catalog.pg_roles role
    WHERE role.rolname='$RELEASE_PROBE_USER'
  " || return
}

require_release_probe_read_scope() {
  local expected="$1"
  local port="${2:-$PGPORT}"
  local state
  state="$(release_probe_read_scope_state "$port")" || return
  local relation_grants column_grants expected_columns
  local invalid_column_grants missing_column_grants function_grants
  IFS='|' read -r \
    relation_grants column_grants expected_columns \
    invalid_column_grants missing_column_grants function_grants <<<"$state"
  if [[ -z "$expected_columns" ]] || [[ ! "$expected_columns" =~ ^[0-9]+$ ]] || \
     (( expected_columns == 0 )); then
    basic_fail "Controlled-health probe read scope has no released columns"
    return 1
  fi
  case "$expected" in
    closed)
      if [[ "$relation_grants" != "0" ]] || \
         [[ "$column_grants" != "0" ]] || \
         [[ "$invalid_column_grants" != "0" ]] || \
         [[ "$missing_column_grants" != "$expected_columns" ]] || \
         [[ "$function_grants" != "0" ]]; then
        basic_fail "Controlled-health probe is not in its closed read scope"
        return 1
      fi
      ;;
    open)
      if [[ "$relation_grants" != "0" ]] || \
         [[ "$column_grants" != "$expected_columns" ]] || \
         [[ "$invalid_column_grants" != "0" ]] || \
         [[ "$missing_column_grants" != "0" ]] || \
         [[ "$function_grants" != "0" ]]; then
        basic_fail \
          "Controlled-health probe does not have its exact column-read scope"
        return 1
      fi
      ;;
    *)
      basic_fail "Invalid controlled-health probe read scope"
      return
      ;;
  esac
}

scrub_release_probe_object_privileges() {
  local port="${1:-$PGPORT}"
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X \
    -h 127.0.0.1 -p "$port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    >/dev/null <<'SQL'
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public
  FROM caresync_release_probe;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public
  FROM caresync_release_probe;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public
  FROM caresync_release_probe;
DO $release_probe_column_acl_scrub$
DECLARE
  target record;
BEGIN
  FOR target IN
    SELECT namespace.nspname,
           relation.relname,
           pg_catalog.string_agg(
             pg_catalog.quote_ident(attribute.attname),
             ',' ORDER BY attribute.attnum
           ) AS column_list
    FROM pg_catalog.pg_attribute AS attribute
    JOIN pg_catalog.pg_class AS relation
      ON relation.oid=attribute.attrelid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid=relation.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(
      COALESCE(
        attribute.attacl,
        pg_catalog.acldefault('c',relation.relowner)
      )
    ) AS grant_entry
    WHERE namespace.nspname='public'
      AND relation.relkind IN ('r','p','v','m','f')
      AND attribute.attnum>0
      AND NOT attribute.attisdropped
      AND grant_entry.grantee=
          pg_catalog.to_regrole('caresync_release_probe')
    GROUP BY namespace.nspname,relation.relname
  LOOP
    EXECUTE pg_catalog.format(
      'REVOKE ALL PRIVILEGES (%s) ON TABLE %I.%I FROM caresync_release_probe',
      target.column_list,
      target.nspname,
      target.relname
    );
  END LOOP;
END
$release_probe_column_acl_scrub$;
SQL
}

grant_release_probe_controlled_read() {
  local port="${1:-$PGPORT}"
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X \
    -h 127.0.0.1 -p "$port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    >/dev/null <<'SQL'
DO $release_probe_column_read$
DECLARE
  target record;
BEGIN
  FOR target IN
    SELECT namespace.nspname,
           relation.relname,
           pg_catalog.string_agg(
             pg_catalog.quote_ident(attribute.attname),
             ',' ORDER BY attribute.attnum
           ) AS column_list
    FROM pg_catalog.pg_attribute AS attribute
    JOIN pg_catalog.pg_class AS relation
      ON relation.oid=attribute.attrelid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid=relation.relnamespace
    WHERE namespace.nspname='public'
      AND relation.relkind IN ('r','p','v','m','f')
      AND attribute.attnum>0
      AND NOT attribute.attisdropped
    GROUP BY namespace.nspname,relation.relname
  LOOP
    EXECUTE pg_catalog.format(
      'GRANT SELECT (%s) ON TABLE %I.%I TO caresync_release_probe',
      target.column_list,
      target.nspname,
      target.relname
    );
  END LOOP;
END
$release_probe_column_read$;
SQL
}

set_release_probe_login_state() {
  local state="$1"
  local port="${2:-$PGPORT}"
  local clause
  case "$state" in
    login) clause=LOGIN ;;
    nologin) clause=NOLOGIN ;;
    *)
      basic_fail "Invalid controlled-health probe login state"
      return
      ;;
  esac
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X \
    -h 127.0.0.1 -p "$port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "ALTER ROLE $RELEASE_PROBE_USER $clause" >/dev/null || return
}

open_release_probe_for_controlled_health() {
  local port="${1:-$PGPORT}"
  if ! require_release_probe_contract nologin "$port" || \
     ! require_release_probe_read_scope closed "$port"; then
    close_release_probe_after_controlled_health "$port" || true
    return 1
  fi
  if ! grant_release_probe_controlled_read "$port"; then
    close_release_probe_after_controlled_health "$port" || true
    return 1
  fi
  if ! require_release_probe_read_scope open "$port"; then
    close_release_probe_after_controlled_health "$port" || true
    return 1
  fi
  if ! set_release_probe_login_state login "$port"; then
    close_release_probe_after_controlled_health "$port" || true
    return 1
  fi
  if ! require_release_probe_contract login "$port" || \
     ! require_release_probe_read_scope open "$port"; then
    close_release_probe_after_controlled_health "$port" || true
    return 1
  fi
}

close_release_probe_after_controlled_health() {
  local port="${1:-$PGPORT}"
  local failed=false
  set_release_probe_login_state nologin "$port" || failed=true
  scrub_release_probe_object_privileges "$port" || failed=true
  require_release_probe_contract nologin "$port" || failed=true
  require_release_probe_read_scope closed "$port" || failed=true
  if [[ "$failed" == "true" ]]; then
    basic_fail "Could not prove the controlled-health probe is fully closed"
    return 1
  fi
}

prove_release_probe_write_rejection() {
  local credential="$1"
  local port="${2:-$PGPORT}"
  require_release_probe_credential "$credential" || return
  local identity
  identity="$(PGPASSWORD="$(<"$credential")" \
    PGOPTIONS="-c default_transaction_read_only=on" \
    "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
      -h 127.0.0.1 -p "$port" -U "$RELEASE_PROBE_USER" \
      -d "$DATABASE_NAME" \
      -c "SELECT current_user || '|' || current_setting('transaction_read_only')"
  )" || return
  if [[ "$identity" != "$RELEASE_PROBE_USER|on" ]]; then
    basic_fail "Controlled-health probe login/read-only identity is invalid"
    return
  fi
  local write_error write_result
  if write_error="$(PGPASSWORD="$(<"$credential")" \
    PGOPTIONS="-c default_transaction_read_only=off" \
    "$PG_BIN/psql" -v ON_ERROR_STOP=1 --set=VERBOSITY=verbose -X \
      -h 127.0.0.1 -p "$port" -U "$RELEASE_PROBE_USER" \
      -d "$DATABASE_NAME" \
      -c "DELETE FROM public.alembic_version WHERE false" \
      2>&1)"; then
    basic_fail "Controlled-health probe unexpectedly acquired business DML"
    return
  else
    write_result=$?
  fi
  if (( write_result == 0 )) || [[ "$write_error" != *"42501"* ]]; then
    basic_fail \
      "Controlled-health probe write rejection was not an authorization denial"
    return
  fi
}

prove_release_probe_write_rejection_or_close() {
  local credential="$1"
  local port="${2:-$PGPORT}"
  if prove_release_probe_write_rejection "$credential" "$port"; then
    return 0
  fi
  close_release_probe_after_controlled_health "$port" || true
  return 1
}

require_high_clone_port() {
  local port="$1"
  if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 55000 || port > 60999 )); then
    basic_fail "Disposable clone port must be an integer from 55000 through 60999"
    return
  fi
  case "$port" in
    5432|5433|5434)
      basic_fail "Protected PostgreSQL ports can never be release-restore targets"
      return
      ;;
  esac
  if lsof -nP -iTCP:"$port" >/dev/null 2>&1 || \
     "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$port" -q; then
    basic_fail "Disposable clone port $port is already in use"
    return
  fi
}

select_clone_port() {
  if [[ -n "${CARESYNC_BASIC_RELEASE_CLONE_PORT:-}" ]]; then
    require_high_clone_port "$CARESYNC_BASIC_RELEASE_CLONE_PORT"
    printf '%s\n' "$CARESYNC_BASIC_RELEASE_CLONE_PORT"
    return
  fi
  local port
  for port in $(seq 56555 56655); do
    if ! lsof -nP -iTCP:"$port" >/dev/null 2>&1 && \
       ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$port" -q; then
      printf '%s\n' "$port"
      return
    fi
  done
  basic_fail "No fresh disposable PostgreSQL port is available"
}

select_rehearsal_port() {
  local excluded_port="$1"
  local port
  for port in $(seq 56656 56756); do
    if [[ "$port" != "$excluded_port" ]] && \
       ! lsof -nP -iTCP:"$port" >/dev/null 2>&1 && \
       ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$port" -q; then
      printf '%s\n' "$port"
      return
    fi
  done
  basic_fail "No independent physical-rehearsal PostgreSQL port is available"
}

ensure_release_state_directory() {
  if [[ -L "$RELEASE_STATE_DIRECTORY" ]] || \
     [[ -e "$RELEASE_STATE_DIRECTORY" && ! -d "$RELEASE_STATE_DIRECTORY" ]]; then
    basic_fail "CareSync release-state directory is unsafe"
    return
  fi
  if [[ ! -e "$RELEASE_STATE_DIRECTORY" ]]; then
    durable_ensure_private_directory "$RELEASE_STATE_DIRECTORY" || return
  fi
  if [[ "$(stat -f '%u' "$RELEASE_STATE_DIRECTORY")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$RELEASE_STATE_DIRECTORY")" != "700" ]]; then
    basic_fail "CareSync release-state directory must be owner-controlled mode 0700"
    return
  fi
}

require_no_global_recovery_journals_for_new_operation() {
  if [[ -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] || \
     [[ -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    basic_fail \
      "A post-retirement role restoration must be recovered by ordinary startup before a new release operation"
    return
  fi
  if [[ -e "$REACTIVATION_PENDING" ]] || \
     [[ -L "$REACTIVATION_PENDING" ]]; then
    basic_fail \
      "A release-fence reactivation must be completed by its bound controlled retry before a new release operation"
    return
  fi
}

create_fence() {
  local run_directory="$1"
  local app_prior_state="$2"
  local ingest_prior_state="$3"
  local pending="$run_directory/prepare-fence-pending-$$-$RANDOM"
  local pending_context="$pending/.context-pending-$$-$RANDOM"
  local source_manifest_sha
  ensure_release_state_directory || return
  require_no_global_recovery_journals_for_new_operation || return
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    basic_fail "A retained release fence already exists; commit or resume it first"
    return
  fi
  source_manifest_sha="$(
    private_file_sha256 "$RELEASE_SOURCE_MANIFEST" \
      "preparing release source manifest"
  )" || return
  bootstrap_verify_pre_candidate_source \
    "$run_directory" "$source_manifest_sha" || return
  durable_ensure_private_directory "$pending" || return
  printf '%s\n' \
    "status=preparing" \
    "run_directory=$run_directory" \
    "release_source_root=$RELEASE_SOURCE_ROOT" \
    "release_source_manifest=$RELEASE_SOURCE_MANIFEST" \
    "release_source_manifest_sha256=$source_manifest_sha" \
    "app_prior_login=$app_prior_state" \
    "ingest_prior_login=$ingest_prior_state" \
    "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
    "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
    >"$pending_context"
  chmod 600 "$pending_context"
  durable_publish_private_file "$pending_context" "$pending/context" || return
  durable_rename_private_fence_no_replace \
    "$pending" "$RELEASE_FENCE_DIRECTORY" || return
}

seal_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local app_prior_state="$3"
  local ingest_prior_state="$4"
  local temporary="$run_directory/.prepared-context.$$.$RANDOM"
  printf '%s\n' \
    "status=prepared" \
    "run_directory=$run_directory" \
    "candidate_receipt=$candidate_receipt" \
    "app_prior_login=$app_prior_state" \
    "ingest_prior_login=$ingest_prior_state" \
    "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
    "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
    >"$temporary"
  chmod 600 "$temporary"
  durable_replace_private_file \
    "$temporary" "$RELEASE_FENCE_DIRECTORY/context" || return
}

create_prepared_fence_evidence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local app_prior_state="$3"
  local ingest_prior_state="$4"
  local evidence="$run_directory/prepared-fence.context"
  local pending="$run_directory/.prepared-fence-context.pending.$$.$RANDOM"
  if [[ -e "$evidence" ]] || [[ -L "$evidence" ]]; then
    basic_fail "Prepared-fence evidence already exists"
    return
  fi
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=prepared" \
      "run_directory=$run_directory" \
      "candidate_receipt=$candidate_receipt" \
      "app_prior_login=$app_prior_state" \
      "ingest_prior_login=$ingest_prior_state" \
      "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
      "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
      >"$pending"
  ); then
    basic_fail "Could not create immutable prepared-fence evidence"
    return
  fi
  chmod 600 "$pending"
  durable_publish_private_file "$pending" "$evidence" || return
}

fence_prior_state() {
  local key="$1"
  local context="$RELEASE_FENCE_DIRECTORY/context"
  local value
  value="$(private_context_value "$context" "$key")" || return
  if [[ "$value" != "login" && "$value" != "nologin" ]]; then
    basic_fail "Prepared fence has an invalid $key value"
    return
  fi
  printf '%s\n' "$value"
}

restore_runtime_role_states_from_fence() {
  local app_prior ingest_prior
  app_prior="$(fence_prior_state app_prior_login)" || return
  ingest_prior="$(fence_prior_state ingest_prior_login)" || return
  if ! basic_set_role_login_state caresync_basic_app "$app_prior"; then
    basic_set_role_login_state caresync_basic_app nologin || true
    basic_set_role_login_state caresync_transport_evidence_ingest nologin || true
    basic_fail "Could not restore the application role; the release fence remains"
    return
  fi
  if ! basic_set_role_login_state \
    caresync_transport_evidence_ingest "$ingest_prior"; then
    # Never leave one writer open after a partial restoration.
    basic_set_role_login_state caresync_basic_app nologin || true
    basic_set_role_login_state caresync_transport_evidence_ingest nologin || true
    basic_fail "Could not restore every writer role; the release fence remains"
    return
  fi
}

open_runtime_roles_for_controlled_start() {
  if ! basic_set_role_login_state caresync_basic_app login; then
    basic_set_role_login_state caresync_basic_app nologin || true
    basic_set_role_login_state caresync_transport_evidence_ingest nologin || true
    basic_fail "Could not open the certified application role for controlled startup"
    return
  fi
  if ! basic_set_role_login_state caresync_transport_evidence_ingest login; then
    basic_set_role_login_state caresync_basic_app nologin || true
    basic_set_role_login_state caresync_transport_evidence_ingest nologin || true
    basic_fail "Could not open every certified runtime role for controlled startup"
    return
  fi
}

fence_runtime_roles() {
  local failed=false
  basic_set_role_login_state caresync_basic_app nologin || failed=true
  basic_set_role_login_state caresync_transport_evidence_ingest nologin || failed=true
  local probe_exists
  probe_exists="$(basic_psql_scalar \
    "SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname='$RELEASE_PROBE_USER'")" \
    || failed=true
  if [[ "$probe_exists" == "1" ]]; then
    basic_set_role_login_state "$RELEASE_PROBE_USER" nologin || failed=true
    scrub_release_probe_object_privileges || failed=true
  elif [[ -n "$probe_exists" ]] && [[ "$probe_exists" != "0" ]]; then
    failed=true
  fi
  if [[ "$failed" == "true" ]]; then
    basic_fail "Could not re-fence every certified runtime role"
    return
  fi
  basic_require_runtime_roles_fenced || return
  if [[ "$probe_exists" == "1" ]]; then
    require_release_probe_contract nologin || return
    require_release_probe_read_scope closed || return
  fi
}

emergency_fence_runtime_roles() {
  basic_verify_retained_identity || return
  fence_runtime_roles || return
}

close_retired_controlled_runtime_after_child_failure() {
  local failed=false
  basic_quiesce_application || failed=true
  basic_assert_no_cluster_clients || failed=true
  close_release_probe_after_controlled_health || failed=true
  if [[ "$failed" == "true" ]]; then
    basic_fail \
      "Could not prove the retired controlled runtime and probe are closed"
    return 1
  fi
}

CONTROLLED_RUNTIME_WINDOW_OPEN=false
CONTROLLED_RUNTIME_WINDOW_FINALIZED=false

refence_interrupted_runtime_window() {
  if [[ "$CONTROLLED_RUNTIME_WINDOW_OPEN" == "true" ]] && \
     [[ "$CONTROLLED_RUNTIME_WINDOW_FINALIZED" != "true" ]]; then
    if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q || \
       ! basic_verify_retained_identity; then
      basic_fail \
        "Retained identity is unavailable; preserving the fence without issuing SQL cleanup"
      return
    fi
    if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
       [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
      if ! fence_runtime_roles; then
        basic_fail "Interrupted controlled runtime could not be fully re-fenced"
        return 1
      fi
    else
      if ! close_retired_controlled_runtime_after_child_failure; then
        basic_fail \
          "Interrupted retired controlled runtime could not be fully closed"
        return 1
      fi
    fi
    CONTROLLED_RUNTIME_WINDOW_OPEN=false
  fi
}

controlled_runtime_window_exit() {
  local result=$?
  refence_interrupted_runtime_window
  return "$result"
}

controlled_runtime_window_signal() {
  local result="$1"
  trap - EXIT INT TERM
  refence_interrupted_runtime_window
  exit "$result"
}

arm_controlled_runtime_window_cleanup() {
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  CONTROLLED_RUNTIME_WINDOW_FINALIZED=false
  trap controlled_runtime_window_exit EXIT
  trap 'controlled_runtime_window_signal 130' INT
  trap 'controlled_runtime_window_signal 143' TERM
}

disarm_controlled_runtime_window_cleanup() {
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  CONTROLLED_RUNTIME_WINDOW_FINALIZED=true
  trap - EXIT INT TERM
}

require_directory_only_contains() {
  local directory="$1"
  local expected="$2"
  local inventory
  inventory="$(mktemp "$RUNTIME_DIR/.directory-inventory.XXXXXX")" || return
  if ! find "$directory" -mindepth 1 -maxdepth 1 -print0 >"$inventory"; then
    rm -f "$inventory"
    basic_fail "Private directory traversal was incomplete"
    return
  fi
  local entries=()
  local entry
  while IFS= read -r -d '' entry; do
    entries+=("$entry")
  done <"$inventory"
  rm -f "$inventory" || return
  if (( ${#entries[@]} != 1 )) || [[ "${entries[0]}" != "$expected" ]]; then
    basic_fail "Private directory contains unexpected metadata"
    return
  fi
}

directory_entry_state() {
  local directory="$1"
  local output result
  set +e
  output="$(find "$directory" -mindepth 1 -maxdepth 1 -print -quit)"
  result=$?
  set -e
  if (( result != 0 )); then
    basic_fail "Private directory inspection failed"
    return
  fi
  if [[ -n "$output" ]]; then
    printf '%s\n' nonempty
  else
    printf '%s\n' empty
  fi
}

require_fence_only_contains_context() {
  local context="$RELEASE_FENCE_DIRECTORY/context"
  if ! require_directory_only_contains \
    "$RELEASE_FENCE_DIRECTORY" "$context"; then
    basic_fail "Release fence contains unexpected metadata; preserving it for review"
    return
  fi
}

remove_preparing_fence() {
  local run_directory="$1"
  local app_prior_state="$2"
  local ingest_prior_state="$3"
  local context="$RELEASE_FENCE_DIRECTORY/context"
  local source_manifest_sha
  source_manifest_sha="$(
    private_context_value "$context" release_source_manifest_sha256
  )" || return
  if [[ -L "$RELEASE_FENCE_DIRECTORY" ]] || [[ -L "$context" ]] || \
     [[ ! -d "$RELEASE_FENCE_DIRECTORY" ]] || [[ ! -f "$context" ]] || \
     [[ "$(stat -f '%u' "$RELEASE_FENCE_DIRECTORY")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$RELEASE_FENCE_DIRECTORY")" != "700" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]] || \
     [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "9" ]] || \
     ! grep -Fqx "status=preparing" "$context" || \
     ! grep -Fqx "run_directory=$run_directory" "$context" || \
     ! grep -Fqx \
       "release_source_root=$run_directory/release-source" "$context" || \
     ! grep -Fqx \
       "release_source_manifest=$run_directory/release-source.manifest.json" \
       "$context" || \
     [[ ! "$source_manifest_sha" =~ ^[0-9a-f]{64}$ ]] || \
     ! grep -Fqx \
       "release_source_manifest_sha256=$source_manifest_sha" "$context" || \
     ! grep -Fqx "app_prior_login=$app_prior_state" "$context" || \
     ! grep -Fqx "ingest_prior_login=$ingest_prior_state" "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" "$context"; then
    basic_fail "Cannot automatically remove a non-preparing release fence"
    return
  fi
  require_fence_only_contains_context || return
  local retired_fence="$run_directory/preparing-fence-retired"
  if [[ -e "$retired_fence" ]] || [[ -L "$retired_fence" ]]; then
    basic_fail "Preparing-fence retirement destination already exists"
    return
  fi
  durable_rename_private_fence_no_replace \
    "$RELEASE_FENCE_DIRECTORY" "$retired_fence" || return
}

private_context_value() {
  local context="$1"
  local key="$2"
  local output
  output="$(sed -n "s/^$key=//p" "$context")" || {
    basic_fail "Private release context could not be read"
    return
  }
  if [[ -z "$output" ]] || [[ "$output" == *$'\n'* ]]; then
    basic_fail "Private release context has an invalid $key value"
    return
  fi
  printf '%s\n' "$output"
}

require_exact_preparing_fence() {
  local context="$RELEASE_FENCE_DIRECTORY/context"
  if [[ -L "$RELEASE_FENCE_DIRECTORY" ]] || [[ -L "$context" ]] || \
     [[ ! -d "$RELEASE_FENCE_DIRECTORY" ]] || [[ ! -f "$context" ]] || \
     [[ "$(stat -f '%u' "$RELEASE_FENCE_DIRECTORY")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$RELEASE_FENCE_DIRECTORY")" != "700" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]]; then
    basic_fail "Interrupted prepare fence is not private owner-controlled evidence"
    return
  fi
  if grep -Fqx "status=prepared" "$context"; then
    basic_fail \
      "A prepared release fence is commit/resume-only and cannot be auto-reconciled"
    return
  fi
  if [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "9" ]] || \
     ! grep -Fqx "status=preparing" "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" "$context"; then
    basic_fail "Automatic recovery accepts only an exact source-bound preparing fence"
    return
  fi
  require_fence_only_contains_context || return

  PREPARING_RUN_DIRECTORY="$(private_context_value "$context" run_directory)"
  PREPARING_SOURCE_ROOT="$(
    private_context_value "$context" release_source_root
  )"
  PREPARING_SOURCE_MANIFEST="$(
    private_context_value "$context" release_source_manifest
  )"
  PREPARING_SOURCE_MANIFEST_SHA="$(
    private_context_value "$context" release_source_manifest_sha256
  )"
  PREPARING_APP_PRIOR_STATE="$(
    private_context_value "$context" app_prior_login
  )"
  PREPARING_INGEST_PRIOR_STATE="$(
    private_context_value "$context" ingest_prior_login
  )"
  if [[ "$PREPARING_APP_PRIOR_STATE" != "login" && \
        "$PREPARING_APP_PRIOR_STATE" != "nologin" ]] || \
     [[ "$PREPARING_INGEST_PRIOR_STATE" != "login" && \
        "$PREPARING_INGEST_PRIOR_STATE" != "nologin" ]]; then
    basic_fail "Interrupted prepare fence has an invalid writer-role state"
    return
  fi
  local run_key
  run_key="$(basename "$PREPARING_RUN_DIRECTORY")"
  if [[ ! "$run_key" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]] || \
     [[ "$PREPARING_RUN_DIRECTORY" != "$RELEASE_STATE_DIRECTORY/$run_key" ]]; then
    basic_fail "Interrupted prepare run is outside the private release-state root"
    return
  fi
  if [[ "$PREPARING_SOURCE_ROOT" != \
        "$PREPARING_RUN_DIRECTORY/release-source" ]] || \
     [[ "$PREPARING_SOURCE_MANIFEST" != \
        "$PREPARING_RUN_DIRECTORY/release-source.manifest.json" ]] || \
     [[ ! "$PREPARING_SOURCE_MANIFEST_SHA" =~ ^[0-9a-f]{64}$ ]]; then
    basic_fail "Interrupted prepare source binding is outside its release run"
    return
  fi
  basic_assert_no_symlink_components "$PREPARING_RUN_DIRECTORY" || return
  if [[ -L "$PREPARING_RUN_DIRECTORY" ]] || \
     [[ ! -d "$PREPARING_RUN_DIRECTORY" ]] || \
     [[ "$(stat -f '%u' "$PREPARING_RUN_DIRECTORY")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$PREPARING_RUN_DIRECTORY")" != "700" ]] || \
     [[ "$(cd "$(dirname "$PREPARING_RUN_DIRECTORY")" && pwd -P)" != \
        "$(cd "$RELEASE_STATE_DIRECTORY" && pwd -P)" ]]; then
    basic_fail "Interrupted prepare run is not a private direct release child"
    return
  fi
  if ! grep -Fqx "run_directory=$PREPARING_RUN_DIRECTORY" "$context" || \
     ! grep -Fqx "release_source_root=$PREPARING_SOURCE_ROOT" "$context" || \
     ! grep -Fqx \
       "release_source_manifest=$PREPARING_SOURCE_MANIFEST" "$context" || \
     ! grep -Fqx \
       "release_source_manifest_sha256=$PREPARING_SOURCE_MANIFEST_SHA" \
       "$context" || \
     ! grep -Fqx "app_prior_login=$PREPARING_APP_PRIOR_STATE" "$context" || \
     ! grep -Fqx \
       "ingest_prior_login=$PREPARING_INGEST_PRIOR_STATE" "$context"; then
    basic_fail "Interrupted prepare fence is internally inconsistent"
    return
  fi
}

require_private_prepare_directory() {
  local path="$1"
  local label="$2"
  if [[ ! -e "$path" ]] && [[ ! -L "$path" ]]; then
    return 0
  fi
  basic_assert_no_symlink_components "$path" || return
  if [[ -L "$path" ]] || [[ ! -d "$path" ]] || \
     [[ "$(stat -f '%u' "$path")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$path")" != "700" ]]; then
    basic_fail "$label is not a private owner-controlled directory"
    return
  fi
}

require_private_prepare_tree() {
  local path="$1"
  local label="$2"
  require_private_prepare_directory "$path" "$label" || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py \
      validate-private-tree --path "$path" || {
    basic_fail "$label failed its complete fail-closed tree traversal"
    return
  }
}

require_private_rehearsal_configuration() {
  local rehearsal_directory="$1"
  local config_file="$rehearsal_directory/postgresql.conf"
  local hba_file="$rehearsal_directory/pg_hba.conf"
  local ident_file="$rehearsal_directory/pg_ident.conf"
  local file
  for file in "$config_file" "$hba_file" "$ident_file"; do
    if [[ -L "$file" ]] || [[ ! -f "$file" ]] || \
       [[ "$(stat -f '%u' "$file")" != "$(id -u)" ]] || \
       [[ "$(stat -f '%Lp' "$file")" != "600" ]] || \
       [[ "$(stat -f '%l' "$file")" != "1" ]]; then
      basic_fail "Interrupted physical rehearsal configuration is unsafe"
      return
    fi
  done
  if [[ "$(wc -l <"$config_file" | tr -d '[:space:]')" != "1" ]] || \
     ! grep -Fqx \
       "# Isolated CareSync physical-rehearsal configuration." "$config_file" || \
     [[ "$(wc -l <"$hba_file" | tr -d '[:space:]')" != "4" ]] || \
     ! grep -Fqx \
       "host \"$DATABASE_NAME\" \"$MIGRATION_USER\" 127.0.0.1/32 trust" \
       "$hba_file" || \
     ! grep -Fqx "host all all 127.0.0.1/32 reject" "$hba_file" || \
     ! grep -Fqx "host all all ::/0 reject" "$hba_file" || \
     ! grep -Fqx "local all all reject" "$hba_file" || \
     [[ "$(wc -l <"$ident_file" | tr -d '[:space:]')" != "1" ]] || \
     ! grep -Fqx "# No user maps." "$ident_file"; then
    basic_fail "Interrupted physical rehearsal configuration has drifted"
    return
  fi
}

preserve_stale_disposable_postmaster_pid() {
  local run_directory="$1"
  local pgdata="$2"
  local label="$3"
  local pid_file="$pgdata/postmaster.pid"
  local preserved
  preserved="$run_directory/stale-$label-postmaster.pid.$(
    date -u +%Y%m%dT%H%M%SZ
  ).$$.$RANDOM"
  durable_publish_private_file "$pid_file" "$preserved" || return
  if [[ -e "$pid_file" ]] || [[ -L "$pid_file" ]] || \
     [[ ! -f "$preserved" ]] || [[ -L "$preserved" ]]; then
    basic_fail "Could not preserve stale $label postmaster evidence"
    return
  fi
}

reconcile_prepare_disposable_postgres() {
  local run_directory="$1"
  local pgdata="$2"
  local kind="$3"
  if [[ ! -e "$pgdata" ]] && [[ ! -L "$pgdata" ]]; then
    return 0
  fi
  require_private_prepare_tree \
    "$pgdata" "interrupted $kind PostgreSQL" || return
  local pid_file="$pgdata/postmaster.pid"
  if [[ ! -e "$pid_file" ]] && [[ ! -L "$pid_file" ]]; then
    local process_inventory
    process_inventory="$(/bin/ps -axo command= 2>/dev/null)" || {
      basic_fail "Interrupted $kind process inventory could not be inspected"
      return
    }
    if "$PG_BIN/pg_ctl" -D "$pgdata" status >/dev/null 2>&1 || \
       { grep -F "$pgdata" <<<"$process_inventory" | \
         grep -Fq "postgres"; }; then
      basic_fail "Interrupted $kind server is running without bound PID evidence"
      return
    fi
    return 0
  fi
  basic_require_safe_postgres_tree \
    "$pgdata" "interrupted $kind PostgreSQL" || return
  if [[ -L "$pid_file" ]] || [[ ! -f "$pid_file" ]] || \
     [[ "$(stat -f '%u' "$pid_file")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$pid_file")" != "600" ]] || \
     [[ "$(stat -f '%l' "$pid_file")" != "1" ]]; then
    basic_fail "Interrupted $kind postmaster evidence is unsafe"
    return
  fi

  local postmaster_pid recorded_data_directory start_epoch port socket_directory
  local listen_addresses canonical_pgdata control_identifier postmaster_options
  postmaster_pid="$(sed -n '1p' "$pid_file")"
  recorded_data_directory="$(sed -n '2p' "$pid_file")"
  start_epoch="$(sed -n '3p' "$pid_file")"
  port="$(sed -n '4p' "$pid_file")"
  socket_directory="$(sed -n '5p' "$pid_file")"
  listen_addresses="$(sed -n '6p' "$pid_file")"
  canonical_pgdata="$(cd "$pgdata" && pwd -P)" || return
  if [[ ! "$postmaster_pid" =~ ^[1-9][0-9]*$ ]] || \
     [[ ! "$start_epoch" =~ ^[1-9][0-9]*$ ]] || \
     [[ "$recorded_data_directory" != "$canonical_pgdata" ]] || \
     [[ ! "$port" =~ ^[0-9]+$ ]] || \
     (( port < 55000 || port > 60999 )) || \
     [[ "$port" == "$PGPORT" ]] || \
     [[ "$listen_addresses" != "127.0.0.1" ]]; then
    basic_fail "Interrupted $kind PID evidence has unsafe endpoint provenance"
    return
  fi

  local connection_database="postgres"
  if [[ "$kind" == "physical-rehearsal" ]]; then
    local rehearsal_directory="$run_directory/physical-rehearsal"
    local expected_socket="/private/tmp/cs-$(basename "$run_directory")-$port"
    if (( port < 56656 || port > 56756 )) || \
       [[ "$socket_directory" != "$expected_socket" ]]; then
      basic_fail "Interrupted physical rehearsal has an unexpected private endpoint"
      return
    fi
    connection_database="$DATABASE_NAME"
  fi

  local postmaster_presence
  postmaster_presence="$(basic_inspect_pid_presence "$postmaster_pid")" || return
  if [[ "$postmaster_presence" == "absent" ]]; then
    if "$PG_BIN/pg_ctl" -D "$pgdata" status >/dev/null 2>&1 || \
       lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      basic_fail "Interrupted $kind PID is stale but its endpoint is still active"
      return
    fi
    preserve_stale_disposable_postmaster_pid \
      "$run_directory" "$pgdata" "$kind" || return
    basic_require_safe_postgres_tree \
      "$pgdata" "reconciled $kind PostgreSQL" || return
    return 0
  fi

  if [[ "$kind" == "physical-rehearsal" ]]; then
    require_private_rehearsal_configuration "$rehearsal_directory" || return
  fi
  if [[ -L "$pgdata/postmaster.opts" ]] || \
     [[ ! -f "$pgdata/postmaster.opts" ]] || \
     [[ "$(stat -f '%u' "$pgdata/postmaster.opts")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$pgdata/postmaster.opts")" != "600" ]] || \
     [[ "$(stat -f '%l' "$pgdata/postmaster.opts")" != "1" ]]; then
    basic_fail "Interrupted $kind has no trustworthy postmaster options"
    return
  fi
  postmaster_options="$(<"$pgdata/postmaster.opts")"
  if [[ "$postmaster_options" != *"\"-D\" \"$canonical_pgdata\""* ]] || \
     [[ "$postmaster_options" != *"\"-p\" \"$port\""* ]] || \
     [[ "$postmaster_options" != *"\"-h\" \"127.0.0.1\""* ]]; then
    basic_fail "Interrupted $kind postmaster options do not match its evidence"
    return
  fi
  if [[ "$kind" == "physical-rehearsal" ]] && \
     { [[ "$postmaster_options" != *"\"-k\" \"$expected_socket\""* ]] || \
       [[ "$postmaster_options" != \
          *"config_file=$run_directory/physical-rehearsal/postgresql.conf"* ]] || \
       [[ "$postmaster_options" != \
          *"hba_file=$run_directory/physical-rehearsal/pg_hba.conf"* ]] || \
       [[ "$postmaster_options" != \
          *"ident_file=$run_directory/physical-rehearsal/pg_ident.conf"* ]] || \
       [[ "$postmaster_options" != *"data_directory=$canonical_pgdata"* ]] || \
       [[ "$postmaster_options" != *"shared_preload_libraries="* ]] || \
       [[ "$postmaster_options" != *"session_preload_libraries="* ]] || \
       [[ "$postmaster_options" != *"local_preload_libraries="* ]] || \
       [[ "$postmaster_options" != *"external_pid_file="* ]] || \
       [[ "$postmaster_options" != *"ssl=off"* ]] || \
       [[ "$postmaster_options" != *"logging_collector=off"* ]] || \
       [[ "$postmaster_options" != *"archive_mode=off"* ]] || \
       [[ "$postmaster_options" != *"primary_conninfo="* ]] || \
       [[ "$postmaster_options" != *"restore_command="* ]] || \
       [[ "$postmaster_options" != *"archive_command="* ]] || \
       [[ "$postmaster_options" != *"archive_cleanup_command="* ]] || \
       [[ "$postmaster_options" != *"recovery_end_command="* ]]; }; then
    basic_fail "Interrupted physical rehearsal isolation options have drifted"
    return
  fi

  control_identifier="$(
    basic_postgres_control_system_identifier "$pgdata"
  )" || return
  local process_command process_executables expected_executable
  local listener_pids online_attestation
  process_command="$(
    /bin/ps -p "$postmaster_pid" -o command= 2>/dev/null
  )" || return
  process_executables="$(
    /usr/sbin/lsof -a -p "$postmaster_pid" -d txt -Fn 2>/dev/null | \
      sed -n 's/^n//p'
  )" || return
  expected_executable="$(cd "$PG_BIN" && pwd -P)/postgres"
  listener_pids="$(
    basic_collect_tcp_listener_pids "$port" | sort -u
  )" || return
  if ! "$PG_BIN/pg_ctl" -D "$pgdata" status >/dev/null 2>&1 || \
     ! printf '%s\n' "$process_executables" | \
       grep -Fqx "$expected_executable" || \
     [[ "$process_command" != *"postgres"* ]] || \
     [[ "$process_command" != *"$canonical_pgdata"* ]] || \
     [[ "$listener_pids" != "$postmaster_pid" ]] || \
     ! /usr/sbin/lsof -nP -a -p "$postmaster_pid" \
       -iTCP:"$port" -sTCP:LISTEN \
       2>/dev/null | grep -Fq "127.0.0.1:$port"; then
    basic_fail "Interrupted $kind process provenance is ambiguous; not signaling it"
    return
  fi
  # Daemon cwd is not a stable PostgreSQL ownership contract across launch
  # implementations. Bind the canonical postgres executable plus an online
  # same-process data-directory/system-id/endpoint query instead; these are
  # stronger than cwd and must all pass before pg_ctl may signal the PID.
  online_attestation="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$port" -U "$MIGRATION_USER" -d "$connection_database" \
    -c "SELECT current_setting('data_directory') || '|' || (SELECT system_identifier::text FROM pg_control_system()) || '|' || host(inet_server_addr()) || ':' || inet_server_port()::text")" || return
  if [[ "$online_attestation" != \
        "$canonical_pgdata|$control_identifier|127.0.0.1:$port" ]]; then
    basic_fail "Interrupted $kind online identity is not the disposable tree"
    return
  fi
  "$PG_BIN/pg_ctl" -D "$pgdata" stop -m fast || return
  local remaining_presence remaining_listeners
  remaining_presence="$(basic_inspect_pid_presence "$postmaster_pid")" || return
  remaining_listeners="$(basic_collect_tcp_listener_pids "$port")" || return
  if [[ "$remaining_presence" != "absent" ]] || \
     [[ -n "$remaining_listeners" ]] || \
     [[ -e "$pid_file" ]] || [[ -L "$pid_file" ]]; then
    basic_fail "Interrupted $kind server did not stop cleanly"
    return
  fi
  basic_require_safe_postgres_tree \
    "$pgdata" "reconciled $kind PostgreSQL" || return
}

reconcile_interrupted_prepare() {
  if [[ ! -e "$RELEASE_FENCE_DIRECTORY" ]] && \
     [[ ! -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    return 0
  fi
  require_exact_preparing_fence || return
  local run_directory="$PREPARING_RUN_DIRECTORY"
  if [[ "$ROOT" != "$PREPARING_SOURCE_ROOT" ]]; then
    basic_fail \
      "Interrupted prepare recovery must execute from its bound captured source"
    return
  fi
  bootstrap_verify_pre_candidate_source \
    "$run_directory" "$PREPARING_SOURCE_MANIFEST_SHA" || return
  reconcile_prepare_disposables_for_run "$run_directory" || return

  basic_start_postgres || return
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  basic_quiesce_application || return
  basic_assert_no_cluster_clients || return
  fence_runtime_roles || return
  prepare_post_retirement_role_restoration \
    prepare-abort "$run_directory" \
    "$run_directory/preparing-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  remove_preparing_fence \
    "$run_directory" \
    "$PREPARING_APP_PRIOR_STATE" \
    "$PREPARING_INGEST_PRIOR_STATE" || return
  complete_post_retirement_role_restoration \
    prepare-abort "$run_directory" \
    "$run_directory/preparing-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  if [[ "$(basic_role_login_state caresync_basic_app)" != \
        "$PREPARING_APP_PRIOR_STATE" ]] || \
     [[ "$(basic_role_login_state caresync_transport_evidence_ingest)" != \
        "$PREPARING_INGEST_PRIOR_STATE" ]]; then
    basic_fail "Interrupted prepare writer-role restoration is incomplete"
    return
  fi
  printf '%s\n' \
    "Recovered an interrupted preparing run; all evidence was preserved at:" \
    "  $run_directory"
}

reconcile_prepare_disposables_for_run() {
  local run_directory="$1"
  local rehearsal_directory="$run_directory/physical-rehearsal"
  local clone_directory="$run_directory/clone"
  if [[ -e "$rehearsal_directory" ]] || [[ -L "$rehearsal_directory" ]]; then
    require_private_prepare_directory "$rehearsal_directory" \
      "Interrupted physical rehearsal directory" || return
  fi
  if [[ -e "$clone_directory" ]] || [[ -L "$clone_directory" ]]; then
    require_private_prepare_directory "$clone_directory" \
      "Interrupted clone directory" || return
  fi
  reconcile_prepare_disposable_postgres \
    "$run_directory" \
    "$rehearsal_directory/postgres-data" \
    physical-rehearsal || return
  reconcile_prepare_disposable_postgres \
    "$run_directory" \
    "$clone_directory/postgres-data" \
    clone || return
}

require_matching_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local context="$RELEASE_FENCE_DIRECTORY/context"
  local bound_context="$run_directory/prepared-fence.context"
  if [[ -L "$RELEASE_FENCE_DIRECTORY" ]] || [[ -L "$context" ]] || \
     [[ -L "$bound_context" ]] || \
     [[ ! -d "$RELEASE_FENCE_DIRECTORY" ]] || [[ ! -f "$context" ]] || \
     [[ ! -f "$bound_context" ]] || \
     [[ "$(stat -f '%u' "$RELEASE_FENCE_DIRECTORY")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$RELEASE_FENCE_DIRECTORY")" != "700" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]] || \
     [[ "$(stat -f '%u' "$bound_context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$bound_context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$bound_context")" != "1" ]] || \
     [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "7" ]] || \
     ! grep -Fqx "status=prepared" "$context" || \
     ! grep -Fqx "run_directory=$run_directory" "$context" || \
     ! grep -Fqx "candidate_receipt=$candidate_receipt" "$context" || \
     ! grep -Eq '^app_prior_login=(login|nologin)$' "$context" || \
     ! grep -Eq '^ingest_prior_login=(login|nologin)$' "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" "$context" || \
     ! cmp -s "$bound_context" "$context"; then
    basic_fail "Prepared release fence does not match this candidate receipt"
    return
  fi
  require_fence_only_contains_context || return
}

remove_matching_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  require_matching_fence "$run_directory" "$candidate_receipt" || return
  local retired_fence="$run_directory/fence-retired"
  if [[ -e "$retired_fence" ]] || [[ -L "$retired_fence" ]]; then
    basic_fail "Prepared-fence retirement destination already exists"
    return
  fi
  durable_rename_private_fence_no_replace \
    "$RELEASE_FENCE_DIRECTORY" "$retired_fence" || return
  require_matching_retired_prepared_fence \
    "$run_directory" "$candidate_receipt" || return
}

require_matching_retired_prepared_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local retired_fence="$run_directory/fence-retired"
  local context="$retired_fence/context"
  local bound_context="$run_directory/prepared-fence.context"
  if [[ -L "$retired_fence" ]] || [[ -L "$context" ]] || \
     [[ -L "$bound_context" ]] || \
     [[ ! -d "$retired_fence" ]] || [[ ! -f "$context" ]] || \
     [[ ! -f "$bound_context" ]] || \
     [[ "$(stat -f '%u' "$retired_fence")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$retired_fence")" != "700" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]] || \
     [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "7" ]] || \
     ! grep -Fqx "status=prepared" "$context" || \
     ! grep -Fqx "run_directory=$run_directory" "$context" || \
     ! grep -Fqx "candidate_receipt=$candidate_receipt" "$context" || \
     ! grep -Eq '^app_prior_login=(login|nologin)$' "$context" || \
     ! grep -Eq '^ingest_prior_login=(login|nologin)$' "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" "$context" || \
     ! cmp -s "$bound_context" "$context"; then
    basic_fail "Retired prepared fence does not match this release"
    return
  fi
  if ! require_directory_only_contains "$retired_fence" "$context"; then
    basic_fail "Retired prepared fence contains unexpected metadata"
    return
  fi
}

reactivation_completed_path() {
  local run_directory="$1"
  local kind="$2"
  printf '%s/%s-fence-reactivation.completed\n' "$run_directory" "$kind"
}

require_reactivation_record() {
  local record="$1"
  local kind="$2"
  local run_directory="$3"
  local retired_fence="$4"
  local candidate_receipt="$5"
  local retired_context="$retired_fence/context"
  local context_for_hash="$retired_context"
  if [[ ! -e "$context_for_hash" ]] && \
     [[ ! -L "$context_for_hash" ]] && \
     [[ -f "$RELEASE_FENCE_DIRECTORY/context" ]] && \
     [[ ! -L "$RELEASE_FENCE_DIRECTORY/context" ]]; then
    context_for_hash="$RELEASE_FENCE_DIRECTORY/context"
  fi
  local context_sha candidate_sha identity_sha
  context_sha="$(
    private_file_sha256 "$context_for_hash" "reactivation fence context"
  )" || return
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" "reactivation candidate receipt"
  )" || return
  identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "reactivation retained identity"
  )" || return
  if [[ -L "$record" ]] || [[ ! -f "$record" ]] || \
     [[ "$(stat -f '%u' "$record")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$record")" != "600" ]] || \
     [[ "$(stat -f '%l' "$record")" != "1" ]] || \
     [[ "$(wc -l <"$record" | tr -d '[:space:]')" != "9" ]] || \
     ! grep -Fqx "status=release_fence_reactivation_pending" "$record" || \
     ! grep -Fqx "kind=$kind" "$record" || \
     ! grep -Fqx "run_directory=$run_directory" "$record" || \
     ! grep -Fqx "retired_fence=$retired_fence" "$record" || \
     ! grep -Fqx "retired_context_sha256=$context_sha" "$record" || \
     ! grep -Fqx "candidate_sha256=$candidate_sha" "$record" || \
     ! grep -Fqx "retained_identity_sha256=$identity_sha" "$record" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
       "$record" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
       "$record"; then
    basic_fail "Release-fence reactivation record is missing or inconsistent"
    return
  fi
}

prepare_reactivation_record() {
  local kind="$1"
  local run_directory="$2"
  local retired_fence="$3"
  local candidate_receipt="$4"
  local retired_context="$retired_fence/context"
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    basic_fail "Cannot prepare reactivation while an active fence exists"
    return
  fi
  local completed
  completed="$(reactivation_completed_path "$run_directory" "$kind")" || return
  if [[ -e "$REACTIVATION_PENDING" ]] || [[ -L "$REACTIVATION_PENDING" ]]; then
    require_reactivation_record \
      "$REACTIVATION_PENDING" "$kind" "$run_directory" \
      "$retired_fence" "$candidate_receipt" || return
    durability_barrier_private_file "$REACTIVATION_PENDING" || return
    return 0
  fi
  local context_sha candidate_sha identity_sha
  context_sha="$(
    private_file_sha256 "$retired_context" "retired reactivation context"
  )" || return
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" "reactivation candidate receipt"
  )" || return
  identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "reactivation retained identity"
  )" || return
  local pending="$RUNTIME_DIR/.release-fence-reactivation.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=release_fence_reactivation_pending" \
      "kind=$kind" \
      "run_directory=$run_directory" \
      "retired_fence=$retired_fence" \
      "retired_context_sha256=$context_sha" \
      "candidate_sha256=$candidate_sha" \
      "retained_identity_sha256=$identity_sha" \
      "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
      "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
      >"$pending"
  ); then
    basic_fail "Could not stage release-fence reactivation"
    return
  fi
  chmod 600 "$pending" || return
  durable_publish_private_file "$pending" "$REACTIVATION_PENDING" || return
  require_reactivation_record \
    "$REACTIVATION_PENDING" "$kind" "$run_directory" \
    "$retired_fence" "$candidate_receipt" || return
  # Re-publishing a later identical attempt may replace the completed record;
  # the global pending record is the sole authority while roles can be fenced.
  if [[ -e "$completed" ]] || [[ -L "$completed" ]]; then
    durability_barrier_private_file "$completed" || return
  fi
}

complete_reactivation_record() {
  local kind="$1"
  local run_directory="$2"
  local retired_fence="$3"
  local candidate_receipt="$4"
  local completed
  completed="$(reactivation_completed_path "$run_directory" "$kind")" || return
  if [[ -e "$REACTIVATION_PENDING" ]] || [[ -L "$REACTIVATION_PENDING" ]]; then
    require_reactivation_record \
      "$REACTIVATION_PENDING" "$kind" "$run_directory" \
      "$retired_fence" "$candidate_receipt" || return
    if [[ -e "$completed" ]] || [[ -L "$completed" ]]; then
      basic_fail \
        "Reactivation pending and completed records cannot coexist"
      return
    fi
    durable_publish_private_file "$REACTIVATION_PENDING" "$completed" || return
  fi
  require_reactivation_record \
    "$completed" "$kind" "$run_directory" \
    "$retired_fence" "$candidate_receipt" || return
  durability_barrier_private_file "$completed" || return
}

reactivate_retired_prepared_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local retired_fence="$run_directory/fence-retired"
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    require_matching_fence "$run_directory" "$candidate_receipt" || return
    if [[ ! -e "$REACTIVATION_PENDING" ]] && \
       [[ ! -L "$REACTIVATION_PENDING" ]]; then
      return 0
    fi
    require_reactivation_record \
      "$REACTIVATION_PENDING" prepared "$run_directory" \
      "$retired_fence" "$candidate_receipt" || return
    basic_quiesce_application || return
    if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      basic_start_postgres || return
    fi
    basic_verify_retained_identity || return
    fence_runtime_roles || return
    basic_assert_no_cluster_clients || return
    if [[ -e "$REACTIVATION_PENDING" ]] || \
       [[ -L "$REACTIVATION_PENDING" ]]; then
      complete_reactivation_record \
        prepared "$run_directory" "$retired_fence" \
        "$candidate_receipt" || return
    fi
    return
  fi
  require_matching_retired_prepared_fence \
    "$run_directory" "$candidate_receipt" || return
  ensure_release_state_directory || return
  basic_require_same_apfs_device \
    "$run_directory" "$RELEASE_STATE_DIRECTORY" || return
  prepare_reactivation_record \
    prepared "$run_directory" "$retired_fence" "$candidate_receipt" || return
  basic_quiesce_application || return
  if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_start_postgres || return
  fi
  basic_verify_retained_identity || return
  fence_runtime_roles || return
  basic_assert_no_cluster_clients || return
  durable_rename_private_fence_no_replace \
    "$retired_fence" "$RELEASE_FENCE_DIRECTORY" || return
  require_matching_fence "$run_directory" "$candidate_receipt" || return
  complete_reactivation_record \
    prepared "$run_directory" "$retired_fence" "$candidate_receipt" || return
}

rollback_context_value() {
  local key="$1"
  local context="$RELEASE_FENCE_DIRECTORY/context"
  private_context_value "$context" "$key" || {
    basic_fail "Rollback fence has an invalid $key value"
    return
  }
}

require_exact_rollback_context_file() {
  local context="$1"
  local status="$2"
  local run_directory="$3"
  local candidate_receipt="$4"
  local commit_receipt="$5"
  local finalization_receipt="$6"
  local authorization="$7"
  local quarantine_directory="$8"
  local partial_directory="$9"
  local app_prior_state="${10}"
  local ingest_prior_state="${11}"
  if [[ "$app_prior_state" != "login" && "$app_prior_state" != "nologin" ]] || \
     [[ "$ingest_prior_state" != "login" && \
        "$ingest_prior_state" != "nologin" ]] || \
     [[ -L "$context" ]] || [[ ! -f "$context" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]] || \
     [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "12" ]] || \
     ! grep -Fqx "status=$status" "$context" || \
     ! grep -Fqx "run_directory=$run_directory" "$context" || \
     ! grep -Fqx "candidate_receipt=$candidate_receipt" "$context" || \
     ! grep -Fqx "commit_receipt=$commit_receipt" "$context" || \
     ! grep -Fqx "finalization_receipt=$finalization_receipt" "$context" || \
     ! grep -Fqx "authorization=$authorization" "$context" || \
     ! grep -Fqx "quarantine_directory=$quarantine_directory" "$context" || \
     ! grep -Fqx "partial_directory=$partial_directory" "$context" || \
     ! grep -Fqx "app_prior_login=$app_prior_state" "$context" || \
     ! grep -Fqx "ingest_prior_login=$ingest_prior_state" "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
       "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
       "$context"; then
    basic_fail "Rollback journal is incomplete or does not match its transition"
    return
  fi
}

write_rollback_context() {
  local status="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local commit_receipt="$4"
  local finalization_receipt="$5"
  local authorization="$6"
  local quarantine_directory="$7"
  local partial_directory="$8"
  local app_prior_state="$9"
  local ingest_prior_state="${10}"
  local destination="${11}"
  local temporary="$run_directory/.rollback-context.$$.$RANDOM"
  case "$status" in
    rollback_preparing|rollback_retained_stopped|rollback_copy_verified|\
rollback_quarantined|rollback_restored|rollback_starting)
      ;;
    *)
      basic_fail "Invalid rollback fence state"
      return
      ;;
  esac
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=$status" \
      "run_directory=$run_directory" \
      "candidate_receipt=$candidate_receipt" \
      "commit_receipt=$commit_receipt" \
      "finalization_receipt=$finalization_receipt" \
      "authorization=$authorization" \
      "quarantine_directory=$quarantine_directory" \
      "partial_directory=$partial_directory" \
      "app_prior_login=$app_prior_state" \
      "ingest_prior_login=$ingest_prior_state" \
      "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
      "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
      >"$temporary"
  ); then
    basic_fail "Could not stage the complete rollback journal"
    return
  fi
  chmod 600 "$temporary" || return
  require_exact_rollback_context_file \
    "$temporary" "$status" "$run_directory" "$candidate_receipt" \
    "$commit_receipt" "$finalization_receipt" "$authorization" \
    "$quarantine_directory" "$partial_directory" "$app_prior_state" \
    "$ingest_prior_state" || return
  if [[ "$destination" == "new" ]]; then
    if [[ -e "$RELEASE_FENCE_DIRECTORY/context" ]] || \
       [[ -L "$RELEASE_FENCE_DIRECTORY/context" ]]; then
      basic_fail "Rollback fence context already exists"
      return
    fi
    durable_publish_private_file \
      "$temporary" "$RELEASE_FENCE_DIRECTORY/context" || return
  else
    durable_replace_private_file \
      "$temporary" "$RELEASE_FENCE_DIRECTORY/context" || return
  fi
  require_exact_rollback_context_file \
    "$RELEASE_FENCE_DIRECTORY/context" "$status" "$run_directory" \
    "$candidate_receipt" "$commit_receipt" "$finalization_receipt" \
    "$authorization" "$quarantine_directory" "$partial_directory" \
    "$app_prior_state" "$ingest_prior_state" || return
}

create_rollback_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local authorization="$5"
  local quarantine_directory="$6"
  local partial_directory="$7"
  local app_prior_state="$8"
  local ingest_prior_state="$9"
  ensure_release_state_directory || return
  require_no_global_recovery_journals_for_new_operation || return
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    basic_fail "A retained release fence already exists"
    return
  fi
  local pending="$run_directory/rollback-fence-pending-$$-$RANDOM"
  local pending_context="$pending/.context-pending-$$-$RANDOM"
  durable_ensure_private_directory "$pending" || return
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=rollback_preparing" \
      "run_directory=$run_directory" \
      "candidate_receipt=$candidate_receipt" \
      "commit_receipt=$commit_receipt" \
      "finalization_receipt=$finalization_receipt" \
      "authorization=$authorization" \
      "quarantine_directory=$quarantine_directory" \
      "partial_directory=$partial_directory" \
      "app_prior_login=$app_prior_state" \
      "ingest_prior_login=$ingest_prior_state" \
      "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
      "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
      >"$pending_context"
  ); then
    basic_fail "Could not stage the initial rollback journal"
    return
  fi
  chmod 600 "$pending_context" || return
  require_exact_rollback_context_file \
    "$pending_context" rollback_preparing "$run_directory" \
    "$candidate_receipt" "$commit_receipt" "$finalization_receipt" \
    "$authorization" "$quarantine_directory" "$partial_directory" \
    "$app_prior_state" "$ingest_prior_state" || return
  durable_publish_private_file "$pending_context" "$pending/context" || return
  durable_rename_private_fence_no_replace \
    "$pending" "$RELEASE_FENCE_DIRECTORY" || return
  require_exact_rollback_context_file \
    "$RELEASE_FENCE_DIRECTORY/context" rollback_preparing "$run_directory" \
    "$candidate_receipt" "$commit_receipt" "$finalization_receipt" \
    "$authorization" "$quarantine_directory" "$partial_directory" \
    "$app_prior_state" "$ingest_prior_state" || return
}

require_matching_rollback_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local context="$RELEASE_FENCE_DIRECTORY/context"
  if [[ -L "$RELEASE_FENCE_DIRECTORY" ]] || [[ -L "$context" ]] || \
     [[ ! -d "$RELEASE_FENCE_DIRECTORY" ]] || [[ ! -f "$context" ]] || \
     [[ "$(stat -f '%u' "$RELEASE_FENCE_DIRECTORY")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$RELEASE_FENCE_DIRECTORY")" != "700" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]] || \
     [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "12" ]] || \
     ! grep -Eq '^status=rollback_(preparing|retained_stopped|copy_verified|quarantined|restored|starting)$' "$context" || \
     ! grep -Fqx "run_directory=$run_directory" "$context" || \
     ! grep -Fqx "candidate_receipt=$candidate_receipt" "$context" || \
     ! grep -Fqx "commit_receipt=$commit_receipt" "$context" || \
     ! grep -Fqx "finalization_receipt=$finalization_receipt" "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" "$context"; then
    basic_fail "Emergency rollback fence does not match these release receipts"
    return
  fi
  require_fence_only_contains_context || return
  local prior
  prior="$(rollback_context_value app_prior_login)"
  [[ "$prior" == "login" || "$prior" == "nologin" ]] || \
    { basic_fail "Rollback fence has an invalid application prior state"; return; }
  prior="$(rollback_context_value ingest_prior_login)"
  [[ "$prior" == "login" || "$prior" == "nologin" ]] || \
    { basic_fail "Rollback fence has an invalid ingest prior state"; return; }
}

advance_rollback_fence() {
  local status="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local commit_receipt="$4"
  local finalization_receipt="$5"
  require_matching_rollback_fence \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt" || return
  local current_status current_rank next_rank
  current_status="$(rollback_context_value status)" || return
  case "$current_status" in
    rollback_preparing) current_rank=0 ;;
    rollback_retained_stopped) current_rank=1 ;;
    rollback_copy_verified) current_rank=2 ;;
    rollback_quarantined) current_rank=3 ;;
    rollback_restored) current_rank=4 ;;
    rollback_starting) current_rank=5 ;;
    *) basic_fail "Rollback fence has an unknown phase"; return ;;
  esac
  case "$status" in
    rollback_preparing) next_rank=0 ;;
    rollback_retained_stopped) next_rank=1 ;;
    rollback_copy_verified) next_rank=2 ;;
    rollback_quarantined) next_rank=3 ;;
    rollback_restored) next_rank=4 ;;
    rollback_starting) next_rank=5 ;;
    *) basic_fail "Rollback fence has an invalid next phase"; return ;;
  esac
  if (( next_rank < current_rank )); then
    # A retry may re-prove an already completed filesystem step, but it may
    # never rewrite the durable journal backwards.
    durability_barrier_private_tree "$RELEASE_FENCE_DIRECTORY" || return
    return 0
  fi
  if (( next_rank == current_rank )); then
    durability_barrier_private_tree "$RELEASE_FENCE_DIRECTORY" || return
    return 0
  fi
  if (( next_rank != current_rank + 1 )); then
    basic_fail "Rollback fence cannot skip a durable recovery phase"
    return
  fi
  local authorization quarantine_directory partial_directory
  local app_prior_state ingest_prior_state
  authorization="$(rollback_context_value authorization)" || return
  quarantine_directory="$(
    rollback_context_value quarantine_directory
  )" || return
  partial_directory="$(rollback_context_value partial_directory)" || return
  app_prior_state="$(rollback_context_value app_prior_login)" || return
  ingest_prior_state="$(rollback_context_value ingest_prior_login)" || return
  write_rollback_context \
    "$status" \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt" \
    "$authorization" \
    "$quarantine_directory" \
    "$partial_directory" \
    "$app_prior_state" \
    "$ingest_prior_state" \
    replace || return
}

remove_matching_rollback_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  require_matching_rollback_fence \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt" || return
  local authorization quarantine_directory partial_directory
  authorization="$(rollback_context_value authorization)" || return
  quarantine_directory="$(
    rollback_context_value quarantine_directory
  )" || return
  partial_directory="$(rollback_context_value partial_directory)" || return
  local retired_fence="$run_directory/rollback-fence-retired"
  if [[ -e "$retired_fence" ]] || [[ -L "$retired_fence" ]]; then
    basic_fail "Rollback-fence retirement destination already exists"
    return
  fi
  durable_rename_private_fence_no_replace \
    "$RELEASE_FENCE_DIRECTORY" "$retired_fence" || return
  require_matching_retired_rollback_fence \
    "$run_directory" "$candidate_receipt" "$commit_receipt" \
    "$finalization_receipt" "$authorization" "$quarantine_directory" \
    "$partial_directory" || return
}

require_matching_retired_rollback_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local authorization="$5"
  local quarantine_directory="$6"
  local partial_directory="$7"
  local retired_fence="$run_directory/rollback-fence-retired"
  local context="$retired_fence/context"
  if [[ -L "$retired_fence" ]] || [[ -L "$context" ]] || \
     [[ ! -d "$retired_fence" ]] || [[ ! -f "$context" ]] || \
     [[ "$(stat -f '%u' "$retired_fence")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$retired_fence")" != "700" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]] || \
     [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "12" ]] || \
     ! grep -Fqx "status=rollback_starting" "$context" || \
     ! grep -Fqx "run_directory=$run_directory" "$context" || \
     ! grep -Fqx "candidate_receipt=$candidate_receipt" "$context" || \
     ! grep -Fqx "commit_receipt=$commit_receipt" "$context" || \
     ! grep -Fqx "finalization_receipt=$finalization_receipt" "$context" || \
     ! grep -Fqx "authorization=$authorization" "$context" || \
     ! grep -Fqx "quarantine_directory=$quarantine_directory" "$context" || \
     ! grep -Fqx "partial_directory=$partial_directory" "$context" || \
     ! grep -Eq '^app_prior_login=(login|nologin)$' "$context" || \
     ! grep -Eq '^ingest_prior_login=(login|nologin)$' "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" "$context"; then
    basic_fail \
      "Retired rollback fence cannot authorize an exact-0039 retry"
    return
  fi
  if ! require_directory_only_contains "$retired_fence" "$context"; then
    basic_fail "Retired rollback fence contains unexpected metadata"
    return
  fi
}

reactivate_retired_rollback_fence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local authorization="$5"
  local quarantine_directory="$6"
  local partial_directory="$7"
  local retired_fence="$run_directory/rollback-fence-retired"
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    require_matching_rollback_fence \
      "$run_directory" "$candidate_receipt" "$commit_receipt" \
      "$finalization_receipt" || return
    if [[ ! -e "$REACTIVATION_PENDING" ]] && \
       [[ ! -L "$REACTIVATION_PENDING" ]]; then
      return 0
    fi
    require_reactivation_record \
      "$REACTIVATION_PENDING" rollback "$run_directory" \
      "$retired_fence" "$candidate_receipt" || return
    basic_quiesce_application || return
    if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      basic_start_postgres || return
    fi
    basic_verify_retained_identity || return
    fence_runtime_roles || return
    basic_assert_no_cluster_clients || return
    if [[ -e "$REACTIVATION_PENDING" ]] || \
       [[ -L "$REACTIVATION_PENDING" ]]; then
      complete_reactivation_record \
        rollback "$run_directory" "$retired_fence" \
        "$candidate_receipt" || return
    fi
    return 0
  fi
  if [[ ! -e "$retired_fence" ]] && [[ ! -L "$retired_fence" ]]; then
    return 0
  fi
  require_matching_retired_rollback_fence \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt" \
    "$authorization" \
    "$quarantine_directory" \
    "$partial_directory" || return
  ensure_release_state_directory || return
  basic_require_same_apfs_device \
    "$run_directory" "$RELEASE_STATE_DIRECTORY" || return
  prepare_reactivation_record \
    rollback "$run_directory" "$retired_fence" "$candidate_receipt" || return
  basic_quiesce_application || return
  if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_start_postgres || return
  fi
  basic_verify_retained_identity || return
  fence_runtime_roles || return
  basic_assert_no_cluster_clients || return
  durable_rename_private_fence_no_replace \
    "$retired_fence" "$RELEASE_FENCE_DIRECTORY" || return
  require_matching_rollback_fence \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt" || return
  if [[ "$(rollback_context_value status)" != "rollback_starting" ]] || \
     [[ "$(rollback_context_value authorization)" != "$authorization" ]] || \
     [[ "$(rollback_context_value quarantine_directory)" != \
        "$quarantine_directory" ]] || \
     [[ "$(rollback_context_value partial_directory)" != \
        "$partial_directory" ]]; then
    basic_fail "Reactivated rollback fence changed at the atomic boundary"
    return
  fi
  complete_reactivation_record \
    rollback "$run_directory" "$retired_fence" "$candidate_receipt" || return
}

private_file_sha256() {
  local path="$1"
  local label="$2"
  if [[ -L "$path" ]] || [[ ! -f "$path" ]] || \
     [[ "$(stat -f '%u' "$path")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$path")" != "600" ]] || \
     [[ "$(stat -f '%l' "$path")" != "1" ]]; then
    basic_fail "$label is not an owner-controlled mode-0600 single-link file"
    return
  fi
  /usr/bin/shasum -a 256 "$path" | /usr/bin/awk '{print $1}'
}

require_commit_attempt_intent() {
  local intent="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local candidate_sha source_sha physical_sha identity_sha
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" \
      "commit-attempt candidate receipt"
  )" || return
  source_sha="$(
    private_file_sha256 "$RELEASE_SOURCE_MANIFEST" \
      "commit-attempt release source manifest"
  )" || return
  physical_sha="$(
    private_file_sha256 "$PHYSICAL_BACKUP_INVENTORY" \
      "commit-attempt physical inventory"
  )" || return
  identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "commit-attempt retained identity"
  )" || return
  if [[ -L "$intent" ]] || [[ ! -f "$intent" ]] || \
     [[ "$(stat -f '%u' "$intent")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$intent")" != "600" ]] || \
     [[ "$(stat -f '%l' "$intent")" != "1" ]] || \
     [[ "$(wc -l <"$intent" | tr -d '[:space:]')" != "8" ]] || \
     ! grep -Fqx "status=commit_attempting" "$intent" || \
     ! grep -Fqx "run_directory=$run_directory" "$intent" || \
     ! grep -Fqx "candidate_sha256=$candidate_sha" "$intent" || \
     ! grep -Fqx "release_source_sha256=$source_sha" "$intent" || \
     ! grep -Fqx "physical_inventory_sha256=$physical_sha" "$intent" || \
     ! grep -Fqx "retained_identity_sha256=$identity_sha" "$intent" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
       "$intent" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
       "$intent"; then
    basic_fail "Commit-attempt intent is missing or inconsistent"
    return
  fi
}

create_commit_attempt_intent() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local intent="$run_directory/commit-attempting.intent"
  if [[ -e "$intent" ]] || [[ -L "$intent" ]]; then
    require_commit_attempt_intent \
      "$intent" "$run_directory" "$candidate_receipt" || return
    durability_barrier_private_file "$intent" || return
    return 0
  fi
  local candidate_sha source_sha physical_sha identity_sha
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" \
      "commit-attempt candidate receipt"
  )" || return
  source_sha="$(
    private_file_sha256 "$RELEASE_SOURCE_MANIFEST" \
      "commit-attempt release source manifest"
  )" || return
  physical_sha="$(
    private_file_sha256 "$PHYSICAL_BACKUP_INVENTORY" \
      "commit-attempt physical inventory"
  )" || return
  identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "commit-attempt retained identity"
  )" || return
  local pending="$run_directory/.commit-attempting.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=commit_attempting" \
      "run_directory=$run_directory" \
      "candidate_sha256=$candidate_sha" \
      "release_source_sha256=$source_sha" \
      "physical_inventory_sha256=$physical_sha" \
      "retained_identity_sha256=$identity_sha" \
      "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" \
      "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" \
      >"$pending"
  ); then
    basic_fail "Could not stage the commit-attempt intent"
    return
  fi
  chmod 600 "$pending" || return
  durable_publish_private_file "$pending" "$intent" || return
  require_commit_attempt_intent \
    "$intent" "$run_directory" "$candidate_receipt" || return
  durability_barrier_private_file "$intent" || return
}

startup_evidence_path() {
  local run_directory="$1"
  local kind="$2"
  local outcome="$3"
  printf '%s/%s-startup-%s.evidence\n' \
    "$run_directory" "$kind" "$outcome"
}

current_epoch_sha_or_none() {
  if [[ -e "$ACTIVE_RELEASE_EPOCH_FILE" ]] || \
     [[ -L "$ACTIVE_RELEASE_EPOCH_FILE" ]]; then
    require_active_runtime_epoch_chain || return
    private_file_sha256 \
      "$ACTIVE_RELEASE_EPOCH_FILE" "active release epoch" || return
  else
    printf '%s\n' none
  fi
}

require_startup_evidence() {
  local kind="$1"
  local outcome="$2"
  local run_directory="$3"
  local candidate_receipt="$4"
  local authorization="$5"
  local retired_context="$6"
  local revision="$7"
  local evidence candidate_sha authorization_sha context_sha predecessor
  evidence="$(startup_evidence_path "$run_directory" "$kind" "$outcome")"
  candidate_sha="$(private_file_sha256 "$candidate_receipt" "candidate receipt")" \
    || return
  authorization_sha="$(
    private_file_sha256 "$authorization" "$kind startup authorization"
  )" || return
  context_sha="$(
    private_file_sha256 "$retired_context" "$kind retired fence context"
  )" || return
  if [[ -L "$evidence" ]] || [[ ! -f "$evidence" ]] || \
     [[ "$(stat -f '%u' "$evidence")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$evidence")" != "600" ]] || \
     [[ "$(stat -f '%l' "$evidence")" != "1" ]] || \
     [[ "$(wc -l <"$evidence" | tr -d '[:space:]')" != "7" ]] || \
     ! grep -Fqx "status=${kind}_startup_${outcome}" "$evidence" || \
     ! grep -Fqx "run_directory=$run_directory" "$evidence" || \
     ! grep -Fqx "candidate_sha256=$candidate_sha" "$evidence" || \
     ! grep -Fqx "authorization_sha256=$authorization_sha" "$evidence" || \
     ! grep -Fqx "retired_context_sha256=$context_sha" "$evidence" || \
     ! grep -Fqx "revision=$revision" "$evidence"; then
    basic_fail "$kind startup $outcome evidence is missing or inconsistent"
    return
  fi
  predecessor="$(
    private_context_value "$evidence" predecessor_epoch_sha256
  )" || return
  if [[ "$predecessor" != "none" ]] && \
     [[ ! "$predecessor" =~ ^[0-9a-f]{64}$ ]]; then
    basic_fail "$kind startup evidence has an invalid predecessor epoch"
    return
  fi
}

create_startup_evidence() {
  local kind="$1"
  local outcome="$2"
  local run_directory="$3"
  local candidate_receipt="$4"
  local authorization="$5"
  local retired_context="$6"
  local revision="$7"
  local evidence opposite_evidence opposite_outcome
  local pending candidate_sha authorization_sha context_sha
  local predecessor_epoch_sha
  case "$outcome" in
    complete)
      opposite_outcome=invalidated
      ;;
    invalidated)
      opposite_outcome=complete
      ;;
    *)
      basic_fail "Unsupported $kind startup evidence outcome: $outcome"
      return
      ;;
  esac
  evidence="$(startup_evidence_path "$run_directory" "$kind" "$outcome")"
  opposite_evidence="$(
    startup_evidence_path "$run_directory" "$kind" "$opposite_outcome"
  )" || return
  if [[ -e "$opposite_evidence" ]] || [[ -L "$opposite_evidence" ]]; then
    require_startup_evidence \
      "$kind" "$opposite_outcome" "$run_directory" "$candidate_receipt" \
      "$authorization" "$retired_context" "$revision" || return
    basic_fail \
      "$kind startup completion and invalidation are mutually exclusive"
    return
  fi
  if [[ -e "$evidence" ]] || [[ -L "$evidence" ]]; then
    require_startup_evidence \
      "$kind" "$outcome" "$run_directory" "$candidate_receipt" \
      "$authorization" "$retired_context" "$revision" || return
    durability_barrier_private_file "$evidence" || return
    return
  fi
  candidate_sha="$(private_file_sha256 "$candidate_receipt" "candidate receipt")" \
    || return
  authorization_sha="$(
    private_file_sha256 "$authorization" "$kind startup authorization"
  )" || return
  context_sha="$(
    private_file_sha256 "$retired_context" "$kind retired fence context"
  )" || return
  predecessor_epoch_sha="$(current_epoch_sha_or_none)" || return
  pending="$run_directory/.${kind}-startup-${outcome}.pending.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=${kind}_startup_${outcome}" \
      "run_directory=$run_directory" \
      "candidate_sha256=$candidate_sha" \
      "authorization_sha256=$authorization_sha" \
      "retired_context_sha256=$context_sha" \
      "revision=$revision" \
      "predecessor_epoch_sha256=$predecessor_epoch_sha" \
      >"$pending"
  ); then
    basic_fail "Could not create $kind startup $outcome evidence"
    return
  fi
  chmod 600 "$pending" || return
  durable_publish_private_file "$pending" "$evidence" || return
  require_startup_evidence \
    "$kind" "$outcome" "$run_directory" "$candidate_receipt" \
    "$authorization" "$retired_context" "$revision" || return
}

require_well_formed_active_runtime_epoch_file() {
  local epoch_file="$1"
  private_file_sha256 "$epoch_file" "active release epoch chain node" \
    >/dev/null || return
  local line_count
  line_count="$(wc -l <"$epoch_file" | tr -d '[:space:]')" || return
  if [[ "$line_count" != "14" ]]; then
    basic_fail "Active release epoch chain node has an invalid line count"
    return
  fi
  local key key_count
  local keys=(
    status kind run_directory candidate_sha256 authorization_sha256
    finalization_sha256 completion_evidence completion_sha256
    fence_context_sha256 retained_identity_sha256 revision
    predecessor_epoch_sha256 predecessor_epoch_archive
    predecessor_archive_sha256
  )
  for key in "${keys[@]}"; do
    key_count="$(awk -F= -v expected="$key" \
      '$1 == expected { count += 1 } END { print count + 0 }' \
      "$epoch_file")" || return
    if [[ "$key_count" != "1" ]]; then
      basic_fail "Active release epoch chain has a missing or duplicate key"
      return
    fi
  done
  local status kind run_directory candidate authorization finalization
  local completion completion_sha context_sha identity_sha revision
  local predecessor archive archive_sha
  status="$(private_context_value "$epoch_file" status)" || return
  kind="$(private_context_value "$epoch_file" kind)" || return
  run_directory="$(private_context_value "$epoch_file" run_directory)" || return
  candidate="$(private_context_value "$epoch_file" candidate_sha256)" || return
  authorization="$(private_context_value "$epoch_file" authorization_sha256)" \
    || return
  finalization="$(private_context_value "$epoch_file" finalization_sha256)" \
    || return
  completion="$(private_context_value "$epoch_file" completion_evidence)" \
    || return
  completion_sha="$(private_context_value "$epoch_file" completion_sha256)" \
    || return
  context_sha="$(private_context_value "$epoch_file" fence_context_sha256)" \
    || return
  identity_sha="$(private_context_value "$epoch_file" retained_identity_sha256)" \
    || return
  revision="$(private_context_value "$epoch_file" revision)" || return
  predecessor="$(private_context_value \
    "$epoch_file" predecessor_epoch_sha256)" || return
  archive="$(private_context_value \
    "$epoch_file" predecessor_epoch_archive)" || return
  archive_sha="$(private_context_value \
    "$epoch_file" predecessor_archive_sha256)" || return
  local hash_pattern='^[0-9a-f]{64}$'
  if [[ "$status" != "active_release_epoch" ]] || \
     { [[ "$kind" != "commit" ]] && [[ "$kind" != "resume" ]] && \
       [[ "$kind" != "rollback" ]]; } || \
     [[ "$run_directory" != "$RELEASE_STATE_DIRECTORY/"* ]] || \
     [[ ! "$candidate" =~ $hash_pattern ]] || \
     [[ ! "$authorization" =~ $hash_pattern ]] || \
     { [[ "$finalization" != "none" ]] && \
       [[ ! "$finalization" =~ $hash_pattern ]]; } || \
     [[ "$completion" != "$run_directory/"* ]] || \
     [[ ! "$completion_sha" =~ $hash_pattern ]] || \
     [[ ! "$context_sha" =~ $hash_pattern ]] || \
     [[ ! "$identity_sha" =~ $hash_pattern ]] || \
     { [[ "$revision" != "$CARESYNC_RETAINED_SOURCE_REVISION" ]] && \
       [[ "$revision" != "$CARESYNC_RETAINED_TARGET_REVISION" ]]; }; then
    basic_fail "Active release epoch chain node is malformed"
    return
  fi
  if [[ "$predecessor" == "none" ]]; then
    if [[ "$archive" != "none" ]] || [[ "$archive_sha" != "none" ]]; then
      basic_fail "Initial active release epoch unexpectedly names an archive"
      return
    fi
  elif [[ ! "$predecessor" =~ $hash_pattern ]] || \
       [[ "$archive" != \
          "$ACTIVE_RELEASE_EPOCH_HISTORY_DIRECTORY/$predecessor.epoch" ]] || \
       [[ "$archive_sha" != "$predecessor" ]]; then
    basic_fail "Active release epoch predecessor archive binding is invalid"
    return
  fi
}

require_active_runtime_epoch_chain() {
  local epoch_file="$ACTIVE_RELEASE_EPOCH_FILE"
  local predecessor archive archive_sha actual_sha
  local depth=0
  while :; do
    (( depth += 1 ))
    if (( depth > 10000 )); then
      basic_fail "Active release epoch history is unreasonably deep"
      return
    fi
    require_well_formed_active_runtime_epoch_file "$epoch_file" || return
    predecessor="$(private_context_value \
      "$epoch_file" predecessor_epoch_sha256)" || return
    archive="$(private_context_value \
      "$epoch_file" predecessor_epoch_archive)" || return
    archive_sha="$(private_context_value \
      "$epoch_file" predecessor_archive_sha256)" || return
    if [[ "$predecessor" == "none" ]]; then
      return 0
    fi
    actual_sha="$(
      private_file_sha256 "$archive" "archived predecessor release epoch"
    )" || return
    if [[ "$actual_sha" != "$predecessor" ]] || \
       [[ "$archive_sha" != "$predecessor" ]]; then
      basic_fail "Archived predecessor release epoch content has drifted"
      return
    fi
    epoch_file="$archive"
  done
}

archive_current_active_runtime_epoch() {
  local expected_sha="$1"
  require_active_runtime_epoch_chain || return
  local current_sha
  current_sha="$(
    private_file_sha256 "$ACTIVE_RELEASE_EPOCH_FILE" \
      "current active release epoch"
  )" || return
  if [[ "$current_sha" != "$expected_sha" ]]; then
    basic_fail "Current active release epoch is not the expected predecessor"
    return
  fi
  durable_ensure_private_directory \
    "$ACTIVE_RELEASE_EPOCH_HISTORY_DIRECTORY" || return
  local archive="$ACTIVE_RELEASE_EPOCH_HISTORY_DIRECTORY/$current_sha.epoch"
  if [[ -e "$archive" ]] || [[ -L "$archive" ]]; then
    local archived_sha
    archived_sha="$(
      private_file_sha256 "$archive" "archived active release epoch"
    )" || return
    if [[ "$archived_sha" != "$current_sha" ]]; then
      basic_fail "Existing active release epoch archive has different bytes"
      return
    fi
    durability_barrier_private_file "$archive" || return
    return 0
  fi
  local pending="$ACTIVE_RELEASE_EPOCH_HISTORY_DIRECTORY/.epoch.pending.$$.$RANDOM"
  /bin/cp -X "$ACTIVE_RELEASE_EPOCH_FILE" "$pending" || return
  chmod 600 "$pending" || return
  local pending_sha
  pending_sha="$(
    private_file_sha256 "$pending" "pending active release epoch archive"
  )" || return
  if [[ "$pending_sha" != "$current_sha" ]]; then
    basic_fail "Pending active release epoch archive changed bytes"
    return
  fi
  durable_publish_private_file "$pending" "$archive" || return
  durability_barrier_private_file "$archive" || return
  require_active_runtime_epoch_chain || return
}

require_exact_active_runtime_epoch() {
  local kind="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local authorization="$4"
  local finalization_receipt="$5"
  local completion_evidence="$6"
  local fence_context="$7"
  local revision="$8"
  local predecessor="$9"
  local candidate_sha authorization_sha finalization_sha completion_sha
  local context_sha identity_sha
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" "epoch candidate receipt"
  )" || return
  authorization_sha="$(
    private_file_sha256 "$authorization" "epoch authorization"
  )" || return
  if [[ "$finalization_receipt" == "none" ]]; then
    finalization_sha=none
  else
    finalization_sha="$(
      private_file_sha256 "$finalization_receipt" \
        "epoch finalization receipt"
    )" || return
  fi
  completion_sha="$(
    private_file_sha256 "$completion_evidence" \
      "epoch completion evidence"
  )" || return
  context_sha="$(
    private_file_sha256 "$fence_context" "epoch fence context"
  )" || return
  identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "epoch retained identity"
  )" || return
  require_active_runtime_epoch_chain || return
  local predecessor_archive predecessor_archive_sha
  if [[ "$predecessor" == "none" ]]; then
    predecessor_archive=none
    predecessor_archive_sha=none
  else
    predecessor_archive="$ACTIVE_RELEASE_EPOCH_HISTORY_DIRECTORY/$predecessor.epoch"
    predecessor_archive_sha="$predecessor"
  fi
  if [[ -L "$ACTIVE_RELEASE_EPOCH_FILE" ]] || \
     [[ ! -f "$ACTIVE_RELEASE_EPOCH_FILE" ]] || \
     [[ "$(stat -f '%u' "$ACTIVE_RELEASE_EPOCH_FILE")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$ACTIVE_RELEASE_EPOCH_FILE")" != "600" ]] || \
     [[ "$(stat -f '%l' "$ACTIVE_RELEASE_EPOCH_FILE")" != "1" ]] || \
     [[ "$(wc -l <"$ACTIVE_RELEASE_EPOCH_FILE" | \
       tr -d '[:space:]')" != "14" ]] || \
     ! grep -Fqx "status=active_release_epoch" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "kind=$kind" "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "run_directory=$run_directory" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "candidate_sha256=$candidate_sha" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "authorization_sha256=$authorization_sha" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "finalization_sha256=$finalization_sha" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "completion_evidence=$completion_evidence" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "completion_sha256=$completion_sha" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "fence_context_sha256=$context_sha" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "retained_identity_sha256=$identity_sha" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "revision=$revision" "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "predecessor_epoch_sha256=$predecessor" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "predecessor_epoch_archive=$predecessor_archive" \
       "$ACTIVE_RELEASE_EPOCH_FILE" || \
     ! grep -Fqx "predecessor_archive_sha256=$predecessor_archive_sha" \
       "$ACTIVE_RELEASE_EPOCH_FILE"; then
    basic_fail "Active release epoch does not match the completed transition"
    return
  fi
}

publish_active_runtime_epoch() {
  local kind="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local authorization="$4"
  local finalization_receipt="$5"
  local completion_evidence="$6"
  local fence_context="$7"
  local revision="$8"
  local predecessor candidate_sha authorization_sha finalization_sha
  local completion_sha context_sha identity_sha current_sha pending
  predecessor="$(
    private_context_value "$completion_evidence" predecessor_epoch_sha256
  )" || return
  if [[ "$predecessor" != "none" ]] && \
     [[ ! "$predecessor" =~ ^[0-9a-f]{64}$ ]]; then
    basic_fail "Completion evidence has an invalid predecessor epoch"
    return
  fi
  if [[ -e "$ACTIVE_RELEASE_EPOCH_FILE" ]] || \
     [[ -L "$ACTIVE_RELEASE_EPOCH_FILE" ]]; then
    if require_exact_active_runtime_epoch \
      "$kind" "$run_directory" "$candidate_receipt" "$authorization" \
      "$finalization_receipt" "$completion_evidence" "$fence_context" \
      "$revision" "$predecessor" 2>/dev/null; then
      durability_barrier_private_file "$ACTIVE_RELEASE_EPOCH_FILE" || return
      return
    fi
    current_sha="$(
      private_file_sha256 "$ACTIVE_RELEASE_EPOCH_FILE" \
        "predecessor active release epoch"
    )" || return
    if [[ "$current_sha" != "$predecessor" ]]; then
      basic_fail \
        "Completed transition cannot supersede a different current release epoch"
      return
    fi
    archive_current_active_runtime_epoch "$predecessor" || return
  elif [[ "$predecessor" != "none" ]]; then
    basic_fail "Completed transition lost its predecessor release epoch"
    return
  fi
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" "epoch candidate receipt"
  )" || return
  authorization_sha="$(
    private_file_sha256 "$authorization" "epoch authorization"
  )" || return
  if [[ "$finalization_receipt" == "none" ]]; then
    finalization_sha=none
  else
    finalization_sha="$(
      private_file_sha256 "$finalization_receipt" \
        "epoch finalization receipt"
    )" || return
  fi
  completion_sha="$(
    private_file_sha256 "$completion_evidence" \
      "epoch completion evidence"
  )" || return
  context_sha="$(
    private_file_sha256 "$fence_context" "epoch fence context"
  )" || return
  identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "epoch retained identity"
  )" || return
  local predecessor_archive predecessor_archive_sha
  if [[ "$predecessor" == "none" ]]; then
    predecessor_archive=none
    predecessor_archive_sha=none
  else
    predecessor_archive="$ACTIVE_RELEASE_EPOCH_HISTORY_DIRECTORY/$predecessor.epoch"
    predecessor_archive_sha="$predecessor"
  fi
  pending="$RUNTIME_DIR/.active-release-epoch.pending.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=active_release_epoch" \
      "kind=$kind" \
      "run_directory=$run_directory" \
      "candidate_sha256=$candidate_sha" \
      "authorization_sha256=$authorization_sha" \
      "finalization_sha256=$finalization_sha" \
      "completion_evidence=$completion_evidence" \
      "completion_sha256=$completion_sha" \
      "fence_context_sha256=$context_sha" \
      "retained_identity_sha256=$identity_sha" \
      "revision=$revision" \
      "predecessor_epoch_sha256=$predecessor" \
      "predecessor_epoch_archive=$predecessor_archive" \
      "predecessor_archive_sha256=$predecessor_archive_sha" \
      >"$pending"
  ); then
    basic_fail "Could not stage the active release epoch"
    return
  fi
  chmod 600 "$pending" || return
  if [[ -e "$ACTIVE_RELEASE_EPOCH_FILE" ]] || \
     [[ -L "$ACTIVE_RELEASE_EPOCH_FILE" ]]; then
    durable_replace_private_file \
      "$pending" "$ACTIVE_RELEASE_EPOCH_FILE" || return
  else
    durable_publish_private_file \
      "$pending" "$ACTIVE_RELEASE_EPOCH_FILE" || return
  fi
  require_exact_active_runtime_epoch \
    "$kind" "$run_directory" "$candidate_receipt" "$authorization" \
    "$finalization_receipt" "$completion_evidence" "$fence_context" \
    "$revision" "$predecessor" || return
  durability_barrier_private_file "$ACTIVE_RELEASE_EPOCH_FILE" || return
}

reject_consumed_or_invalidated_startup() {
  local kind="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local authorization="$4"
  local retired_context="$5"
  local revision="$6"
  local complete invalidated
  complete="$(startup_evidence_path "$run_directory" "$kind" complete)"
  invalidated="$(startup_evidence_path "$run_directory" "$kind" invalidated)"
  if [[ -e "$complete" ]] || [[ -L "$complete" ]]; then
    require_startup_evidence \
      "$kind" complete "$run_directory" "$candidate_receipt" \
      "$authorization" "$retired_context" "$revision" || return
    basic_fail \
      "$kind controlled startup already completed; use ordinary startup"
    return
  fi
  if [[ -e "$invalidated" ]] || [[ -L "$invalidated" ]]; then
    require_startup_evidence \
      "$kind" invalidated "$run_directory" "$candidate_receipt" \
      "$authorization" "$retired_context" "$revision" || return
    basic_fail \
      "$kind controlled startup was safely retired; prepare a fresh candidate"
    return
  fi
  return 0
}

restore_runtime_role_states_from_private_context() {
  local context="$1"
  local app_prior ingest_prior
  app_prior="$(private_context_value "$context" app_prior_login)" || return
  ingest_prior="$(private_context_value "$context" ingest_prior_login)" || return
  if [[ "$app_prior" != "login" && "$app_prior" != "nologin" ]] || \
     [[ "$ingest_prior" != "login" && "$ingest_prior" != "nologin" ]]; then
    basic_fail "Private startup context contains invalid writer-role states"
    return
  fi
  # The read-only health identity must be fully closed before either writer
  # can be restored. A partial writer restoration may return early.
  close_release_probe_after_controlled_health || return
  if ! basic_set_role_login_state caresync_basic_app "$app_prior"; then
    basic_set_role_login_state caresync_basic_app nologin || true
    basic_set_role_login_state caresync_transport_evidence_ingest nologin || true
    basic_fail "Could not restore the application role from startup evidence"
    return
  fi
  if ! basic_set_role_login_state \
    caresync_transport_evidence_ingest "$ingest_prior"; then
    basic_set_role_login_state caresync_basic_app nologin || true
    basic_set_role_login_state caresync_transport_evidence_ingest nologin || true
    basic_fail "Could not restore both writer roles from startup evidence"
    return
  fi
  if [[ "$(basic_role_login_state caresync_basic_app)" != "$app_prior" ]] || \
     [[ "$(basic_role_login_state caresync_transport_evidence_ingest)" != \
        "$ingest_prior" ]]; then
    basic_fail "Startup writer-role restoration did not persist exactly"
    return
  fi
  require_release_probe_contract nologin || return
  require_release_probe_read_scope closed || return
}

post_retirement_role_restoration_completed_path() {
  local run_directory="$1"
  local operation="$2"
  if [[ ! "$operation" =~ ^[a-z0-9-]+$ ]]; then
    basic_fail "Post-retirement role-restoration operation is invalid"
    return
  fi
  printf '%s/%s-role-restoration.completed\n' \
    "$run_directory" "$operation"
}

require_post_retirement_file_binding() {
  local record="$1"
  local path_key="$2"
  local sha_key="$3"
  local expected_path="$4"
  local allow_none="$5"
  local bound_path bound_sha actual_sha
  bound_path="$(private_context_value "$record" "$path_key")" || return
  bound_sha="$(private_context_value "$record" "$sha_key")" || return
  if [[ "$bound_path" == "none" ]] || [[ "$bound_sha" == "none" ]]; then
    if [[ "$allow_none" != "true" ]] || \
       [[ "$bound_path" != "none" ]] || [[ "$bound_sha" != "none" ]]; then
      basic_fail "Post-retirement $path_key binding cannot be absent"
      return
    fi
    return 0
  fi
  if [[ "$bound_path" != "$expected_path" ]] || \
     [[ ! "$bound_sha" =~ ^[0-9a-f]{64}$ ]]; then
    basic_fail "Post-retirement $path_key binding is outside its release run"
    return
  fi
  actual_sha="$(
    private_file_sha256 "$bound_path" "post-retirement $path_key"
  )" || return
  if [[ "$actual_sha" != "$bound_sha" ]]; then
    basic_fail "Post-retirement $path_key binding has drifted"
    return
  fi
}

require_post_retirement_role_restoration_record() {
  local record="$1"
  local operation="$2"
  local run_directory="$3"
  local retired_context="$4"
  local revision="$5"
  if [[ -L "$record" ]] || [[ ! -f "$record" ]] || \
     [[ "$(stat -f '%u' "$record")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$record")" != "600" ]] || \
     [[ "$(stat -f '%l' "$record")" != "1" ]] || \
     [[ "$(wc -l <"$record" | tr -d '[:space:]')" != "22" ]]; then
    basic_fail "Post-retirement role-restoration record is not private evidence"
    return
  fi
  local context_sha identity_sha app_prior ingest_prior
  local source_root source_manifest active_epoch
  local candidate_receipt authorization finalization_receipt
  local completion_evidence
  context_sha="$(
    private_context_value "$record" retired_context_sha256
  )" || return
  identity_sha="$(
    private_context_value "$record" retained_identity_sha256
  )" || return
  app_prior="$(private_context_value "$record" app_prior_login)" || return
  ingest_prior="$(private_context_value "$record" ingest_prior_login)" || return
  source_root="$(private_context_value "$record" release_source_root)" || return
  source_manifest="$(
    private_context_value "$record" release_source_manifest
  )" || return
  active_epoch="$(private_context_value "$record" active_epoch)" || return
  candidate_receipt="$(
    private_context_value "$record" candidate_receipt
  )" || return
  authorization="$(private_context_value "$record" authorization)" || return
  finalization_receipt="$(
    private_context_value "$record" finalization_receipt
  )" || return
  completion_evidence="$(
    private_context_value "$record" completion_evidence
  )" || return
  if ! grep -Fqx \
       "status=post_retirement_role_restoration_pending" "$record" || \
     ! grep -Fqx "operation=$operation" "$record" || \
     ! grep -Fqx "run_directory=$run_directory" "$record" || \
     ! grep -Fqx "retired_context=$retired_context" "$record" || \
     ! grep -Fqx "retired_context_sha256=$context_sha" "$record" || \
     ! grep -Fqx "app_prior_login=$app_prior" "$record" || \
     ! grep -Fqx "ingest_prior_login=$ingest_prior" "$record" || \
     ! grep -Fqx "revision=$revision" "$record" || \
     ! grep -Fqx "retained_identity_sha256=$identity_sha" "$record" || \
     ! grep -Fqx "release_source_root=$source_root" "$record" || \
     ! grep -Fqx "release_source_manifest=$source_manifest" "$record" || \
     ! grep -Fqx "active_epoch=$active_epoch" "$record" || \
     ! grep -Fqx "candidate_receipt=$candidate_receipt" "$record" || \
     ! grep -Fqx "authorization=$authorization" "$record" || \
     ! grep -Fqx "finalization_receipt=$finalization_receipt" "$record" || \
     ! grep -Fqx "completion_evidence=$completion_evidence" "$record" || \
     [[ ! "$context_sha" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$identity_sha" =~ ^[0-9a-f]{64}$ ]] || \
     { [[ "$app_prior" != "login" ]] && [[ "$app_prior" != "nologin" ]]; } || \
     { [[ "$ingest_prior" != "login" ]] && \
       [[ "$ingest_prior" != "nologin" ]]; } || \
     { [[ "$revision" != "$CARESYNC_RETAINED_SOURCE_REVISION" ]] && \
       [[ "$revision" != "$CARESYNC_RETAINED_TARGET_REVISION" ]]; }; then
    basic_fail "Post-retirement role-restoration record is invalid"
    return
  fi
  local actual_identity_sha
  actual_identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "post-retirement retained identity"
  )" || return
  if [[ "$actual_identity_sha" != "$identity_sha" ]]; then
    basic_fail "Post-retirement retained identity binding has drifted"
    return
  fi
  if [[ "$source_root" != "$run_directory/release-source" ]] || \
     [[ "$source_manifest" != \
        "$run_directory/release-source.manifest.json" ]]; then
    basic_fail "Post-retirement release source is outside its release run"
    return
  fi
  require_post_retirement_file_binding \
    "$record" release_source_manifest release_source_manifest_sha256 \
    "$run_directory/release-source.manifest.json" false || return
  require_post_retirement_file_binding \
    "$record" active_epoch active_epoch_sha256 \
    "$ACTIVE_RELEASE_EPOCH_FILE" true || return
  require_post_retirement_file_binding \
    "$record" candidate_receipt candidate_sha256 \
    "$run_directory/candidate-receipt.json" true || return
  local expected_authorization="$run_directory/$(
    basename "$authorization"
  )"
  if [[ "$authorization" != "none" ]] && \
     [[ "$authorization" != "$run_directory/commit-receipt.json" ]] && \
     [[ "$authorization" != \
        "$run_directory/resume-0039.authorization.json" ]] && \
     [[ "$authorization" != \
        "$run_directory/rollback-resume-0039.authorization.json" ]]; then
    basic_fail "Post-retirement authorization is outside its release run"
    return
  fi
  require_post_retirement_file_binding \
    "$record" authorization authorization_sha256 \
    "$expected_authorization" true || return
  require_post_retirement_file_binding \
    "$record" finalization_receipt finalization_sha256 \
    "$run_directory/finalization-receipt.json" true || return
  if [[ "$completion_evidence" != "none" ]] && \
     [[ "$completion_evidence" != \
        "$run_directory/"*-startup-complete.evidence ]] && \
     [[ "$completion_evidence" != \
        "$run_directory/"*-startup-invalidated.evidence ]]; then
    basic_fail "Post-retirement completion evidence is outside its release run"
    return
  fi
  require_post_retirement_file_binding \
    "$record" completion_evidence completion_sha256 \
    "$completion_evidence" true || return
  if [[ -e "$retired_context" ]] || [[ -L "$retired_context" ]]; then
    local actual_context_sha
    actual_context_sha="$(
      private_file_sha256 "$retired_context" \
        "post-retirement fence context"
    )" || return
    if [[ "$actual_context_sha" != "$context_sha" ]]; then
      basic_fail "Post-retirement fence context binding has drifted"
      return
    fi
  fi
}

prepare_post_retirement_role_restoration() {
  local operation="$1"
  local run_directory="$2"
  local retired_context="$3"
  local revision="$4"
  local active_context="$RELEASE_FENCE_DIRECTORY/context"
  basic_require_runtime_roles_fenced || return
  require_release_probe_contract nologin || return
  local completed
  completed="$(
    post_retirement_role_restoration_completed_path \
      "$run_directory" "$operation"
  )" || return
  if [[ -e "$completed" ]] || [[ -L "$completed" ]]; then
    basic_fail "Post-retirement role restoration is already completed"
    return
  fi
  if [[ -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] || \
     [[ -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    require_post_retirement_role_restoration_record \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" "$operation" \
      "$run_directory" "$retired_context" "$revision" || return
    durability_barrier_private_file \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" || return
    return 0
  fi
  local context_sha identity_sha app_prior ingest_prior
  local source_root=none source_manifest=none source_manifest_sha=none
  local active_epoch=none active_epoch_sha=none
  local candidate_receipt=none candidate_sha=none
  local authorization=none authorization_sha=none
  local finalization_receipt=none finalization_sha=none
  local completion_evidence=none completion_sha=none
  context_sha="$(
    private_file_sha256 "$active_context" "active release fence context"
  )" || return
  identity_sha="$(
    private_file_sha256 "$RETAINED_IDENTITY_FILE" \
      "post-retirement retained identity"
  )" || return
  app_prior="$(private_context_value "$active_context" app_prior_login)" || return
  ingest_prior="$(
    private_context_value "$active_context" ingest_prior_login
  )" || return
  if [[ -L "$run_directory/release-source" ]] || \
       [[ ! -d "$run_directory/release-source" ]] || \
       [[ -L "$run_directory/release-source.manifest.json" ]] || \
       [[ ! -f "$run_directory/release-source.manifest.json" ]] || \
       { [[ "$operation" != "prepare-abort" ]] && \
         { [[ -L "$run_directory/candidate-receipt.json" ]] || \
           [[ ! -f "$run_directory/candidate-receipt.json" ]]; }; }; then
    basic_fail \
      "Post-retirement recovery requires this candidate's captured release source"
    return
  fi
  source_root="$run_directory/release-source"
  source_manifest="$run_directory/release-source.manifest.json"
  source_manifest_sha="$(
    private_file_sha256 "$source_manifest" \
      "post-retirement release source manifest"
  )" || return
  if [[ "$operation" == "prepare-abort" ]]; then
    bootstrap_verify_pre_candidate_source \
      "$run_directory" "$source_manifest_sha" || return
  else
    bootstrap_verify_captured_release_source \
      "$run_directory" "$source_manifest_sha" || return
  fi
  if [[ -f "$ACTIVE_RELEASE_EPOCH_FILE" ]] && \
     [[ ! -L "$ACTIVE_RELEASE_EPOCH_FILE" ]]; then
    active_epoch="$ACTIVE_RELEASE_EPOCH_FILE"
    active_epoch_sha="$(
      private_file_sha256 "$active_epoch" "post-retirement active epoch"
    )" || return
  fi
  if [[ -f "$run_directory/candidate-receipt.json" ]] && \
     [[ ! -L "$run_directory/candidate-receipt.json" ]]; then
    candidate_receipt="$run_directory/candidate-receipt.json"
    candidate_sha="$(
      private_file_sha256 "$candidate_receipt" \
        "post-retirement candidate receipt"
    )" || return
  fi
  case "$operation" in
    commit-*)
      authorization="$run_directory/commit-receipt.json"
      ;;
    resume-*)
      authorization="$run_directory/resume-0039.authorization.json"
      ;;
    rollback-*)
      authorization="$run_directory/rollback-resume-0039.authorization.json"
      ;;
  esac
  if [[ "$authorization" != "none" ]]; then
    authorization_sha="$(
      private_file_sha256 "$authorization" \
        "post-retirement startup authorization"
    )" || return
  fi
  if [[ -f "$run_directory/finalization-receipt.json" ]] && \
     [[ ! -L "$run_directory/finalization-receipt.json" ]]; then
    finalization_receipt="$run_directory/finalization-receipt.json"
    finalization_sha="$(
      private_file_sha256 "$finalization_receipt" \
        "post-retirement finalization receipt"
    )" || return
  fi
  case "$operation" in
    *-complete)
      completion_evidence="$run_directory/${operation%-complete}-startup-complete.evidence"
      ;;
    *-invalidated)
      completion_evidence="$run_directory/${operation%-invalidated}-startup-invalidated.evidence"
      ;;
  esac
  if [[ "$completion_evidence" != "none" ]]; then
    completion_sha="$(
      private_file_sha256 "$completion_evidence" \
        "post-retirement completion evidence"
    )" || return
  fi
  local pending="$RUNTIME_DIR/.post-retirement-role-restoration.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=post_retirement_role_restoration_pending" \
      "operation=$operation" \
      "run_directory=$run_directory" \
      "retired_context=$retired_context" \
      "retired_context_sha256=$context_sha" \
      "app_prior_login=$app_prior" \
      "ingest_prior_login=$ingest_prior" \
      "revision=$revision" \
      "retained_identity_sha256=$identity_sha" \
      "release_source_root=$source_root" \
      "release_source_manifest=$source_manifest" \
      "release_source_manifest_sha256=$source_manifest_sha" \
      "active_epoch=$active_epoch" \
      "active_epoch_sha256=$active_epoch_sha" \
      "candidate_receipt=$candidate_receipt" \
      "candidate_sha256=$candidate_sha" \
      "authorization=$authorization" \
      "authorization_sha256=$authorization_sha" \
      "finalization_receipt=$finalization_receipt" \
      "finalization_sha256=$finalization_sha" \
      "completion_evidence=$completion_evidence" \
      "completion_sha256=$completion_sha" \
      >"$pending"
  ); then
    basic_fail "Could not stage post-retirement role restoration"
    return
  fi
  chmod 600 "$pending" || return
  require_post_retirement_role_restoration_record \
    "$pending" "$operation" "$run_directory" "$retired_context" \
    "$revision" || return
  durable_publish_private_file \
    "$pending" "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" || return
  require_post_retirement_role_restoration_record \
    "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" "$operation" \
    "$run_directory" "$retired_context" "$revision" || return
}

complete_post_retirement_role_restoration() {
  local operation="$1"
  local run_directory="$2"
  local retired_context="$3"
  local revision="$4"
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    basic_fail "Writer roles cannot be restored while a release fence is active"
    return
  fi
  local completed record
  completed="$(
    post_retirement_role_restoration_completed_path \
      "$run_directory" "$operation"
  )" || return
  if [[ -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] || \
     [[ -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    if [[ -e "$completed" ]] || [[ -L "$completed" ]]; then
      basic_fail "Role-restoration pending and completed records coexist"
      return
    fi
    record="$POST_RETIREMENT_ROLE_RESTORATION_PENDING"
  else
    record="$completed"
  fi
  require_post_retirement_role_restoration_record \
    "$record" "$operation" "$run_directory" "$retired_context" \
    "$revision" || return
  if [[ ! -e "$retired_context" ]] || [[ -L "$retired_context" ]]; then
    basic_fail "Retired fence context is unavailable for role restoration"
    return
  fi
  basic_verify_retained_identity || return
  # A prior attempt may have lost power after restoring only one writer.
  # Re-establish the no-writer posture from the durable pending record before
  # replaying either prior state.
  fence_runtime_roles || return
  basic_quiesce_application || return
  basic_assert_no_cluster_clients || return
  basic_require_exact_revision "$revision" || return
  restore_runtime_role_states_from_private_context "$retired_context" || return
  if [[ "$record" == "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    durable_publish_private_file "$record" "$completed" || return
  fi
  require_post_retirement_role_restoration_record \
    "$completed" "$operation" "$run_directory" "$retired_context" \
    "$revision" || return
  durability_barrier_private_file "$completed" || return
}

load_pending_post_retirement_role_restoration() {
  if [[ -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] || \
     [[ ! -f "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] || \
     [[ "$(stat -f '%u' "$POST_RETIREMENT_ROLE_RESTORATION_PENDING")" != \
        "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$POST_RETIREMENT_ROLE_RESTORATION_PENDING")" != \
        "600" ]] || \
     [[ "$(stat -f '%l' "$POST_RETIREMENT_ROLE_RESTORATION_PENDING")" != \
        "1" ]] || \
     [[ "$(wc -l <"$POST_RETIREMENT_ROLE_RESTORATION_PENDING" | \
       tr -d '[:space:]')" != "22" ]]; then
    basic_fail "Pending post-retirement role restoration is unsafe"
    return
  fi
  PENDING_ROLE_RESTORATION_OPERATION="$(
    private_context_value \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" operation
  )" || return
  PENDING_ROLE_RESTORATION_RUN="$(
    private_context_value \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" run_directory
  )" || return
  PENDING_ROLE_RESTORATION_CONTEXT="$(
    private_context_value \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" retired_context
  )" || return
  PENDING_ROLE_RESTORATION_REVISION="$(
    private_context_value \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" revision
  )" || return
  PENDING_ROLE_RESTORATION_SOURCE_ROOT="$(
    private_context_value \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" release_source_root
  )" || return
  PENDING_ROLE_RESTORATION_SOURCE_MANIFEST="$(
    private_context_value \
      "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" release_source_manifest
  )" || return
  require_post_retirement_role_restoration_record \
    "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" \
    "$PENDING_ROLE_RESTORATION_OPERATION" \
    "$PENDING_ROLE_RESTORATION_RUN" \
    "$PENDING_ROLE_RESTORATION_CONTEXT" \
    "$PENDING_ROLE_RESTORATION_REVISION" || return
}

preflight_pending_post_retirement_role_restoration() {
  if [[ ! -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] && \
     [[ ! -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    return 0
  fi
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    basic_fail "Active release fence dominates pending role restoration"
    return
  fi
  load_pending_post_retirement_role_restoration || return
  if [[ ! -e "$PENDING_ROLE_RESTORATION_CONTEXT" ]] || \
     [[ -L "$PENDING_ROLE_RESTORATION_CONTEXT" ]]; then
    basic_fail "Pending role restoration has no retired fence context"
    return
  fi
}

recover_pending_post_retirement_role_restoration() {
  preflight_pending_post_retirement_role_restoration || return
  if [[ ! -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] && \
     [[ ! -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    return 0
  fi
  complete_post_retirement_role_restoration \
    "$PENDING_ROLE_RESTORATION_OPERATION" \
    "$PENDING_ROLE_RESTORATION_RUN" \
    "$PENDING_ROLE_RESTORATION_CONTEXT" \
    "$PENDING_ROLE_RESTORATION_REVISION" || return
}

pending_post_retirement_recovery_source_root() {
  if [[ ! -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] && \
     [[ ! -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    printf '%s\n' none
    return 0
  fi
  load_pending_post_retirement_role_restoration || return
  if [[ "$PENDING_ROLE_RESTORATION_SOURCE_ROOT" == "none" ]]; then
    printf '%s\n' none
    return 0
  fi
  local expected_manifest_sha
  expected_manifest_sha="$(
    private_context_value "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" \
      release_source_manifest_sha256
  )" || return
  if [[ "$PENDING_ROLE_RESTORATION_OPERATION" == "prepare-abort" ]]; then
    bootstrap_verify_pre_candidate_source \
      "$PENDING_ROLE_RESTORATION_RUN" "$expected_manifest_sha" || return
  else
    bootstrap_verify_captured_release_source \
      "$PENDING_ROLE_RESTORATION_RUN" "$expected_manifest_sha" || return
  fi
  printf '%s\n' "$PENDING_ROLE_RESTORATION_SOURCE_ROOT"
}

invalidate_reactivated_prepared_start() {
  local kind="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local authorization="$4"
  local revision="$5"
  basic_quiesce_application || return
  basic_assert_no_cluster_clients || return
  require_matching_fence "$run_directory" "$candidate_receipt" || return
  fence_runtime_roles || return
  create_startup_evidence \
    "$kind" invalidated "$run_directory" "$candidate_receipt" \
    "$authorization" "$RELEASE_FENCE_DIRECTORY/context" "$revision" || return
  prepare_post_retirement_role_restoration \
    "$kind-invalidated" "$run_directory" \
    "$run_directory/fence-retired/context" "$revision" || return
  remove_matching_fence "$run_directory" "$candidate_receipt" || return
  require_startup_evidence \
    "$kind" invalidated "$run_directory" "$candidate_receipt" \
    "$authorization" "$run_directory/fence-retired/context" "$revision" || return
  complete_post_retirement_role_restoration \
    "$kind-invalidated" "$run_directory" \
    "$run_directory/fence-retired/context" "$revision" || return
  CONTROLLED_RUNTIME_WINDOW_FINALIZED=true
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  disarm_controlled_runtime_window_cleanup
}

invalidate_reactivated_rollback_start() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local authorization="$5"
  basic_quiesce_application || return
  basic_assert_no_cluster_clients || return
  require_matching_rollback_fence \
    "$run_directory" "$candidate_receipt" \
    "$commit_receipt" "$finalization_receipt" || return
  fence_runtime_roles || return
  create_startup_evidence \
    rollback invalidated "$run_directory" "$candidate_receipt" \
    "$authorization" "$RELEASE_FENCE_DIRECTORY/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  prepare_post_retirement_role_restoration \
    rollback-invalidated "$run_directory" \
    "$run_directory/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  remove_matching_rollback_fence \
    "$run_directory" "$candidate_receipt" \
    "$commit_receipt" "$finalization_receipt" || return
  require_startup_evidence \
    rollback invalidated "$run_directory" "$candidate_receipt" \
    "$authorization" "$run_directory/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  complete_post_retirement_role_restoration \
    rollback-invalidated "$run_directory" \
    "$run_directory/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  CONTROLLED_RUNTIME_WINDOW_FINALIZED=true
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  disarm_controlled_runtime_window_cleanup
}

ACTIVE_INVALIDATION_FINISHED=false
finish_active_prepared_invalidation_if_present() {
  local kind="$1"
  local run_directory="$2"
  local candidate_receipt="$3"
  local authorization="$4"
  local revision="$5"
  ACTIVE_INVALIDATION_FINISHED=false
  local invalidated
  invalidated="$(
    startup_evidence_path "$run_directory" "$kind" invalidated
  )" || return
  if [[ ! -e "$invalidated" ]] && [[ ! -L "$invalidated" ]]; then
    return 0
  fi
  require_startup_evidence \
    "$kind" invalidated "$run_directory" "$candidate_receipt" \
    "$authorization" "$RELEASE_FENCE_DIRECTORY/context" "$revision" || return
  arm_controlled_runtime_window_cleanup
  CONTROLLED_RUNTIME_WINDOW_OPEN=true
  basic_quiesce_application || return
  if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_start_postgres || return
  fi
  basic_verify_retained_identity || return
  fence_runtime_roles || return
  basic_assert_no_cluster_clients || return
  invalidate_reactivated_prepared_start \
    "$kind" "$run_directory" "$candidate_receipt" \
    "$authorization" "$revision" || return
  ACTIVE_INVALIDATION_FINISHED=true
}

finish_active_rollback_invalidation_if_present() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local authorization="$5"
  ACTIVE_INVALIDATION_FINISHED=false
  local invalidated
  invalidated="$(
    startup_evidence_path "$run_directory" rollback invalidated
  )" || return
  if [[ ! -e "$invalidated" ]] && [[ ! -L "$invalidated" ]]; then
    return 0
  fi
  require_startup_evidence \
    rollback invalidated "$run_directory" "$candidate_receipt" \
    "$authorization" "$RELEASE_FENCE_DIRECTORY/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  arm_controlled_runtime_window_cleanup
  CONTROLLED_RUNTIME_WINDOW_OPEN=true
  basic_quiesce_application || return
  if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_start_postgres || return
  fi
  basic_verify_retained_identity || return
  fence_runtime_roles || return
  basic_assert_no_cluster_clients || return
  invalidate_reactivated_rollback_start \
    "$run_directory" "$candidate_receipt" "$commit_receipt" \
    "$finalization_receipt" "$authorization" || return
  ACTIVE_INVALIDATION_FINISHED=true
}

create_stopped_0042_evidence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local data_directory="$5"
  local system_identifier="$6"
  local evidence="$run_directory/rollback-stopped-0042.evidence"
  if [[ -e "$evidence" ]] || [[ -L "$evidence" ]]; then
    verify_stopped_0042_evidence \
      "$run_directory" "$candidate_receipt" "$commit_receipt" \
      "$finalization_receipt" "$data_directory" "$system_identifier" || return
    durability_barrier_private_file "$evidence" || return
    return
  fi
  local candidate_sha commit_sha finalization_sha
  local pending="$run_directory/.rollback-stopped-0042.pending.$$.$RANDOM"
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" "candidate receipt"
  )" || return
  commit_sha="$(private_file_sha256 "$commit_receipt" "commit receipt")" \
    || return
  finalization_sha="$(
    private_file_sha256 "$finalization_receipt" "finalization receipt"
  )" || return
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=stopped_retained_0042" \
      "data_directory=$data_directory" \
      "system_identifier=$system_identifier" \
      "cluster_state=shut down" \
      "revision=$CARESYNC_RETAINED_TARGET_REVISION" \
      "candidate_sha256=$candidate_sha" \
      "commit_sha256=$commit_sha" \
      "finalization_sha256=$finalization_sha" \
      >"$pending"
  ); then
    basic_fail "Could not seal stopped 0042 rollback evidence"
    return
  fi
  chmod 600 "$pending" || return
  durable_publish_private_file "$pending" "$evidence" || return
  if [[ -e "$pending" ]] || [[ -L "$pending" ]] || \
     [[ ! -f "$evidence" ]]; then
    basic_fail \
      "Stopped 0042 evidence publication collided; pending evidence was preserved"
    return
  fi
  verify_stopped_0042_evidence \
    "$run_directory" "$candidate_receipt" "$commit_receipt" \
    "$finalization_receipt" "$data_directory" "$system_identifier" || return
}

verify_stopped_0042_evidence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local data_directory="$5"
  local system_identifier="$6"
  local evidence="$run_directory/rollback-stopped-0042.evidence"
  local candidate_sha commit_sha finalization_sha
  candidate_sha="$(
    private_file_sha256 "$candidate_receipt" "candidate receipt"
  )" || return
  commit_sha="$(private_file_sha256 "$commit_receipt" "commit receipt")" \
    || return
  finalization_sha="$(
    private_file_sha256 "$finalization_receipt" "finalization receipt"
  )" || return
  if [[ ! "$candidate_sha" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$commit_sha" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$finalization_sha" =~ ^[0-9a-f]{64}$ ]]; then
    basic_fail "Stopped 0042 evidence receipt digests are malformed"
    return
  fi
  if [[ -L "$evidence" ]] || [[ ! -f "$evidence" ]] || \
     [[ "$(stat -f '%u' "$evidence")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$evidence")" != "600" ]] || \
     [[ "$(stat -f '%l' "$evidence")" != "1" ]] || \
     [[ "$(wc -l <"$evidence" | tr -d '[:space:]')" != "8" ]] || \
     ! grep -Fqx "status=stopped_retained_0042" "$evidence" || \
     ! grep -Fqx "data_directory=$data_directory" "$evidence" || \
     ! grep -Fqx "system_identifier=$system_identifier" "$evidence" || \
     ! grep -Fqx "cluster_state=shut down" "$evidence" || \
     ! grep -Fqx "revision=$CARESYNC_RETAINED_TARGET_REVISION" "$evidence" || \
     ! grep -Fqx "candidate_sha256=$candidate_sha" "$evidence" || \
     ! grep -Fqx "commit_sha256=$commit_sha" "$evidence" || \
     ! grep -Fqx "finalization_sha256=$finalization_sha" "$evidence"; then
    basic_fail "Stopped 0042 rollback evidence is missing or inconsistent"
    return
  fi
}

verify_rollback_copy_matches_backup() {
  local path="$1"
  local expected_system_identifier="$2"
  basic_require_safe_postgres_tree "$path" "rollback restore copy" || return
  if "$PG_BIN/pg_ctl" -D "$path" status >/dev/null 2>&1 || \
     [[ -f "$path/postmaster.pid" ]]; then
    basic_fail "Rollback restore copy is not offline"
    return
  fi
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-physical-backup-inventory \
      --pgdata "$path" \
      --inventory "$PHYSICAL_BACKUP_INVENTORY" || return
  "$PG_BIN/pg_verifybackup" --exit-on-error "$path" || return
  # Repeat process/control checks after the potentially long byte verification.
  if "$PG_BIN/pg_ctl" -D "$path" status >/dev/null 2>&1 || \
     [[ -f "$path/postmaster.pid" ]] || \
     [[ "$(basic_postgres_control_system_identifier "$path")" != \
          "$expected_system_identifier" ]]; then
    basic_fail "Rollback restore copy changed or started during verification"
    return
  fi
}

preserve_incomplete_rollback_copy() {
  local partial_directory="$1"
  local quarantine_parent="$2"
  local run_key="$3"
  basic_assert_no_symlink_components "$partial_directory" || return
  if [[ -L "$partial_directory" ]] || [[ ! -d "$partial_directory" ]] || \
     [[ "$(stat -f '%u' "$partial_directory")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$partial_directory")" != "700" ]]; then
    basic_fail "Incomplete rollback copy is unsafe and was left untouched"
    return
  fi
  if "$PG_BIN/pg_ctl" -D "$partial_directory" status >/dev/null 2>&1 || \
     [[ -f "$partial_directory/postmaster.pid" ]]; then
    basic_fail \
      "Incomplete rollback copy might be running; it was preserved in place"
    return
  fi
  local root_device entry inventory
  root_device="$(stat -f '%d' "$partial_directory")"
  inventory="$(mktemp "$RUNTIME_DIR/.rollback-tree-inventory.XXXXXX")" || return
  if ! find "$partial_directory" -xdev -print0 >"$inventory"; then
    rm -f "$inventory"
    basic_fail "Incomplete rollback-copy traversal failed"
    return
  fi
  while IFS= read -r -d '' entry; do
    if [[ "$(stat -f '%d' "$entry")" != "$root_device" ]]; then
      rm -f "$inventory"
      basic_fail "Incomplete rollback copy contains a nested mount; preserving in place"
      return
    fi
  done <"$inventory"
  rm -f "$inventory" || return
  basic_require_same_apfs_device "$quarantine_parent" "$partial_directory"
  local failed_attempt
  failed_attempt="$quarantine_parent/rollback-partial-incomplete-$run_key-$(date -u +%Y%m%dT%H%M%SZ)-$$-$RANDOM"
  if [[ -e "$failed_attempt" ]] || [[ -L "$failed_attempt" ]]; then
    basic_fail "Incomplete rollback-copy quarantine destination already exists"
    return
  fi
  atomic_rollback_rename_no_replace \
    "$partial_directory" "$failed_attempt" || return
}

verify_quarantined_0042() {
  local run_directory="$1"
  local candidate_receipt="$2"
  local commit_receipt="$3"
  local finalization_receipt="$4"
  local quarantine_directory="$5"
  local expected_data_directory="$6"
  local expected_system_identifier="$7"
  verify_stopped_0042_evidence \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt" \
    "$expected_data_directory" \
    "$expected_system_identifier" || return
  basic_require_safe_postgres_tree \
    "$quarantine_directory" \
    "quarantined 0042 PostgreSQL" || return
  if "$PG_BIN/pg_ctl" -D "$quarantine_directory" status >/dev/null 2>&1 || \
     [[ -f "$quarantine_directory/postmaster.pid" ]] || \
     [[ "$(basic_postgres_control_system_identifier "$quarantine_directory")" != \
          "$expected_system_identifier" ]] || \
     [[ "$(basic_postgres_control_state "$quarantine_directory")" != "shut down" ]]; then
    basic_fail "Quarantined 0042 PGDATA is not the pinned cleanly stopped tree"
    return
  fi
}

atomic_rollback_rename_no_replace() {
  local source="$1"
  local destination="$2"
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py atomic-rename-no-replace \
      --source "$source" \
      --destination "$destination" || return
  if [[ -e "$source" ]] || [[ -L "$source" ]] || \
     [[ ! -d "$destination" ]] || [[ -L "$destination" ]]; then
    basic_fail "Rollback atomic rename postconditions failed"
    return
  fi
}

preserve_proven_stale_postmaster_pid() {
  local run_directory="$1"
  local pgdata="$2"
  local pid_file="$pgdata/postmaster.pid"
  [[ -f "$pid_file" ]] || return 0
  basic_require_safe_postgres_tree \
    "$pgdata" "stale-PID retained PostgreSQL" || return
  local expected_data_directory expected_system_identifier canonical_pgdata
  if [[ -L "$RETAINED_IDENTITY_FILE" ]] || \
     [[ ! -f "$RETAINED_IDENTITY_FILE" ]] || \
     [[ "$(stat -f '%u' "$RETAINED_IDENTITY_FILE")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$RETAINED_IDENTITY_FILE")" != "600" ]] || \
     [[ "$(stat -f '%l' "$RETAINED_IDENTITY_FILE")" != "1" ]]; then
    basic_fail "Pinned retained identity is unavailable for stale-PID recovery"
    return
  fi
  expected_data_directory="$(
    sed -n 's/^data_directory=//p' "$RETAINED_IDENTITY_FILE"
  )" || return
  expected_system_identifier="$(
    sed -n 's/^system_identifier=//p' "$RETAINED_IDENTITY_FILE"
  )" || return
  canonical_pgdata="$(cd "$pgdata" && pwd -P)" || return
  if [[ "$canonical_pgdata" != "$expected_data_directory" ]] || \
     [[ ! "$expected_system_identifier" =~ ^[0-9]+$ ]] || \
     [[ "$(basic_postgres_control_system_identifier "$pgdata")" != \
          "$expected_system_identifier" ]]; then
    basic_fail "Stale-PID recovery target differs from pinned retained PGDATA"
    return
  fi
  if [[ -L "$pid_file" ]] || \
     [[ "$(stat -f '%u' "$pid_file")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%l' "$pid_file")" != "1" ]] || \
     "$PG_BIN/pg_ctl" -D "$pgdata" status >/dev/null 2>&1; then
    basic_fail "PostgreSQL PID evidence is live or ambiguous; preserving in place"
    return
  fi
  local retained_listeners
  retained_listeners="$(basic_collect_tcp_listener_pids "$PGPORT")" || return
  if [[ -n "$retained_listeners" ]]; then
    basic_fail "PostgreSQL PID evidence endpoint is still active"
    return
  fi
  local postmaster_pid
  postmaster_pid="$(sed -n '1p' "$pid_file")" || return
  if [[ ! "$postmaster_pid" =~ ^[1-9][0-9]*$ ]]; then
    basic_fail "PostgreSQL PID evidence has an invalid PID"
    return
  fi
  local postmaster_presence
  postmaster_presence="$(basic_inspect_pid_presence "$postmaster_pid")" || return
  if [[ "$postmaster_presence" != "absent" ]]; then
    basic_fail "PostgreSQL PID evidence cannot be proven stale"
    return
  fi
  local preserved
  preserved="$run_directory/stale-postmaster.pid.$(date -u +%Y%m%dT%H%M%SZ).$$.$RANDOM"
  durable_publish_private_file "$pid_file" "$preserved" || return
  if [[ -e "$pid_file" ]] || [[ -L "$pid_file" ]] || \
     [[ ! -f "$preserved" ]] || [[ -L "$preserved" ]]; then
    basic_fail "Stale PostgreSQL PID preservation postconditions failed"
    return
  fi
}

discover_artifacts() {
  local run_directory="$1"
  local phase="${2:-prepared}"
  local artifacts_directory="$run_directory/artifacts"
  local backups=()
  shopt -s nullglob
  backups=("$artifacts_directory"/caresync-postgres-*.json.gz)
  shopt -u nullglob
  if (( ${#backups[@]} != 1 )); then
    basic_fail "Release run must contain exactly one logical database backup"
    return
  fi
  BACKUP_PATH="${backups[0]}"
  MANIFEST_PATH="${BACKUP_PATH%.gz}.manifest.json"
  ARTIFACT_STEM="${BACKUP_PATH%.json.gz}"
  FAMILY_BUNDLE_PATH="$ARTIFACT_STEM.family-evidence.zip"
  FAMILY_BUNDLE_MANIFEST_PATH="$ARTIFACT_STEM.family-evidence.manifest.json"
  STAFF_BUNDLE_PATH="$ARTIFACT_STEM.staff-transport-evidence.zip"
  STAFF_BUNDLE_MANIFEST_PATH="$ARTIFACT_STEM.staff-transport-evidence.manifest.json"
  STAFF_VAULT_KEY_PATH="$artifacts_directory/staff-screening-vault.key"
  DATABASE_RESTORE_RECEIPT="$run_directory/clone/database-restore.receipt.json"
  FAMILY_RESTORE_RECEIPT="$run_directory/clone/family-evidence.receipt.json"
  STAFF_RESTORE_RECEIPT="$run_directory/clone/staff-transport.receipt.json"
  CLONE_CERTIFICATE="$run_directory/clone/certificate.json"
  RELEASE_PAYLOAD="$run_directory/release-payload.json"
  CANDIDATE_RECEIPT="$run_directory/candidate-receipt.json"
  COMMIT_RECEIPT="$run_directory/commit-receipt.json"
  COMMIT_ATTEMPT_INTENT="$run_directory/commit-attempting.intent"
  FINALIZATION_RECEIPT="$run_directory/finalization-receipt.json"
  RESUME_AUTHORIZATION="$run_directory/resume-0039.authorization.json"
  ROLLBACK_AUTHORIZATION="$run_directory/rollback-resume-0039.authorization.json"
  PHYSICAL_BACKUP_PATH="$run_directory/physical-postgres"
  PHYSICAL_BACKUP_MANIFEST="$PHYSICAL_BACKUP_PATH/backup_manifest"
  PHYSICAL_BACKUP_INVENTORY="$run_directory/physical-backup.inventory.json"
  PHYSICAL_REHEARSAL_OBSERVATION="$run_directory/physical-rehearsal.observation.json"
  PHYSICAL_REHEARSAL_RECEIPT="$run_directory/physical-rehearsal.receipt.json"
  RELEASE_PROBE_CREDENTIAL="$run_directory/controlled-health-probe.credential"
  RELEASE_SOURCE_ROOT="$run_directory/release-source"
  RELEASE_SOURCE_MANIFEST="$run_directory/release-source.manifest.json"
  RELEASE_EXECUTION_ROOT="$RELEASE_SOURCE_ROOT"
  RETAINED_IDENTITY_ARTIFACT="$RETAINED_IDENTITY_FILE"
  PREPARED_FENCE_CONTEXT="$run_directory/prepared-fence.context"

  if [[ ! -f "$MANIFEST_PATH" ]] || [[ ! -f "$DATABASE_RESTORE_RECEIPT" ]] || \
     [[ ! -f "$CLONE_CERTIFICATE" ]] || \
     [[ ! -f "$PHYSICAL_BACKUP_MANIFEST" ]] || \
     [[ ! -f "$PHYSICAL_BACKUP_INVENTORY" ]] || \
     [[ ! -f "$PHYSICAL_REHEARSAL_OBSERVATION" ]] || \
     [[ ! -f "$PHYSICAL_REHEARSAL_RECEIPT" ]] || \
     [[ ! -f "$RELEASE_PROBE_CREDENTIAL" ]] || \
     [[ ! -d "$RELEASE_SOURCE_ROOT" ]] || \
     [[ ! -f "$RELEASE_SOURCE_MANIFEST" ]] || \
     [[ ! -f "$RETAINED_IDENTITY_ARTIFACT" ]]; then
    basic_fail "Prepared release consistency set is incomplete"
    return
  fi
  if [[ "$phase" != "before-payload" ]] && \
     [[ ! -f "$PREPARED_FENCE_CONTEXT" ]]; then
    basic_fail "Prepared-fence evidence is missing"
    return
  fi
  if [[ "$phase" == "prepared" ]] && [[ ! -f "$RELEASE_PAYLOAD" ]]; then
    basic_fail "Prepared release payload is missing"
    return
  fi
}

build_contract_artifact_args() {
  CONTRACT_ARTIFACT_ARGS=(
    --artifact "backup=$BACKUP_PATH"
    --artifact "backup_manifest=$MANIFEST_PATH"
    --artifact "database_restore_receipt=$DATABASE_RESTORE_RECEIPT"
    --artifact "physical_backup_manifest=$PHYSICAL_BACKUP_MANIFEST"
    --artifact "physical_backup_inventory=$PHYSICAL_BACKUP_INVENTORY"
    --artifact "physical_rehearsal_observation=$PHYSICAL_REHEARSAL_OBSERVATION"
    --artifact "physical_rehearsal_receipt=$PHYSICAL_REHEARSAL_RECEIPT"
    --artifact "prepared_fence_context=$PREPARED_FENCE_CONTEXT"
    --artifact "release_probe_credential=$RELEASE_PROBE_CREDENTIAL"
    --artifact "release_source_manifest=$RELEASE_SOURCE_MANIFEST"
    --artifact "retained_identity=$RETAINED_IDENTITY_ARTIFACT"
  )
  local family_count=0
  local staff_count=0
  [[ ! -f "$FAMILY_BUNDLE_PATH" ]] || (( family_count += 1 ))
  [[ ! -f "$FAMILY_BUNDLE_MANIFEST_PATH" ]] || (( family_count += 1 ))
  [[ ! -f "$FAMILY_RESTORE_RECEIPT" ]] || (( family_count += 1 ))
  if (( family_count != 0 && family_count != 3 )); then
    basic_fail "Family evidence release artifacts are partial"
    return
  fi
  if (( family_count == 3 )); then
    CONTRACT_ARTIFACT_ARGS+=(
      --artifact "family_vault_bundle=$FAMILY_BUNDLE_PATH"
      --artifact "family_vault_manifest=$FAMILY_BUNDLE_MANIFEST_PATH"
      --artifact "family_vault_restore_receipt=$FAMILY_RESTORE_RECEIPT"
    )
  fi

  [[ ! -f "$STAFF_BUNDLE_PATH" ]] || (( staff_count += 1 ))
  [[ ! -f "$STAFF_BUNDLE_MANIFEST_PATH" ]] || (( staff_count += 1 ))
  [[ ! -f "$STAFF_RESTORE_RECEIPT" ]] || (( staff_count += 1 ))
  [[ ! -f "$STAFF_VAULT_KEY_PATH" ]] || (( staff_count += 1 ))
  if (( staff_count != 0 && staff_count != 4 )); then
    basic_fail "Staff/transport evidence release artifacts are partial"
    return
  fi
  if (( staff_count == 4 )); then
    CONTRACT_ARTIFACT_ARGS+=(
      --artifact "staff_transport_vault_bundle=$STAFF_BUNDLE_PATH"
      --artifact "staff_transport_vault_manifest=$STAFF_BUNDLE_MANIFEST_PATH"
      --artifact "staff_transport_vault_restore_receipt=$STAFF_RESTORE_RECEIPT"
      --artifact "staff_transport_vault_key=$STAFF_VAULT_KEY_PATH"
    )
  fi
}

require_bound_prepared_fence_context() {
  local context="$PREPARED_FENCE_CONTEXT"
  if [[ -L "$context" ]] || [[ ! -f "$context" ]] || \
     [[ "$(stat -f '%u' "$context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$context")" != "1" ]] || \
     [[ "$(wc -l <"$context" | tr -d '[:space:]')" != "7" ]] || \
     ! grep -Fqx "status=prepared" "$context" || \
     ! grep -Fqx "run_directory=$(dirname "$CANDIDATE_RECEIPT")" "$context" || \
     ! grep -Fqx "candidate_receipt=$CANDIDATE_RECEIPT" "$context" || \
     ! grep -Eq '^app_prior_login=(login|nologin)$' "$context" || \
     ! grep -Eq '^ingest_prior_login=(login|nologin)$' "$context" || \
     ! grep -Fqx "source_revision=$CARESYNC_RETAINED_SOURCE_REVISION" "$context" || \
     ! grep -Fqx "target_revision=$CARESYNC_RETAINED_TARGET_REVISION" "$context"; then
    basic_fail "Prepared-fence evidence is incomplete or does not match this release"
    return
  fi
  local durable_context=""
  if [[ -f "$(dirname "$CANDIDATE_RECEIPT")/fence-retired/context" ]]; then
    durable_context="$(dirname "$CANDIDATE_RECEIPT")/fence-retired/context"
  elif [[ -f "$RELEASE_FENCE_DIRECTORY/context" ]] && \
       grep -Fqx "status=prepared" "$RELEASE_FENCE_DIRECTORY/context"; then
    durable_context="$RELEASE_FENCE_DIRECTORY/context"
  elif [[ -f "$RELEASE_FENCE_DIRECTORY/context" ]] && \
       grep -Eq \
         '^status=rollback_(preparing|retained_stopped|copy_verified|quarantined|restored|starting)$' \
         "$RELEASE_FENCE_DIRECTORY/context" && \
       grep -Fqx "run_directory=$(dirname "$CANDIDATE_RECEIPT")" \
         "$RELEASE_FENCE_DIRECTORY/context" && \
       grep -Fqx "candidate_receipt=$CANDIDATE_RECEIPT" \
         "$RELEASE_FENCE_DIRECTORY/context" && \
       grep -Fqx "commit_receipt=$COMMIT_ATTEMPT_INTENT" \
         "$RELEASE_FENCE_DIRECTORY/context" && \
       grep -Fqx "finalization_receipt=none" \
         "$RELEASE_FENCE_DIRECTORY/context"; then
    # Interrupted live migration recovery monotonically replaces the active
    # prepared context with its physical-rollback journal. The separately
    # sealed prepared-fence evidence remains the immutable pre-transition
    # binding and is re-opened above.
    durable_context="$context"
  elif [[ -f "$(dirname "$CANDIDATE_RECEIPT")/rollback-fence-retired/context" ]] && \
       grep -Fqx "run_directory=$(dirname "$CANDIDATE_RECEIPT")" \
         "$(dirname "$CANDIDATE_RECEIPT")/rollback-fence-retired/context" && \
       grep -Fqx "candidate_receipt=$CANDIDATE_RECEIPT" \
         "$(dirname "$CANDIDATE_RECEIPT")/rollback-fence-retired/context" && \
       grep -Fqx "commit_receipt=$COMMIT_ATTEMPT_INTENT" \
         "$(dirname "$CANDIDATE_RECEIPT")/rollback-fence-retired/context" && \
       grep -Fqx "finalization_receipt=none" \
         "$(dirname "$CANDIDATE_RECEIPT")/rollback-fence-retired/context"; then
    durable_context="$context"
  fi
  if [[ -z "$durable_context" ]] || [[ -L "$durable_context" ]] || \
     [[ "$(stat -f '%u' "$durable_context")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$durable_context")" != "600" ]] || \
     [[ "$(stat -f '%l' "$durable_context")" != "1" ]] || \
     { [[ "$durable_context" != "$context" ]] && \
       ! cmp -s "$context" "$durable_context"; }; then
    basic_fail \
      "Active or retired prepared fence differs from its bound evidence copy"
    return
  fi
}

require_interrupted_commit_recovery_evidence() {
  local run_directory="$1"
  local candidate_receipt="$2"
  verify_static_artifacts || return
  require_commit_attempt_intent \
    "$COMMIT_ATTEMPT_INTENT" "$run_directory" "$candidate_receipt" || return
  durability_barrier_private_file "$COMMIT_ATTEMPT_INTENT" || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-prepare-receipt \
      --receipt "$candidate_receipt" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" || return
}

verify_interrupted_commit_quarantine() {
  local quarantine_directory="$1"
  local expected_system_identifier="$2"
  basic_require_safe_postgres_tree \
    "$quarantine_directory" \
    "quarantined interrupted-commit PostgreSQL" || return
  if "$PG_BIN/pg_ctl" -D "$quarantine_directory" status >/dev/null 2>&1 || \
     [[ -f "$quarantine_directory/postmaster.pid" ]] || \
     [[ "$(basic_postgres_control_system_identifier \
       "$quarantine_directory")" != "$expected_system_identifier" ]]; then
    basic_fail \
      "Interrupted-commit quarantine is not a stopped pinned retained tree"
    return
  fi
}

verify_stopped_pinned_postgres_tree() {
  local path="$1"
  local expected_system_identifier="$2"
  local require_clean_shutdown="$3"
  basic_require_safe_postgres_tree "$path" "stopped retained PostgreSQL" || return
  if "$PG_BIN/pg_ctl" -D "$path" status >/dev/null 2>&1 || \
     [[ -f "$path/postmaster.pid" ]] || \
     [[ "$(basic_postgres_control_system_identifier "$path")" != \
       "$expected_system_identifier" ]]; then
    basic_fail "Retained PostgreSQL tree is not stopped and identity-pinned"
    return
  fi
  if [[ "$require_clean_shutdown" == "true" ]] && \
     [[ "$(basic_postgres_control_state "$path")" != "shut down" ]]; then
    basic_fail "Finalized retained PostgreSQL tree is not cleanly shut down"
    return
  fi
}

require_interrupted_commit_live_revision() {
  local revision
  revision="$(basic_current_revision)" || return
  case "$revision" in
    "$CARESYNC_RETAINED_SOURCE_REVISION"|\
0041_live_room_presence|\
"$CARESYNC_RETAINED_TARGET_REVISION")
      ;;
    *)
      basic_fail \
        "Interrupted commit recovery found a revision outside the 0039-to-0042 path"
      return
      ;;
  esac
}

stop_unready_retained_postgres_for_interrupted_commit() {
  local run_directory="$1"
  if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_fail "Unready PostgreSQL recovery was invoked for a ready server"
    return
  fi
  local pid_file="$PGDATA/postmaster.pid"
  if [[ ! -f "$pid_file" ]]; then
    if "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
      basic_fail "PostgreSQL reports running without a retained PID record"
      return
    fi
    return 0
  fi
  if [[ -L "$pid_file" ]] || \
     [[ "$(stat -f '%u' "$pid_file")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%l' "$pid_file")" != "1" ]]; then
    basic_fail "Unready PostgreSQL PID evidence is unsafe"
    return
  fi
  local postmaster_pid presence command canonical_pgdata expected_identifier
  postmaster_pid="$(sed -n '1p' "$pid_file")" || return
  if [[ ! "$postmaster_pid" =~ ^[1-9][0-9]*$ ]]; then
    basic_fail "Unready PostgreSQL PID evidence is malformed"
    return
  fi
  canonical_pgdata="$(cd "$PGDATA" && pwd -P)" || return
  expected_identifier="$(
    private_context_value "$RETAINED_IDENTITY_FILE" system_identifier
  )" || return
  if [[ "$(basic_postgres_control_system_identifier "$PGDATA")" != \
        "$expected_identifier" ]]; then
    basic_fail "Unready PostgreSQL differs from the pinned retained cluster"
    return
  fi
  presence="$(basic_inspect_pid_presence "$postmaster_pid")" || return
  if [[ "$presence" == "absent" ]]; then
    preserve_proven_stale_postmaster_pid "$run_directory" "$PGDATA" || return
    return 0
  fi
  command="$(ps -p "$postmaster_pid" -o command= 2>/dev/null)" || return
  if [[ "$command" != *"postgres"* ]] || \
     [[ "$command" != *"$canonical_pgdata"* ]] || \
     ! "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
    basic_fail \
      "Unready retained PID does not prove the expected PostgreSQL process"
    return
  fi
  "$PG_BIN/pg_ctl" -D "$PGDATA" stop -m immediate || return
  basic_wait_for_process_exit "$postmaster_pid" || {
    basic_fail "Unready retained PostgreSQL did not stop"
    return
  }
  if [[ -f "$pid_file" ]]; then
    preserve_proven_stale_postmaster_pid "$run_directory" "$PGDATA" || return
  fi
  if "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1 || \
     "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_fail "Unready retained PostgreSQL still appears active"
    return
  fi
}

bootstrap_verify_pre_candidate_source() {
  local run_directory="$1"
  local expected_manifest_sha="$2"
  local source_root="$run_directory/release-source"
  local manifest="$run_directory/release-source.manifest.json"
  local verifier="$source_root/backend/scripts/release_source_bundle.py"
  local verifier_binding verifier_sha verifier_bytes
  verifier_binding="$(
    "$VENV_PATH/bin/python" -c '
import json
import pathlib
import sys

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

manifest = json.loads(
    pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"),
    object_pairs_hook=unique,
)
verifier = manifest["files"]["backend/scripts/release_source_bundle.py"]
if set(verifier) != {"bytes", "sha256"}:
    raise ValueError("invalid verifier binding")
print("{}|{}".format(verifier["sha256"], verifier["bytes"]))
' "$manifest"
  )" || {
    basic_fail "Pre-candidate source bootstrap binding is unreadable"
    return
  }
  IFS='|' read -r verifier_sha verifier_bytes <<<"$verifier_binding"
  local actual_manifest_sha actual_verifier_sha
  if [[ ! "$expected_manifest_sha" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$verifier_sha" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$verifier_bytes" =~ ^[0-9]+$ ]] || \
     [[ "$(stat -f '%z' "$verifier")" != "$verifier_bytes" ]]; then
    basic_fail "Pre-candidate source bootstrap binding is invalid"
    return
  fi
  actual_manifest_sha="$(
    /usr/bin/shasum -a 256 "$manifest" | /usr/bin/awk '{print $1}'
  )" || return
  actual_verifier_sha="$(
    /usr/bin/shasum -a 256 "$verifier" | /usr/bin/awk '{print $1}'
  )" || return
  if [[ "$actual_manifest_sha" != "$expected_manifest_sha" ]] || \
     [[ "$actual_verifier_sha" != "$verifier_sha" ]]; then
    basic_fail \
      "Pre-candidate source failed independent fence-bound bootstrap verification"
    return
  fi
  PYTHONDONTWRITEBYTECODE=1 CARESYNC_PG_BIN="$PG_BIN" \
    CARESYNC_INSTALLED_NODE_MODULES="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}/frontend-redesign/node_modules" \
    "$VENV_PATH/bin/python" "$verifier" verify \
      --destination "$source_root" \
      --manifest "$manifest" || return
}

bootstrap_verify_captured_release_source() {
  local run_directory="$1"
  local expected_manifest_sha="${2:-}"
  local source_root="$run_directory/release-source"
  local manifest="$run_directory/release-source.manifest.json"
  local candidate="$run_directory/candidate-receipt.json"
  local verifier="$source_root/backend/scripts/release_source_bundle.py"
  local bindings
  bindings="$(
    "$VENV_PATH/bin/python" -c '
import hashlib
import json
import pathlib
import sys

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

candidate_path, manifest_path = map(pathlib.Path, sys.argv[1:3])
candidate = json.loads(
    candidate_path.read_text(encoding="utf-8"),
    object_pairs_hook=unique,
)
binding = candidate["artifacts"]["release_source_manifest"]
if set(binding) != {"name", "sha256", "sizeBytes"}:
    raise ValueError("invalid release source artifact binding")
manifest = json.loads(
    manifest_path.read_text(encoding="utf-8"),
    object_pairs_hook=unique,
)
verifier = manifest["files"]["backend/scripts/release_source_bundle.py"]
if set(verifier) != {"bytes", "sha256"}:
    raise ValueError("invalid verifier binding")
print(
    "|".join(
        (
            str(binding["name"]),
            str(binding["sha256"]),
            str(binding["sizeBytes"]),
            str(verifier["sha256"]),
            str(verifier["bytes"]),
        )
    )
)
' "$candidate" "$manifest"
  )" || {
    basic_fail "Captured release source bootstrap bindings are unreadable"
    return
  }
  local manifest_name manifest_sha manifest_bytes verifier_sha verifier_bytes
  IFS='|' read -r \
    manifest_name manifest_sha manifest_bytes verifier_sha verifier_bytes \
    <<<"$bindings"
  local actual_manifest_sha actual_verifier_sha
  if [[ "$manifest_name" != "$(basename "$manifest")" ]] || \
     [[ ! "$manifest_sha" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$manifest_bytes" =~ ^[0-9]+$ ]] || \
     [[ ! "$verifier_sha" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$verifier_bytes" =~ ^[0-9]+$ ]] || \
     [[ "$(stat -f '%z' "$manifest")" != "$manifest_bytes" ]] || \
     [[ "$(stat -f '%z' "$verifier")" != "$verifier_bytes" ]]; then
    basic_fail "Captured release source bootstrap binding is invalid"
    return
  fi
  actual_manifest_sha="$(
    /usr/bin/shasum -a 256 "$manifest" | /usr/bin/awk '{print $1}'
  )" || return
  actual_verifier_sha="$(
    /usr/bin/shasum -a 256 "$verifier" | /usr/bin/awk '{print $1}'
  )" || return
  if [[ "$actual_manifest_sha" != "$manifest_sha" ]] || \
     [[ -n "$expected_manifest_sha" && \
        "$actual_manifest_sha" != "$expected_manifest_sha" ]] || \
     [[ "$actual_verifier_sha" != "$verifier_sha" ]]; then
    basic_fail \
      "Captured release source failed independent candidate-bound bootstrap verification"
    return
  fi
  PYTHONDONTWRITEBYTECODE=1 CARESYNC_PG_BIN="$PG_BIN" \
    CARESYNC_INSTALLED_NODE_MODULES="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}/frontend-redesign/node_modules" \
    "$VENV_PATH/bin/python" "$verifier" verify \
      --destination "$source_root" \
      --manifest "$manifest" || return
}

verify_static_artifacts() {
  bootstrap_verify_captured_release_source \
    "$(dirname "$CANDIDATE_RECEIPT")" || return
  require_bound_prepared_fence_context || return
  basic_require_safe_postgres_tree \
    "$PHYSICAL_BACKUP_PATH" \
    "physical backup evidence" || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-physical-backup-inventory \
      --pgdata "$PHYSICAL_BACKUP_PATH" \
      --inventory "$PHYSICAL_BACKUP_INVENTORY" || return
  "$PG_BIN/pg_verifybackup" \
    --exit-on-error "$PHYSICAL_BACKUP_PATH" || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-physical-rehearsal \
      --observation "$PHYSICAL_REHEARSAL_OBSERVATION" \
      --physical-backup-manifest "$PHYSICAL_BACKUP_MANIFEST" \
      --physical-backup-inventory "$PHYSICAL_BACKUP_INVENTORY" \
      --retained-identity "$RETAINED_IDENTITY_ARTIFACT" \
      --receipt "$PHYSICAL_REHEARSAL_RECEIPT" || return
  backend_env 127.0.0.1 "$PGPORT" "$BACKUP_USER" "$BACKUP_PASSWORD" \
    python scripts/backup_database.py \
      --verify "$BACKUP_PATH" "$MANIFEST_PATH" || return
  if [[ -f "$FAMILY_BUNDLE_PATH" ]]; then
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/family_evidence_vault_bundle.py verify \
        --backup "$BACKUP_PATH" \
        --manifest "$MANIFEST_PATH" \
        --bundle "$FAMILY_BUNDLE_PATH" \
        --bundle-manifest "$FAMILY_BUNDLE_MANIFEST_PATH" || return
  fi
  if [[ -f "$STAFF_BUNDLE_PATH" ]]; then
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/staff_transport_vault_bundle.py verify \
        --backup "$BACKUP_PATH" \
        --manifest "$MANIFEST_PATH" \
        --bundle "$STAFF_BUNDLE_PATH" \
        --bundle-manifest "$STAFF_BUNDLE_MANIFEST_PATH" || return
  fi
  return 0
}

reexec_release_from_captured_source_if_needed() {
  local run_directory="$1"
  shift
  bootstrap_verify_captured_release_source "$run_directory" || return
  local source_sha
  source_sha="$(
    private_file_sha256 "$RELEASE_SOURCE_MANIFEST" \
      "captured release source manifest"
  )" || return
  if [[ "${CARESYNC_CAPTURED_RELEASE_SOURCE_SHA:-}" == "$source_sha" ]]; then
    if [[ "$ROOT" != "$RELEASE_SOURCE_ROOT" ]]; then
      basic_fail "Captured release-source marker does not match the executing root"
      return
    fi
    return 0
  fi
  if [[ -n "${CARESYNC_CAPTURED_RELEASE_SOURCE_SHA:-}" ]]; then
    basic_fail "Release process cannot switch between captured source bundles"
    return
  fi
  export CARESYNC_CAPTURED_RELEASE_SOURCE_SHA="$source_sha"
  export CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}"
  exec /bin/bash "$RELEASE_SOURCE_ROOT/scripts/basic-release.sh" "$@"
}

reexec_interrupted_prepare_source_if_needed() {
  if [[ ! -f "$RELEASE_FENCE_DIRECTORY/context" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY/context" ]] || \
     ! grep -Fqx "status=preparing" \
       "$RELEASE_FENCE_DIRECTORY/context"; then
    return 0
  fi
  require_exact_preparing_fence || return
  bootstrap_verify_pre_candidate_source \
    "$PREPARING_RUN_DIRECTORY" "$PREPARING_SOURCE_MANIFEST_SHA" || return
  if [[ "${CARESYNC_CAPTURED_RELEASE_SOURCE_SHA:-}" == \
        "$PREPARING_SOURCE_MANIFEST_SHA" ]]; then
    if [[ "$ROOT" != "$PREPARING_SOURCE_ROOT" ]]; then
      basic_fail \
        "Interrupted prepare source marker does not match the executing root"
      return
    fi
    return 0
  fi
  if [[ -n "${CARESYNC_CAPTURED_RELEASE_SOURCE_SHA:-}" ]]; then
    basic_fail "Prepare recovery cannot switch captured source bundles"
    return
  fi
  export CARESYNC_CAPTURED_RELEASE_SOURCE_SHA="$PREPARING_SOURCE_MANIFEST_SHA"
  export CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}"
  exec /bin/bash "$PREPARING_SOURCE_ROOT/scripts/basic-release.sh" "$@"
}

recover_interrupted_prepare_from_bound_source() {
  # A fresh prepare captures its source before creating the fence, but the
  # original shell still has the installed ROOT. Recovery itself deliberately
  # refuses that root. Re-open and verify the exact fence-bound source, then
  # run the recovery entry point from that source without replacing this shell:
  # the surrounding EXIT trap must retain and return the original failure.
  require_exact_preparing_fence || return
  local run_directory="$PREPARING_RUN_DIRECTORY"
  bootstrap_verify_pre_candidate_source \
    "$run_directory" "$PREPARING_SOURCE_MANIFEST_SHA" || return
  if [[ "$ROOT" == "$PREPARING_SOURCE_ROOT" ]]; then
    reconcile_interrupted_prepare
    return
  fi
  # A shell that just recovered an older run may carry that run's marker while
  # legitimately starting a new prepare. The newly verified preparing fence is
  # the authority here; pass its exact hash to the bound child.
  CARESYNC_CAPTURED_RELEASE_SOURCE_SHA="$PREPARING_SOURCE_MANIFEST_SHA" \
    CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}" \
    /bin/bash "$PREPARING_SOURCE_ROOT/scripts/basic-release.sh" \
      _recover-interrupted-prepare
}

prepare_release() {
  local original_arguments=("$@")
  local clone_port_override=""
  while (( $# > 0 )); do
    case "$1" in
      --clone-port)
        [[ $# -ge 2 ]] || { usage; return 2; }
        clone_port_override="$2"
        shift 2
        ;;
      *)
        usage
        return 2
        ;;
    esac
  done

  # A read-only preflight prevents an invocation against the wrong retained
  # revision from leaving an orphan fence. The revision is checked again after
  # the fence and writer quiescence before any backup is allowed.
  basic_require_local_toolchain
  basic_require_runtime_layout
  basic_normalize_known_runtime_files
  ensure_release_state_directory || return
  if (( ${#original_arguments[@]} == 0 )); then
    # Bash 3.2 with nounset treats an empty "${array[@]}" expansion as an
    # unbound variable. Keep the zero-option path explicit so the supported
    # `prepare` invocation reaches the recovery gate on macOS.
    reexec_interrupted_prepare_source_if_needed prepare || return
  else
    reexec_interrupted_prepare_source_if_needed \
      prepare "${original_arguments[@]}" || return
  fi
  # SIGKILL and power loss bypass the local EXIT trap. A new prepare may
  # reconcile only the exact private source-bound `preparing` journal: any proven
  # disposable clone is stopped (or its stale PID is preserved), retained
  # writer states are restored, and the whole fence is retired into its
  # original run before a fresh release ID is allocated.
  reconcile_interrupted_prepare
  require_no_global_recovery_journals_for_new_operation || return
  basic_start_postgres
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"
  basic_cleanup_appledouble_sidecars
  local private_vault
  for private_vault in \
    "$FAMILY_EVIDENCE_VAULT_PATH" \
    "$STAFF_SCREENING_VAULT_PATH"; do
    if [[ -L "$private_vault" ]] || \
       [[ -e "$private_vault" && ! -d "$private_vault" ]] || \
       { [[ -d "$private_vault" ]] && \
         { [[ "$(stat -f '%u' "$private_vault")" != "$(id -u)" ]] || \
           [[ "$(stat -f '%Lp' "$private_vault")" != "700" ]]; }; }; then
      basic_fail "Release preflight found an unsafe evidence vault"
      return
    fi
    if [[ ! -e "$private_vault" ]]; then
      durable_ensure_private_directory "$private_vault" || return
    fi
  done
  (
    cd "$ROOT/backend"
    CARESYNC_VENV_PATH="$VENV_PATH" \
      /bin/bash ./scripts/uv.sh run python scripts/basic_runtime_secrets.py \
        --runtime-directory "$RUNTIME_DIR"
  )
  local staff_vault_key="$RUNTIME_SECRET_DIRECTORY/staff-screening-vault.key"
  if [[ -L "$staff_vault_key" ]] || [[ ! -f "$staff_vault_key" ]] || \
     [[ "$(stat -f '%u' "$staff_vault_key")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$staff_vault_key")" != "600" ]] || \
     [[ "$(stat -f '%l' "$staff_vault_key")" != "1" ]]; then
    basic_fail "Release preflight cannot bind the staff evidence-vault key"
    return
  fi
  local app_prior_state ingest_prior_state
  app_prior_state="$(basic_role_login_state caresync_basic_app)"
  ingest_prior_state="$(basic_role_login_state caresync_transport_evidence_ingest)"
  if [[ "$app_prior_state" != "login" ]] || \
     [[ "$ingest_prior_state" != "login" ]]; then
    basic_fail \
      "Both certified CareSync runtime roles must be LOGIN before release preparation"
    return
  fi

  local release_id run_directory artifacts_directory clone_directory
  release_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  run_directory="$RELEASE_STATE_DIRECTORY/$release_id"
  artifacts_directory="$run_directory/artifacts"
  clone_directory="$run_directory/clone"
  ensure_release_state_directory || return
  durable_ensure_private_directory "$run_directory" || return
  durable_ensure_private_directory "$artifacts_directory" || return
  durable_ensure_private_directory "$clone_directory" || return
  create_release_probe_credential "$run_directory" || return
  RELEASE_PROBE_CREDENTIAL="$run_directory/controlled-health-probe.credential"
  RELEASE_SOURCE_ROOT="$run_directory/release-source"
  RELEASE_SOURCE_MANIFEST="$run_directory/release-source.manifest.json"
  PYTHONDONTWRITEBYTECODE=1 CARESYNC_PG_BIN="$PG_BIN" \
    CARESYNC_INSTALLED_NODE_MODULES="$ROOT/frontend-redesign/node_modules" \
    "$VENV_PATH/bin/python" \
      "$ROOT/backend/scripts/release_source_bundle.py" create \
      --source-root "$ROOT" \
      --destination "$RELEASE_SOURCE_ROOT" \
      --manifest "$RELEASE_SOURCE_MANIFEST" || return
  PYTHONDONTWRITEBYTECODE=1 CARESYNC_PG_BIN="$PG_BIN" \
    CARESYNC_INSTALLED_NODE_MODULES="$ROOT/frontend-redesign/node_modules" \
    "$VENV_PATH/bin/python" \
      "$RELEASE_SOURCE_ROOT/backend/scripts/release_source_bundle.py" verify \
      --destination "$RELEASE_SOURCE_ROOT" \
      --manifest "$RELEASE_SOURCE_MANIFEST" || return
  RELEASE_EXECUTION_ROOT="$RELEASE_SOURCE_ROOT"

  local clone_port="" clone_pgdata="" clone_started=false
  local rehearsal_port="" rehearsal_pgdata="" rehearsal_started=false
  local rehearsal_socket_directory=""

  PREPARE_CLEANUP_RUN_DIRECTORY="$run_directory"
  PREPARE_CLEANUP_RETAINED_FENCED=false
  PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
  PREPARE_CLEANUP_CANDIDATE_SEALED=false
  PREPARE_CLEANUP_FENCE_CREATED=false

  prepare_cleanup() {
    local result="${1:?prepare cleanup status is required}"
    if (( result != 0 )); then
      printf '%s\n' "Release preparation failed; no retained migration ran." >&2
      # Never signal a PID merely because this shell remembers starting it.
      # Re-open both expected disposable trees and prove executable, PGDATA,
      # endpoint, system identity and online SQL identity before any stop.
      if ! reconcile_prepare_disposables_for_run \
        "$PREPARE_CLEANUP_RUN_DIRECTORY"; then
        if [[ "$PREPARE_CLEANUP_RETAINED_FENCED" == "true" ]]; then
          fence_runtime_roles || true
        fi
        printf '%s\n' \
          "Disposable PostgreSQL reconciliation failed; the release fence and NOLOGIN roles were preserved." >&2
        return "$result"
      fi
      if [[ -n "$PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY" ]] && \
         [[ -d "$PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY" ]] && \
         [[ ! -L "$PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY" ]] && \
         [[ "$(directory_entry_state \
           "$PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY")" == \
           "empty" ]]; then
        rmdir "$PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY" || {
          if [[ "$PREPARE_CLEANUP_RETAINED_FENCED" == "true" ]]; then
            fence_runtime_roles || true
          fi
          printf '%s\n' \
            "Physical-rehearsal socket cleanup failed; the release fence was preserved." >&2
          return "$result"
        }
      fi
      if [[ "$PREPARE_CLEANUP_CANDIDATE_SEALED" == "false" ]] && \
         [[ "$PREPARE_CLEANUP_FENCE_CREATED" == "true" ]] && \
         [[ -d "$RELEASE_FENCE_DIRECTORY" ]]; then
        if ! recover_interrupted_prepare_from_bound_source; then
          fence_runtime_roles || true
          printf '%s\n' \
            "Writer restoration failed; the preparing fence was retained." >&2
        fi
      elif [[ "$PREPARE_CLEANUP_CANDIDATE_SEALED" == "true" ]]; then
        printf '%s\n' \
          "The retained database remains prepared and every writer role remains NOLOGIN." >&2
      else
        printf '%s\n' \
          "The retained application roles were not changed." >&2
      fi
    fi
    return "$result"
  }
  trap 'prepare_cleanup "$?"' EXIT

  # Prove the rollback geometry while the live runtime is still unfenced and
  # before any candidate can exist. The physical destination is intentionally
  # absent; its private run directory is the attested filesystem anchor.
  local quarantine_parent="$RUNTIME_DIR/quarantine"
  durable_ensure_private_directory "$quarantine_parent" || return
  basic_require_release_apfs_topology \
    "$run_directory/physical-postgres" "$quarantine_parent" || return

  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  basic_quiesce_application || return
  basic_assert_no_database_clients || return
  basic_require_app_login_state "login" || return
  create_fence \
    "$run_directory" "$app_prior_state" "$ingest_prior_state" || return
  PREPARE_CLEANUP_FENCE_CREATED=true
  # Mark the cleanup obligation before the first ALTER ROLE. If PostgreSQL
  # applies the ALTER but the follow-up verification loses its connection, the
  # EXIT trap must still attempt exact role restoration and retain the fence on
  # failure.
  PREPARE_CLEANUP_RETAINED_FENCED=true
  basic_set_role_login_state caresync_basic_app nologin || return
  basic_set_role_login_state \
    caresync_transport_evidence_ingest nologin || return
  configure_release_probe \
    "$run_directory/controlled-health-probe.credential" || return
  require_release_probe_contract nologin || return
  basic_require_runtime_roles_fenced || return
  basic_assert_no_database_clients || return
  basic_assert_no_cluster_clients || return
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return

  if [[ -n "$clone_port_override" ]]; then
    require_high_clone_port "$clone_port_override" || return
    clone_port="$clone_port_override"
  else
    clone_port="$(select_clone_port)" || return
  fi
  rehearsal_port="$(select_rehearsal_port "$clone_port")" || return
  clone_pgdata="$clone_directory/postgres-data"
  if [[ "$(basic_psql_scalar "SELECT pg_is_in_recovery()")" != "f" ]] || \
     [[ -e "$PGDATA/standby.signal" ]] || [[ -L "$PGDATA/standby.signal" ]] || \
     [[ -e "$PGDATA/recovery.signal" ]] || [[ -L "$PGDATA/recovery.signal" ]]; then
    basic_fail "Release preparation requires a primary retained PostgreSQL tree"
    return
  fi
  if [[ "$(basic_psql_scalar \
    "SELECT count(*) FROM pg_tablespace WHERE spcname NOT IN ('pg_default','pg_global') AND pg_tablespace_location(oid) <> ''")" != "0" ]]; then
    basic_fail \
      "Physical release backup refuses external PostgreSQL tablespaces"
    return
  fi

  if [[ -e "$run_directory/physical-postgres" ]] || \
     [[ -L "$run_directory/physical-postgres" ]]; then
    basic_fail "Physical backup destination already exists"
    return
  fi
  PGPASSWORD="$BACKUP_PASSWORD" "$PG_BIN/pg_basebackup" \
    --host=127.0.0.1 \
    --port="$PGPORT" \
    --username="$BACKUP_USER" \
    --no-password \
    --pgdata="$run_directory/physical-postgres" \
    --format=plain \
    --wal-method=stream \
    --checkpoint=fast \
    --manifest-checksums=SHA256
  basic_strip_unbound_postgres_metadata "$run_directory/physical-postgres"
  chmod 700 "$run_directory/physical-postgres"
  chmod 600 "$run_directory/physical-postgres/backup_manifest"
  basic_require_safe_postgres_tree \
    "$run_directory/physical-postgres" \
    "physical backup evidence"
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py inventory-physical-backup \
      --pgdata "$run_directory/physical-postgres" \
      --output "$run_directory/physical-backup.inventory.json"
  "$PG_BIN/pg_verifybackup" --exit-on-error "$run_directory/physical-postgres"
  basic_assert_no_database_clients
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"

  # A checksum-valid base backup is not yet a recovery proof. Copy it without
  # mutating the evidence, boot that copy on an independent high port, and
  # seal its exact-0039 snapshot/system identity before any candidate exists.
  local rehearsal_directory="$run_directory/physical-rehearsal"
  local rehearsal_config_file="$rehearsal_directory/postgresql.conf"
  local rehearsal_hba_file="$rehearsal_directory/pg_hba.conf"
  local rehearsal_ident_file="$rehearsal_directory/pg_ident.conf"
  durable_ensure_private_directory "$rehearsal_directory" || return
  rehearsal_socket_directory="/private/tmp/cs-$release_id-$rehearsal_port"
  if [[ -e "$rehearsal_socket_directory" ]] || \
     [[ -L "$rehearsal_socket_directory" ]] || \
     [[ "$rehearsal_directory" == *"'"* ]] || \
     [[ "$rehearsal_socket_directory" == *"'"* ]] || \
     [[ ! "$MIGRATION_USER" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]]; then
    basic_fail "Physical rehearsal configuration paths or role are unsafe"
    return
  fi
  mkdir -m 700 "$rehearsal_socket_directory"
  PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY="$rehearsal_socket_directory"
  printf '%s\n' \
    "# Isolated CareSync physical-rehearsal configuration." \
    >"$rehearsal_config_file"
  printf '%s\n' \
    "host \"$DATABASE_NAME\" \"$MIGRATION_USER\" 127.0.0.1/32 trust" \
    "host all all 127.0.0.1/32 reject" \
    "host all all ::/0 reject" \
    "local all all reject" \
    >"$rehearsal_hba_file"
  printf '%s\n' "# No user maps." >"$rehearsal_ident_file"
  chmod 600 \
    "$rehearsal_config_file" \
    "$rehearsal_hba_file" \
    "$rehearsal_ident_file"
  rehearsal_pgdata="$rehearsal_directory/postgres-data"
  basic_materialize_physical_copy \
    "$run_directory/physical-postgres" \
    "$rehearsal_pgdata" \
    "physical backup rehearsal"
  if [[ -f "$rehearsal_pgdata/postmaster.pid" ]]; then
    basic_fail "Physical rehearsal copy unexpectedly contains postmaster.pid"
    return
  fi
  basic_run_guarded_without_state_lock_in_child \
    "$PG_BIN/pg_ctl" -D "$rehearsal_pgdata" \
    -l "$rehearsal_directory/postgres.log" \
    -o "-p $rehearsal_port -h 127.0.0.1 -k '$rehearsal_socket_directory' \
-c config_file='$rehearsal_config_file' \
-c data_directory='$rehearsal_pgdata' \
-c hba_file='$rehearsal_hba_file' \
-c ident_file='$rehearsal_ident_file' \
-c external_pid_file='' -c ssl=off -c logging_collector=off \
-c archive_mode=off -c shared_preload_libraries='' \
-c session_preload_libraries='' -c local_preload_libraries='' \
-c primary_conninfo='' -c restore_command='' -c archive_command='' \
-c archive_cleanup_command='' -c recovery_end_command=''" start || return
  rehearsal_started=true
  local rehearsal_attempt
  for rehearsal_attempt in {1..80}; do
    "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$rehearsal_port" -q && break
    sleep 0.125
  done
  "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$rehearsal_port" -q
  local online_rehearsal_data_directory
  online_rehearsal_data_directory="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$rehearsal_port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "SHOW data_directory")"
  if [[ "$(cd "$online_rehearsal_data_directory" && pwd -P)" != \
        "$(cd "$rehearsal_pgdata" && pwd -P)" ]]; then
    basic_fail "Physical rehearsal server reports the wrong data directory"
    return
  fi
  local rehearsal_endpoint rehearsal_writer_states rehearsal_other_clients
  rehearsal_endpoint="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$rehearsal_port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "SELECT host(inet_server_addr()) || ':' || inet_server_port()::text")"
  if [[ "$rehearsal_endpoint" != "127.0.0.1:$rehearsal_port" ]]; then
    basic_fail "Physical rehearsal is not bound to its exact loopback endpoint"
    return
  fi
  rehearsal_writer_states="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$rehearsal_port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "SELECT string_agg(rolname || ':' || CASE WHEN rolcanlogin THEN 'login' ELSE 'nologin' END, ',' ORDER BY rolname) FROM pg_roles WHERE rolname IN ('caresync_basic_app','caresync_transport_evidence_ingest')")"
  if [[ "$rehearsal_writer_states" != \
        "caresync_basic_app:nologin,caresync_transport_evidence_ingest:nologin" ]]; then
    basic_fail "Physical rehearsal did not preserve both writer-role fences"
    return
  fi
  rehearsal_other_clients="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$rehearsal_port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid()")"
  if [[ "$rehearsal_other_clients" != "0" ]]; then
    basic_fail "Physical rehearsal has another database client"
    return
  fi
  backend_env 127.0.0.1 "$rehearsal_port" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py observe-physical-rehearsal \
      --physical-backup-manifest \
        "$run_directory/physical-postgres/backup_manifest" \
      --physical-backup-inventory \
        "$run_directory/physical-backup.inventory.json" \
      --retained-identity "$RETAINED_IDENTITY_FILE" \
      --observation "$run_directory/physical-rehearsal.observation.json"
  reconcile_prepare_disposable_postgres \
    "$run_directory" "$rehearsal_pgdata" physical-rehearsal
  rehearsal_started=false
  if "$PG_BIN/pg_ctl" -D "$rehearsal_pgdata" status >/dev/null 2>&1 || \
     [[ -f "$rehearsal_pgdata/postmaster.pid" ]]; then
    basic_fail "Physical rehearsal did not stop cleanly"
    return
  fi
  local rehearsal_socket_state
  rehearsal_socket_state="$(
    directory_entry_state "$rehearsal_socket_directory"
  )" || return
  if [[ "$rehearsal_socket_state" != "empty" ]]; then
    basic_fail "Physical rehearsal left an unexpected Unix-socket artifact"
    return
  fi
  rmdir "$rehearsal_socket_directory"
  rehearsal_socket_directory=""
  PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py certify-physical-rehearsal \
      --observation "$run_directory/physical-rehearsal.observation.json" \
      --rehearsal-pgdata "$rehearsal_pgdata" \
      --physical-backup-manifest \
        "$run_directory/physical-postgres/backup_manifest" \
      --physical-backup-inventory \
        "$run_directory/physical-backup.inventory.json" \
      --retained-identity "$RETAINED_IDENTITY_FILE" \
      --receipt "$run_directory/physical-rehearsal.receipt.json"
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-physical-rehearsal \
      --observation "$run_directory/physical-rehearsal.observation.json" \
      --physical-backup-manifest \
        "$run_directory/physical-postgres/backup_manifest" \
      --physical-backup-inventory \
        "$run_directory/physical-backup.inventory.json" \
      --retained-identity "$RETAINED_IDENTITY_FILE" \
      --receipt "$run_directory/physical-rehearsal.receipt.json"
  basic_assert_no_database_clients
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"

  local backup_output backup_path manifest_path artifact_stem
  backup_output="$(
    backend_env 127.0.0.1 "$PGPORT" "$BACKUP_USER" "$BACKUP_PASSWORD" \
      python scripts/backup_database.py --output-directory "$artifacts_directory"
  )"
  backup_path="$(printf '%s\n' "$backup_output" | sed -n 's/^Backup created: //p')"
  manifest_path="$(printf '%s\n' "$backup_output" | sed -n 's/^Manifest created: //p')"
  if [[ ! -f "$backup_path" ]] || [[ ! -f "$manifest_path" ]]; then
    basic_fail "Logical backup did not produce its verified consistency set"
    return
  fi
  artifact_stem="${backup_path%.json.gz}"

  local family_shape staff_shape
  family_shape="$(basic_psql_scalar \
    "SELECT count(*) FROM unnest(ARRAY['family_authority_evidence_objects','family_authority_evidence_object_assessments']) AS expected(name) WHERE to_regclass('public.' || expected.name) IS NOT NULL")"
  staff_shape="$(basic_psql_scalar \
    "SELECT count(*) FROM unnest(ARRAY['staff_screening_document_versions','staff_driver_qualification_evidence_objects','transport_vehicle_evidence_versions']) AS expected(name) WHERE to_regclass('public.' || expected.name) IS NOT NULL")"
  if [[ "$family_shape" != "0" && "$family_shape" != "2" ]] || \
     [[ "$staff_shape" != "0" && "$staff_shape" != "3" ]]; then
    basic_fail "Evidence-vault database shape is partial"
    return
  fi
  if [[ "$family_shape" == "0" ]] && \
     [[ -d "$FAMILY_EVIDENCE_VAULT_PATH" ]]; then
    local family_vault_state
    family_vault_state="$(
      directory_entry_state "$FAMILY_EVIDENCE_VAULT_PATH"
    )" || return
    if [[ "$family_vault_state" != "empty" ]]; then
      basic_fail "Family vault bytes exist without database evidence rows"
      return
    fi
  fi
  if [[ "$staff_shape" == "0" ]] && \
     [[ -d "$STAFF_SCREENING_VAULT_PATH" ]]; then
    local staff_vault_state
    staff_vault_state="$(
      directory_entry_state "$STAFF_SCREENING_VAULT_PATH"
    )" || return
    if [[ "$staff_vault_state" != "empty" ]]; then
      basic_fail "Staff vault bytes exist without database evidence rows"
      return
    fi
  fi

  if [[ "$family_shape" == "2" ]]; then
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/family_evidence_vault_bundle.py create \
        --backup "$backup_path" \
        --manifest "$manifest_path" \
        --vault-root "$FAMILY_EVIDENCE_VAULT_PATH" \
        --output-directory "$artifacts_directory"
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/family_evidence_vault_bundle.py verify \
        --backup "$backup_path" \
        --manifest "$manifest_path" \
        --bundle "$artifact_stem.family-evidence.zip" \
        --bundle-manifest "$artifact_stem.family-evidence.manifest.json"
  fi
  if [[ "$staff_shape" == "3" ]]; then
    if [[ ! -f "$RUNTIME_SECRET_DIRECTORY/staff-screening-vault.key" ]]; then
      basic_fail "Staff vault recovery key is missing"
      return
    fi
    cp "$RUNTIME_SECRET_DIRECTORY/staff-screening-vault.key" \
      "$artifacts_directory/staff-screening-vault.key"
    chmod 600 "$artifacts_directory/staff-screening-vault.key"
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/staff_transport_vault_bundle.py create \
        --backup "$backup_path" \
        --manifest "$manifest_path" \
        --vault-root "$STAFF_SCREENING_VAULT_PATH" \
        --output-directory "$artifacts_directory"
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/staff_transport_vault_bundle.py verify \
        --backup "$backup_path" \
        --manifest "$manifest_path" \
        --bundle "$artifact_stem.staff-transport-evidence.zip" \
        --bundle-manifest "$artifact_stem.staff-transport-evidence.manifest.json"
  fi

  "$PG_BIN/initdb" -D "$clone_pgdata" \
    --username="$MIGRATION_USER" \
    --auth-local=trust --auth-host=trust --encoding=UTF8 --no-instructions
  chmod 700 "$clone_pgdata"
  basic_run_guarded_without_state_lock_in_child \
    "$PG_BIN/pg_ctl" -D "$clone_pgdata" \
    -l "$clone_directory/postgres.log" \
    -o "-p $clone_port -h 127.0.0.1" start || return
  clone_started=true
  local attempt
  for attempt in {1..80}; do
    "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$clone_port" -q && break
    sleep 0.125
  done
  "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$clone_port" -q
  "$PG_BIN/createdb" -h 127.0.0.1 -p "$clone_port" -U "$MIGRATION_USER" \
    "$DATABASE_NAME"

  local clone_data_directory clone_system_identifier restore_receipt
  clone_data_directory="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$clone_port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "SHOW data_directory")"
  clone_system_identifier="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$clone_port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "SELECT system_identifier::text FROM pg_control_system()")"
  restore_receipt="$clone_directory/database-restore.receipt.json"
  CARESYNC_RESTORE_CONFIRM_DISPOSABLE="127.0.0.1:$clone_port/$DATABASE_NAME" \
    backend_env 127.0.0.1 "$clone_port" "$MIGRATION_USER" "" \
      python scripts/restore_database.py \
        --backup "$backup_path" \
        --manifest "$manifest_path" \
        --receipt "$restore_receipt" \
        --prepare-empty-target \
        --expected-data-directory "$clone_data_directory" \
        --expected-system-identifier "$clone_system_identifier" \
        --require-empty-target

  if [[ "$family_shape" == "2" ]]; then
    backend_env 127.0.0.1 "$clone_port" "$MIGRATION_USER" "" \
      python scripts/family_evidence_vault_bundle.py restore \
        --backup "$backup_path" \
        --manifest "$manifest_path" \
        --bundle "$artifact_stem.family-evidence.zip" \
        --bundle-manifest "$artifact_stem.family-evidence.manifest.json" \
        --destination "$clone_directory/private-family-authority-vault" \
        --receipt "$clone_directory/family-evidence.receipt.json"
  fi
  if [[ "$staff_shape" == "3" ]]; then
    backend_env 127.0.0.1 "$clone_port" "$MIGRATION_USER" "" \
      python scripts/staff_transport_vault_bundle.py restore \
        --backup "$backup_path" \
        --manifest "$manifest_path" \
        --bundle "$artifact_stem.staff-transport-evidence.zip" \
        --bundle-manifest "$artifact_stem.staff-transport-evidence.manifest.json" \
        --destination "$clone_directory/private-staff-screening-vault" \
        --receipt "$clone_directory/staff-transport.receipt.json"
  fi

  # The restore receipt proves the populated clone at exact 0039. Migrate that
  # disposable database in its own Alembic transaction, rebuild the restricted
  # runtime boundary there, and only then ask the read-only contract helper to
  # issue the 0042 clone certificate. Complete row evidence is collected in a
  # read-only transaction by the migration maintenance identity, which can see
  # every FORCE RLS row. The helper's separate runtime hook still connects only
  # through the opened NOBYPASSRLS release probe below.
  backend_env 127.0.0.1 "$clone_port" "$MIGRATION_USER" "" \
    alembic upgrade "$CARESYNC_RETAINED_TARGET_REVISION"
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X \
    -h 127.0.0.1 -p "$clone_port" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -f "$RELEASE_EXECUTION_ROOT/backend/scripts/bootstrap_basic_runtime_role.sql" \
    >/dev/null
  configure_release_probe \
    "$run_directory/controlled-health-probe.credential" "$clone_port" || return
  open_release_probe_for_controlled_health "$clone_port" || return
  prove_release_probe_write_rejection_or_close \
    "$run_directory/controlled-health-probe.credential" "$clone_port" || return
  local clone_certify_result=0
  backend_env 127.0.0.1 "$clone_port" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py certify-clone \
      --restore-receipt "$restore_receipt" \
      --output "$clone_directory/certificate.json" || clone_certify_result=$?
  close_release_probe_after_controlled_health "$clone_port" || return
  if (( clone_certify_result != 0 )); then
    basic_fail "Disposable clone certification failed"
    return "$clone_certify_result"
  fi
  require_release_probe_contract nologin "$clone_port" || return

  # A prepared fence is commit/resume-only, so no trust-auth disposable
  # server may survive across that boundary. Prove and stop the clone first.
  reconcile_prepare_disposable_postgres \
    "$run_directory" "$clone_pgdata" clone
  clone_started=false

  discover_artifacts "$run_directory" before-payload
  # Bind an immutable run-local copy first. The active fence remains in its
  # recoverable preparing state until the no-clobber candidate exists.
  create_prepared_fence_evidence \
    "$run_directory" \
    "$CANDIDATE_RECEIPT" \
    "$app_prior_state" \
    "$ingest_prior_state"
  # The candidate binds copied keys, vault bundles, database backup trees,
  # restore receipts, certificates and the prepared-context evidence. Flush
  # the whole closed tree before hashes are admitted into the candidate.
  durability_barrier_private_tree "$run_directory" || return
  build_contract_artifact_args || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py prepare \
      --clone-certificate "$CLONE_CERTIFICATE" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --release-payload "$RELEASE_PAYLOAD" \
      --receipt "$CANDIDATE_RECEIPT"
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-prepare-receipt \
      --receipt "$CANDIDATE_RECEIPT" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD"
  durability_barrier_private_tree "$run_directory" || return

  # Only a complete and independently reopened candidate may seal the active
  # fence. The active context must be byte-identical to its bound evidence.
  seal_fence \
    "$run_directory" \
    "$CANDIDATE_RECEIPT" \
    "$app_prior_state" \
    "$ingest_prior_state"
  if ! cmp -s "$PREPARED_FENCE_CONTEXT" "$RELEASE_FENCE_DIRECTORY/context"; then
    basic_fail "Sealed release fence differs from candidate-bound evidence"
    return
  fi
  PREPARE_CLEANUP_CANDIDATE_SEALED=true
  trap - EXIT
  printf '%s\n' \
    "CareSync release preparation passed." \
    "Retained database: exact $CARESYNC_RETAINED_SOURCE_REVISION, fenced, NOLOGIN." \
    "Candidate receipt: $CANDIDATE_RECEIPT" \
    "Commit phrase: $CARESYNC_RELEASE_COMMIT_PHRASE"
}

commit_release() {
  local candidate_receipt=""
  local confirmation=""
  while (( $# > 0 )); do
    case "$1" in
      --receipt)
        [[ $# -ge 2 ]] || { usage; return 2; }
        candidate_receipt="$2"
        shift 2
        ;;
      --confirm)
        [[ $# -ge 2 ]] || { usage; return 2; }
        confirmation="$2"
        shift 2
        ;;
      *)
        usage
        return 2
        ;;
    esac
  done
  if [[ -z "$candidate_receipt" ]] || [[ "$confirmation" != "$CARESYNC_RELEASE_COMMIT_PHRASE" ]]; then
    basic_fail "Commit requires the candidate receipt and exact confirmation phrase"
    return
  fi
  candidate_receipt="$(
    cd "$(dirname "$candidate_receipt")" && pwd
  )/$(basename "$candidate_receipt")" || return
  if [[ ! -f "$candidate_receipt" ]] || \
     [[ "$(basename "$candidate_receipt")" != "candidate-receipt.json" ]]; then
    basic_fail "Candidate receipt is missing or has an unexpected name"
    return
  fi
  local run_directory
  run_directory="$(dirname "$candidate_receipt")"
  discover_artifacts "$run_directory"
  if [[ "$candidate_receipt" != "$CANDIDATE_RECEIPT" ]]; then
    basic_fail "Candidate receipt does not belong to its release run"
    return
  fi
  reexec_release_from_captured_source_if_needed \
    "$run_directory" commit --receipt "$candidate_receipt" \
    --confirm "$confirmation" || return
  require_matching_fence "$run_directory" "$candidate_receipt" || return
  if [[ -f "$COMMIT_RECEIPT" ]] && [[ ! -L "$COMMIT_RECEIPT" ]]; then
    finish_active_prepared_invalidation_if_present \
      commit "$run_directory" "$candidate_receipt" "$COMMIT_RECEIPT" \
      "$CARESYNC_RETAINED_TARGET_REVISION" || return
    if [[ "$ACTIVE_INVALIDATION_FINISHED" == "true" ]]; then
      basic_fail \
        "The invalidated commit startup was safely retired; prepare a fresh candidate"
      return
    fi
  fi
  build_contract_artifact_args || return
  arm_controlled_runtime_window_cleanup
  CONTROLLED_RUNTIME_WINDOW_OPEN=true

  # A retry can arrive after a controlled startup opened LOGIN but before it
  # completed. Reassert the durable fence before any long artifact hash:
  # prove identity, make NOLOGIN the first mutation, then drain every writer.
  if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_verify_retained_identity || return
    fence_runtime_roles || return
    basic_quiesce_application || return
  else
    basic_quiesce_application || return
    basic_start_postgres || return
    fence_runtime_roles || return
  fi
  basic_assert_no_cluster_clients || return
  basic_cleanup_appledouble_sidecars || return

  # Every immutable artifact is reopened only in the proven no-writer posture.
  verify_static_artifacts || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-prepare-receipt \
      --receipt "$candidate_receipt" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" || return

  # Re-open the same-filesystem feasibility proof at the last boundary before
  # durable commit intent and the first live Alembic byte.
  basic_require_release_apfs_topology \
    "$PHYSICAL_BACKUP_PATH" "$RUNTIME_DIR/quarantine" || return

  # This monotonic, candidate/source/physical-backup-bound intent is durable
  # before the first live Alembic byte executes. If the process is lost before
  # commit/finalization receipts exist, the exact phrase-gated physical
  # recovery path can still restore the rehearsed 0039 tree.
  create_commit_attempt_intent "$run_directory" "$candidate_receipt" || return

  local current_revision
  current_revision="$(basic_current_revision)" || return
  if [[ "$current_revision" == "$CARESYNC_RETAINED_SOURCE_REVISION" ]]; then
    (
      cd "$RELEASE_EXECUTION_ROOT/backend"
      CARESYNC_VENV_PATH="$VENV_PATH" \
      ENVIRONMENT=development \
      DATABASE_TYPE=postgres \
      DATABASE_HOST=127.0.0.1 \
      DATABASE_PORT="$PGPORT" \
      DATABASE_USER="$MIGRATION_USER" \
      DATABASE_PASSWORD= \
      DATABASE_NAME="$DATABASE_NAME" \
      DATABASE_READ_ONLY=false \
      ENABLE_ADVANCED_ROUTES=false \
      CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true \
        /bin/bash ./scripts/uv.sh run alembic upgrade \
          "$CARESYNC_RETAINED_TARGET_REVISION"
    ) || return
  elif [[ "$current_revision" != "$CARESYNC_RETAINED_TARGET_REVISION" ]]; then
    basic_fail "Commit recovery accepts only exact 0039 or already-migrated exact 0042"
    return
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_TARGET_REVISION" || return
  basic_assert_no_cluster_clients || return

  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X \
    -h 127.0.0.1 -p "$PGPORT" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -f "$RELEASE_EXECUTION_ROOT/backend/scripts/bootstrap_basic_runtime_role.sql" \
    >/dev/null || return
  configure_release_probe "$RELEASE_PROBE_CREDENTIAL" || return
  basic_set_role_login_state caresync_basic_app nologin || return
  basic_set_role_login_state \
    caresync_transport_evidence_ingest nologin || return
  require_release_probe_contract nologin || return
  basic_require_runtime_roles_fenced || return
  basic_require_exact_revision "$CARESYNC_RETAINED_TARGET_REVISION" || return

  if [[ ! -f "$COMMIT_RECEIPT" ]]; then
    # Runtime certification uses only the candidate-bound SELECT-only probe.
    # Both application writer identities remain NOLOGIN throughout.
    CONTROLLED_RUNTIME_WINDOW_OPEN=true
    open_release_probe_for_controlled_health || return
    prove_release_probe_write_rejection_or_close \
      "$RELEASE_PROBE_CREDENTIAL" || return
    if ! backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/basic_release_contract.py certify-live \
        --candidate-receipt "$candidate_receipt" \
        --clone-certificate "$CLONE_CERTIFICATE" \
        --release-payload "$RELEASE_PAYLOAD" \
        "${CONTRACT_ARTIFACT_ARGS[@]}" \
        --receipt "$COMMIT_RECEIPT"; then
      if close_release_probe_after_controlled_health; then
        CONTROLLED_RUNTIME_WINDOW_OPEN=false
      fi
      return 1
    fi
    close_release_probe_after_controlled_health || return
    CONTROLLED_RUNTIME_WINDOW_OPEN=false
  fi
  if ! backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-commit-receipt \
      --candidate-receipt "$candidate_receipt" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --receipt "$COMMIT_RECEIPT"; then
    fence_runtime_roles || true
    return 1
  fi

  # Start only the bounded read-only probe runtime. No application or outbox
  # writer is opened until the epoch is durable and the fence is retired.
  CONTROLLED_RUNTIME_WINDOW_OPEN=true
  open_release_probe_for_controlled_health || return
  prove_release_probe_write_rejection_or_close \
    "$RELEASE_PROBE_CREDENTIAL" || return
  if ! CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}" \
    /bin/bash "$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh" \
    --commit-0042 \
    --receipt "$candidate_receipt" \
    --commit-receipt "$COMMIT_RECEIPT"; then
    if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
       [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
      if fence_runtime_roles; then
        CONTROLLED_RUNTIME_WINDOW_OPEN=false
      fi
    else
      if close_retired_controlled_runtime_after_child_failure; then
        CONTROLLED_RUNTIME_WINDOW_OPEN=false
      fi
    fi
    return 1
  fi
  CONTROLLED_RUNTIME_WINDOW_FINALIZED=true
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  disarm_controlled_runtime_window_cleanup
}

resume_release_0039() {
  local candidate_receipt=""
  local confirmation=""
  while (( $# > 0 )); do
    case "$1" in
      --receipt)
        [[ $# -ge 2 ]] || { usage; return 2; }
        candidate_receipt="$2"
        shift 2
        ;;
      --confirm)
        [[ $# -ge 2 ]] || { usage; return 2; }
        confirmation="$2"
        shift 2
        ;;
      *)
        usage
        return 2
        ;;
    esac
  done
  if [[ -z "$candidate_receipt" ]] || [[ "$confirmation" != "$CARESYNC_RELEASE_RESUME_PHRASE" ]]; then
    basic_fail "0039 resume requires the candidate receipt and exact resume phrase"
    return
  fi
  candidate_receipt="$(cd "$(dirname "$candidate_receipt")" && pwd)/$(basename "$candidate_receipt")"
  if [[ ! -f "$candidate_receipt" ]] || \
     [[ "$(basename "$candidate_receipt")" != "candidate-receipt.json" ]]; then
    basic_fail "Candidate receipt is missing or has an unexpected name"
    return
  fi
  local run_directory
  run_directory="$(dirname "$candidate_receipt")"
  discover_artifacts "$run_directory"
  if [[ "$candidate_receipt" != "$CANDIDATE_RECEIPT" ]]; then
    basic_fail "Candidate receipt does not belong to its release run"
    return
  fi
  reexec_release_from_captured_source_if_needed \
    "$run_directory" _resume-0039 --receipt "$candidate_receipt" \
    --confirm "$confirmation" || return
  build_contract_artifact_args
  local resume_reentry=false
  if [[ ! -e "$RELEASE_FENCE_DIRECTORY" ]] && \
     [[ ! -L "$RELEASE_FENCE_DIRECTORY" ]] && \
     { [[ -e "$run_directory/fence-retired" ]] || \
       [[ -L "$run_directory/fence-retired" ]]; }; then
    require_matching_retired_prepared_fence \
      "$run_directory" "$candidate_receipt" || return
    if [[ "$RESUME_AUTHORIZATION" != "$run_directory/resume-0039.authorization.json" ]] || \
       [[ ! -f "$RESUME_AUTHORIZATION" ]]; then
      basic_fail "Retired resume fence has no run-bound authorization"
      return
    fi
    reject_consumed_or_invalidated_startup \
      resume "$run_directory" "$candidate_receipt" "$RESUME_AUTHORIZATION" \
      "$run_directory/fence-retired/context" \
      "$CARESYNC_RETAINED_SOURCE_REVISION" || return
    if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      basic_verify_retained_identity || return
      if ! basic_require_exact_revision \
        "$CARESYNC_RETAINED_SOURCE_REVISION"; then
        create_startup_evidence \
          resume invalidated "$run_directory" "$candidate_receipt" \
          "$RESUME_AUTHORIZATION" "$run_directory/fence-retired/context" \
          "$CARESYNC_RETAINED_SOURCE_REVISION" || return
        basic_fail \
          "Retired resume belongs to an older live state and was not reactivated"
        return
      fi
    fi
    arm_controlled_runtime_window_cleanup
    CONTROLLED_RUNTIME_WINDOW_OPEN=true
    reactivate_retired_prepared_fence \
      "$run_directory" "$candidate_receipt" || return
    resume_reentry=true
  else
    require_matching_fence "$run_directory" "$candidate_receipt" || return
    finish_active_prepared_invalidation_if_present \
      resume "$run_directory" "$candidate_receipt" "$RESUME_AUTHORIZATION" \
      "$CARESYNC_RETAINED_SOURCE_REVISION" || return
    if [[ "$ACTIVE_INVALIDATION_FINISHED" == "true" ]]; then
      basic_fail \
        "The invalidated resume startup was safely retired; prepare a fresh candidate"
      return
    fi
    if [[ -e "$REACTIVATION_PENDING" ]] || \
       [[ -L "$REACTIVATION_PENDING" ]]; then
      reactivate_retired_prepared_fence \
        "$run_directory" "$candidate_receipt" || return
    fi
    arm_controlled_runtime_window_cleanup
    CONTROLLED_RUNTIME_WINDOW_OPEN=true
  fi

  # The active fence precedes every boot or long hash. If PostgreSQL is already
  # ready, identity is proven and NOLOGIN is the first mutation. If it is down,
  # all managed writers are stopped before boot and both roles are fenced
  # immediately after identity becomes queryable.
  if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_verify_retained_identity || return
    fence_runtime_roles || return
    basic_quiesce_application || return
  else
    basic_quiesce_application || return
    basic_start_postgres || return
    fence_runtime_roles || return
  fi
  basic_assert_no_cluster_clients || return
  basic_cleanup_appledouble_sidecars || return
  if ! basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"; then
    if [[ "$resume_reentry" == "true" ]]; then
      invalidate_reactivated_prepared_start \
        resume "$run_directory" "$candidate_receipt" \
        "$RESUME_AUTHORIZATION" "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      basic_fail \
        "Retired resume state belongs to a changed runtime; it was safely retired. Prepare a fresh candidate."
    fi
    return 1
  fi

  verify_static_artifacts || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-prepare-receipt \
      --receipt "$candidate_receipt" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" || return

  if [[ ! -f "$RESUME_AUTHORIZATION" ]] && \
     [[ "$resume_reentry" != "true" ]]; then
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/basic_release_contract.py certify-resume-0039 \
        --candidate-receipt "$candidate_receipt" \
        --clone-certificate "$CLONE_CERTIFICATE" \
        --release-payload "$RELEASE_PAYLOAD" \
        "${CONTRACT_ARTIFACT_ARGS[@]}" \
        --authorization "$RESUME_AUTHORIZATION" || return
  fi
  if ! backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-resume-authorization \
      --candidate-receipt "$candidate_receipt" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --authorization "$RESUME_AUTHORIZATION"; then
    if [[ "$resume_reentry" == "true" ]]; then
      invalidate_reactivated_prepared_start \
        resume "$run_directory" "$candidate_receipt" \
        "$RESUME_AUTHORIZATION" "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      basic_fail \
        "Retired resume authorization no longer matches the source; it was safely retired. Prepare a fresh candidate."
    fi
    return 1
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return

  require_release_probe_contract nologin || return
  open_release_probe_for_controlled_health || return
  prove_release_probe_write_rejection_or_close \
    "$RELEASE_PROBE_CREDENTIAL" || return
  if ! CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}" \
    /bin/bash "$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh" \
    --resume-0039 \
    --receipt "$candidate_receipt" \
    --authorization "$RESUME_AUTHORIZATION"; then
    if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
       [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
      if fence_runtime_roles; then
        CONTROLLED_RUNTIME_WINDOW_OPEN=false
      fi
    else
      if close_retired_controlled_runtime_after_child_failure; then
        CONTROLLED_RUNTIME_WINDOW_OPEN=false
      fi
    fi
    return 1
  fi
  CONTROLLED_RUNTIME_WINDOW_FINALIZED=true
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  disarm_controlled_runtime_window_cleanup
}

rollback_release() {
  local candidate_receipt=""
  local commit_receipt=""
  local finalization_receipt=""
  local confirmation=""
  while (( $# > 0 )); do
    case "$1" in
      --receipt)
        [[ $# -ge 2 ]] || { usage; return 2; }
        candidate_receipt="$2"
        shift 2
        ;;
      --commit-receipt)
        [[ $# -ge 2 ]] || { usage; return 2; }
        commit_receipt="$2"
        shift 2
        ;;
      --finalization-receipt)
        [[ $# -ge 2 ]] || { usage; return 2; }
        finalization_receipt="$2"
        shift 2
        ;;
      --confirm)
        [[ $# -ge 2 ]] || { usage; return 2; }
        confirmation="$2"
        shift 2
        ;;
      *)
        usage
        return 2
        ;;
    esac
  done
  if [[ -z "$candidate_receipt" ]] || \
     [[ "$confirmation" != "$CARESYNC_RELEASE_ROLLBACK_PHRASE" ]] || \
     { [[ -n "$commit_receipt" ]] && [[ -z "$finalization_receipt" ]]; } || \
     { [[ -z "$commit_receipt" ]] && [[ -n "$finalization_receipt" ]]; }; then
    basic_fail \
      "Rollback requires the candidate and exact phrase, plus either both finalized receipts or neither after an interrupted commit"
    return
  fi
  local pre_finalization_rollback=false
  if [[ -z "$commit_receipt" ]]; then
    pre_finalization_rollback=true
  fi
  basic_require_local_toolchain

  candidate_receipt="$(
    cd "$(dirname "$candidate_receipt")" && pwd
  )/$(basename "$candidate_receipt")"
  if [[ "$pre_finalization_rollback" != "true" ]]; then
    commit_receipt="$(
      cd "$(dirname "$commit_receipt")" && pwd
    )/$(basename "$commit_receipt")" || return
    finalization_receipt="$(
      cd "$(dirname "$finalization_receipt")" && pwd
    )/$(basename "$finalization_receipt")" || return
  fi
  if [[ ! -f "$candidate_receipt" ]] || \
     [[ "$(basename "$candidate_receipt")" != "candidate-receipt.json" ]]; then
    basic_fail "Candidate receipt is missing or has an unexpected name"
    return
  fi
  local run_directory
  run_directory="$(dirname "$candidate_receipt")"
  discover_artifacts "$run_directory" || return
  if [[ "$candidate_receipt" != "$CANDIDATE_RECEIPT" ]]; then
    basic_fail "Rollback candidate does not belong to its release run"
    return
  fi
  local reexec_arguments=(rollback --receipt "$candidate_receipt")
  if [[ "$pre_finalization_rollback" != "true" ]]; then
    reexec_arguments+=(
      --commit-receipt "$commit_receipt"
      --finalization-receipt "$finalization_receipt"
    )
  fi
  reexec_arguments+=(--confirm "$confirmation")
  reexec_release_from_captured_source_if_needed \
    "$run_directory" "${reexec_arguments[@]}" || return
  build_contract_artifact_args || return
  if [[ "$pre_finalization_rollback" == "true" ]]; then
    commit_receipt="$COMMIT_ATTEMPT_INTENT"
    finalization_receipt=none
    require_commit_attempt_intent \
      "$commit_receipt" "$run_directory" "$candidate_receipt" || return
  elif [[ "$commit_receipt" != "$COMMIT_RECEIPT" ]] || \
       [[ "$finalization_receipt" != "$FINALIZATION_RECEIPT" ]] || \
       [[ ! -f "$commit_receipt" ]] || [[ ! -f "$finalization_receipt" ]]; then
    basic_fail "Rollback receipts do not belong to one finalized release run"
    return
  fi

  local run_key
  run_key="$(basename "$run_directory")"
  if [[ ! "$run_key" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]]; then
    basic_fail "Release run directory has an unsafe rollback identifier"
    return
  fi
  ensure_release_state_directory || return
  basic_assert_no_symlink_components "$run_directory" || return
  if [[ "$run_directory" != "$RELEASE_STATE_DIRECTORY/$run_key" ]] || \
     [[ -L "$run_directory" ]] || [[ ! -d "$run_directory" ]] || \
     [[ "$(stat -f '%u' "$run_directory")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$run_directory")" != "700" ]] || \
     [[ "$(cd "$(dirname "$run_directory")" && pwd -P)" != \
        "$(cd "$RELEASE_STATE_DIRECTORY" && pwd -P)" ]]; then
    basic_fail "Rollback run must be a private direct release-state child"
    return
  fi
  local quarantine_parent="$RUNTIME_DIR/quarantine"
  local quarantine_directory
  if [[ "$pre_finalization_rollback" == "true" ]]; then
    quarantine_directory="$quarantine_parent/postgres-data-interrupted-commit-$run_key"
  else
    quarantine_directory="$quarantine_parent/postgres-data-0042-$run_key"
  fi
  local partial_directory="$RUNTIME_DIR/.postgres-data-rollback-$run_key"
  local rollback_authorization="$ROLLBACK_AUTHORIZATION"

  # Establish and attest the rollback geometry before converting, reactivating,
  # or creating any rollback fence. This includes the already-captured
  # physical evidence and the direct parents of both atomic rename targets.
  if [[ -L "$quarantine_parent" ]] || \
     [[ -e "$quarantine_parent" && ! -d "$quarantine_parent" ]]; then
    basic_fail "Rollback quarantine parent is unsafe"
    return
  fi
  if [[ ! -e "$quarantine_parent" ]]; then
    durable_ensure_private_directory "$quarantine_parent" || return
  fi
  if [[ "$(stat -f '%u' "$quarantine_parent")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$quarantine_parent")" != "700" ]]; then
    basic_fail "Rollback quarantine parent must be private mode 0700"
    return
  fi
  basic_require_release_apfs_topology \
    "$PHYSICAL_BACKUP_PATH" "$quarantine_parent" || return

  if [[ "$pre_finalization_rollback" == "true" ]] && \
     [[ -f "$RELEASE_FENCE_DIRECTORY/context" ]] && \
     grep -Fqx "status=prepared" "$RELEASE_FENCE_DIRECTORY/context"; then
    # Convert the already durable prepared fence in place. This journal
    # transition precedes every PostgreSQL stop/rename, so power loss can
    # always resume from one active, candidate-bound recovery state.
    require_matching_fence "$run_directory" "$candidate_receipt" || return
    require_interrupted_commit_recovery_evidence \
      "$run_directory" "$candidate_receipt" || return
    local interrupted_app_prior interrupted_ingest_prior
    interrupted_app_prior="$(fence_prior_state app_prior_login)" || return
    interrupted_ingest_prior="$(fence_prior_state ingest_prior_login)" || return
    basic_quiesce_application || return
    if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      basic_verify_retained_identity || return
      fence_runtime_roles || return
      basic_assert_no_cluster_clients || return
    fi
    write_rollback_context \
      rollback_preparing "$run_directory" "$candidate_receipt" \
      "$commit_receipt" "$finalization_receipt" "$rollback_authorization" \
      "$quarantine_directory" "$partial_directory" \
      "$interrupted_app_prior" "$interrupted_ingest_prior" replace || return
    require_matching_rollback_fence \
      "$run_directory" "$candidate_receipt" \
      "$commit_receipt" "$finalization_receipt" || return
  elif [[ "$pre_finalization_rollback" != "true" ]] && \
       [[ -f "$RELEASE_FENCE_DIRECTORY/context" ]] && \
       grep -Fqx "status=prepared" "$RELEASE_FENCE_DIRECTORY/context"; then
    # A finalized receipt can exist before the prepared fence is retired.
    # Admit that narrow post-health failure state only after re-opening the
    # exact candidate, commit and finalization chain. Then monotonically
    # convert the already durable prepared journal into this finalized
    # rollback's receipt-bound journal before any PostgreSQL stop or rename.
    require_matching_fence "$run_directory" "$candidate_receipt" || return
    verify_static_artifacts || return
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/basic_release_contract.py verify-finalization-receipt \
        --candidate-receipt "$candidate_receipt" \
        --clone-certificate "$CLONE_CERTIFICATE" \
        --release-payload "$RELEASE_PAYLOAD" \
        "${CONTRACT_ARTIFACT_ARGS[@]}" \
        --commit-receipt "$commit_receipt" \
        --receipt "$finalization_receipt" || return
    local finalized_app_prior finalized_ingest_prior
    finalized_app_prior="$(fence_prior_state app_prior_login)" || return
    finalized_ingest_prior="$(fence_prior_state ingest_prior_login)" || return
    basic_quiesce_application || return
    if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      basic_verify_retained_identity || return
      basic_require_exact_revision \
        "$CARESYNC_RETAINED_TARGET_REVISION" || return
      fence_runtime_roles || return
      basic_assert_no_cluster_clients || return
    fi
    write_rollback_context \
      rollback_preparing "$run_directory" "$candidate_receipt" \
      "$commit_receipt" "$finalization_receipt" "$rollback_authorization" \
      "$quarantine_directory" "$partial_directory" \
      "$finalized_app_prior" "$finalized_ingest_prior" replace || return
    require_matching_rollback_fence \
      "$run_directory" "$candidate_receipt" \
      "$commit_receipt" "$finalization_receipt" || return
  elif [[ "$pre_finalization_rollback" == "true" ]] && \
       { [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
         [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; }; then
    require_matching_rollback_fence \
      "$run_directory" "$candidate_receipt" \
      "$commit_receipt" "$finalization_receipt" || return
  elif [[ "$pre_finalization_rollback" == "true" ]] && \
       [[ ! -e "$run_directory/rollback-fence-retired" ]] && \
       [[ ! -L "$run_directory/rollback-fence-retired" ]]; then
    basic_fail \
      "Interrupted-commit rollback requires this run's active prepared recovery fence"
    return
  fi

  # A power loss can occur after post-health rollback finalization has restored
  # writer states and retired the fence but before start-basic finishes its
  # deferred push step. Only this run's exact private `rollback_starting`
  # context may be atomically moved back into the active fence. The ordinary
  # no-fence branch still accepts only live 0042, so this is not a general
  # unauthenticated exact-0039 startup path.
  local rollback_reentry_guard_armed=false
  local rollback_was_reactivated=false
  if [[ ! -e "$RELEASE_FENCE_DIRECTORY" ]] && \
     [[ ! -L "$RELEASE_FENCE_DIRECTORY" ]] && \
     { [[ -e "$run_directory/rollback-fence-retired" ]] || \
       [[ -L "$run_directory/rollback-fence-retired" ]]; }; then
    require_matching_retired_rollback_fence \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt" \
      "$rollback_authorization" \
      "$quarantine_directory" \
      "$partial_directory" || return
    reject_consumed_or_invalidated_startup \
      rollback "$run_directory" "$candidate_receipt" \
      "$rollback_authorization" \
      "$run_directory/rollback-fence-retired/context" \
      "$CARESYNC_RETAINED_SOURCE_REVISION" || return
    if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      basic_verify_retained_identity || return
      if ! basic_require_exact_revision \
        "$CARESYNC_RETAINED_SOURCE_REVISION"; then
        create_startup_evidence \
          rollback invalidated "$run_directory" "$candidate_receipt" \
          "$rollback_authorization" \
          "$run_directory/rollback-fence-retired/context" \
          "$CARESYNC_RETAINED_SOURCE_REVISION" || return
        basic_fail \
          "Retired rollback belongs to an older live state and was not reactivated"
        return
      fi
    fi
    arm_controlled_runtime_window_cleanup
    CONTROLLED_RUNTIME_WINDOW_OPEN=true
    rollback_reentry_guard_armed=true
    rollback_was_reactivated=true
  fi
  if [[ "$pre_finalization_rollback" != "true" ]] || \
     { [[ ! -e "$RELEASE_FENCE_DIRECTORY" ]] && \
       [[ ! -L "$RELEASE_FENCE_DIRECTORY" ]]; } || \
     [[ -e "$REACTIVATION_PENDING" ]] || \
     [[ -L "$REACTIVATION_PENDING" ]]; then
    reactivate_retired_rollback_fence \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt" \
      "$rollback_authorization" \
      "$quarantine_directory" \
      "$partial_directory" || return
  fi
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    finish_active_rollback_invalidation_if_present \
      "$run_directory" "$candidate_receipt" "$commit_receipt" \
      "$finalization_receipt" "$rollback_authorization" || return
    if [[ "$ACTIVE_INVALIDATION_FINISHED" == "true" ]]; then
      basic_fail \
        "The invalidated rollback startup was safely retired; prepare a fresh candidate"
      return
    fi
  fi

  # A retry may have been interrupted after the controlled runtime roles were
  # reopened. Structurally match the durable rollback fence, then quiesce and
  # re-fence immediately—before any potentially long cryptographic rehash.
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    if [[ "$rollback_reentry_guard_armed" != "true" ]]; then
      arm_controlled_runtime_window_cleanup
      CONTROLLED_RUNTIME_WINDOW_OPEN=true
      rollback_reentry_guard_armed=true
    fi
    require_matching_rollback_fence \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt"
    if [[ -d "$PGDATA" ]] && \
       { [[ "$pre_finalization_rollback" != "true" ]] || \
         "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; }; then
      local early_rollback_status
      early_rollback_status="$(rollback_context_value status)"
      if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
        basic_verify_retained_identity
        # The active rollback fence is already durable. Make NOLOGIN the first
        # database mutation, then drain sessions and writers.
        fence_runtime_roles
        basic_quiesce_application
        basic_assert_no_cluster_clients
      elif [[ "$early_rollback_status" == "rollback_starting" ]]; then
        # When exact 0039 is down, prove all application writers stopped before
        # boot. The EXIT/INT/TERM guard spans the only unavoidable interval
        # between readiness/identity and the first NOLOGIN mutation.
        basic_quiesce_application
        preserve_proven_stale_postmaster_pid "$run_directory" "$PGDATA"
        basic_start_postgres
        fence_runtime_roles
        basic_assert_no_cluster_clients
      fi
      if [[ "$early_rollback_status" == "rollback_starting" ]] && \
         ! basic_require_exact_revision \
           "$CARESYNC_RETAINED_SOURCE_REVISION"; then
        if [[ "$rollback_was_reactivated" == "true" ]]; then
          invalidate_reactivated_rollback_start \
            "$run_directory" "$candidate_receipt" \
            "$commit_receipt" "$finalization_receipt" \
            "$rollback_authorization" || return
          basic_fail \
            "Retired rollback state belongs to a changed runtime; it was safely retired."
        fi
        return 1
      fi
    fi
    CONTROLLED_RUNTIME_WINDOW_OPEN=false
    disarm_controlled_runtime_window_cleanup
    rollback_reentry_guard_armed=false
  fi

  # For a new rollback this proof is read-only and precedes the rollback fence.
  # On retry the existing fence was already reasserted above.
  if [[ "$pre_finalization_rollback" == "true" ]]; then
    require_interrupted_commit_recovery_evidence \
      "$run_directory" "$candidate_receipt" || return
  else
    if [[ "$pre_finalization_rollback" == "true" ]]; then
      require_interrupted_commit_recovery_evidence \
        "$run_directory" "$candidate_receipt" || return
    else
      verify_static_artifacts || return
      backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
        python scripts/basic_release_contract.py verify-finalization-receipt \
          --candidate-receipt "$candidate_receipt" \
          --clone-certificate "$CLONE_CERTIFICATE" \
          --release-payload "$RELEASE_PAYLOAD" \
          "${CONTRACT_ARTIFACT_ARGS[@]}" \
          --commit-receipt "$commit_receipt" \
          --receipt "$finalization_receipt" || return
    fi
  fi

  if [[ -L "$quarantine_parent" ]] || \
     [[ -e "$quarantine_parent" && ! -d "$quarantine_parent" ]]; then
    basic_fail "Rollback quarantine parent is unsafe"
    return
  fi
  if [[ ! -e "$quarantine_parent" ]]; then
    durable_ensure_private_directory "$quarantine_parent" || return
  fi
  if [[ "$(stat -f '%u' "$quarantine_parent")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$quarantine_parent")" != "700" ]]; then
    basic_fail "Rollback quarantine parent must be private mode 0700"
    return
  fi
  # Recheck after receipt re-open and immediately before a new rollback fence
  # can lead to stop/copy/rename work.
  basic_require_release_apfs_topology \
    "$PHYSICAL_BACKUP_PATH" "$quarantine_parent" || return

  local new_rollback=false
  if [[ ! -e "$RELEASE_FENCE_DIRECTORY" ]] && \
     [[ ! -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    if [[ -d "$PGDATA" ]] && \
       ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      preserve_proven_stale_postmaster_pid "$run_directory" "$PGDATA"
    fi
    basic_start_postgres
    basic_require_exact_revision "$CARESYNC_RETAINED_TARGET_REVISION"
    basic_cleanup_appledouble_sidecars
    basic_quiesce_application
    basic_assert_no_database_clients
    local app_prior_state ingest_prior_state
    app_prior_state="$(basic_role_login_state caresync_basic_app)"
    ingest_prior_state="$(basic_role_login_state caresync_transport_evidence_ingest)"
    if [[ "$app_prior_state" != "login" ]] || \
       [[ "$ingest_prior_state" != "login" ]]; then
      basic_fail \
        "A new emergency rollback requires both finalized runtime roles LOGIN"
      return
    fi
    create_rollback_fence \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt" \
      "$rollback_authorization" \
      "$quarantine_directory" \
      "$partial_directory" \
      "$app_prior_state" \
      "$ingest_prior_state"
    new_rollback=true
  else
    require_matching_rollback_fence \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt"
    if [[ "$(rollback_context_value quarantine_directory)" != \
          "$quarantine_directory" ]] || \
       [[ "$(rollback_context_value partial_directory)" != "$partial_directory" ]] || \
       [[ "$(rollback_context_value authorization)" != "$rollback_authorization" ]]; then
      basic_fail "Rollback fence paths do not match the finalized release"
      return
    fi
  fi

  # A durable rollback fence must close every known writer identity before the
  # second (potentially long) artifact rehash. Also reject client sessions in
  # every database, not merely `caresync`.
  if [[ -d "$PGDATA" ]] && \
     ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q && \
     [[ ! -e "$quarantine_directory" ]] && \
     [[ ! -L "$quarantine_directory" ]]; then
    if [[ "$pre_finalization_rollback" == "true" ]]; then
      stop_unready_retained_postgres_for_interrupted_commit \
        "$run_directory" || return
    else
      preserve_proven_stale_postmaster_pid "$run_directory" "$PGDATA"
      basic_start_postgres
    fi
  fi
  if [[ -d "$PGDATA" ]] && \
     "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    fence_runtime_roles
    basic_assert_no_cluster_clients
  fi

  # Reopen all evidence after the durable fence too. If any artifact changed
  # between preflight and fencing, no server or filesystem promotion follows.
  if [[ "$pre_finalization_rollback" == "true" ]]; then
    require_interrupted_commit_recovery_evidence \
      "$run_directory" "$candidate_receipt" || return
  else
    if [[ "$pre_finalization_rollback" == "true" ]]; then
      require_interrupted_commit_recovery_evidence \
        "$run_directory" "$candidate_receipt" || return
    else
      verify_static_artifacts || return
      backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
        python scripts/basic_release_contract.py verify-finalization-receipt \
          --candidate-receipt "$candidate_receipt" \
          --clone-certificate "$CLONE_CERTIFICATE" \
          --release-payload "$RELEASE_PAYLOAD" \
          "${CONTRACT_ARTIFACT_ARGS[@]}" \
          --commit-receipt "$commit_receipt" \
          --receipt "$finalization_receipt" || return
    fi
  fi

  if [[ -d "$PGDATA" ]] && \
     "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_verify_retained_identity
    basic_cleanup_appledouble_sidecars
    basic_quiesce_application
    fence_runtime_roles
    basic_assert_no_database_clients
    basic_assert_no_cluster_clients
    if [[ ! -e "$quarantine_directory" ]] && \
       [[ ! -L "$quarantine_directory" ]]; then
      if [[ "$pre_finalization_rollback" == "true" ]]; then
        require_interrupted_commit_live_revision || return
      else
        basic_require_exact_revision "$CARESYNC_RETAINED_TARGET_REVISION"
      fi
    else
      basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"
    fi
    basic_stop_retained_postgres
  elif [[ -f "$PGDATA/postmaster.pid" ]]; then
    basic_fail \
      "Rollback found retained PostgreSQL running but could not prove its identity"
    return
  fi
  advance_rollback_fence \
    rollback_retained_stopped \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt"

  local expected_data_directory expected_system_identifier
  expected_data_directory="$(
    sed -n 's/^data_directory=//p' "$RETAINED_IDENTITY_FILE"
  )"
  expected_system_identifier="$(
    sed -n 's/^system_identifier=//p' "$RETAINED_IDENTITY_FILE"
  )"
  if [[ -z "$expected_data_directory" ]] || \
     [[ "$(cd "$(dirname "$PGDATA")" && pwd -P)/$(basename "$PGDATA")" != \
          "$expected_data_directory" ]] || \
     [[ ! "$expected_system_identifier" =~ ^[0-9]+$ ]] || \
     [[ "$(basic_postgres_control_system_identifier "$PHYSICAL_BACKUP_PATH")" != \
          "$expected_system_identifier" ]]; then
    basic_fail "Physical backup control identity differs from retained identity"
    return
  fi
  if [[ -f "$PHYSICAL_BACKUP_PATH/postmaster.pid" ]]; then
    basic_fail "Physical backup evidence unexpectedly contains postmaster.pid"
    return
  fi
  local require_clean_quarantine=true
  if [[ "$pre_finalization_rollback" == "true" ]]; then
    require_clean_quarantine=false
  fi

  if [[ -d "$PGDATA" ]] && [[ -d "$quarantine_directory" ]] && \
     { [[ -e "$partial_directory" ]] || [[ -L "$partial_directory" ]]; }; then
    basic_fail "Rollback found an ambiguous extra partial beside both retained trees"
    return
  fi
  if [[ ! -e "$PGDATA" ]] && [[ ! -L "$PGDATA" ]] && \
     [[ ! -e "$quarantine_directory" ]] && \
     [[ ! -L "$quarantine_directory" ]]; then
    basic_fail "Rollback cannot locate either the retained or quarantined PGDATA"
    return
  fi
  if [[ -e "$partial_directory" ]] || [[ -L "$partial_directory" ]]; then
    if [[ -L "$partial_directory" ]] || [[ ! -d "$partial_directory" ]]; then
      basic_fail "Rollback partial path is not a safe directory"
      return
    fi
    if ! verify_rollback_copy_matches_backup \
      "$partial_directory" "$expected_system_identifier"; then
      preserve_incomplete_rollback_copy \
        "$partial_directory" "$quarantine_parent" "$run_key" || return
    fi
  fi
  if [[ ! -e "$partial_directory" ]] && [[ ! -L "$partial_directory" ]] && \
     { [[ ! -d "$PGDATA" ]] || [[ ! -d "$quarantine_directory" ]]; }; then
    basic_materialize_physical_copy \
      "$PHYSICAL_BACKUP_PATH" \
      "$partial_directory" \
      "rollback physical restore"
  fi
  if [[ -d "$partial_directory" ]]; then
    verify_rollback_copy_matches_backup \
      "$partial_directory" "$expected_system_identifier" || return
    durability_barrier_private_tree "$partial_directory" || return
    basic_require_same_apfs_device \
      "$(dirname "$PGDATA")" "$partial_directory" || return
    advance_rollback_fence \
      rollback_copy_verified \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt" || return
  fi

  if [[ -d "$PGDATA" ]] && [[ ! -e "$quarantine_directory" ]] && \
     [[ ! -L "$quarantine_directory" ]]; then
    if [[ ! -d "$partial_directory" ]]; then
      basic_fail "Rollback has no verified partial restore to promote"
      return
    fi
    # The rename boundary gets its own complete re-open. Nothing below this
    # line trusts evidence verified only before PostgreSQL was stopped.
    if [[ "$pre_finalization_rollback" == "true" ]]; then
      require_interrupted_commit_recovery_evidence \
        "$run_directory" "$candidate_receipt" || return
    else
      verify_static_artifacts || return
      backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
        python scripts/basic_release_contract.py verify-finalization-receipt \
          --candidate-receipt "$candidate_receipt" \
          --clone-certificate "$CLONE_CERTIFICATE" \
          --release-payload "$RELEASE_PAYLOAD" \
          "${CONTRACT_ARTIFACT_ARGS[@]}" \
          --commit-receipt "$commit_receipt" \
          --receipt "$finalization_receipt" || return
    fi
    verify_rollback_copy_matches_backup \
      "$partial_directory" "$expected_system_identifier" || return
    durability_barrier_private_tree "$partial_directory" || return
    durability_barrier_private_tree "$PGDATA" || return
    verify_stopped_pinned_postgres_tree \
      "$PGDATA" "$expected_system_identifier" \
      "$require_clean_quarantine" || return
    if [[ "$pre_finalization_rollback" != "true" ]]; then
      create_stopped_0042_evidence \
        "$run_directory" \
        "$candidate_receipt" \
        "$commit_receipt" \
        "$finalization_receipt" \
        "$expected_data_directory" \
        "$expected_system_identifier" || return
      verify_stopped_0042_evidence \
        "$run_directory" \
        "$candidate_receipt" \
        "$commit_receipt" \
        "$finalization_receipt" \
        "$expected_data_directory" \
        "$expected_system_identifier" || return
    fi
    # Last possible checks at the atomic rename boundary.
    verify_stopped_pinned_postgres_tree \
      "$PGDATA" "$expected_system_identifier" \
      "$require_clean_quarantine" || return
    if "$PG_BIN/pg_ctl" -D "$partial_directory" status >/dev/null 2>&1 || \
       [[ -f "$partial_directory/postmaster.pid" ]] || \
       [[ "$(basic_postgres_control_system_identifier "$partial_directory")" != \
            "$expected_system_identifier" ]]; then
      basic_fail "A PostgreSQL tree changed at the rollback rename boundary"
      return
    fi
    basic_require_release_apfs_topology \
      "$PHYSICAL_BACKUP_PATH" "$quarantine_parent" || return
    basic_require_same_apfs_device \
      "$partial_directory" "$PGDATA" || return
    atomic_rollback_rename_no_replace \
      "$PGDATA" "$quarantine_directory" || return
    durability_barrier_private_tree "$quarantine_directory" || return
    advance_rollback_fence \
      rollback_quarantined \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt" || return
  fi
  if [[ -d "$quarantine_directory" ]]; then
    if [[ "$pre_finalization_rollback" == "true" ]]; then
      verify_interrupted_commit_quarantine \
        "$quarantine_directory" "$expected_system_identifier" || return
    else
      verify_quarantined_0042 \
        "$run_directory" \
        "$candidate_receipt" \
        "$commit_receipt" \
        "$finalization_receipt" \
        "$quarantine_directory" \
        "$expected_data_directory" \
        "$expected_system_identifier" || return
    fi
    durability_barrier_private_tree "$quarantine_directory" || return
    advance_rollback_fence \
      rollback_quarantined \
      "$run_directory" \
      "$candidate_receipt" \
      "$commit_receipt" \
      "$finalization_receipt" || return
  fi
  if [[ ! -e "$PGDATA" ]] && [[ -d "$quarantine_directory" ]] && \
     [[ -d "$partial_directory" ]]; then
    # Reopen the entire release chain again at the second atomic boundary.
    if [[ "$pre_finalization_rollback" == "true" ]]; then
      require_interrupted_commit_recovery_evidence \
        "$run_directory" "$candidate_receipt" || return
      verify_interrupted_commit_quarantine \
        "$quarantine_directory" "$expected_system_identifier" || return
    else
      verify_static_artifacts || return
      backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
        python scripts/basic_release_contract.py verify-finalization-receipt \
          --candidate-receipt "$candidate_receipt" \
          --clone-certificate "$CLONE_CERTIFICATE" \
          --release-payload "$RELEASE_PAYLOAD" \
          "${CONTRACT_ARTIFACT_ARGS[@]}" \
          --commit-receipt "$commit_receipt" \
          --receipt "$finalization_receipt" || return
      verify_quarantined_0042 \
        "$run_directory" \
        "$candidate_receipt" \
        "$commit_receipt" \
        "$finalization_receipt" \
        "$quarantine_directory" \
        "$expected_data_directory" \
        "$expected_system_identifier" || return
    fi
    verify_rollback_copy_matches_backup \
      "$partial_directory" "$expected_system_identifier" || return
    durability_barrier_private_tree "$partial_directory" || return
    basic_require_same_apfs_device \
      "$(dirname "$PGDATA")" "$partial_directory" || return
    basic_require_release_apfs_topology \
      "$PHYSICAL_BACKUP_PATH" "$quarantine_parent" || return
    atomic_rollback_rename_no_replace \
      "$partial_directory" "$PGDATA" || return
    durability_barrier_private_tree "$PGDATA" || return
  fi
  if [[ ! -d "$PGDATA" ]] || [[ ! -d "$quarantine_directory" ]] || \
     [[ -e "$partial_directory" ]] || [[ -L "$partial_directory" ]]; then
    basic_fail \
      "Rollback filesystem state is incomplete or ambiguous; evidence was preserved"
    return
  fi
  basic_require_safe_postgres_tree \
    "$PGDATA" "restored retained PostgreSQL" || return
  basic_require_safe_postgres_tree \
    "$quarantine_directory" \
    "quarantined 0042 PostgreSQL"
  if [[ "$(basic_postgres_control_system_identifier "$PGDATA")" != \
        "$expected_system_identifier" ]]; then
    basic_fail "Restored PGDATA has the wrong PostgreSQL system identifier"
    return
  fi
  durability_barrier_private_tree "$PGDATA" || return
  durability_barrier_private_tree "$quarantine_directory" || return
  local rollback_status
  rollback_status="$(rollback_context_value status)"
  if [[ "$rollback_status" != "rollback_starting" ]]; then
    # The promoted copy has not been authorized to boot yet, so it must remain
    # byte-for-byte equal to the complete physical-backup inventory.
    verify_rollback_copy_matches_backup \
      "$PGDATA" "$expected_system_identifier"
  fi
  advance_rollback_fence \
    rollback_restored \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt"

  # Persist that recovery may now mutate pg_control/WAL before the first boot.
  # A retry in this state proves exact 0039 business/source authorization
  # instead of incorrectly demanding the preboot byte inventory.
  advance_rollback_fence \
    rollback_starting \
    "$run_directory" \
    "$candidate_receipt" \
    "$commit_receipt" \
    "$finalization_receipt"
  basic_start_postgres
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"
  basic_require_runtime_roles_fenced
  basic_assert_no_database_clients
  if [[ ! -f "$rollback_authorization" ]]; then
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/basic_release_contract.py certify-resume-0039 \
        --candidate-receipt "$candidate_receipt" \
        --clone-certificate "$CLONE_CERTIFICATE" \
        --release-payload "$RELEASE_PAYLOAD" \
        "${CONTRACT_ARTIFACT_ARGS[@]}" \
        --authorization "$rollback_authorization"
  fi
  if ! backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-resume-authorization \
      --candidate-receipt "$candidate_receipt" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --authorization "$rollback_authorization"; then
    if [[ "$rollback_was_reactivated" == "true" ]]; then
      invalidate_reactivated_rollback_start \
        "$run_directory" "$candidate_receipt" \
        "$commit_receipt" "$finalization_receipt" \
        "$rollback_authorization" || return
      basic_fail \
        "Retired rollback source changed after finalization; the old rollback was safely retired."
    fi
    return 1
  fi
  arm_controlled_runtime_window_cleanup
  CONTROLLED_RUNTIME_WINDOW_OPEN=true
  require_release_probe_contract nologin || return
  open_release_probe_for_controlled_health || return
  prove_release_probe_write_rejection_or_close \
    "$RELEASE_PROBE_CREDENTIAL" || return
  if ! CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}" \
    /bin/bash "$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh" \
    --rollback-0039 \
    --receipt "$candidate_receipt" \
    --authorization "$rollback_authorization"; then
    if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
       [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
      if fence_runtime_roles; then
        CONTROLLED_RUNTIME_WINDOW_OPEN=false
      fi
    else
      if close_retired_controlled_runtime_after_child_failure; then
        CONTROLLED_RUNTIME_WINDOW_OPEN=false
      fi
    fi
    return 1
  fi
  CONTROLLED_RUNTIME_WINDOW_FINALIZED=true
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  disarm_controlled_runtime_window_cleanup
  if [[ "$new_rollback" == "true" ]]; then
    printf '%s\n' \
      "Emergency rollback completed; exact 0039 resumed." \
      "Quarantined 0042 PGDATA: $quarantine_directory"
  fi
}

load_release_run() {
  local candidate_receipt="$1"
  candidate_receipt="$(cd "$(dirname "$candidate_receipt")" && pwd)/$(basename "$candidate_receipt")"
  if [[ ! -f "$candidate_receipt" ]] || \
     [[ "$(basename "$candidate_receipt")" != "candidate-receipt.json" ]]; then
    basic_fail "Candidate receipt is missing or has an unexpected name"
    return
  fi
  ACTIVE_CANDIDATE_RECEIPT="$candidate_receipt"
  ACTIVE_RUN_DIRECTORY="$(dirname "$candidate_receipt")"
  discover_artifacts "$ACTIVE_RUN_DIRECTORY" || return
  if [[ "$candidate_receipt" != "$CANDIDATE_RECEIPT" ]]; then
    basic_fail "Candidate receipt does not belong to its release run"
    return
  fi
  require_matching_fence \
    "$ACTIVE_RUN_DIRECTORY" "$candidate_receipt" || return
  build_contract_artifact_args || return
}

preflight_controlled_start() {
  local kind="$1"
  local candidate_receipt="$2"
  local authorization="$3"
  candidate_receipt="$(
    cd "$(dirname "$candidate_receipt")" && pwd
  )/$(basename "$candidate_receipt")" || return
  local run_directory="$(dirname "$candidate_receipt")"
  discover_artifacts "$run_directory" || return
  if [[ "$candidate_receipt" != "$CANDIDATE_RECEIPT" ]]; then
    basic_fail "Controlled startup candidate is outside its release run"
    return
  fi
  reexec_release_from_captured_source_if_needed \
    "$run_directory" _preflight-controlled-start \
    "$kind" "$candidate_receipt" "$authorization" || return
  build_contract_artifact_args || return
  bootstrap_verify_captured_release_source "$run_directory" || return
  case "$kind" in
    commit)
      require_matching_fence "$run_directory" "$candidate_receipt" || return
      if [[ "$authorization" != "$COMMIT_RECEIPT" ]] || \
         [[ ! -f "$authorization" ]]; then
        basic_fail "Controlled commit receipt is missing"
        return
      fi
      ;;
    resume)
      require_matching_fence "$run_directory" "$candidate_receipt" || return
      if [[ "$authorization" != "$RESUME_AUTHORIZATION" ]] || \
         [[ ! -f "$authorization" ]]; then
        basic_fail "Controlled resume authorization is missing"
        return
      fi
      ;;
    rollback)
      local context="$RELEASE_FENCE_DIRECTORY/context"
      local rollback_commit rollback_finalization
      rollback_commit="$(private_context_value "$context" commit_receipt)" \
        || return
      rollback_finalization="$(
        private_context_value "$context" finalization_receipt
      )" || return
      require_matching_rollback_fence \
        "$run_directory" "$candidate_receipt" \
        "$rollback_commit" "$rollback_finalization" || return
      if [[ "$authorization" != "$ROLLBACK_AUTHORIZATION" ]] || \
         [[ ! -f "$authorization" ]] || \
         [[ "$(private_context_value "$context" authorization)" != \
            "$authorization" ]]; then
        basic_fail "Controlled rollback authorization is missing"
        return
      fi
      ;;
    *)
      basic_fail "Unknown controlled startup kind"
      return
      ;;
  esac
}

preflight_normal_start() {
  basic_require_no_release_fence || return
  if [[ -e "$REACTIVATION_PENDING" ]] || [[ -L "$REACTIVATION_PENDING" ]]; then
    basic_fail \
      "Ordinary startup is blocked by an incomplete release-fence reactivation"
    return
  fi
  preflight_pending_post_retirement_role_restoration || return
  if [[ -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] || \
     [[ -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
    if [[ "$PENDING_ROLE_RESTORATION_SOURCE_ROOT" != "none" ]]; then
      if [[ "$ROOT" != "$PENDING_ROLE_RESTORATION_SOURCE_ROOT" ]]; then
        basic_fail \
          "Pending role restoration must execute from its captured release source"
        return
      fi
      local pending_manifest_sha
      pending_manifest_sha="$(
        private_context_value "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" \
          release_source_manifest_sha256
      )" || return
      if [[ "$PENDING_ROLE_RESTORATION_OPERATION" == "prepare-abort" ]]; then
        bootstrap_verify_pre_candidate_source \
          "$PENDING_ROLE_RESTORATION_RUN" "$pending_manifest_sha" || return
      else
        bootstrap_verify_captured_release_source \
          "$PENDING_ROLE_RESTORATION_RUN" "$pending_manifest_sha" || return
      fi
    fi
    return 0
  fi
  if [[ ! -e "$ACTIVE_RELEASE_EPOCH_FILE" ]] || \
     [[ -L "$ACTIVE_RELEASE_EPOCH_FILE" ]]; then
    basic_fail "Ordinary startup requires a completed active release epoch"
    return
  fi
  require_active_runtime_epoch_chain || return
  local kind run_directory revision completion predecessor
  kind="$(private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" kind)" || return
  run_directory="$(
    private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" run_directory
  )" || return
  revision="$(
    private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" revision
  )" || return
  completion="$(
    private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" completion_evidence
  )" || return
  predecessor="$(
    private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" \
      predecessor_epoch_sha256
  )" || return
  discover_artifacts "$run_directory" || return
  reexec_release_from_captured_source_if_needed \
    "$run_directory" _preflight-normal-start || return
  build_contract_artifact_args || return
  verify_static_artifacts || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-prepare-receipt \
      --receipt "$CANDIDATE_RECEIPT" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" || return
  case "$kind" in
    commit)
      require_matching_retired_prepared_fence \
        "$run_directory" "$CANDIDATE_RECEIPT" || return
      require_startup_evidence \
        commit complete "$run_directory" "$CANDIDATE_RECEIPT" \
        "$COMMIT_RECEIPT" "$run_directory/fence-retired/context" \
        "$CARESYNC_RETAINED_TARGET_REVISION" || return
      require_exact_active_runtime_epoch \
        commit "$run_directory" "$CANDIDATE_RECEIPT" "$COMMIT_RECEIPT" \
        "$FINALIZATION_RECEIPT" "$completion" \
        "$run_directory/fence-retired/context" \
        "$CARESYNC_RETAINED_TARGET_REVISION" "$predecessor" || return
      ;;
    resume)
      require_matching_retired_prepared_fence \
        "$run_directory" "$CANDIDATE_RECEIPT" || return
      require_startup_evidence \
        resume complete "$run_directory" "$CANDIDATE_RECEIPT" \
        "$RESUME_AUTHORIZATION" "$run_directory/fence-retired/context" \
        "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      require_exact_active_runtime_epoch \
        resume "$run_directory" "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION" \
        none "$completion" "$run_directory/fence-retired/context" \
        "$CARESYNC_RETAINED_SOURCE_REVISION" "$predecessor" || return
      ;;
    rollback)
      local rollback_context="$run_directory/rollback-fence-retired/context"
      local rollback_commit rollback_finalization
      rollback_commit="$(
        private_context_value "$rollback_context" commit_receipt
      )" || return
      rollback_finalization="$(
        private_context_value "$rollback_context" finalization_receipt
      )" || return
      require_startup_evidence \
        rollback complete "$run_directory" "$CANDIDATE_RECEIPT" \
        "$ROLLBACK_AUTHORIZATION" "$rollback_context" \
        "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      require_exact_active_runtime_epoch \
        rollback "$run_directory" "$CANDIDATE_RECEIPT" \
        "$ROLLBACK_AUTHORIZATION" "$rollback_finalization" "$completion" \
        "$rollback_context" "$CARESYNC_RETAINED_SOURCE_REVISION" \
        "$predecessor" || return
      ;;
    *)
      basic_fail "Active release epoch has an unknown startup kind"
      return
      ;;
  esac
  if [[ "$revision" != "$(
    private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" revision
  )" ]]; then
    basic_fail "Active release epoch revision changed during preflight"
    return
  fi
}

load_rollback_run() {
  local candidate_receipt="$1"
  candidate_receipt="$(
    cd "$(dirname "$candidate_receipt")" && pwd
  )/$(basename "$candidate_receipt")"
  if [[ ! -f "$candidate_receipt" ]] || \
     [[ "$(basename "$candidate_receipt")" != "candidate-receipt.json" ]]; then
    basic_fail "Rollback candidate receipt is missing or has an unexpected name"
    return
  fi
  ACTIVE_CANDIDATE_RECEIPT="$candidate_receipt"
  ACTIVE_RUN_DIRECTORY="$(dirname "$candidate_receipt")"
  discover_artifacts "$ACTIVE_RUN_DIRECTORY" || return
  if [[ "$candidate_receipt" != "$CANDIDATE_RECEIPT" ]]; then
    basic_fail "Rollback candidate receipt does not belong to its release run"
    return
  fi
  ACTIVE_COMMIT_RECEIPT="$(rollback_context_value commit_receipt)" || return
  ACTIVE_FINALIZATION_RECEIPT="$(
    rollback_context_value finalization_receipt
  )" || return
  require_matching_rollback_fence \
    "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_CANDIDATE_RECEIPT" \
    "$ACTIVE_COMMIT_RECEIPT" \
    "$ACTIVE_FINALIZATION_RECEIPT" || return
  build_contract_artifact_args || return
}

verify_rollback_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  load_rollback_run "$candidate_receipt" || return
  authorization="$(
    cd "$(dirname "$authorization")" && pwd
  )/$(basename "$authorization")" || return
  if [[ "$authorization" != "$ROLLBACK_AUTHORIZATION" ]] || \
     [[ "$authorization" != "$(rollback_context_value authorization)" ]] || \
     [[ ! -f "$authorization" ]] || \
     ! grep -Fqx "status=rollback_starting" \
       "$RELEASE_FENCE_DIRECTORY/context"; then
    basic_fail "Rollback startup authorization or fence state is invalid"
    return
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  if [[ "$ACTIVE_FINALIZATION_RECEIPT" == "none" ]]; then
    if [[ "$ACTIVE_COMMIT_RECEIPT" != "$COMMIT_ATTEMPT_INTENT" ]]; then
      basic_fail "Interrupted rollback journal has the wrong commit intent"
      return
    fi
    require_interrupted_commit_recovery_evidence \
      "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" || return
  else
    verify_static_artifacts || return
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/basic_release_contract.py verify-finalization-receipt \
        --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
        --clone-certificate "$CLONE_CERTIFICATE" \
        --release-payload "$RELEASE_PAYLOAD" \
        "${CONTRACT_ARTIFACT_ARGS[@]}" \
        --commit-receipt "$ACTIVE_COMMIT_RECEIPT" \
        --receipt "$ACTIVE_FINALIZATION_RECEIPT" || return
  fi
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-resume-authorization \
      --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --authorization "$authorization" || return
  local quarantine_directory
  quarantine_directory="$(rollback_context_value quarantine_directory)"
  local expected_data_directory expected_system_identifier
  expected_data_directory="$(
    sed -n 's/^data_directory=//p' "$RETAINED_IDENTITY_FILE"
  )"
  expected_system_identifier="$(
    sed -n 's/^system_identifier=//p' "$RETAINED_IDENTITY_FILE"
  )"
  if [[ "$ACTIVE_FINALIZATION_RECEIPT" == "none" ]]; then
    verify_interrupted_commit_quarantine \
      "$quarantine_directory" "$expected_system_identifier" || return
  else
    verify_quarantined_0042 \
      "$ACTIVE_RUN_DIRECTORY" \
      "$ACTIVE_CANDIDATE_RECEIPT" \
      "$ACTIVE_COMMIT_RECEIPT" \
      "$ACTIVE_FINALIZATION_RECEIPT" \
      "$quarantine_directory" \
      "$expected_data_directory" \
      "$expected_system_identifier" || return
  fi
}

finalize_rollback_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  verify_rollback_start "$candidate_receipt" "$authorization" || return
  curl -fsS http://127.0.0.1:3002/api/v1/health >/dev/null || return
  curl -fsS http://127.0.0.1:5174/ >/dev/null || return
  require_matching_rollback_fence \
    "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_CANDIDATE_RECEIPT" \
    "$ACTIVE_COMMIT_RECEIPT" \
    "$ACTIVE_FINALIZATION_RECEIPT" || return
  basic_quiesce_application || return
  close_release_probe_after_controlled_health || return
  basic_assert_no_cluster_clients || return
  basic_require_runtime_roles_fenced || return
  # Re-open the captured execution closure after the health processes have
  # exited. No epoch or fence transition may trust only a pre-execution hash.
  verify_static_artifacts || return
  verify_rollback_start "$candidate_receipt" "$authorization" || return
  local context="$RELEASE_FENCE_DIRECTORY/context"
  local completion
  completion="$(
    startup_evidence_path "$ACTIVE_RUN_DIRECTORY" rollback complete
  )" || return
  create_startup_evidence \
    rollback complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  publish_active_runtime_epoch \
    rollback "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$ACTIVE_FINALIZATION_RECEIPT" "$completion" "$context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  prepare_post_retirement_role_restoration \
    rollback-complete "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  remove_matching_rollback_fence \
    "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_CANDIDATE_RECEIPT" \
    "$ACTIVE_COMMIT_RECEIPT" \
    "$ACTIVE_FINALIZATION_RECEIPT" || return
  complete_post_retirement_role_restoration \
    rollback-complete "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  require_startup_evidence \
    rollback complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  require_exact_active_runtime_epoch \
    rollback "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$ACTIVE_FINALIZATION_RECEIPT" "$completion" \
    "$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" \
    "$(private_context_value "$completion" predecessor_epoch_sha256)" || return
}

verify_resume_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  load_release_run "$candidate_receipt" || return
  authorization="$(
    cd "$(dirname "$authorization")" && pwd
  )/$(basename "$authorization")" || return
  if [[ "$authorization" != "$RESUME_AUTHORIZATION" ]] || [[ ! -f "$authorization" ]]; then
    basic_fail "Resume authorization does not belong to this release run"
    return
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-resume-authorization \
      --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --authorization "$authorization" || return
}

finalize_resume_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  verify_resume_start "$candidate_receipt" "$authorization" || return
  curl -fsS http://127.0.0.1:3002/api/v1/health >/dev/null || return
  curl -fsS http://127.0.0.1:5174/ >/dev/null || return
  require_matching_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" || return
  basic_quiesce_application || return
  close_release_probe_after_controlled_health || return
  basic_assert_no_cluster_clients || return
  basic_require_runtime_roles_fenced || return
  verify_static_artifacts || return
  verify_resume_start "$candidate_receipt" "$authorization" || return
  local context="$RELEASE_FENCE_DIRECTORY/context"
  local completion
  completion="$(
    startup_evidence_path "$ACTIVE_RUN_DIRECTORY" resume complete
  )" || return
  create_startup_evidence \
    resume complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  publish_active_runtime_epoch \
    resume "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" none "$completion" "$context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  prepare_post_retirement_role_restoration \
    resume-complete "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  remove_matching_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" || return
  complete_post_retirement_role_restoration \
    resume-complete "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  require_startup_evidence \
    resume complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  require_exact_active_runtime_epoch \
    resume "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" none "$completion" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" \
    "$(private_context_value "$completion" predecessor_epoch_sha256)" || return
}

verify_commit_start() {
  local candidate_receipt="$1"
  local commit_receipt="$2"
  load_release_run "$candidate_receipt" || return
  commit_receipt="$(
    cd "$(dirname "$commit_receipt")" && pwd
  )/$(basename "$commit_receipt")" || return
  if [[ "$commit_receipt" != "$COMMIT_RECEIPT" ]] || [[ ! -f "$commit_receipt" ]]; then
    basic_fail "Commit receipt does not belong to this release run"
    return
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_TARGET_REVISION" || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-live-commit \
      --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --commit-receipt "$commit_receipt" || return
}

verify_commit_start_in_bounded_probe_window() {
  local candidate_receipt="$1"
  local commit_receipt="$2"
  local proof_succeeded=false
  local verified=false

  # The controlled health runtime has already been quiesced and its probe
  # closed. Reopen only the exact column-scoped probe needed by the runtime
  # certificate, then close it again before any epoch or fence transition.
  open_release_probe_for_controlled_health || return
  prove_release_probe_write_rejection_or_close \
    "$RELEASE_PROBE_CREDENTIAL" && proof_succeeded=true
  if [[ "$proof_succeeded" != "true" ]]; then
    close_release_probe_after_controlled_health || true
    return 1
  fi
  if verify_commit_start "$candidate_receipt" "$commit_receipt"; then
    verified=true
  fi
  close_release_probe_after_controlled_health || return
  if [[ "$verified" != "true" ]]; then
    return 1
  fi
}

finalize_commit_start() {
  local candidate_receipt="$1"
  local commit_receipt="$2"
  verify_commit_start "$candidate_receipt" "$commit_receipt" || return
  curl -fsS http://127.0.0.1:3002/api/v1/health >/dev/null || return
  curl -fsS http://127.0.0.1:5174/ >/dev/null || return
  if [[ ! -f "$FINALIZATION_RECEIPT" ]]; then
    backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
      python scripts/basic_release_contract.py finalize-live \
        --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
        --clone-certificate "$CLONE_CERTIFICATE" \
        --release-payload "$RELEASE_PAYLOAD" \
        "${CONTRACT_ARTIFACT_ARGS[@]}" \
        --commit-receipt "$COMMIT_RECEIPT" \
        --receipt "$FINALIZATION_RECEIPT" || return
  fi
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-finalization-receipt \
      --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --commit-receipt "$COMMIT_RECEIPT" \
      --receipt "$FINALIZATION_RECEIPT" || return
  require_matching_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" || return
  basic_quiesce_application || return
  close_release_probe_after_controlled_health || return
  basic_assert_no_cluster_clients || return
  basic_require_runtime_roles_fenced || return
  verify_static_artifacts || return
  verify_commit_start_in_bounded_probe_window \
    "$candidate_receipt" "$commit_receipt" || return
  basic_assert_no_cluster_clients || return
  basic_require_runtime_roles_fenced || return
  backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
    python scripts/basic_release_contract.py verify-finalization-receipt \
      --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
      --clone-certificate "$CLONE_CERTIFICATE" \
      --release-payload "$RELEASE_PAYLOAD" \
      "${CONTRACT_ARTIFACT_ARGS[@]}" \
      --commit-receipt "$COMMIT_RECEIPT" \
      --receipt "$FINALIZATION_RECEIPT" || return
  local context="$RELEASE_FENCE_DIRECTORY/context"
  local completion
  completion="$(
    startup_evidence_path "$ACTIVE_RUN_DIRECTORY" commit complete
  )" || return
  create_startup_evidence \
    commit complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$commit_receipt" "$context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" || return
  publish_active_runtime_epoch \
    commit "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$commit_receipt" "$FINALIZATION_RECEIPT" "$completion" "$context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" || return
  prepare_post_retirement_role_restoration \
    commit-complete "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" || return
  remove_matching_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" || return
  complete_post_retirement_role_restoration \
    commit-complete "$ACTIVE_RUN_DIRECTORY" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" || return
  require_startup_evidence \
    commit complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$commit_receipt" "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" || return
  require_exact_active_runtime_epoch \
    commit "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$commit_receipt" "$FINALIZATION_RECEIPT" "$completion" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" \
    "$(private_context_value "$completion" predecessor_epoch_sha256)" || return
}

load_retired_prepared_run() {
  local candidate_receipt="$1"
  candidate_receipt="$(
    cd "$(dirname "$candidate_receipt")" && pwd
  )/$(basename "$candidate_receipt")"
  if [[ ! -f "$candidate_receipt" ]] || \
     [[ "$(basename "$candidate_receipt")" != "candidate-receipt.json" ]]; then
    basic_fail "Retired startup candidate receipt is missing"
    return
  fi
  ACTIVE_CANDIDATE_RECEIPT="$candidate_receipt"
  ACTIVE_RUN_DIRECTORY="$(dirname "$candidate_receipt")"
  discover_artifacts "$ACTIVE_RUN_DIRECTORY" || return
  if [[ "$candidate_receipt" != "$CANDIDATE_RECEIPT" ]]; then
    basic_fail "Retired startup candidate does not belong to its release run"
    return
  fi
  require_matching_retired_prepared_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" || return
  build_contract_artifact_args
}

complete_resume_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  load_retired_prepared_run "$candidate_receipt" || return
  authorization="$(
    cd "$(dirname "$authorization")" && pwd
  )/$(basename "$authorization")"
  if [[ "$authorization" != "$RESUME_AUTHORIZATION" ]]; then
    basic_fail "Resume completion authorization is outside its release run"
    return
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  local completion predecessor
  completion="$(startup_evidence_path \
    "$ACTIVE_RUN_DIRECTORY" resume complete)" || return
  require_startup_evidence \
    resume complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  predecessor="$(
    private_context_value "$completion" predecessor_epoch_sha256
  )" || return
  require_exact_active_runtime_epoch \
    resume "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" none "$completion" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" "$predecessor" || return
}

complete_commit_start() {
  local candidate_receipt="$1"
  local commit_receipt="$2"
  load_retired_prepared_run "$candidate_receipt" || return
  commit_receipt="$(
    cd "$(dirname "$commit_receipt")" && pwd
  )/$(basename "$commit_receipt")"
  if [[ "$commit_receipt" != "$COMMIT_RECEIPT" ]]; then
    basic_fail "Commit completion receipt is outside its release run"
    return
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_TARGET_REVISION" || return
  local completion predecessor
  completion="$(startup_evidence_path \
    "$ACTIVE_RUN_DIRECTORY" commit complete)" || return
  require_startup_evidence \
    commit complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$commit_receipt" "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" || return
  predecessor="$(
    private_context_value "$completion" predecessor_epoch_sha256
  )" || return
  require_exact_active_runtime_epoch \
    commit "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$commit_receipt" "$FINALIZATION_RECEIPT" "$completion" \
    "$ACTIVE_RUN_DIRECTORY/fence-retired/context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" "$predecessor" || return
}

load_retired_rollback_run() {
  local candidate_receipt="$1"
  candidate_receipt="$(
    cd "$(dirname "$candidate_receipt")" && pwd
  )/$(basename "$candidate_receipt")"
  if [[ ! -f "$candidate_receipt" ]]; then
    basic_fail "Retired rollback candidate receipt is missing"
    return
  fi
  ACTIVE_CANDIDATE_RECEIPT="$candidate_receipt"
  ACTIVE_RUN_DIRECTORY="$(dirname "$candidate_receipt")"
  discover_artifacts "$ACTIVE_RUN_DIRECTORY" || return
  local retired_context="$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context"
  ACTIVE_COMMIT_RECEIPT="$(
    private_context_value "$retired_context" commit_receipt
  )" || return
  ACTIVE_FINALIZATION_RECEIPT="$(
    private_context_value "$retired_context" finalization_receipt
  )" || return
  local quarantine_directory partial_directory
  quarantine_directory="$(
    private_context_value "$retired_context" quarantine_directory
  )" || return
  partial_directory="$(
    private_context_value "$retired_context" partial_directory
  )" || return
  require_matching_retired_rollback_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$ACTIVE_COMMIT_RECEIPT" "$ACTIVE_FINALIZATION_RECEIPT" \
    "$ROLLBACK_AUTHORIZATION" "$quarantine_directory" \
    "$partial_directory" || return
  build_contract_artifact_args
}

complete_rollback_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  load_retired_rollback_run "$candidate_receipt" || return
  authorization="$(
    cd "$(dirname "$authorization")" && pwd
  )/$(basename "$authorization")"
  if [[ "$authorization" != "$ROLLBACK_AUTHORIZATION" ]]; then
    basic_fail "Rollback completion authorization is outside its release run"
    return
  fi
  basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  local completion predecessor
  completion="$(startup_evidence_path \
    "$ACTIVE_RUN_DIRECTORY" rollback complete)" || return
  require_startup_evidence \
    rollback complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" || return
  predecessor="$(
    private_context_value "$completion" predecessor_epoch_sha256
  )" || return
  require_exact_active_runtime_epoch \
    rollback "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$authorization" "$ACTIVE_FINALIZATION_RECEIPT" "$completion" \
    "$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context" \
    "$CARESYNC_RETAINED_SOURCE_REVISION" "$predecessor" || return
}

recover_incomplete_resume_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    load_release_run "$candidate_receipt" || return
    authorization="$(
      cd "$(dirname "$authorization")" && pwd
    )/$(basename "$authorization")" || return
    if [[ "$authorization" != "$RESUME_AUTHORIZATION" ]]; then
      basic_fail "Resume recovery authorization is outside its release run"
      return
    fi
    basic_verify_retained_identity || return
    fence_runtime_roles || return
    basic_quiesce_application || return
    basic_assert_no_cluster_clients || return
    local active_invalidated
    active_invalidated="$(
      startup_evidence_path "$ACTIVE_RUN_DIRECTORY" resume invalidated
    )" || return
    if [[ -e "$active_invalidated" ]] || \
       [[ -L "$active_invalidated" ]]; then
      require_startup_evidence \
        resume invalidated "$ACTIVE_RUN_DIRECTORY" \
        "$ACTIVE_CANDIDATE_RECEIPT" "$authorization" \
        "$RELEASE_FENCE_DIRECTORY/context" \
        "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      arm_controlled_runtime_window_cleanup
      CONTROLLED_RUNTIME_WINDOW_OPEN=true
      invalidate_reactivated_prepared_start \
        resume "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
        "$authorization" "$CARESYNC_RETAINED_SOURCE_REVISION" || return
    fi
    return
  fi
  load_retired_prepared_run "$candidate_receipt" || return
  authorization="$(
    cd "$(dirname "$authorization")" && pwd
  )/$(basename "$authorization")"
  local context="$ACTIVE_RUN_DIRECTORY/fence-retired/context"
  local evidence
  for evidence in \
    "$(startup_evidence_path "$ACTIVE_RUN_DIRECTORY" resume complete)" \
    "$(startup_evidence_path "$ACTIVE_RUN_DIRECTORY" resume invalidated)"; do
    if [[ -e "$evidence" ]] || [[ -L "$evidence" ]]; then
      local outcome="${evidence##*-startup-}"
      outcome="${outcome%.evidence}"
      require_startup_evidence \
        resume "$outcome" "$ACTIVE_RUN_DIRECTORY" \
        "$ACTIVE_CANDIDATE_RECEIPT" "$authorization" "$context" \
        "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      if [[ "$outcome" == "complete" ]]; then
        complete_resume_start "$candidate_receipt" "$authorization" || return
      fi
      return
    fi
  done
  arm_controlled_runtime_window_cleanup
  CONTROLLED_RUNTIME_WINDOW_OPEN=true
  reactivate_retired_prepared_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" || return
  basic_verify_retained_identity || return
  fence_runtime_roles || return
  basic_quiesce_application || return
  basic_assert_no_cluster_clients || return
  if ! basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || \
     ! verify_static_artifacts || \
     ! backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
       python scripts/basic_release_contract.py verify-resume-authorization \
         --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
         --clone-certificate "$CLONE_CERTIFICATE" \
         --release-payload "$RELEASE_PAYLOAD" \
         "${CONTRACT_ARTIFACT_ARGS[@]}" \
         --authorization "$authorization"; then
    invalidate_reactivated_prepared_start \
      resume "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
      "$authorization" "$CARESYNC_RETAINED_SOURCE_REVISION" || return
    return 0
  fi
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  disarm_controlled_runtime_window_cleanup
}

recover_incomplete_rollback_start() {
  local candidate_receipt="$1"
  local authorization="$2"
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    load_rollback_run "$candidate_receipt" || return
    authorization="$(
      cd "$(dirname "$authorization")" && pwd
    )/$(basename "$authorization")" || return
    if [[ "$authorization" != "$ROLLBACK_AUTHORIZATION" ]]; then
      basic_fail "Rollback recovery authorization is outside its release run"
      return
    fi
    basic_verify_retained_identity || return
    fence_runtime_roles || return
    basic_quiesce_application || return
    basic_assert_no_cluster_clients || return
    local active_invalidated
    active_invalidated="$(
      startup_evidence_path "$ACTIVE_RUN_DIRECTORY" rollback invalidated
    )" || return
    if [[ -e "$active_invalidated" ]] || \
       [[ -L "$active_invalidated" ]]; then
      require_startup_evidence \
        rollback invalidated "$ACTIVE_RUN_DIRECTORY" \
        "$ACTIVE_CANDIDATE_RECEIPT" "$authorization" \
        "$RELEASE_FENCE_DIRECTORY/context" \
        "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      arm_controlled_runtime_window_cleanup
      CONTROLLED_RUNTIME_WINDOW_OPEN=true
      invalidate_reactivated_rollback_start \
        "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
        "$ACTIVE_COMMIT_RECEIPT" "$ACTIVE_FINALIZATION_RECEIPT" \
        "$authorization" || return
    fi
    return
  fi
  load_retired_rollback_run "$candidate_receipt" || return
  authorization="$(
    cd "$(dirname "$authorization")" && pwd
  )/$(basename "$authorization")"
  local context="$ACTIVE_RUN_DIRECTORY/rollback-fence-retired/context"
  local evidence
  for evidence in \
    "$(startup_evidence_path "$ACTIVE_RUN_DIRECTORY" rollback complete)" \
    "$(startup_evidence_path "$ACTIVE_RUN_DIRECTORY" rollback invalidated)"; do
    if [[ -e "$evidence" ]] || [[ -L "$evidence" ]]; then
      local outcome="${evidence##*-startup-}"
      outcome="${outcome%.evidence}"
      require_startup_evidence \
        rollback "$outcome" "$ACTIVE_RUN_DIRECTORY" \
        "$ACTIVE_CANDIDATE_RECEIPT" "$authorization" "$context" \
        "$CARESYNC_RETAINED_SOURCE_REVISION" || return
      if [[ "$outcome" == "complete" ]]; then
        complete_rollback_start "$candidate_receipt" "$authorization" || return
      fi
      return
    fi
  done
  local quarantine_directory partial_directory
  quarantine_directory="$(
    private_context_value "$context" quarantine_directory
  )" || return
  partial_directory="$(private_context_value "$context" partial_directory)" \
    || return
  arm_controlled_runtime_window_cleanup
  CONTROLLED_RUNTIME_WINDOW_OPEN=true
  reactivate_retired_rollback_fence \
    "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$ACTIVE_COMMIT_RECEIPT" "$ACTIVE_FINALIZATION_RECEIPT" \
    "$authorization" "$quarantine_directory" "$partial_directory" || return
  basic_verify_retained_identity || return
  fence_runtime_roles || return
  basic_quiesce_application || return
  basic_assert_no_cluster_clients || return
  if ! basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION" || \
     ! verify_static_artifacts || \
     ! backend_env 127.0.0.1 "$PGPORT" "$MIGRATION_USER" "" \
       python scripts/basic_release_contract.py verify-resume-authorization \
         --candidate-receipt "$ACTIVE_CANDIDATE_RECEIPT" \
         --clone-certificate "$CLONE_CERTIFICATE" \
         --release-payload "$RELEASE_PAYLOAD" \
         "${CONTRACT_ARTIFACT_ARGS[@]}" \
         --authorization "$authorization"; then
    invalidate_reactivated_rollback_start \
      "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
      "$ACTIVE_COMMIT_RECEIPT" "$ACTIVE_FINALIZATION_RECEIPT" \
      "$authorization" || return
    return 0
  fi
  CONTROLLED_RUNTIME_WINDOW_OPEN=false
  disarm_controlled_runtime_window_cleanup
}

recover_incomplete_commit_start() {
  local candidate_receipt="$1"
  local commit_receipt="$2"
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
     [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    load_release_run "$candidate_receipt" || return
    commit_receipt="$(
      cd "$(dirname "$commit_receipt")" && pwd
    )/$(basename "$commit_receipt")" || return
    if [[ "$commit_receipt" != "$COMMIT_RECEIPT" ]]; then
      basic_fail "Commit recovery receipt is outside its release run"
      return
    fi
    basic_verify_retained_identity || return
    fence_runtime_roles || return
    basic_quiesce_application || return
    basic_assert_no_cluster_clients || return
    local active_invalidated
    active_invalidated="$(
      startup_evidence_path "$ACTIVE_RUN_DIRECTORY" commit invalidated
    )" || return
    if [[ -e "$active_invalidated" ]] || \
       [[ -L "$active_invalidated" ]]; then
      require_startup_evidence \
        commit invalidated "$ACTIVE_RUN_DIRECTORY" \
        "$ACTIVE_CANDIDATE_RECEIPT" "$commit_receipt" \
        "$RELEASE_FENCE_DIRECTORY/context" \
        "$CARESYNC_RETAINED_TARGET_REVISION" || return
      arm_controlled_runtime_window_cleanup
      CONTROLLED_RUNTIME_WINDOW_OPEN=true
      invalidate_reactivated_prepared_start \
        commit "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
        "$commit_receipt" "$CARESYNC_RETAINED_TARGET_REVISION" || return
    fi
    return
  fi
  load_retired_prepared_run "$candidate_receipt" || return
  commit_receipt="$(
    cd "$(dirname "$commit_receipt")" && pwd
  )/$(basename "$commit_receipt")"
  local context="$ACTIVE_RUN_DIRECTORY/fence-retired/context"
  local complete invalidated
  complete="$(startup_evidence_path "$ACTIVE_RUN_DIRECTORY" commit complete)"
  invalidated="$(
    startup_evidence_path "$ACTIVE_RUN_DIRECTORY" commit invalidated
  )"
  if [[ -e "$complete" ]] || [[ -L "$complete" ]]; then
    require_startup_evidence \
      commit complete "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
      "$commit_receipt" "$context" \
      "$CARESYNC_RETAINED_TARGET_REVISION" || return
    complete_commit_start "$candidate_receipt" "$commit_receipt" || return
    return
  fi
  if [[ -e "$invalidated" ]] || [[ -L "$invalidated" ]]; then
    require_startup_evidence \
      commit invalidated "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
      "$commit_receipt" "$context" \
      "$CARESYNC_RETAINED_TARGET_REVISION" || return
    return
  fi
  basic_verify_retained_identity || return
  basic_quiesce_application || return
  basic_assert_no_cluster_clients || return
  if basic_require_exact_revision "$CARESYNC_RETAINED_TARGET_REVISION"; then
    restore_runtime_role_states_from_private_context "$context" || return
  fi
  create_startup_evidence \
    commit invalidated "$ACTIVE_RUN_DIRECTORY" "$ACTIVE_CANDIDATE_RECEIPT" \
    "$commit_receipt" "$context" \
    "$CARESYNC_RETAINED_TARGET_REVISION" || return
}

case "${1:-}" in
  prepare|commit|rollback|_resume-0039|\
_verify-resume-start|_finalize-resume-start|_complete-resume-start|\
_verify-commit-start|_finalize-commit-start|_complete-commit-start|\
_verify-rollback-start|_finalize-rollback-start|_complete-rollback-start|\
_recover-incomplete-resume-start|_recover-incomplete-commit-start|\
_recover-incomplete-rollback-start|\
  _fence-runtime-roles|\
  _recover-interrupted-prepare|\
  _preflight-post-retirement-roles|_recover-post-retirement-roles|\
_pending-post-retirement-recovery-source|\
  _preflight-controlled-start|_preflight-normal-start)
    basic_reexec_with_state_change_lock "$0" "$@"
    ;;
esac

case "${1:-}" in
  prepare)
    shift
    prepare_release "$@"
    ;;
  commit)
    shift
    commit_release "$@"
    ;;
  rollback)
    shift
    rollback_release "$@"
    ;;
  _resume-0039)
    shift
    resume_release_0039 "$@"
    ;;
  _verify-resume-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    verify_resume_start "$2" "$3"
    ;;
  _finalize-resume-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    finalize_resume_start "$2" "$3"
    ;;
  _complete-resume-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    complete_resume_start "$2" "$3"
    ;;
  _recover-incomplete-resume-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    recover_incomplete_resume_start "$2" "$3"
    ;;
  _verify-commit-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    verify_commit_start "$2" "$3"
    ;;
  _finalize-commit-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    finalize_commit_start "$2" "$3"
    ;;
  _complete-commit-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    complete_commit_start "$2" "$3"
    ;;
  _recover-incomplete-commit-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    recover_incomplete_commit_start "$2" "$3"
    ;;
  _verify-rollback-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    verify_rollback_start "$2" "$3"
    ;;
  _finalize-rollback-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    finalize_rollback_start "$2" "$3"
    ;;
  _complete-rollback-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    complete_rollback_start "$2" "$3"
    ;;
  _recover-incomplete-rollback-start)
    [[ "$#" == "3" ]] || { usage; exit 2; }
    recover_incomplete_rollback_start "$2" "$3"
    ;;
  _fence-runtime-roles)
    [[ "$#" == "1" ]] || { usage; exit 2; }
    emergency_fence_runtime_roles
    ;;
  _recover-interrupted-prepare)
    [[ "$#" == "1" ]] || { usage; exit 2; }
    reconcile_interrupted_prepare
    ;;
  _preflight-post-retirement-roles)
    [[ "$#" == "1" ]] || { usage; exit 2; }
    preflight_pending_post_retirement_role_restoration
    ;;
  _recover-post-retirement-roles)
    [[ "$#" == "1" ]] || { usage; exit 2; }
    recover_pending_post_retirement_role_restoration
    ;;
  _pending-post-retirement-recovery-source)
    [[ "$#" == "1" ]] || { usage; exit 2; }
    pending_post_retirement_recovery_source_root
    ;;
  _preflight-controlled-start)
    [[ "$#" == "4" ]] || { usage; exit 2; }
    preflight_controlled_start "$2" "$3" "$4"
    ;;
  _preflight-normal-start)
    [[ "$#" == "1" ]] || { usage; exit 2; }
    preflight_normal_start
    ;;
  --help|-h|"")
    usage
    [[ -n "${1:-}" ]] || exit 2
    ;;
  *)
    usage
    exit 2
    ;;
esac
