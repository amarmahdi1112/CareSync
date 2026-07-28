"""Regression coverage for finalized rollback from an active prepared fence."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_finalized_receipt_converts_matching_prepared_fence_before_reactivation() -> None:
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )
    rollback = release[
        release.index("rollback_release()") : release.index("load_release_run()")
    ]

    branch_start = rollback.index(
        "# A finalized receipt can exist before the prepared fence is retired."
    )
    branch_end = rollback.index(
        'elif [[ "$pre_finalization_rollback" == "true" ]] && \\\n'
        "       { [[ -e \"$RELEASE_FENCE_DIRECTORY\" ]]",
        branch_start,
    )
    finalized_prepared = rollback[branch_start:branch_end]
    reactivation = rollback.index(
        "reactivate_retired_rollback_fence",
        branch_end,
    )

    prepared_match = finalized_prepared.index("require_matching_fence")
    artifacts = finalized_prepared.index("verify_static_artifacts", prepared_match)
    receipt = finalized_prepared.index(
        "basic_release_contract.py verify-finalization-receipt",
        artifacts,
    )
    app_prior = finalized_prepared.index(
        "fence_prior_state app_prior_login",
        receipt,
    )
    ingest_prior = finalized_prepared.index(
        "fence_prior_state ingest_prior_login",
        app_prior,
    )
    quiesce = finalized_prepared.index(
        "basic_quiesce_application",
        ingest_prior,
    )
    ready = finalized_prepared.index(
        '"$PG_BIN/pg_isready"',
        quiesce,
    )
    identity = finalized_prepared.index(
        "basic_verify_retained_identity",
        ready,
    )
    target_revision = finalized_prepared.index(
        "basic_require_exact_revision",
        identity,
    )
    assert (
        '"$CARESYNC_RETAINED_TARGET_REVISION"'
        in finalized_prepared[target_revision:]
    )
    fence_roles = finalized_prepared.index(
        "fence_runtime_roles",
        target_revision,
    )
    no_clients = finalized_prepared.index(
        "basic_assert_no_cluster_clients",
        fence_roles,
    )
    journal = finalized_prepared.index(
        "write_rollback_context",
        no_clients,
    )
    rollback_preparing = finalized_prepared.index(
        "rollback_preparing",
        journal,
    )
    rollback_match = finalized_prepared.index(
        "require_matching_rollback_fence",
        rollback_preparing,
    )

    assert (
        prepared_match
        < artifacts
        < receipt
        < app_prior
        < ingest_prior
        < quiesce
        < ready
        < identity
        < target_revision
        < fence_roles
        < no_clients
        < journal
        < rollback_preparing
        < rollback_match
    )
    assert '--candidate-receipt "$candidate_receipt"' in finalized_prepared
    assert '--commit-receipt "$commit_receipt"' in finalized_prepared
    assert '--receipt "$finalization_receipt"' in finalized_prepared
    assert rollback.index("require_matching_rollback_fence", branch_start) < reactivation
