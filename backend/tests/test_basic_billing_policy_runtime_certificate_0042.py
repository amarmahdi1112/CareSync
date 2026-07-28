"""Pure runtime-certificate proofs for PostgreSQL 17 billing policies."""

import pytest

from app.db import session as database_session

POLICY_KINDS = {
    ("table_select_one", "policy_select_one"): "select",
    ("table_select_two", "policy_select_two"): "select",
    ("table_manage", "policy_manage"): "manage",
    ("table_issue", "policy_issue"): "issue",
    ("table_payments", "policy_payments"): "payments",
    ("table_adjust", "policy_adjust"): "adjust",
    ("table_recover", "policy_recover"): "recover",
    ("table_command", "policy_command"): "command",
    ("table_journal_entry", "policy_journal_entry"): "journal_entry",
    ("table_journal_line", "policy_journal_line"): "journal_line",
}


def _profile(
    hashes_by_kind: dict[str, str],
) -> dict[tuple[str, str], str]:
    return {
        key: hashes_by_kind[kind]
        for key, kind in POLICY_KINDS.items()
    }


def test_original_profile_a_remains_accepted_before_0042() -> None:
    profile_a = _profile(
        database_session._BILLING_0033_POLICY_EXPRESSION_SHA256
    )

    assert (
        database_session._certify_billing_policy_catalog_profile(
            profile_a,
            POLICY_KINDS,
            revision=None,
        )
        == "A"
    )
    assert (
        database_session._certify_billing_policy_catalog_profile(
            profile_a,
            POLICY_KINDS,
            revision="0041_live_room_presence",
        )
        == "A"
    )


def test_dump_profile_b_is_accepted_at_trusted_0042() -> None:
    profile_b = _profile(
        database_session._BILLING_0042_DUMP_POLICY_EXPRESSION_SHA256
    )

    assert (
        database_session._certify_billing_policy_catalog_profile(
            profile_b,
            POLICY_KINDS,
            revision="0042_billing_policy_recert",
        )
        == "B"
    )


@pytest.mark.parametrize(
    "revision",
    [
        None,
        "0033_billing_ledger",
        "0041_live_room_presence",
        "untrusted_future_revision",
    ],
)
def test_dump_profile_b_is_rejected_without_trusted_0042_ancestry(
    revision: str | None,
) -> None:
    profile_b = _profile(
        database_session._BILLING_0042_DUMP_POLICY_EXPRESSION_SHA256
    )

    assert (
        database_session._certify_billing_policy_catalog_profile(
            profile_b,
            POLICY_KINDS,
            revision=revision,
        )
        is None
    )


def test_mixed_and_unknown_policy_catalogs_are_rejected() -> None:
    profile_a = _profile(
        database_session._BILLING_0033_POLICY_EXPRESSION_SHA256
    )
    mixed = dict(profile_a)
    first_key = next(iter(POLICY_KINDS))
    mixed[first_key] = (
        database_session._BILLING_0042_DUMP_POLICY_EXPRESSION_SHA256[
            POLICY_KINDS[first_key]
        ]
    )
    unknown = dict(profile_a)
    unknown[first_key] = "f" * 64

    for observed in (mixed, unknown):
        assert (
            database_session._certify_billing_policy_catalog_profile(
                observed,
                POLICY_KINDS,
                revision="0042_billing_policy_recert",
            )
            is None
        )


def test_incomplete_or_extra_policy_catalogs_are_rejected() -> None:
    profile_a = _profile(
        database_session._BILLING_0033_POLICY_EXPRESSION_SHA256
    )
    incomplete = dict(profile_a)
    incomplete.pop(next(iter(POLICY_KINDS)))
    extra = dict(profile_a)
    extra[("unknown_table", "unknown_policy")] = next(iter(profile_a.values()))

    for observed in (incomplete, extra):
        assert (
            database_session._certify_billing_policy_catalog_profile(
                observed,
                POLICY_KINDS,
                revision="0042_billing_policy_recert",
            )
            is None
        )
