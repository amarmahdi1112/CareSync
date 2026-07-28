#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/basic-runtime.sh
source "$ROOT/scripts/lib/basic-runtime.sh"

load_runtime_configuration() {
  local installed_root="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}"
  local external_env="$installed_root/backend/.env"
  if [[ "${CARESYNC_BASIC_RUNTIME_CONFIG_LOADED:-}" == \
    "caresync-basic-runtime-config-v1" ]]; then
    "$VENV_PATH/bin/python" \
      "$ROOT/backend/scripts/basic_runtime_config.py" validate
    return
  fi
  exec "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/basic_runtime_config.py" exec \
      --source-env "$external_env" \
      -- /bin/bash "$0" "$@"
}

if [[ "${1:-}" != "--help" ]] && [[ "${1:-}" != "-h" ]]; then
  load_runtime_configuration "$@"
fi

basic_reexec_with_state_change_lock "$0" "$@"

EXPECTED_REVISION="$CARESYNC_RETAINED_TARGET_REVISION"
START_LABEL="released"
RELEASE_START_KIND="normal"
CANDIDATE_RECEIPT=""
RESUME_AUTHORIZATION=""
COMMIT_RECEIPT=""
NORMAL_PENDING_ROLE_RECOVERY=false

case "${1:-}" in
  "")
    ;;
  --resume-0039)
    if [[ "$#" != "5" ]] || [[ "$2" != "--receipt" ]] || \
       [[ "$4" != "--authorization" ]]; then
      basic_fail "0039 startup requires a candidate receipt and resume authorization"
      exit 2
    fi
    CANDIDATE_RECEIPT="$3"
    RESUME_AUTHORIZATION="$5"
    EXPECTED_REVISION="$CARESYNC_RETAINED_SOURCE_REVISION"
    START_LABEL="explicitly resumed"
    RELEASE_START_KIND="resume"
    ;;
  --commit-0042)
    if [[ "$#" != "5" ]] || [[ "$2" != "--receipt" ]] || \
       [[ "$4" != "--commit-receipt" ]]; then
      basic_fail "0042 release startup requires candidate and commit receipts"
      exit 2
    fi
    CANDIDATE_RECEIPT="$3"
    COMMIT_RECEIPT="$5"
    RELEASE_START_KIND="commit"
    ;;
  --rollback-0039)
    if [[ "$#" != "5" ]] || [[ "$2" != "--receipt" ]] || \
       [[ "$4" != "--authorization" ]]; then
      basic_fail "Rollback startup requires a candidate receipt and authorization"
      exit 2
    fi
    CANDIDATE_RECEIPT="$3"
    RESUME_AUTHORIZATION="$5"
    EXPECTED_REVISION="$CARESYNC_RETAINED_SOURCE_REVISION"
    START_LABEL="emergency rollback resumed"
    RELEASE_START_KIND="rollback"
    ;;
  --help|-h)
    printf '%s\n' \
      "Usage: scripts/start-basic.sh" \
      "       scripts/resume-basic-0039.sh --receipt RECEIPT --confirm PHRASE" \
      "       scripts/basic-release.sh commit --receipt RECEIPT --confirm PHRASE" \
      "       scripts/basic-release.sh rollback --receipt RECEIPT --commit-receipt RECEIPT --finalization-receipt RECEIPT --confirm PHRASE" \
      "       scripts/basic-release.sh rollback --receipt RECEIPT --confirm PHRASE  # interrupted commit intent only"
    exit 0
    ;;
  *)
    basic_fail "Use ordinary start or a receipt-controlled release entry point"
    exit 2
    ;;
esac

# This launcher is deliberately not a release tool. It never creates a
# database backup, restores data or invokes Alembic. A prepared fence blocks
# ordinary startup. Receipt-certified release/resume modes keep that fence in
# place through service health and discharge it only through post-health proof.
basic_require_local_toolchain
basic_require_runtime_layout
basic_normalize_known_runtime_files

enter_active_epoch_source() {
  ACTIVE_EPOCH_RUN="$(
    basic_private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" run_directory
  )" || return
  EXPECTED_REVISION="$(
    basic_private_context_value "$ACTIVE_RELEASE_EPOCH_FILE" revision
  )" || return
  ACTIVE_EPOCH_SOURCE_ROOT="$ACTIVE_EPOCH_RUN/release-source"
  if [[ "$ROOT" != "$ACTIVE_EPOCH_SOURCE_ROOT" ]]; then
    export CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}"
    exec /bin/bash "$ACTIVE_EPOCH_SOURCE_ROOT/scripts/start-basic.sh"
  fi
}

case "$RELEASE_START_KIND" in
  normal)
    PENDING_ROLE_SOURCE="$(
      /bin/bash "$ROOT/scripts/basic-release.sh" \
        _pending-post-retirement-recovery-source
    )"
    if [[ "$PENDING_ROLE_SOURCE" != "none" ]]; then
      NORMAL_PENDING_ROLE_RECOVERY=true
      if [[ "$ROOT" != "$PENDING_ROLE_SOURCE" ]]; then
        export CARESYNC_INSTALLED_DEPENDENCY_ROOT="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}"
        exec /bin/bash "$PENDING_ROLE_SOURCE/scripts/start-basic.sh"
      fi
    elif [[ -e "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]] || \
         [[ -L "$POST_RETIREMENT_ROLE_RESTORATION_PENDING" ]]; then
      NORMAL_PENDING_ROLE_RECOVERY=true
    fi
    /bin/bash "$ROOT/scripts/basic-release.sh" _preflight-normal-start
    if [[ "$NORMAL_PENDING_ROLE_RECOVERY" != "true" ]]; then
      enter_active_epoch_source
    fi
    ;;
  resume)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _preflight-controlled-start \
      resume "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
    ;;
  commit)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _preflight-controlled-start \
      commit "$CANDIDATE_RECEIPT" "$COMMIT_RECEIPT"
    ;;
  rollback)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _preflight-controlled-start \
      rollback "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
    ;;
esac
basic_start_postgres
basic_verify_retained_identity
basic_cleanup_appledouble_sidecars
if [[ "$RELEASE_START_KIND" == "normal" ]]; then
  /bin/bash "$ROOT/scripts/basic-release.sh" _recover-post-retirement-roles
  if [[ "$NORMAL_PENDING_ROLE_RECOVERY" == "true" ]]; then
    /bin/bash "$ROOT/scripts/basic-release.sh" _preflight-normal-start
    enter_active_epoch_source
  fi
  basic_require_exact_revision "$EXPECTED_REVISION"
  basic_require_app_login_state "login"
else
  case "$RELEASE_START_KIND" in
    resume)
      /bin/bash "$ROOT/scripts/basic-release.sh" \
        _verify-resume-start "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
      ;;
    commit)
      /bin/bash "$ROOT/scripts/basic-release.sh" \
        _verify-commit-start "$CANDIDATE_RECEIPT" "$COMMIT_RECEIPT"
      ;;
    rollback)
      /bin/bash "$ROOT/scripts/basic-release.sh" \
        _verify-rollback-start "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
      ;;
  esac
  basic_require_runtime_roles_fenced
fi

API_BIND_HOST="${CARESYNC_BASIC_API_HOST:-127.0.0.1}"
APP_PASSWORD="${CARESYNC_BASIC_APP_PASSWORD:-}"
RUNTIME_DATABASE_USER="$APP_USER"
RUNTIME_DATABASE_PASSWORD="$APP_PASSWORD"
RUNTIME_DATABASE_READ_ONLY=false
if [[ "$RELEASE_START_KIND" != "normal" ]]; then
  CONTROLLED_PROBE_CREDENTIAL="$(
    dirname "$CANDIDATE_RECEIPT"
  )/controlled-health-probe.credential"
  if [[ -L "$CONTROLLED_PROBE_CREDENTIAL" ]] || \
     [[ ! -f "$CONTROLLED_PROBE_CREDENTIAL" ]]; then
    basic_fail "Controlled-health probe credential is unavailable"
    exit 1
  fi
  RUNTIME_DATABASE_USER="$RELEASE_PROBE_USER"
  RUNTIME_DATABASE_PASSWORD="$(<"$CONTROLLED_PROBE_CREDENTIAL")"
  RUNTIME_DATABASE_READ_ONLY=true
fi
PUSH_WORKER_POLL_SECONDS="${CARESYNC_PUSH_WORKER_POLL_SECONDS:-5}"
BILLING_RUNTIME_MODE="${CARESYNC_BASIC_BILLING_MODE:-manual}"
BILLING_MANUAL_ORGANIZATION_IDS="${CARESYNC_BASIC_BILLING_MANUAL_ORGANIZATION_IDS:-}"
FAMILY_EVIDENCE_VAULT_PATH="$RUNTIME_DIR/private-family-authority-vault"
STAFF_SCREENING_VAULT_PATH="$RUNTIME_DIR/private-staff-screening-vault"

if [[ "$BILLING_RUNTIME_MODE" != "disabled" ]] && \
   [[ "$BILLING_RUNTIME_MODE" != "manual" ]]; then
  basic_fail "CARESYNC_BASIC_BILLING_MODE must be disabled or manual"
  exit 1
fi

for private_vault in "$FAMILY_EVIDENCE_VAULT_PATH" "$STAFF_SCREENING_VAULT_PATH"; do
  if [[ -L "$private_vault" ]] || [[ -e "$private_vault" && ! -d "$private_vault" ]]; then
    basic_fail "A CareSync private vault path is unsafe; refusing startup"
    exit 1
  fi
  basic_durable_ensure_private_runtime_directory "$private_vault" || exit 1
  if [[ "$(stat -f '%u' "$private_vault")" != "$(id -u)" ]] || \
     [[ "$(stat -f '%Lp' "$private_vault")" != "700" ]]; then
    basic_fail "A CareSync private vault must be owner-controlled mode 0700"
    exit 1
  fi
done
(
  cd "$ROOT/backend"
  CARESYNC_VENV_PATH="$VENV_PATH" \
    /bin/bash ./scripts/uv.sh run python scripts/basic_runtime_secrets.py \
      --runtime-directory "$RUNTIME_DIR"
)
RUNTIME_SECRET_DIRECTORY="$RUNTIME_DIR/secrets"
STAFF_SCREENING_VAULT_ENCRYPTION_KEY="$(
  <"$RUNTIME_SECRET_DIRECTORY/staff-screening-vault.key"
)"
TRANSPORT_EVIDENCE_INGEST_PASSWORD="$(
  <"$RUNTIME_SECRET_DIRECTORY/transport-evidence-ingest.password"
)"
secret_pattern='^[A-Za-z0-9_-]{43}$'
if [[ ! "$STAFF_SCREENING_VAULT_ENCRYPTION_KEY" =~ $secret_pattern ]] || \
   [[ ! "$TRANSPORT_EVIDENCE_INGEST_PASSWORD" =~ $secret_pattern ]] || \
   [[ "$STAFF_SCREENING_VAULT_ENCRYPTION_KEY" == "$TRANSPORT_EVIDENCE_INGEST_PASSWORD" ]] || \
   [[ -n "$APP_PASSWORD" && "$TRANSPORT_EVIDENCE_INGEST_PASSWORD" == "$APP_PASSWORD" ]]; then
  basic_fail "CareSync private runtime secrets are invalid; refusing startup"
  exit 1
fi

STARTUP_COMPLETE=false
startup_cleanup() {
  local result=$?
  if [[ "$STARTUP_COMPLETE" != "true" ]]; then
    local quiesced=false
    if basic_quiesce_application; then
      quiesced=true
      if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q; then
        basic_assert_no_cluster_clients || quiesced=false
      fi
    fi
    if [[ "$RELEASE_START_KIND" != "normal" ]] && \
       [[ "$quiesced" == "true" ]]; then
      case "$RELEASE_START_KIND" in
        resume)
          /bin/bash "$ROOT/scripts/basic-release.sh" \
            _recover-incomplete-resume-start \
            "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION" || quiesced=false
          ;;
        commit)
          /bin/bash "$ROOT/scripts/basic-release.sh" \
            _recover-incomplete-commit-start \
            "$CANDIDATE_RECEIPT" "$COMMIT_RECEIPT" || quiesced=false
          ;;
        rollback)
          /bin/bash "$ROOT/scripts/basic-release.sh" \
            _recover-incomplete-rollback-start \
            "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION" || quiesced=false
          ;;
      esac
    fi
    if [[ "$RELEASE_START_KIND" != "normal" ]] && \
       [[ "$quiesced" != "true" ]] && \
       { [[ -e "$RELEASE_FENCE_DIRECTORY" ]] || \
         [[ -L "$RELEASE_FENCE_DIRECTORY" ]]; }; then
      if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q && \
         basic_verify_retained_identity; then
        if ! /bin/bash "$ROOT/scripts/basic-release.sh" \
          _fence-runtime-roles; then
          # Preserve the old last-ditch NOLOGIN behavior even when complete
          # ACL scrubbing cannot be attested.
          basic_set_app_login_state "nologin" || true
          basic_set_role_login_state \
            caresync_transport_evidence_ingest nologin || true
          basic_set_role_login_state "$RELEASE_PROBE_USER" nologin || true
        fi
      else
        basic_fail \
          "Retained identity unavailable; preserving the active fence without SQL cleanup"
      fi
    fi
  fi
  return "$result"
}
trap startup_cleanup EXIT

# Only after the complete local dependency/vault/secret preflight succeeds may
# an existing healthy runtime be quiesced or credentials be changed.
basic_quiesce_application

# Password provisioning is deferred until after a controlled fence is retired.
# The health runtime authenticates only as the dedicated database-enforced
# read-only probe and never needs an application credential.
configure_writable_runtime_credentials() {
  (
    cd "$ROOT/backend"
    CARESYNC_VENV_PATH="$VENV_PATH" \
      /bin/bash ./scripts/uv.sh run python \
        scripts/configure_basic_runtime_credentials.py \
        --runtime-directory "$RUNTIME_DIR" \
        --host 127.0.0.1 \
        --port "$PGPORT" \
        --database "$DATABASE_NAME" \
        --migration-user "$MIGRATION_USER"
  )
}
if [[ "$RELEASE_START_KIND" == "normal" ]]; then
  configure_writable_runtime_credentials
fi
basic_require_exact_revision "$EXPECTED_REVISION"
if [[ "$RELEASE_START_KIND" == "normal" ]]; then
  basic_require_app_login_state "login"
else
  basic_require_runtime_roles_fenced
fi

BILLING_MANUAL_TARGET_ATTESTATION=""
BILLING_MANUAL_READY=false
if [[ "$BILLING_RUNTIME_MODE" == "manual" ]]; then
  if [[ -z "$BILLING_MANUAL_ORGANIZATION_IDS" ]]; then
    active_organization_count="$(basic_psql_scalar \
      "SELECT count(*) FROM organizations WHERE status='active'")"
    if [[ "$active_organization_count" == "1" ]]; then
      BILLING_MANUAL_ORGANIZATION_IDS="$(basic_psql_scalar \
        "SELECT id::text FROM organizations WHERE status='active'")"
      BILLING_MANUAL_READY=true
    elif [[ "$active_organization_count" != "0" ]]; then
      basic_fail "Manual billing needs CARESYNC_BASIC_BILLING_MANUAL_ORGANIZATION_IDS when more than one active organization exists"
      exit 1
    fi
  else
    normalized_billing_organization_ids=""
    requested_billing_organization_ids=()
    IFS=',' read -r -a requested_billing_organization_ids \
      <<<"$BILLING_MANUAL_ORGANIZATION_IDS"
    if (( ${#requested_billing_organization_ids[@]} == 0 )); then
      basic_fail "Manual billing organization allowlist cannot be empty"
      exit 1
    fi
    for requested_billing_organization_id in \
      "${requested_billing_organization_ids[@]+"${requested_billing_organization_ids[@]}"}"; do
      requested_billing_organization_id="$(
        printf '%s' "$requested_billing_organization_id" | tr -d '[:space:]'
      )"
      if [[ ! "$requested_billing_organization_id" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]; then
        basic_fail "Manual billing organization allowlist contains an invalid UUID"
        exit 1
      fi
      validated_billing_organization_id="$(basic_psql_scalar \
        "SELECT id::text FROM organizations WHERE status='active' AND id='$requested_billing_organization_id'::uuid")"
      if [[ -z "$validated_billing_organization_id" ]]; then
        basic_fail "Manual billing allowlist must contain only active local organization UUIDs"
        exit 1
      fi
      [[ -z "$normalized_billing_organization_ids" ]] || \
        normalized_billing_organization_ids+=","
      normalized_billing_organization_ids+="$validated_billing_organization_id"
    done
    if [[ -z "$normalized_billing_organization_ids" ]]; then
      basic_fail "Manual billing organization allowlist cannot be empty"
      exit 1
    fi
    BILLING_MANUAL_ORGANIZATION_IDS="$normalized_billing_organization_ids"
    BILLING_MANUAL_READY=true
  fi
  BILLING_MANUAL_TARGET_ATTESTATION="PRIVATE_LOCAL_MANUAL_BILLING"
else
  BILLING_MANUAL_ORGANIZATION_IDS=""
fi

push_pid_file="$RUNTIME_DIR/pids/push-worker.pid"
push_provider_ready=no
detect_push_provider() {
  (
    cd "$ROOT/backend"
    CARESYNC_VENV_PATH="$VENV_PATH" \
    ENVIRONMENT=development \
    DATABASE_TYPE=postgres \
    DATABASE_HOST=127.0.0.1 \
    DATABASE_PORT="$PGPORT" \
    DATABASE_USER="$APP_USER" \
    DATABASE_PASSWORD="$APP_PASSWORD" \
    DATABASE_NAME="$DATABASE_NAME" \
    DATABASE_READ_ONLY=false \
    ENABLE_ADVANCED_ROUTES=false \
    BILLING_MODE="$BILLING_RUNTIME_MODE" \
    BILLING_MANUAL_TARGET_ATTESTATION="$BILLING_MANUAL_TARGET_ATTESTATION" \
    BILLING_MANUAL_ORGANIZATION_IDS="$BILLING_MANUAL_ORGANIZATION_IDS" \
    FAMILY_EVIDENCE_VAULT_PATH="$FAMILY_EVIDENCE_VAULT_PATH" \
    STAFF_SCREENING_VAULT_PATH="$STAFF_SCREENING_VAULT_PATH" \
    STAFF_SCREENING_VAULT_ENCRYPTION_KEY="$STAFF_SCREENING_VAULT_ENCRYPTION_KEY" \
    TRANSPORT_EVIDENCE_INGEST_PASSWORD="$TRANSPORT_EVIDENCE_INGEST_PASSWORD" \
      /bin/bash ./scripts/uv.sh run python -c \
        'from app.basic.push import build_push_provider; from app.core.config import Settings; print("yes" if build_push_provider(Settings()) else "no")'
  )
}
if [[ "$RELEASE_START_KIND" == "normal" ]]; then
  push_provider_ready="$(detect_push_provider 2>/dev/null)" || exit
fi

launch_push_worker_detached() {
    local nonce
    nonce="$(
      basic_prepare_managed_launch \
        "push-worker" "scripts/push_worker.py" "$ROOT/backend"
    )" || return
    cd "$ROOT/backend"
    CARESYNC_VENV_PATH="$VENV_PATH" \
    ENVIRONMENT=development \
    DATABASE_TYPE=postgres \
    DATABASE_HOST=127.0.0.1 \
    DATABASE_PORT="$PGPORT" \
    DATABASE_USER="$APP_USER" \
    DATABASE_PASSWORD="$APP_PASSWORD" \
    DATABASE_NAME="$DATABASE_NAME" \
    DATABASE_READ_ONLY=false \
    ENABLE_ADVANCED_ROUTES=false \
    BILLING_MODE="$BILLING_RUNTIME_MODE" \
    BILLING_MANUAL_TARGET_ATTESTATION="$BILLING_MANUAL_TARGET_ATTESTATION" \
    BILLING_MANUAL_ORGANIZATION_IDS="$BILLING_MANUAL_ORGANIZATION_IDS" \
    FAMILY_EVIDENCE_VAULT_PATH="$FAMILY_EVIDENCE_VAULT_PATH" \
    STAFF_SCREENING_VAULT_PATH="$STAFF_SCREENING_VAULT_PATH" \
    STAFF_SCREENING_VAULT_ENCRYPTION_KEY="$STAFF_SCREENING_VAULT_ENCRYPTION_KEY" \
    TRANSPORT_EVIDENCE_INGEST_PASSWORD="$TRANSPORT_EVIDENCE_INGEST_PASSWORD" \
      nohup "$VENV_PATH/bin/python" \
        "$ROOT/backend/scripts/gated_service_exec.py" hold \
          --intent "$RUNTIME_DIR/pids/push-worker.launching" \
          --gate "$RUNTIME_DIR/pids/push-worker.gate" \
          --pid-file "$RUNTIME_DIR/pids/push-worker.pid" \
          --service push-worker \
          --nonce "$nonce" \
          --expected-cwd "$ROOT/backend" \
          --signature "scripts/push_worker.py" \
          --timeout-seconds 15 \
          -- /bin/bash ./scripts/uv.sh run python scripts/push_worker.py \
            --poll "$PUSH_WORKER_POLL_SECONDS" \
        >"$RUNTIME_DIR/logs/push-worker.log" 2>&1 &
    local child_pid="$!"
    if ! basic_publish_managed_pid "push-worker" "$child_pid"; then
      kill "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
      return 1
    fi
    if ! basic_publish_managed_launch_gate \
      "push-worker" "$nonce" "$child_pid"; then
      kill "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
      return 1
    fi
}

start_push_worker() {
  if [[ "$push_provider_ready" == "yes" ]]; then
    basic_run_guarded_without_state_lock_in_child \
      launch_push_worker_detached || return
  else
    printf '%s\n' \
      '{"provider_disabled":true,"message":"Push worker not started; provider configuration is incomplete."}' \
      >"$RUNTIME_DIR/logs/push-worker.log"
  fi
}

# A controlled commit/resume/rollback must recapture and finalize exact
# database evidence before a queued push worker is allowed to mutate outbox
# rows. Ordinary exact-0042 startup has no candidate digest to preserve.
if [[ "$RELEASE_START_KIND" == "normal" ]]; then
  start_push_worker
fi

launch_backend_detached() {
  local database_user="$1"
  local database_password="$2"
  local database_read_only="$3"
  local nonce
  nonce="$(
    basic_prepare_managed_launch \
      "backend" "uvicorn app.main:app" "$ROOT/backend"
  )" || return
  cd "$ROOT/backend"
  CARESYNC_VENV_PATH="$VENV_PATH" \
  APP_NAME="CareSync Basic" \
  ENVIRONMENT=development \
  PORT=3002 \
  DATABASE_TYPE=postgres \
  DATABASE_HOST=127.0.0.1 \
  DATABASE_PORT="$PGPORT" \
  DATABASE_USER="$database_user" \
  DATABASE_PASSWORD="$database_password" \
  DATABASE_NAME="$DATABASE_NAME" \
  DATABASE_READ_ONLY="$database_read_only" \
  ENABLE_ADVANCED_ROUTES=false \
  BILLING_MODE="$BILLING_RUNTIME_MODE" \
  BILLING_MANUAL_TARGET_ATTESTATION="$BILLING_MANUAL_TARGET_ATTESTATION" \
  BILLING_MANUAL_ORGANIZATION_IDS="$BILLING_MANUAL_ORGANIZATION_IDS" \
  FAMILY_EVIDENCE_VAULT_PATH="$FAMILY_EVIDENCE_VAULT_PATH" \
  STAFF_SCREENING_VAULT_PATH="$STAFF_SCREENING_VAULT_PATH" \
  STAFF_SCREENING_VAULT_ENCRYPTION_KEY="$STAFF_SCREENING_VAULT_ENCRYPTION_KEY" \
  TRANSPORT_EVIDENCE_INGEST_PASSWORD="$TRANSPORT_EVIDENCE_INGEST_PASSWORD" \
    nohup "$VENV_PATH/bin/python" \
      "$ROOT/backend/scripts/gated_service_exec.py" hold \
        --intent "$RUNTIME_DIR/pids/backend.launching" \
        --gate "$RUNTIME_DIR/pids/backend.gate" \
        --pid-file "$RUNTIME_DIR/pids/backend.pid" \
        --service backend \
        --nonce "$nonce" \
        --expected-cwd "$ROOT/backend" \
        --signature "uvicorn app.main:app" \
        --timeout-seconds 15 \
        -- /bin/bash ./scripts/uv.sh run uvicorn app.main:app \
          --host "$API_BIND_HOST" --port 3002 \
      >"$RUNTIME_DIR/logs/backend.log" 2>&1 &
  local child_pid="$!"
  if ! basic_publish_managed_pid "backend" "$child_pid"; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
    return 1
  fi
  if ! basic_publish_managed_launch_gate \
    "backend" "$nonce" "$child_pid"; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
    return 1
  fi
}

verify_captured_runtime_source() {
  local run_directory
  run_directory="$(dirname "$ROOT")" || return
  if [[ "$ROOT" != "$RELEASE_STATE_DIRECTORY/"*"/release-source" ]] || \
     [[ "$run_directory" != "$RELEASE_STATE_DIRECTORY/"* ]]; then
    basic_fail "CareSync runtime did not re-execute from a captured release source"
    return
  fi
  PYTHONDONTWRITEBYTECODE=1 CARESYNC_PG_BIN="$PG_BIN" \
    CARESYNC_INSTALLED_NODE_MODULES="${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}/frontend-redesign/node_modules" \
    "$VENV_PATH/bin/python" \
      "$ROOT/backend/scripts/release_source_bundle.py" verify \
      --destination "$ROOT" \
      --manifest "$run_directory/release-source.manifest.json"
}

launch_frontend_detached() {
  local frontend_dist="$ROOT/frontend-redesign/dist"
  local nonce
  nonce="$(
    basic_prepare_managed_launch \
      "frontend" "serve_basic_frontend.py" "$frontend_dist"
  )" || return
  cd "$frontend_dist"
  nohup "$VENV_PATH/bin/python" \
    "$ROOT/backend/scripts/gated_service_exec.py" hold \
      --intent "$RUNTIME_DIR/pids/frontend.launching" \
      --gate "$RUNTIME_DIR/pids/frontend.gate" \
      --pid-file "$RUNTIME_DIR/pids/frontend.pid" \
      --service frontend \
      --nonce "$nonce" \
      --expected-cwd "$frontend_dist" \
      --signature "serve_basic_frontend.py" \
      --timeout-seconds 15 \
      -- "$VENV_PATH/bin/python" \
        "$ROOT/backend/scripts/serve_basic_frontend.py" \
          --root "$frontend_dist" --host 127.0.0.1 --port 5174 \
    >"$RUNTIME_DIR/logs/frontend.log" 2>&1 &
  local child_pid="$!"
  if ! basic_publish_managed_pid "frontend" "$child_pid"; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
    return 1
  fi
  if ! basic_publish_managed_launch_gate \
    "frontend" "$nonce" "$child_pid"; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
    return 1
  fi
}

start_application_runtime() {
  local database_user="$1"
  local database_password="$2"
  local database_read_only="$3"
  verify_captured_runtime_source || return
  basic_run_guarded_without_state_lock_in_child \
    launch_backend_detached \
      "$database_user" "$database_password" "$database_read_only" || return
  basic_run_guarded_without_state_lock_in_child \
    launch_frontend_detached || return
}

start_application_runtime \
  "$RUNTIME_DATABASE_USER" \
  "$RUNTIME_DATABASE_PASSWORD" \
  "$RUNTIME_DATABASE_READ_ONLY"

for url in http://127.0.0.1:3002/api/v1/health http://127.0.0.1:5174/; do
  for _ in {1..60}; do
    curl -fsS "$url" >/dev/null 2>&1 && break
    sleep 0.25
  done
  curl -fsS "$url" >/dev/null
done

basic_complete_managed_launch \
  "backend" "uvicorn app.main:app" "$ROOT/backend"
basic_complete_managed_launch \
  "frontend" "serve_basic_frontend.py" "$ROOT/frontend-redesign/dist"
basic_assert_managed_service_running \
  "backend" "uvicorn app.main:app" "$ROOT/backend"
basic_assert_managed_service_running \
  "frontend" "serve_basic_frontend.py" "$ROOT/frontend-redesign/dist"
basic_assert_frontend_listener_provenance
if [[ "$push_provider_ready" == "yes" ]] && \
   [[ "$RELEASE_START_KIND" == "normal" ]]; then
  basic_complete_managed_launch \
    "push-worker" "scripts/push_worker.py" "$ROOT/backend"
  basic_assert_managed_service_running \
    "push-worker" "scripts/push_worker.py" "$ROOT/backend"
fi

case "$RELEASE_START_KIND" in
  resume)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _finalize-resume-start "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
    ;;
  commit)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _finalize-commit-start "$CANDIDATE_RECEIPT" "$COMMIT_RECEIPT"
    ;;
  rollback)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _finalize-rollback-start "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
    ;;
esac
if [[ "$RELEASE_START_KIND" != "normal" ]]; then
  # Finalization has stopped the probe runtime, durably published the epoch,
  # retired the fence, and completed the retryable post-retirement role
  # restoration. Start a *fresh* writable application process only now.
  configure_writable_runtime_credentials
  basic_require_app_login_state "login"
  start_application_runtime "$APP_USER" "$APP_PASSWORD" false
  for url in \
    http://127.0.0.1:3002/api/v1/health \
    http://127.0.0.1:5174/; do
    for _ in {1..60}; do
      curl -fsS "$url" >/dev/null 2>&1 && break
      sleep 0.25
    done
    curl -fsS "$url" >/dev/null
  done
  basic_complete_managed_launch \
    "backend" "uvicorn app.main:app" "$ROOT/backend"
  basic_complete_managed_launch \
    "frontend" "serve_basic_frontend.py" "$ROOT/frontend-redesign/dist"
  basic_assert_managed_service_running \
    "backend" "uvicorn app.main:app" "$ROOT/backend"
  basic_assert_managed_service_running \
    "frontend" "serve_basic_frontend.py" "$ROOT/frontend-redesign/dist"
  basic_assert_frontend_listener_provenance
  push_provider_ready="$(detect_push_provider 2>/dev/null)" || exit
  start_push_worker
  if [[ "$push_provider_ready" == "yes" ]]; then
    basic_complete_managed_launch \
      "push-worker" "scripts/push_worker.py" "$ROOT/backend"
    basic_assert_managed_service_running \
      "push-worker" "scripts/push_worker.py" "$ROOT/backend"
  fi
fi
case "$RELEASE_START_KIND" in
  resume)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _complete-resume-start "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
    ;;
  commit)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _complete-commit-start "$CANDIDATE_RECEIPT" "$COMMIT_RECEIPT"
    ;;
  rollback)
    /bin/bash "$ROOT/scripts/basic-release.sh" \
      _complete-rollback-start "$CANDIDATE_RECEIPT" "$RESUME_AUTHORIZATION"
    ;;
esac
STARTUP_COMPLETE=true
trap - EXIT

echo "CareSync Basic is running:"
echo "  App:      http://127.0.0.1:5174"
echo "  API:      http://127.0.0.1:3002/api/v1"
echo "  API docs: http://127.0.0.1:3002/docs"
echo "  Database: $DATABASE_NAME on isolated PostgreSQL $PGPORT"
echo "  Schema:   $EXPECTED_REVISION ($START_LABEL)"
echo "  Runtime:  $APP_USER (non-superuser, RLS enforced)"
echo "  API bind: $API_BIND_HOST"
if [[ "$BILLING_RUNTIME_MODE" == "manual" && "$BILLING_MANUAL_READY" == "true" ]]; then
  echo "  Billing:  manual/private mode ready for explicit owner activation"
elif [[ "$BILLING_RUNTIME_MODE" == "manual" ]]; then
  echo "  Billing:  manual mode configured; no active organization is available"
else
  echo "  Billing:  disabled by local runtime configuration"
fi
if [[ "$push_provider_ready" == "yes" ]]; then
  echo "  Push:     worker running (provider receipt confirmation enabled)"
else
  echo "  Push:     provider disabled; durable outbox remains queued"
fi
