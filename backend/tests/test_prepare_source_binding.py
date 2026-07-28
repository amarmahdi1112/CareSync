"""Crash-recovery source binding for the pre-candidate preparing fence."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scripts.release_source_bundle import (
    SourceBundleError,
    _closed_tree_identity,
    _python_identity_roots,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SCRIPT = PROJECT_ROOT / "scripts" / "basic-release.sh"
RUNTIME_SCRIPT = PROJECT_ROOT / "scripts" / "lib" / "basic-runtime.sh"
START_SCRIPT = PROJECT_ROOT / "scripts" / "start-basic.sh"


def _function(source: str, name: str, following: str) -> str:
    return source[source.index(f"{name}()") : source.index(f"{following}()")]


def test_preparing_fence_binds_the_captured_recovery_engine() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    create_fence = _function(source, "create_fence", "seal_fence")
    exact_fence = _function(
        source,
        "require_exact_preparing_fence",
        "require_private_prepare_directory",
    )

    assert '"status=preparing"' in create_fence
    assert '"run_directory=$run_directory"' in create_fence
    assert '"release_source_root=$RELEASE_SOURCE_ROOT"' in create_fence
    assert '"release_source_manifest=$RELEASE_SOURCE_MANIFEST"' in create_fence
    assert '"release_source_manifest_sha256=$source_manifest_sha"' in create_fence
    assert '[[ "$(wc -l <"$context"' in exact_fence
    assert '!= "9"' in exact_fence
    for field in (
        "release_source_root",
        "release_source_manifest",
        "release_source_manifest_sha256",
    ):
        assert field in exact_fence


def test_installed_source_drift_reexecutes_bound_source_before_recovery() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    reexec = _function(
        source,
        "reexec_interrupted_prepare_source_if_needed",
        "prepare_release",
    )
    prepare = _function(source, "prepare_release", "commit_release")
    reconcile = _function(
        source,
        "reconcile_interrupted_prepare",
        "require_matching_fence",
    )

    exact = reexec.index("require_exact_preparing_fence")
    verify = reexec.index("bootstrap_verify_pre_candidate_source", exact)
    drift = reexec.index('if [[ "$ROOT" != "$PREPARING_SOURCE_ROOT" ]]', verify)
    execute = reexec.index(
        'exec /bin/bash "$PREPARING_SOURCE_ROOT/scripts/basic-release.sh"',
        drift,
    )
    assert exact < verify < drift < execute

    reexec_call = prepare.index("reexec_interrupted_prepare_source_if_needed")
    recovery_call = prepare.index("reconcile_interrupted_prepare", reexec_call)
    assert reexec_call < recovery_call
    assert "bootstrap_verify_pre_candidate_source" in reconcile
    assert '[[ "$ROOT" != "$PREPARING_SOURCE_ROOT" ]]' in reconcile


def test_fresh_prepare_cleanup_delegates_to_its_bound_source(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    bridge = _function(
        source,
        "recover_interrupted_prepare_from_bound_source",
        "prepare_release",
    )
    run_directory = tmp_path / "run"
    captured_root = run_directory / "release-source"
    captured_script = captured_root / "scripts" / "basic-release.sh"
    captured_script.parent.mkdir(parents=True)
    captured_script.write_text(
        """#!/usr/bin/env bash
set -eu
printf '%s|%s|%s\\n' \\
  "$CARESYNC_CAPTURED_RELEASE_SOURCE_SHA" \\
  "$CARESYNC_INSTALLED_DEPENDENCY_ROOT" "$*"
""",
        encoding="utf-8",
    )
    captured_script.chmod(0o700)
    manifest_sha = "a" * 64
    harness = f"""
set -eu
{bridge}
ROOT=/installed/source
RUN_DIRECTORY="$1"
CAPTURED_ROOT="$2"
EXPECTED_SHA={manifest_sha}
CARESYNC_CAPTURED_RELEASE_SOURCE_SHA=""
CARESYNC_INSTALLED_DEPENDENCY_ROOT=""
require_exact_preparing_fence() {{
  PREPARING_RUN_DIRECTORY="$RUN_DIRECTORY"
  PREPARING_SOURCE_ROOT="$CAPTURED_ROOT"
  PREPARING_SOURCE_MANIFEST_SHA="$EXPECTED_SHA"
}}
bootstrap_verify_pre_candidate_source() {{
  [[ "$1" == "$RUN_DIRECTORY" && "$2" == "$EXPECTED_SHA" ]]
}}
reconcile_interrupted_prepare() {{
  printf 'wrong-root-recovery\\n'
  return 1
}}
basic_fail() {{ printf 'FAIL: %s\\n' "$*" >&2; return 1; }}
recover_interrupted_prepare_from_bound_source
"""
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            harness,
            "bash",
            str(run_directory),
            str(captured_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"{manifest_sha}|/installed/source|_recover-interrupted-prepare\n"
    )
    assert result.stderr == ""
    assert "wrong-root-recovery" not in result.stdout


def test_prepare_cleanup_bridge_replaces_a_stale_captured_bundle_marker(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    bridge = _function(
        source,
        "recover_interrupted_prepare_from_bound_source",
        "prepare_release",
    )
    run_directory = tmp_path / "run"
    captured_root = run_directory / "release-source"
    captured_script = captured_root / "scripts" / "basic-release.sh"
    captured_script.parent.mkdir(parents=True)
    captured_script.write_text(
        """#!/usr/bin/env bash
set -eu
printf '%s|%s\\n' "$CARESYNC_CAPTURED_RELEASE_SOURCE_SHA" "$*"
""",
        encoding="utf-8",
    )
    captured_script.chmod(0o700)
    manifest_sha = "a" * 64
    harness = f"""
set -eu
{bridge}
ROOT=/installed/source
RUN_DIRECTORY="$1"
CAPTURED_ROOT="$2"
EXPECTED_SHA={manifest_sha}
CARESYNC_CAPTURED_RELEASE_SOURCE_SHA={"b" * 64}
require_exact_preparing_fence() {{
  PREPARING_RUN_DIRECTORY="$RUN_DIRECTORY"
  PREPARING_SOURCE_ROOT="$CAPTURED_ROOT"
  PREPARING_SOURCE_MANIFEST_SHA="$EXPECTED_SHA"
}}
bootstrap_verify_pre_candidate_source() {{ :; }}
reconcile_interrupted_prepare() {{ return 99; }}
basic_fail() {{ printf 'FAIL: %s\\n' "$*" >&2; return 1; }}
recover_interrupted_prepare_from_bound_source
"""
    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            harness,
            "bash",
            str(run_directory),
            str(captured_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"{manifest_sha}|_recover-interrupted-prepare\n"
    )
    assert result.stderr == ""


def test_prepare_without_options_is_safe_under_bash_32_nounset() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    prepare = _function(source, "prepare_release", "commit_release")
    harness = f"""
set -u
{prepare}
basic_require_local_toolchain() {{ :; }}
basic_require_runtime_layout() {{ :; }}
basic_normalize_known_runtime_files() {{ :; }}
ensure_release_state_directory() {{ :; }}
reexec_interrupted_prepare_source_if_needed() {{
  printf '%s\\n' "$*"
  return 1
}}
prepare_release || [[ "$?" == "1" ]]
"""
    result = subprocess.run(
        ["/bin/bash"],
        check=False,
        capture_output=True,
        input=harness,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "prepare\n"


def test_runtime_empty_arrays_are_safe_under_bash_32_nounset() -> None:
    source = RUNTIME_SCRIPT.read_text(encoding="utf-8")
    functions = "\n".join(
        (
            _function(
                source,
                "basic_assert_no_symlink_components",
                "basic_durable_ensure_private_runtime_directory",
            ),
            _function(
                source,
                "basic_reconcile_torn_managed_pid",
                "basic_stop_managed_service",
            ),
            _function(
                source,
                "basic_stop_api_listener",
                "basic_assert_no_writer_processes",
            ),
            _function(
                source,
                "basic_stop_frontend_listener",
                "basic_assert_managed_service_running",
            ),
        )
    )
    harness = f"""
set -eu
RUNTIME_DIR=/tmp/caresync-bash32-array-harness
{functions}
basic_fail() {{ printf 'FAIL: %s\\n' "$*" >&2; return 1; }}
basic_expected_backend_runtime_root() {{ printf '/tmp/backend\\n'; }}
basic_expected_frontend_runtime_root() {{ printf '/tmp/frontend\\n'; }}
basic_collect_tcp_listener_pids() {{ :; }}
basic_process_cwd() {{ return 1; }}
basic_inspect_pid_presence() {{ return 1; }}
basic_wait_for_process_exit() {{ return 1; }}
basic_durable_remove_private_runtime_file() {{
  printf 'removed=%s\\n' "$1"
}}
ps() {{ :; }}

basic_assert_no_symlink_components /
printf 'root-path=ok\\n'
basic_reconcile_torn_managed_pid backend signature /tmp/backend
printf 'torn-pid=ok\\n'
basic_stop_api_listener
printf 'api-listener=ok\\n'
basic_stop_frontend_listener
printf 'frontend-listener=ok\\n'
"""
    result = subprocess.run(
        ["/bin/bash"],
        check=False,
        capture_output=True,
        input=harness,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "root-path=ok" in result.stdout
    assert "torn-pid=ok" in result.stdout
    assert "api-listener=ok" in result.stdout
    assert "frontend-listener=ok" in result.stdout
    assert "removed=/tmp/caresync-bash32-array-harness/pids/backend.pid" in (
        result.stdout
    )
    assert "removed=/tmp/caresync-bash32-array-harness/pids/frontend.pid" in (
        result.stdout
    )


def test_every_optional_runtime_array_uses_bash_32_safe_expansion() -> None:
    runtime = RUNTIME_SCRIPT.read_text(encoding="utf-8")
    assert not re.findall(
        r'for \w+ in "\$\{(?:components|matching_pids|listener_pids)'
        r'\[@\]\}";',
        runtime,
    )
    expected_safe_expansions = {
        "components": 1,
        "matching_pids": 2,
        "listener_pids": 6,
    }
    for array, expected in expected_safe_expansions.items():
        safe = f'"${{{array}[@]+"${{{array}[@]}}"}}"'
        assert runtime.count(safe) == expected

    start = START_SCRIPT.read_text(encoding="utf-8")
    initialize = start.index("requested_billing_organization_ids=()")
    read = start.index(
        "read -r -a requested_billing_organization_ids",
        initialize,
    )
    guard = start.index(
        "${#requested_billing_organization_ids[@]} == 0",
        read,
    )
    safe_loop = start.index(
        '${requested_billing_organization_ids[@]+"'
        '${requested_billing_organization_ids[@]}"}',
        guard,
    )
    assert initialize < read < guard < safe_loop


def test_release_probe_contract_avoids_reserved_column_alias(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    contract = _function(
        source,
        "require_release_probe_contract",
        "set_release_probe_login_state",
    )
    expected = (
        "nologin|false|false|false|false|false|false|true|"
        "default_transaction_read_only=on,lock_timeout=2s,"
        "search_path=pg_catalog, public,statement_timeout=15s|"
        "0|0|0|0|0|true|false|true|false|0|0|0|0|0"
    )
    query_file = tmp_path / "release-probe-query.sql"
    harness = f"""
set -eu
{contract}
RELEASE_PROBE_USER=caresync_release_probe
QUERY_FILE="$1"
release_psql_scalar() {{
  printf '%s' "$2" >"$QUERY_FILE"
  printf '%s\\n' '{expected}'
}}
basic_fail() {{ printf 'FAIL: %s\\n' "$*" >&2; return 1; }}
require_release_probe_contract nologin 5434
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(query_file)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    query = query_file.read_text(encoding="utf-8")
    assert "pg_catalog.pg_attribute column" not in query
    assert "pg_catalog.pg_attribute attribute" in query
    assert "object.oid=attribute.attrelid" in query
    assert "attribute.attnum>0" in query
    assert "NOT attribute.attisdropped" in query
    assert "object.oid,attribute.attnum" in query
    assert "FROM pg_catalog.pg_authid auth" in query
    assert "SELECT auth.rolpassword LIKE 'SCRAM-SHA-256$%'" in query
    assert "WHEN object.relkind='S' THEN" in query


@pytest.mark.parametrize(
    ("expected_scope", "state", "accepted"),
    (
        ("closed", "0|0|7|0|7|0", True),
        ("open", "0|7|7|0|0|0", True),
        ("closed", "1|0|7|0|7|0", False),
        ("closed", "0|1|7|0|6|0", False),
        ("open", "1|7|7|0|0|0", False),
        ("open", "0|8|7|1|0|0", False),
        ("open", "0|6|7|0|1|0", False),
        ("open", "0|7|7|0|0|1", False),
        ("closed", "0|0|0|0|0|0", False),
        ("open", "0|0|0|0|0|0", False),
    ),
)
def test_release_probe_accepts_only_exact_closed_or_all_column_open_scope(
    expected_scope: str,
    state: str,
    accepted: bool,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    scope_guard = _function(
        source,
        "require_release_probe_read_scope",
        "scrub_release_probe_object_privileges",
    )
    harness = f"""
set -u
{scope_guard}
MOCK_SCOPE_STATE="$2"
release_probe_read_scope_state() {{ printf '%s\\n' "$MOCK_SCOPE_STATE"; }}
basic_fail() {{ printf 'FAIL: %s\\n' "$*" >&2; return 1; }}
require_release_probe_read_scope "$1" 5434
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", expected_scope, state],
        check=False,
        capture_output=True,
        text=True,
    )

    assert (result.returncode == 0) is accepted, result.stderr


def test_release_probe_open_close_executes_fail_closed_transition_order(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    lifecycle = _function(
        source,
        "open_release_probe_for_controlled_health",
        "prove_release_probe_write_rejection",
    )
    log = tmp_path / "probe-lifecycle.log"
    harness = f"""
set -eu
{lifecycle}
LOG="$1"
record() {{ printf '%s\\n' "$1" >>"$LOG"; }}
require_release_probe_contract() {{ record "contract:$1:$2"; }}
require_release_probe_read_scope() {{ record "scope:$1:$2"; }}
grant_release_probe_controlled_read() {{ record "grant-columns:$1"; }}
set_release_probe_login_state() {{ record "login:$1:$2"; }}
scrub_release_probe_object_privileges() {{ record "scrub:$1"; }}
basic_fail() {{ printf 'FAIL: %s\\n' "$*" >&2; return 1; }}
open_release_probe_for_controlled_health 56656
close_release_probe_after_controlled_health 56656
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(log)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "contract:nologin:56656",
        "scope:closed:56656",
        "grant-columns:56656",
        "scope:open:56656",
        "login:login:56656",
        "contract:login:56656",
        "scope:open:56656",
        "login:nologin:56656",
        "scrub:56656",
        "contract:nologin:56656",
        "scope:closed:56656",
    ]


@pytest.mark.parametrize(
    "failed_step",
    (
        "grant-columns",
        "scope:open",
        "login:login",
        "contract:login",
    ),
)
def test_release_probe_open_failure_runs_complete_close_sequence(
    tmp_path: Path,
    failed_step: str,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    lifecycle = _function(
        source,
        "open_release_probe_for_controlled_health",
        "prove_release_probe_write_rejection",
    )
    log = tmp_path / "probe-open-failure.log"
    harness = f"""
set -u
{lifecycle}
LOG="$1"
FAILED_STEP="$2"
record() {{ printf '%s\\n' "$1" >>"$LOG"; }}
maybe_fail() {{ [[ "$1" != "$FAILED_STEP" ]]; }}
require_release_probe_contract() {{
  record "contract:$1"
  maybe_fail "contract:$1"
}}
require_release_probe_read_scope() {{
  record "scope:$1"
  maybe_fail "scope:$1"
}}
grant_release_probe_controlled_read() {{
  record "grant-columns"
  maybe_fail "grant-columns"
}}
set_release_probe_login_state() {{
  record "login:$1"
  maybe_fail "login:$1"
}}
scrub_release_probe_object_privileges() {{ record "scrub"; }}
basic_fail() {{ record "basic-fail"; return 1; }}
if open_release_probe_for_controlled_health 56656; then
  exit 99
fi
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(log), failed_step],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines()[-4:] == [
        "login:nologin",
        "scrub",
        "contract:nologin",
        "scope:closed",
    ]


@pytest.mark.parametrize("failed_step", ("login:nologin", "scrub"))
def test_release_probe_close_attests_closed_even_after_mutation_error(
    tmp_path: Path,
    failed_step: str,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    lifecycle = _function(
        source,
        "close_release_probe_after_controlled_health",
        "prove_release_probe_write_rejection",
    )
    log = tmp_path / "probe-close-failure.log"
    harness = f"""
set -u
{lifecycle}
LOG="$1"
FAILED_STEP="$2"
record() {{ printf '%s\\n' "$1" >>"$LOG"; }}
maybe_fail() {{ [[ "$1" != "$FAILED_STEP" ]]; }}
set_release_probe_login_state() {{ record "login:$1"; maybe_fail "login:$1"; }}
scrub_release_probe_object_privileges() {{ record "scrub"; maybe_fail "scrub"; }}
require_release_probe_contract() {{ record "contract:$1"; }}
require_release_probe_read_scope() {{ record "scope:$1"; }}
basic_fail() {{ record "basic-fail"; return 1; }}
close_release_probe_after_controlled_health 56656
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(log), failed_step],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert log.read_text(encoding="utf-8").splitlines() == [
        "login:nologin",
        "scrub",
        "contract:nologin",
        "scope:closed",
        "basic-fail",
    ]


def test_release_probe_read_scope_is_column_only_and_sequence_safe() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    configure = (
        PROJECT_ROOT / "backend" / "scripts" / "configure_basic_release_probe.sql"
    ).read_text(encoding="utf-8")
    scope = _function(
        source,
        "release_probe_read_scope_state",
        "scrub_release_probe_object_privileges",
    )
    grant = _function(
        source,
        "grant_release_probe_controlled_read",
        "set_release_probe_login_state",
    )
    scrub = _function(
        source,
        "scrub_release_probe_object_privileges",
        "grant_release_probe_controlled_read",
    )

    assert "CASE WHEN relation.relkind='S' THEN 's'::\\\"char\\\"" in scope
    assert "THEN 'S'::\\\"char\\\"" not in scope
    assert "relation.relkind IN ('r','p','v','m','f')" in scope
    assert '"$column_grants" != "$expected_columns"' in scope
    assert '"$missing_column_grants" != "0"' in scope
    assert '"$relation_grants" != "0"' in scope
    assert '"$function_grants" != "0"' in scope

    assert "pg_catalog.string_agg(" in grant
    assert "pg_catalog.quote_ident(attribute.attname)" in grant
    assert "attribute.attnum>0" in grant
    assert "NOT attribute.attisdropped" in grant
    assert "relation.relkind IN ('r','p','v','m','f')" in grant
    assert (
        "'GRANT SELECT (%s) ON TABLE %I.%I TO caresync_release_probe'"
        in grant
    )
    assert re.search(
        r"GRANT\s+SELECT\s+ON\s+(?:ALL\s+)?TABLE",
        grant,
        flags=re.IGNORECASE,
    ) is None
    assert "GRANT SELECT ON ALL TABLES" not in source
    assert "GRANT SELECT ON ALL TABLES" not in configure

    assert "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public" in scrub
    assert (
        "'REVOKE ALL PRIVILEGES (%s) ON TABLE %I.%I "
        "FROM caresync_release_probe'"
    ) in scrub
    assert "pg_catalog.acldefault('c',relation.relowner)" in scrub
    assert "GRANT SELECT" not in configure

    proof_wrapper = _function(
        source,
        "prove_release_probe_write_rejection_or_close",
        "require_high_clone_port",
    )
    assert proof_wrapper.index("prove_release_probe_write_rejection") < (
        proof_wrapper.index("close_release_probe_after_controlled_health")
    )
    assert len(
        re.findall(
            r"(?m)^\s+prove_release_probe_write_rejection_or_close \\$",
            source,
        )
    ) == 6


def test_post_health_commit_verification_probe_window_closes_on_verify_failure(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    bounded_verify = _function(
        source,
        "verify_commit_start_in_bounded_probe_window",
        "finalize_commit_start",
    )
    log = tmp_path / "post-health-probe-window.log"
    harness = f"""
set -u
{bounded_verify}
LOG="$1"
RELEASE_PROBE_CREDENTIAL=credential
record() {{ printf '%s\\n' "$1" >>"$LOG"; }}
open_release_probe_for_controlled_health() {{ record "open-columns"; }}
prove_release_probe_write_rejection_or_close() {{ record "prove-no-write"; }}
verify_commit_start() {{ record "verify-live"; return 1; }}
close_release_probe_after_controlled_health() {{ record "close"; }}
if verify_commit_start_in_bounded_probe_window candidate receipt; then
  exit 99
fi
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(log)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "open-columns",
        "prove-no-write",
        "verify-live",
        "close",
    ]


def test_post_health_commit_verification_probe_window_closes_on_success(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    bounded_verify = _function(
        source,
        "verify_commit_start_in_bounded_probe_window",
        "finalize_commit_start",
    )
    log = tmp_path / "post-health-probe-window.log"
    harness = f"""
set -eu
{bounded_verify}
LOG="$1"
RELEASE_PROBE_CREDENTIAL=credential
record() {{ printf '%s\\n' "$1" >>"$LOG"; }}
open_release_probe_for_controlled_health() {{ record "open-columns"; }}
prove_release_probe_write_rejection_or_close() {{ record "prove-no-write"; }}
verify_commit_start() {{ record "verify-live"; }}
close_release_probe_after_controlled_health() {{ record "close"; }}
verify_commit_start_in_bounded_probe_window candidate receipt
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(log)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "open-columns",
        "prove-no-write",
        "verify-live",
        "close",
    ]


def test_post_health_commit_verification_probe_window_closes_on_proof_failure(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    bounded_verify = _function(
        source,
        "verify_commit_start_in_bounded_probe_window",
        "finalize_commit_start",
    )
    log = tmp_path / "post-health-probe-proof-failure.log"
    harness = f"""
set -u
{bounded_verify}
LOG="$1"
RELEASE_PROBE_CREDENTIAL=credential
record() {{ printf '%s\\n' "$1" >>"$LOG"; }}
open_release_probe_for_controlled_health() {{ record "open-columns"; }}
prove_release_probe_write_rejection_or_close() {{
  record "prove-no-write"
  return 1
}}
verify_commit_start() {{ record "verify-live"; }}
close_release_probe_after_controlled_health() {{ record "close"; }}
if verify_commit_start_in_bounded_probe_window candidate receipt; then
  exit 99
fi
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(log)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "open-columns",
        "prove-no-write",
        "close",
    ]


def test_post_health_commit_verification_probe_window_propagates_close_failure(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    bounded_verify = _function(
        source,
        "verify_commit_start_in_bounded_probe_window",
        "finalize_commit_start",
    )
    log = tmp_path / "post-health-probe-close-failure.log"
    harness = f"""
set -u
{bounded_verify}
LOG="$1"
RELEASE_PROBE_CREDENTIAL=credential
record() {{ printf '%s\\n' "$1" >>"$LOG"; }}
open_release_probe_for_controlled_health() {{ record "open-columns"; }}
prove_release_probe_write_rejection_or_close() {{ record "prove-no-write"; }}
verify_commit_start() {{ record "verify-live"; }}
close_release_probe_after_controlled_health() {{
  record "close"
  return 1
}}
if verify_commit_start_in_bounded_probe_window candidate receipt; then
  exit 99
fi
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(log)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "open-columns",
        "prove-no-write",
        "verify-live",
        "close",
    ]


def test_startup_emergency_cleanup_uses_locked_full_fence_before_fallback() -> None:
    release = RELEASE_SCRIPT.read_text(encoding="utf-8")
    start = START_SCRIPT.read_text(encoding="utf-8")

    cleanup = _function(start, "startup_cleanup", "configure_writable_runtime_credentials")
    identity = cleanup.index("basic_verify_retained_identity")
    full_fence = cleanup.index("_fence-runtime-roles", identity)
    app_fallback = cleanup.index(
        'basic_set_app_login_state "nologin" || true',
        full_fence,
    )
    ingest_fallback = cleanup.index(
        "caresync_transport_evidence_ingest nologin || true",
        app_fallback,
    )
    probe_fallback = cleanup.index(
        'basic_set_role_login_state "$RELEASE_PROBE_USER" nologin || true',
        ingest_fallback,
    )
    assert identity < full_fence < app_fallback < ingest_fallback < probe_fallback

    helper = _function(
        release,
        "emergency_fence_runtime_roles",
        "refence_interrupted_runtime_window",
    )
    helper_identity = helper.index("basic_verify_retained_identity")
    assert helper_identity < helper.index(
        "\n  fence_runtime_roles",
        helper_identity,
    )

    lock_dispatch = release[
        release.rfind(
            'case "${1:-}" in',
            0,
            release.index("basic_reexec_with_state_change_lock"),
        ) :
        release.index("basic_reexec_with_state_change_lock") + len(
            'basic_reexec_with_state_change_lock "$0" "$@"'
        )
    ]
    assert "_fence-runtime-roles|" in lock_dispatch
    assert 'basic_reexec_with_state_change_lock "$0" "$@"' in lock_dispatch

    route = release[
        release.index("  _fence-runtime-roles)") :
        release.index("  _recover-interrupted-prepare)")
    ]
    assert '[[ "$#" == "1" ]] || { usage; exit 2; }' in route
    assert "emergency_fence_runtime_roles" in route


def test_release_endpoint_checks_normalize_inet_host_addresses() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")

    assert source.count("host(inet_server_addr())") == 2
    assert "inet_server_addr()::text" not in source
    assert (
        "host(inet_server_addr()) || ':' || inet_server_port()::text"
        in source
    )


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    (("false", 1), ("false || return", 1), ("return 37", 37)),
)
def test_prepare_failure_cleanup_survives_lost_local_scope(
    failure: str,
    expected_status: int,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    prepare = _function(source, "prepare_release", "commit_release")
    cleanup_start = prepare.index("  prepare_cleanup()")
    trap_start = prepare.index(
        """  trap 'prepare_cleanup "$?"' EXIT""",
        cleanup_start,
    )
    cleanup = prepare[cleanup_start:trap_start]
    harness = f"""
set -eu
PREPARE_CLEANUP_RUN_DIRECTORY=""
PREPARE_CLEANUP_RETAINED_FENCED=false
PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
PREPARE_CLEANUP_CANDIDATE_SEALED=false
PREPARE_CLEANUP_FENCE_CREATED=false
RELEASE_FENCE_DIRECTORY=/tmp/release-fence
reconcile_prepare_disposables_for_run() {{
  [[ "$1" == "/tmp/release-run" ]]
}}
fence_runtime_roles() {{ :; }}
directory_entry_state() {{ printf 'empty\\n'; }}
reconcile_interrupted_prepare() {{ :; }}
prepare_scope() {{
  local run_directory=/tmp/release-run
  PREPARE_CLEANUP_RUN_DIRECTORY="$run_directory"
  PREPARE_CLEANUP_RETAINED_FENCED=false
  PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
  PREPARE_CLEANUP_CANDIDATE_SEALED=false
  PREPARE_CLEANUP_FENCE_CREATED=false
{cleanup}
  trap 'prepare_cleanup "$?"' EXIT
  {failure}
}}
prepare_scope
"""
    result = subprocess.run(
        ["/bin/bash"],
        check=False,
        capture_output=True,
        input=harness,
        text=True,
    )

    assert result.returncode == expected_status
    assert result.stdout == ""
    assert "Release preparation failed; no retained migration ran." in (
        result.stderr
    )
    assert "The retained application roles were not changed." in result.stderr
    assert "unbound variable" not in result.stderr
    assert """trap 'prepare_cleanup "$?"' EXIT""" in prepare
    assert "trap - EXIT" in prepare
    for state in (
        "PREPARE_CLEANUP_RUN_DIRECTORY",
        "PREPARE_CLEANUP_RETAINED_FENCED",
        "PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY",
        "PREPARE_CLEANUP_CANDIDATE_SEALED",
        "PREPARE_CLEANUP_FENCE_CREATED",
    ):
        assert state in cleanup
    socket_mkdir = prepare.index(
        'mkdir -m 700 "$rehearsal_socket_directory"'
    )
    socket_obligation = prepare.index(
        'PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY='
        '"$rehearsal_socket_directory"',
        socket_mkdir,
    )
    socket_remove = prepare.index(
        'rmdir "$rehearsal_socket_directory"',
        socket_obligation,
    )
    socket_clear = prepare.index(
        'PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""',
        socket_remove,
    )
    assert socket_mkdir < socket_obligation < socket_remove < socket_clear


def test_prepare_failure_cleanup_uses_bound_source_recovery_after_scope_loss(
    tmp_path: Path,
) -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    prepare = _function(source, "prepare_release", "commit_release")
    cleanup_start = prepare.index("  prepare_cleanup()")
    trap_start = prepare.index(
        """  trap 'prepare_cleanup "$?"' EXIT""",
        cleanup_start,
    )
    cleanup = prepare[cleanup_start:trap_start]
    fence_directory = tmp_path / "release-fence"
    fence_directory.mkdir()
    harness = f"""
set -eu
PREPARE_CLEANUP_RUN_DIRECTORY=/tmp/release-run
PREPARE_CLEANUP_RETAINED_FENCED=true
PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
PREPARE_CLEANUP_CANDIDATE_SEALED=false
PREPARE_CLEANUP_FENCE_CREATED=true
RELEASE_FENCE_DIRECTORY="$1"
reconcile_prepare_disposables_for_run() {{
  [[ "$1" == "/tmp/release-run" ]]
}}
fence_runtime_roles() {{ :; }}
directory_entry_state() {{ printf 'empty\\n'; }}
recover_interrupted_prepare_from_bound_source() {{
  printf 'bound-source-recovery\\n' >&2
}}
prepare_scope() {{
{cleanup}
  trap 'prepare_cleanup "$?"' EXIT
  return 37
}}
prepare_scope
"""
    result = subprocess.run(
        ["/bin/bash", "-c", harness, "bash", str(fence_directory)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 37
    assert result.stdout == ""
    assert "bound-source-recovery" in result.stderr
    assert "Writer restoration failed" not in result.stderr
    assert "unbound variable" not in result.stderr
    assert "if ! recover_interrupted_prepare_from_bound_source; then" in cleanup
    assert "if ! reconcile_interrupted_prepare; then" not in cleanup


def test_prepare_success_disarms_exit_cleanup() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    prepare = _function(source, "prepare_release", "commit_release")
    cleanup_start = prepare.index("  prepare_cleanup()")
    trap_start = prepare.index(
        """  trap 'prepare_cleanup "$?"' EXIT""",
        cleanup_start,
    )
    cleanup = prepare[cleanup_start:trap_start]
    harness = f"""
set -eu
PREPARE_CLEANUP_RUN_DIRECTORY=/tmp/release-run
PREPARE_CLEANUP_RETAINED_FENCED=false
PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
PREPARE_CLEANUP_CANDIDATE_SEALED=true
PREPARE_CLEANUP_FENCE_CREATED=true
RELEASE_FENCE_DIRECTORY=/tmp/release-fence
reconcile_prepare_disposables_for_run() {{
  printf 'cleanup-ran\\n'
}}
fence_runtime_roles() {{ :; }}
directory_entry_state() {{ printf 'empty\\n'; }}
reconcile_interrupted_prepare() {{ :; }}
prepare_scope() {{
{cleanup}
  trap 'prepare_cleanup "$?"' EXIT
  trap - EXIT
}}
prepare_scope
printf 'success\\n'
"""
    result = subprocess.run(
        ["/bin/bash"],
        check=False,
        capture_output=True,
        input=harness,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "success\n"
    assert result.stderr == ""


def test_prepare_cleanup_refences_after_disposable_reconcile_failure() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    prepare = _function(source, "prepare_release", "commit_release")
    cleanup_start = prepare.index("  prepare_cleanup()")
    trap_start = prepare.index(
        """  trap 'prepare_cleanup "$?"' EXIT""",
        cleanup_start,
    )
    cleanup = prepare[cleanup_start:trap_start]
    harness = f"""
set -eu
PREPARE_CLEANUP_RUN_DIRECTORY=/tmp/release-run
PREPARE_CLEANUP_RETAINED_FENCED=true
PREPARE_CLEANUP_REHEARSAL_SOCKET_DIRECTORY=""
PREPARE_CLEANUP_CANDIDATE_SEALED=false
PREPARE_CLEANUP_FENCE_CREATED=true
RELEASE_FENCE_DIRECTORY=/tmp/release-fence
reconcile_prepare_disposables_for_run() {{ return 1; }}
fence_runtime_roles() {{ printf 'refenced\\n' >&2; }}
directory_entry_state() {{ printf 'empty\\n'; }}
reconcile_interrupted_prepare() {{ :; }}
prepare_scope() {{
{cleanup}
  trap 'prepare_cleanup "$?"' EXIT
  return 37
}}
prepare_scope
"""
    result = subprocess.run(
        ["/bin/bash"],
        check=False,
        capture_output=True,
        input=harness,
        text=True,
    )

    assert result.returncode == 37
    assert result.stdout == ""
    assert "refenced" in result.stderr
    assert "Disposable PostgreSQL reconciliation failed" in result.stderr
    assert "unbound variable" not in result.stderr


def _homebrew_python_layout(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    keg = tmp_path / "opt" / "homebrew" / "Cellar" / "python@3.14" / "3.14.3_1"
    base = (
        keg
        / "Frameworks"
        / "Python.framework"
        / "Versions"
        / "3.14"
    )
    external = keg / "lib" / "python3.14" / "site-packages"
    python = keg / "bin" / "python3.14"
    base.mkdir(parents=True)
    external.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")
    (keg / "INSTALL_RECEIPT.json").write_text("{}", encoding="utf-8")
    link = base / "lib" / "python3.14" / "site-packages"
    link.parent.mkdir(parents=True)
    link.symlink_to(
        Path("../../../../../../lib/python3.14/site-packages"),
        target_is_directory=True,
    )
    return keg, base, external, python


def test_homebrew_python_identity_uses_exact_versioned_keg(
    tmp_path: Path,
) -> None:
    keg, base, external, python = _homebrew_python_layout(tmp_path)
    venv = tmp_path / "venv"
    venv.mkdir()
    dependency = external / "dependency.py"
    dependency.write_text("VERSION = 1\n", encoding="utf-8")

    roots = _python_identity_roots(python, venv, base)

    assert roots == tuple(sorted((keg, venv), key=str))
    assert keg.parent not in roots
    assert keg.parent.parent not in roots
    first = _closed_tree_identity(keg)
    dependency.write_text("VERSION = 2\n", encoding="utf-8")
    second = _closed_tree_identity(keg)

    assert first["sha256Tree"] != second["sha256Tree"]


def test_generic_dependency_identity_still_rejects_external_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dependency-root"
    external = tmp_path / "unrelated-tree"
    root.mkdir()
    external.mkdir()
    (root / "escape").symlink_to(
        external,
        target_is_directory=True,
    )

    with pytest.raises(SourceBundleError, match="escapes its tree"):
        _closed_tree_identity(root)


def test_python_identity_does_not_merge_different_homebrew_kegs(
    tmp_path: Path,
) -> None:
    _, base, _, _ = _homebrew_python_layout(tmp_path / "base")
    other_keg, _, _, other_python = _homebrew_python_layout(
        tmp_path / "executable"
    )
    prefix = tmp_path / "venv"
    prefix.mkdir()

    roots = _python_identity_roots(other_python, prefix, base)

    assert other_keg not in roots
    assert roots == tuple(sorted((base, prefix), key=str))
