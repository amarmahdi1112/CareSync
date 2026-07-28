"""Fail-closed backup, quiescence, and disposable-restore contract tests."""

from __future__ import annotations

import gzip
import json
import stat
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings
from scripts.backup_database import (
    BACKUP_FORMAT,
    BackupContractError,
    create_backup,
    verify_backup_artifacts,
)
from scripts.restore_database import (
    RestoreContractError,
    decode_value,
    disposable_confirmation,
    validate_disposable_target,
    write_private_restore_receipt,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def _create_sqlite_fixture(path: Path) -> None:
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('test_revision')"))
            connection.execute(
                text(
                    "CREATE TABLE families ("
                    "id INTEGER PRIMARY KEY, name TEXT NOT NULL, payload BLOB)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO families (id,name,payload) VALUES "
                    "(2,'Second',x'00ff'),(1,'First',x'0102')"
                )
            )
    finally:
        engine.dispose()


def test_sqlite_backup_is_atomic_complete_and_self_verifying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "caresync.db"
    _create_sqlite_fixture(database_path)
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")

    backup, manifest = create_backup(tmp_path / "backups")
    verified = verify_backup_artifacts(backup, manifest)

    assert verified["header"]["format"] == BACKUP_FORMAT
    assert verified["header"]["visibilityMode"] == "sqlite-whole-file"
    assert verified["header"]["alembicRevisions"] == ["test_revision"]
    assert verified["tableCounts"] == {"alembic_version": 1, "families": 2}
    assert verified["manifest"]["totalRows"] == 3
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.parent.stat().st_mode) == 0o700
    assert not list(backup.parent.glob("*.partial-*"))

    with gzip.open(backup, "rt", encoding="utf-8") as source:
        lines = [json.loads(line) for line in source]
    family_ids = [row["row"]["id"] for row in lines[1:] if row["table"] == "families"]
    assert family_ids == [1, 2]


def test_backup_verification_rejects_modified_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "caresync.db"
    _create_sqlite_fixture(database_path)
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    backup, manifest = create_backup(tmp_path / "backups")

    backup.write_bytes(backup.read_bytes() + b"tampered")
    with pytest.raises(BackupContractError, match="Compressed backup SHA-256 mismatch"):
        verify_backup_artifacts(backup, manifest)


def test_backup_verification_rejects_non_private_artifact_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "caresync.db"
    _create_sqlite_fixture(database_path)
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    backup, manifest = create_backup(tmp_path / "backups")

    backup.chmod(0o644)
    with pytest.raises(BackupContractError, match="required mode is 0600"):
        verify_backup_artifacts(backup, manifest)


@pytest.mark.parametrize("port", [5432, 5433, 5434])
def test_restore_target_guard_permanently_rejects_live_ports(port: int) -> None:
    settings = Settings(
        database_type="postgres",
        database_host="127.0.0.1",
        database_port=port,
        database_name="caresync",
    )
    with pytest.raises(RestoreContractError, match="protected"):
        validate_disposable_target(settings, disposable_confirmation(settings))


def test_restore_target_guard_requires_exact_loopback_confirmation() -> None:
    settings = Settings(
        database_type="postgres",
        database_host="127.0.0.1",
        database_port=55447,
        database_name="caresync",
    )
    with pytest.raises(RestoreContractError, match="confirmation is missing"):
        validate_disposable_target(settings, None)
    with pytest.raises(RestoreContractError, match="confirmation is missing"):
        validate_disposable_target(settings, "127.0.0.1:55448/caresync")
    validate_disposable_target(settings, "127.0.0.1:55447/caresync")


def test_typed_backup_values_round_trip() -> None:
    from datetime import date, datetime, time
    from decimal import Decimal
    from uuid import uuid4

    from scripts.backup_database import encode_value

    values = [
        Decimal("10.250"),
        uuid4(),
        datetime.fromisoformat("2026-07-17T01:02:03+00:00"),
        date.fromisoformat("2026-07-17"),
        time.fromisoformat("01:02:03"),
        b"\x00\xff",
        {"$type": "uuid", "value": "literal application JSON"},
        ["one", {"nested": True}],
    ]
    assert [decode_value(encode_value(value)) for value in values] == values


def test_restore_receipt_is_private_and_no_clobber(tmp_path: Path) -> None:
    receipt = tmp_path / "private-receipts" / "restore.json"
    write_private_restore_receipt(receipt, {"result": "first"})

    assert json.loads(receipt.read_text(encoding="utf-8")) == {"result": "first"}
    assert stat.S_IMODE(receipt.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert receipt.stat().st_nlink == 1

    with pytest.raises(RestoreContractError, match="Refusing to replace"):
        write_private_restore_receipt(receipt, {"result": "second"})
    assert json.loads(receipt.read_text(encoding="utf-8")) == {"result": "first"}


def test_restore_receipt_rejects_symlinked_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir(mode=0o700)
    real_parent.chmod(0o700)
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(RestoreContractError, match="symbolic link"):
        write_private_restore_receipt(linked_parent / "restore.json", {"result": "unsafe"})
    assert not (real_parent / "restore.json").exists()


def test_strong_restore_attestation_is_same_transaction_and_precedes_truncate() -> None:
    restore = (BACKEND_ROOT / "scripts" / "restore_database.py").read_text(encoding="utf-8")
    transaction = restore.index(
        "with database.engine.connect() as connection, connection.begin():"
    )
    attestation = restore.index("_assert_strong_target_attestation(", transaction)
    replication_bypass = restore.index(
        'connection.exec_driver_sql("SET LOCAL session_replication_role = replica")',
        attestation,
    )
    truncate = restore.index("_truncate_target(connection, metadata)", replication_bypass)

    assert transaction < attestation < replication_bypass < truncate
    assert 'LOCK TABLE {locked_names} IN ACCESS EXCLUSIVE MODE' in restore
    assert "current_setting('data_directory')" in restore
    assert "SELECT system_identifier::text FROM pg_control_system()" in restore
    assert "Disposable target contains application rows immediately before restore" in restore
    assert "Disposable target has another client session" in restore
    assert "Disposable target contains a non-system schema outside public" in restore
    assert "namespace.nspname NOT IN ('public','information_schema')" in restore
    assert 'f"TRUNCATE TABLE {names} RESTART IDENTITY"' in restore
    assert "RESTART IDENTITY CASCADE" not in restore


def test_ordinary_startup_is_not_a_release_or_migration_tool() -> None:
    start = (PROJECT_ROOT / "scripts" / "start-basic.sh").read_text(encoding="utf-8")

    preflight = start.index("_preflight-normal-start")
    postgres = start.index("basic_start_postgres", preflight)
    exact_revision = start.index(
        'basic_require_exact_revision "$EXPECTED_REVISION"', postgres
    )
    preflight_complete = start.index(
        "# Only after the complete local dependency/vault/secret preflight succeeds"
    )
    quiesce = start.index("basic_quiesce_application", preflight_complete)
    worker = start.index(
        'if [[ "$RELEASE_START_KIND" == "normal" ]]; then\n  start_push_worker',
        quiesce,
    )
    api = start.index(
        'start_application_runtime \\\n  "$RUNTIME_DATABASE_USER"',
        worker,
    )

    assert preflight < postgres < exact_revision < quiesce < worker < api
    assert start.count("gated_service_exec.py") == 3
    assert "basic_prepare_managed_launch" in start
    assert "basic_publish_managed_launch_gate" in start
    assert "basic_complete_managed_launch" in start
    assert 'EXPECTED_REVISION="$CARESYNC_RETAINED_TARGET_REVISION"' in start
    assert 'EXPECTED_REVISION="$CARESYNC_RETAINED_SOURCE_REVISION"' in start
    assert "_verify-resume-start" in start
    assert "_finalize-resume-start" in start
    assert "CARESYNC_BASIC_RESUME_0039_CONFIRMATION" not in start
    assert "CARESYNC_BASIC_RESUME_CERTIFIED" not in start
    for forbidden in (
        "backup_database.py",
        "restore_database.py",
        "pg_basebackup",
        "pg_verifybackup",
        "alembic upgrade",
        "bootstrap_basic_runtime_role.sql",
        "CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET",
    ):
        assert forbidden not in start


def test_two_phase_release_orders_proof_before_retained_migration_and_start() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    prepare = release.index("prepare_release()")
    source_preflight = release.index(
        'basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"',
        prepare,
    )
    prepare_topology = release.index(
        "basic_require_release_apfs_topology", source_preflight
    )
    quiesce = release.index("basic_quiesce_application", prepare_topology)
    fence = release.index("  create_fence \\", quiesce)
    nologin = release.index(
        "basic_set_role_login_state caresync_basic_app nologin", fence
    )
    source_revision = release.index(
        'basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"',
        nologin,
    )
    physical = release.index('"$PG_BIN/pg_basebackup"', nologin)
    physical_verify = release.index('"$PG_BIN/pg_verifybackup"', physical)
    logical = release.index("python scripts/backup_database.py --output-directory", physical)
    initdb = release.index('"$PG_BIN/initdb"', logical)
    restore = release.index("python scripts/restore_database.py", initdb)
    strong_directory = release.index("--expected-data-directory", restore)
    strong_system = release.index("--expected-system-identifier", strong_directory)
    require_empty = release.index("--require-empty-target", strong_system)
    clone_migrate = release.index(
        'alembic upgrade "$CARESYNC_RETAINED_TARGET_REVISION"', require_empty
    )
    clone_bootstrap = release.index("bootstrap_basic_runtime_role.sql", clone_migrate)
    clone_certificate = release.index(
        "basic_release_contract.py certify-clone", clone_bootstrap
    )
    candidate = release.index("basic_release_contract.py prepare", clone_certificate)
    candidate_verify = release.index(
        "basic_release_contract.py verify-prepare-receipt", candidate
    )
    sealed = release.index("seal_fence \\", candidate_verify)

    commit = release.index("commit_release()")
    retained_nologin = release.index("fence_runtime_roles", commit)
    commit_quiesce = release.index(
        "basic_quiesce_application", retained_nologin
    )
    immutable_reverify = release.index("verify_static_artifacts", commit_quiesce)
    receipt_reverify = release.index(
        "basic_release_contract.py verify-prepare-receipt", immutable_reverify
    )
    commit_topology = release.index(
        "basic_require_release_apfs_topology", receipt_reverify
    )
    commit_intent = release.index("create_commit_attempt_intent", commit_topology)
    protected_opt_in = release.index(
        "CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true", commit_intent
    )
    retained_migrate = release.index(
        "/bin/bash ./scripts/uv.sh run alembic upgrade", protected_opt_in
    )
    retained_bootstrap = release.index(
        "bootstrap_basic_runtime_role.sql", retained_migrate
    )
    live_certificate = release.index(
        "basic_release_contract.py certify-live", retained_bootstrap
    )
    certification_open = release.index(
        "open_release_probe_for_controlled_health", retained_bootstrap
    )
    certification_refence = release.index(
        "close_release_probe_after_controlled_health", live_certificate
    )
    commit_verify = release.index(
        "basic_release_contract.py verify-commit-receipt", certification_refence
    )
    probe_reopen = release.index(
        "open_release_probe_for_controlled_health", commit_verify
    )
    start = release.index(
        '"$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh"', probe_reopen
    )

    assert (
        source_preflight
        < prepare_topology
        < quiesce
        < fence
        < nologin
        < source_revision
        < physical
        < physical_verify
        < logical
        < initdb
        < restore
        < strong_directory
        < strong_system
        < require_empty
        < clone_migrate
        < clone_bootstrap
        < clone_certificate
        < candidate
        < candidate_verify
        < sealed
    )
    assert (
        retained_nologin
        < commit_quiesce
        < immutable_reverify
        < receipt_reverify
        < commit_topology
        < commit_intent
        < protected_opt_in
        < retained_migrate
        < retained_bootstrap
        < certification_open
        < live_certificate
        < certification_refence
        < commit_verify
        < probe_reopen
        < start
    )
    assert release.count("CARESYNC_ALLOW_PROTECTED_LOCAL_ALEMBIC_TARGET=true") == 1
    assert "alembic downgrade" not in release
    assert '5432|5433|5434)' in release
    assert "COMMIT CARESYNC RETAINED 0039 TO 0042" not in release
    assert "CARESYNC_RELEASE_COMMIT_PHRASE" in release


def test_clone_certification_separates_complete_evidence_from_runtime_probe() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    clone_migrate = release.index(
        'alembic upgrade "$CARESYNC_RETAINED_TARGET_REVISION"'
    )
    probe_open = release.index(
        'open_release_probe_for_controlled_health "$clone_port"', clone_migrate
    )
    probe_write_rejection = release.index(
        "prove_release_probe_write_rejection", probe_open
    )
    clone_certificate = release.index(
        "python scripts/basic_release_contract.py certify-clone",
        probe_write_rejection,
    )
    probe_close = release.index(
        'close_release_probe_after_controlled_health "$clone_port"',
        clone_certificate,
    )
    probe_refenced = release.index(
        'require_release_probe_contract nologin "$clone_port"', probe_close
    )
    certification_block = release[
        release.rfind("  backend_env ", probe_write_rejection, clone_certificate) :
        clone_certificate
    ]

    assert (
        'backend_env 127.0.0.1 "$clone_port" "$MIGRATION_USER" ""'
        in certification_block
    )
    assert "$RELEASE_PROBE_USER" not in certification_block
    assert (
        probe_open
        < probe_write_rejection
        < clone_certificate
        < probe_close
        < probe_refenced
    )

    contract = (
        PROJECT_ROOT / "backend" / "scripts" / "basic_release_contract.py"
    ).read_text(encoding="utf-8")
    assert "rolsuper, rolbypassrls" in contract
    assert (
        "Release evidence role cannot bypass FORCE RLS; refusing partial evidence"
        in contract
    )


def test_resume_wrapper_recertifies_exact_0039_and_never_migrates() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    resume = release[release.index("resume_release_0039()") :]
    source_reexec = resume.index("reexec_release_from_captured_source_if_needed")
    guarded_retry = resume.index(
        "# The active fence precedes every boot or long hash.", source_reexec
    )
    retry_fence = resume.index("fence_runtime_roles", guarded_retry)
    quiesce = resume.index("basic_quiesce_application", retry_fence)
    no_clients = resume.index("basic_assert_no_cluster_clients", quiesce)
    exact = resume.index(
        'basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"',
        no_clients,
    )
    artifacts = resume.index("verify_static_artifacts", exact)
    certificate = resume.index(
        "basic_release_contract.py certify-resume-0039", artifacts
    )
    exact_again = resume.index(
        'basic_require_exact_revision "$CARESYNC_RETAINED_SOURCE_REVISION"',
        certificate,
    )
    authorization_verify = resume.index(
        "basic_release_contract.py verify-resume-authorization", certificate
    )
    probe = resume.index(
        "open_release_probe_for_controlled_health", exact_again
    )
    start = resume.index(
        '"$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh"', probe
    )

    assert (
        source_reexec
        < retry_fence
        < quiesce
        < no_clients
        < exact
        < artifacts
        < certificate
        < authorization_verify
        < exact_again
        < probe
        < start
    )
    assert "alembic upgrade" not in resume
    assert "alembic downgrade" not in resume
    assert "remove_matching_fence" not in resume[: resume.index("load_release_run()")]
    wrapper = (PROJECT_ROOT / "scripts" / "resume-basic-0039.sh").read_text(
        encoding="utf-8"
    )
    assert (
        'exec /bin/bash "$ROOT/scripts/basic-release.sh" _resume-0039 "$@"'
        in wrapper
    )


def test_physical_rehearsal_and_emergency_rollback_are_receipt_gated() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    runtime = (PROJECT_ROOT / "scripts" / "lib" / "basic-runtime.sh").read_text(
        encoding="utf-8"
    )
    start = (PROJECT_ROOT / "scripts" / "start-basic.sh").read_text(
        encoding="utf-8"
    )

    prepare = release[release.index("prepare_release()") : release.index("commit_release()")]
    inventory = prepare.index("inventory-physical-backup")
    physical_verify = prepare.index('"$PG_BIN/pg_verifybackup"', inventory)
    physical_copy = prepare.index("basic_materialize_physical_copy", physical_verify)
    observe = prepare.index("observe-physical-rehearsal", physical_copy)
    clean_stop = prepare.index(
        "reconcile_prepare_disposable_postgres", observe
    )
    offline_receipt = prepare.index("certify-physical-rehearsal", clean_stop)
    immutable_context = prepare.index("create_prepared_fence_evidence", offline_receipt)
    candidate = prepare.index("basic_release_contract.py prepare", immutable_context)
    seal = prepare.index("seal_fence", candidate)
    assert (
        inventory
        < physical_verify
        < physical_copy
        < observe
        < clean_stop
        < offline_receipt
        < immutable_context
        < candidate
        < seal
    )
    assert "caresync_basic_app:nologin" in prepare
    assert "caresync_transport_evidence_ingest:nologin" in prepare
    assert "shared_preload_libraries=''" in prepare
    assert "session_preload_libraries=''" in prepare
    assert "local_preload_libraries=''" in prepare
    assert "-c data_directory='$rehearsal_pgdata'" in prepare
    assert "-c config_file='$rehearsal_config_file'" in prepare
    assert 'rehearsal_socket_directory="/private/tmp/' in prepare
    assert "SELECT pg_is_in_recovery()" in prepare
    assert "physical_backup_inventory" in release
    assert "physical_rehearsal_observation" in release
    assert "prepared_fence_context" in release

    rollback = release[release.index("rollback_release()") : release.index("load_release_run()")]
    first_reopen = rollback.index("verify_static_artifacts")
    stop = rollback.index("basic_stop_retained_postgres", first_reopen)
    partial_verify = rollback.index("verify_rollback_copy_matches_backup", stop)
    quarantine = rollback.index("atomic_rollback_rename_no_replace", partial_verify)
    offline_live = rollback.rfind(
        "verify_stopped_pinned_postgres_tree",
        partial_verify,
        quarantine,
    )
    boundary_reopen = rollback.rfind(
        "verify_static_artifacts",
        partial_verify,
        quarantine,
    )
    promote = rollback.index("atomic_rollback_rename_no_replace", quarantine + 1)
    promotion_reopen = rollback.rfind(
        "verify_static_artifacts",
        quarantine,
        promote,
    )
    authorization = rollback.index("certify-resume-0039", promote)
    controlled_start = rollback.index("--rollback-0039", authorization)
    assert (
        first_reopen
        < stop
        < partial_verify
        < boundary_reopen
        < offline_live
        < quarantine
        < promotion_reopen
        < promote
        < authorization
        < controlled_start
    )
    stopped_evidence = rollback.index("create_stopped_0042_evidence")
    stopped_evidence_verify = rollback.index(
        "verify_stopped_0042_evidence",
        stopped_evidence,
    )
    assert (
        boundary_reopen
        < stopped_evidence
        < stopped_evidence_verify
        < offline_live
        < quarantine
    )
    assert "preserve_incomplete_rollback_copy" in rollback
    assert "rollback_copy_verified" in rollback
    starting_phase = rollback.rindex("rollback_starting", promote, authorization)
    restored_boot = rollback.index("basic_start_postgres", starting_phase)
    assert promote < starting_phase < restored_boot < authorization
    assert "--commit-receipt" in rollback
    assert "--finalization-receipt" in rollback
    assert "CARESYNC_RELEASE_ROLLBACK_PHRASE" in rollback
    assert "alembic downgrade" not in rollback
    assert "rm -rf" not in rollback
    assert 'rollback)' in release
    assert "_verify-rollback-start" in release
    assert "_finalize-rollback-start" in release

    assert "/bin/df -P" in runtime
    assert "/usr/sbin/diskutil info -plist" in runtime
    assert "/usr/bin/plutil -extract FilesystemType raw -" in runtime
    assert "stat -f '%T'" not in runtime
    assert 'stat -f \'%d\'' in runtime
    assert 'find "$destination" -xdev' in runtime
    assert "--norsrc --noextattr --noacl --noqtn" in runtime
    assert "--nopersistRootless" in runtime

    finalization = start.index("_finalize-commit-start")
    deferred_push = start.index("start_push_worker", finalization)
    rollback_finalize = start.index("_finalize-rollback-start")
    assert finalization < rollback_finalize < deferred_push
    assert "--rollback-0039" in start

    start_preflight = start.index("basic_require_local_toolchain")
    start_secrets = start.index("basic_runtime_secrets.py")
    start_quiesce = start.index("basic_quiesce_application")
    start_credentials = start.index("configure_basic_runtime_credentials.py")
    assert start_preflight < start_secrets < start_quiesce < start_credentials
    prepare_preflight = prepare.index("basic_require_local_toolchain")
    prepare_quiesce = prepare.index("basic_quiesce_application")
    assert prepare_preflight < prepare_quiesce


def test_interrupted_prepare_recovery_is_private_proven_and_evidence_preserving() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    exact_fence = release[
        release.index("require_exact_preparing_fence()") :
        release.index("require_private_prepare_directory()")
    ]
    disposable = release[
        release.index("reconcile_prepare_disposable_postgres()") :
        release.index("reconcile_interrupted_prepare()")
    ]
    reconcile = release[
        release.index("reconcile_interrupted_prepare()") :
        release.index("require_matching_fence()")
    ]
    prepare = release[
        release.index("prepare_release()") : release.index("commit_release()")
    ]

    assert "exact source-bound preparing fence" in exact_fence
    assert '"$(wc -l <"$context" | tr -d \'[:space:]\')" != "9"' in exact_fence
    assert '"status=prepared"' in exact_fence
    assert "commit/resume-only" in exact_fence
    assert "status=preparing" in exact_fence
    assert "run_directory" in exact_fence
    assert "release_source_root" in exact_fence
    assert "release_source_manifest" in exact_fence
    assert "release_source_manifest_sha256" in exact_fence
    assert "source_revision" in exact_fence
    assert "target_revision" in exact_fence
    assert "app_prior_login" in exact_fence
    assert "ingest_prior_login" in exact_fence
    assert "RELEASE_STATE_DIRECTORY/$run_key" in exact_fence
    assert "basic_assert_no_symlink_components" in exact_fence
    assert "require_fence_only_contains_context" in exact_fence

    assert '"$run_directory/physical-rehearsal"' in reconcile
    assert '"$run_directory/clone"' in reconcile
    assert "reconcile_prepare_disposables_for_run" in reconcile
    prepare_restore = reconcile.index("prepare_post_retirement_role_restoration")
    retire = reconcile.index("remove_preparing_fence", prepare_restore)
    finish_restore = reconcile.index(
        "complete_post_retirement_role_restoration", retire
    )
    assert prepare_restore < retire < finish_restore
    assert "rm -rf" not in reconcile
    assert "rm -f" not in reconcile

    pid_shape = disposable.index('postmaster_pid="$(sed -n \'1p\'')
    executable = disposable.index('lsof -a -p "$postmaster_pid" -d txt', pid_shape)
    listener = disposable.index("basic_collect_tcp_listener_pids", executable)
    online_identity = disposable.index("online_attestation=", listener)
    signal = disposable.index('"$PG_BIN/pg_ctl" -D "$pgdata" stop -m fast')
    assert pid_shape < executable < listener < online_identity < signal
    assert "current_setting('data_directory')" in disposable
    assert "system_identifier::text FROM pg_control_system()" in disposable
    assert "127.0.0.1:$port" in disposable
    assert "process provenance is ambiguous; not signaling it" in disposable
    assert 'kill "$postmaster_pid"' not in disposable
    stale_proof = disposable.index(
        '"$PG_BIN/pg_ctl" -D "$pgdata" status', pid_shape
    )
    stale_preserve = disposable.index(
        "preserve_stale_disposable_postmaster_pid", stale_proof
    )
    assert pid_shape < stale_proof < stale_preserve < executable < signal

    recovery_call = prepare.index("reconcile_interrupted_prepare")
    fresh_fence = prepare.index("  create_fence \\")
    assert recovery_call < fresh_fence


def test_retired_rollback_starting_fence_can_only_reenter_the_same_receipted_run() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    retired = release[
        release.index("require_matching_retired_rollback_fence()") :
        release.index("reactivate_retired_rollback_fence()")
    ]
    reactivate = release[
        release.index("reactivate_retired_rollback_fence()") :
        release.index("create_stopped_0042_evidence()")
    ]
    rollback = release[
        release.index("rollback_release()") : release.index("load_release_run()")
    ]

    assert "status=rollback_starting" in retired
    assert '"candidate_receipt=$candidate_receipt"' in retired
    assert '"commit_receipt=$commit_receipt"' in retired
    assert '"finalization_receipt=$finalization_receipt"' in retired
    assert '"authorization=$authorization"' in retired
    assert '"quarantine_directory=$quarantine_directory"' in retired
    assert '"partial_directory=$partial_directory"' in retired
    assert "source_revision" in retired
    assert "target_revision" in retired
    assert "unexpected metadata" in retired
    assert "durable_rename_private_fence_no_replace" in reactivate
    assert "prepare_reactivation_record" in reactivate
    assert "complete_reactivation_record" in reactivate
    assert "require_matching_rollback_fence" in reactivate
    assert "rollback_context_value authorization" in reactivate

    guard = rollback.index("arm_controlled_runtime_window_cleanup")
    reentry = rollback.index("reactivate_retired_rollback_fence")
    full_reopen = rollback.index("verify_static_artifacts", reentry)
    new_rollback = rollback.index("local new_rollback=false", full_reopen)
    assert guard < reentry < full_reopen < new_rollback
    assert '"$run_directory" != "$RELEASE_STATE_DIRECTORY/$run_key"' in rollback
    assert "Rollback run must be a private direct release-state child" in rollback

    running = rollback.index(
        'if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q',
        reentry,
    )
    identity = rollback.index("basic_verify_retained_identity", running)
    running_fence = rollback.index("fence_runtime_roles", identity)
    running_quiesce = rollback.index("basic_quiesce_application", running_fence)
    down = rollback.index(
        'elif [[ "$early_rollback_status" == "rollback_starting" ]]',
        running_quiesce,
    )
    down_quiesce = rollback.index("basic_quiesce_application", down)
    down_start = rollback.index("basic_start_postgres", down_quiesce)
    down_fence = rollback.index("fence_runtime_roles", down_start)
    assert running < identity < running_fence < running_quiesce
    assert down < down_quiesce < down_start < down_fence < full_reopen
    assert "CARESYNC_RELEASE_ROLLBACK_PHRASE" in rollback


def test_release_shell_pins_identity_fences_every_writer_and_finalizes_after_health() -> None:
    runtime = (PROJECT_ROOT / "scripts" / "lib" / "basic-runtime.sh").read_text(
        encoding="utf-8"
    )
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    start = (PROJECT_ROOT / "scripts" / "start-basic.sh").read_text(encoding="utf-8")

    ready = runtime.index('"$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q')
    identity = runtime.index("basic_verify_retained_identity", ready)
    assert ready < identity
    assert "SHOW data_directory; SELECT system_identifier::text FROM pg_control_system()" in runtime
    assert 'RETAINED_IDENTITY_FILE="$RUNTIME_DIR/retained-postgres.identity"' in runtime
    assert "First retained identity enrollment is allowed only at exact 0039" in runtime
    assert "Port $PGPORT is not serving the configured retained PGDATA" in runtime
    assert '[[ "$(<"$PGDATA/PG_VERSION")" != "17" ]]' in runtime
    assert "A CareSync-signature API writer is running from an unexpected directory" in runtime
    assert "A CareSync-signature push writer is running from an unexpected directory" in runtime
    assert "basic_stop_frontend_listener" in runtime
    assert "basic_cleanup_appledouble_sidecars" in start

    prepare = release[release.index("prepare_release()") : release.index("commit_release()")]
    assert (
        "Both certified CareSync runtime roles must be LOGIN before release preparation"
        in prepare
    )
    prior_state_check = prepare.index(
        '[[ "$ingest_prior_state" != "login" ]]'
    )
    fence_creation = prepare.index("  create_fence \\")
    assert prior_state_check < fence_creation
    assert "basic_set_role_login_state caresync_basic_app nologin" in prepare
    assert (
        "basic_set_role_login_state \\\n"
        "    caresync_transport_evidence_ingest nologin"
    ) in prepare
    assert "basic_require_runtime_roles_fenced" in prepare
    cleanup_obligation = prepare.index(
        "PREPARE_CLEANUP_RETAINED_FENCED=true"
    )
    first_role_mutation = prepare.index(
        "basic_set_role_login_state caresync_basic_app nologin"
    )
    assert cleanup_obligation < first_role_mutation
    assert "reconcile_interrupted_prepare" in prepare
    assert (
        "Writer restoration failed; the preparing fence was retained."
        in prepare
    )
    assert 'candidate_sealed="false"' not in prepare
    assert "PREPARE_CLEANUP_CANDIDATE_SEALED=false" in prepare
    assert """trap 'prepare_cleanup "$?"' EXIT""" in prepare
    assert 'chmod 600 "$run_directory/physical-postgres/backup_manifest"' in prepare
    assert '--artifact "physical_backup_manifest=$PHYSICAL_BACKUP_MANIFEST"' in release
    assert "trap controlled_runtime_window_exit EXIT" in release
    assert "controlled_runtime_window_signal 130" in release
    assert "controlled_runtime_window_signal 143" in release
    assert "refence_interrupted_runtime_window" in release
    assert "require_fence_only_contains_context" in release
    assert "durable_rename_private_fence_no_replace" in release
    assert 'rm -f "$RELEASE_FENCE_DIRECTORY/context"' not in release
    assert 'rmdir "$RELEASE_FENCE_DIRECTORY"' not in release

    assert "CARESYNC_BASIC_RESUME_CERTIFIED" not in start
    assert "CARESYNC_BASIC_RESUME_0039_CONFIRMATION" not in start
    assert "_verify-resume-start" in start
    assert "_finalize-resume-start" in start
    assert "startup_cleanup" in start
    cleanup = start[
        start.index("startup_cleanup()") : start.index("trap startup_cleanup EXIT")
    ]
    assert "basic_set_app_login_state" in cleanup
    assert "caresync_transport_evidence_ingest nologin" in cleanup
    assert "basic_quiesce_application" in start
    assert "no active organization is available" in start

    commit = release[release.index("commit_release()") : release.index("resume_release_0039()")]
    commit_start = commit.index(
        '"$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh"'
    )
    assert commit.index("open_release_probe_for_controlled_health") < commit_start
    resume = release[release.index("resume_release_0039()") : release.index("load_release_run()")]
    resume_start = resume.index(
        '"$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh"'
    )
    assert resume.index("open_release_probe_for_controlled_health") < resume_start
    opener = release[
        release.index("open_runtime_roles_for_controlled_start()") :
        release.index("remove_preparing_fence()")
    ]
    assert "caresync_basic_app login" in opener
    assert "caresync_transport_evidence_ingest login" in opener
    assert "caresync_basic_app nologin" in opener
    assert "caresync_transport_evidence_ingest nologin" in opener

    health = start.index("for url in http://127.0.0.1:3002/api/v1/health")
    resume_finalize = start.index("_finalize-resume-start", health)
    commit_finalize = start.index("_finalize-commit-start", health)
    complete = start.index("STARTUP_COMPLETE=true", commit_finalize)
    assert health < resume_finalize < commit_finalize < complete

    internal_finalize = release.index("finalize_commit_start()")
    finalization = release.index(
        "basic_release_contract.py finalize-live", internal_finalize
    )
    finalization_verify = release.index(
        "basic_release_contract.py verify-finalization-receipt", finalization
    )
    unfence = release.index("remove_matching_fence", finalization_verify)
    assert finalization < finalization_verify < unfence

    commit_finalize = release[
        internal_finalize : release.index("load_retired_prepared_run", internal_finalize)
    ]
    health_quiesce = commit_finalize.index("basic_quiesce_application")
    health_probe_close = commit_finalize.index(
        "close_release_probe_after_controlled_health",
        health_quiesce,
    )
    post_health_window = commit_finalize.index(
        "verify_commit_start_in_bounded_probe_window",
        health_probe_close,
    )
    post_health_no_clients = commit_finalize.index(
        "basic_assert_no_cluster_clients",
        post_health_window,
    )
    post_health_writers_fenced = commit_finalize.index(
        "basic_require_runtime_roles_fenced",
        post_health_no_clients,
    )
    epoch_publish = commit_finalize.index(
        "publish_active_runtime_epoch",
        post_health_writers_fenced,
    )
    fence_retire = commit_finalize.index("remove_matching_fence", epoch_publish)
    assert (
        health_quiesce
        < health_probe_close
        < post_health_window
        < post_health_no_clients
        < post_health_writers_fenced
        < epoch_publish
        < fence_retire
    )


def test_release_probe_cleanup_is_nologin_first_and_covers_recovery_paths() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )

    configure = release[
        release.index("configure_release_probe()") :
        release.index("release_psql_scalar()")
    ]
    configured = configure.index(
        '-f "${RELEASE_EXECUTION_ROOT:-$ROOT}/backend/scripts/'
        'configure_basic_release_probe.sql"'
    )
    configured_contract = configure.index(
        'require_release_probe_contract nologin "$port"',
        configured,
    )
    configured_closed = configure.index(
        'require_release_probe_read_scope closed "$port"',
        configured_contract,
    )
    assert configured < configured_contract < configured_closed

    close = release[
        release.index("close_release_probe_after_controlled_health()") :
        release.index("prove_release_probe_write_rejection()")
    ]
    probe_nologin = close.index('set_release_probe_login_state nologin "$port"')
    scrub = close.index('scrub_release_probe_object_privileges "$port"')
    contract = close.index('require_release_probe_contract nologin "$port"')
    closed = close.index('require_release_probe_read_scope closed "$port"')
    assert probe_nologin < scrub < contract < closed

    fence = release[
        release.index("fence_runtime_roles()") :
        release.index("CONTROLLED_RUNTIME_WINDOW_OPEN=false")
    ]
    app_nologin = fence.index(
        "basic_set_role_login_state caresync_basic_app nologin"
    )
    ingest_nologin = fence.index(
        "basic_set_role_login_state caresync_transport_evidence_ingest nologin"
    )
    probe_nologin = fence.index(
        'basic_set_role_login_state "$RELEASE_PROBE_USER" nologin'
    )
    scrub = fence.index("scrub_release_probe_object_privileges")
    runtime_fenced = fence.index("basic_require_runtime_roles_fenced")
    contract = fence.index("require_release_probe_contract nologin")
    closed = fence.index("require_release_probe_read_scope closed")
    assert (
        app_nologin
        < ingest_nologin
        < probe_nologin
        < scrub
        < runtime_fenced
        < contract
        < closed
    )

    interrupted = release[
        release.index("refence_interrupted_runtime_window()") :
        release.index("controlled_runtime_window_exit()")
    ]
    identity = interrupted.index("basic_verify_retained_identity")
    active_fence = interrupted.index("if ! fence_runtime_roles", identity)
    retired_close = interrupted.index(
        "if ! close_retired_controlled_runtime_after_child_failure",
        active_fence,
    )
    cleared = interrupted.index(
        "CONTROLLED_RUNTIME_WINDOW_OPEN=false",
        retired_close,
    )
    assert identity < active_fence < retired_close < cleared
    assert "fence_runtime_roles || true" not in interrupted

    retired_cleanup = release[
        release.index("close_retired_controlled_runtime_after_child_failure()") :
        release.index("CONTROLLED_RUNTIME_WINDOW_OPEN=false")
    ]
    retired_quiesce = retired_cleanup.index("basic_quiesce_application")
    retired_no_clients = retired_cleanup.index("basic_assert_no_cluster_clients")
    retired_probe_close = retired_cleanup.index(
        "close_release_probe_after_controlled_health"
    )
    retired_failure = retired_cleanup.index('if [[ "$failed" == "true" ]]')
    assert (
        retired_quiesce
        < retired_no_clients
        < retired_probe_close
        < retired_failure
    )

    for name, following in (
        ("commit_release", "resume_release_0039"),
        ("resume_release_0039", "rollback_release"),
        ("rollback_release", "load_release_run"),
    ):
        operation = release[
            release.index(f"{name}()") : release.index(f"{following}()")
        ]
        child_failure = operation[
            operation.index(
                'if ! CARESYNC_INSTALLED_DEPENDENCY_ROOT='
                '"${CARESYNC_INSTALLED_DEPENDENCY_ROOT:-$ROOT}"'
            ) :
        ]
        active_cleanup = child_failure.index("if fence_runtime_roles; then")
        active_clear = child_failure.index(
            "CONTROLLED_RUNTIME_WINDOW_OPEN=false",
            active_cleanup,
        )
        retired_cleanup = child_failure.index(
            "if close_retired_controlled_runtime_after_child_failure; then",
            active_clear,
        )
        retired_clear = child_failure.index(
            "CONTROLLED_RUNTIME_WINDOW_OPEN=false",
            retired_cleanup,
        )
        failure_return = child_failure.index("return 1", retired_clear)
        assert (
            active_cleanup
            < active_clear
            < retired_cleanup
            < retired_clear
            < failure_return
        )
        assert child_failure[:failure_return].count(
            "CONTROLLED_RUNTIME_WINDOW_OPEN=false"
        ) == 2

    restore = release[
        release.index("restore_runtime_role_states_from_private_context()") :
        release.index("post_retirement_role_restoration_completed_path()")
    ]
    assert restore.count(
        "basic_set_role_login_state caresync_basic_app nologin || true"
    ) == 2
    assert restore.count(
        "basic_set_role_login_state "
        "caresync_transport_evidence_ingest nologin || true"
    ) == 2
    probe_close = restore.index(
        "close_release_probe_after_controlled_health"
    )
    app_restore = restore.index(
        'basic_set_role_login_state caresync_basic_app "$app_prior"'
    )
    ingest_restore = restore.index(
        'caresync_transport_evidence_ingest "$ingest_prior"'
    )
    exact_state = restore.index(
        '"$(basic_role_login_state caresync_transport_evidence_ingest)"'
    )
    final_contract = restore.index(
        "require_release_probe_contract nologin",
        exact_state,
    )
    final_closed = restore.index(
        "require_release_probe_read_scope closed",
        final_contract,
    )
    assert (
        probe_close
        < app_restore
        < ingest_restore
        < exact_state
        < final_contract
        < final_closed
    )

    for name, following in (
        ("finalize_rollback_start", "verify_resume_start"),
        ("finalize_resume_start", "verify_commit_start"),
        ("finalize_commit_start", "load_retired_prepared_run"),
    ):
        finalizer = release[
            release.index(f"{name}()") : release.index(f"{following}()")
        ]
        api_health = finalizer.index(
            "curl -fsS http://127.0.0.1:3002/api/v1/health"
        )
        frontend_health = finalizer.index(
            "curl -fsS http://127.0.0.1:5174/",
            api_health,
        )
        quiesce = finalizer.index("basic_quiesce_application", frontend_health)
        probe_close = finalizer.index(
            "close_release_probe_after_controlled_health",
            quiesce,
        )
        no_clients = finalizer.index(
            "basic_assert_no_cluster_clients",
            probe_close,
        )
        writers_fenced = finalizer.index(
            "basic_require_runtime_roles_fenced",
            no_clients,
        )
        assert (
            api_health
            < frontend_health
            < quiesce
            < probe_close
            < no_clients
            < writers_fenced
        )


def test_startup_exposes_manual_billing_only_through_explicit_activation_boundary() -> None:
    start = (PROJECT_ROOT / "scripts" / "start-basic.sh").read_text(encoding="utf-8")

    allowlist_resolution = start.index(
        'BILLING_MANUAL_TARGET_ATTESTATION=""',
    )
    api = start.index(
        'basic_prepare_managed_launch \\\n      "backend" "uvicorn app.main:app"',
        allowlist_resolution,
    )

    assert allowlist_resolution < api
    assert "gated_service_exec.py" in start
    assert 'BILLING_RUNTIME_MODE="${CARESYNC_BASIC_BILLING_MODE:-manual}"' in start
    assert 'BILLING_MANUAL_TARGET_ATTESTATION="PRIVATE_LOCAL_MANUAL_BILLING"' in start
    assert "CARESYNC_BASIC_BILLING_MANUAL_ORGANIZATION_IDS" in start
    assert "WHERE status='active'" in start
    assert "when more than one active organization exists" in start
    assert start.count("ENVIRONMENT=development") == 3
    assert start.count('BILLING_MODE="$BILLING_RUNTIME_MODE"') == 3
    assert start.count(
        'BILLING_MANUAL_ORGANIZATION_IDS="$BILLING_MANUAL_ORGANIZATION_IDS"'
    ) == 3
    assert "manual/private mode ready for explicit owner activation" in start
    assert "activate_billing" not in start


def test_stop_basic_verifies_and_quiesces_api_before_postgres() -> None:
    stop = (PROJECT_ROOT / "scripts" / "stop-basic.sh").read_text(encoding="utf-8")

    layout = stop.index("basic_require_runtime_layout")
    identity = stop.index("basic_verify_retained_identity", layout)
    quiescent = stop.index("basic_quiesce_application", identity)
    sessions = stop.index("basic_assert_no_database_clients", quiescent)
    postgres_stop = stop.index("basic_stop_retained_postgres")

    assert layout < identity < quiescent < sessions < postgres_stop
    assert "running but not ready enough to prove identity" in stop
    assert "remove_matching_fence" not in stop
    assert "rmdir" not in stop
