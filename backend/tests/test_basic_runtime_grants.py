"""Keep the least-privilege PostgreSQL bootstrap synchronized with Basic schema growth."""

import hashlib
import re
import subprocess
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.basic.models import BasicBase
from app.core.config import Settings
from app.db.session import Database, _revision_descends_from

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_transport_evidence_identity_requires_a_distinct_nonempty_secret() -> None:
    common = {
        "_env_file": None,
        "database_type": "postgres",
        "database_name": "caresync",
        "database_user": "caresync_basic_app",
        "database_password": "ordinary-runtime-secret",
    }
    assert (
        Settings(**common, transport_evidence_ingest_password="")
        .transport_evidence_ingest_database_url
        is None
    )
    assert (
        Settings(
            **common,
            transport_evidence_ingest_password="ordinary-runtime-secret",
        ).transport_evidence_ingest_database_url
        is None
    )
    isolated = Settings(
        **common,
        transport_evidence_ingest_password="distinct-evidence-secret",
    ).transport_evidence_ingest_database_url
    assert isolated is not None
    assert isolated.username == "caresync_transport_evidence_ingest"
    assert isolated.password == "distinct-evidence-secret"


@pytest.mark.parametrize(
    ("database_read_only", "enable_advanced_routes"),
    [(True, False), (False, True)],
)
def test_transport_evidence_factory_stays_outside_nonbasic_write_modes(
    database_read_only: bool,
    enable_advanced_routes: bool,
) -> None:
    database = Database(
        Settings(
            _env_file=None,
            database_type="postgres",
            database_name="caresync",
            database_user="caresync_basic_app",
            database_password="ordinary-runtime-secret",
            transport_evidence_ingest_password="distinct-evidence-secret",
            database_read_only=database_read_only,
            enable_advanced_routes=enable_advanced_routes,
        )
    )
    try:
        assert database.transport_evidence_engine is None
        assert database.transport_evidence_session_factory is None
    finally:
        database.dispose()


def test_runtime_role_bootstrap_mentions_every_basic_table() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    missing = {name for name in BasicBase.metadata.tables if f"public.{name}" not in sql}
    assert not missing, f"Basic tables missing from runtime-role bootstrap: {sorted(missing)}"


def test_runtime_role_bootstrap_mentions_every_basic_sequence() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    expected = {
        f"{table.name}_{column.name}_seq"
        for table in BasicBase.metadata.sorted_tables
        for column in table.primary_key.columns
        if column.autoincrement is True
    }
    missing = {name for name in expected if name not in sql}
    assert not missing, f"Basic sequences missing from runtime-role bootstrap: {sorted(missing)}"


def test_runtime_role_bootstrap_requires_the_reviewed_local_release() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    assert "alembic upgrade head" not in sql
    assert "exact reviewed revision 0042_billing_policy_recert" in sql


def test_0042_local_release_wiring_is_pinned_but_never_auto_activated() -> None:
    project_root = BACKEND_ROOT.parent
    launcher = (project_root / "scripts" / "start-basic.sh").read_text(
        encoding="utf-8"
    )
    runtime = (project_root / "scripts" / "lib" / "basic-runtime.sh").read_text(
        encoding="utf-8"
    )
    release = (project_root / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    assert (
        'CARESYNC_RETAINED_TARGET_REVISION="0042_billing_policy_recert"'
        in runtime
    )
    assert 'EXPECTED_REVISION="$CARESYNC_RETAINED_TARGET_REVISION"' in launcher
    assert 'alembic upgrade "$CARESYNC_RETAINED_TARGET_REVISION"' in release
    assert "alembic upgrade" not in launcher
    assert "room_safety.release_reconciliation" not in launcher
    assert "release-reconciliation" not in launcher
    assert "SET ROLE" not in launcher.upper()


def test_0041_bootstrap_preflights_catalog_before_role_or_acl_mutation() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text(
        encoding="utf-8"
    )
    start = sql.index("DO $live_room_presence_shape_preflight$")
    end = sql.index("$live_room_presence_shape_preflight$;", start)
    first_role_mutation = sql.index("DO $cluster_role$")
    first_acl_mutation = sql.index("-- Database TEMP is granted")
    preflight = sql[start:end]

    assert end < first_role_mutation < first_acl_mutation
    assert "RETURN;" in preflight  # capability-gated pre-0041 path
    assert "0041_live_room_presence" in preflight
    assert "0042_billing_policy_recert" in preflight
    assert "version_num IN (" in preflight
    assert "65<>(" in preflight
    assert "42<>(" in preflight
    assert "IF 19<>(" in preflight
    assert "0041 room-presence CHECK expressions are not exact" in preflight
    for table in (
        "staff_room_presence_sessions",
        "staff_room_presence_events",
        "room_operational_exception_heads",
        "room_operational_exception_events",
    ):
        assert table in preflight
    assert "relation.relname || '_tenant'" in preflight
    for function in (
        "caresync_0041_presence_row_guard",
        "caresync_0041_event_immutable_guard",
        "caresync_0041_presence_event_guard",
        "caresync_0041_presence_bundle_guard",
        "caresync_0041_exception_head_guard",
        "caresync_0041_exception_event_guard",
        "caresync_0041_exception_bundle_guard",
    ):
        assert function in preflight


def test_0041_runtime_gate_uses_the_installed_trusted_revision_graph() -> None:
    assert _revision_descends_from(
        "0041_live_room_presence",
        "0041_live_room_presence",
    )
    assert _revision_descends_from(
        "0042_billing_policy_recert",
        "0041_live_room_presence",
    )
    assert not _revision_descends_from(
        "0039_admissions_decision_spine",
        "0041_live_room_presence",
    )
    assert not _revision_descends_from(
        "0042_uninstalled_or_untrusted_marker",
        "0041_live_room_presence",
    )


def test_0041_bootstrap_guard_hashes_track_the_migration_bodies() -> None:
    migration = (
        BACKEND_ROOT / "alembic" / "versions" / "0041_live_room_presence.py"
    ).read_text(encoding="utf-8")
    bootstrap = (
        BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
    ).read_text(encoding="utf-8")
    names = set(
        re.findall(
            r"CREATE FUNCTION public\.(caresync_0041_[a-z_]+)\(\)",
            migration,
        )
    )
    assert len(names) == 7
    for name in names:
        body_match = re.search(
            rf"CREATE FUNCTION public\.{name}\(\).*?"
            r"AS \$(\w+)\$(.*?)\$\1\$",
            migration,
            flags=re.DOTALL,
        )
        assert body_match is not None
        body = re.sub(r"/\\*.*?\\*/", " ", body_match.group(2), flags=re.DOTALL)
        body = re.sub(r"--.*?$", " ", body, flags=re.MULTILINE).lower()
        compact = "".join(body.split()).replace('"', "")
        assert hashlib.md5(compact.encode()).hexdigest() in bootstrap


def test_0041_bootstrap_restores_only_exact_runtime_dml_authority() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text(
        encoding="utf-8"
    )
    start = sql.index("DO $live_room_presence_runtime_grants$")
    end = sql.index("$live_room_presence_runtime_grants$;", start)
    grants = sql[start:end]
    assert "GRANT SELECT, INSERT ON TABLE" in grants
    assert "16<>(" in grants
    assert "'DELETE, TRUNCATE, REFERENCES, TRIGGER'" in grants
    assert "'UPDATE'" in grants
    assert "FROM PUBLIC, caresync_basic_app" in grants
    assert "privilege.privilege_type='EXECUTE'" in grants
    assert "pg_catalog.to_regrole('caresync_basic_app')" in grants
    assert "GRANT DELETE" not in grants
    assert "GRANT UPDATE ON TABLE" not in grants


def test_0041_runtime_gate_observes_app_column_acls_from_isolated_probe() -> None:
    session = (BACKEND_ROOT / "app" / "db" / "session.py").read_text(
        encoding="utf-8"
    )
    start = session.index("    def has_live_room_presence_safety_board")
    end = session.index("\n    def ", start + 1)
    gate = session[start:end]

    # information_schema.column_privileges hides grants made to an unrelated
    # role from the deliberately isolated release-probe observer. PostgreSQL's
    # catalog ACL is observer-independent and still permits an exact direct
    # UPDATE-column comparison without granting the probe role membership.
    assert "information_schema.column_privileges" not in gate
    assert "pg_catalog.pg_attribute AS attribute" in gate
    assert "pg_catalog.aclexplode(" in gate
    assert "pg_catalog.acldefault('c',relation.relowner)" in gate
    assert "pg_catalog.to_regrole('caresync_basic_app')" in gate
    assert "privilege.privilege_type='UPDATE'" in gate


def test_0039_admissions_gate_audits_app_grants_independently_of_observer() -> None:
    session = (BACKEND_ROOT / "app" / "db" / "session.py").read_text(
        encoding="utf-8"
    )
    start = session.index("    def has_admissions_decision_spine")
    end = session.index("\n    def ", start + 1)
    gate = session[start:end]

    # The controlled release probe is deliberately not a member of the app
    # role. Every privilege assertion must therefore name the app identity
    # explicitly instead of relying on visibility-filtered information_schema
    # rows or on whichever observer happens to execute the startup audit.
    assert "information_schema.column_privileges" not in gate
    assert "current_user" not in gate
    assert "pg_catalog.has_function_privilege(" in gate
    assert "\"'caresync_basic_app',procedure.oid,'EXECUTE') \"" in gate
    assert "\"'caresync_basic_app',:relation,'SELECT') \"" in gate
    assert "\"'caresync_basic_app',:relation,'INSERT')\"" in gate
    assert "\"'caresync_basic_app',:relation,:privilege)\"" in gate
    assert "\"'caresync_basic_app',attribute.attrelid,\"" in gate
    assert "\"attribute.attnum,'UPDATE')\"" in gate


def test_uv_wrapper_removes_appledouble_migrations_before_alembic_load() -> None:
    metadata = BACKEND_ROOT / "alembic" / "versions" / "._broken_test_migration.py"
    metadata.write_bytes(b"\x00AppleDouble")
    try:
        result = subprocess.run(
            [str(BACKEND_ROOT / "scripts" / "uv.sh"), "run", "alembic", "heads"],
            cwd=BACKEND_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert not metadata.exists()
    finally:
        metadata.unlink(missing_ok=True)


def test_direct_alembic_upgrade_removes_appledouble_revision_sidecar(
    tmp_path,
    monkeypatch,
) -> None:
    metadata = BACKEND_ROOT / "alembic" / "versions" / "._broken_direct_migration.py"
    metadata.write_bytes(b"\x00AppleDouble")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "caresync.db"))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    try:
        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
        assert not metadata.exists()
    finally:
        metadata.unlink(missing_ok=True)


def test_uv_wrapper_defaults_to_rebuild_environment() -> None:
    wrapper = (BACKEND_ROOT / "scripts" / "uv.sh").read_text(encoding="utf-8")
    assert "$HOME/Library/Caches/CareSync-Private-Rebuild/.venv" in wrapper
    assert "$HOME/Library/Caches/CareSync-Private/.venv" not in wrapper


def test_basic_runtime_supervises_configured_push_worker_after_role_bootstrap() -> None:
    project_root = BACKEND_ROOT.parent
    start = (project_root / "scripts" / "start-basic.sh").read_text(encoding="utf-8")
    release = (project_root / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    stop = (project_root / "scripts" / "stop-basic.sh").read_text(encoding="utf-8")

    bootstrap_position = release.index("bootstrap_basic_runtime_role.sql")
    controlled_start_position = release.index(
        '"$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh"',
        bootstrap_position,
    )
    provider_probe_position = start.index("build_push_provider")
    worker_start_position = start.index("scripts/push_worker.py", provider_probe_position)
    assert bootstrap_position < controlled_start_position
    assert provider_probe_position < worker_start_position
    assert "bootstrap_basic_runtime_role.sql" not in start
    assert "alembic upgrade" not in start
    assert 'push_pid_file="$RUNTIME_DIR/pids/push-worker.pid"' in start
    assert '"$RUNTIME_DIR/logs/push-worker.log"' in start
    assert 'basic_assert_managed_service_running \\\n    "push-worker"' in start
    assert "basic_quiesce_application" in stop


def test_basic_runtime_fixes_application_role_and_forwards_optional_password() -> None:
    project_root = BACKEND_ROOT.parent
    start = (project_root / "scripts" / "start-basic.sh").read_text(encoding="utf-8")
    runtime = (project_root / "scripts" / "lib" / "basic-runtime.sh").read_text(
        encoding="utf-8"
    )

    assert 'APP_USER="${CARESYNC_BASIC_APP_USER:-caresync_basic_app}"' in runtime
    assert 'if [[ "$APP_USER" != "caresync_basic_app" ]]; then' in runtime
    assert "CARESYNC_BASIC_APP_USER must be exactly caresync_basic_app" in runtime
    assert 'APP_PASSWORD="${CARESYNC_BASIC_APP_PASSWORD:-}"' in start
    assert start.count('DATABASE_USER="$APP_USER"') == 3
    assert start.count('DATABASE_PASSWORD="$APP_PASSWORD"') == 3


def test_writable_basic_postgres_runtime_identity_fails_closed() -> None:
    Database.validate_basic_runtime_role(
        configured_user="caresync_basic_app",
        current_user="caresync_basic_app",
        session_user="caresync_basic_app",
        is_superuser=False,
        bypasses_rls=False,
        inherits_privileges=False,
        can_create_role=False,
        can_create_database=False,
        can_replicate=False,
        has_role_memberships=False,
        owns_database_objects=False,
        search_path_is_safe=True,
        has_unsafe_role_configuration=False,
        has_dangerous_privileges=False,
        has_missing_required_privileges=False,
    )
    for values in (
        {
            "configured_user": "migration_owner",
            "current_user": "migration_owner",
            "session_user": "migration_owner",
            "is_superuser": False,
            "bypasses_rls": False,
            "inherits_privileges": False,
            "can_create_role": False,
            "can_create_database": False,
            "can_replicate": False,
            "has_role_memberships": False,
            "owns_database_objects": False,
            "search_path_is_safe": True,
            "has_unsafe_role_configuration": False,
            "has_dangerous_privileges": False,
            "has_missing_required_privileges": False,
        },
        {
            "configured_user": "caresync_basic_app",
            "current_user": "caresync_basic_app",
            "session_user": "caresync_basic_app",
            "is_superuser": True,
            "bypasses_rls": False,
            "inherits_privileges": False,
            "can_create_role": False,
            "can_create_database": False,
            "can_replicate": False,
            "has_role_memberships": False,
            "owns_database_objects": False,
            "search_path_is_safe": True,
            "has_unsafe_role_configuration": False,
            "has_dangerous_privileges": False,
            "has_missing_required_privileges": False,
        },
        {
            "configured_user": "caresync_basic_app",
            "current_user": "caresync_basic_app",
            "session_user": "caresync_basic_app",
            "is_superuser": False,
            "bypasses_rls": True,
            "inherits_privileges": False,
            "can_create_role": False,
            "can_create_database": False,
            "can_replicate": False,
            "has_role_memberships": False,
            "owns_database_objects": False,
            "search_path_is_safe": True,
            "has_unsafe_role_configuration": False,
            "has_dangerous_privileges": False,
            "has_missing_required_privileges": False,
        },
        *(
            {
                "configured_user": "caresync_basic_app",
                "current_user": "caresync_basic_app",
                "session_user": "caresync_basic_app",
                "is_superuser": False,
                "bypasses_rls": False,
                "inherits_privileges": attribute == "inherits_privileges",
                "can_create_role": attribute == "can_create_role",
                "can_create_database": attribute == "can_create_database",
                "can_replicate": attribute == "can_replicate",
                "has_role_memberships": False,
                "owns_database_objects": False,
                "search_path_is_safe": True,
                "has_unsafe_role_configuration": False,
                "has_dangerous_privileges": False,
                "has_missing_required_privileges": False,
            }
            for attribute in (
                "inherits_privileges",
                "can_create_role",
                "can_create_database",
                "can_replicate",
            )
        ),
        *(
            {
                "configured_user": "caresync_basic_app",
                "current_user": "caresync_basic_app",
                "session_user": "caresync_basic_app",
                "is_superuser": False,
                "bypasses_rls": False,
                "inherits_privileges": False,
                "can_create_role": False,
                "can_create_database": False,
                "can_replicate": False,
                "has_role_memberships": attribute == "has_role_memberships",
                "owns_database_objects": attribute == "owns_database_objects",
                "search_path_is_safe": attribute != "unsafe_search_path",
                "has_unsafe_role_configuration": attribute == "has_unsafe_role_configuration",
                "has_dangerous_privileges": attribute == "has_dangerous_privileges",
                "has_missing_required_privileges": attribute == "has_missing_required_privileges",
            }
            for attribute in (
                "has_role_memberships",
                "owns_database_objects",
                "unsafe_search_path",
                "has_unsafe_role_configuration",
                "has_dangerous_privileges",
                "has_missing_required_privileges",
            )
        ),
    ):
        with pytest.raises(RuntimeError):
            Database.validate_basic_runtime_role(**values)


def test_runtime_role_bootstrap_removes_memberships_and_refuses_ownership() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    assert "FROM pg_catalog.pg_auth_members" in sql
    assert "REVOKE %I FROM caresync_basic_app" in sql
    assert "REVOKE caresync_basic_app FROM %I" in sql
    assert "FROM pg_catalog.pg_shdepend" in sql
    assert "caresync_basic_app owns database objects" in sql


def test_runtime_role_bootstrap_pins_path_and_repairs_all_privilege_surfaces() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    assert "set_config('search_path', 'pg_catalog', false)" in sql
    assert "ALTER ROLE caresync_basic_app RESET ALL" in sql
    assert "SET search_path = public, pg_catalog" in sql
    assert "REVOKE CREATE, TEMPORARY ON DATABASE" in sql
    assert "ALL TABLES IN SCHEMA %I FROM PUBLIC, caresync_basic_app" in sql
    assert "ALL SEQUENCES IN SCHEMA %I FROM PUBLIC, caresync_basic_app" in sql
    for signature in (
        "caresync_charge_childcare_reconciliation(uuid, uuid, uuid)",
        "caresync_childcare_operation_guard()",
        "caresync_childcare_reconciliation_proof_guard()",
        "caresync_childcare_immutable_ledger_guard()",
        "caresync_childcare_contact_retirement_guard()",
    ):
        assert signature in sql


def test_schema_authority_preflight_cannot_bypass_completeness_as_superuser() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    schema_start = sql.index("DO $schema_authority$")
    schema_end = sql.index("$schema_authority$;", schema_start)
    schema_preflight = sql[schema_start:schema_end]
    first_acl_mutation = sql.index("-- Database TEMP is granted", schema_end)

    # SUPERUSER may bypass object-ownership checks, but it must not exit this
    # block before the additive migration-completeness gates have all run.
    assert "IF NOT executor_super THEN" in schema_preflight
    assert "IF executor_super THEN" not in schema_preflight
    assert "RETURN;" not in schema_preflight
    for gate_message in (
        "complete dormant 0029C",
        "complete 0029D",
        "complete 0030",
    ):
        assert gate_message in schema_preflight
    assert schema_end < first_acl_mutation


def test_dormant_0029c_acl_is_absent_safe_complete_and_zero_authority() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    schema_start = sql.index("DO $schema_authority$")
    schema_end = sql.index("$schema_authority$;", schema_start)
    schema_preflight = sql[schema_start:schema_end]
    first_acl_mutation = sql.index("-- Database TEMP is granted", schema_end)
    assert schema_end < first_acl_mutation

    activation_table = "public.facility_release_checkout_activations"
    guard_signatures = (
        "public.caresync_release_checkout_activation_immutable()",
        "public.caresync_release_snapshot_immutable()",
        "public.caresync_release_checkout_activation_insert_guard()",
        "public.caresync_release_snapshot_insert_guard()",
    )
    # All five NULL at retained 0028 takes the no-C path. Any one present makes
    # the first half true and requires every member in the second half. 0029D's
    # additive completeness gate independently requires the same C table.
    assert schema_preflight.count(activation_table) == 3
    for signature in guard_signatures:
        # Ownership allowlist plus present/missing halves of the completeness gate.
        assert schema_preflight.count(signature) == 3
    assert (
        "schema-grant repair requires the complete dormant 0029C "
        "release-checkout table and guard set"
    ) in schema_preflight
    assert schema_preflight.index("complete dormant 0029C") < schema_preflight.index(
        "IF NOT executor_super THEN"
    )

    revoke_start = sql.index("DO $family_release_checkout_dormant_revoke$")
    revoke_end = sql.index("$family_release_checkout_dormant_revoke$;", revoke_start)
    revoke_block = sql[revoke_start:revoke_end]
    assert f"to_regclass(\n         '{activation_table}'" in revoke_block
    assert f"REVOKE ALL PRIVILEGES ON TABLE\n            {activation_table}" in revoke_block
    for signature in guard_signatures:
        assert (f"REVOKE ALL PRIVILEGES ON FUNCTION\n            {signature}") in revoke_block

    audit_start = sql.index("DO $family_release_checkout_dormant_audit$")
    audit_end = sql.index("$family_release_checkout_dormant_audit$;", audit_start)
    audit_block = sql[audit_start:audit_end]
    assert f"to_regclass(\n         '{activation_table}'" in audit_block
    assert "SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER" in audit_block
    for signature in guard_signatures:
        assert signature in audit_block

    assert not re.search(
        rf"GRANT\b[^;]*\bON\s+TABLE\s+{re.escape(activation_table)}\b",
        sql,
        flags=re.IGNORECASE,
    )
    for signature in guard_signatures:
        assert not re.search(
            rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{re.escape(signature)}(?:\s|;)",
            sql,
            flags=re.IGNORECASE,
        )


def test_0029d_release_checkout_acl_is_absent_safe_complete_and_narrow() -> None:
    sql = (BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql").read_text()
    schema_start = sql.index("DO $schema_authority$")
    schema_end = sql.index("$schema_authority$;", schema_start)
    schema_preflight = sql[schema_start:schema_end]

    activation_signature = "public.caresync_release_checkout_activation_enabled(uuid)"
    replay_signature = "public.caresync_release_checkout_replay(uuid)"
    context_at_signature = (
        "public.caresync_family_release_context_inputs_at(uuid,uuid,timestamp with time zone)"
    )
    insert_signature = (
        "public.caresync_release_checkout_insert_snapshot("
        "uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,"
        "integer,integer,text,text,text,text,timestamp with time zone,"
        "timestamp with time zone,text)"
    )
    interval_trigger_signature = "public.caresync_attendance_interval_verified_release_guard()"
    commit_time_trigger_signature = "public.caresync_release_snapshot_commit_time_guard()"
    callable_signatures = (
        activation_signature,
        replay_signature,
        context_at_signature,
        insert_signature,
    )
    trigger_signatures = (
        interval_trigger_signature,
        commit_time_trigger_signature,
    )
    all_signatures = (*callable_signatures, *trigger_signatures)

    for table in (
        "public.facility_release_checkout_activations",
        "public.attendance_release_snapshots",
        "public.attendance_intervals",
    ):
        assert table in schema_preflight
    for signature in all_signatures:
        assert signature in schema_preflight
    assert "attendance_intervals_verified_release_guard" in schema_preflight
    assert "zy_attendance_release_snapshots_commit_time" in schema_preflight
    assert schema_preflight.count("trigger.tgenabled='O'") == 2
    # FOR EACH ROW + BEFORE + UPDATE + DELETE is pg_trigger.tgtype 27.
    assert "trigger.tgtype=27" in schema_preflight
    # FOR EACH ROW + BEFORE + INSERT is pg_trigger.tgtype 7.
    assert "trigger.tgtype=7" in schema_preflight
    assert (
        "schema-grant repair requires the complete 0029D release-checkout "
        "runtime function and trigger set"
    ) in schema_preflight
    assert schema_preflight.index("complete 0029D") < schema_preflight.index(
        "IF NOT executor_super THEN"
    )

    ownership_start = schema_preflight.index("SELECT procedure.oid::pg_catalog.regprocedure::text")
    ownership_end = schema_preflight.index("IF unauthorized_object IS NOT NULL", ownership_start)
    ownership_preflight = schema_preflight[ownership_start:ownership_end]
    for signature in all_signatures:
        assert signature in ownership_preflight

    grants_start = sql.index("DO $family_release_checkout_runtime_grants$")
    grants_end = sql.index("$family_release_checkout_runtime_grants$;", grants_start)
    grants = sql[grants_start:grants_end]
    normalized_grants = re.sub(r"\s+", " ", grants)
    assert f"to_regprocedure( '{activation_signature}'" in normalized_grants
    for function_name in (
        "caresync_release_checkout_activation_enabled",
        "caresync_release_checkout_replay",
        "caresync_family_release_context_inputs_at",
        "caresync_release_checkout_insert_snapshot",
        "caresync_attendance_interval_verified_release_guard",
        "caresync_release_snapshot_commit_time_guard",
    ):
        assert f"REVOKE ALL PRIVILEGES ON FUNCTION public.{function_name}" in (normalized_grants)
    assert normalized_grants.count("GRANT EXECUTE ON FUNCTION") == 4
    for function_name in (
        "caresync_release_checkout_activation_enabled",
        "caresync_release_checkout_replay",
        "caresync_family_release_context_inputs_at",
        "caresync_release_checkout_insert_snapshot",
    ):
        assert f"GRANT EXECUTE ON FUNCTION public.{function_name}" in normalized_grants
    assert (
        "GRANT EXECUTE ON FUNCTION public.caresync_attendance_interval_verified_release_guard"
    ) not in normalized_grants
    assert (
        "GRANT EXECUTE ON FUNCTION public.caresync_release_snapshot_commit_time_guard"
    ) not in normalized_grants

    audit_start = sql.index("DO $family_release_checkout_runtime_audit$")
    audit_end = sql.index("$family_release_checkout_runtime_audit$;", audit_start)
    audit = sql[audit_start:audit_end]
    for signature in all_signatures:
        assert signature in audit
    assert "pg_catalog.aclexplode" in audit
    assert "privilege.grantee=0" in audit
    assert "public.facility_release_checkout_activations" in audit
    assert "public.attendance_release_snapshots" in audit
    assert "pg_catalog.has_column_privilege" in audit
    assert "INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER" in audit

    assert not re.search(
        r"GRANT\s+[^;]*(?:INSERT|UPDATE|DELETE|TRUNCATE|REFERENCES|TRIGGER)"
        r"[^;]*ON\s+TABLE\s+[^;]*public\.attendance_release_snapshots",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )


def test_runtime_identity_query_uses_qualified_catalogs_and_guard_allowlist() -> None:
    source = (BACKEND_ROOT / "app" / "db" / "session.py").read_text()
    for catalog in (
        "pg_catalog.pg_roles",
        "pg_catalog.pg_auth_members",
        "pg_catalog.pg_shdepend",
        "pg_catalog.pg_db_role_setting",
        "pg_catalog.pg_namespace",
        "pg_catalog.pg_class",
        "pg_catalog.pg_attribute",
    ):
        assert catalog in source
    assert "-c search_path=public,pg_catalog" in source


def test_env_example_uses_runtime_role_not_migration_owner() -> None:
    example = (BACKEND_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DATABASE_USER=caresync_basic_app" in example
    assert "owner only for Alembic" in example


def test_push_worker_checks_runtime_identity_before_processing(monkeypatch) -> None:
    from app.basic import push_worker

    calls: list[str] = []

    class FakeDatabase:
        def __init__(self, _settings) -> None:
            pass

        def assert_basic_runtime_identity(self) -> None:
            calls.append("identity")

        def dispose(self) -> None:
            calls.append("dispose")

    monkeypatch.setattr(push_worker, "Settings", lambda: object())
    monkeypatch.setattr(push_worker, "Database", FakeDatabase)
    monkeypatch.setattr(
        push_worker,
        "run_once",
        lambda _database, _settings, batch_size: (
            calls.append(f"run:{batch_size}") or {"provider_disabled": True}
        ),
    )
    monkeypatch.setattr("sys.argv", ["push_worker.py", "--once", "--batch-size", "7"])
    assert push_worker.main() == 0
    assert calls == ["identity", "run:7", "dispose"]
