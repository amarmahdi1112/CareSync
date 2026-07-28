#!/usr/bin/env bash

# Shared, side-effect-free declarations and narrowly scoped process/database
# guards for the CareSync Basic launcher and release scripts.  Callers must set
# ROOT before sourcing this file and must enable `set -euo pipefail`.

if [[ -z "${ROOT:-}" ]]; then
  echo "scripts/lib/basic-runtime.sh requires ROOT" >&2
  return 1
fi

RUNTIME_DIR="${CARESYNC_BASIC_RUNTIME:-$HOME/Library/Application Support/CareSync Basic}"
PGDATA="${CARESYNC_BASIC_PGDATA:-$RUNTIME_DIR/postgres-data}"
PG_BIN="${CARESYNC_PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
PGPORT="${CARESYNC_BASIC_PGPORT:-5434}"
DATABASE_NAME="${CARESYNC_BASIC_DATABASE_NAME:-caresync}"
MIGRATION_USER="${CARESYNC_BASIC_MIGRATION_USER:-$(id -un)}"
APP_USER="${CARESYNC_BASIC_APP_USER:-caresync_basic_app}"
RELEASE_PROBE_USER="caresync_release_probe"
VENV_PATH="${CARESYNC_REBUILD_VENV:-$HOME/Library/Caches/CareSync-Private-Rebuild/.venv}"
FRONTEND_RUNTIME_ROOT="$ROOT/frontend-redesign"
RELEASE_STATE_DIRECTORY="$RUNTIME_DIR/releases"
RELEASE_FENCE_DIRECTORY="$RUNTIME_DIR/release-fence"
RETAINED_IDENTITY_FILE="$RUNTIME_DIR/retained-postgres.identity"
STATE_CHANGE_LOCK_FILE="$RUNTIME_DIR/state-change.lock"
ACTIVE_RELEASE_EPOCH_FILE="$RUNTIME_DIR/active-release.epoch"
ACTIVE_RELEASE_EPOCH_HISTORY_DIRECTORY="$RUNTIME_DIR/release-epoch-history"
POST_RETIREMENT_ROLE_RESTORATION_PENDING="$RUNTIME_DIR/post-retirement-role-restoration.pending"
REACTIVATION_PENDING="$RUNTIME_DIR/release-fence-reactivation.pending"

CARESYNC_RETAINED_SOURCE_REVISION="0039_admissions_decision_spine"
CARESYNC_RETAINED_TARGET_REVISION="0042_billing_policy_recert"
CARESYNC_RELEASE_COMMIT_PHRASE="COMMIT CARESYNC RETAINED 0039 TO 0042"
CARESYNC_RELEASE_RESUME_PHRASE="RESUME CARESYNC RETAINED 0039 WITH THIS SOURCE"
CARESYNC_RELEASE_ROLLBACK_PHRASE="ROLL BACK CARESYNC RETAINED 0042 TO CAPTURED 0039"

basic_fail() {
  printf '%s\n' "$*" >&2
  return 1
}

basic_require_private_state_change_lock_file() {
  basic_assert_no_symlink_components "$STATE_CHANGE_LOCK_FILE" || return
  if [[ -L "$STATE_CHANGE_LOCK_FILE" ]] || \
     [[ ! -f "$STATE_CHANGE_LOCK_FILE" ]] || \
     [[ "$(stat -f '%u' "$STATE_CHANGE_LOCK_FILE")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$STATE_CHANGE_LOCK_FILE")" != "600" ]] || \
     [[ "$(stat -f '%l' "$STATE_CHANGE_LOCK_FILE")" != "1" ]]; then
    basic_fail \
      "CareSync state-change lock must be an owner-controlled mode-0600 regular file"
    return
  fi
}

basic_require_inherited_state_change_lock_fd() {
  if [[ "${CARESYNC_STATE_CHANGE_LOCK_FD:-}" != "9" ]] || \
     [[ ! -e /dev/fd/9 ]]; then
    basic_fail "CareSync inherited state-change lock descriptor is invalid"
    return
  fi
  basic_require_private_state_change_lock_file || return
  local expected_device expected_inode descriptor_facts
  printf -v expected_device '0x%x' \
    "$(stat -f '%d' "$STATE_CHANGE_LOCK_FILE")" || return
  expected_inode="$(stat -f '%i' "$STATE_CHANGE_LOCK_FILE")" || return
  descriptor_facts="$(
    /usr/sbin/lsof -a -p "$$" -d 9 -FDi 2>/dev/null
  )" || return
  if ! grep -Fqx "D$expected_device" <<<"$descriptor_facts" || \
     ! grep -Fqx "i$expected_inode" <<<"$descriptor_facts"; then
    basic_fail \
      "CareSync inherited state-change lock descriptor is not bound to the private lock file"
    return
  fi
}

basic_reexec_with_state_change_lock() {
  # FD 9 is deliberate: macOS ships Bash 3.2, which has no dynamic-FD
  # allocation syntax. The descriptor, not a PID/environment marker, carries
  # serialization through nested release -> start -> finalizer commands.
  : "${1:?state-changing script path is required}"
  if [[ -L "$RUNTIME_DIR" ]] || [[ ! -d "$RUNTIME_DIR" ]] || \
     [[ "$(stat -f '%u' "$RUNTIME_DIR")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$RUNTIME_DIR")" != "700" ]]; then
    basic_fail \
      "CareSync runtime must be a private real directory before state serialization"
    exit 1
  fi
  if [[ ! -e "$STATE_CHANGE_LOCK_FILE" ]] && \
     [[ ! -L "$STATE_CHANGE_LOCK_FILE" ]]; then
    if ! (
      set -o noclobber
      : >"$STATE_CHANGE_LOCK_FILE"
    ); then
      [[ -e "$STATE_CHANGE_LOCK_FILE" ]] || {
        basic_fail "Could not initialize the CareSync state-change lock"
        exit 1
      }
    fi
  fi
  basic_require_private_state_change_lock_file || exit 1

  if [[ -n "${CARESYNC_STATE_CHANGE_LOCK_FD:-}" ]]; then
    basic_require_inherited_state_change_lock_fd || exit 1
  else
    exec 9<>"$STATE_CHANGE_LOCK_FILE" || {
      basic_fail "Could not open the CareSync state-change lock"
      exit 1
    }
    export CARESYNC_STATE_CHANGE_LOCK_FD=9
    basic_require_inherited_state_change_lock_fd || exit 1
  fi

  local result
  set +e
  /usr/bin/lockf -s -t 0 9
  result=$?
  set -e
  if (( result == 75 )); then
    basic_fail \
      "Another CareSync start, stop, prepare, commit, resume, or rollback is active"
    exit "$result"
  elif (( result != 0 )); then
    basic_fail "CareSync state-change lock failed before the command could run"
    exit "$result"
  fi
}

basic_close_state_change_lock_for_detached_child() {
  basic_require_inherited_state_change_lock_fd || return
  exec 9>&- || return
  unset CARESYNC_STATE_CHANGE_LOCK_FD
}

basic_run_guarded_without_state_lock_in_child() (
  # The guardian keeps FD 9 until the foreground launcher exits. The launcher
  # closes it before exec, so a successfully detached daemon cannot retain the
  # global state lock.
  local result
  (
    basic_close_state_change_lock_for_detached_child || exit
    "$@"
  )
  result=$?
  : "$result"
  return "$result"
)

basic_require_local_toolchain() {
  local executable
  for executable in \
    "$PG_BIN/pg_basebackup" \
    "$PG_BIN/pg_controldata" \
    "$PG_BIN/pg_ctl" \
    "$PG_BIN/pg_isready" \
    "$PG_BIN/pg_verifybackup" \
    "$PG_BIN/psql" \
    /bin/chmod \
    /bin/df \
    /bin/ls \
    /usr/bin/curl \
    /usr/bin/ditto \
    /usr/bin/find \
    /usr/bin/lockf \
    /usr/bin/plutil \
    /usr/bin/stat \
    /usr/bin/xattr \
    /usr/sbin/diskutil \
    /usr/sbin/lsof \
    "$VENV_PATH/bin/python"; do
    if [[ ! -x "$executable" ]]; then
      basic_fail "Required CareSync local executable is unavailable: $executable"
      return
    fi
  done
  if [[ ! -f "$ROOT/backend/scripts/uv.sh" ]] || \
     [[ -L "$ROOT/backend/scripts/uv.sh" ]]; then
    basic_fail "CareSync captured uv wrapper is missing or unsafe"
    return
  fi
  local command_name
  for command_name in lsof node npm; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      basic_fail "Required CareSync command is unavailable: $command_name"
      return
    fi
  done
  local dependency_root="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}"
  if [[ ! -f "$ROOT/frontend-redesign/package.json" ]] || \
     [[ ! -d "$dependency_root/frontend-redesign/node_modules" ]]; then
    basic_fail "CareSync frontend dependencies are incomplete"
    return
  fi
  if [[ "$ROOT" == "$RELEASE_STATE_DIRECTORY/"*"/release-source" ]] && \
     { [[ -L "$ROOT/frontend-redesign/dist" ]] || \
       [[ ! -f "$ROOT/frontend-redesign/dist/index.html" ]]; }; then
    basic_fail "CareSync captured frontend production build is unavailable"
    return
  fi
}

basic_normalize_known_runtime_files() {
  local private_file
  for private_file in \
    "$RUNTIME_DIR"/logs/*.log \
    "$RUNTIME_DIR"/pids/*.pid \
    "$RUNTIME_DIR"/pids/*.launching \
    "$RUNTIME_DIR"/pids/*.gate; do
    [[ ! -e "$private_file" ]] && continue
    if [[ -L "$private_file" ]] || [[ ! -f "$private_file" ]] || \
       [[ "$(stat -f '%u' "$private_file")" != "$(id -u)" ]] || \
       [[ "$(stat -f '%l' "$private_file")" != "1" ]]; then
      basic_fail \
        "CareSync runtime files must be owner-controlled single-link regular files"
      return
    fi
    chmod 600 "$private_file"
    if [[ "$(stat -f '%Lp' "$private_file")" != "600" ]]; then
      basic_fail "CareSync runtime file privacy normalization failed"
      return
    fi
  done
}

basic_assert_no_symlink_components() {
  local path="$1"
  local absolute
  if [[ "$path" == /* ]]; then
    absolute="$path"
  else
    absolute="$PWD/$path"
  fi
  local components=()
  local component cursor="/"
  IFS='/' read -r -a components <<<"${absolute#/}"
  # macOS Bash 3.2 treats an empty "${array[@]}" as unbound under `set -u`.
  # The + form preserves every populated element while expanding to zero
  # arguments for an empty array.
  for component in "${components[@]+"${components[@]}"}"; do
    [[ -n "$component" ]] || continue
    cursor="${cursor%/}/$component"
    if [[ -L "$cursor" ]]; then
      basic_fail "CareSync private path contains a symbolic link: $path"
      return
    fi
  done
}

basic_durable_ensure_private_runtime_directory() {
  local directory="${1:?private runtime directory is required}"
  local contract="$ROOT/backend/scripts/basic_release_contract.py"
  if [[ ! -x "$VENV_PATH/bin/python" ]] || \
     [[ -L "$contract" ]] || [[ ! -f "$contract" ]]; then
    basic_fail \
      "CareSync cannot durably create a private runtime directory without its captured release contract"
    return
  fi
  PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
    "$contract" ensure-private-directory --path "$directory" >/dev/null || {
    basic_fail \
      "CareSync could not durably create or validate its private runtime directory: $directory"
    return
  }
}

basic_require_runtime_layout() {
  if [[ "$APP_USER" != "caresync_basic_app" ]]; then
    basic_fail "CARESYNC_BASIC_APP_USER must be exactly caresync_basic_app"
    return
  fi
  if [[ ! "$PGPORT" =~ ^[0-9]+$ ]] || (( PGPORT != 5434 )); then
    basic_fail "The retained CareSync Basic release contract requires port 5434"
    return
  fi
  if [[ "$DATABASE_NAME" != "caresync" ]]; then
    basic_fail "The retained CareSync Basic release contract requires database caresync"
    return
  fi
  basic_assert_no_symlink_components "$RUNTIME_DIR" || return
  if [[ -L "$RUNTIME_DIR" ]] || [[ -e "$RUNTIME_DIR" && ! -d "$RUNTIME_DIR" ]]; then
    basic_fail "CareSync runtime directory is not a safe real directory"
    return
  fi
  basic_durable_ensure_private_runtime_directory "$RUNTIME_DIR" || return
  local owner mode
  owner="$(stat -f '%u' "$RUNTIME_DIR")"
  mode="$(stat -f '%Lp' "$RUNTIME_DIR")"
  if [[ "$owner" != "$(id -u)" ]] || [[ "$mode" != "700" ]]; then
    basic_fail "CareSync runtime directory must be owner-controlled mode 0700"
    return
  fi
  basic_assert_no_symlink_components "$PGDATA" || return
  if [[ -L "$PGDATA" ]] || [[ ! -d "$PGDATA" ]] || [[ ! -f "$PGDATA/PG_VERSION" ]]; then
    basic_fail "The isolated CareSync Basic PostgreSQL cluster is missing at: $PGDATA"
    return
  fi
  if [[ "$(<"$PGDATA/PG_VERSION")" != "17" ]]; then
    basic_fail "CareSync retained PostgreSQL must be major version 17"
    return
  fi
  owner="$(stat -f '%u' "$PGDATA")"
  mode="$(stat -f '%Lp' "$PGDATA")"
  if [[ "$owner" != "$(id -u)" ]] || [[ "$mode" != "700" ]]; then
    basic_fail "CareSync PGDATA must be owner-controlled mode 0700"
    return
  fi
  local directory
  for directory in "$RUNTIME_DIR/logs" "$RUNTIME_DIR/pids"; do
    if [[ -L "$directory" ]] || [[ -e "$directory" && ! -d "$directory" ]]; then
      basic_fail "CareSync runtime child is not a safe real directory: $directory"
      return
    fi
    basic_durable_ensure_private_runtime_directory "$directory" || return
    owner="$(stat -f '%u' "$directory")"
    mode="$(stat -f '%Lp' "$directory")"
    if [[ "$owner" != "$(id -u)" ]] || [[ "$mode" != "700" ]]; then
      basic_fail "CareSync runtime child must be owner-controlled mode 0700: $directory"
      return
    fi
  done
}

basic_identity_query() {
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$PGPORT" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "SHOW data_directory; SELECT system_identifier::text FROM pg_control_system()"
}

basic_verify_retained_identity() {
  local identity_output
  identity_output="$(basic_identity_query)" || {
    basic_fail "Retained PostgreSQL identity query failed"
    return
  }
  local rows=()
  while IFS= read -r value; do
    rows+=("$value")
  done <<<"$identity_output"
  if (( ${#rows[@]} != 2 )) || [[ ! "${rows[1]}" =~ ^[0-9]+$ ]]; then
    basic_fail "Retained PostgreSQL identity query returned an invalid shape"
    return
  fi
  local live_data_directory="${rows[0]}"
  local live_system_identifier="${rows[1]}"
  if [[ -L "$live_data_directory" ]] || [[ ! -d "$live_data_directory" ]]; then
    basic_fail "Live retained PostgreSQL reports an unsafe data directory"
    return
  fi
  local canonical_live canonical_expected
  canonical_live="$(cd "$live_data_directory" && pwd -P)"
  canonical_expected="$(cd "$PGDATA" && pwd -P)"
  if [[ "$canonical_live" != "$canonical_expected" ]]; then
    basic_fail "Port $PGPORT is not serving the configured retained PGDATA"
    return
  fi

  if [[ -L "$RETAINED_IDENTITY_FILE" ]] || \
     [[ -e "$RETAINED_IDENTITY_FILE" && ! -f "$RETAINED_IDENTITY_FILE" ]]; then
    basic_fail "Retained PostgreSQL identity file is unsafe"
    return
  fi
  if [[ ! -e "$RETAINED_IDENTITY_FILE" ]]; then
    if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
      basic_fail "Cannot enroll retained PostgreSQL identity while a release is fenced"
      return
    fi
    local revision
    revision="$("$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
      -h 127.0.0.1 -p "$PGPORT" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
      -c "SELECT version_num FROM public.alembic_version")"
    if [[ "$revision" != "$CARESYNC_RETAINED_SOURCE_REVISION" ]]; then
      basic_fail "First retained identity enrollment is allowed only at exact 0039"
      return
    fi
    local pending_identity
    pending_identity="$RUNTIME_DIR/.retained-postgres.identity.pending.$$.$RANDOM"
    if ! (
      set -o noclobber
      printf '%s\n' \
        "data_directory=$canonical_expected" \
        "system_identifier=$live_system_identifier" \
        "port=$PGPORT" \
        "database=$DATABASE_NAME" \
        >"$pending_identity"
    ); then
      basic_fail "Retained PostgreSQL identity enrollment raced another writer"
      return
    fi
    chmod 600 "$pending_identity"
    basic_run_backend_python \
      scripts/basic_release_contract.py durable-publish-private-file \
        --source "$pending_identity" \
        --destination "$RETAINED_IDENTITY_FILE" || return
    if [[ -e "$pending_identity" ]] || [[ -L "$pending_identity" ]]; then
      basic_fail "Retained PostgreSQL identity publication was incomplete"
      return
    fi
  fi
  local identity_owner identity_mode
  identity_owner="$(stat -f '%u' "$RETAINED_IDENTITY_FILE")"
  identity_mode="$(stat -f '%Lp' "$RETAINED_IDENTITY_FILE")"
  if [[ "$identity_owner" != "$(id -u)" ]] || [[ "$identity_mode" != "600" ]] || \
     [[ "$(stat -f '%l' "$RETAINED_IDENTITY_FILE")" != "1" ]] || \
     [[ "$(wc -l <"$RETAINED_IDENTITY_FILE" | tr -d '[:space:]')" != "4" ]] || \
     ! grep -Fqx "data_directory=$canonical_expected" "$RETAINED_IDENTITY_FILE" || \
     ! grep -Fqx "system_identifier=$live_system_identifier" "$RETAINED_IDENTITY_FILE" || \
     ! grep -Fqx "port=$PGPORT" "$RETAINED_IDENTITY_FILE" || \
     ! grep -Fqx "database=$DATABASE_NAME" "$RETAINED_IDENTITY_FILE"; then
    basic_fail "Live retained PostgreSQL does not match its private pinned identity"
    return
  fi
}

basic_start_postgres() {
  basic_require_runtime_layout || return
  if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_run_guarded_without_state_lock_in_child \
      "$PG_BIN/pg_ctl" -D "$PGDATA" \
      -l "$RUNTIME_DIR/logs/postgres.log" \
      -o "-p $PGPORT -h 127.0.0.1" start || return
  fi
  local attempt
  for attempt in {1..80}; do
    if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
      basic_verify_retained_identity || return
      return
    fi
    sleep 0.125
  done
  basic_fail "CareSync retained PostgreSQL did not become ready"
}

basic_stop_retained_postgres() {
  basic_require_runtime_layout || return
  if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
    basic_verify_retained_identity || return
    "$PG_BIN/pg_ctl" -D "$PGDATA" stop -m fast || return
  elif [[ -f "$PGDATA/postmaster.pid" ]]; then
    basic_fail \
      "Retained PostgreSQL has a postmaster PID but is not ready enough to prove identity"
    return
  fi
  local attempt
  for attempt in {1..80}; do
    if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q && \
       [[ ! -f "$PGDATA/postmaster.pid" ]]; then
      return 0
    fi
    sleep 0.125
  done
  basic_fail "Retained PostgreSQL did not stop cleanly"
}

basic_require_safe_postgres_tree() {
  local path="$1"
  local label="$2"
  basic_assert_no_symlink_components "$path" || return
  if [[ -L "$path" ]] || [[ ! -d "$path" ]] || \
     [[ "$(stat -f '%u' "$path")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$path")" != "700" ]] || \
     [[ ! -f "$path/PG_VERSION" ]] || [[ "$(<"$path/PG_VERSION")" != "17" ]]; then
    basic_fail "$label is not an owner-controlled PostgreSQL 17 directory"
    return
  fi
  if ! basic_run_backend_python \
    scripts/basic_release_contract.py validate-private-tree --path "$path"; then
    basic_fail "$label failed its complete fail-closed tree traversal"
    return
  fi
  if [[ -d "$path/pg_tblspc" ]]; then
    local tablespace_entry
    tablespace_entry="$(
      find "$path/pg_tblspc" -xdev -mindepth 1 -print -quit
    )" || {
      basic_fail "$label tablespace directory could not be traversed"
      return
    }
    if [[ -n "$tablespace_entry" ]]; then
      basic_fail "$label contains an external tablespace mapping"
      return
    fi
  fi
  if [[ -e "$path/standby.signal" ]] || [[ -L "$path/standby.signal" ]] || \
     [[ -e "$path/recovery.signal" ]] || [[ -L "$path/recovery.signal" ]]; then
    basic_fail "$label contains a PostgreSQL recovery signal"
    return
  fi
}

basic_strip_unbound_postgres_metadata() {
  local path="$1"
  basic_assert_no_symlink_components "$path" || return
  if [[ -L "$path" ]] || [[ ! -d "$path" ]] || \
     [[ "$(stat -f '%u' "$path")" != "$(id -u)" ]]; then
    basic_fail "Cannot sanitize metadata on an unsafe PostgreSQL tree"
    return
  fi
  /bin/chmod -RN "$path" || return
  /usr/bin/xattr -cr "$path" || return
}

basic_postgres_control_system_identifier() {
  local path="$1"
  local identifier
  identifier="$(LC_ALL=C "$PG_BIN/pg_controldata" "$path" | \
    sed -n 's/^Database system identifier:[[:space:]]*//p')" || return
  if [[ ! "$identifier" =~ ^[0-9]+$ ]]; then
    basic_fail "PostgreSQL control data has no valid system identifier"
    return
  fi
  printf '%s\n' "$identifier"
}

basic_postgres_control_state() {
  local path="$1"
  local state
  state="$(LC_ALL=C "$PG_BIN/pg_controldata" "$path" | \
    sed -n 's/^Database cluster state:[[:space:]]*//p')" || return
  if [[ -z "$state" ]]; then
    basic_fail "PostgreSQL control data has no cluster state"
    return
  fi
  printf '%s\n' "$state"
}

basic_materialize_physical_copy() {
  local source="$1"
  local destination="$2"
  local label="$3"
  basic_require_safe_postgres_tree "$source" "$label source" || return
  basic_assert_no_symlink_components "$(dirname "$destination")" || return
  if [[ -e "$destination" ]] || [[ -L "$destination" ]]; then
    basic_fail "$label destination already exists"
    return
  fi
  /usr/bin/ditto -X --norsrc --noextattr --noacl --noqtn \
    --nopersistRootless --nopreserveHFSCompression --noclone \
    "$source" "$destination" || return
  basic_strip_unbound_postgres_metadata "$destination" || return
  find "$destination" -xdev -type d -exec chmod 700 {} + || return
  find "$destination" -xdev -type f -exec chmod 600 {} + || return
  basic_require_safe_postgres_tree \
    "$destination" "$label destination" || return
  basic_run_backend_python \
    scripts/basic_release_contract.py \
      durability-barrier-private-tree --path "$destination" || return
}

basic_require_same_apfs_device() {
  local first="$1"
  local second="$2"
  local dependency first_device second_device first_type second_type
  for dependency in /bin/df /usr/sbin/diskutil /usr/bin/plutil; do
    if [[ ! -x "$dependency" ]]; then
      basic_fail "Required filesystem attestation tool is missing: $dependency"
      return
    fi
  done
  first_device="$(
    /bin/df -P "$first" | /usr/bin/awk 'NR==2 {print $1}'
  )" || return
  second_device="$(
    /bin/df -P "$second" | /usr/bin/awk 'NR==2 {print $1}'
  )" || return
  if [[ ! "$first_device" =~ ^/dev/ ]] || \
     [[ ! "$second_device" =~ ^/dev/ ]]; then
    basic_fail "Could not identify rollback filesystem devices"
    return
  fi
  first_type="$(/usr/sbin/diskutil info -plist "$first_device" | \
    /usr/bin/plutil -extract FilesystemType raw -)" || return
  second_type="$(/usr/sbin/diskutil info -plist "$second_device" | \
    /usr/bin/plutil -extract FilesystemType raw -)" || return
  if [[ "$first_type" != "apfs" ]] || [[ "$second_type" != "apfs" ]] || \
     [[ "$(stat -f '%d' "$first")" != "$(stat -f '%d' "$second")" ]]; then
    basic_fail "Rollback paths must be on the same APFS filesystem"
    return
  fi
}

basic_existing_filesystem_anchor() {
  local path="$1"
  basic_assert_no_symlink_components "$path" || return
  if [[ -e "$path" ]] || [[ -L "$path" ]]; then
    if [[ -L "$path" ]]; then
      basic_fail "Release filesystem path is a symbolic link: $path"
      return
    fi
    printf '%s\n' "$path"
    return
  fi
  local parent
  parent="$(dirname "$path")" || return
  basic_assert_no_symlink_components "$parent" || return
  if [[ -L "$parent" ]] || [[ ! -d "$parent" ]]; then
    basic_fail \
      "Release filesystem destination has no safe existing parent: $path"
    return
  fi
  printf '%s\n' "$parent"
}

basic_require_release_apfs_topology() {
  local physical_path="$1"
  local quarantine_path="$2"
  local runtime_anchor pgdata_anchor release_anchor physical_anchor
  local quarantine_anchor
  runtime_anchor="$(basic_existing_filesystem_anchor "$RUNTIME_DIR")" || return
  pgdata_anchor="$(basic_existing_filesystem_anchor "$PGDATA")" || return
  release_anchor="$(
    basic_existing_filesystem_anchor "$RELEASE_STATE_DIRECTORY"
  )" || return
  physical_anchor="$(
    basic_existing_filesystem_anchor "$physical_path"
  )" || return
  quarantine_anchor="$(
    basic_existing_filesystem_anchor "$quarantine_path"
  )" || return
  local anchor
  for anchor in \
    "$pgdata_anchor" \
    "$release_anchor" \
    "$physical_anchor" \
    "$quarantine_anchor"; do
    basic_require_same_apfs_device "$runtime_anchor" "$anchor" || {
      basic_fail \
        "CareSync release requires PGDATA, runtime, release evidence, physical backup, and quarantine on one APFS filesystem"
      return
    }
  done
}

basic_psql_scalar() {
  "$PG_BIN/psql" -v ON_ERROR_STOP=1 -X -At \
    -h 127.0.0.1 -p "$PGPORT" -U "$MIGRATION_USER" -d "$DATABASE_NAME" \
    -c "$1"
}

basic_current_revision() {
  local has_version row_count revision
  has_version="$(basic_psql_scalar \
    "SELECT CASE WHEN to_regclass('public.alembic_version') IS NULL THEN 0 ELSE 1 END")" \
    || return
  if [[ "$has_version" != "1" ]]; then
    basic_fail "Retained database has no Alembic provenance"
    return
  fi
  row_count="$(
    basic_psql_scalar "SELECT count(*) FROM public.alembic_version"
  )" || return
  if [[ "$row_count" != "1" ]]; then
    basic_fail "Retained database must contain exactly one Alembic revision row"
    return
  fi
  revision="$(
    basic_psql_scalar "SELECT version_num FROM public.alembic_version"
  )" || return
  if [[ -z "$revision" ]]; then
    basic_fail "Retained Alembic revision is blank"
    return
  fi
  printf '%s\n' "$revision"
}

basic_require_exact_revision() {
  local expected="$1"
  local actual
  actual="$(basic_current_revision)"
  if [[ "$actual" != "$expected" ]]; then
    basic_fail "CareSync retained revision is $actual; exact $expected is required"
    return
  fi
}

basic_process_cwd() {
  local pid="$1"
  local facts
  facts="$(/usr/sbin/lsof -a -p "$pid" -d cwd -Fn 2>/dev/null)" || return
  sed -n 's/^n//p' <<<"$facts" | head -n 1
}

basic_private_context_value() {
  local context="$1"
  local key="$2"
  local output
  output="$(/usr/bin/sed -n "s/^$key=//p" "$context")" || {
    basic_fail "CareSync private context could not be read"
    return
  }
  if [[ -z "$output" ]] || [[ "$output" == *$'\n'* ]]; then
    basic_fail "CareSync private context has an invalid $key"
    return
  fi
  printf '%s\n' "$output"
}

basic_expected_release_source_root() {
  if [[ "$ROOT" == "$RELEASE_STATE_DIRECTORY/"*"/release-source" ]]; then
    printf '%s\n' "$ROOT"
    return
  fi
  local context=""
  if [[ -f "$RELEASE_FENCE_DIRECTORY/context" ]] && \
     [[ ! -L "$RELEASE_FENCE_DIRECTORY/context" ]]; then
    context="$RELEASE_FENCE_DIRECTORY/context"
  elif [[ -f "$ACTIVE_RELEASE_EPOCH_FILE" ]] && \
       [[ ! -L "$ACTIVE_RELEASE_EPOCH_FILE" ]]; then
    context="$ACTIVE_RELEASE_EPOCH_FILE"
  fi
  if [[ -n "$context" ]]; then
    local run_directory
    run_directory="$(basic_private_context_value \
      "$context" run_directory)" || return
    if [[ "$run_directory" == "$RELEASE_STATE_DIRECTORY/"* ]] && \
       [[ -d "$run_directory/release-source/backend" ]] && \
       [[ ! -L "$run_directory/release-source/backend" ]]; then
      printf '%s/release-source\n' "$run_directory"
      return
    fi
  fi
  printf '%s\n' "$ROOT"
}

basic_expected_backend_runtime_root() {
  local source_root
  source_root="$(basic_expected_release_source_root)" || return
  printf '%s/backend\n' "$source_root"
}

basic_expected_frontend_runtime_root() {
  local source_root
  source_root="$(basic_expected_release_source_root)" || return
  printf '%s/frontend-redesign\n' "$source_root"
}

basic_inspect_pid_presence() {
  # BSD ps reports status 1 with no output when the selected PID is absent.
  # Treat only that exact tuple as absence; every other inspection anomaly is
  # fail-closed so a caller never mistakes an unreadable process for a stopped
  # one.
  local pid="$1"
  local output result
  set +e
  output="$(/bin/ps -p "$pid" -o pid= 2>/dev/null)"
  result=$?
  set -e
  if (( result == 0 )) && \
     [[ "$(tr -d '[:space:]' <<<"$output")" == "$pid" ]]; then
    printf '%s\n' present
    return 0
  fi
  if (( result == 1 )) && [[ -z "$output" ]]; then
    local self_probe
    self_probe="$(/bin/ps -p "$$" -o pid= 2>/dev/null)" || {
      basic_fail "Process inspection is unavailable"
      return
    }
    if [[ "$(tr -d '[:space:]' <<<"$self_probe")" != "$$" ]]; then
      basic_fail "Process inspection self-check returned an invalid PID"
      return
    fi
    printf '%s\n' absent
    return 0
  fi
  basic_fail "Process inspection returned an ambiguous result for PID $pid"
  return 1
}

basic_collect_tcp_listener_pids() {
  local port="$1"
  local output result
  set +e
  output="$(
    /usr/sbin/lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null
  )"
  result=$?
  set -e
  if (( result == 1 )) && [[ -z "$output" ]]; then
    # lsof uses status 1 for a valid empty selection. Prove the inspection
    # mechanism itself still works before interpreting that as no listener.
    /usr/sbin/lsof -a -p "$$" -d cwd -Fn >/dev/null 2>&1 || {
      basic_fail "TCP listener inspection is unavailable"
      return
    }
    return 0
  fi
  if (( result != 0 )); then
    basic_fail "TCP listener inspection failed"
    return
  fi
  local pid
  while IFS= read -r pid; do
    [[ -z "$pid" ]] || [[ "$pid" =~ ^[1-9][0-9]*$ ]] || {
      basic_fail "TCP listener inspection returned an invalid PID"
      return
    }
  done <<<"$output"
  printf '%s\n' "$output"
}

basic_wait_for_process_exit() {
  local pid="$1"
  local attempt
  for attempt in {1..80}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.125
  done
  return 1
}

basic_publish_managed_pid() {
  local service="$1"
  local pid="$2"
  local pid_file="$RUNTIME_DIR/pids/$service.pid"
  if [[ ! "$pid" =~ ^[1-9][0-9]*$ ]] || (( pid <= 1 )); then
    basic_fail "Refusing to publish an invalid $service PID"
    return
  fi
  local presence
  presence="$(basic_inspect_pid_presence "$pid")" || return
  if [[ "$presence" != "present" ]]; then
    basic_fail "The $service process exited before PID publication"
    return
  fi
  local pending="$RUNTIME_DIR/pids/.$service.pid.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' "$pid" >"$pending"
  ); then
    basic_fail "Could not stage the $service PID record"
    return
  fi
  chmod 600 "$pending" || {
    rm -f "$pending"
    return 1
  }
  if [[ -e "$pid_file" ]] || [[ -L "$pid_file" ]]; then
    rm -f "$pending"
    basic_fail \
      "Refusing to replace an existing $service PID record during launch"
    return
  fi
  if ! PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/basic_release_contract.py" \
      durable-publish-private-file \
      --source "$pending" \
      --destination "$pid_file"; then
    rm -f "$pending"
    basic_fail "Could not durably publish the $service PID record"
    return
  fi
  if [[ -L "$pid_file" ]] || [[ ! -f "$pid_file" ]] || \
     [[ "$(<"$pid_file")" != "$pid" ]] || \
     [[ "$(stat -f '%u' "$pid_file")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$pid_file")" != "600" ]] || \
     [[ "$(stat -f '%l' "$pid_file")" != "1" ]]; then
    basic_fail "The durable $service PID record failed verification"
    return
  fi
}

basic_durable_remove_private_runtime_file() {
  local path="$1"
  PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/basic_release_contract.py" \
      durable-remove-private-file --path "$path" >/dev/null || {
    basic_fail "Could not durably remove private runtime state: $path"
    return
  }
}

basic_prepare_managed_launch() {
  local service="$1"
  local signature="$2"
  local expected_cwd="$3"
  local intent="$RUNTIME_DIR/pids/$service.launching"
  local gate="$RUNTIME_DIR/pids/$service.gate"
  local pid_file="$RUNTIME_DIR/pids/$service.pid"
  case "$service" in
    backend|frontend|push-worker)
      ;;
    *)
      basic_fail "Unsupported managed launch service: $service"
      return
      ;;
  esac
  if [[ "$signature" == *$'\n'* ]] || [[ -z "$signature" ]] || \
     [[ "$(cd "$expected_cwd" && pwd -P)" != "$expected_cwd" ]]; then
    basic_fail "Managed launch identity is unsafe for $service"
    return
  fi
  if [[ -e "$intent" ]] || [[ -L "$intent" ]] || \
     [[ -e "$gate" ]] || [[ -L "$gate" ]] || \
     [[ -e "$pid_file" ]] || [[ -L "$pid_file" ]]; then
    basic_fail \
      "Managed launch state already exists for $service; reconcile it first"
    return
  fi
  local nonce pending
  nonce="$(
    PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" -c \
      'import secrets; print(secrets.token_hex(32))'
  )" || return
  if [[ ! "$nonce" =~ ^[0-9a-f]{64}$ ]]; then
    basic_fail "Could not generate a managed launch nonce for $service"
    return
  fi
  pending="$RUNTIME_DIR/pids/.$service.launching.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=managed_launch_pending" \
      "service=$service" \
      "nonce=$nonce" \
      "parent_pid=$$" \
      "expected_cwd=$expected_cwd" \
      "signature=$signature" >"$pending"
  ); then
    basic_fail "Could not stage the managed launch intent for $service"
    return
  fi
  chmod 600 "$pending" || {
    rm -f "$pending"
    return 1
  }
  if ! PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/basic_release_contract.py" \
      durable-publish-private-file \
      --source "$pending" \
      --destination "$intent" >/dev/null; then
    rm -f "$pending"
    basic_fail "Could not durably publish the launch intent for $service"
    return
  fi
  printf '%s\n' "$nonce"
}

basic_publish_managed_launch_gate() {
  local service="$1"
  local nonce="$2"
  local pid="$3"
  local intent="$RUNTIME_DIR/pids/$service.launching"
  local gate="$RUNTIME_DIR/pids/$service.gate"
  local pid_file="$RUNTIME_DIR/pids/$service.pid"
  if [[ ! "$nonce" =~ ^[0-9a-f]{64}$ ]] || \
     [[ ! "$pid" =~ ^[1-9][0-9]*$ ]] || (( pid <= 1 )) || \
     [[ -L "$intent" ]] || [[ ! -f "$intent" ]] || \
     [[ -L "$pid_file" ]] || [[ ! -f "$pid_file" ]] || \
     [[ "$(<"$pid_file")" != "$pid" ]] || \
     [[ -e "$gate" ]] || [[ -L "$gate" ]]; then
    basic_fail "Managed launch gate preconditions failed for $service"
    return
  fi
  local pending="$RUNTIME_DIR/pids/.$service.gate.$$.$RANDOM"
  if ! (
    set -o noclobber
    printf '%s\n' \
      "status=managed_launch_released" \
      "service=$service" \
      "nonce=$nonce" \
      "pid=$pid" >"$pending"
  ); then
    basic_fail "Could not stage the managed launch gate for $service"
    return
  fi
  chmod 600 "$pending" || {
    rm -f "$pending"
    return 1
  }
  if ! PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/basic_release_contract.py" \
      durable-publish-private-file \
      --source "$pending" \
      --destination "$gate" >/dev/null; then
    rm -f "$pending"
    basic_fail "Could not durably publish the managed launch gate for $service"
    return
  fi
}

basic_complete_managed_launch() {
  local service="$1"
  local signature="$2"
  local expected_cwd="$3"
  local attempt
  for attempt in {1..80}; do
    if PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
      "$ROOT/backend/scripts/gated_service_exec.py" complete \
        --intent "$RUNTIME_DIR/pids/$service.launching" \
        --gate "$RUNTIME_DIR/pids/$service.gate" \
        --pid-file "$RUNTIME_DIR/pids/$service.pid" \
        --service "$service" \
        --expected-cwd "$expected_cwd" \
        --signature "$signature" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.125
  done
  PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/gated_service_exec.py" complete \
      --intent "$RUNTIME_DIR/pids/$service.launching" \
      --gate "$RUNTIME_DIR/pids/$service.gate" \
      --pid-file "$RUNTIME_DIR/pids/$service.pid" \
      --service "$service" \
      --expected-cwd "$expected_cwd" \
      --signature "$signature" || {
    basic_fail "Could not complete the durable launch handoff for $service"
    return
  }
}

basic_reconcile_managed_launch() {
  local service="$1"
  local signature="$2"
  local expected_cwd="$3"
  PYTHONDONTWRITEBYTECODE=1 "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/gated_service_exec.py" reconcile \
      --intent "$RUNTIME_DIR/pids/$service.launching" \
      --gate "$RUNTIME_DIR/pids/$service.gate" \
      --pid-file "$RUNTIME_DIR/pids/$service.pid" \
      --service "$service" \
      --expected-cwd "$expected_cwd" \
      --signature "$signature" || {
    basic_fail "Could not reconcile the durable launch state for $service"
    return
  }
}

basic_reconcile_torn_managed_pid() {
  local service="$1"
  local signature="$2"
  local expected_cwd="$3"
  local pid_file="$RUNTIME_DIR/pids/$service.pid"
  local process_list pid command cwd
  process_list="$(ps -ax -o pid=,command=)" || {
    basic_fail "Could not reconcile the invalid $service PID record"
    return
  }
  local matching_pids=()
  while read -r pid command; do
    [[ -n "$pid" ]] || continue
    [[ "$command" == *"$signature"* ]] || continue
    cwd="$(basic_process_cwd "$pid")" || {
      basic_fail "Could not identify a process matching the invalid $service PID"
      return
    }
    if [[ "$cwd" != "$expected_cwd" ]]; then
      basic_fail \
        "An unexpected process matches the invalid $service PID signature"
      return
    fi
    matching_pids+=("$pid")
  done <<<"$process_list"
  for pid in "${matching_pids[@]+"${matching_pids[@]}"}"; do
    local presence
    presence="$(basic_inspect_pid_presence "$pid")" || return
    [[ "$presence" == "present" ]] || continue
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return
    cwd="$(basic_process_cwd "$pid")" || return
    if [[ "$command" != *"$signature"* ]] || [[ "$cwd" != "$expected_cwd" ]]; then
      basic_fail "$service identity changed during PID reconciliation"
      return
    fi
    kill "$pid" || return
  done
  for pid in "${matching_pids[@]+"${matching_pids[@]}"}"; do
    basic_wait_for_process_exit "$pid" || {
      basic_fail "$service did not stop during PID reconciliation"
      return
    }
  done
  basic_durable_remove_private_runtime_file "$pid_file" || return
}

basic_stop_managed_service() {
  local service="$1"
  local signature="$2"
  local expected_cwd="$3"
  local pid_file="$RUNTIME_DIR/pids/$service.pid"
  [[ -f "$pid_file" ]] || return 0

  local pid command cwd
  pid="$(<"$pid_file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || (( pid <= 1 )); then
    basic_reconcile_torn_managed_pid \
      "$service" "$signature" "$expected_cwd" || return
    return 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || {
      kill -0 "$pid" 2>/dev/null || {
        basic_durable_remove_private_runtime_file "$pid_file" || return
        return 0
      }
      basic_fail "Could not inspect the live $service process command"
      return
    }
    cwd="$(basic_process_cwd "$pid")" || {
      kill -0 "$pid" 2>/dev/null || {
        basic_durable_remove_private_runtime_file "$pid_file" || return
        return 0
      }
      basic_fail "Could not inspect the live $service process directory"
      return
    }
    if ! kill -0 "$pid" 2>/dev/null; then
      basic_durable_remove_private_runtime_file "$pid_file" || return
      return 0
    fi
    if [[ "$command" != *"$signature"* ]] || [[ "$cwd" != "$expected_cwd" ]]; then
      basic_fail "The $service PID belongs to an unexpected process; refusing to signal it"
      return
    fi
    kill "$pid" || return
    if ! basic_wait_for_process_exit "$pid"; then
      basic_fail "$service did not quiesce after SIGTERM"
      return
    fi
  fi
  basic_durable_remove_private_runtime_file "$pid_file" || return
}

basic_stop_api_listener() {
  local listener_pids=()
  local pid command cwd expected_backend_root
  expected_backend_root="$(basic_expected_backend_runtime_root)" || return
  local listener_output
  listener_output="$(basic_collect_tcp_listener_pids 3002)" || return
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && listener_pids+=("$pid")
  done <<<"$listener_output"

  for pid in "${listener_pids[@]+"${listener_pids[@]}"}"; do
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return
    cwd="$(basic_process_cwd "$pid")" || return
    if [[ "$command" != *"uvicorn app.main:app"* ]] || \
       [[ "$cwd" != "$expected_backend_root" ]]; then
      basic_fail "Port 3002 is owned by an unexpected process; refusing to signal it"
      return
    fi
  done
  for pid in "${listener_pids[@]+"${listener_pids[@]}"}"; do
    kill -0 "$pid" 2>/dev/null || continue
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return
    cwd="$(basic_process_cwd "$pid")" || return
    kill -0 "$pid" 2>/dev/null || continue
    if [[ "$command" != *"uvicorn app.main:app"* ]] || \
       [[ "$cwd" != "$expected_backend_root" ]]; then
      basic_fail "API listener identity changed before signal; refusing to signal it"
      return
    fi
    kill "$pid" || return
  done
  for pid in "${listener_pids[@]+"${listener_pids[@]}"}"; do
    if ! basic_wait_for_process_exit "$pid"; then
      basic_fail "The CareSync API listener did not quiesce after SIGTERM"
      return
    fi
  done
  listener_output="$(basic_collect_tcp_listener_pids 3002)" || return
  if [[ -n "$listener_output" ]]; then
    basic_fail "Port 3002 still has a listener"
    return
  fi
}

basic_assert_no_writer_processes() {
  local pid command cwd process_list expected_backend_root
  expected_backend_root="$(basic_expected_backend_runtime_root)" || return
  process_list="$(ps -ax -o pid=,command=)" || {
    basic_fail "Could not enumerate processes while proving writer quiescence"
    return
  }
  while read -r pid command; do
    [[ -n "$pid" ]] || continue
    if [[ "$command" == *"uvicorn app.main:app"*"--port 3002"* ]]; then
      cwd="$(basic_process_cwd "$pid")" || return
      if [[ "$cwd" != "$expected_backend_root" ]]; then
        basic_fail "A CareSync-signature API writer is running from an unexpected directory"
        return
      fi
      basic_fail "A CareSync API writer is still running as PID $pid"
      return
    elif [[ "$command" == *"scripts/push_worker.py"* ]]; then
      cwd="$(basic_process_cwd "$pid")" || return
      if [[ "$cwd" != "$expected_backend_root" ]]; then
        basic_fail "A CareSync-signature push writer is running from an unexpected directory"
        return
      fi
      basic_fail "A CareSync push writer is still running as PID $pid"
      return
    fi
  done <<<"$process_list"
}

basic_stop_frontend_listener() {
  local listener_pids=()
  local pid command cwd expected_frontend_root
  expected_frontend_root="$(basic_expected_frontend_runtime_root)" || return
  local listener_output
  listener_output="$(basic_collect_tcp_listener_pids 5174)" || return
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && listener_pids+=("$pid")
  done <<<"$listener_output"
  for pid in "${listener_pids[@]+"${listener_pids[@]}"}"; do
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return
    cwd="$(basic_process_cwd "$pid")" || return
    if [[ "$cwd" != "$expected_frontend_root/dist" ]] || \
       [[ "$command" != *"serve_basic_frontend.py"* ]]; then
      basic_fail "Port 5174 is owned by an unexpected process; refusing to signal it"
      return
    fi
  done
  for pid in "${listener_pids[@]+"${listener_pids[@]}"}"; do
    kill -0 "$pid" 2>/dev/null || continue
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return
    cwd="$(basic_process_cwd "$pid")" || return
    kill -0 "$pid" 2>/dev/null || continue
    if [[ "$cwd" != "$expected_frontend_root/dist" ]] || \
       [[ "$command" != *"serve_basic_frontend.py"* ]]; then
      basic_fail "Frontend listener identity changed before signal; refusing to signal it"
      return
    fi
    kill "$pid" || return
  done
  for pid in "${listener_pids[@]+"${listener_pids[@]}"}"; do
    if ! basic_wait_for_process_exit "$pid"; then
      basic_fail "The CareSync frontend listener did not quiesce after SIGTERM"
      return
    fi
  done
  listener_output="$(basic_collect_tcp_listener_pids 5174)" || return
  if [[ -n "$listener_output" ]]; then
    basic_fail "Port 5174 still has a listener"
    return
  fi
  basic_durable_remove_private_runtime_file \
    "$RUNTIME_DIR/pids/frontend.pid" || return
}

basic_assert_managed_service_running() {
  local service="$1"
  local signature="$2"
  local expected_cwd="$3"
  local pid_file="$RUNTIME_DIR/pids/$service.pid"
  if [[ -L "$pid_file" ]] || [[ ! -f "$pid_file" ]]; then
    basic_fail "CareSync $service PID file is missing or unsafe"
    return
  fi
  local pid command cwd
  pid="$(<"$pid_file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    basic_fail "CareSync $service process is not running"
    return
  fi
  command="$(ps -p "$pid" -o command= 2>/dev/null)" || return
  cwd="$(basic_process_cwd "$pid")" || return
  kill -0 "$pid" 2>/dev/null || {
    basic_fail "CareSync $service process exited during identity verification"
    return
  }
  if [[ "$command" != *"$signature"* ]] || [[ "$cwd" != "$expected_cwd" ]]; then
    basic_fail "CareSync $service process has unexpected identity"
    return
  fi
}

basic_assert_frontend_listener_provenance() {
  local count=0
  local pid command cwd listener_output expected_frontend_root
  expected_frontend_root="$(basic_expected_frontend_runtime_root)" || return
  listener_output="$(basic_collect_tcp_listener_pids 5174)" || return
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    (( count += 1 ))
    command="$(ps -p "$pid" -o command= 2>/dev/null)" || return
    cwd="$(basic_process_cwd "$pid")" || return
    if [[ "$cwd" != "$expected_frontend_root/dist" ]] || \
       [[ "$command" != *"serve_basic_frontend.py"* ]]; then
      basic_fail "Port 5174 listener is not the CareSync frontend"
      return
    fi
  done <<<"$listener_output"
  if (( count == 0 )); then
    basic_fail "CareSync frontend has no port 5174 listener"
    return
  fi
}

basic_quiesce_application() {
  local failed=false
  local expected_backend_root expected_frontend_root
  expected_backend_root="$(basic_expected_backend_runtime_root)" || return
  expected_frontend_root="$(basic_expected_frontend_runtime_root)" || return
  basic_reconcile_managed_launch \
    "frontend" "serve_basic_frontend.py" \
    "$expected_frontend_root/dist" || failed=true
  basic_reconcile_managed_launch \
    "backend" "uvicorn app.main:app" "$expected_backend_root" || failed=true
  basic_reconcile_managed_launch \
    "push-worker" "scripts/push_worker.py" \
    "$expected_backend_root" || failed=true
  basic_stop_managed_service \
    "frontend" "serve_basic_frontend.py" \
    "$expected_frontend_root/dist" || failed=true
  basic_stop_managed_service \
    "backend" "uvicorn app.main:app" "$expected_backend_root" || failed=true
  basic_stop_managed_service \
    "push-worker" "scripts/push_worker.py" "$expected_backend_root" || failed=true
  basic_stop_api_listener || failed=true
  basic_stop_frontend_listener || failed=true
  basic_assert_no_writer_processes || failed=true
  if [[ "$failed" == "true" ]]; then
    basic_fail "CareSync application quiescence could not be proven"
    return
  fi
}

basic_assert_no_database_clients() {
  local count=""
  local attempt
  for attempt in {1..80}; do
    count="$(basic_psql_scalar \
      "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid()")"
    if [[ "$count" == "0" ]]; then
      return 0
    fi
    sleep 0.125
  done
  basic_fail "Retained database still has another client session; release remains fenced"
}

basic_assert_no_cluster_clients() {
  local count=""
  local attempt
  for attempt in {1..80}; do
    count="$(basic_psql_scalar \
      "SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()")"
    if [[ "$count" == "0" ]]; then
      return 0
    fi
    sleep 0.125
  done
  basic_fail \
    "Retained PostgreSQL still has another client session anywhere in the cluster"
}

basic_require_app_login_state() {
  local expected="$1"
  local actual
  actual="$(basic_psql_scalar \
    "SELECT CASE WHEN rolcanlogin THEN 'login' ELSE 'nologin' END FROM pg_roles WHERE rolname='caresync_basic_app'")"
  if [[ "$actual" != "$expected" ]]; then
    basic_fail "caresync_basic_app must be $expected for this operation"
    return
  fi
}

basic_role_login_state() {
  local role="$1"
  local actual
  actual="$(basic_psql_scalar \
    "SELECT CASE WHEN rolcanlogin THEN 'login' ELSE 'nologin' END FROM pg_roles WHERE rolname='$role'")"
  if [[ "$actual" != "login" && "$actual" != "nologin" ]]; then
    basic_fail "Required CareSync runtime role is missing: $role"
    return
  fi
  printf '%s\n' "$actual"
}

basic_set_role_login_state() {
  local role="$1"
  local target="$2"
  if [[ "$role" != "caresync_basic_app" && \
        "$role" != "caresync_transport_evidence_ingest" && \
        "$role" != "$RELEASE_PROBE_USER" ]]; then
    basic_fail "Refusing to change an unknown CareSync runtime role"
    return
  fi
  case "$target" in
    login)
      basic_psql_scalar "ALTER ROLE $role LOGIN" >/dev/null
      ;;
    nologin)
      basic_psql_scalar "ALTER ROLE $role NOLOGIN" >/dev/null
      ;;
    *)
      basic_fail "Unknown CareSync role login state: $target"
      return
      ;;
  esac
  if [[ "$(basic_role_login_state "$role")" != "$target" ]]; then
    basic_fail "CareSync runtime role did not reach $target: $role"
    return
  fi
}

basic_set_app_login_state() {
  basic_set_role_login_state "caresync_basic_app" "$1"
}

basic_require_runtime_roles_fenced() {
  if [[ "$(basic_role_login_state caresync_basic_app)" != "nologin" ]] || \
     [[ "$(basic_role_login_state caresync_transport_evidence_ingest)" != "nologin" ]]; then
    basic_fail "Every CareSync database writer role must remain NOLOGIN"
    return
  fi
}

basic_cleanup_appledouble_sidecars() {
  local directory failed=false
  for directory in \
    "$ROOT/backend/alembic" \
    "$ROOT/backend/app" \
    "$ROOT/backend/tests" \
    "$ROOT/frontend-redesign/src"; do
    if [[ -d "$directory" ]] && [[ ! -L "$directory" ]]; then
      find "$directory" -type f -name '._*' -delete || failed=true
    fi
  done
  if [[ "$failed" == "true" ]]; then
    basic_fail "CareSync AppleDouble sidecar cleanup was incomplete"
    return
  fi
}

basic_require_no_release_fence() {
  if [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; then
    basic_fail "CareSync retained release is fenced; commit or explicitly resume the prepared release"
    return
  fi
}

basic_run_backend_python() {
  (
    cd "$ROOT/backend"
    CARESYNC_VENV_PATH="$VENV_PATH" /bin/bash ./scripts/uv.sh run python "$@"
  )
}
