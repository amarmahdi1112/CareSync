"""Production first-activation recovery and interruption contracts."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = PROJECT_ROOT / "deploy" / "scripts" / "deploy-release.sh"
ROLLBACK_SCRIPT = PROJECT_ROOT / "deploy" / "scripts" / "rollback-release.sh"


def _source() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _rollback_source() -> str:
    return ROLLBACK_SCRIPT.read_text(encoding="utf-8")


def _function(source: str, name: str, following: str) -> str:
    return source[source.index(f"{name}()") : source.index(f"{following}()")]


def test_production_deploy_script_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["/bin/bash", "-n", str(DEPLOY_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_production_release_revision_matches_the_sole_alembic_head() -> None:
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "backend" / "alembic"),
    )
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == ["0043_org_wide_room_presence"]
    expected = heads[0]

    build = (
        PROJECT_ROOT / "deploy" / "scripts" / "build-release.sh"
    ).read_text(encoding="utf-8")
    validator = (
        PROJECT_ROOT / "deploy" / "scripts" / "validate-release-archive.py"
    ).read_text(encoding="utf-8")
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert f'"database_revision": "{expected}"' in build
    assert f'EXPECTED_REVISION = "{expected}"' in validator
    assert f'readonly expected_revision="{expected}"' in deploy
    assert f"upgrade {expected}" in deploy


def test_first_activation_requires_the_exact_provisioned_baseline_before_mutation() -> None:
    source = _source()
    trap_start = source.index("trap 'recover_failed_deployment")
    pre_mutation = source[:trap_start]
    certificate = _function(
        source,
        "certify_first_activation_security_baseline",
        "restore_first_activation_security_baseline",
    )

    assert 'first_activation=1' in pre_mutation
    assert '[[ "$api_initial_state" != "inactive" ]]' in pre_mutation
    assert '[[ "$push_initial_state" != "inactive" ]]' in pre_mutation
    assert (
        pre_mutation.rindex("certify_first_activation_security_baseline")
        < trap_start
    )

    for exact_role in (
        "caresync_basic_app",
        "caresync_transport_command_owner",
        "caresync_transport_evidence_ingest",
    ):
        assert exact_role in certificate
    for exact_attribute in (
        "NOT identity.rolsuper",
        "NOT identity.rolinherit",
        "NOT identity.rolcreaterole",
        "NOT identity.rolcreatedb",
        "NOT identity.rolreplication",
        "NOT identity.rolbypassrls",
        "identity.rolconnlimit=-1",
        "identity.rolvaliduntil IS NULL",
        "identity.rolpassword IS NOT NULL",
        "identity.rolpassword IS NULL",
        "ARRAY['search_path=public, pg_catalog']::text[]",
    ):
        assert exact_attribute in certificate
    assert "pg_catalog.left(rolname,9)='caresync_'" in certificate
    assert "first-activation CareSync role inventory differs" in certificate
    assert "pg_catalog.pg_auth_members" in certificate
    assert "pg_catalog.pg_db_role_setting" in certificate
    assert "setting.setdatabase<>0" in certificate
    assert "database_owner" in certificate
    assert "database_allows_connections" in certificate
    assert "database_connection_limit<>-1" in certificate
    assert "pg_catalog.aclexplode" in certificate
    assert "privilege.grantee IN (app_role,ingest_role)" in certificate
    assert "privilege.privilege_type='CONNECT'" in certificate
    assert "namespace.nspname='public'" in certificate
    assert "relation.relkind IN ('r','p')" in certificate


def test_first_activation_restore_recreates_roles_and_exact_database_acl() -> None:
    source = _source()
    restore = _function(
        source,
        "restore_first_activation_security_baseline",
        "certify_services_inactive_during_recovery",
    )

    reassign = restore.index("REASSIGN OWNED BY %I TO postgres")
    drop_owned = restore.index("DROP OWNED BY %I", reassign)
    drop_role = restore.index("DROP ROLE %I", drop_owned)
    create_app = restore.index("CREATE ROLE caresync_basic_app", drop_role)
    create_owner = restore.index(
        "CREATE ROLE caresync_transport_command_owner", create_app
    )
    create_ingest = restore.index(
        "CREATE ROLE caresync_transport_evidence_ingest", create_owner
    )
    database_owner = restore.index(
        "ALTER DATABASE caresync OWNER TO postgres", create_ingest
    )
    revoke_public = restore.index(
        "REVOKE ALL PRIVILEGES ON DATABASE caresync FROM PUBLIC",
        database_owner,
    )
    grant_app = restore.index(
        "GRANT CONNECT ON DATABASE caresync TO caresync_basic_app",
        revoke_public,
    )
    grant_ingest = restore.index(
        "GRANT CONNECT ON DATABASE caresync TO caresync_transport_evidence_ingest",
        grant_app,
    )
    passwords = restore.index("bind_runtime_passwords", grant_ingest)
    certificate = restore.index(
        "certify_first_activation_security_baseline", passwords
    )

    assert (
        reassign
        < drop_owned
        < drop_role
        < create_app
        < create_owner
        < create_ingest
        < database_owner
        < revoke_public
        < grant_app
        < grant_ingest
        < passwords
        < certificate
    )
    assert "ALLOW_CONNECTIONS true" in restore
    assert "CONNECTION LIMIT -1" in restore
    assert restore.count("NOINHERIT") == 3
    assert restore.count("NOSUPERUSER") == 3
    assert restore.count("NOBYPASSRLS") == 3


def test_failure_recovery_is_bounded_and_claims_success_only_after_certification() -> None:
    source = _source()
    bounded = _function(
        source,
        "run_bounded_recovery_command",
        "run_maybe_bounded_command",
    )
    recovery_start = source.index("recover_failed_deployment()")
    recovery = source[
        recovery_start : source.index("\ntrap cleanup EXIT", recovery_start)
    ]

    assert "recovery_deadline - SECONDS" in source
    assert "recovery_budget_seconds=600" in source
    assert "remaining_recovery_seconds" in bounded
    assert "timeout" in bounded
    assert "--foreground" in bounded
    assert "--signal=TERM" in bounded
    assert "--kill-after=10s" in bounded

    stop = recovery.index("run_bounded_recovery_command")
    stopped = recovery.index(
        "certify_services_inactive_during_recovery", stop
    )
    sealed_backup = recovery.index(
        "sha256sum --check --strict SHA256SUMS", stopped
    )
    database = recovery.index("restore_database", sealed_backup)
    roles = recovery.index(
        "restore_first_activation_security_baseline", database
    )
    remove_link = recovery.index(
        'run_bounded_recovery_command rm -f -- "$current_link"', roles
    )
    certified = recovery.index(
        "certify_first_activation_recovery", remove_link
    )
    cleanup = recovery.index("if ! cleanup", certified)
    fatal_gate = recovery.index('if [[ "$recovery_failed" -ne 0 ]]', cleanup)
    success_claim = recovery.index(
        "CareSync first-activation baseline was restored and certified",
        fatal_gate,
    )

    assert (
        stop
        < stopped
        < sealed_backup
        < database
        < roles
        < remove_link
        < certified
        < cleanup
        < fatal_gate
        < success_claim
    )
    assert (
        "FATAL: CareSync automatic recovery could not fully certify "
        "the prior state; operator attention is required."
        in recovery
    )
    assert (
        'run_bounded_recovery_command \\\n'
        '         ln -sfn "$previous_target" "$current_link.rollback"'
        in recovery
    )
    assert (
        'run_bounded_recovery_command \\\n'
        '         mv -Tf "$current_link.rollback" "$current_link"'
        in recovery
    )


def test_err_and_terminal_signals_arm_before_live_mutation() -> None:
    source = _source()
    err_trap = source.index("trap 'recover_failed_deployment \"$?\" ERR' ERR")
    int_trap = source.index("trap 'recover_failed_deployment 130 INT' INT")
    term_trap = source.index("trap 'recover_failed_deployment 143 TERM' TERM")
    hup_trap = source.index("trap 'recover_failed_deployment 129 HUP' HUP")
    mutation = source.index(
        'systemctl stop "$push_service_name" "$service_name"', hup_trap
    )
    clear = source.rindex("trap - ERR INT TERM HUP")
    mutating_tail = source[mutation:clear]

    assert err_trap < int_trap < term_trap < hup_trap < mutation < clear
    assert "migration_started=1" in mutating_tail
    assert mutating_tail.index("migration_started=1") < mutating_tail.index(
        "upgrade 0043_org_wide_room_presence"
    )
    assert not re.search(r"(?m)^[ \t]*exit[ \t]+[0-9$]", mutating_tail)
    assert mutating_tail.count("fail_deployment_after_mutation 70") == 3


def test_active_release_geometry_is_sealed_before_incoming_release_mutation() -> None:
    source = _source()
    current_capture = source.index('if [[ -L "$current_link" ]]')
    release_mutation = source.index('if [[ -e "$release_path" ]]')
    captured = source[current_capture:release_mutation]

    assert current_capture < release_mutation
    assert 'previous_target="$(readlink -f "$current_link"' in captured
    assert '[[ ! "$previous_release_name" =~ ^[0-9a-f]{40}$ ]]' in captured
    assert '"$releases_root/$previous_release_name"' in captured
    assert "release-manifest.json" in captured
    assert '[[ "$previous_manifest_sha" != "$previous_release_name" ]]' in captured
    assert 'first_activation=1' in captured


def test_external_delivery_and_retention_run_after_the_core_commit_boundary() -> None:
    source = _source()
    recovery_trap = source.index("trap 'recover_failed_deployment")
    gate = source.index("activate_traffic_gate", recovery_trap)
    service_stop = source.index(
        'systemctl stop "$push_service_name" "$service_name"',
        gate,
    )
    health = source.rindex("if ! certify_local_health; then")
    commit = source.rindex("trap - ERR INT TERM HUP")
    reopen = source.index("deactivate_traffic_gate", commit)
    public_health = source.index("certify_public_health", reopen)
    nginx_reload = source.index("systemctl reload nginx", commit)
    push_restart = source.index(
        'systemctl restart "$push_service_name"',
        nginx_reload,
    )
    retention = source.index(
        'find "$releases_root" -mindepth 1',
        push_restart,
    )

    assert recovery_trap < gate < service_stop
    assert (
        health
        < commit
        < reopen
        < public_health
        < nginx_reload
        < push_restart
        < retention
    )
    assert "post_commit_failed=1" in source[commit:retention]
    nginx = (
        PROJECT_ROOT / "deploy" / "nginx" / "caresync.conf.template"
    ).read_text(encoding="utf-8")
    assert "if (-f /run/caresync-maintenance)" in nginx
    assert "return 503;" in nginx


def test_database_recovery_is_atomic_and_recertifies_sealed_contents() -> None:
    source = _source()
    restore = _function(source, "restore_database", "bind_runtime_passwords")
    certificate = _function(
        source,
        "certify_first_activation_recovery",
        "recover_failed_deployment",
    )

    assert "--single-transaction" in restore
    assert "--exit-on-error" in restore
    assert "dropdb --if-exists --force caresync" in restore
    assert "--template=template0" in restore
    assert "--owner=postgres" in restore
    assert "recovery_database_restored" in certificate
    assert "database.dump" in certificate
    assert "SHA256SUMS" in certificate
    assert "sha256sum --check --strict SHA256SUMS" in certificate
    assert "certify_first_activation_security_baseline" in certificate
    assert '[[ -e "$current_link" ]]' in certificate
    assert '[[ -L "$current_link" ]]' in certificate
    assert '[[ "$api_initial_state" != "inactive" ]]' in certificate
    assert '[[ "$push_initial_state" != "inactive" ]]' in certificate


def test_production_rollback_script_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["/bin/bash", "-n", str(ROLLBACK_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_rollback_traffic_gate_fences_every_live_mutation() -> None:
    source = _rollback_source()
    err_trap = source.index("trap 'recover_failed_rollback \"$?\" ERR' ERR")
    int_trap = source.index("trap 'recover_failed_rollback 130 INT' INT")
    term_trap = source.index("trap 'recover_failed_rollback 143 TERM' TERM")
    hup_trap = source.index("trap 'recover_failed_rollback 129 HUP' HUP")
    gate = source.index("\nactivate_traffic_gate\n", hup_trap)
    service_stop = source.index(
        'systemctl stop "$push_service_name" "$service_name"',
        gate,
    )
    database_mutation = source.index("database_mutated=1", service_stop)
    pointer_mutation = source.index(
        'ln -sfn "$target" "$current_link.next"',
        service_stop,
    )
    local_health = source.rindex("if ! certify_local_health; then")
    commit = source.rindex("trap - ERR INT TERM HUP")
    staged_gate_cleanup = source.index(
        'rm -f -- "${maintenance_flag}.next.$$"',
        commit,
    )
    reopen = source.index("deactivate_traffic_gate", staged_gate_cleanup)
    public_health = source.index("certify_public_health", reopen)
    push_restart = source.index(
        'systemctl start "$push_service_name"',
        public_health,
    )
    mutating_region = source[gate:commit]

    assert (
        err_trap
        < int_trap
        < term_trap
        < hup_trap
        < gate
        < service_stop
        < database_mutation
        < pointer_mutation
        < local_health
        < commit
        < staged_gate_cleanup
        < reopen
        < public_health
        < push_restart
    )
    assert not re.search(r"(?m)^[ \t]*exit[ \t]+[0-9$]", mutating_region)
    assert mutating_region.count("fail_rollback_after_mutation 70") == 3


def test_rollback_gate_is_atomic_typed_and_observable_before_use() -> None:
    source = _rollback_source()
    gate = _function(source, "activate_traffic_gate", "deactivate_traffic_gate")
    certificate = _function(
        source,
        "certify_traffic_gate_active",
        "activate_traffic_gate",
    )
    mutation_traps = source.index("trap 'recover_failed_rollback")
    gate_call = source.index("\nactivate_traffic_gate\n", mutation_traps)
    pre_mutation = source[:gate_call]

    assert 'readonly maintenance_flag="/run/caresync-maintenance"' in source
    assert '[[ -e "$maintenance_flag" || -L "$maintenance_flag" ]]' in pre_mutation
    assert 'local gate_next="${maintenance_flag}.next.$$"' in gate
    assert "install -o root -g root -m 0644 /dev/null" in gate
    assert 'mv -Tf -- "$gate_next" "$maintenance_flag"' in gate
    assert gate.count("run_maybe_bounded_command") == 2
    assert gate.index("traffic_gate_mutated=1") < gate.index("install -o root")
    assert gate.index("mv -Tf") < gate.index("certify_traffic_gate_active")
    assert '[[ -f "$maintenance_flag" && ! -L "$maintenance_flag" ]]' in certificate
    assert '"root:root:644"' in certificate
    assert '[[ "$(public_health_status)" == "503" ]]' in certificate


def test_rollback_recovery_is_bounded_deferred_and_ordered() -> None:
    source = _rollback_source()
    bounded = _function(
        source,
        "run_bounded_recovery_command",
        "run_maybe_bounded_command",
    )
    recovery_start = source.index("recover_failed_rollback()")
    recovery = source[
        recovery_start
        : source.index(
            "\n# From this point onward every failure restores",
            recovery_start,
        )
    ]

    assert "recovery_deadline - SECONDS" in source
    assert "recovery_budget_seconds=600" in source
    assert "remaining_recovery_seconds" in bounded
    assert "timeout" in bounded
    assert "--foreground" in bounded
    assert "--signal=TERM" in bounded
    assert "--kill-after=10s" in bounded
    assert "trap - ERR" in recovery
    assert "trap 'recovery_interrupted=1' INT TERM HUP" in recovery
    assert "trap - ERR INT TERM HUP" not in recovery

    service_stop = recovery.index("run_bounded_recovery_command")
    database = recovery.index(
        'restore_database "$safety_backup/database.dump"',
        service_stop,
    )
    roles = recovery.index('bind_runtime_roles "$previous_target"', database)
    vault = recovery.index(
        'install_vault_archive "$safety_backup/private-vaults.tar.gz"',
        roles,
    )
    staged_gate_cleanup = recovery.index(
        'rm -f -- "${maintenance_flag}.next.$$"',
        vault,
    )
    pointer = recovery.index(
        'ln -sfn "$previous_target" "$current_link.recovery"',
        staged_gate_cleanup,
    )
    api_start = recovery.index(
        'systemctl start "$service_name"',
        pointer,
    )
    local_health = recovery.index("certify_local_health", api_start)
    reopen = recovery.index("deactivate_traffic_gate", local_health)
    public_health = recovery.index("certify_public_health", reopen)
    push_start = recovery.index(
        'systemctl start "$push_service_name"',
        public_health,
    )
    fatal_gate = recovery.index('if [[ "$recovery_failed" -ne 0 ]]', push_start)
    gate_recertification = recovery.index(
        "if certify_traffic_gate_active; then",
        fatal_gate,
    )
    gate_reactivation = recovery.index(
        "if activate_traffic_gate && certify_traffic_gate_active; then",
        gate_recertification,
    )
    fail_closed_stop = recovery.index(
        'systemctl stop "$push_service_name" "$service_name"',
        gate_reactivation,
    )
    success_claim = recovery.index(
        "CareSync pre-rollback state was restored and certified.",
        fail_closed_stop,
    )

    assert (
        service_stop
        < database
        < roles
        < vault
        < staged_gate_cleanup
        < pointer
        < api_start
        < local_health
        < reopen
        < public_health
        < push_start
        < fatal_gate
        < gate_recertification
        < gate_reactivation
        < fail_closed_stop
        < success_claim
    )
    assert (
        '[[ "$traffic_gate_mutated" -eq 1 &&\n'
        '        "$recovery_failed" -eq 0 ]]'
        in recovery
    )
    assert (
        "FATAL: CareSync automatic rollback recovery could not fully certify "
        "the prior state; operator attention is required."
        in recovery
    )


def test_rollback_database_restore_is_transactional_and_recovery_aware() -> None:
    source = _rollback_source()
    restore = _function(source, "restore_database", "install_vault_archive")

    assert "run_maybe_bounded_command" in restore
    assert "dropdb --if-exists --force caresync" in restore
    assert "--template=template0" in restore
    assert "--encoding=UTF8" in restore
    assert "--owner=postgres" in restore
    assert "--exit-on-error" in restore
    assert "--single-transaction" in restore
    assert "--no-owner" in restore
    assert "--role=postgres" in restore


def test_gate_failure_cannot_cross_the_live_mutation_fence() -> None:
    scripts = (
        (
            _source(),
            "recover_failed_deployment",
            "\ntrap cleanup EXIT",
        ),
        (
            _rollback_source(),
            "recover_failed_rollback",
            "\n# From this point onward every failure restores",
        ),
    )

    for source, recovery_name, recovery_end_marker in scripts:
        recovery_start = source.index(f"{recovery_name}()")
        recovery = source[
            recovery_start
            : source.index(recovery_end_marker, recovery_start)
        ]
        trap_start = source.index(f"trap '{recovery_name}")
        gate_call = source.index("\nactivate_traffic_gate\n", trap_start)
        mutation_marker = source.index(
            "\nlive_mutation_started=1\n",
            gate_call,
        )
        service_stop = source.index(
            'systemctl stop "$push_service_name" "$service_name"',
            mutation_marker,
        )
        pre_gate = source[:gate_call]
        gate = _function(
            source,
            "activate_traffic_gate",
            "deactivate_traffic_gate",
        )
        gate_lines = [
            line.strip() for line in gate.splitlines() if line.strip()
        ]

        assert source.count("live_mutation_started=0") == 1
        assert source.count("live_mutation_started=1") == 1
        assert gate_lines[-2:] == ["certify_traffic_gate_active", "}"]
        assert gate_call < mutation_marker < service_stop
        assert source[gate_call:service_stop].count(
            "certify_traffic_gate_active"
        ) == 0
        assert (
            source[gate_call:service_stop]
            == "\nactivate_traffic_gate\nlive_mutation_started=1\n"
        )

        api_capture = pre_gate.rindex(
            'api_initial_state="$(\n'
            '  systemctl show --property=ActiveState --value "$service_name"'
        )
        push_capture = pre_gate.rindex(
            'push_initial_state="$(\n'
            '  systemctl show --property=ActiveState --value '
            '"$push_service_name"'
        )
        assert api_capture < push_capture < trap_start < gate_call

        early_branch = recovery.index(
            'if [[ "$live_mutation_started" -eq 0 ]]; then'
        )
        recovery_service_stop = recovery.index(
            'systemctl stop "$push_service_name" "$service_name"',
            early_branch,
        )
        pre_mutation_recovery = recovery[early_branch:recovery_service_stop]

        assert "deactivate_traffic_gate" in pre_mutation_recovery
        assert (
            'systemctl show --property=ActiveState --value "$service_name"'
            in pre_mutation_recovery
        )
        assert (
            'systemctl show --property=ActiveState --value '
            '"$push_service_name"'
            in pre_mutation_recovery
        )
        assert (
            '[[ "$api_recovered_state" != "$api_initial_state" ||'
            in pre_mutation_recovery
        )
        assert (
            '"$push_recovered_state" != "$push_initial_state" ]]'
            in pre_mutation_recovery
        )
        state_comparison = pre_mutation_recovery.index(
            '[[ "$api_recovered_state" != "$api_initial_state" ||'
        )
        public_guard = pre_mutation_recovery.index(
            'if [[ "$api_initial_state" == "active" &&',
            state_comparison,
        )
        public_certificate = pre_mutation_recovery.index(
            "! certify_public_health",
            public_guard,
        )
        failure_gate = pre_mutation_recovery.index(
            'if [[ "$recovery_failed" -ne 0 ]]',
            public_certificate,
        )
        clean_exit = pre_mutation_recovery.index(
            'exit "$exit_status"',
            failure_gate,
        )
        assert (
            state_comparison
            < public_guard
            < public_certificate
            < failure_gate
            < clean_exit
        )
        assert '"$recovery_failed" -eq 0 ]]' in pre_mutation_recovery[
            public_guard:public_certificate
        ]
        assert (
            'certify_public_health() {\n'
            '  [[ "$(public_health_status)" == "200" ]]\n'
            "}"
            in source
        )
        assert 'exit "$exit_status"' in pre_mutation_recovery
        assert not re.search(
            r"systemctl[ \t\\\n]+"
            r"(?:stop|start|restart|reload|enable|disable)\b",
            pre_mutation_recovery,
        )
        for forbidden_mutation in (
            "restore_database",
            "bind_runtime_roles",
            "activate_ocr_runtime",
            'ln -sfn "$previous_target"',
        ):
            assert forbidden_mutation not in pre_mutation_recovery


def test_rollback_release_identity_is_sealed_before_live_state_capture() -> None:
    source = _rollback_source()
    service_state_capture = source.index('api_initial_state="$(')
    sealed = source[:service_state_capture]
    target_geometry = sealed[
        sealed.index('target="$releases_root/$target_sha"')
        : sealed.index("target_ocr_lock=")
    ]
    target_manifest = sealed[
        sealed.index('python3 - "$target/release-manifest.json" "$target_sha"')
        : sealed.index("exec 9>")
    ]
    active_geometry = sealed[
        sealed.index('previous_target=""')
        : sealed.index('configured_origin="$(tr')
    ]

    assert '! -d "$target"' in target_geometry
    assert '-L "$target"' in target_geometry
    assert '! -f "$target/release-manifest.json"' in target_geometry
    assert '-L "$target/release-manifest.json"' in target_geometry
    assert 'manifest.get("schema") != "caresync-release-v1"' in target_manifest
    assert 'manifest.get("git_sha") != sys.argv[2]' in target_manifest
    assert 'python3 - "$target/release-manifest.json" "$target_sha"' in (
        target_manifest
    )
    assert 'previous_target="$(readlink -f "$current_link")"' in active_geometry
    assert (
        '! "$previous_release_name" =~ ^[0-9a-f]{40}$'
        in active_geometry
    )
    assert (
        '"$previous_target" != "$releases_root/$previous_release_name"'
        in active_geometry
    )
    assert '! -d "$previous_target"' in active_geometry
    assert '-L "$previous_target"' in active_geometry
    assert (
        '! -f "$previous_target/release-manifest.json"' in active_geometry
    )
    assert '-L "$previous_target/release-manifest.json"' in active_geometry
    assert 'manifest.get("schema") != "caresync-release-v1"' in active_geometry
    assert (
        '[[ "$previous_manifest_sha" != "$previous_release_name" ]]'
        in active_geometry
    )
    assert source.index("exec 9>") < source.index('previous_target=""')
    assert (
        source.index(
            '[[ "$previous_manifest_sha" != "$previous_release_name" ]]'
        )
        < service_state_capture
        < source.index("trap 'recover_failed_rollback")
    )


def test_recovery_service_stop_certification_is_exact_and_bounded() -> None:
    scripts = (
        (
            _source(),
            "recover_failed_deployment",
            "\ntrap cleanup EXIT",
        ),
        (
            _rollback_source(),
            "recover_failed_rollback",
            "\n# From this point onward every failure restores",
        ),
    )

    for source, recovery_name, recovery_end_marker in scripts:
        certificate = _function(
            source,
            "certify_services_inactive_during_recovery",
            "certify_local_health",
        )
        recovery_start = source.index(f"{recovery_name}()")
        recovery = source[
            recovery_start
            : source.index(recovery_end_marker, recovery_start)
        ]
        early_exit = recovery.index('exit "$exit_status"')
        stop = recovery.index(
            'systemctl stop "$push_service_name" "$service_name"',
            early_exit,
        )
        certified = recovery.index(
            "certify_services_inactive_during_recovery",
            stop,
        )
        first_restore = recovery.index("restore_database", certified)

        assert certificate.count("run_bounded_recovery_command") == 2
        assert certificate.count(
            "systemctl show --property=ActiveState --value"
        ) == 2
        assert '[[ "$api_state" == "inactive"' in certificate
        assert '"$push_state" == "inactive" ]]' in certificate
        assert "systemctl is-active" not in certificate
        assert stop < certified < first_restore
        assert (
            '[[ "$recovery_failed" -eq 0 ]]'
            in recovery[stop:certified]
        )


def test_upgrade_certifies_shared_ocr_directories_without_mutating_them() -> None:
    source = _source()
    certificate = _function(
        source,
        "certify_ocr_shared_directory",
        "certify_ocr_runtime_permissions",
    )
    setup_start = source.index(
        'if [[ "$first_activation" -eq 1 ]]; then',
        source.index("readonly ocr_lock_path="),
    )
    setup_end = source.index(
        'if [[ -L "$ocr_candidate" ]]',
        setup_start,
    )
    setup = source[setup_start:setup_end]
    first_activation, upgrade = setup.split(
        "elif ! certify_ocr_shared_directory",
        maxsplit=1,
    )

    assert "install -d -o root -g caresync -m 0750" in first_activation
    assert "install -d -o caresync -g caresync -m 0700" in first_activation
    assert '[[ -d "$directory_path" && ! -L "$directory_path" ]]' in certificate
    assert "stat -c '%U:%G:%a'" in certificate
    assert not re.search(
        r"(?m)^[ \t]*(?:install|chown|chmod|mkdir|rm|mv)\b",
        certificate,
    )
    assert '"$ocr_root" "root:caresync:750"' in setup
    assert '"$ocr_versions_root" "root:caresync:750"' in setup
    for shared_home in (
        '"$ocr_home" "caresync:caresync:700"',
        '"$ocr_home/cache" "caresync:caresync:700"',
        '"$ocr_home/paddlex" "caresync:caresync:700"',
        '"$ocr_home/paddle" "caresync:caresync:700"',
    ):
        assert shared_home in setup
    assert not re.search(
        r"(?m)^[ \t]*(?:install|chown|chmod|mkdir|rm|mv)\b",
        upgrade,
    )
    assert (
        "The active CareSync OCR directory geometry is not certified."
        in upgrade
    )


def test_service_state_is_fenced_around_pre_activation_preparation() -> None:
    source = _source()
    active_release_sealed = source.index(
        '[[ "$previous_manifest_sha" != "$previous_release_name" ]]'
    )
    api_initial = source.index('api_initial_state="$(', active_release_sealed)
    push_initial = source.index('push_initial_state="$(', api_initial)
    first_activation_refusal = source.index(
        'if [[ "$first_activation" -eq 1 ]] &&',
        push_initial,
    )
    release_mutation = source.index(
        'if [[ -e "$release_path" ]]',
        first_activation_refusal,
    )
    ocr_shared_setup = source.index(
        'if [[ "$first_activation" -eq 1 ]]; then',
        source.index("readonly ocr_lock_path="),
    )
    api_pre_gate = source.index('api_pre_gate_state="$(', ocr_shared_setup)
    push_pre_gate = source.index('push_pre_gate_state="$(', api_pre_gate)
    state_drift_refusal = source.index(
        'if [[ "$api_pre_gate_state" != "$api_initial_state" ||',
        push_pre_gate,
    )
    first_activation_certificate = source.index(
        "certify_first_activation_security_baseline",
        state_drift_refusal,
    )
    recovery_trap = source.index(
        "trap 'recover_failed_deployment",
        first_activation_certificate,
    )
    gate = source.index("\nactivate_traffic_gate\n", recovery_trap)

    assert (
        active_release_sealed
        < api_initial
        < push_initial
        < first_activation_refusal
        < release_mutation
        < ocr_shared_setup
        < api_pre_gate
        < push_pre_gate
        < state_drift_refusal
        < first_activation_certificate
        < recovery_trap
        < gate
    )
    refusal = source[first_activation_refusal:release_mutation]
    assert '[[ "$api_initial_state" != "inactive" ]]' in refusal
    assert '[[ "$push_initial_state" != "inactive" ]]' in refusal
    drift = source[state_drift_refusal:first_activation_certificate]
    assert '"$push_pre_gate_state" != "$push_initial_state"' in drift
    assert "CareSync service state changed during deployment preflight." in drift
    assert re.search(r"(?m)^[ \t]*exit 66$", drift)


def test_failed_recovery_requires_a_certified_core_or_public_fence() -> None:
    scripts = (
        (
            _source(),
            "recover_failed_deployment",
            "\ntrap cleanup EXIT",
        ),
        (
            _rollback_source(),
            "recover_failed_rollback",
            "\n# From this point onward every failure restores",
        ),
    )

    for source, recovery_name, recovery_end_marker in scripts:
        recovery_start = source.index(f"{recovery_name}()")
        recovery = source[
            recovery_start
            : source.index(recovery_end_marker, recovery_start)
        ]
        core = recovery.index(
            'if [[ "$recovery_failed" -eq 0 ]]; then\n'
            "    recovery_core_certified=1"
        )
        fatal = recovery.index(
            'if [[ "$recovery_failed" -ne 0 ]]',
            core,
        )
        existing_fence = recovery.index(
            "if certify_traffic_gate_active; then",
            fatal,
        )
        rebuild_fence = recovery.index(
            "if activate_traffic_gate && certify_traffic_gate_active; then",
            existing_fence,
        )
        no_safe_fence = recovery.index(
            'if [[ "$recovery_gate_certified" -eq 0 &&',
            rebuild_fence,
        )
        preserve_certified_core = recovery.index(
            "the restored API was left running for operator attention.",
            no_safe_fence,
        )
        operator_exit = recovery.index("exit 72", preserve_certified_core)
        fail_closed_stop = recovery.index(
            'systemctl stop "$push_service_name" "$service_name"',
            operator_exit,
        )
        fatal_exit = recovery.index("exit 71", fail_closed_stop)

        assert source.count("recovery_core_certified=1") == 1
        assert (
            core
            < fatal
            < existing_fence
            < rebuild_fence
            < no_safe_fence
            < preserve_certified_core
            < operator_exit
            < fail_closed_stop
            < fatal_exit
        )
        protected_branch = recovery[no_safe_fence:operator_exit]
        assert '"$recovery_core_certified" -eq 1' in protected_branch
        assert '"$api_was_active" -eq 1' in protected_branch
        assert (
            protected_branch.index('"$recovery_core_certified" -eq 1')
            < protected_branch.index('"$api_was_active" -eq 1')
        )


def test_release_link_staging_cleanup_never_removes_non_symlink_objects() -> None:
    deploy = _source()
    deploy_cleanup = _function(deploy, "cleanup", "abort_before_mutation")
    rollback = _rollback_source()
    rollback_cleanup = _function(
        rollback,
        "cleanup_temporary_release_links",
        "certify_services_inactive_during_recovery",
    )

    for cleanup, expected_links in (
        (
            deploy_cleanup,
            ('"$current_link.next"', '"$current_link.rollback"'),
        ),
        (
            rollback_cleanup,
            ('"$current_link.next"', '"$current_link.recovery"'),
        ),
    ):
        for expected_link in expected_links:
            assert expected_link in cleanup
        symlink_guard = cleanup.index('if [[ -L "$temporary_link" ]]')
        removal = cleanup.index('rm -f -- "$temporary_link"', symlink_guard)
        unsafe_object = cleanup.index(
            'elif [[ -e "$temporary_link" ]]',
            removal,
        )
        rejected = cleanup.index("cleanup_failed=1", unsafe_object)

        assert symlink_guard < removal < unsafe_object < rejected
        assert cleanup.count('rm -f -- "$temporary_link"') in {1, 2}
        assert "rm -rf -- \"$temporary_link\"" not in cleanup

    rollback_recovery_start = rollback.index("recover_failed_rollback()")
    rollback_recovery = rollback[
        rollback_recovery_start
        : rollback.index(
            "\n# From this point onward every failure restores",
            rollback_recovery_start,
        )
    ]
    cleanup_call = rollback_recovery.index("cleanup_temporary_release_links")
    recovery_link = rollback_recovery.index(
        'ln -sfn "$previous_target" "$current_link.recovery"',
        cleanup_call,
    )
    assert cleanup_call < recovery_link
