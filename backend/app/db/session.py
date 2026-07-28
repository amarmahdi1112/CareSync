"""Database connection lifecycle and non-destructive health checks."""

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn

from alembic.script import ScriptDirectory
from alembic.script.revision import RangeNotAncestorError, ResolutionError
from fastapi import Request
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.sqlite_functions import register_sqlite_functions

_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SQL_LINE_COMMENT = re.compile(r"--[^\n]*")


@lru_cache(maxsize=32)
def _revision_descends_from(candidate: str, required_ancestor: str) -> bool:
    """Resolve a persisted revision against the installed, trusted migration graph."""

    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    try:
        list(scripts.iterate_revisions(candidate, required_ancestor))
    except (RangeNotAncestorError, ResolutionError):
        return False
    return True


_TRANSPORT_AUDIT_BRIDGE_SHA256 = "09114a9bcefa8eba5e98b23ddf54b4d62cee9c0d3531d46a7b8702aaddb9a0ab"
_NOTIFICATION_ENQUEUE_TRIGGER_SHA256 = (
    "940acca64555507f89b9bb365805193b891d4a5cd53b69e1ace17540c28a890e"
)
# PostgreSQL 17 canonical identities for the frozen 0031/0032 transport
# repository.  Each tuple is ``(normalized prosrc, normalized
# pg_get_functiondef)``.  Metadata and ACLs are attested separately below;
# these hashes make semantic source drift fail closed even when all previous
# marker strings remain present.
_TRANSPORT_CANONICAL_FUNCTION_SHA256 = {
    "caresync_0032_execute_command(text,uuid,text,jsonb)": (
        "37623fef02d09ffa3d447a723b08a91a75305c9c35f9773dfb4d1cd3ca865bfc",
        "7b2d38b6b710b44926e978a7c427970854bbad2b7418d24a1ddff9b7c428f912",
    ),
    "caresync_0032_immutable_fact()": (
        "ded4efc3b93cde31ecfae1f7b973fb7aa6a6015635ebd027056d18eece43d58d",
        "79e4d1861bc8f0b0fe1f68b1887a266695e53bfe9a9d4e4c21b41047bcaa0017",
    ),
    "caresync_0032_receipt_guard()": (
        "e4c9815101da4344caec4747d0a6a2c89705ec0305eda31dbcbe83a0683233b7",
        "54f21d98cd2dba952f7900171a4b0f062f2d0a4cb843ab7ff48ec9250f387959",
    ),
    "caresync_0032_qualification_evidence_guard()": (
        "db6ff856bb6b5d9ecdbbf051ead18596d26c67390f8e4258ebae08553a0a896d",
        "ae496ca388e95048f7253b8d035b390f34716932f0a05bef573db7329dac3ccd",
    ),
    "caresync_0032_qualification_review_guard()": (
        "8487caa806ee087de9fca8c79591a203b713aaeb9aa78653380a952bdd1942d7",
        "e5f73ece9fb01a45aaf90a827bddbf175e6954e1706af7c64d118be63e431600",
    ),
    "caresync_0032_vehicle_review_guard()": (
        "18b11f2c1fd1328156c1893cd7455edd192b759f35b93c1615dab5a447c1d8d8",
        "68d1ebc5f00b001f6cf8e9293758df42783fa952c1605730514850b4e37237f8",
    ),
    "caresync_0032_vehicle_scan_guard()": (
        "eb501eed98a5a1c0970dcfca3de5686d90e96e8196f57f97bedae09e64301445",
        "fa1c5eef6e0a7c7fef3bdb0a175a6d5b589d4df068130d987df395b89b7d6889",
    ),
    "caresync_0031_immutable_fact()": (
        "9926a61f98a7976403f72317579d4a520694e2169ea41a12f0d8cfdb4f694894",
        "8bca3d642ac789c45276db119b5803cc7e89a1e2f60ac6359d5fc4a41fc051fd",
    ),
    "caresync_0031_capability_guard()": (
        "5202b9d1d073ce77ac6598102137045044fa365fbc210460f47ecc6471e4b7da",
        "f5b58ac23c3873b780191ec2c550fefded433b3c18d3a8bec445d1637b467af6",
    ),
    "caresync_0031_qualification_guard()": (
        "51b5d15aa29a0129ca16d9e428dce30c7b7dc4f016ef3c179da1f0dcf6ef360e",
        "010c72ac71c7af8182a0338101a8c09485f5f3732c25a642ef9b2bda47e8d0e4",
    ),
    "caresync_0031_authorization_guard()": (
        "b79b3cc091fcff84017f4f6ef43d0c52a447ea689355767234577c364fdc9ae0",
        "dc1bcbfc51704de36901feb1f3fde7552acc27005bc763b133597712d5a1b745",
    ),
    "caresync_0031_vehicle_guard()": (
        "f7f469f625dfc8da04573ad235d491e6fbbdf1de4d5e5a72246e0d4844c98b17",
        "30c665a45aec129510aa4e94d32aa74e4db3c71524e469896d7bec4349c3b5a5",
    ),
    "caresync_0031_vehicle_version_guard()": (
        "862be173c22c86981bf46deeac2b3a9d3017d120aa1495ada39424e08e02f152",
        "77bd1a7da80965275a3320cbfa8cfac70cf5aa770c5d8ce44a6f7b9570628540",
    ),
    "caresync_0031_vehicle_evidence_guard()": (
        "89b3977be4cc62a5ab1f2e0a8a7935bb583d40e3028956bd08a5f43a439a020d",
        "ec2f6cd75580c62051c989638a81e9dc43e0c07494f5a936f72cba210dabd27e",
    ),
    "caresync_0031_readiness_guard()": (
        "7350e9e05051a4bb0aad827c6a4d99c4c8a8f6c8d11864d75a6f472444ffedc9",
        "4a5c66b4aa4778aa80482ed0eb5b03841ce4dc0683fc56837a303c3ada74731a",
    ),
}
# Frozen 0033 billing guard identities.  Function metadata, ACLs, policy
# command/role shape, and trigger bindings are attested separately.  These
# source and expression hashes make a same-name replacement fail closed.
_BILLING_0033_FUNCTION_SOURCE_SHA256 = {
    "caresync_0033_attested_source_immutable": (
        "1777dd6ca4cc0d59ffd5a3f970d2c92c84b94e81feecc7969d02d419f4568b15"
    ),
    "caresync_0033_actor_guard": (
        "ccd21b254bbdb91e7a36eb8549519315173f5b20fdc95f0633ec8970f77b9821"
    ),
    "caresync_0033_allocation_guard": (
        "3360f590b1665d7f5a877e4b58e658a67d3dfdfe1da7d07e6df6ae26fc2269e3"
    ),
    "caresync_0033_bundle_validate": (
        "53a9a0e54c0b35aed704649c94addf323ee471778d727ce4138d9dd34fe2c355"
    ),
    "caresync_0033_claim_guard": (
        "b401da787d0fb4943ef516f37775179450a0bbb388149b848725e8e6ef9ec696"
    ),
    "caresync_0033_credit_guard": (
        "0efa32212a6ac1440b22a97325687af15ba068aaca7f2db4cae8a86594c06b3b"
    ),
    "caresync_0033_effect_open_guard": (
        "f9486b578fe059bc08aebb9ad76382ea7a23397e7d8502244909596359da258f"
    ),
    "caresync_0033_immutable_fact": (
        "fbe71c6ba05d1c386f0e065e2cdf26554ddcb9e51060dcffa9a1483cc7577964"
    ),
    "caresync_0033_invoice_line_guard": (
        "f2bb413525d7e4ad37e2f8d734a6eba08e9e538cc1dcfed09c13fbd170e50c51"
    ),
    "caresync_0033_journal_sequence_guard": (
        "f15d576045432e20f365ae47d4fc378267b8f24f6d7ea93ec7113c40be076162"
    ),
    "caresync_0033_journal_validate": (
        "759be0b83afa58169e71290aebcc354228859e4c24d5467e7735774b059c907a"
    ),
    "caresync_0033_receipt_guard": (
        "3e147af6005fad0e3a7c3ae3a535fcbf6530e4680aed6768ea19e8335ce29113"
    ),
    "caresync_0033_role_permission_guard": (
        "7ecc36c760874edad2bb52dd4eb86700a5f0a972efe29be5dd8929d30c628198"
    ),
    "caresync_0033_source_attestation_guard": (
        "b6424f3d060a69a8e8d28a40df60bc10b43a6e7851e77082afcd002337b5e5f0"
    ),
    "caresync_0033_terminal_claim": (
        "c7eea153078fd61abfeb3e60b7d3739617087722adcd77d015dc3423e1d8c6e6"
    ),
    "caresync_0033_version_guard": (
        "78a91e7b2fe56b9177cc62c2f7e39bb3d0a4d158283c8d9fa0e5491c232c3899"
    ),
}
_BILLING_0033_POLICY_EXPRESSION_SHA256 = {
    "select": "18d93cb0b39184162b43f4ef5f9c06c919eac6b4ae696dcf3322285021503d28",
    "manage": "375bffb43c9174d5ac955031278f82237fe9ae1c0247e7ae80a7b473efa7f3eb",
    "issue": "34b1d859068b459173db0591c023310aed0de8554cee85d4e0d8164ec6e30b02",
    "payments": "e210fd5cc0fca2fb6021a68c96ed8adf438dc1320e91da21d94c8ba83252be8e",
    "adjust": "99da565eb97a063083a27abd0a6ff9a336563c0278157baf54c8f771dc8480fe",
    "recover": "fcab26ab0ba0b53667633a05c54537570741bf231fce7c1ce1b45d3c0ba07edd",
    "command": "a9e8631e078624fa64950ab0544cd646f93ca77438ed4c01e8a256473cac4f7a",
    "journal_entry": "9fc77aef7678a37fef676eec4debe6314e419413995883a4d6d9635bdc3847f4",
    "journal_line": "b180690f53b4441b8e4034a9ab6f68eec81a6fd28771c01ae519ba8a68305ed8",
}
# PostgreSQL 17's dump/restore path can deparse the same frozen policy
# predicates into this second, audited catalog identity.  Profile B is not a
# general normalization rule: every one of the 36 policy hashes must match it
# as a coherent catalog, and it is trusted only at revision 0042 or a
# descendant from the installed migration graph.
_BILLING_0042_DUMP_POLICY_EXPRESSION_SHA256 = {
    "select": "4b64b7fb76b4cf60e1032497c5bbfbb67ceb49515ee3a1143c1e1f1346a784c2",
    "manage": "47a5b154550491be58ca93c93704d4e6fef24e2125f0c6d52ad9328627db7f9d",
    "issue": "2799b1973ad446874a2fd409fa0a7e351d5b14038582995a1855d0a4247c5aa0",
    "payments": "6f14b8f4290a26ba09048ba9f32cb186ab1a56bcdda451c5ed4be9c87b2f2a1d",
    "adjust": "f4782adcc0d042916aa875a511b23ecbbb497908278b97a3a0d56debeb4c6fc5",
    "recover": "7058ab9771fbf7b72f645c2789954e2934f74a331de1ae8ad6882820e98744b7",
    "command": "c1ef04ccc3ab509588946949e03181506a61e68f075e0dda6fd709ba84e23c89",
    "journal_entry": (
        "70e1f7b4b49fe12829ff79a4ff86d338fb7a55ca855d0728dde1e261e9d5d52a"
    ),
    "journal_line": (
        "cccd1cd9250d5f2002fad0dcc95031e6df515c43857aa7109edd68f0446a02e4"
    ),
}
# Frozen 0041 PL/pgSQL bodies.  PostgreSQL stores the text between the
# dollar-quotes in ``pg_proc.prosrc``; hashing its comment/format-insensitive
# form attests semantics without depending on pg_dump presentation details.
_LIVE_ROOM_PRESENCE_0041_FUNCTION_SOURCE_SHA256 = {
    "caresync_0041_presence_row_guard": (
        "c2885e959f4b68c8ac0cdbd3e1a076a00849cb7aa643d90ff3c4db954379c2ce"
    ),
    "caresync_0041_event_immutable_guard": (
        "8098e7f68006913c76bd843a219740c1bf25557999250cdc4e26a3f179704f1f"
    ),
    "caresync_0041_presence_event_guard": (
        "42bef1d4c942fd2fabc28a7135adea6f8b86ff0f4fb96cab3884535e7d643801"
    ),
    "caresync_0041_presence_bundle_guard": (
        "9faeed03b6de065e01d1a45f4aa24494c436a620ccd239c3ce75341a224e03b5"
    ),
    "caresync_0041_exception_head_guard": (
        "55d851eb69f59b994c52ce0a69f8eb0fd8e23760f7fa8f60fd1fac0c282b8808"
    ),
    "caresync_0041_exception_event_guard": (
        "0fd5688d108bbb8f316c2c1a7b4fc862d7f8857dcde66ce9a0e65e3729da6c49"
    ),
    "caresync_0041_exception_bundle_guard": (
        "bac2311c2624c353a0291b9306e2f5feeba55044efc62fa82d02d6568777cdff"
    ),
}
_LIVE_ROOM_PRESENCE_0041_CHECK_EXPRESSION_SHA256 = {
    (
        "room_operational_exception_events",
        "ck_room_operational_exception_events_acknowledgement",
    ): "3fdfdc9b8865c39295ce64aafa2ef34544e406c6797ba587e979da28c20e481d",
    (
        "room_operational_exception_events",
        "ck_room_operational_exception_events_current_fingerprint",
    ): "de8e89c9302cdec176cccc1c73b63927f75d3b8a62368ad03af1e752843f426c",
    (
        "room_operational_exception_events",
        "ck_room_operational_exception_events_previous_fingerprint",
    ): "af1abe6f54e2a174b719d88d14727fd59f61be29347df71881380323d9404035",
    (
        "room_operational_exception_events",
        "ck_room_operational_exception_events_type",
    ): "a2cc846323aa4af7d81256b12656362b32bee3c038e6c1d4849f59a991be1386",
    (
        "room_operational_exception_heads",
        "ck_room_operational_exceptions_condition",
    ): "94dcdc1dfb8daca4534d493b7dabea1d742b43d0b717c80e437fa9ba81a696ab",
    (
        "room_operational_exception_heads",
        "ck_room_operational_exceptions_fingerprint",
    ): "de8e89c9302cdec176cccc1c73b63927f75d3b8a62368ad03af1e752843f426c",
    (
        "room_operational_exception_heads",
        "ck_room_operational_exceptions_scope",
    ): "afa755b89320862320ace01efa90a439bbb02b97a294b7f688b23478b5f1defb",
    (
        "room_operational_exception_heads",
        "ck_room_operational_exceptions_scope_identity",
    ): "1c90ed03db46b5c50dd8c2509d42608048b63c02a1ce570a187f3a774e4586f7",
    (
        "room_operational_exception_heads",
        "ck_room_operational_exceptions_state",
    ): "53f635f7662d5f89e3b43a6c95df748ceca8df7bdfde14d6dd10ddfb7159a15f",
    (
        "room_operational_exception_heads",
        "ck_room_operational_exceptions_state_bundle",
    ): "53f346ee68e78fd8749adc9641eb414fc08486ec1b396897bfc2a228adf207b7",
    (
        "room_operational_exception_heads",
        "ck_room_operational_exceptions_version",
    ): "36a391c56fb7eec47fe5cf24da89e2db67ec3c6c464c825300fcf70cffe4b087",
    (
        "staff_room_presence_events",
        "ck_room_presence_events_request_sha256",
    ): "3d33d5aaa9ce7ac1ffb6876327a8416a4fb44737ef48310ddf8822023bae349a",
    (
        "staff_room_presence_events",
        "ck_room_presence_events_transition",
    ): "ed87fdd30591bdf7c82a6527c5804ce6439b26b3f7950210eb4cc29a1518c6cf",
    (
        "staff_room_presence_events",
        "ck_room_presence_events_type",
    ): "0f29de547176e120b19a1139c98cc86c53bb5cc9abeaa81cd60d64504164c774",
    (
        "staff_room_presence_sessions",
        "ck_room_presence_sessions_end_reason",
    ): "2a20848f79cea8c4be841b4e5181ac5717d1afb1fb429677ce437f7ec11db439",
    (
        "staff_room_presence_sessions",
        "ck_room_presence_sessions_source",
    ): "e0ef7ede9454dad88699fa1c7760a2308a1b547c541c39038036cb6af49b93a9",
    (
        "staff_room_presence_sessions",
        "ck_room_presence_sessions_terminal_bundle",
    ): "38b16cdfb5f2bb8a0c2baaf0875d7d96d3d58cab98a733a79c0b328b67f387e2",
    (
        "staff_room_presence_sessions",
        "ck_room_presence_sessions_time_order",
    ): "6ccc1267d6bb0a35d9cb8a70dcfc6cc036f7da717fec391a9c589e79b225f004",
    (
        "staff_room_presence_sessions",
        "ck_room_presence_sessions_version",
    ): "d310a5655997196037b972202b664992e4a7d59fadd8404f0bae5bf015f7d911",
}
_PROJECTION_FORBIDDEN_DML = (
    re.compile(r"\binsert\s+into\b"),
    re.compile(r"\bdelete\s+from\b"),
    re.compile(r"\bupdate\s+(?:only\s+)?(?:public\.)?[a-z_][a-z0-9_]*\b"),
    re.compile(r"\bmerge\s+into\b"),
    re.compile(r"\btruncate\b"),
    re.compile(r"\bcopy\b"),
    re.compile(r"\bcall\b"),
    re.compile(r"\bexecute\b"),
    re.compile(r"\bperform\b"),
    re.compile(r"\bcreate\s+(?:temporary\s+|temp\s+)?table\b"),
    re.compile(r"\balter\s+table\b"),
    re.compile(r"\bdrop\s+table\b"),
    re.compile(r"\bfor\s+(?:no\s+key\s+)?update\b"),
    re.compile(r"\b(?:nextval|setval|pg_notify|set_config)\s*\("),
)
_PROJECTION_REQUIRED_RELATIONS = (
    "public.users",
    "public.organization_memberships",
    "public.organizations",
    "public.roles",
    "public.facilities",
    "public.staff_shifts",
    "public.children",
    "public.families",
    "public.enrollments",
    "public.attendance_days",
    "public.attendance_intervals",
    "public.rooms",
    "public.membership_room_assignments",
    "public.child_authority_heads",
    "public.family_authority_people",
    "public.family_authority_person_versions",
    "public.child_release_authorizations",
    "public.child_release_rules",
    "public.family_authority_evidence",
    "public.family_authority_evidence_assessments",
)
_PROJECTION_OPERATIONAL_RELATIONS = (
    "public.users",
    "public.organization_memberships",
    "public.organizations",
    "public.roles",
    "public.facilities",
    "public.staff_shifts",
    "public.children",
    "public.families",
    "public.enrollments",
    "public.attendance_days",
    "public.attendance_intervals",
    "public.rooms",
    "public.membership_room_assignments",
)
_PROJECTION_OPERATIONAL_EXCLUSIVE_RELATIONS = tuple(
    relation
    for relation in _PROJECTION_OPERATIONAL_RELATIONS
    if relation not in {"public.children", "public.families"}
)
_PROJECTION_FORBIDDEN_RELATIONS = (
    "public.family_authority_evidence_objects",
    "public.family_authority_evidence_object_assessments",
    "public.consent_policy_versions",
    "public.child_consent_decisions",
    "public.attendance_release_snapshots",
    "public.childcare_command_receipts",
    "public.audit_events",
    "public.realtime_events",
    "public.notifications",
    "public.user_notifications",
    "public.notification_deliveries",
    "public.notification_push_subscriptions",
    "public.marketplace_credential_notifications",
)
_PROJECTION_FORBIDDEN_FIELDS = (
    "confidential_reason",
    "confidential_note",
    "storage_reference",
    "content_sha256",
    "media_type",
    "byte_size",
    "grantor_person_id",
    "grantor_person_version_id",
    "grantor_authority_basis",
    "source_guardian_id",
    "source_emergency_contact_id",
    "primary_phone",
    "email",
    "street_address",
    "home_phone",
    "work_phone",
    "cell_phone",
)
_PROJECTION_MINIMUM_OUTPUT_KEYS = (
    "input_schema_version",
    "organization_id",
    "family_id",
    "facility_id",
    "room_id",
    "child_id",
    "attendance_day_id",
    "attendance_interval_id",
    "staff_shift_id",
    "evaluated_at",
    "authority_revision",
    "people",
    "authorizations",
    "rules",
    "person_id",
    "person_version_id",
    "relationship_kind",
    "authorization_id",
    "authorization_version",
    "recipient_person_id",
    "verification_policy_code",
    "rule_id",
    "rule_version",
    "rule_kind",
    "scope_kind",
    "safe_explanation_code",
    "supporting_evidence",
)


def _sql_without_comments(definition: str) -> str:
    without_blocks = _SQL_BLOCK_COMMENT.sub(" ", definition)
    return _SQL_LINE_COMMENT.sub(" ", without_blocks).lower()


def _compact_sql(definition: str) -> str:
    return "".join(_sql_without_comments(definition).split()).replace('"', "")


def _canonical_sql_sha256(definition: str) -> str:
    """Hash the frozen PostgreSQL 17 catalog form after harmless formatting removal."""

    return hashlib.sha256(_compact_sql(definition).encode("utf-8")).hexdigest()


def _certify_billing_policy_catalog_profile(
    observed_hashes: Mapping[tuple[str, str], str],
    policy_kinds: Mapping[tuple[str, str], str],
    *,
    revision: str | None,
) -> str | None:
    """Recognize only a coherent frozen billing-policy catalog.

    Profile A is the original 0033 identity.  Profile B is the one reviewed
    PostgreSQL 17 dump/deparse identity and is accepted only after the trusted
    0042 recertification proves that the canonical source profile was installed.
    Mapping equality deliberately rejects missing, extra, mixed, or unknown
    policy expressions.
    """

    profile_a = {
        key: _BILLING_0033_POLICY_EXPRESSION_SHA256[kind]
        for key, kind in policy_kinds.items()
    }
    if dict(observed_hashes) == profile_a:
        return "A"

    profile_b = {
        key: _BILLING_0042_DUMP_POLICY_EXPRESSION_SHA256[kind]
        for key, kind in policy_kinds.items()
    }
    if (
        dict(observed_hashes) == profile_b
        and revision is not None
        and _revision_descends_from(revision, "0042_billing_policy_recert")
    ):
        return "B"
    return None


def _normalized_0041_catalog_expression(definition: str) -> str:
    """Normalize only catalog-added qualification, grouping and text casts."""

    normalized = _compact_sql(definition).replace("pg_catalog.", "")
    normalized = normalized.replace("public.", "")
    normalized = re.sub(
        r"::(?:text|uuid|character(?:varying)?|varchar)",
        "",
        normalized,
    )
    normalized = normalized.replace("(", "").replace(")", "")
    return normalized.replace(
        "fromorganization_membershipsasmembership",
        "fromorganization_membershipsmembership",
    )


def _live_room_presence_tenant_policy_is_exact(definition: str) -> bool:
    """Recognize the frozen active-membership tenant predicate from 0041."""

    normalized = _normalized_0041_catalog_expression(definition)
    return normalized == (
        "organization_id=nullifcurrent_setting"
        "'app.current_organization_id',true,''andexistsselect1from"
        "organization_membershipsmembershipwhere"
        "membership.organization_id=nullifcurrent_setting"
        "'app.current_organization_id',true,''and"
        "membership.user_id=nullifcurrent_setting"
        "'app.current_user_id',true,''andmembership.status='active'"
    )


def _normalized_transport_policy(definition: str) -> str:
    """Return the canonical catalog form used by the 0032 policy attestations."""

    normalized = re.sub(
        r"::(?:pg_catalog\.)?name(?:\[\])?",
        "",
        _compact_sql(definition),
    )
    return normalized.replace("(", "").replace(")", "")


def _transport_writer_policy_is_exact(definition: str) -> bool:
    """Recognize only the terminal 0032 SECURITY DEFINER identity predicate."""

    return _normalized_transport_policy(definition) == (
        "current_user='caresync_transport_command_owner'and"
        "session_user=anyarray['caresync_basic_app',"
        "'caresync_transport_evidence_ingest']"
    )


def _transport_context_lock_policy_is_exact(
    *,
    table: str,
    policy_name: str,
    permissive: bool,
    using_expression: str,
    check_expression: str,
) -> bool:
    """Recognize only the four fail-closed 0032 context row-lock policies."""

    scopes = {
        "users": ("id=nullifcurrent_setting'app.current_user_id'::text,true,''::text::uuid"),
        "organizations": (
            "id=nullifcurrent_setting'app.current_organization_id'::text,true,''::text::uuid"
        ),
        "organization_memberships": (
            "organization_id=nullifcurrent_setting"
            "'app.current_organization_id'::text,true,''::text::uuid"
        ),
        "roles": (
            "organization_id=nullifcurrent_setting"
            "'app.current_organization_id'::text,true,''::text::uuid"
        ),
    }
    scope = scopes.get(table)
    if scope is None:
        return False
    owner = "caresync_transport_command_owner"
    writer = (
        f"current_user='{owner}'and"
        "session_user=anyarray['caresync_basic_app',"
        "'caresync_transport_evidence_ingest']"
    )
    normalized_using = _normalized_transport_policy(using_expression)
    normalized_check = _normalized_transport_policy(check_expression)
    if policy_name == f"{table}_0032_lock":
        return (
            permissive and normalized_using == f"{writer}and{scope}" and normalized_check == "false"
        )
    if policy_name == f"{table}_0032_lock_no_mutation":
        return (
            not permissive
            and normalized_using == f"current_user<>'{owner}'or{writer}and{scope}"
            and normalized_check == f"current_user<>'{owner}'"
        )
    return False


def _notification_context_insert_policy_is_exact(definition: str) -> bool:
    """Recognize only the user-or-organization context INSERT predicate."""

    normalized = _compact_sql(definition).replace("pg_catalog.", "")
    normalized = re.sub(r"::(?:text|uuid)", "", normalized)
    normalized = normalized.replace("(", "").replace(")", "")
    return normalized == (
        "user_id=nullifcurrent_setting'app.current_user_id',true,''or"
        "organization_id=nullifcurrent_setting'app.current_organization_id',true,''"
    )


def _transport_audit_realtime_bridge_is_hardened(definition: str) -> bool:
    compact = _compact_sql(definition)
    exact_transport_branch = (
        "ifnew.entity_type='transport_registry_command'then"
        "insertintopublic.realtime_events("
        "id,organization_id,event_type,entity_type,entity_id,occurred_at,payload)"
        "values(new.id,new.organization_id,'transport_registry.changed',"
        "'transport_registry',null,new.occurred_at,"
        "pg_catalog.jsonb_build_object("
        "'source','audit_event','refresh_required',true));returnnew;endif;"
    )
    return bool(
        hashlib.sha256(compact.encode()).hexdigest() == _TRANSPORT_AUDIT_BRIDGE_SHA256
        and exact_transport_branch in compact
        and "new.details" not in compact
        and _sql_string_literals(definition)
        == {
            "audit_event",
            "child.consent.%",
            "child.release.%",
            "facility_id",
            "family.authority.%",
            "organization.consent.%",
            "refresh_required",
            "source",
            "transport_registry",
            "transport_registry.changed",
            "transport_registry_command",
        }
    )


def _notification_enqueue_trigger_is_hardened(definition: str) -> bool:
    compact = _compact_sql(definition)
    realtime_insert = (
        "insertintopublic.user_realtime_events("
        "id,user_id,organization_id,event_type,entity_type,entity_id,occurred_at,payload)"
        "values(new.id,new.user_id,new.organization_id,'notification.created',"
        "'notification',new.id,new.created_at,pg_catalog.jsonb_build_object("
        "'source','notification_ledger'))onconflict(id)donothing;"
    )
    return bool(
        hashlib.sha256(compact.encode()).hexdigest() == _NOTIFICATION_ENQUEUE_TRIGGER_SHA256
        and realtime_insert in compact
        and compact.count("pg_catalog.set_config(") == 3
        and "insertintopublic.notification_deliveries(" in compact
        and "frompublic.notification_push_subscriptionsassubscription" in compact
        and "leftjoinpublic.user_notification_preferencesaspreference" in compact
        and "onconflict(notification_id,subscription_id)donothing;" in compact
        and "exceptionwhenothersthen" in compact
        and "raise;" in compact
        and _sql_string_literals(definition)
        == {
            "",
            "notification context unavailable",
            "active",
            "app.current_organization_id",
            "app.current_user_id",
            "assignment",
            "category",
            "credential",
            "hiring",
            "notification",
            "notification.created",
            "notification_id",
            "notification_ledger",
            "operations",
            "pending",
            "severity",
            "source",
            "suppressed",
            "type",
        }
    )


def _sql_string_literals(definition: str) -> set[str]:
    return {
        match.group(1).replace("''", "'").lower()
        for match in re.finditer(r"'((?:''|[^'])*)'", definition)
    }


def _named_check_expression(definition: str, constraint_name: str) -> str | None:
    """Return one compact named CHECK body without truncating nested clauses."""

    compact = _compact_sql(definition)
    marker = f"constraint{constraint_name.lower()}check("
    start = compact.find(marker)
    if start < 0:
        return None
    index = start + len(marker)
    body_start = index
    depth = 1
    in_literal = False
    while index < len(compact):
        character = compact[index]
        if character == "'":
            if in_literal and index + 1 < len(compact) and compact[index + 1] == "'":
                index += 2
                continue
            in_literal = not in_literal
        elif not in_literal:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    return compact[body_start:index]
        index += 1
    return None


def _sqlite_column_manifest(connection: Any, table_name: str) -> dict[str, tuple[str, bool, int]]:
    """Return SQLite type, NOT NULL and primary-key position for every column."""

    return {
        str(row[1]): (str(row[2]).upper(), bool(row[3]), int(row[5]))
        for row in connection.exec_driver_sql(f"PRAGMA table_info('{table_name}')")
    }


def _sqlite_foreign_key_manifest(
    connection: Any,
    table_name: str,
) -> set[tuple[str, tuple[str, ...], tuple[str, ...], str, str, str]]:
    """Return composite SQLite foreign keys independent of generated row ids."""

    grouped: dict[int, list[Any]] = {}
    for row in connection.exec_driver_sql(f"PRAGMA foreign_key_list('{table_name}')"):
        grouped.setdefault(int(row[0]), []).append(row)
    return {
        (
            str(rows[0][2]),
            tuple(str(row[3]) for row in sorted(rows, key=lambda item: int(item[1]))),
            tuple(str(row[4]) for row in sorted(rows, key=lambda item: int(item[1]))),
            str(rows[0][5]).upper(),
            str(rows[0][6]).upper(),
            str(rows[0][7]).upper(),
        )
        for rows in grouped.values()
    }


def _sqlite_unique_manifest(connection: Any, table_name: str) -> set[tuple[str, ...]]:
    """Return column tuples for named UNIQUE constraints on a SQLite table."""

    result: set[tuple[str, ...]] = set()
    for row in connection.exec_driver_sql(f"PRAGMA index_list('{table_name}')"):
        if not bool(row[2]) or str(row[3]).lower() != "u":
            continue
        columns = tuple(
            str(item[2])
            for item in sorted(
                connection.exec_driver_sql(f"PRAGMA index_info('{str(row[1])}')"),
                key=lambda item: int(item[0]),
            )
        )
        result.add(columns)
    return result


_SQLITE_RELEASE_SNAPSHOT_CHECKS = {
    "ck_release_snapshots_attendance_day_version": _compact_sql("attendance_day_version >= 1"),
    "ck_release_snapshots_scope_basis": _compact_sql(
        "scope_basis IN ('organization_role','room_assignment') AND "
        "((scope_basis = 'organization_role' AND room_assignment_id IS NULL) OR "
        "(scope_basis = 'room_assignment' AND room_assignment_id IS NOT NULL))"
    ),
    "ck_release_snapshots_executable_verification_policy": _compact_sql(
        "(verification_policy_code = 'government_photo_id' "
        "AND verification_method = 'government_photo_id' "
        "AND verification_result = 'verified') OR "
        "(verification_policy_code = 'documented_familiarity' "
        "AND verification_method = 'documented_familiarity' "
        "AND verification_result = 'documented_familiarity') OR "
        "(verification_policy_code = "
        "'government_photo_id_or_documented_familiarity' AND "
        "((verification_method = 'government_photo_id' "
        "AND verification_result = 'verified') OR "
        "(verification_method = 'documented_familiarity' "
        "AND verification_result = 'documented_familiarity')))"
    ),
    "ck_release_snapshots_checkout_time_order": _compact_sql(
        "checked_out_at >= requested_at AND committed_at = checked_out_at"
    ),
    "ck_release_snapshots_decision_policy_version": _compact_sql(
        "decision_policy_version = 'release-context-v1'"
    ),
}
_SQLITE_RELEASE_ACTIVATION_CHECKS = {
    "ck_release_checkout_activations_privileged_role": _compact_sql(
        "activated_by_role_key IN ('owner','administrator')"
    ),
    "ck_release_checkout_activations_policy_version": _compact_sql(
        "activation_policy_version = 'normal_verified_release_v1'"
    ),
}
_SQLITE_RELEASE_RECEIPT_TARGET_CHECK = _compact_sql(
    "target_type IN ('family','child','enrollment','authority_person',"
    "'authority_evidence','authority_evidence_object','release_authorization',"
    "'release_rule','consent','release_activation','attendance_release')"
)


def _relation_aliases(normalized: str, relation: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(
            rf"(?:from|join)\s+public\.{re.escape(relation)}"
            r"(?:\s+as)?\s+([a-z_][a-z0-9_]*)",
            normalized,
        )
    }


def _one_alias_has_all(compact: str, aliases: set[str], suffixes: tuple[str, ...]) -> bool:
    return any(all(f"{alias}.{suffix}" in compact for suffix in suffixes) for alias in aliases)


def _common_operational_segment(normalized: str) -> str | None:
    """Return the single-statement operational CTE, never a composed substitute."""

    start_marker = "with actor_scope as ("
    end_marker = "from shift_summary cross join attendance_summary;"
    if normalized.count(start_marker) != 1 or normalized.count(end_marker) != 1:
        return None
    start = normalized.index(start_marker)
    end = normalized.index(end_marker, start) + len(end_marker)
    segment = normalized[start:end]
    if segment.count(";") != 1 or not segment.endswith(";"):
        return None
    return segment


def _release_context_projection_definition_is_hardened(definition: str) -> bool:
    """Best-effort fail-closed proof of the fixed read-only projection body."""

    normalized = " ".join(_sql_without_comments(definition).split()).replace('"', "")
    compact = "".join(normalized.split())
    operational = _common_operational_segment(normalized)
    if operational is None:
        return False
    operational_compact = "".join(operational.split())
    required_identity_and_scope = (
        "current_setting('app.current_organization_id',true)",
        "current_setting('app.current_user_id',true)",
        "requested_child_id",
        "requested_facility_id",
        "'release:read'",
        "'owner'",
        "'administrator'",
        "membership_id",
        "role_id",
        "permissions",
        "clocked_out_at",
        "placement_effective_date",
        "checked_out_at",
        "forshare",
    )
    exact_evaluation_clock = (
        compact.count("pg_catalog.statement_timestamp()")
        + compact.count("evaluated_at_valuetimestamptz:=requested_evaluated_at;")
        == 1
        and "clock_timestamp()" not in compact
    )
    required_state_patterns = (
        re.compile(r"\.status\s*=\s*'active'"),
        re.compile(r"\.is_active\s*=\s*true"),
        re.compile(r"\.status\s*=\s*'open'"),
        re.compile(r"\.clocked_out_at\s+is\s+null"),
        re.compile(r"\.status\s*=\s*'present'"),
        re.compile(r"\.checked_out_at\s+is\s+null"),
        re.compile(r"\.placement_effective_date\s+is\s+not\s+null"),
    )
    aliases = {
        relation: _relation_aliases(normalized, relation.removeprefix("public."))
        for relation in _PROJECTION_REQUIRED_RELATIONS
    }
    operational_aliases = {
        relation: _relation_aliases(
            operational,
            relation.removeprefix("public."),
        )
        for relation in _PROJECTION_OPERATIONAL_RELATIONS
    }
    exact_scope_gates = (
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.users"],
            ("id=actor_user_id", "is_active=true"),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.organization_memberships"],
            (
                "organization_id=actor_organization_id",
                "status='active'",
                "user_id=",
                "role_id",
            ),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.organizations"],
            ("id=", "status='active'"),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.roles"],
            ("organization_id=", "id=", "key", "permissions"),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.facilities"],
            (
                "organization_id=actor_organization_id",
                "id=requested_facility_id",
                "status='active'",
            ),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.staff_shifts"],
            (
                "organization_id=actor_organization_id",
                "membership_id=",
                "facility_id=requested_facility_id",
                "facility_id<>requested_facility_id",
                "status='open'",
                "clocked_out_atisnull",
            ),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.children"],
            (
                "organization_id=actor_organization_id",
                "id=requested_child_id",
                "is_active=true",
            ),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.families"],
            ("organization_id=", "id=", "status='active'"),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.enrollments"],
            (
                "organization_id=",
                "child_id=",
                "facility_id=requested_facility_id",
                "status='active'",
                "room_idisnotnull",
                "placement_effective_dateisnotnull",
                "start_date<=",
                "end_dateisnull",
            ),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.attendance_days"],
            (
                "organization_id=actor_organization_id",
                "facility_id=requested_facility_id",
                "child_id=requested_child_id",
                "enrollment_id=",
                "room_id=",
                "status='present'",
            ),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.attendance_intervals"],
            ("organization_id=", "attendance_day_id=", "checked_out_atisnull"),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.rooms"],
            ("organization_id=", "facility_id=", "id=", "is_active=true"),
        ),
        _one_alias_has_all(
            operational_compact,
            operational_aliases["public.membership_room_assignments"],
            (
                "organization_id=actor_organization_id",
                "membership_id=",
                "facility_id=requested_facility_id",
                "room_id=",
                "is_active=true",
            ),
        ),
    )
    if any(pattern.search(normalized) for pattern in _PROJECTION_FORBIDDEN_DML):
        return False
    if any(relation in compact for relation in _PROJECTION_FORBIDDEN_RELATIONS):
        return False
    if any(field in compact for field in _PROJECTION_FORBIDDEN_FIELDS):
        return False
    operational_markers = (
        "withactor_scopeas(",
        "active_facilityas(",
        "facility_scopeas(",
        "active_enrollmentsas(",
        "shift_summaryas(",
        "open_attendanceas(",
        "attendance_summaryas(",
        "actor_organization_id",
        "actor_user_id",
        "'release:read'",
        "pg_catalog.pg_timezone_names",
        "attimezone",
        "service_date",
        "exact_count",
        "other_count",
        "'owner'",
        "'administrator'",
        "fromshift_summarycrossjoinattendance_summary;",
    )
    return bool(
        "returnsjsonb" in compact
        and "securitydefiner" in compact
        and all(relation in compact for relation in _PROJECTION_REQUIRED_RELATIONS)
        and all(aliases.values())
        and all(relation in operational_compact for relation in _PROJECTION_OPERATIONAL_RELATIONS)
        and all(operational_aliases.values())
        and all(marker in operational_compact for marker in operational_markers)
        and all(
            compact.count(relation) == operational_compact.count(relation)
            for relation in _PROJECTION_OPERATIONAL_EXCLUSIVE_RELATIONS
        )
        and all(marker in compact for marker in required_identity_and_scope)
        and exact_evaluation_clock
        and all(pattern.search(normalized) for pattern in required_state_patterns)
        and all(exact_scope_gates)
        and operational_compact.count(".status='active'") >= 4
        and operational_compact.count(".is_active=true") >= 3
        and "in('owner','administrator')orexists" in operational_compact
        and "open_shift_facility_mismatch" in compact
        and "open_shift_required" in compact
        and "child_not_on_site" in compact
        and "active_enrollment_count<>1" in compact
        and "open_attendance_count<>1" in compact
        and any(f"forshareof{alias}" in compact for alias in aliases["public.families"])
        and all(f"'{key}'" in compact for key in _PROJECTION_MINIMUM_OUTPUT_KEYS)
        and "'release-context-input-v1'" in compact
    )


def _release_context_invalidation_definitions_are_hardened(
    function_definition: str,
    trigger_definition: str,
) -> bool:
    """Require one generic, payload-exact authority-head invalidation path."""

    normalized_function = " ".join(_sql_without_comments(function_definition).split()).replace(
        '"', ""
    )
    function = "".join(normalized_function.split())
    trigger = _compact_sql(trigger_definition)
    function_markers = (
        "returnstrigger",
        "securitydefiner",
        "iftg_op='update'andold.revisionisnotdistinctfromnew.revisionthen",
        "insertintopublic.realtime_events",
        "(id,organization_id,event_type,entity_type,entity_id,occurred_at,payload)",
        "pg_catalog.gen_random_uuid()",
        "new.organization_id",
        "'family_authority.release_context_invalidated'",
        "'child_authority_head',null,pg_catalog.statement_timestamp()",
        "pg_catalog.jsonb_build_object('source','authority_head','scope','release_context')",
        "returnnew",
    )
    trigger_prefix = (
        "createtriggerchild_authority_heads_release_context_invalidated"
        "afterinsertorupdateofrevisiononpublic.child_authority_heads"
        "foreachrowexecute"
    )
    trigger_suffixes = (
        "functionpublic.caresync_release_context_from_authority_head()",
        "functioncaresync_release_context_from_authority_head()",
        "procedurepublic.caresync_release_context_from_authority_head()",
        "procedurecaresync_release_context_from_authority_head()",
    )
    return bool(
        all(marker in function for marker in function_markers)
        and function.count("insertintopublic.realtime_events") == 1
        and function.count("pg_catalog.jsonb_build_object(") == 1
        and (
            "pg_catalog.jsonb_build_object('source','authority_head','scope',"
            "'release_context'));returnnew;end"
        )
        in function
        and "new.child_id" not in function
        and "new.family_id" not in function
        and "updatepublic." not in function
        and "deletefrom" not in function
        and "execute" not in function
        and trigger.startswith(trigger_prefix)
        and trigger.endswith(trigger_suffixes)
        and "when(" not in trigger
    )


def _release_checkout_activation_immutability_is_hardened(
    function_definition: str,
    trigger_definition: str,
) -> bool:
    """Prove the fixed UPDATE/DELETE activation guard, not merely its name."""

    function = _compact_sql(function_definition)
    trigger = _compact_sql(trigger_definition)
    function_markers = (
        "returns trigger".replace(" ", ""),
        "language plpgsql".replace(" ", ""),
        "security definer".replace(" ", ""),
        "raise exception 'release checkout activation is immutable'".replace(" ", ""),
        "errcode='23514'",
        "constraint='ck_release_checkout_activation_immutable'",
    )
    trigger_prefix = (
        "createtriggerfacility_release_checkout_activations_immutable"
        "beforedeleteorupdateonpublic.facility_release_checkout_activations"
        "foreachrowexecute"
    )
    trigger_suffixes = (
        "functionpublic.caresync_release_checkout_activation_immutable()",
        "functioncaresync_release_checkout_activation_immutable()",
        "procedurepublic.caresync_release_checkout_activation_immutable()",
        "procedurecaresync_release_checkout_activation_immutable()",
    )
    return bool(
        all(marker in function for marker in function_markers)
        and function.count("raiseexception") == 1
        and not any(pattern.search(function) for pattern in _PROJECTION_FORBIDDEN_DML)
        and trigger.startswith(trigger_prefix)
        and trigger.endswith(trigger_suffixes)
        and "when(" not in trigger
    )


def _release_checkout_snapshot_immutability_is_hardened(
    function_definition: str,
    trigger_definition: str,
) -> bool:
    """Prove the fixed UPDATE/DELETE release-snapshot guard, not merely its name."""

    function = _compact_sql(function_definition)
    trigger = _compact_sql(trigger_definition)
    function_markers = (
        "returns trigger".replace(" ", ""),
        "language plpgsql".replace(" ", ""),
        "security definer".replace(" ", ""),
        "raise exception 'attendance release snapshot is immutable'".replace(" ", ""),
        "errcode='23514'",
        "constraint='ck_release_snapshot_immutable'",
    )
    trigger_prefix = (
        "createtriggerattendance_release_snapshots_immutable"
        "beforedeleteorupdateonpublic.attendance_release_snapshots"
        "foreachrowexecute"
    )
    trigger_suffixes = (
        "functionpublic.caresync_release_snapshot_immutable()",
        "functioncaresync_release_snapshot_immutable()",
        "procedurepublic.caresync_release_snapshot_immutable()",
        "procedurecaresync_release_snapshot_immutable()",
    )
    return bool(
        all(marker in function for marker in function_markers)
        and function.count("raiseexception") == 1
        and not any(pattern.search(function) for pattern in _PROJECTION_FORBIDDEN_DML)
        and trigger.startswith(trigger_prefix)
        and trigger.endswith(trigger_suffixes)
        and "when(" not in trigger
    )


def _release_checkout_activation_insert_guard_is_hardened(
    function_definition: str,
    trigger_definition: str,
) -> bool:
    """Prove every duplicated activation identity is joined before insertion."""

    function = _compact_sql(function_definition)
    trigger = _compact_sql(trigger_definition)
    required_fragments = (
        "returnstrigger",
        "languageplpgsql",
        "securitydefiner",
        "ifnotexists(select1frompublic.organization_membershipsasmembership",
        "joinpublic.rolesasactor_roleonactor_role.organization_id="
        "membership.organization_idandactor_role.id=membership.role_id",
        "joinpublic.childcare_command_receiptsasreceiptonreceipt.organization_id="
        "new.organization_idandreceipt.client_operation_id=new.activation_operation_id",
        "membership.organization_id=new.organization_id",
        "membership.id=new.activated_by_membership_id",
        "membership.user_id=new.activated_by_user_id",
        "membership.role_id=new.activated_by_role_id",
        "membership.status='active'",
        "actor_role.organization_id=new.organization_id",
        "actor_role.id=new.activated_by_role_id",
        "actor_role.key=new.activated_by_role_key",
        "receipt.command_type='facility.release_checkout.activate'",
        "receipt.target_type='release_activation'",
        "receipt.target_id=new.id",
        "receipt.actor_user_id=new.activated_by_user_id",
        "receipt.facility_id=new.facility_id",
        "receipt.committed_version=1",
        "raiseexception'releasecheckoutactivationrelationalconsistencyfailed'",
        "errcode='23514'",
        "constraint='ck_release_checkout_activation_relational_consistency'",
        "returnnew",
    )
    trigger_prefix = (
        "createtriggerfacility_release_checkout_activations_insert_guard"
        "beforeinsertonpublic.facility_release_checkout_activations"
        "foreachrowexecute"
    )
    trigger_suffixes = (
        "functionpublic.caresync_release_checkout_activation_insert_guard()",
        "functioncaresync_release_checkout_activation_insert_guard()",
        "procedurepublic.caresync_release_checkout_activation_insert_guard()",
        "procedurecaresync_release_checkout_activation_insert_guard()",
    )
    return bool(
        all(fragment in function for fragment in required_fragments)
        and function.count("raiseexception") == 1
        and function.count("ifnotexists(") == 1
        and not any(pattern.search(function) for pattern in _PROJECTION_FORBIDDEN_DML)
        and trigger.startswith(trigger_prefix)
        and trigger.endswith(trigger_suffixes)
        and "when(" not in trigger
    )


def _release_checkout_snapshot_insert_guard_is_hardened(
    function_definition: str,
    trigger_definition: str,
) -> bool:
    """Prove every duplicated release fact is joined before insertion."""

    function = _compact_sql(function_definition)
    trigger = _compact_sql(trigger_definition)
    required_fragments = (
        "returnstrigger",
        "languageplpgsql",
        "securitydefiner",
        "ifnotexists(select1frompublic.organization_membershipsasmembership",
        "joinpublic.rolesasactor_roleonactor_role.organization_id="
        "membership.organization_idandactor_role.id=membership.role_id",
        "joinpublic.staff_shiftsasstaff_shiftonstaff_shift.organization_id="
        "new.organization_idandstaff_shift.id=new.staff_shift_id",
        "joinpublic.childcare_command_receiptsasreceiptonreceipt.organization_id="
        "new.organization_idandreceipt.client_operation_id=new.client_operation_id",
        "joinpublic.attendance_eventsascheckout_eventoncheckout_event.organization_id="
        "new.organization_idandcheckout_event.id=new.checkout_event_id",
        "membership.organization_id=new.organization_id",
        "membership.id=new.actor_membership_id",
        "membership.user_id=new.actor_user_id",
        "membership.role_id=new.actor_role_id",
        "membership.status='active'",
        "actor_role.organization_id=new.organization_id",
        "actor_role.id=new.actor_role_id",
        "actor_role.key=new.actor_role_key",
        "staff_shift.membership_id=new.actor_membership_id",
        "staff_shift.facility_id=new.facility_id",
        "receipt.command_type='attendance.release.checkout'",
        "receipt.target_type='attendance_release'",
        "receipt.target_id=new.id",
        "receipt.actor_user_id=new.actor_user_id",
        "receipt.facility_id=new.facility_id",
        "receipt.request_hash=new.request_hash",
        "receipt.committed_at=new.committed_at",
        "receipt.committed_version=1",
        "checkout_event.attendance_day_id=new.attendance_day_id",
        "checkout_event.client_operation_id=new.client_operation_id",
        "checkout_event.actor_user_id=new.actor_user_id",
        "checkout_event.occurred_at=new.checked_out_at",
        "checkout_event.event_type='check_out'",
        "new.room_assignment_idisnullorexists(select1frompublic."
        "membership_room_assignmentsasroom_assignment",
        "room_assignment.organization_id=new.organization_id",
        "room_assignment.id=new.room_assignment_id",
        "room_assignment.membership_id=new.actor_membership_id",
        "room_assignment.facility_id=new.facility_id",
        "room_assignment.room_id=new.room_id",
        "raiseexception'attendancereleasesnapshotrelationalconsistencyfailed'",
        "errcode='23514'",
        "constraint='ck_release_snapshot_relational_consistency'",
        "returnnew",
    )
    trigger_prefix = (
        "createtriggerzz_attendance_release_snapshots_insert_guard"
        "beforeinsertonpublic.attendance_release_snapshotsforeachrowexecute"
    )
    trigger_suffixes = (
        "functionpublic.caresync_release_snapshot_insert_guard()",
        "functioncaresync_release_snapshot_insert_guard()",
        "procedurepublic.caresync_release_snapshot_insert_guard()",
        "procedurecaresync_release_snapshot_insert_guard()",
    )
    return bool(
        all(fragment in function for fragment in required_fragments)
        and function.count("raiseexception") == 1
        and function.count("ifnotexists(") == 1
        and function.count("orexists(") == 1
        and not any(pattern.search(function) for pattern in _PROJECTION_FORBIDDEN_DML)
        and trigger.startswith(trigger_prefix)
        and trigger.endswith(trigger_suffixes)
        and "when(" not in trigger
    )


_RELEASE_RESOURCE_TABLE_RESULT = _compact_sql(
    "TABLE(release_id uuid, organization_id uuid, facility_id uuid, room_id uuid, "
    "child_id uuid, attendance_day_id uuid, attendance_interval_id uuid, "
    "attendance_day_version integer, checkout_event_id uuid, staff_shift_id uuid, "
    "actor_user_id uuid, actor_membership_id uuid, recipient_person_id uuid, "
    "recipient_person_version_id uuid, recipient_display_name text, "
    "recipient_relationship text, authorization_id uuid, authorization_version integer, "
    "authority_revision integer, restriction_digest_sha256 text, "
    "verification_policy_code text, verification_method text, verification_result text, "
    "decision_policy_version text, requested_at timestamp with time zone, "
    "checked_out_at timestamp with time zone, committed_at timestamp with time zone, "
    "client_operation_id uuid, request_hash text, release_mode text)"
)


def _release_checkout_activation_projection_is_hardened(definition: str) -> bool:
    """Require pure facility activation truth behind an identity boundary."""

    function = _compact_sql(definition)
    required = (
        "returnsboolean",
        "stable",
        "securitydefiner",
        "current_setting('app.current_organization_id',true)",
        "current_setting('app.current_user_id',true)",
        "frompublic.usersasactor",
        "joinpublic.organization_membershipsasmembership",
        "membership.organization_id=context_organization_id",
        "membership.status='active'",
        "joinpublic.organizationsasorganization_record",
        "organization_record.status='active'",
        "joinpublic.facilitiesasfacility",
        "facility.organization_id=membership.organization_id",
        "facility.id=requested_facility_id",
        "facility.status='active'",
        "joinpublic.facility_release_checkout_activationsasactivation",
        "activation.organization_id=facility.organization_id",
        "activation.facility_id=facility.id",
        "activation.activation_policy_version='normal_verified_release_v1'",
        "actor.id=context_user_id",
        "actor.is_active=true",
        "actor.email_verified_atisnotnull",
    )
    return bool(
        all(marker in function for marker in required)
        and "permission.value=" not in function
        and "joinpublic.roles" not in function
        and "public.staff_shifts" not in function
        and not any(pattern.search(function) for pattern in _PROJECTION_FORBIDDEN_DML)
        and function.count("returnexists(") == 1
    )


def _release_checkout_replay_projection_is_hardened(
    definition: str,
    result_type: str,
) -> bool:
    """Require the actor/org/operation-bound post-commit replay resource."""

    function = _compact_sql(definition)
    required = (
        "stable",
        "securitydefiner",
        "current_setting('app.current_organization_id',true)",
        "current_setting('app.current_user_id',true)",
        "current_setting('app.current_childcare_operation_id',true)",
        "context_operation_id<>requested_client_operation_id",
        "frompublic.usersasactor",
        "joinpublic.organization_membershipsasmembership",
        "membership.status='active'",
        "joinpublic.organizationsasorganization_record",
        "organization_record.status='active'",
        "actor.id=context_user_id",
        "actor.is_active=true",
        "actor.email_verified_atisnotnull",
        "returnqueryselectsnapshot.id,snapshot.organization_id",
        "frompublic.attendance_release_snapshotsassnapshot",
        "joinpublic.childcare_command_receiptsasreceipt",
        "snapshot.actor_user_id=context_user_id",
        "receipt.actor_user_id=context_user_id",
        "receipt.command_type='attendance.release.checkout'",
        "receipt.target_type='attendance_release'",
        "receipt.committed_at=snapshot.committed_at",
        "release_checkout_receipt_incomplete",
    )
    resource_sequence = (
        "snapshot.actor_membership_id,snapshot.recipient_person_id,"
        "snapshot.recipient_person_version_id,"
        "snapshot.recipient_display_name::text"
    )
    return bool(
        _compact_sql(result_type) == _RELEASE_RESOURCE_TABLE_RESULT
        and all(marker in function for marker in required)
        and resource_sequence in function
        and function.count("snapshot.recipient_person_id,") == 1
        and function.count("snapshot.recipient_person_version_id,") == 1
        and "permission.value=" not in function
        and "joinpublic.roles" not in function
        and "public.staff_shifts" not in function
        and not any(pattern.search(function) for pattern in _PROJECTION_FORBIDDEN_DML)
    )


def _release_checkout_snapshot_repository_is_hardened(
    definition: str,
    result_type: str,
) -> bool:
    """Require the one-statement event/receipt/snapshot append repository."""

    function = _compact_sql(definition)
    required = (
        "securitydefiner",
        "requested_decision_attimestampwithtimezone",
        "requested_requested_attimestampwithtimezone",
        "current_setting('app.current_organization_id',true)",
        "current_setting('app.current_user_id',true)",
        "current_setting('app.current_childcare_operation_id',true)",
        "decision_at<pg_catalog.transaction_timestamp()",
        "observed_after_locks:=pg_catalog.clock_timestamp()",
        "selected_authorization_effective_until<=observed_after_locks",
        "selected_evidence_expires_at<=observed_after_locks",
        "permission.value='attendance:record'",
        "permission.value='release:checkout'",
        "joinpublic.facility_release_checkout_activationsasactivation",
        "forshareofactor,membership,organization_record,role_record",
        "forshareoffacility,activation",
        "forshareofshift_record",
        "forshareofchild_record,family_record,authority_head,attendance_day,"
        "attendance_interval,enrollment,room_record,program_record",
        "forshareofauthorization_record,person_record,person_version,evidence,assessment",
        "selected_scope_basis:='organization_role'",
        "selected_scope_basis:='room_assignment'",
        "evidence_document:=",
        "pg_catalog.sha256(pg_catalog.convert_to(evidence_document,'utf8'))",
        "insertintopublic.attendance_events",
        "insertintopublic.childcare_command_receipts",
        "insertintopublic.attendance_release_snapshots",
        "'attendance.release.checkout'",
        "'attendance_release'",
        "committed_version,committed_at,outcome",
        "context_operation_id,requested_request_hash,'normal',null,null",
        "returnqueryselectsnapshot.id,snapshot.organization_id",
    )
    event_position = function.find("insertintopublic.attendance_events")
    receipt_position = function.find("insertintopublic.childcare_command_receipts")
    snapshot_position = function.find("insertintopublic.attendance_release_snapshots")
    resource_sequence = (
        "snapshot.actor_membership_id,snapshot.recipient_person_id,"
        "snapshot.recipient_person_version_id,"
        "snapshot.recipient_display_name::text"
    )
    return bool(
        _compact_sql(result_type) == _RELEASE_RESOURCE_TABLE_RESULT
        and all(marker in function for marker in required)
        and function.count("insertintopublic.attendance_events") == 1
        and function.count("insertintopublic.childcare_command_receipts") == 1
        and function.count("insertintopublic.attendance_release_snapshots") == 1
        and 0 <= event_position < receipt_position < snapshot_position
        and resource_sequence in function
        and function.count("snapshot.recipient_person_id,") == 1
        and function.count("snapshot.recipient_person_version_id,") == 1
    )


def _release_checkout_snapshot_time_guard_is_hardened(
    function_definition: str,
    trigger_definition: str,
) -> bool:
    """Require receipt-derived checkout/commit time before C consistency."""

    function = _compact_sql(function_definition)
    trigger = _compact_sql(trigger_definition)
    required = (
        "returnstrigger",
        "securitydefiner",
        "frompublic.childcare_command_receiptsasreceipt",
        "receipt.client_operation_id=new.client_operation_id",
        "receipt.actor_user_id=new.actor_user_id",
        "receipt.command_type='attendance.release.checkout'",
        "receipt.target_type='attendance_release'",
        "receipt.target_id=new.id",
        "receipt.request_hash=new.request_hash",
        "receipt.xmin=pg_catalog.pg_current_xact_id()::text::xid",
        "new.checked_out_at:=receipt_committed_at",
        "new.committed_at:=receipt_committed_at",
        "returnnew",
    )
    trigger_prefix = (
        "createtriggerzy_attendance_release_snapshots_commit_time"
        "beforeinsertonpublic.attendance_release_snapshotsforeachrowexecute"
    )
    return bool(
        all(marker in function for marker in required)
        and trigger.startswith(trigger_prefix)
        and trigger.endswith("caresync_release_snapshot_commit_time_guard()")
        and "when(" not in trigger
    )


def _release_checkout_interval_guard_is_hardened(
    function_definition: str,
    trigger_definition: str,
) -> bool:
    """Require immutable released intervals and one same-xact close bundle."""

    function = _compact_sql(function_definition)
    trigger = _compact_sql(trigger_definition)
    required = (
        "returnstrigger",
        "securitydefiner",
        "iftg_op='delete'then",
        "frompublic.attendance_release_snapshotsassnapshot",
        "joinpublic.facility_release_checkout_activationsasactivation",
        "old.checked_out_atisnullandnew.checked_out_atisnotnullandactivated",
        "joinpublic.attendance_eventsascheckout_event",
        "joinpublic.childcare_command_receiptsasreceipt",
        "snapshot.checked_out_at=new.checked_out_at",
        "snapshot.xmin=pg_catalog.pg_current_xact_id()::text::xid",
        "checkout_event.xmin=pg_catalog.pg_current_xact_id()::text::xid",
        "receipt.xmin=pg_catalog.pg_current_xact_id()::text::xid",
        "constraint='ck_verified_release_interval_bundle'",
        "constraint='ck_verified_release_interval_immutable'",
    )
    trigger_prefix = (
        "createtriggerattendance_intervals_verified_release_guard"
        "beforedeleteorupdateonpublic.attendance_intervalsforeachrowexecute"
    )
    return bool(
        all(marker in function for marker in required)
        and trigger.startswith(trigger_prefix)
        and trigger.endswith("caresync_attendance_interval_verified_release_guard()")
        and "when(" not in trigger
    )


class Database:
    """Own the SQLAlchemy engine without creating or changing tables."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if settings.database_type == "sqlite":
            # BEGIN IMMEDIATE makes the first operation-slot INSERT acquire
            # SQLite's single-writer reservation before either command ledger
            # can be observed or mutated. It is the non-PostgreSQL equivalent
            # of the per-operation advisory/slot serialization contract.
            connect_args: dict[str, Any] = {
                "check_same_thread": False,
                "isolation_level": "IMMEDIATE",
                "timeout": 30,
            }
        else:
            connect_args = {}
            if settings.database_ssl:
                connect_args["sslmode"] = "require"
            postgres_options = ["-c search_path=public,pg_catalog"]
            if settings.database_read_only:
                postgres_options.append("-c default_transaction_read_only=on")
            # Never inherit a role-, database-, or environment-controlled path.
            # The runtime bootstrap pins the role default too, while this startup
            # option protects the very first statement on every pooled connection.
            connect_args["options"] = " ".join(postgres_options)
        self.engine: Engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        if settings.database_type == "sqlite":
            self._configure_sqlite()
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        self._public_job_catalog_outbox_enabled: bool | None = None
        self._admissions_decision_spine_enabled: bool | None = None
        self._live_room_presence_safety_board_enabled: bool | None = None
        self.transport_evidence_engine: Engine | None = None
        self.transport_evidence_session_factory: sessionmaker[Session] | None = None
        evidence_url = settings.transport_evidence_ingest_database_url
        if (
            evidence_url is not None
            and not settings.database_read_only
            and not settings.enable_advanced_routes
        ):
            evidence_connect_args: dict[str, Any] = {
                "options": "-c search_path=public,pg_catalog",
                "connect_timeout": 3,
            }
            if settings.database_ssl:
                evidence_connect_args["sslmode"] = "require"
            self.transport_evidence_engine = create_engine(
                evidence_url,
                connect_args=evidence_connect_args,
                pool_pre_ping=True,
            )
            self.transport_evidence_session_factory = sessionmaker(
                bind=self.transport_evidence_engine,
                autoflush=False,
                expire_on_commit=False,
            )

    def _configure_sqlite(self) -> None:
        read_only = self.settings.database_read_only

        @event.listens_for(self.engine, "connect")
        def configure_connection(dbapi_connection: Any, _: Any) -> None:
            register_sqlite_functions(dbapi_connection)
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            if read_only:
                cursor.execute("PRAGMA query_only=ON")
            cursor.close()

    def has_live_room_presence_safety_board(self) -> bool:
        """Fail closed unless the complete additive 0041 boundary is present."""

        if self._live_room_presence_safety_board_enabled is not None:
            return self._live_room_presence_safety_board_enabled
        expected = {
            "staff_room_presence_sessions",
            "staff_room_presence_events",
            "room_operational_exception_heads",
            "room_operational_exception_events",
        }
        required_columns = {
            "staff_room_presence_sessions": {
                "organization_id",
                "membership_id",
                "staff_shift_id",
                "facility_id",
                "room_id",
                "source",
                "started_at",
                "ended_at",
                "start_operation_id",
                "end_operation_id",
                "version",
            },
            "staff_room_presence_events": {
                "organization_id",
                "operation_id",
                "actor_user_id",
                "membership_id",
                "staff_shift_id",
                "facility_id",
                "event_type",
                "request_sha256",
                "intent",
                "result",
            },
            "room_operational_exception_heads": {
                "organization_id",
                "facility_id",
                "scope_kind",
                "scope_id",
                "condition_code",
                "state",
                "current_fingerprint_sha256",
                "current_evidence",
                "last_changed_at",
                "version",
            },
            "room_operational_exception_events": {
                "organization_id",
                "exception_id",
                "operation_id",
                "event_type",
                "cause_entity_type",
                "cause_entity_id",
                "current_fingerprint_sha256",
                "evidence",
            },
        }
        required_postgres_column_specs = {
            "staff_room_presence_sessions": {
                "id": ("uuid", False, None, None),
                "organization_id": ("uuid", False, None, None),
                "membership_id": ("uuid", False, None, None),
                "staff_shift_id": ("uuid", False, None, None),
                "facility_id": ("uuid", False, None, None),
                "room_id": ("uuid", False, None, None),
                "source": ("varchar", False, 30, None),
                "started_at": ("timestamptz", False, None, None),
                "ended_at": ("timestamptz", True, None, None),
                "end_reason": ("varchar", True, 30, None),
                "start_operation_id": ("uuid", False, None, None),
                "end_operation_id": ("uuid", True, None, None),
                "started_by_user_id": ("uuid", False, None, None),
                "ended_by_user_id": ("uuid", True, None, None),
                "version": ("int4", False, None, "1"),
                "created_at": ("timestamptz", False, None, "now()"),
                "updated_at": ("timestamptz", False, None, "now()"),
            },
            "staff_room_presence_events": {
                "id": ("uuid", False, None, None),
                "organization_id": ("uuid", False, None, None),
                "operation_id": ("uuid", False, None, None),
                "actor_user_id": ("uuid", False, None, None),
                "membership_id": ("uuid", False, None, None),
                "staff_shift_id": ("uuid", False, None, None),
                "facility_id": ("uuid", False, None, None),
                "event_type": ("varchar", False, 40, None),
                "from_session_id": ("uuid", True, None, None),
                "to_session_id": ("uuid", True, None, None),
                "request_sha256": ("bpchar", False, 64, None),
                "intent": ("json", False, None, None),
                "result": ("json", False, None, None),
                "occurred_at": ("timestamptz", False, None, None),
                "created_at": ("timestamptz", False, None, "now()"),
            },
            "room_operational_exception_heads": {
                "id": ("uuid", False, None, None),
                "organization_id": ("uuid", False, None, None),
                "facility_id": ("uuid", False, None, None),
                "scope_kind": ("varchar", False, 20, None),
                "scope_id": ("uuid", False, None, None),
                "room_id": ("uuid", True, None, None),
                "condition_code": ("varchar", False, 100, None),
                "state": ("varchar", False, 20, None),
                "current_fingerprint_sha256": (
                    "bpchar",
                    False,
                    64,
                    None,
                ),
                "current_evidence": ("json", False, None, None),
                "opened_at": ("timestamptz", False, None, None),
                "last_changed_at": ("timestamptz", False, None, None),
                "acknowledged_at": ("timestamptz", True, None, None),
                "acknowledged_by_user_id": (
                    "uuid",
                    True,
                    None,
                    None,
                ),
                "acknowledgement_reason": ("text", True, None, None),
                "resolved_at": ("timestamptz", True, None, None),
                "version": ("int4", False, None, "1"),
                "created_at": ("timestamptz", False, None, "now()"),
                "updated_at": ("timestamptz", False, None, "now()"),
            },
            "room_operational_exception_events": {
                "id": ("uuid", False, None, None),
                "organization_id": ("uuid", False, None, None),
                "exception_id": ("uuid", False, None, None),
                "operation_id": ("uuid", False, None, None),
                "event_type": ("varchar", False, 30, None),
                "actor_user_id": ("uuid", True, None, None),
                "cause_entity_type": ("varchar", False, 60, None),
                "cause_entity_id": ("uuid", False, None, None),
                "previous_fingerprint_sha256": (
                    "bpchar",
                    True,
                    64,
                    None,
                ),
                "current_fingerprint_sha256": (
                    "bpchar",
                    False,
                    64,
                    None,
                ),
                "evidence": ("json", False, None, None),
                "reason": ("text", True, None, None),
                "occurred_at": ("timestamptz", False, None, None),
                "created_at": ("timestamptz", False, None, "now()"),
            },
        }
        required_columns = {
            table_name: set(specs)
            for table_name, specs in required_postgres_column_specs.items()
        }
        required_indexes = {
            "uq_room_presence_sessions_open_membership",
            "uq_room_presence_sessions_open_shift",
            "ix_room_presence_sessions_room_live",
            "ix_room_presence_events_membership_time",
            "uq_room_operational_exceptions_unresolved",
            "ix_room_operational_exceptions_facility_state",
            "ix_room_operational_exception_events_timeline",
        }
        required_index_specs = {
            "uq_room_presence_sessions_open_membership": (
                "staff_room_presence_sessions",
                ("organization_id", "membership_id"),
                True,
                "ended_atisnull",
            ),
            "uq_room_presence_sessions_open_shift": (
                "staff_room_presence_sessions",
                ("organization_id", "staff_shift_id"),
                True,
                "ended_atisnull",
            ),
            "ix_room_presence_sessions_room_live": (
                "staff_room_presence_sessions",
                ("organization_id", "facility_id", "room_id", "ended_at"),
                False,
                "",
            ),
            "ix_room_presence_events_membership_time": (
                "staff_room_presence_events",
                ("organization_id", "membership_id", "occurred_at"),
                False,
                "",
            ),
            "uq_room_operational_exceptions_unresolved": (
                "room_operational_exception_heads",
                ("organization_id", "scope_kind", "scope_id", "condition_code"),
                True,
                "state<>'resolved'",
            ),
            "ix_room_operational_exceptions_facility_state": (
                "room_operational_exception_heads",
                ("organization_id", "facility_id", "state", "last_changed_at"),
                False,
                "",
            ),
            "ix_room_operational_exception_events_timeline": (
                "room_operational_exception_events",
                ("organization_id", "exception_id", "occurred_at"),
                False,
                "",
            ),
        }
        required_constraints = {
            "staff_room_presence_sessions": {
                "fk_room_presence_sessions_membership",
                "fk_room_presence_sessions_shift",
                "fk_room_presence_sessions_facility",
                "fk_room_presence_sessions_room",
                "fk_room_presence_sessions_started_by",
                "fk_room_presence_sessions_ended_by",
                "uq_room_presence_sessions_org_id",
                "ck_room_presence_sessions_source",
                "ck_room_presence_sessions_end_reason",
                "ck_room_presence_sessions_terminal_bundle",
                "ck_room_presence_sessions_time_order",
                "ck_room_presence_sessions_version",
            },
            "staff_room_presence_events": {
                "fk_room_presence_events_membership",
                "fk_room_presence_events_shift",
                "fk_room_presence_events_facility",
                "fk_room_presence_events_from_session",
                "fk_room_presence_events_to_session",
                "fk_room_presence_events_actor",
                "uq_room_presence_events_org_id",
                "uq_room_presence_events_operation",
                "ck_room_presence_events_type",
                "ck_room_presence_events_transition",
                "ck_room_presence_events_request_sha256",
            },
            "room_operational_exception_heads": {
                "fk_room_operational_exceptions_facility",
                "fk_room_operational_exceptions_room",
                "fk_room_operational_exceptions_acknowledged_by",
                "uq_room_operational_exceptions_org_id",
                "ck_room_operational_exceptions_scope",
                "ck_room_operational_exceptions_scope_identity",
                "ck_room_operational_exceptions_condition",
                "ck_room_operational_exceptions_state",
                "ck_room_operational_exceptions_fingerprint",
                "ck_room_operational_exceptions_state_bundle",
                "ck_room_operational_exceptions_version",
            },
            "room_operational_exception_events": {
                "fk_room_operational_exception_events_head",
                "fk_room_operational_exception_events_actor",
                "uq_room_operational_exception_events_org_id",
                "uq_room_operational_exception_events_operation",
                "ck_room_operational_exception_events_type",
                "ck_room_operational_exception_events_acknowledgement",
                "ck_room_operational_exception_events_current_fingerprint",
                "ck_room_operational_exception_events_previous_fingerprint",
            },
        }
        required_fk_bindings = {
            "staff_room_presence_sessions": {
                (
                    ("organization_id", "membership_id"),
                    "organization_memberships",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "staff_shift_id"),
                    "staff_shifts",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "facility_id"),
                    "facilities",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "facility_id", "room_id"),
                    "rooms",
                    ("organization_id", "facility_id", "id"),
                ),
                (("started_by_user_id",), "users", ("id",)),
                (("ended_by_user_id",), "users", ("id",)),
            },
            "staff_room_presence_events": {
                (
                    ("organization_id", "membership_id"),
                    "organization_memberships",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "staff_shift_id"),
                    "staff_shifts",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "facility_id"),
                    "facilities",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "from_session_id"),
                    "staff_room_presence_sessions",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "to_session_id"),
                    "staff_room_presence_sessions",
                    ("organization_id", "id"),
                ),
                (("actor_user_id",), "users", ("id",)),
            },
            "room_operational_exception_heads": {
                (
                    ("organization_id", "facility_id"),
                    "facilities",
                    ("organization_id", "id"),
                ),
                (
                    ("organization_id", "facility_id", "room_id"),
                    "rooms",
                    ("organization_id", "facility_id", "id"),
                ),
                (("acknowledged_by_user_id",), "users", ("id",)),
            },
            "room_operational_exception_events": {
                (
                    ("organization_id", "exception_id"),
                    "room_operational_exception_heads",
                    ("organization_id", "id"),
                ),
                (("actor_user_id",), "users", ("id",)),
            },
        }
        required_unique_bindings = {
            "staff_room_presence_sessions": {
                "uq_room_presence_sessions_org_id": (
                    "organization_id",
                    "id",
                ),
            },
            "staff_room_presence_events": {
                "uq_room_presence_events_org_id": (
                    "organization_id",
                    "id",
                ),
                "uq_room_presence_events_operation": (
                    "organization_id",
                    "operation_id",
                ),
            },
            "room_operational_exception_heads": {
                "uq_room_operational_exceptions_org_id": (
                    "organization_id",
                    "id",
                ),
            },
            "room_operational_exception_events": {
                "uq_room_operational_exception_events_org_id": (
                    "organization_id",
                    "id",
                ),
                "uq_room_operational_exception_events_operation": (
                    "organization_id",
                    "operation_id",
                ),
            },
        }
        required_sha256_checks = {
            "staff_room_presence_events": {
                "ck_room_presence_events_request_sha256": "request_sha256",
            },
            "room_operational_exception_heads": {
                "ck_room_operational_exceptions_fingerprint": (
                    "current_fingerprint_sha256"
                ),
            },
            "room_operational_exception_events": {
                "ck_room_operational_exception_events_current_fingerprint": (
                    "current_fingerprint_sha256"
                ),
                "ck_room_operational_exception_events_previous_fingerprint": (
                    "previous_fingerprint_sha256"
                ),
            },
        }

        def invalid(detail: str) -> NoReturn:
            raise RuntimeError(
                "Partial or drifted 0041 live room-presence boundary; "
                f"{detail}; repair the schema and runtime grants before startup"
            )

        with self.engine.connect() as connection:
            inspector = inspect(connection)
            found = expected.intersection(inspector.get_table_names())
            if not found:
                self._live_room_presence_safety_board_enabled = False
                return False
            if found != expected:
                invalid("required tables are incomplete")
            revision = (
                connection.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
                if "alembic_version" in inspector.get_table_names()
                else None
            )
            if revision is None and self.settings.database_type == "sqlite":
                # ``BasicBase.metadata.create_all`` is intentionally used by
                # isolated portable tests and developer fixtures.  It creates
                # the model tables but not the migration-owned mutation
                # guards, so the truthful result is an unavailable foundation,
                # not a fatal partial-release diagnosis.  A migrated/stamped
                # SQLite proof database continues through full attestation.
                self._live_room_presence_safety_board_enabled = False
                return False
            if not _revision_descends_from(
                str(revision or ""),
                "0041_live_room_presence",
            ):
                invalid(
                    "Alembic revision does not descend from the trusted "
                    "0041_live_room_presence boundary"
                )
            indexes: set[str] = set()
            for table_name in expected:
                columns = {
                    str(column["name"]) for column in inspector.get_columns(table_name)
                }
                if required_columns[table_name] != columns:
                    invalid(f"{table_name} column set is not exact")
                table_indexes = inspector.get_indexes(table_name)
                indexes.update(
                    str(index["name"])
                    for index in table_indexes
                    if index.get("name")
                )
                for index in table_indexes:
                    index_name = str(index.get("name") or "")
                    expected_spec = required_index_specs.get(index_name)
                    if expected_spec is None:
                        continue
                    (
                        expected_table,
                        expected_columns,
                        expected_unique,
                        expected_predicate,
                    ) = expected_spec
                    dialect_options = index.get("dialect_options") or {}
                    predicate = dialect_options.get(
                        f"{connection.dialect.name}_where"
                    )
                    if (
                        table_name != expected_table
                        or tuple(
                            str(value)
                            for value in index.get("column_names", ())
                        )
                        != expected_columns
                        or bool(index.get("unique")) != expected_unique
                        or _normalized_0041_catalog_expression(
                            str(predicate) if predicate is not None else ""
                        )
                        != expected_predicate
                    ):
                        invalid(f"{index_name} definition is not exact")
                check_constraints = inspector.get_check_constraints(table_name)
                foreign_keys = inspector.get_foreign_keys(table_name)
                unique_constraints = inspector.get_unique_constraints(
                    table_name
                )
                constraints = {
                    str(item["name"])
                    for group in (
                        check_constraints,
                        foreign_keys,
                        unique_constraints,
                    )
                    for item in group
                    if item.get("name")
                }
                if constraints != required_constraints[table_name]:
                    invalid(f"{table_name} constraint set is not exact")
                actual_fk_bindings = {
                    (
                        tuple(str(value) for value in item["constrained_columns"]),
                        str(item["referred_table"]),
                        tuple(str(value) for value in item["referred_columns"]),
                    )
                    for item in foreign_keys
                }
                if actual_fk_bindings != required_fk_bindings[table_name]:
                    invalid(f"{table_name} foreign-key bindings are not exact")
                actual_unique_bindings = {
                    str(item["name"]): tuple(
                        str(value)
                        for value in item.get("column_names", ())
                    )
                    for item in unique_constraints
                    if item.get("name")
                }
                if (
                    actual_unique_bindings
                    != required_unique_bindings[table_name]
                ):
                    invalid(
                        f"{table_name} unique-constraint bindings are not exact"
                    )
                if any(
                    str((item.get("options") or {}).get("ondelete", "")).upper()
                    != "RESTRICT"
                    for item in foreign_keys
                ):
                    invalid(f"{table_name} foreign-key delete rules are not exact")
                checks_by_name = {
                    str(item["name"]): _compact_sql(str(item.get("sqltext") or ""))
                    for item in check_constraints
                    if item.get("name")
                }
                for check_name, column_name in required_sha256_checks.get(
                    table_name, {}
                ).items():
                    definition = checks_by_name.get(check_name, "")
                    if (
                        definition.count("replace(") != 16
                        or column_name not in definition
                        or "length(" not in definition
                        or "=64" not in definition
                        or "lower(" not in definition
                        or "=0" not in definition
                    ):
                        invalid(f"{check_name} is not an exact lowercase-hex check")
            if not required_indexes.issubset(indexes):
                invalid("required indexes are incomplete")
            if self.settings.database_type == "sqlite":
                trigger_names = {
                    str(row.name)
                    for row in connection.execute(
                        text(
                            "SELECT name FROM sqlite_master "
                            "WHERE type='trigger' AND ("
                            "name LIKE 'staff_room_presence_%' OR "
                            "name LIKE 'room_operational_exception_%')"
                        )
                    )
                }
                required_triggers = {
                    "staff_room_presence_sessions_insert_guard",
                    "staff_room_presence_sessions_update_guard",
                    "staff_room_presence_sessions_no_delete",
                    "staff_room_presence_events_no_update",
                    "staff_room_presence_events_no_delete",
                    "room_operational_exception_heads_insert_guard",
                    "room_operational_exception_heads_update_guard",
                    "room_operational_exception_heads_no_delete",
                    "room_operational_exception_events_no_update",
                    "room_operational_exception_events_no_delete",
                }
                if not required_triggers.issubset(trigger_names):
                    invalid("portable mutation guards are incomplete")
                self._live_room_presence_safety_board_enabled = True
                return True

            relation_rows = list(
                connection.execute(
                    text(
                        "SELECT class.relname,class.relrowsecurity,class.relforcerowsecurity,"
                        "pg_catalog.pg_get_userbyid(class.relowner) AS owner "
                        "FROM pg_catalog.pg_class AS class "
                        "WHERE class.oid=ANY(CAST(:tables AS regclass[]))"
                    ),
                    {"tables": [f"public.{name}" for name in sorted(expected)]},
                )
            )
            if len(relation_rows) != len(expected):
                invalid("PostgreSQL relations are incomplete")
            owners = {str(row.owner) for row in relation_rows}
            if (
                any(not row.relrowsecurity or not row.relforcerowsecurity for row in relation_rows)
                or "caresync_basic_app" in owners
                or len(owners) != 1
            ):
                invalid("RLS or ownership boundary is invalid")
            postgres_column_specs: dict[
                str, dict[str, tuple[str, bool, int | None, str | None]]
            ] = {table_name: {} for table_name in expected}
            for row in connection.execute(
                text(
                    "SELECT table_name,column_name,udt_name,is_nullable,"
                    "character_maximum_length,column_default,is_identity "
                    "FROM information_schema.columns "
                    "WHERE table_schema='public' "
                    "AND table_name=ANY(CAST(:tables AS text[]))"
                ),
                {"tables": sorted(expected)},
            ):
                default = (
                    _compact_sql(str(row.column_default))
                    if row.column_default is not None
                    else None
                )
                postgres_column_specs[str(row.table_name)][
                    str(row.column_name)
                ] = (
                    str(row.udt_name),
                    str(row.is_nullable).upper() == "YES",
                    (
                        int(row.character_maximum_length)
                        if row.character_maximum_length is not None
                        else None
                    ),
                    default,
                )
                if str(row.is_identity).upper() != "NO":
                    invalid(
                        f"{row.table_name}.{row.column_name} identity drifted"
                    )
            if postgres_column_specs != required_postgres_column_specs:
                invalid("PostgreSQL column metadata/defaults have drifted")
            postgres_indexes = {
                str(row.index_name): (
                    str(row.table_name),
                    tuple(str(value) for value in (row.columns or [])),
                    bool(row.indisunique),
                    _normalized_0041_catalog_expression(
                        str(row.predicate or "")
                    ),
                )
                for row in connection.execute(
                    text(
                        "SELECT index_relation.relname AS index_name,"
                        "table_relation.relname AS table_name,"
                        "index_row.indisunique,index_row.indisvalid,"
                        "index_row.indisready,index_row.indislive,"
                        "method.amname,index_row.indnkeyatts,"
                        "index_row.indnatts,"
                        "ARRAY(SELECT attribute.attname "
                        "FROM unnest(index_row.indkey) WITH ORDINALITY "
                        "AS key(attnum,position) "
                        "JOIN pg_catalog.pg_attribute AS attribute "
                        "ON attribute.attrelid=index_row.indrelid "
                        "AND attribute.attnum=key.attnum "
                        "ORDER BY key.position) AS columns,"
                        "pg_catalog.pg_get_expr("
                        "index_row.indpred,index_row.indrelid,true) "
                        "AS predicate "
                        "FROM pg_catalog.pg_index AS index_row "
                        "JOIN pg_catalog.pg_class AS index_relation "
                        "ON index_relation.oid=index_row.indexrelid "
                        "JOIN pg_catalog.pg_class AS table_relation "
                        "ON table_relation.oid=index_row.indrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=table_relation.relnamespace "
                        "JOIN pg_catalog.pg_am AS method "
                        "ON method.oid=index_relation.relam "
                        "WHERE namespace.nspname='public' "
                        "AND index_relation.relname="
                        "ANY(CAST(:indexes AS text[])) "
                        "AND index_row.indisvalid "
                        "AND index_row.indisready "
                        "AND index_row.indislive "
                        "AND method.amname='btree' "
                        "AND index_row.indnkeyatts=index_row.indnatts"
                    ),
                    {"indexes": sorted(required_indexes)},
                )
            }
            if postgres_indexes != required_index_specs:
                invalid("PostgreSQL index definitions have drifted")
            constraint_rows = list(
                connection.execute(
                    text(
                        "SELECT relation.relname AS table_name,"
                        "constraint_row.conname,constraint_row.contype,"
                        "constraint_row.convalidated,"
                        "constraint_row.condeferrable,"
                        "constraint_row.condeferred,"
                        "CASE WHEN constraint_row.contype='c' THEN "
                        "pg_catalog.pg_get_expr("
                        "constraint_row.conbin,constraint_row.conrelid,true) "
                        "ELSE NULL END AS expression "
                        "FROM pg_catalog.pg_constraint AS constraint_row "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=constraint_row.conrelid "
                        "WHERE constraint_row.conrelid="
                        "ANY(CAST(:tables AS regclass[])) "
                        "AND constraint_row.contype IN ('c','f','u')"
                    ),
                    {
                        "tables": [
                            f"public.{name}" for name in sorted(expected)
                        ]
                    },
                )
            )
            if any(
                not row.convalidated
                or row.condeferrable
                or row.condeferred
                for row in constraint_rows
            ):
                invalid("PostgreSQL constraints are not immediate and validated")
            check_expression_hashes = {
                (str(row.table_name), str(row.conname)): (
                    _canonical_sql_sha256(str(row.expression or ""))
                )
                for row in constraint_rows
                if str(row.contype) == "c"
            }
            if (
                check_expression_hashes
                != _LIVE_ROOM_PRESENCE_0041_CHECK_EXPRESSION_SHA256
            ):
                invalid("PostgreSQL CHECK expressions have drifted")
            policy_rows = list(
                connection.execute(
                    text(
                        "SELECT tablename,policyname,permissive,roles,cmd,"
                        "qual,with_check FROM pg_catalog.pg_policies "
                        "WHERE schemaname='public' AND tablename=ANY(CAST(:tables AS text[]))"
                    ),
                    {"tables": sorted(expected)},
                )
            )
            if len(policy_rows) != len(expected):
                invalid("active-membership tenant policies are incomplete")
            for policy in policy_rows:
                roles = policy.roles
                if isinstance(roles, str):
                    role_values = {
                        value.strip()
                        for value in roles.strip("{}").split(",")
                        if value.strip()
                    }
                else:
                    role_values = {
                        str(value) for value in (roles or [])
                    }
                if (
                    policy.policyname
                    != f"{policy.tablename}_tenant"
                    or str(policy.permissive).upper() != "PERMISSIVE"
                    or role_values != {"public"}
                    or str(policy.cmd).upper() != "ALL"
                    or not _live_room_presence_tenant_policy_is_exact(
                        str(policy.qual or "")
                    )
                    or not _live_room_presence_tenant_policy_is_exact(
                        str(policy.with_check or "")
                    )
                ):
                    invalid("active-membership tenant policy definitions drifted")
            expected_trigger_bindings = {
                (
                    "staff_room_presence_sessions",
                    "staff_room_presence_sessions_row_guard",
                ): ("caresync_0041_presence_row_guard", 31, False),
                (
                    "staff_room_presence_sessions",
                    "staff_room_presence_sessions_bundle_guard",
                ): ("caresync_0041_presence_bundle_guard", 21, True),
                (
                    "staff_room_presence_events",
                    "staff_room_presence_events_insert_guard",
                ): ("caresync_0041_presence_event_guard", 7, False),
                (
                    "staff_room_presence_events",
                    "staff_room_presence_events_immutable",
                ): ("caresync_0041_event_immutable_guard", 27, False),
                (
                    "room_operational_exception_heads",
                    "room_operational_exception_heads_row_guard",
                ): ("caresync_0041_exception_head_guard", 31, False),
                (
                    "room_operational_exception_heads",
                    "room_operational_exception_heads_bundle_guard",
                ): ("caresync_0041_exception_bundle_guard", 21, True),
                (
                    "room_operational_exception_events",
                    "room_operational_exception_events_insert_guard",
                ): ("caresync_0041_exception_event_guard", 7, False),
                (
                    "room_operational_exception_events",
                    "room_operational_exception_events_immutable",
                ): ("caresync_0041_event_immutable_guard", 27, False),
            }
            trigger_bindings = {
                (str(row.table_name), str(row.trigger_name)): (
                    str(row.function_name),
                    int(row.trigger_type),
                    bool(row.is_deferred),
                )
                for row in connection.execute(
                    text(
                        "SELECT relation.relname AS table_name,"
                        "trigger.tgname AS trigger_name,"
                        "procedure.proname AS function_name,"
                        "trigger.tgtype AS trigger_type,"
                        "(trigger.tgdeferrable AND trigger.tginitdeferred) "
                        "AS is_deferred,trigger.tgenabled,"
                        "(trigger.tgconstraint<>0) AS is_constraint,"
                        "trigger.tgattr::text AS update_columns,"
                        "trigger.tgqual IS NULL AS has_no_when "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN pg_catalog.pg_proc AS procedure "
                        "ON procedure.oid=trigger.tgfoid "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:tables AS text[])) "
                        "AND NOT trigger.tgisinternal"
                    ),
                    {"tables": sorted(expected)},
                )
            }
            trigger_metadata = list(
                connection.execute(
                    text(
                        "SELECT relation.relname AS table_name,"
                        "trigger.tgname AS trigger_name,"
                        "trigger.tgenabled,"
                        "(trigger.tgconstraint<>0) AS is_constraint,"
                        "trigger.tgattr::text AS update_columns,"
                        "trigger.tgqual IS NULL AS has_no_when "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:tables AS text[])) "
                        "AND NOT trigger.tgisinternal"
                    ),
                    {"tables": sorted(expected)},
                )
            )
            if trigger_bindings != expected_trigger_bindings or any(
                row.tgenabled != "O"
                or bool(row.is_constraint)
                != expected_trigger_bindings[
                    (str(row.table_name), str(row.trigger_name))
                ][2]
                or str(row.update_columns or "") != ""
                or not row.has_no_when
                for row in trigger_metadata
            ):
                invalid("PostgreSQL mutation guard bindings have drifted")
            function_names = set(
                _LIVE_ROOM_PRESENCE_0041_FUNCTION_SOURCE_SHA256
            )
            function_rows = {
                str(row.proname): row
                for row in connection.execute(
                    text(
                        "SELECT procedure.proname,procedure.prosecdef,"
                        "procedure.proconfig,procedure.prosrc,"
                        "procedure.prorettype='pg_catalog.trigger'::regtype "
                        "AS returns_trigger,procedure.provolatile,"
                        "procedure.proparallel,procedure.proleakproof,"
                        "procedure.proisstrict,"
                        "pg_catalog.pg_get_function_identity_arguments("
                        "procedure.oid) AS identity_arguments,"
                        "language.lanname,"
                        "pg_catalog.pg_get_userbyid(procedure.proowner) AS owner,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode("
                        "COALESCE(procedure.proacl,"
                        "pg_catalog.acldefault('f',procedure.proowner))) AS privilege "
                        "WHERE privilege.grantee=0 "
                        "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                        "CASE WHEN pg_catalog.to_regrole('caresync_basic_app') "
                        "IS NULL THEN true ELSE "
                        "pg_catalog.has_function_privilege("
                        "'caresync_basic_app',procedure.oid,'EXECUTE') END "
                        "AS runtime_execute "
                        "FROM pg_catalog.pg_proc AS procedure "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=procedure.pronamespace "
                        "JOIN pg_catalog.pg_language AS language "
                        "ON language.oid=procedure.prolang "
                        "WHERE namespace.nspname='public' "
                        "AND procedure.proname=ANY(CAST(:names AS text[]))"
                    ),
                    {"names": sorted(function_names)},
                )
            }
            if (
                set(function_rows) != function_names
                or any(
                    not row.prosecdef
                    or not row.returns_trigger
                    or row.public_execute
                    or row.runtime_execute
                    or str(row.owner) not in owners
                    or str(row.identity_arguments or "") != ""
                    or row.lanname != "plpgsql"
                    or row.provolatile != "v"
                    or row.proparallel != "u"
                    or row.proleakproof
                    or row.proisstrict
                    or frozenset(
                        str(value).replace(" ", "")
                        for value in (row.proconfig or [])
                    )
                    not in {
                        frozenset({"search_path=pg_catalog"}),
                        frozenset({"search_path=pg_catalog,public"}),
                    }
                    or _canonical_sql_sha256(str(row.prosrc))
                    != _LIVE_ROOM_PRESENCE_0041_FUNCTION_SOURCE_SHA256[
                        str(row.proname)
                    ]
                    for row in function_rows.values()
                )
            ):
                invalid("guard function semantics/ownership/ACL boundary is invalid")
            expected_update_columns = {
                ("staff_room_presence_sessions", "ended_at"),
                ("staff_room_presence_sessions", "end_reason"),
                ("staff_room_presence_sessions", "end_operation_id"),
                ("staff_room_presence_sessions", "ended_by_user_id"),
                ("staff_room_presence_sessions", "version"),
                ("staff_room_presence_sessions", "updated_at"),
                ("room_operational_exception_heads", "state"),
                (
                    "room_operational_exception_heads",
                    "current_fingerprint_sha256",
                ),
                ("room_operational_exception_heads", "current_evidence"),
                ("room_operational_exception_heads", "last_changed_at"),
                ("room_operational_exception_heads", "acknowledged_at"),
                (
                    "room_operational_exception_heads",
                    "acknowledged_by_user_id",
                ),
                ("room_operational_exception_heads", "acknowledgement_reason"),
                ("room_operational_exception_heads", "resolved_at"),
                ("room_operational_exception_heads", "version"),
                ("room_operational_exception_heads", "updated_at"),
            }
            actual_update_columns = {
                (str(row.table_name), str(row.column_name))
                for row in connection.execute(
                    text(
                        "SELECT relation.relname AS table_name,"
                        "attribute.attname AS column_name "
                        "FROM pg_catalog.pg_attribute AS attribute "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=attribute.attrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "CROSS JOIN LATERAL pg_catalog.aclexplode("
                        "COALESCE(attribute.attacl,"
                        "pg_catalog.acldefault('c',relation.relowner))) "
                        "AS privilege "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:tables AS text[])) "
                        "AND attribute.attnum>0 "
                        "AND NOT attribute.attisdropped "
                        "AND privilege.grantee="
                        "pg_catalog.to_regrole('caresync_basic_app') "
                        "AND privilege.privilege_type='UPDATE'"
                    ),
                    {"tables": sorted(expected)},
                )
            }
            if actual_update_columns != expected_update_columns:
                invalid("runtime UPDATE column grants are not exact")
            for table_name in expected:
                if (
                    connection.scalar(
                        text(
                            "SELECT EXISTS ("
                            "SELECT 1 FROM pg_catalog.pg_class AS class "
                            "CROSS JOIN LATERAL pg_catalog.aclexplode("
                            "COALESCE(class.relacl,pg_catalog.acldefault('r',class.relowner))) "
                            "AS privilege WHERE class.oid=CAST(:table AS regclass) "
                            "AND privilege.grantee=0)"
                        ),
                        {"table": f"public.{table_name}"},
                    )
                    or not connection.scalar(
                        text(
                            "SELECT pg_catalog.has_table_privilege("
                            "'caresync_basic_app',CAST(:table AS regclass),'SELECT')"
                        ),
                        {"table": f"public.{table_name}"},
                    )
                    or not connection.scalar(
                        text(
                            "SELECT pg_catalog.has_table_privilege("
                            "'caresync_basic_app',CAST(:table AS regclass),'INSERT')"
                        ),
                        {"table": f"public.{table_name}"},
                    )
                    or bool(
                        connection.scalar(
                        text(
                            "SELECT pg_catalog.has_table_privilege("
                            "'caresync_basic_app',CAST(:table AS regclass),'DELETE')"
                        ),
                        {"table": f"public.{table_name}"},
                        )
                    )
                    or bool(
                        connection.scalar(
                            text(
                                "SELECT pg_catalog.has_table_privilege("
                                "'caresync_basic_app',CAST(:table AS regclass),'TRUNCATE')"
                            ),
                            {"table": f"public.{table_name}"},
                        )
                    )
                    or bool(
                        connection.scalar(
                        text(
                            "SELECT pg_catalog.has_table_privilege("
                            "'caresync_basic_app',CAST(:table AS regclass),'UPDATE')"
                        ),
                        {"table": f"public.{table_name}"},
                        )
                    )
                ):
                    invalid(f"{table_name} grants are invalid")
            self._live_room_presence_safety_board_enabled = True
            return True

    def has_admissions_decision_spine(self) -> bool:
        """Attest and cache the complete additive 0039 admissions table boundary."""

        if self._admissions_decision_spine_enabled is not None:
            return self._admissions_decision_spine_enabled

        expected = {
            "admission_applications",
            "admission_application_preferences",
            "admission_waitlist_entries",
            "admission_offers",
            "admission_conversion_links",
            "admission_application_events",
        }
        required_columns = {
            "admission_applications": {
                "reference",
                "status",
                "version",
                "child_date_of_birth",
                "contact_normalized_email",
                "last_operation_id",
            },
            "admission_application_preferences": {
                "current_rank",
                "current_lane_key",
                "application_version",
                "retired_operation_id",
            },
            "admission_waitlist_entries": {
                "current_application_id",
                "priority_at",
                "closure_reason",
                "version",
            },
            "admission_offers": {
                "open_application_id",
                "prior_application_status",
                "respond_by_date",
                "version",
            },
            "admission_conversion_links": {
                "resolution_mode",
                "acceptance_operation_id",
                "review_proof_digest",
            },
            "admission_application_events": {
                "application_version",
                "command",
                "client_operation_id",
            },
        }
        required_indexes = {
            "admission_applications": {
                "ix_admission_applications_organization_id": (
                    ("organization_id",),
                    False,
                ),
                "ix_admission_applications_org_status_updated": (
                    ("organization_id", "status", "updated_at"),
                    False,
                ),
            },
            "admission_application_preferences": {
                "ix_admission_preferences_application": (
                    ("organization_id", "application_id"),
                    False,
                ),
                "uq_admission_preferences_current_rank": (
                    ("organization_id", "application_id", "current_rank"),
                    True,
                ),
                "uq_admission_preferences_current_lane": (
                    ("organization_id", "application_id", "current_lane_key"),
                    True,
                ),
            },
            "admission_waitlist_entries": {
                "ix_admission_waitlist_lane_priority": (
                    (
                        "organization_id",
                        "facility_id",
                        "program_id",
                        "priority_at",
                        "id",
                    ),
                    False,
                ),
                "ix_admission_waitlist_application": (
                    ("organization_id", "application_id"),
                    False,
                ),
            },
            "admission_offers": {
                "ix_admission_offers_application": (
                    ("organization_id", "application_id"),
                    False,
                )
            },
            "admission_conversion_links": {
                "ix_admission_conversion_application": (
                    ("organization_id", "application_id"),
                    False,
                )
            },
            "admission_application_events": {
                "ix_admission_events_timeline": (
                    (
                        "organization_id",
                        "application_id",
                        "application_version",
                    ),
                    False,
                )
            },
        }
        required_constraints = {
            "admission_applications": {
                "uq_admission_applications_org_id",
                "uq_admission_applications_org_reference",
                "ck_admission_applications_source",
                "ck_admission_applications_status",
                "ck_admission_applications_version",
                "ck_admission_applications_submission",
                "ck_admission_applications_terminal",
            },
            "admission_application_preferences": {
                "fk_admission_preferences_application",
                "fk_admission_preferences_facility",
                "fk_admission_preferences_program",
                "uq_admission_preferences_org_id",
                "ck_admission_preferences_rank",
                "ck_admission_preferences_application_version",
                "ck_admission_preferences_current",
            },
            "admission_waitlist_entries": {
                "fk_admission_waitlist_application",
                "fk_admission_waitlist_current_application",
                "fk_admission_waitlist_program",
                "uq_admission_waitlist_org_id",
                "uq_admission_waitlist_current_application",
                "ck_admission_waitlist_status",
                "ck_admission_waitlist_version",
                "ck_admission_waitlist_closure_reason",
                "ck_admission_waitlist_current",
            },
            "admission_offers": {
                "fk_admission_offers_application",
                "fk_admission_offers_open_application",
                "fk_admission_offers_program",
                "uq_admission_offers_org_id",
                "uq_admission_offers_open_application",
                "ck_admission_offers_status",
                "ck_admission_offers_prior_status",
                "ck_admission_offers_version",
                "ck_admission_offers_current",
            },
            "admission_conversion_links": {
                "fk_admission_conversion_application",
                "fk_admission_conversion_offer",
                "fk_admission_conversion_family",
                "fk_admission_conversion_child",
                "fk_admission_conversion_enrollment",
                "uq_admission_conversion_org_id",
                "uq_admission_conversion_application",
                "uq_admission_conversion_offer",
                "uq_admission_conversion_enrollment",
                "ck_admission_conversion_resolution",
                "ck_admission_conversion_review_digest",
            },
            "admission_application_events": {
                "fk_admission_events_application",
                "uq_admission_events_org_id",
                "uq_admission_events_application_version",
                "uq_admission_events_operation",
                "ck_admission_events_application_version",
                "ck_admission_events_to_status",
                "ck_admission_events_from_status",
            },
        }
        receipt_targets = {
            "family",
            "child",
            "enrollment",
            "authority_person",
            "authority_evidence",
            "authority_evidence_object",
            "release_authorization",
            "release_rule",
            "consent",
            "release_activation",
            "attendance_release",
            "admission_application",
            "admission_waitlist",
            "admission_offer",
        }

        def invalid_boundary(detail: str) -> NoReturn:
            raise RuntimeError(
                "Drifted 0039 admissions decision spine; "
                f"{detail}; repair the schema before startup"
            )

        with self.engine.connect() as connection:
            inspector = inspect(connection)
            existing = expected.intersection(inspector.get_table_names())
            if not existing:
                self._admissions_decision_spine_enabled = False
                return False
            if existing != expected:
                raise RuntimeError(
                    "Partial 0039 admissions decision spine; repair the schema before startup"
                )
            for table_name, columns in required_columns.items():
                present = {
                    str(column["name"])
                    for column in inspector.get_columns(table_name)
                }
                if not columns.issubset(present):
                    invalid_boundary(f"{table_name} columns are incomplete")
                indexes = {
                    str(index["name"]): (
                        tuple(str(value) for value in index["column_names"]),
                        bool(index["unique"]),
                    )
                    for index in inspector.get_indexes(table_name)
                    if index.get("name")
                }
                if any(
                    indexes.get(name) != specification
                    for name, specification in required_indexes[table_name].items()
                ):
                    invalid_boundary(f"{table_name} indexes are incomplete")
                constraint_names = {
                    str(value["name"])
                    for collection in (
                        inspector.get_check_constraints(table_name),
                        inspector.get_unique_constraints(table_name),
                        inspector.get_foreign_keys(table_name),
                    )
                    for value in collection
                    if value.get("name")
                }
                if not required_constraints[table_name].issubset(
                    constraint_names
                ):
                    invalid_boundary(f"{table_name} constraints are incomplete")
            receipt_checks = {
                str(value["name"]): str(value.get("sqltext") or "")
                for value in inspector.get_check_constraints(
                    "childcare_command_receipts"
                )
                if value.get("name")
            }
            receipt_definition = receipt_checks.get(
                "ck_childcare_command_receipts_target", ""
            )
            if not receipt_definition or any(
                f"'{target}'" not in receipt_definition
                for target in receipt_targets
            ):
                invalid_boundary("the childcare receipt vocabulary is incomplete")
            revision = None
            if "alembic_version" in inspector.get_table_names():
                revision = connection.scalar(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
            if revision and not _revision_descends_from(
                str(revision), "0039_admissions_decision_spine"
            ):
                raise RuntimeError(
                    "Admissions tables exist outside the trusted 0039 migration graph"
                )
            if self.settings.database_type == "sqlite" and revision:
                expected_triggers = {
                    "admission_application_acceptance_coherence",
                    "admission_offer_acceptance_coherence",
                    "admission_conversion_insert_coherence",
                    "admission_application_preferences_active_program_insert",
                    "admission_application_preferences_active_program_update",
                    "admission_waitlist_entries_active_program_insert",
                    "admission_waitlist_entries_active_program_update",
                    "admission_offers_active_program_insert",
                    "admission_offers_active_program_update",
                    "admission_waitlist_priority_immutable",
                    "admission_conversion_links_no_update",
                    "admission_conversion_links_no_delete",
                    "admission_application_events_no_update",
                    "admission_application_events_no_delete",
                }
                trigger_rows = {
                    str(row.name): _compact_sql(str(row.sql or ""))
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master "
                            "WHERE type='trigger' AND tbl_name IN "
                            "('admission_applications',"
                            "'admission_application_preferences',"
                            "'admission_waitlist_entries','admission_offers',"
                            "'admission_conversion_links',"
                            "'admission_application_events')"
                        )
                    )
                }
                if set(trigger_rows) != expected_triggers:
                    invalid_boundary("SQLite guard triggers are incomplete")
                active_program_triggers = {
                    name
                    for name in expected_triggers
                    if "_active_program_" in name
                }
                if any(
                    "program.is_active=1" not in trigger_rows[name]
                    or "facility.status='active'" not in trigger_rows[name]
                    for name in active_program_triggers
                ):
                    invalid_boundary("SQLite lane guards have drifted")
                if any(
                    marker not in trigger_rows[name]
                    for name, marker in {
                        "admission_conversion_insert_coherence": (
                            "enrollment.status='pending'"
                        ),
                        "admission_offer_acceptance_coherence": (
                            "acceptedadmissionofferrequiresconversion"
                        ),
                        "admission_application_acceptance_coherence": (
                            "acceptedadmissionapplicationrequiresconversion"
                        ),
                    }.items()
                ):
                    invalid_boundary("SQLite conversion guards have drifted")
            elif self.settings.database_type == "postgres":
                forced = int(
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM pg_catalog.pg_class AS relation "
                            "JOIN pg_catalog.pg_namespace AS namespace "
                            "ON namespace.oid=relation.relnamespace "
                            "WHERE namespace.nspname='public' "
                            "AND relation.relname = ANY(:tables) "
                            "AND relation.relrowsecurity "
                            "AND relation.relforcerowsecurity"
                        ),
                        {"tables": sorted(expected)},
                    )
                    or 0
                )
                if forced != len(expected):
                    invalid_boundary("all admission tables must FORCE tenant RLS")

                policies = list(
                    connection.execute(
                        text(
                            "SELECT tablename,policyname,permissive,roles,cmd,"
                            "qual,with_check FROM pg_catalog.pg_policies "
                            "WHERE schemaname='public' "
                            "AND tablename=ANY(CAST(:tables AS text[])) "
                            "ORDER BY tablename,policyname"
                        ),
                        {"tables": sorted(expected)},
                    )
                )
                if len(policies) != len(expected):
                    invalid_boundary("tenant policies are incomplete")
                for policy in policies:
                    roles = policy.roles
                    if isinstance(roles, str):
                        role_values = {
                            value.strip()
                            for value in roles.strip("{}").split(",")
                            if value.strip()
                        }
                    else:
                        role_values = {str(value) for value in (roles or [])}
                    qualifier = _compact_sql(str(policy.qual or ""))
                    check = _compact_sql(str(policy.with_check or ""))
                    normalized_qualifier = qualifier.replace(
                        "pg_catalog.", ""
                    )
                    normalized_check = check.replace("pg_catalog.", "")
                    expected_qualifier = (
                        "(organization_id=(nullif(current_setting("
                        "'app.current_organization_id'::text,true),"
                        "''::text))::uuid)"
                    )
                    if (
                        policy.policyname != f"{policy.tablename}_tenant"
                        or str(policy.permissive).upper() != "PERMISSIVE"
                        or role_values != {"public"}
                        or str(policy.cmd).upper() != "ALL"
                        or normalized_qualifier != expected_qualifier
                        or normalized_check != expected_qualifier
                    ):
                        invalid_boundary("tenant policy definitions have drifted")

                expected_trigger_bindings = {
                    ("admission_applications", "admission_applications_conversion_coherence"): (
                        "caresync_0039_conversion_coherence_guard",
                        True,
                    ),
                    ("admission_applications", "admission_applications_command_row"): (
                        "caresync_0039_command_row_guard",
                        False,
                    ),
                    ("admission_applications", "admission_applications_command_bundle"): (
                        "caresync_0039_command_bundle_guard",
                        True,
                    ),
                    (
                        "admission_application_preferences",
                        "admission_application_preferences_active_program",
                    ): ("caresync_0039_active_program_guard", False),
                    (
                        "admission_application_preferences",
                        "admission_application_preferences_command_row",
                    ): ("caresync_0039_command_row_guard", False),
                    (
                        "admission_application_preferences",
                        "admission_application_preferences_command_bundle",
                    ): ("caresync_0039_command_bundle_guard", True),
                    (
                        "admission_waitlist_entries",
                        "admission_waitlist_priority_immutable",
                    ): ("caresync_0039_waitlist_priority_guard", False),
                    (
                        "admission_waitlist_entries",
                        "admission_waitlist_entries_active_program",
                    ): ("caresync_0039_active_program_guard", False),
                    (
                        "admission_waitlist_entries",
                        "admission_waitlist_entries_command_row",
                    ): ("caresync_0039_command_row_guard", False),
                    (
                        "admission_waitlist_entries",
                        "admission_waitlist_entries_command_bundle",
                    ): ("caresync_0039_command_bundle_guard", True),
                    ("admission_offers", "admission_offers_active_program"): (
                        "caresync_0039_active_program_guard",
                        False,
                    ),
                    ("admission_offers", "admission_offers_conversion_coherence"): (
                        "caresync_0039_conversion_coherence_guard",
                        True,
                    ),
                    ("admission_offers", "admission_offers_command_row"): (
                        "caresync_0039_command_row_guard",
                        False,
                    ),
                    ("admission_offers", "admission_offers_command_bundle"): (
                        "caresync_0039_command_bundle_guard",
                        True,
                    ),
                    (
                        "admission_conversion_links",
                        "admission_conversion_links_immutable",
                    ): ("caresync_0039_immutable_fact", False),
                    (
                        "admission_conversion_links",
                        "admission_conversion_links_conversion_coherence",
                    ): ("caresync_0039_conversion_coherence_guard", True),
                    (
                        "admission_conversion_links",
                        "admission_conversion_links_command_row",
                    ): ("caresync_0039_command_row_guard", False),
                    (
                        "admission_conversion_links",
                        "admission_conversion_links_command_bundle",
                    ): ("caresync_0039_command_bundle_guard", True),
                    (
                        "admission_application_events",
                        "admission_application_events_immutable",
                    ): ("caresync_0039_immutable_fact", False),
                    (
                        "admission_application_events",
                        "admission_application_events_command_row",
                    ): ("caresync_0039_command_row_guard", False),
                    (
                        "admission_application_events",
                        "admission_application_events_command_bundle",
                    ): ("caresync_0039_command_bundle_guard", True),
                }
                trigger_bindings = {
                    (str(row.table_name), str(row.trigger_name)): (
                        str(row.function_name),
                        bool(row.is_deferred),
                    )
                    for row in connection.execute(
                        text(
                            "SELECT relation.relname AS table_name,"
                            "trigger.tgname AS trigger_name,"
                            "procedure.proname AS function_name,"
                            "(trigger.tgdeferrable AND "
                            "trigger.tginitdeferred) AS is_deferred "
                            "FROM pg_catalog.pg_trigger AS trigger "
                            "JOIN pg_catalog.pg_class AS relation "
                            "ON relation.oid=trigger.tgrelid "
                            "JOIN pg_catalog.pg_namespace AS namespace "
                            "ON namespace.oid=relation.relnamespace "
                            "JOIN pg_catalog.pg_proc AS procedure "
                            "ON procedure.oid=trigger.tgfoid "
                            "WHERE namespace.nspname='public' "
                            "AND relation.relname=ANY(CAST(:tables AS text[])) "
                            "AND NOT trigger.tgisinternal "
                            "AND trigger.tgenabled<>'D'"
                        ),
                        {"tables": sorted(expected)},
                    )
                }
                if trigger_bindings != expected_trigger_bindings:
                    invalid_boundary("PostgreSQL guard bindings have drifted")

                function_paths = {
                    "caresync_0039_immutable_fact": "search_path=pg_catalog",
                    "caresync_0039_waitlist_priority_guard": (
                        "search_path=pg_catalog"
                    ),
                    "caresync_0039_active_program_guard": (
                        "search_path=pg_catalog,public"
                    ),
                    "caresync_0039_conversion_coherence_guard": (
                        "search_path=pg_catalog,public"
                    ),
                    "caresync_0039_command_row_guard": (
                        "search_path=pg_catalog"
                    ),
                    "caresync_0039_command_bundle_guard": (
                        "search_path=pg_catalog,public"
                    ),
                }
                function_rows = {
                    str(row.function_name): row
                    for row in connection.execute(
                        text(
                            "SELECT procedure.proname AS function_name,"
                            "procedure.prosecdef,procedure.proconfig,"
                            "procedure.prorettype='pg_catalog.trigger'::regtype "
                            "AS returns_trigger,"
                            "procedure.proowner=relation.relowner AS owner_matches,"
                            "pg_catalog.has_function_privilege("
                            "'caresync_basic_app',procedure.oid,'EXECUTE') "
                            "AS runtime_executes,"
                            "EXISTS (SELECT 1 FROM pg_catalog.aclexplode("
                            "COALESCE(procedure.proacl,pg_catalog.acldefault("
                            "'f',procedure.proowner))) AS privilege "
                            "WHERE privilege.grantee=0 "
                            "AND privilege.privilege_type='EXECUTE') "
                            "AS public_executes "
                            "FROM pg_catalog.pg_proc AS procedure "
                            "JOIN pg_catalog.pg_namespace AS namespace "
                            "ON namespace.oid=procedure.pronamespace "
                            "JOIN pg_catalog.pg_class AS relation "
                            "ON relation.oid='public.admission_applications'::regclass "
                            "WHERE namespace.nspname='public' "
                            "AND procedure.proname=ANY(CAST(:functions AS text[]))"
                        ),
                        {"functions": sorted(function_paths)},
                    )
                }
                if set(function_rows) != set(function_paths):
                    invalid_boundary("PostgreSQL guard functions are incomplete")
                for name, expected_path in function_paths.items():
                    function = function_rows[name]
                    configuration = {
                        str(value).replace(" ", "")
                        for value in (function.proconfig or [])
                    }
                    if (
                        not function.prosecdef
                        or not function.returns_trigger
                        or not function.owner_matches
                        or function.runtime_executes
                        or function.public_executes
                        or configuration != {expected_path}
                    ):
                        invalid_boundary("PostgreSQL guard functions have drifted")

                expected_update_columns = {
                    "admission_applications": {
                        "status",
                        "version",
                        "child_first_name",
                        "child_last_name",
                        "child_normalized_name",
                        "child_date_of_birth",
                        "contact_first_name",
                        "contact_last_name",
                        "contact_relationship",
                        "contact_email",
                        "contact_normalized_email",
                        "contact_telephone",
                        "contact_normalized_telephone",
                        "internal_note",
                        "updated_by_user_id",
                        "last_operation_id",
                        "submitted_at",
                        "review_started_at",
                        "terminal_at",
                        "updated_at",
                    },
                    "admission_application_preferences": {
                        "current_rank",
                        "current_lane_key",
                        "retired_by_user_id",
                        "retired_operation_id",
                        "retired_at",
                    },
                    "admission_waitlist_entries": {
                        "current_application_id",
                        "status",
                        "version",
                        "closure_reason",
                        "updated_by_user_id",
                        "last_operation_id",
                        "closed_at",
                        "updated_at",
                    },
                    "admission_offers": {
                        "open_application_id",
                        "status",
                        "version",
                        "updated_by_user_id",
                        "last_operation_id",
                        "withdrawn_at",
                        "declined_at",
                        "accepted_at",
                        "updated_at",
                    },
                    "admission_conversion_links": set(),
                    "admission_application_events": set(),
                }
                for table_name in sorted(expected):
                    relation = f"public.{table_name}"
                    if not connection.scalar(
                        text(
                            "SELECT pg_catalog.has_table_privilege("
                            "'caresync_basic_app',:relation,'SELECT') "
                            "AND pg_catalog.has_table_privilege("
                            "'caresync_basic_app',:relation,'INSERT')"
                        ),
                        {"relation": relation},
                    ):
                        invalid_boundary("runtime SELECT/INSERT grants are incomplete")
                    if any(
                        bool(
                            connection.scalar(
                                text(
                                    "SELECT pg_catalog.has_table_privilege("
                                    "'caresync_basic_app',:relation,:privilege)"
                                ),
                                {
                                    "relation": relation,
                                    "privilege": privilege,
                                },
                            )
                        )
                        for privilege in (
                            "UPDATE",
                            "DELETE",
                            "TRUNCATE",
                            "REFERENCES",
                            "TRIGGER",
                        )
                    ):
                        invalid_boundary("runtime table grants are over-broad")
                    granted_update_columns = {
                        str(row.column_name)
                        for row in connection.execute(
                            text(
                                "SELECT attribute.attname AS column_name "
                                "FROM pg_catalog.pg_attribute AS attribute "
                                "WHERE attribute.attrelid="
                                "pg_catalog.to_regclass(:relation) "
                                "AND attribute.attnum>0 "
                                "AND NOT attribute.attisdropped "
                                "AND pg_catalog.has_column_privilege("
                                "'caresync_basic_app',attribute.attrelid,"
                                "attribute.attnum,'UPDATE')"
                            ),
                            {"relation": relation},
                        )
                    }
                    if granted_update_columns != expected_update_columns[table_name]:
                        invalid_boundary("runtime column grants have drifted")
                public_grants = int(
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM pg_catalog.pg_class AS relation "
                            "JOIN pg_catalog.pg_namespace AS namespace "
                            "ON namespace.oid=relation.relnamespace "
                            "CROSS JOIN LATERAL pg_catalog.aclexplode("
                            "COALESCE(relation.relacl,pg_catalog.acldefault("
                            "'r',relation.relowner))) AS privilege "
                            "WHERE namespace.nspname='public' "
                            "AND relation.relname=ANY(CAST(:tables AS text[])) "
                            "AND privilege.grantee=0"
                        ),
                        {"tables": sorted(expected)},
                    )
                    or 0
                )
                if public_grants:
                    invalid_boundary("PUBLIC retains admission table privileges")
        self._admissions_decision_spine_enabled = True
        return True

    def has_public_job_catalog_outbox(self) -> bool:
        """Attest and cache the complete additive 0038 public invalidation boundary."""

        if self._public_job_catalog_outbox_enabled is not None:
            return self._public_job_catalog_outbox_enabled

        def resolved(value: bool) -> bool:
            self._public_job_catalog_outbox_enabled = value
            return value

        def invalid_boundary() -> NoReturn:
            raise RuntimeError(
                "Partial or drifted 0038 public-job catalog outbox; "
                "repair the schema and runtime grants before startup"
            )

        table = "public_job_catalog_events"
        trigger_name = "realtime_events_public_job_catalog"
        expected_columns = {
            "sequence_id",
            "event_id",
            "listing_id",
            "event_type",
            "public_status",
            "listing_version",
            "occurred_at",
        }

        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                table_sql = connection.scalar(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type='table' AND name=:table"
                    ),
                    {"table": table},
                )
                trigger_sql = connection.scalar(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type='trigger' AND name=:trigger"
                    ),
                    {"trigger": trigger_name},
                )
                alembic_managed = bool(
                    connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                            "WHERE type='table' AND name='alembic_version')"
                        )
                    )
                )
                revision_values = (
                    list(connection.scalars(text("SELECT version_num FROM alembic_version")))
                    if alembic_managed
                    else []
                )
                revision_has_0038 = bool(
                    len(revision_values) == 1
                    and _revision_descends_from(
                        str(revision_values[0]),
                        "0038_public_job_catalog_outbox",
                    )
                )
                if not revision_has_0038:
                    # BasicBase.metadata.create_all() intentionally has neither
                    # an Alembic marker nor migration-owned triggers. It remains
                    # a legacy test/development scaffold using the 0037 replay.
                    if (
                        table_sql is not None
                        and trigger_sql is None
                        and not alembic_managed
                        and self.settings.environment in {"development", "test"}
                    ):
                        return resolved(False)
                    if table_sql is not None or trigger_sql is not None:
                        invalid_boundary()
                    return resolved(False)
                if table_sql is None or trigger_sql is None:
                    invalid_boundary()

                column_rows = list(
                    connection.exec_driver_sql(
                        f"PRAGMA table_info('{table}')"
                    )
                )
                if (
                    {str(row[1]) for row in column_rows} != expected_columns
                    or [str(row[1]) for row in column_rows]
                    != [
                        "sequence_id",
                        "event_id",
                        "listing_id",
                        "event_type",
                        "public_status",
                        "listing_version",
                        "occurred_at",
                    ]
                    or [str(row[1]) for row in column_rows if int(row[5])]
                    != ["sequence_id"]
                    or any(not int(row[3]) for row in column_rows)
                ):
                    invalid_boundary()

                foreign_keys = {
                    (str(row[3]), str(row[2]), str(row[4]), str(row[6]).upper())
                    for row in connection.exec_driver_sql(
                        f"PRAGMA foreign_key_list('{table}')"
                    )
                }
                if foreign_keys != {
                    ("sequence_id", "realtime_events", "sequence_id", "RESTRICT"),
                    ("event_id", "realtime_events", "id", "RESTRICT"),
                }:
                    invalid_boundary()

                indexes: dict[tuple[str, ...], bool] = {}
                for index in connection.exec_driver_sql(
                    f"PRAGMA index_list('{table}')"
                ):
                    index_name = str(index[1])
                    columns = tuple(
                        str(item[2])
                        for item in connection.exec_driver_sql(
                            f"PRAGMA index_info('{index_name}')"
                        )
                    )
                    indexes[columns] = bool(index[2])
                if indexes != {
                    ("event_id",): True,
                    ("listing_id", "listing_version"): True,
                    ("listing_id",): False,
                }:
                    invalid_boundary()

                normalized_table = _compact_sql(str(table_sql))
                normalized_trigger = _compact_sql(str(trigger_sql))
                if not (
                    "constraintck_public_job_catalog_statuscheck"
                    "(public_statusin('open','paused','closed'))" in normalized_table
                    and "constraintck_public_job_catalog_event_typecheck"
                    "(event_typein('job.updated','job.status_changed'))"
                    in normalized_table
                    and "constraintck_public_job_catalog_versioncheck"
                    "(listing_version>0)" in normalized_table
                    and normalized_trigger.startswith(
                        "createtriggerrealtime_events_public_job_catalog"
                        "afterinsertonrealtime_eventswhen"
                    )
                    and "new.event_typein('job.updated','job.status_changed')"
                    in normalized_trigger
                    and "new.entity_type='job'" in normalized_trigger
                    and "insertintopublic_job_catalog_events" in normalized_trigger
                    and "job.published_atisnotnull" in normalized_trigger
                    and "job.statusin('open','paused','closed')" in normalized_trigger
                    and "(new.event_type='job.status_changed'orjob.status='open')"
                    in normalized_trigger
                ):
                    invalid_boundary()
                return resolved(True)

            presence = connection.execute(
                text(
                    "SELECT pg_catalog.to_regclass("
                    "'public.public_job_catalog_events')::pg_catalog.oid AS table_oid,"
                    "pg_catalog.to_regprocedure("
                    "'public.caresync_public_job_catalog_from_realtime()')"
                    "::pg_catalog.oid "
                    "AS function_oid,"
                    "(SELECT count(*) FROM pg_catalog.pg_trigger AS trigger_row "
                    "WHERE trigger_row.tgrelid=pg_catalog.to_regclass("
                    "'public.realtime_events') "
                    "AND trigger_row.tgname='realtime_events_public_job_catalog' "
                    "AND NOT trigger_row.tgisinternal) AS trigger_count"
                )
            ).one()
            all_objects_absent = bool(
                presence.table_oid is None
                and presence.function_oid is None
                and int(presence.trigger_count) == 0
            )
            try:
                revision_values = list(
                    connection.scalars(text("SELECT version_num FROM public.alembic_version"))
                )
            except SQLAlchemyError:
                invalid_boundary()
            revision_has_0038 = bool(
                len(revision_values) == 1
                and _revision_descends_from(
                    str(revision_values[0]),
                    "0038_public_job_catalog_outbox",
                )
            )
            if all_objects_absent:
                if revision_has_0038:
                    invalid_boundary()
                return resolved(False)
            if (
                presence.table_oid is None
                or presence.function_oid is None
                or int(presence.trigger_count) != 1
                or not revision_has_0038
            ):
                invalid_boundary()

            columns = list(
                connection.execute(
                    text(
                        "SELECT attribute_row.attname,"
                        "pg_catalog.format_type("
                        "attribute_row.atttypid,attribute_row.atttypmod) "
                        "AS data_type,attribute_row.attnotnull "
                        "FROM pg_catalog.pg_attribute AS attribute_row "
                        "WHERE attribute_row.attrelid=:table_oid "
                        "AND attribute_row.attnum>0 "
                        "AND NOT attribute_row.attisdropped "
                        "ORDER BY attribute_row.attnum"
                    ),
                    {"table_oid": presence.table_oid},
                )
            )
            expected_postgres_columns = [
                ("sequence_id", "integer", True),
                ("event_id", "uuid", True),
                ("listing_id", "uuid", True),
                ("event_type", "character varying(100)", True),
                ("public_status", "character varying(20)", True),
                ("listing_version", "integer", True),
                ("occurred_at", "timestamp with time zone", True),
            ]
            if [
                (str(row.attname), str(row.data_type), bool(row.attnotnull))
                for row in columns
            ] != expected_postgres_columns:
                invalid_boundary()

            constraints = {
                str(row.conname): (
                    str(row.contype),
                    _compact_sql(str(row.definition)),
                )
                for row in connection.execute(
                    text(
                        "SELECT constraint_row.conname,constraint_row.contype,"
                        "pg_catalog.pg_get_constraintdef(constraint_row.oid,true) "
                        "AS definition "
                        "FROM pg_catalog.pg_constraint AS constraint_row "
                        "WHERE constraint_row.conrelid=:table_oid"
                    ),
                    {"table_oid": presence.table_oid},
                )
            }
            expected_constraint_names = {
                "public_job_catalog_events_pkey",
                "public_job_catalog_events_sequence_id_fkey",
                "public_job_catalog_events_event_id_fkey",
                "uq_public_job_catalog_event_id",
                "uq_public_job_catalog_listing_version",
                "ck_public_job_catalog_status",
                "ck_public_job_catalog_event_type",
                "ck_public_job_catalog_version",
            }
            if set(constraints) != expected_constraint_names:
                invalid_boundary()
            constraint_markers = {
                "public_job_catalog_events_pkey": ("p", "primarykey(sequence_id)"),
                "public_job_catalog_events_sequence_id_fkey": (
                    "f",
                    "foreignkey(sequence_id)referencesrealtime_events(sequence_id)"
                    "ondeleterestrict",
                ),
                "public_job_catalog_events_event_id_fkey": (
                    "f",
                    "foreignkey(event_id)referencesrealtime_events(id)ondeleterestrict",
                ),
                "uq_public_job_catalog_event_id": ("u", "unique(event_id)"),
                "uq_public_job_catalog_listing_version": (
                    "u",
                    "unique(listing_id,listing_version)",
                ),
                "ck_public_job_catalog_status": (
                    "c",
                    "public_status",
                ),
                "ck_public_job_catalog_event_type": (
                    "c",
                    "event_type",
                ),
                "ck_public_job_catalog_version": (
                    "c",
                    "listing_version>0",
                ),
            }
            if not all(
                constraints[name][0] == expected_type
                and marker in constraints[name][1]
                for name, (expected_type, marker) in constraint_markers.items()
            ):
                invalid_boundary()
            status_check = constraints["ck_public_job_catalog_status"][1]
            event_check = constraints["ck_public_job_catalog_event_type"][1]
            if not (
                all(value in status_check for value in ("'open'", "'paused'", "'closed'"))
                and all(
                    value in event_check
                    for value in ("'job.updated'", "'job.status_changed'")
                )
            ):
                invalid_boundary()

            indexes = set(
                connection.scalars(
                    text(
                        "SELECT index_class.relname "
                        "FROM pg_catalog.pg_index AS index_row "
                        "JOIN pg_catalog.pg_class AS index_class "
                        "ON index_class.oid=index_row.indexrelid "
                        "WHERE index_row.indrelid=:table_oid"
                    ),
                    {"table_oid": presence.table_oid},
                )
            )
            if indexes != {
                "public_job_catalog_events_pkey",
                "uq_public_job_catalog_event_id",
                "uq_public_job_catalog_listing_version",
                "ix_public_job_catalog_events_listing_id",
            }:
                invalid_boundary()

            boundary = connection.execute(
                text(
                    "SELECT relation_row.relowner AS table_owner,"
                    "relation_row.relrowsecurity,relation_row.relforcerowsecurity,"
                    "owner_role_row.rolname AS owner_name,"
                    "procedure_row.proowner AS function_owner,"
                    "procedure_row.prosecdef,procedure_row.proconfig,"
                    "pg_catalog.pg_get_functiondef(procedure_row.oid) "
                    "AS function_definition,"
                    "NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "relation_row.relacl,pg_catalog.acldefault("
                    "'r',relation_row.relowner)"
                    ")) AS privilege WHERE privilege.grantee=0) AS table_public_none,"
                    "NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "relation_row.relacl,pg_catalog.acldefault("
                    "'r',relation_row.relowner)"
                    ")) AS privilege WHERE privilege.grantee NOT IN "
                    "(relation_row.relowner,COALESCE(runtime_role_row.oid,0::oid)) "
                    "OR (privilege.grantee=runtime_role_row.oid "
                    "AND privilege.privilege_type<>'SELECT')) AS table_acl_bounded,"
                    "NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure_row.proacl,pg_catalog.acldefault("
                    "'f',procedure_row.proowner)"
                    ")) AS privilege WHERE privilege.grantee=0 "
                    "AND privilege.privilege_type='EXECUTE') AS function_public_none,"
                    "NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure_row.proacl,pg_catalog.acldefault("
                    "'f',procedure_row.proowner)"
                    ")) AS privilege WHERE privilege.grantee<>procedure_row.proowner "
                    "OR privilege.privilege_type<>'EXECUTE') AS function_acl_bounded,"
                    "NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class AS version_relation "
                    "CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE("
                    "version_relation.relacl,pg_catalog.acldefault("
                    "'r',version_relation.relowner))) AS privilege "
                    "WHERE version_relation.oid=pg_catalog.to_regclass("
                    "'public.alembic_version') AND privilege.grantee=0) "
                    "AS version_public_none,"
                    "NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class AS version_relation "
                    "CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE("
                    "version_relation.relacl,pg_catalog.acldefault("
                    "'r',version_relation.relowner))) AS privilege "
                    "WHERE version_relation.oid=pg_catalog.to_regclass("
                    "'public.alembic_version') AND (privilege.grantee NOT IN "
                    "(version_relation.relowner,"
                    "COALESCE(runtime_role_row.oid,0::oid)) "
                    "OR (privilege.grantee=runtime_role_row.oid "
                    "AND privilege.privilege_type<>'SELECT'))) "
                    "AS version_acl_bounded,"
                    "COALESCE(pg_catalog.has_table_privilege("
                    "runtime_role_row.rolname,relation_row.oid,'SELECT'),false) "
                    "AS runtime_select,"
                    "COALESCE(pg_catalog.has_table_privilege("
                    "runtime_role_row.rolname,relation_row.oid,"
                    "'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'),false) "
                    "AS runtime_mutation,"
                    "COALESCE(pg_catalog.has_table_privilege("
                    "runtime_role_row.rolname,'public.alembic_version','SELECT'),false) "
                    "AS runtime_version_select,"
                    "COALESCE(pg_catalog.has_table_privilege("
                    "runtime_role_row.rolname,'public.alembic_version',"
                    "'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'),false) "
                    "AS runtime_version_mutation,"
                    "COALESCE(pg_catalog.has_function_privilege("
                    "runtime_role_row.rolname,procedure_row.oid,'EXECUTE'),false) "
                    "AS runtime_execute "
                    "FROM pg_catalog.pg_class AS relation_row "
                    "JOIN pg_catalog.pg_roles AS owner_role_row "
                    "ON owner_role_row.oid=relation_row.relowner "
                    "JOIN pg_catalog.pg_proc AS procedure_row "
                    "ON procedure_row.oid=:function_oid "
                    "LEFT JOIN pg_catalog.pg_roles AS runtime_role_row "
                    "ON runtime_role_row.rolname='caresync_basic_app' "
                    "WHERE relation_row.oid=:table_oid"
                ),
                {
                    "table_oid": presence.table_oid,
                    "function_oid": presence.function_oid,
                },
            ).one_or_none()
            if boundary is None:
                invalid_boundary()
            function = _compact_sql(str(boundary.function_definition))
            if not (
                boundary.table_owner == boundary.function_owner
                and boundary.owner_name != "caresync_basic_app"
                and boundary.relrowsecurity
                and not boundary.relforcerowsecurity
                and boundary.prosecdef
                and list(boundary.proconfig or []) == ["search_path=pg_catalog"]
                and boundary.table_public_none
                and boundary.table_acl_bounded
                and boundary.function_public_none
                and boundary.function_acl_bounded
                and boundary.version_public_none
                and boundary.version_acl_bounded
                and boundary.runtime_select
                and not boundary.runtime_mutation
                and boundary.runtime_version_select
                and not boundary.runtime_version_mutation
                and not boundary.runtime_execute
                and "insertintopublic.public_job_catalog_events" in function
                and "frompublic.ats_jobsasjob" in function
                and "new.event_typein('job.updated','job.status_changed')" in function
                and "job.published_atisnotnull" in function
                and "job.statusin('open','paused','closed')" in function
                and "(new.event_type='job.status_changed'orjob.status='open')" in function
            ):
                invalid_boundary()

            policies = list(
                connection.execute(
                    text(
                        "SELECT policy_row.polname,policy_row.polcmd,"
                        "policy_row.polpermissive,policy_row.polroles,"
                        "pg_catalog.pg_get_expr("
                        "policy_row.polqual,policy_row.polrelid,true) "
                        "AS using_expression,policy_row.polwithcheck "
                        "FROM pg_catalog.pg_policy AS policy_row "
                        "WHERE policy_row.polrelid=:table_oid"
                    ),
                    {"table_oid": presence.table_oid},
                )
            )
            if len(policies) != 1:
                invalid_boundary()
            policy = policies[0]
            if not (
                policy.polname == "public_job_catalog_events_public_read"
                and policy.polcmd == "r"
                and policy.polpermissive
                and tuple(int(role) for role in policy.polroles) == (0,)
                and _compact_sql(str(policy.using_expression)) == "true"
                and policy.polwithcheck is None
            ):
                invalid_boundary()

            trigger = connection.execute(
                text(
                    "SELECT trigger_row.tgenabled,"
                    "pg_catalog.pg_get_triggerdef(trigger_row.oid,true) AS definition "
                    "FROM pg_catalog.pg_trigger AS trigger_row "
                    "WHERE trigger_row.tgrelid=pg_catalog.to_regclass("
                    "'public.realtime_events') "
                    "AND trigger_row.tgname='realtime_events_public_job_catalog' "
                    "AND trigger_row.tgfoid=:function_oid "
                    "AND NOT trigger_row.tgisinternal"
                ),
                {"function_oid": presence.function_oid},
            ).one_or_none()
            trigger_definition = _compact_sql(str(trigger.definition if trigger else ""))
            if not (
                trigger is not None
                and trigger.tgenabled == "O"
                and trigger_definition.startswith(
                    "createtriggerrealtime_events_public_job_catalog"
                    "afterinsertonrealtime_eventsforeachrowexecute"
                )
                and trigger_definition.endswith(
                    "caresync_public_job_catalog_from_realtime()"
                )
            ):
                invalid_boundary()
            return resolved(True)

    def has_staff_screening_pathways(self) -> bool:
        """Fail closed unless the complete additive 0030 screening boundary exists."""

        def invalid_boundary() -> NoReturn:
            raise RuntimeError(
                "Partial or drifted 0030 staff-screening boundary; repair the schema before startup"
            )

        tables = {
            "ats_job_screening_terms",
            "marketplace_job_screening_terms",
            "marketplace_screening_profiles",
            "ats_application_screening_snapshots",
            "ats_offer_screening_terms",
            "staff_screening_documents",
            "staff_screening_document_versions",
            "staff_screening_candidate_confirmations",
            "staff_screening_application_shares",
            "staff_screening_employer_reviews",
            "ats_offer_acknowledgments",
        }
        required_columns = {
            "marketplace_screening_profiles": {"pathway", "version", "candidate_provided"},
            "staff_screening_document_versions": {
                "declared_coverage",
                "storage_reference",
                "ciphertext_sha256",
            },
            "ats_application_screening_snapshots": {
                "screening_profile_version",
                "job_terms_version",
                "driver_declaration_snapshot",
                "job_terms_snapshot",
            },
            "staff_screening_candidate_confirmations": {
                "document_version_id",
                "subject_name",
                "account_name_snapshot",
                "subject_name_match",
                "mismatch_resolution",
                "candidate_confirmed_at",
            },
            "staff_screening_application_shares": {
                "application_id",
                "document_version_id",
                "screening_profile_version",
                "revoked_at",
            },
            "staff_screening_employer_reviews": {
                "application_id",
                "share_id",
                "requirement_class",
                "review_sequence",
            },
            "ats_offer_screening_terms": {"offer_version", "terms_digest"},
            "ats_offer_acknowledgments": {
                "offer_version",
                "terms_digest",
                "driver_terms_acknowledged",
            },
        }
        immutable_tables = {
            "staff_screening_document_versions",
            "staff_screening_candidate_confirmations",
            "staff_screening_employer_reviews",
            "ats_offer_screening_terms",
            "ats_offer_acknowledgments",
        }
        sqlite_trigger_fragments = {
            "ats_job_screening_marketplace_insert": ("marketplace_job_screening_terms",),
            "ats_job_screening_marketplace_update": ("marketplace_job_screening_terms",),
            "marketplace_jobs_screening_projection": ("ats_job_screening_terms",),
            "staff_screening_versions_coverage_guard": ("json_valid", "distinct value"),
            "ats_application_screening_snapshots_json_guard": (
                "json_valid",
                "count(distinct key)",
            ),
            "ats_application_screening_snapshots_insert_guard": (
                "job_terms_version",
                "screening_profile_version",
            ),
            "ats_application_screening_snapshots_immutable_update": ("immutable",),
            "ats_application_screening_snapshots_immutable_delete": ("immutable",),
            "staff_screening_shares_insert_guard": ("screening_profile_version",),
            "staff_screening_documents_guard": ("candidate_confirmations",),
            "staff_screening_reviews_insert_guard": ("revoked_at is null",),
            "ats_offer_screening_terms_insert_guard": (
                "application_screening_snapshots",
                "vehicle_access",
            ),
            "ats_offers_0030_terms_guard": ("expires_at", "contractual terms"),
            "staff_screening_shares_guard_update": ("one-way revocation",),
            "staff_screening_shares_guard_delete": ("cannot be deleted",),
            "ats_offer_acknowledgments_guard": (
                "driver_terms_acknowledged",
                "terms_digest",
            ),
        }
        for table in immutable_tables:
            for operation in ("update", "delete"):
                sqlite_trigger_fragments[f"{table}_immutable_{operation}"] = (
                    "immutable screening fact",
                )

        postgres_trigger_functions = {
            ("ats_job_screening_marketplace", "ats_job_screening_terms"): (
                "sync_marketplace_job_screening_from_terms",
            ),
            ("marketplace_jobs_screening_projection", "marketplace_jobs"): (
                "sync_marketplace_job_screening_from_listing",
            ),
            ("staff_screening_versions_coverage_guard", "staff_screening_document_versions"): (
                "caresync_0030_coverage_guard",
            ),
            ("ats_application_screening_snapshots_guard", "ats_application_screening_snapshots"): (
                "caresync_0030_snapshot_guard",
            ),
            ("staff_screening_shares_insert_guard", "staff_screening_application_shares"): (
                "caresync_0030_share_insert_guard",
            ),
            ("staff_screening_reviews_insert_guard", "staff_screening_employer_reviews"): (
                "caresync_0030_review_insert_guard",
            ),
            ("staff_screening_documents_guard", "staff_screening_documents"): (
                "caresync_0030_document_guard",
            ),
            ("ats_offer_screening_terms_insert_guard", "ats_offer_screening_terms"): (
                "caresync_0030_offer_terms_insert_guard",
            ),
            ("ats_offers_0030_terms_guard", "ats_offers"): ("caresync_0030_offer_terms_guard",),
            ("staff_screening_shares_guard", "staff_screening_application_shares"): (
                "caresync_0030_share_guard",
            ),
            ("ats_offer_acknowledgments_guard", "ats_offer_acknowledgments"): (
                "caresync_0030_offer_ack_guard",
            ),
        }
        for table in immutable_tables:
            postgres_trigger_functions[(f"{table}_immutable", table)] = (
                "caresync_0030_immutable_fact",
            )

        postgres_function_fragments = {
            "sync_marketplace_job_screening_from_terms()": ("marketplace_job_screening_terms",),
            "sync_marketplace_job_screening_from_listing()": ("ats_job_screening_terms",),
            "caresync_0030_immutable_fact()": ("immutable screening fact",),
            "caresync_0030_coverage_guard()": ("declared coverage",),
            "caresync_0030_snapshot_guard()": ("job_terms_version",),
            "caresync_0030_share_insert_guard()": ("screening_profile_version",),
            "caresync_0030_review_insert_guard()": ("active shared requirement",),
            "caresync_0030_document_guard()": ("current screening version",),
            "caresync_0030_offer_terms_insert_guard()": ("application disclosure",),
            "caresync_0030_offer_terms_guard()": ("contractual terms",),
            "caresync_0030_share_guard()": ("one-way revocation",),
            "caresync_0030_offer_ack_guard()": ("driver_terms_acknowledged",),
        }
        postgres_policy_fragments = {
            ("ats_job_screening_terms", "ats_job_screening_terms_read"): (
                "ats:read",
                "marketplace_jobs",
                "listing_id",
                "ats_job_screening_terms.job_id",
            ),
            ("ats_job_screening_terms", "ats_job_screening_terms_manage"): ("ats:manage",),
            ("ats_offer_screening_terms", "ats_offer_screening_terms_select"): (
                "claimed_user_id",
                "ats:manage",
            ),
            (
                "ats_offer_screening_terms",
                "ats_offer_screening_terms_manage_insert",
            ): ("ats:manage",),
            (
                "ats_application_screening_snapshots",
                "ats_application_screening_snapshots_select",
            ): ("candidate_user_id", "ats:manage"),
            (
                "ats_application_screening_snapshots",
                "ats_application_screening_snapshots_candidate_insert",
            ): ("candidate_user_id",),
            ("marketplace_screening_profiles", "marketplace_screening_profiles_owner"): (
                "user_id",
            ),
            (
                "marketplace_screening_profiles",
                "marketplace_screening_profiles_employer_select",
            ): ("discoverable", "ats:manage"),
            ("staff_screening_documents", "staff_screening_documents_owner"): ("user_id",),
            (
                "staff_screening_document_versions",
                "staff_screening_document_versions_owner",
            ): ("user_id",),
            (
                "staff_screening_candidate_confirmations",
                "staff_screening_candidate_confirmations_owner",
            ): ("user_id",),
            (
                "staff_screening_document_versions",
                "staff_screening_versions_shared_select",
            ): ("revoked_at", "ats:manage"),
            (
                "staff_screening_candidate_confirmations",
                "staff_screening_confirmations_shared_select",
            ): ("revoked_at", "ats:manage"),
            (
                "staff_screening_documents",
                "staff_screening_documents_shared_select",
            ): ("revoked_at", "ats:manage"),
            (
                "staff_screening_documents",
                "staff_screening_documents_employer_lock",
            ): ("revoked_at", "ats:manage", "false"),
            (
                "staff_screening_application_shares",
                "staff_screening_shares_owner",
            ): ("candidate_user_id",),
            (
                "staff_screening_application_shares",
                "staff_screening_shares_employer_select",
            ): ("ats:manage",),
            (
                "staff_screening_application_shares",
                "staff_screening_shares_employer_lock",
            ): ("organization_id", "ats:manage", "false"),
            (
                "staff_screening_employer_reviews",
                "staff_screening_reviews_employer_select",
            ): ("ats:manage",),
            (
                "staff_screening_employer_reviews",
                "staff_screening_reviews_employer_insert",
            ): ("reviewer_user_id", "ats:manage"),
            (
                "staff_screening_employer_reviews",
                "staff_screening_reviews_candidate_select",
            ): ("candidate_user_id",),
            ("ats_offer_acknowledgments", "ats_offer_acknowledgments_select"): (
                "candidate_user_id",
                "ats:manage",
            ),
            (
                "ats_offer_acknowledgments",
                "ats_offer_acknowledgments_candidate_insert",
            ): ("candidate_user_id",),
        }
        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                found = set(
                    connection.execute(
                        text(
                            "SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name IN (" + ",".join(f"'{name}'" for name in sorted(tables)) + ")"
                        )
                    ).scalars()
                )
                if not found:
                    orphaned_trigger = connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                            "WHERE type='trigger' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                            + "))"
                        )
                    )
                    if orphaned_trigger:
                        invalid_boundary()
                    return False
                if found != tables:
                    invalid_boundary()
                for table, expected in required_columns.items():
                    columns = {
                        str(row[1])
                        for row in connection.exec_driver_sql(f"PRAGMA table_info('{table}')")
                    }
                    if not expected.issubset(columns):
                        invalid_boundary()
                # A number of isolated SQLite test/development fixtures still
                # use ``BasicBase.metadata.create_all``.  That creates the ORM
                # sidecar tables but cannot create the enforcement triggers
                # owned by Alembic revision 0030.  Such an unversioned metadata
                # scaffold is a legacy boundary with the feature disabled, not
                # evidence that the migration was attempted.
                #
                # Keep this escape hatch deliberately narrow: production and
                # every Alembic-managed database remain fail-closed, partial
                # table sets already failed above, and any 0030 trigger below
                # is treated as evidence of a partial migration rather than a
                # metadata-only scaffold.
                alembic_managed = bool(
                    connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                            "WHERE type='table' AND name='alembic_version')"
                        )
                    )
                )
                screening_trigger_count = int(
                    connection.scalar(
                        text(
                            "SELECT COUNT(*) FROM sqlite_master "
                            "WHERE type='trigger' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                            + ")"
                        )
                    )
                    or 0
                )
                if (
                    not alembic_managed
                    and screening_trigger_count == 0
                    and self.settings.environment in {"development", "test"}
                ):
                    return False
                trigger_rows = {
                    str(row.name): str(row.sql or "").lower()
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                            + ")"
                        )
                    )
                }
                if set(trigger_rows) != set(sqlite_trigger_fragments):
                    invalid_boundary()
                if not all(
                    all(fragment in trigger_rows[name] for fragment in fragments)
                    for name, fragments in sqlite_trigger_fragments.items()
                ):
                    invalid_boundary()
                return True

            found = set(
                connection.execute(
                    text(
                        "SELECT name FROM unnest(CAST(:names AS text[])) AS name "
                        "WHERE pg_catalog.to_regclass('public.' || name) IS NOT NULL"
                    ),
                    {"names": sorted(tables)},
                ).scalars()
            )
            if not found:
                orphaned = connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM unnest(CAST(:signatures AS text[])) "
                        "AS expected(signature) WHERE pg_catalog.to_regprocedure("
                        "'public.' || expected.signature) IS NOT NULL) OR EXISTS("
                        "SELECT 1 FROM pg_catalog.pg_trigger AS trigger "
                        "WHERE NOT trigger.tgisinternal "
                        "AND trigger.tgname=ANY(CAST(:triggers AS text[])))"
                    ),
                    {
                        "signatures": sorted(postgres_function_fragments),
                        "triggers": sorted({name for name, _table in postgres_trigger_functions}),
                    },
                )
                if orphaned:
                    invalid_boundary()
                return False
            if found != tables:
                invalid_boundary()
            for table, expected in required_columns.items():
                columns = set(
                    connection.execute(
                        text(
                            "SELECT attribute.attname FROM pg_catalog.pg_attribute AS attribute "
                            "WHERE attribute.attrelid=pg_catalog.to_regclass(:table) "
                            "AND attribute.attnum>0 AND NOT attribute.attisdropped"
                        ),
                        {"table": f"public.{table}"},
                    ).scalars()
                )
                if not expected.issubset(columns):
                    invalid_boundary()
            hardened = set(
                connection.execute(
                    text(
                        "SELECT relation.relname FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' AND relation.relname=ANY(:names) "
                        "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                    ),
                    {"names": sorted(tables - {"marketplace_job_screening_terms"})},
                ).scalars()
            )
            if hardened != tables - {"marketplace_job_screening_terms"}:
                invalid_boundary()
            trigger_rows = {
                (str(row.tgname), str(row.relname)): str(row.proname)
                for row in connection.execute(
                    text(
                        "SELECT trigger.tgname,relation.relname,procedure.proname "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                        "WHERE namespace.nspname='public' AND NOT trigger.tgisinternal "
                        "AND trigger.tgenabled<>'D' "
                        "AND trigger.tgname=ANY(CAST(:names AS text[]))"
                    ),
                    {"names": sorted({name for name, _table in postgres_trigger_functions})},
                )
            }
            if set(trigger_rows) != set(postgres_trigger_functions):
                invalid_boundary()
            if not all(
                all(fragment in trigger_rows[key] for fragment in fragments)
                for key, fragments in postgres_trigger_functions.items()
            ):
                invalid_boundary()

            function_rows = {
                str(row.signature): row
                for row in connection.execute(
                    text(
                        "SELECT expected.signature,procedure.oid,procedure.provolatile,"
                        "procedure.prosecdef,procedure.proconfig,"
                        "pg_catalog.pg_get_functiondef(procedure.oid) AS definition,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner))) "
                        "AS privilege WHERE privilege.grantee=0 "
                        "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                        "CASE WHEN EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
                        "WHERE rolname='caresync_basic_app') THEN COALESCE("
                        "pg_catalog.has_function_privilege("
                        "'caresync_basic_app',procedure.oid,'EXECUTE'),false) ELSE false END "
                        "AS app_execute FROM unnest(CAST(:signatures AS text[])) "
                        "AS expected(signature) LEFT JOIN pg_catalog.pg_proc AS procedure "
                        "ON procedure.oid=pg_catalog.to_regprocedure("
                        "'public.' || expected.signature)"
                    ),
                    {"signatures": sorted(postgres_function_fragments)},
                )
            }
            if set(function_rows) != set(postgres_function_fragments):
                invalid_boundary()
            for signature, fragments in postgres_function_fragments.items():
                row = function_rows[signature]
                config = set(row.proconfig or [])
                definition = str(row.definition or "").lower()
                if (
                    row.oid is None
                    or str(row.provolatile) != "v"
                    or bool(row.prosecdef)
                    or config != {"search_path=pg_catalog, public"}
                    or bool(row.public_execute)
                    or bool(row.app_execute)
                    or not all(fragment in definition for fragment in fragments)
                ):
                    invalid_boundary()

            policy_rows = {
                (str(row.relname), str(row.polname)): (
                    f"{row.using_expression or ''} {row.check_expression or ''}".lower()
                )
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,policy.polname,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                        "AS using_expression,"
                        "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                        "AS check_expression FROM pg_catalog.pg_policy AS policy "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=policy.polrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:tables AS text[]))"
                    ),
                    {"tables": sorted(tables - {"marketplace_job_screening_terms"})},
                )
            }
            if set(policy_rows) != set(postgres_policy_fragments):
                invalid_boundary()
            if not all(
                all(fragment in policy_rows[key] for fragment in fragments)
                for key, fragments in postgres_policy_fragments.items()
            ):
                invalid_boundary()
            return True

    def has_driver_vehicle_registry(self) -> bool:
        """Fail closed unless the complete read-only 0031 registry boundary exists."""

        def invalid_boundary() -> NoReturn:
            raise RuntimeError(
                "Partial or drifted 0031 driver/vehicle registry; repair the schema before startup"
            )

        tables = {
            "staff_driver_capability_versions",
            "staff_driver_qualification_versions",
            "staff_driver_authorization_decisions",
            "staff_driver_readiness_decisions",
            "transport_vehicles",
            "transport_vehicle_versions",
            "transport_vehicle_evidence_versions",
        }
        required_columns = {
            "staff_driver_capability_versions": {
                "membership_id",
                "version_number",
                "source_kind",
                "effective_at",
            },
            "staff_driver_qualification_versions": {
                "qualification_type",
                "version_number",
                "source_screening_document_version_id",
            },
            "staff_driver_authorization_decisions": {
                "capability_version_id",
                "qualification_version_ids",
                "operational_driver_ready",
                "dispatch_authorized",
            },
            "transport_vehicles": {"owner_kind", "staff_owner_membership_id", "retired_at"},
            "transport_vehicle_versions": {
                "vehicle_id",
                "version_number",
                "child_passenger_capacity",
            },
            "transport_vehicle_evidence_versions": {
                "vehicle_version_id",
                "evidence_type",
                "storage_reference",
                "ciphertext_sha256",
            },
            "staff_driver_readiness_decisions": {
                "authorization_decision_id",
                "vehicle_evidence_version_ids",
                "operational_driver_ready",
                "dispatch_authorized",
            },
        }
        immutable_tables = tables - {"transport_vehicles"}
        sqlite_trigger_fragments = {
            "staff_driver_capability_insert_guard": ("screening_profile", "version_number"),
            "staff_driver_qualification_insert_guard": (
                "screening_document_version_id",
                "version_number",
            ),
            "staff_driver_authorization_insert_guard": (
                "qualification_version_ids",
                "driver_licence",
                "membership.user_id=new.reviewed_by_user_id",
                "authorization_valid_until",
            ),
            "transport_vehicles_guard_update": ("one-way retirement",),
            "transport_vehicles_guard_delete": ("cannot be deleted",),
            "transport_vehicle_versions_insert_guard": ("version_number", "retired_at"),
            "transport_vehicle_versions_plate_guard": (
                "transport_vehicle_plate_conflict",
                "with recursive normalized",
            ),
            "transport_vehicle_evidence_insert_guard": (
                "evidence_type",
                "version_number",
            ),
            "staff_driver_readiness_insert_guard": (
                "authorization_decision_id",
                "vehicle_evidence_version_ids",
            ),
        }
        for table in immutable_tables:
            for operation in ("update", "delete"):
                sqlite_trigger_fragments[f"{table}_immutable_{operation}"] = (
                    "immutable driver/vehicle fact",
                )

        postgres_trigger_functions = {
            ("staff_driver_capability_insert_guard", "staff_driver_capability_versions"): (
                "caresync_0031_capability_guard",
            ),
            (
                "staff_driver_qualification_insert_guard",
                "staff_driver_qualification_versions",
            ): ("caresync_0031_qualification_guard",),
            (
                "staff_driver_authorization_insert_guard",
                "staff_driver_authorization_decisions",
            ): ("caresync_0031_authorization_guard",),
            ("transport_vehicles_guard", "transport_vehicles"): ("caresync_0031_vehicle_guard",),
            ("transport_vehicle_versions_insert_guard", "transport_vehicle_versions"): (
                "caresync_0031_vehicle_version_guard",
            ),
            (
                "transport_vehicle_evidence_insert_guard",
                "transport_vehicle_evidence_versions",
            ): ("caresync_0031_vehicle_evidence_guard",),
            ("staff_driver_readiness_insert_guard", "staff_driver_readiness_decisions"): (
                "caresync_0031_readiness_guard",
            ),
        }
        for table in immutable_tables:
            postgres_trigger_functions[(f"{table}_immutable", table)] = (
                "caresync_0031_immutable_fact",
            )
        postgres_function_fragments = {
            "caresync_0031_immutable_fact()": ("immutable driver/vehicle fact",),
            "caresync_0031_capability_guard()": ("screening profile mismatch",),
            "caresync_0031_qualification_guard()": ("evidence owner mismatch",),
            "caresync_0031_authorization_guard()": (
                "qualification_version_ids",
                "verified driver licence",
                "independent reviewer",
                "authorization_valid_until",
            ),
            "caresync_0031_vehicle_guard()": ("one-way retirement",),
            "caresync_0031_vehicle_version_guard()": (
                "vehicle version sequence",
                "transport_vehicle_plate_conflict",
                "pg_advisory_xact_lock",
            ),
            "caresync_0031_vehicle_evidence_guard()": ("vehicle evidence version sequence",),
            "caresync_0031_readiness_guard()": (
                "authorization_decision_id",
                "vehicle evidence mismatch",
            ),
        }
        postgres_policy_fragments = {
            (table, f"{table}_select"): ("transport:read", "transport:manage") for table in tables
        }
        postgres_policy_fragments[("transport_vehicles", "transport_vehicles_select")] += (
            "staff_personal",
            "staff_owner_membership_id",
        )
        postgres_policy_fragments[
            ("transport_vehicle_versions", "transport_vehicle_versions_select")
        ] += ("staff_personal", "staff_owner_membership_id")
        postgres_policy_fragments[
            (
                "transport_vehicle_evidence_versions",
                "transport_vehicle_evidence_versions_select",
            )
        ] += ("staff_personal", "staff_owner_membership_id")

        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                found = set(
                    connection.execute(
                        text(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(tables))
                            + ")"
                        )
                    ).scalars()
                )
                if not found:
                    orphaned = connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                            "WHERE type='trigger' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                            + "))"
                        )
                    )
                    if orphaned:
                        invalid_boundary()
                    return False
                if found != tables:
                    invalid_boundary()
                for table, expected in required_columns.items():
                    columns = {
                        str(row[1])
                        for row in connection.exec_driver_sql(f"PRAGMA table_info('{table}')")
                    }
                    if not expected.issubset(columns):
                        invalid_boundary()
                alembic_managed = bool(
                    connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                            "WHERE type='table' AND name='alembic_version')"
                        )
                    )
                )
                registry_trigger_count = int(
                    connection.scalar(
                        text(
                            "SELECT COUNT(*) FROM sqlite_master "
                            "WHERE type='trigger' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                            + ")"
                        )
                    )
                    or 0
                )
                if (
                    not alembic_managed
                    and registry_trigger_count == 0
                    and self.settings.environment in {"development", "test"}
                ):
                    return False
                trigger_rows = {
                    str(row.name): str(row.sql or "").lower()
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master "
                            "WHERE type='trigger' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                            + ")"
                        )
                    )
                }
                if set(trigger_rows) != set(sqlite_trigger_fragments) or not all(
                    all(fragment in trigger_rows[name] for fragment in fragments)
                    for name, fragments in sqlite_trigger_fragments.items()
                ):
                    invalid_boundary()
                return True

            found = set(
                connection.execute(
                    text(
                        "SELECT name FROM unnest(CAST(:names AS text[])) AS name "
                        "WHERE pg_catalog.to_regclass('public.' || name) IS NOT NULL"
                    ),
                    {"names": sorted(tables)},
                ).scalars()
            )
            if not found:
                orphaned = connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM unnest(CAST(:signatures AS text[])) "
                        "AS expected(signature) WHERE pg_catalog.to_regprocedure("
                        "'public.' || expected.signature) IS NOT NULL) OR EXISTS("
                        "SELECT 1 FROM pg_catalog.pg_trigger AS trigger "
                        "WHERE NOT trigger.tgisinternal "
                        "AND trigger.tgname=ANY(CAST(:triggers AS text[])))"
                    ),
                    {
                        "signatures": sorted(postgres_function_fragments),
                        "triggers": sorted({name for name, _ in postgres_trigger_functions}),
                    },
                )
                if orphaned:
                    invalid_boundary()
                return False
            if found != tables:
                invalid_boundary()
            for table, expected in required_columns.items():
                columns = set(
                    connection.execute(
                        text(
                            "SELECT attribute.attname FROM pg_catalog.pg_attribute AS attribute "
                            "WHERE attribute.attrelid=pg_catalog.to_regclass(:table) "
                            "AND attribute.attnum>0 AND NOT attribute.attisdropped"
                        ),
                        {"table": f"public.{table}"},
                    ).scalars()
                )
                if not expected.issubset(columns):
                    invalid_boundary()
            hardened = set(
                connection.execute(
                    text(
                        "SELECT relation.relname FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' AND relation.relname=ANY(:names) "
                        "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                    ),
                    {"names": sorted(tables)},
                ).scalars()
            )
            if hardened != tables:
                invalid_boundary()
            trigger_rows = {
                (str(row.tgname), str(row.relname)): str(row.proname)
                for row in connection.execute(
                    text(
                        "SELECT trigger.tgname,relation.relname,procedure.proname "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                        "WHERE namespace.nspname='public' AND NOT trigger.tgisinternal "
                        "AND trigger.tgenabled<>'D' "
                        "AND trigger.tgname=ANY(CAST(:names AS text[]))"
                    ),
                    {"names": sorted({name for name, _ in postgres_trigger_functions})},
                )
            }
            if set(trigger_rows) != set(postgres_trigger_functions) or not all(
                all(fragment in trigger_rows[key] for fragment in fragments)
                for key, fragments in postgres_trigger_functions.items()
            ):
                invalid_boundary()
            function_rows = {
                str(row.signature): row
                for row in connection.execute(
                    text(
                        "SELECT expected.signature,procedure.oid,procedure.provolatile,"
                        "procedure.prosecdef,procedure.proconfig,"
                        "pg_catalog.pg_get_functiondef(procedure.oid) AS definition,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner))) "
                        "AS privilege WHERE privilege.grantee=0 "
                        "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                        "CASE WHEN EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
                        "WHERE rolname='caresync_basic_app') THEN COALESCE("
                        "pg_catalog.has_function_privilege("
                        "'caresync_basic_app',procedure.oid,'EXECUTE'),false) ELSE false END "
                        "AS app_execute FROM unnest(CAST(:signatures AS text[])) "
                        "AS expected(signature) LEFT JOIN pg_catalog.pg_proc AS procedure "
                        "ON procedure.oid=pg_catalog.to_regprocedure("
                        "'public.' || expected.signature)"
                    ),
                    {"signatures": sorted(postgres_function_fragments)},
                )
            }
            if set(function_rows) != set(postgres_function_fragments):
                invalid_boundary()
            for signature, fragments in postgres_function_fragments.items():
                row = function_rows[signature]
                definition = str(row.definition or "").lower()
                if (
                    row.oid is None
                    or str(row.provolatile) != "v"
                    or bool(row.prosecdef)
                    or set(row.proconfig or []) != {"search_path=pg_catalog, public"}
                    or bool(row.public_execute)
                    or bool(row.app_execute)
                    or not all(fragment in definition for fragment in fragments)
                ):
                    invalid_boundary()
            policy_rows = {
                (str(row.relname), str(row.polname)): (
                    f"{row.using_expression or ''} {row.check_expression or ''}".lower()
                )
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,policy.polname,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                        "AS using_expression,"
                        "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                        "AS check_expression FROM pg_catalog.pg_policy AS policy "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=policy.polrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:tables AS text[])) "
                        "AND policy.polname NOT LIKE '%\\_0032\\_writer' ESCAPE '\\'"
                    ),
                    {"tables": sorted(tables)},
                )
            }
            if set(policy_rows) != set(postgres_policy_fragments) or not all(
                all(fragment in policy_rows[key] for fragment in fragments)
                for key, fragments in postgres_policy_fragments.items()
            ):
                invalid_boundary()
            return True

    def has_billing_ledger(self) -> bool:
        """Fail closed unless the complete synthetic-only 0033 ledger is certified."""

        def invalid_boundary() -> NoReturn:
            raise RuntimeError(
                "Partial or drifted 0033 billing ledger; repair the schema before startup"
            )

        tables = {
            "billing_sandbox_source_attestations",
            "billing_accounts",
            "billing_account_payer_versions",
            "billing_rate_plans",
            "billing_rate_plan_versions",
            "billing_agreements",
            "billing_agreement_versions",
            "billing_invoices",
            "billing_invoice_lines",
            "billing_payments",
            "billing_allocations",
            "billing_credits",
            "billing_journal_entries",
            "billing_journal_lines",
            "billing_reversals",
            "billing_command_preparations",
            "billing_command_terminals",
            "billing_command_receipts",
            "billing_command_claims",
        }
        backup_table = "billing_0033_role_permission_backups"
        required_columns = {
            "billing_sandbox_source_attestations": {
                "source_type",
                "source_id",
                "marker",
                "reason_code",
                "attested_by_user_id",
            },
            "billing_accounts": {
                "family_id",
                "payer_guardian_id",
                "account_number",
                "opened_by_user_id",
            },
            "billing_account_payer_versions": {
                "billing_account_id",
                "payer_guardian_id",
                "version_number",
            },
            "billing_rate_plans": {"program_type", "charge_kind", "facility_id", "program_id"},
            "billing_rate_plan_versions": {
                "billing_unit",
                "unit_amount_minor",
                "tax_rate_basis_points",
                "effective_from",
            },
            "billing_agreements": {
                "billing_account_id",
                "child_id",
                "enrollment_id",
                "facility_id",
            },
            "billing_agreement_versions": {
                "rate_plan_version_id",
                "billing_frequency",
                "family_amount_minor_per_unit",
                "funding_amount_minor_per_unit",
                "review_status",
            },
            "billing_invoices": {
                "invoice_number",
                "billing_account_payer_version_id",
                "payer_guardian_id",
                "service_period_start",
                "service_period_end",
                "total_minor",
            },
            "billing_invoice_lines": {
                "agreement_version_id",
                "quantity",
                "gross_subtotal_minor",
                "total_minor",
            },
            "billing_payments": {
                "payer_guardian_id",
                "payer_name_snapshot",
                "amount_minor",
                "received_at",
            },
            "billing_allocations": {"payment_id", "invoice_id", "amount_minor"},
            "billing_credits": {"invoice_id", "amount_minor", "reason_code"},
            "billing_journal_entries": {
                "client_operation_id",
                "request_hash",
                "book_sequence",
                "source_type",
                "source_id",
                "line_count",
                "total_debit_minor",
            },
            "billing_journal_lines": {
                "journal_entry_id",
                "line_number",
                "direction",
                "amount_minor",
            },
            "billing_reversals": {"original_journal_entry_id", "reversing_journal_entry_id"},
            "billing_command_preparations": {
                "actor_user_id",
                "client_operation_id",
                "command_type",
                "target_scope",
                "request_hash",
            },
            "billing_command_terminals": {
                "actor_user_id",
                "client_operation_id",
                "command_type",
                "request_hash",
                "terminal_kind",
                "terminal_id",
            },
            "billing_command_receipts": {
                "actor_user_id",
                "client_operation_id",
                "command_type",
                "request_hash",
                "result_kind",
                "result_id",
            },
            "billing_command_claims": {
                "actor_user_id",
                "client_operation_id",
                "command_type",
                "request_hash",
                "target_scope",
                "reason_code",
            },
        }
        actor_tables = {
            "billing_accounts": "opened_by_user_id",
            "billing_account_payer_versions": "assigned_by_user_id",
            "billing_rate_plans": "created_by_user_id",
            "billing_rate_plan_versions": "published_by_user_id",
            "billing_agreements": "created_by_user_id",
            "billing_agreement_versions": "reviewed_by_user_id",
            "billing_invoices": "issued_by_user_id",
            "billing_payments": "recorded_by_user_id",
            "billing_allocations": "allocated_by_user_id",
            "billing_credits": "issued_by_user_id",
            "billing_journal_entries": "posted_by_user_id",
            "billing_reversals": "reversed_by_user_id",
            "billing_command_preparations": "actor_user_id",
            "billing_command_receipts": "actor_user_id",
            "billing_command_claims": "actor_user_id",
        }
        version_tables = {
            "billing_account_payer_versions",
            "billing_rate_plan_versions",
            "billing_agreement_versions",
        }
        effect_tables = {
            "billing_accounts",
            "billing_account_payer_versions",
            "billing_rate_plans",
            "billing_rate_plan_versions",
            "billing_agreements",
            "billing_agreement_versions",
            "billing_invoices",
            "billing_invoice_lines",
            "billing_payments",
            "billing_allocations",
            "billing_credits",
            "billing_journal_entries",
        }
        source_tables = {
            "organizations",
            "families",
            "guardians",
            "children",
            "enrollments",
            "facilities",
            "facility_programs",
        }
        for table in effect_tables:
            required_columns[table].update({"client_operation_id", "request_hash"})
        sqlite_special = {
            "billing_sandbox_source_attestations_0033_insert_guard": ("invalid synthetic source",),
            "billing_invoices_0033_payer_guard": ("invalid invoice payer snapshot",),
            "billing_allocations_0033_guard": ("allocation exceeds balance",),
            "billing_credits_0033_guard": ("credit exceeds balance",),
            "billing_journal_lines_0033_guard": ("invalid journal line",),
            "billing_command_receipts_0033_guard": (
                "billing_command_preparations",
                "incomplete terminal receipt proof",
            ),
            "billing_command_claims_0033_guard": (
                "billing_command_preparations",
                "incomplete absence proof",
            ),
            "billing_journal_entries_0033_sequence": (
                "billing_command_preparations",
                "book_sequence",
            ),
            "billing_command_receipts_0033_terminal": ("billing_command_terminals", "'receipt'"),
            "billing_command_claims_0033_terminal": (
                "billing_command_terminals",
                "'absence_claim'",
            ),
            "roles_0033_billing_permissions_insert": ("invalid role billing permissions",),
            "roles_0033_billing_permissions_update": ("invalid role billing permissions",),
        }
        for table in tables:
            for operation in ("update", "delete"):
                sqlite_special[f"{table}_0033_immutable_{operation}"] = ("immutable billing fact",)
        for table in source_tables:
            for operation in ("update", "delete"):
                sqlite_special[f"{table}_0033_attested_source_immutable_{operation}"] = (
                    "attested synthetic source is immutable",
                )
        for table in actor_tables:
            sqlite_special[f"{table}_0033_actor"] = ("invalid billing actor",)
        for table in version_tables:
            sqlite_special[f"{table}_0033_version"] = ("invalid billing version sequence",)

        from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

        from app.basic.models import BasicBase

        metadata_tables = {name: BasicBase.metadata.tables[name] for name in sorted(tables)}
        expected_constraint_shapes: dict[str, dict[str, tuple[str, str]]] = {}
        for table_name, metadata_table in metadata_tables.items():
            shapes: dict[str, tuple[str, str]] = {f"{table_name}_pkey": ("p", "primarykey(id)")}
            for constraint in metadata_table.constraints:
                if not constraint.name:
                    continue
                if isinstance(constraint, CheckConstraint):
                    shapes[str(constraint.name)] = (
                        "c",
                        f"check({_compact_sql(str(constraint.sqltext))})",
                    )
                elif isinstance(constraint, UniqueConstraint):
                    columns = ",".join(column.name for column in constraint.columns)
                    shapes[str(constraint.name)] = ("u", f"unique({columns})")
                elif isinstance(constraint, ForeignKeyConstraint):
                    columns = ",".join(element.parent.name for element in constraint.elements)
                    remote_table = constraint.elements[0].column.table.name
                    remote_columns = ",".join(
                        element.column.name for element in constraint.elements
                    )
                    suffix = (
                        f"ondelete{str(constraint.ondelete).lower()}" if constraint.ondelete else ""
                    )
                    shapes[str(constraint.name)] = (
                        "f",
                        f"foreignkey({columns})references{remote_table}({remote_columns}){suffix}",
                    )
            expected_constraint_shapes[table_name] = shapes

        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                found = set(
                    connection.execute(
                        text(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(tables | {backup_table}))
                            + ")"
                        )
                    ).scalars()
                )
                trigger_count = int(
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM sqlite_master WHERE type='trigger' "
                            "AND name LIKE '%_0033_%'"
                        )
                    )
                    or 0
                )
                alembic_catalog_present = bool(
                    connection.scalar(
                        text(
                            "SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='alembic_version'"
                        )
                    )
                )
                # ORM-created local schemas intentionally have no release
                # marker or migration-owned guards. They do not advertise the
                # 0033 capability and must remain a normal unavailable state.
                if not alembic_catalog_present:
                    return False
                if not found and not trigger_count:
                    return False
                if (
                    found == tables
                    and backup_table not in found
                    and trigger_count == 0
                    and self.settings.environment in {"development", "test"}
                ):
                    return False
                if found != tables | {backup_table}:
                    invalid_boundary()
                revision_values = list(
                    connection.scalars(text("SELECT version_num FROM alembic_version"))
                )
                if len(revision_values) != 1 or not _revision_descends_from(
                    str(revision_values[0]),
                    "0033_billing_ledger",
                ):
                    invalid_boundary()
                current_agreement_scope = _revision_descends_from(
                    str(revision_values[0]),
                    "0037_billing_agreement_scope",
                )
                agreement_shapes = expected_constraint_shapes["billing_agreements"]
                agreement_shapes.pop("uq_bill_agreement_account_child", None)
                agreement_shapes.pop("uq_bill_agreement_account_enrollment", None)
                if current_agreement_scope:
                    agreement_shapes["uq_bill_agreement_account_enrollment"] = (
                        "u",
                        "unique(organization_id,billing_account_id,enrollment_id)",
                    )
                else:
                    agreement_shapes["uq_bill_agreement_account_child"] = (
                        "u",
                        "unique(organization_id,billing_account_id,child_id)",
                    )
                for table, expected in required_columns.items():
                    columns = {
                        str(row[1])
                        for row in connection.exec_driver_sql(f"PRAGMA table_info('{table}')")
                    }
                    if not expected.issubset(columns):
                        invalid_boundary()
                    table_sql = _compact_sql(
                        str(
                            connection.scalar(
                                text(
                                    "SELECT sql FROM sqlite_master WHERE type='table' "
                                    "AND name=:table"
                                ),
                                {"table": table},
                            )
                            or ""
                        )
                    )
                    for constraint_name, (_kind, shape) in expected_constraint_shapes[
                        table
                    ].items():
                        if constraint_name.endswith("_pkey"):
                            if "primarykey(id)" not in table_sql:
                                invalid_boundary()
                        elif (
                            f"constraint{_compact_sql(constraint_name)}" not in table_sql
                            or _compact_sql(shape) not in table_sql
                        ):
                            invalid_boundary()
                    if table == "billing_agreements":
                        forbidden_scope = (
                            "uq_bill_agreement_account_child"
                            if current_agreement_scope
                            else "uq_bill_agreement_account_enrollment"
                        )
                        if f"constraint{forbidden_scope}" in table_sql:
                            invalid_boundary()
                legacy_scope_index_sql = _compact_sql(
                    str(
                        connection.scalar(
                            text(
                                "SELECT sql FROM sqlite_master WHERE type='index' "
                                "AND name='uq_bill_agreement_legacy_account_child'"
                            )
                        )
                        or ""
                    )
                )
                if current_agreement_scope:
                    if not all(
                        fragment in legacy_scope_index_sql
                        for fragment in (
                            "createuniqueindexuq_bill_agreement_legacy_account_child",
                            "onbilling_agreements(organization_id,billing_account_id,child_id)",
                            "whereenrollment_idisnull",
                        )
                    ):
                        invalid_boundary()
                elif legacy_scope_index_sql:
                    invalid_boundary()
                backup_sql = _compact_sql(
                    str(
                        connection.scalar(
                            text(
                                "SELECT sql FROM sqlite_master WHERE type='table' AND name=:table"
                            ),
                            {"table": backup_table},
                        )
                        or ""
                    )
                )
                if not all(
                    fragment in backup_sql
                    for fragment in (
                        "role_idchar(32)notnull",
                        "permissionsjsonnotnull",
                        "primarykey(role_id)",
                        "foreignkey(role_id)referencesroles(id)ondeleterestrict",
                    )
                ):
                    invalid_boundary()
                trigger_rows = {
                    str(row.name): str(row.sql or "").lower()
                    for row in connection.execute(
                        text("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
                    )
                    if str(row.name) in sqlite_special
                }
                if set(trigger_rows) != set(sqlite_special) or not all(
                    all(fragment in trigger_rows[name] for fragment in fragments)
                    for name, fragments in sqlite_special.items()
                ):
                    invalid_boundary()
                role_rows = list(connection.execute(text("SELECT key,permissions FROM roles")))
                self._validate_billing_role_permissions(role_rows, invalid_boundary)
                return True

            expected_relations = tables | {backup_table}
            found = set(
                connection.execute(
                    text(
                        "SELECT name FROM unnest(CAST(:names AS text[])) name WHERE "
                        "pg_catalog.to_regclass('public.'||name) IS NOT NULL"
                    ),
                    {"names": sorted(expected_relations)},
                ).scalars()
            )
            function_names = {
                "caresync_0033_attested_source_immutable",
                "caresync_0033_immutable_fact",
                "caresync_0033_role_permission_guard",
                "caresync_0033_source_attestation_guard",
                "caresync_0033_actor_guard",
                "caresync_0033_version_guard",
                "caresync_0033_invoice_line_guard",
                "caresync_0033_allocation_guard",
                "caresync_0033_credit_guard",
                "caresync_0033_journal_sequence_guard",
                "caresync_0033_journal_validate",
                "caresync_0033_effect_open_guard",
                "caresync_0033_bundle_validate",
                "caresync_0033_receipt_guard",
                "caresync_0033_claim_guard",
                "caresync_0033_terminal_claim",
            }
            if not found:
                orphan = bool(
                    connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n "
                            "ON n.oid=p.pronamespace WHERE n.nspname='public' "
                            "AND p.proname=ANY(CAST(:names AS text[])))"
                        ),
                        {"names": sorted(function_names)},
                    )
                )
                if orphan:
                    invalid_boundary()
                return False
            if found != expected_relations:
                invalid_boundary()
            manual_boundary_shapes = {
                "activation": bool(
                    connection.scalar(
                        text("SELECT pg_catalog.to_regclass('public.billing_manual_activations')")
                    )
                ),
                "authorization_view": bool(
                    connection.scalar(
                        text(
                            "SELECT pg_catalog.to_regclass("
                            "'public.billing_source_authorizations_0036')"
                        )
                    )
                ),
                "bundle_function": bool(
                    connection.scalar(
                        text(
                            "SELECT pg_catalog.to_regprocedure("
                            "'public.caresync_0036_bundle_validate()')"
                        )
                    )
                ),
            }
            if any(manual_boundary_shapes.values()) and not all(manual_boundary_shapes.values()):
                invalid_boundary()
            manual_boundary_present = all(manual_boundary_shapes.values())
            for table, expected in required_columns.items():
                columns = set(
                    connection.execute(
                        text(
                            "SELECT attname FROM pg_attribute WHERE attrelid="
                            "pg_catalog.to_regclass(:table) AND attnum>0 AND NOT attisdropped"
                        ),
                        {"table": f"public.{table}"},
                    ).scalars()
                )
                if not expected.issubset(columns):
                    invalid_boundary()
            hardened = set(
                connection.execute(
                    text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid="
                        "c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(CAST(:names "
                        "AS text[])) AND c.relrowsecurity AND c.relforcerowsecurity"
                    ),
                    {"names": sorted(tables)},
                ).scalars()
            )
            if hardened != tables:
                invalid_boundary()
            insert_policy_kinds = {
                "billing_accounts": "manage",
                "billing_account_payer_versions": "manage",
                "billing_rate_plans": "manage",
                "billing_rate_plan_versions": "manage",
                "billing_agreements": "manage",
                "billing_agreement_versions": "manage",
                "billing_invoices": "issue",
                "billing_invoice_lines": "issue",
                "billing_payments": "payments",
                "billing_allocations": "payments",
                "billing_credits": "adjust",
                "billing_command_claims": "recover",
                "billing_command_preparations": "command",
                "billing_command_receipts": "command",
                "billing_command_terminals": "command",
                "billing_journal_entries": "journal_entry",
                "billing_journal_lines": "journal_line",
            }
            expected_policy_specs = {
                (table, f"{table}_0033_select"): (
                    "r",
                    "select",
                )
                for table in tables
            }
            expected_policy_specs.update(
                {
                    (table, f"{table}_0033_insert"): (
                        "a",
                        kind,
                    )
                    for table, kind in insert_policy_kinds.items()
                }
            )
            policy_rows = {
                (str(row.relname), str(row.polname)): row
                for row in connection.execute(
                    text(
                        "SELECT c.relname,p.polname,p.polcmd,p.polpermissive,p.polroles,"
                        "pg_catalog.pg_get_expr(p.polqual,p.polrelid) using_expression,"
                        "pg_catalog.pg_get_expr(p.polwithcheck,p.polrelid) check_expression "
                        "FROM pg_catalog.pg_policy p JOIN pg_catalog.pg_class c "
                        "ON c.oid=p.polrelid JOIN pg_catalog.pg_namespace n "
                        "ON n.oid=c.relnamespace WHERE n.nspname='public' "
                        "AND c.relname=ANY(CAST(:tables AS text[]))"
                    ),
                    {"tables": sorted(tables)},
                )
            }
            if set(policy_rows) != set(expected_policy_specs):
                invalid_boundary()
            observed_policy_hashes: dict[tuple[str, str], str] = {}
            for key, (expected_command, _kind) in expected_policy_specs.items():
                row = policy_rows[key]
                expression = (
                    row.using_expression if expected_command == "r" else row.check_expression
                )
                unused_expression = (
                    row.check_expression if expected_command == "r" else row.using_expression
                )
                if (
                    str(row.polcmd) != expected_command
                    or not bool(row.polpermissive)
                    or tuple(int(role) for role in (row.polroles or [])) != (0,)
                    or unused_expression is not None
                ):
                    invalid_boundary()
                observed_policy_hashes[key] = _canonical_sql_sha256(str(expression or ""))

            policy_kinds = {
                key: kind for key, (_command, kind) in expected_policy_specs.items()
            }
            policy_profile = _certify_billing_policy_catalog_profile(
                observed_policy_hashes,
                policy_kinds,
                revision=None,
            )
            if policy_profile is None:
                alembic_catalog_present = bool(
                    connection.scalar(
                        text(
                            "SELECT pg_catalog.to_regclass("
                            "'public.alembic_version') IS NOT NULL"
                        )
                    )
                )
                revision_values = (
                    list(
                        connection.scalars(
                            text("SELECT version_num FROM public.alembic_version")
                        )
                    )
                    if alembic_catalog_present
                    else []
                )
                revision = (
                    str(revision_values[0]) if len(revision_values) == 1 else None
                )
                policy_profile = _certify_billing_policy_catalog_profile(
                    observed_policy_hashes,
                    policy_kinds,
                    revision=revision,
                )
            if policy_profile is None:
                invalid_boundary()

            function_rows = {
                str(row.proname): row
                for row in connection.execute(
                    text(
                        "SELECT p.proname,p.oid,p.prokind,p.pronargs,p.provolatile,"
                        "p.prosecdef,p.proisstrict,p.proleakproof,p.proparallel,p.proconfig,"
                        "p.prosrc,l.lanname,pg_catalog.pg_get_function_result(p.oid) result_type,"
                        "pg_catalog.pg_get_userbyid(p.proowner) owner_name,"
                        "owner.rolsuper owner_superuser,owner.rolbypassrls owner_bypassrls,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "p.proacl,pg_catalog.acldefault('f',p.proowner))) privilege "
                        "WHERE privilege.grantee=0 AND privilege.privilege_type='EXECUTE') "
                        "public_exec,CASE WHEN EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
                        "WHERE rolname='caresync_basic_app') THEN COALESCE("
                        "pg_catalog.has_function_privilege('caresync_basic_app',p.oid,"
                        "'EXECUTE'),false) ELSE false END app_exec "
                        "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n "
                        "ON n.oid=p.pronamespace JOIN pg_catalog.pg_language l "
                        "ON l.oid=p.prolang JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner "
                        "WHERE n.nspname='public' "
                        "AND p.proname=ANY(CAST(:names AS text[]))"
                    ),
                    {"names": sorted(function_names)},
                )
            }
            if set(function_rows) != function_names:
                invalid_boundary()
            for name, expected_hash in _BILLING_0033_FUNCTION_SOURCE_SHA256.items():
                row = function_rows[name]
                if (
                    row.oid is None
                    or str(row.prokind) != "f"
                    or int(row.pronargs) != 0
                    or str(row.provolatile) != "v"
                    or str(row.lanname) != "plpgsql"
                    or str(row.result_type) != "trigger"
                    or bool(row.prosecdef)
                    is not (
                        name
                        in {
                            "caresync_0033_attested_source_immutable",
                            "caresync_0033_terminal_claim",
                        }
                    )
                    or bool(row.proisstrict)
                    or bool(row.proleakproof)
                    or str(row.proparallel) != "u"
                    or set(row.proconfig or []) != {"search_path=pg_catalog, public"}
                    or str(row.owner_name) == "caresync_basic_app"
                    or (
                        name == "caresync_0033_attested_source_immutable"
                        and not (bool(row.owner_superuser) or bool(row.owner_bypassrls))
                    )
                    or bool(row.public_exec)
                    or bool(row.app_exec)
                    or _canonical_sql_sha256(str(row.prosrc or "")) != expected_hash
                ):
                    invalid_boundary()
            if manual_boundary_present:
                manual_function = connection.execute(
                    text(
                        "SELECT p.oid,p.prokind,p.pronargs,p.provolatile,p.prosecdef,"
                        "p.proisstrict,p.proleakproof,p.proparallel,p.proconfig,p.prosrc,"
                        "l.lanname,pg_catalog.pg_get_function_result(p.oid) result_type,"
                        "pg_catalog.pg_get_userbyid(p.proowner) owner_name,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "p.proacl,pg_catalog.acldefault('f',p.proowner))) privilege "
                        "WHERE privilege.grantee=0 AND privilege.privilege_type='EXECUTE') "
                        "public_exec,CASE WHEN EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
                        "WHERE rolname='caresync_basic_app') THEN COALESCE("
                        "pg_catalog.has_function_privilege('caresync_basic_app',p.oid,"
                        "'EXECUTE'),false) ELSE false END app_exec "
                        "FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n "
                        "ON n.oid=p.pronamespace JOIN pg_catalog.pg_language l "
                        "ON l.oid=p.prolang WHERE n.nspname='public' "
                        "AND p.proname='caresync_0036_bundle_validate'"
                    )
                ).one_or_none()
                base_source = str(function_rows["caresync_0033_bundle_validate"].prosrc or "")
                expected_manual_source = base_source.replace(
                    "public.billing_sandbox_source_attestations",
                    "public.billing_source_authorizations_0036",
                )
                if (
                    manual_function is None
                    or base_source.count("public.billing_sandbox_source_attestations") != 15
                    or manual_function.oid is None
                    or str(manual_function.prokind) != "f"
                    or int(manual_function.pronargs) != 0
                    or str(manual_function.provolatile) != "v"
                    or bool(manual_function.prosecdef)
                    or bool(manual_function.proisstrict)
                    or bool(manual_function.proleakproof)
                    or str(manual_function.proparallel) != "u"
                    or set(manual_function.proconfig or []) != {"search_path=pg_catalog, public"}
                    or str(manual_function.lanname) != "plpgsql"
                    or str(manual_function.result_type) != "trigger"
                    or str(manual_function.owner_name) == "caresync_basic_app"
                    or bool(manual_function.public_exec)
                    or bool(manual_function.app_exec)
                    or _canonical_sql_sha256(str(manual_function.prosrc or ""))
                    != _canonical_sql_sha256(expected_manual_source)
                ):
                    invalid_boundary()

            bundle_tables = {
                "billing_accounts",
                "billing_account_payer_versions",
                "billing_rate_plans",
                "billing_rate_plan_versions",
                "billing_agreements",
                "billing_agreement_versions",
                "billing_invoices",
                "billing_invoice_lines",
                "billing_payments",
                "billing_allocations",
                "billing_credits",
                "billing_journal_entries",
                "billing_journal_lines",
            }
            trigger_contracts: dict[tuple[str, str], tuple[str, int, bool, bool, str]] = {}

            def add_trigger(
                table: str,
                name: str,
                function: str,
                event_clause: str,
                trigger_type: int,
                *,
                argument: str | None = None,
                constraint: bool = False,
            ) -> None:
                prefix = "CREATE CONSTRAINT TRIGGER" if constraint else "CREATE TRIGGER"
                deferrability = " DEFERRABLE INITIALLY DEFERRED" if constraint else ""
                arguments = f"'{argument}'" if argument is not None else ""
                definition = (
                    f"{prefix} {name} {event_clause} ON public.{table}{deferrability} "
                    f"FOR EACH ROW EXECUTE FUNCTION {function}({arguments})"
                )
                trigger_contracts[(table, name)] = (
                    function,
                    trigger_type,
                    constraint,
                    constraint,
                    _compact_sql(definition),
                )

            for table in tables:
                add_trigger(
                    table,
                    f"{table}_0033_immutable",
                    "caresync_0033_immutable_fact",
                    "BEFORE DELETE OR UPDATE",
                    27,
                )
            for table in source_tables:
                add_trigger(
                    table,
                    f"{table}_0033_attested_source_immutable",
                    "caresync_0033_attested_source_immutable",
                    "BEFORE DELETE OR UPDATE",
                    27,
                )
            for table, actor_column in actor_tables.items():
                add_trigger(
                    table,
                    f"{table}_0033_actor",
                    "caresync_0033_actor_guard",
                    "BEFORE INSERT",
                    7,
                    argument=actor_column,
                )
            for table in version_tables:
                add_trigger(
                    table,
                    f"{table}_0033_version",
                    "caresync_0033_version_guard",
                    "BEFORE INSERT",
                    7,
                )
            for table in bundle_tables:
                add_trigger(
                    table,
                    f"{table}_0033_effect_open",
                    "caresync_0033_effect_open_guard",
                    "BEFORE INSERT",
                    7,
                )
                add_trigger(
                    table,
                    f"{table}_0033_bundle",
                    (
                        "caresync_0036_bundle_validate"
                        if manual_boundary_present
                        else "caresync_0033_bundle_validate"
                    ),
                    "AFTER INSERT",
                    5,
                    constraint=True,
                )
            for table, name, function in (
                (
                    "billing_sandbox_source_attestations",
                    "billing_sandbox_source_attestations_0033_insert_guard",
                    "caresync_0033_source_attestation_guard",
                ),
                (
                    "billing_invoice_lines",
                    "billing_invoice_lines_0033_guard",
                    "caresync_0033_invoice_line_guard",
                ),
                (
                    "billing_allocations",
                    "billing_allocations_0033_guard",
                    "caresync_0033_allocation_guard",
                ),
                (
                    "billing_credits",
                    "billing_credits_0033_guard",
                    "caresync_0033_credit_guard",
                ),
                (
                    "billing_journal_entries",
                    "billing_journal_entries_0033_sequence",
                    "caresync_0033_journal_sequence_guard",
                ),
                (
                    "billing_command_receipts",
                    "billing_command_receipts_0033_guard",
                    "caresync_0033_receipt_guard",
                ),
                (
                    "billing_command_claims",
                    "billing_command_claims_0033_guard",
                    "caresync_0033_claim_guard",
                ),
            ):
                add_trigger(table, name, function, "BEFORE INSERT", 7)
            for table in ("billing_journal_entries", "billing_journal_lines"):
                add_trigger(
                    table,
                    f"{table}_0033_balance",
                    "caresync_0033_journal_validate",
                    "AFTER INSERT",
                    5,
                    constraint=True,
                )
            for table in ("billing_command_receipts", "billing_command_claims"):
                add_trigger(
                    table,
                    f"{table}_0033_terminal",
                    "caresync_0033_terminal_claim",
                    "AFTER INSERT",
                    5,
                )
            add_trigger(
                "roles",
                "roles_0033_billing_permissions",
                "caresync_0033_role_permission_guard",
                "BEFORE INSERT OR UPDATE OF key, permissions",
                23,
            )
            trigger_rows = {
                (str(row.relname), str(row.tgname)): row
                for row in connection.execute(
                    text(
                        "SELECT c.relname,t.tgname,t.tgenabled,t.tgtype,t.tgqual,t.tgnargs,"
                        "t.tgdeferrable,t.tginitdeferred,t.tgconstraint,p.proname,"
                        "fn.nspname function_schema,pg_catalog.pg_get_triggerdef(t.oid) "
                        "trigger_definition FROM pg_catalog.pg_trigger t "
                        "JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid "
                        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                        "JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid "
                        "JOIN pg_catalog.pg_namespace fn ON fn.oid=p.pronamespace "
                        "WHERE n.nspname='public' AND NOT t.tgisinternal "
                        "AND c.relname=ANY(CAST(:tables AS text[])) "
                        "AND t.tgname LIKE '%\\_0033\\_%' ESCAPE '\\'"
                    ),
                    {"tables": sorted(tables | source_tables | {"roles"})},
                )
            }
            if set(trigger_rows) != set(trigger_contracts):
                invalid_boundary()
            for key, contract in trigger_contracts.items():
                function, trigger_type, deferrable, initially_deferred, definition = contract
                row = trigger_rows[key]
                if (
                    str(row.tgenabled) != "O"
                    or int(row.tgtype) != trigger_type
                    or row.tgqual is not None
                    or bool(row.tgdeferrable) is not deferrable
                    or bool(row.tginitdeferred) is not initially_deferred
                    or bool(int(row.tgconstraint)) is not deferrable
                    or str(row.proname) != function
                    or str(row.function_schema) != "public"
                    or _compact_sql(str(row.trigger_definition or "")) != definition
                ):
                    invalid_boundary()
            if connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app'")):
                insert_tables = tables - {
                    "billing_sandbox_source_attestations",
                    "billing_command_terminals",
                    "billing_reversals",
                }
                privilege_rows = list(
                    connection.execute(
                        text(
                            "SELECT name,"
                            "has_table_privilege('caresync_basic_app',"
                            "pg_catalog.to_regclass('public.'||name),'SELECT') can_select,"
                            "has_table_privilege('caresync_basic_app',"
                            "pg_catalog.to_regclass('public.'||name),'INSERT') can_insert,"
                            "has_table_privilege('caresync_basic_app',"
                            "pg_catalog.to_regclass('public.'||name),"
                            "'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') forbidden "
                            "FROM unnest(CAST(:tables AS text[])) name"
                        ),
                        {"tables": sorted(tables)},
                    )
                )
                if any(
                    not bool(row.can_select)
                    or bool(row.can_insert) is not (str(row.name) in insert_tables)
                    or bool(row.forbidden)
                    for row in privilege_rows
                ):
                    invalid_boundary()
                if connection.scalar(
                    text(
                        "SELECT has_table_privilege('caresync_basic_app',"
                        "pg_catalog.to_regclass(:table),"
                        "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
                    ),
                    {"table": f"public.{backup_table}"},
                ):
                    invalid_boundary()
            return True

    def has_billing_manual_activation_boundary(self) -> bool:
        """Fail closed unless the complete 0036 private-manual boundary is present."""

        def invalid_boundary() -> NoReturn:
            raise RuntimeError(
                "Partial or drifted 0036 manual billing boundary; repair the schema before startup"
            )

        table = "billing_manual_activations"
        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                table_sql = str(
                    connection.scalar(
                        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
                        {"name": table},
                    )
                    or ""
                )
                if not table_sql:
                    return False
                trigger_rows = {
                    str(row.name): _compact_sql(str(row.sql or ""))
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                            "AND name LIKE 'billing_manual_activations_0036_%'"
                        )
                    )
                }
                expected = {
                    "billing_manual_activations_0036_insert_guard": (
                        "role.key='owner'",
                        "billing:manage",
                        "billing_sandbox_source_attestations",
                        "billing_command_preparations",
                        "billing_accounts",
                    ),
                    "billing_manual_activations_0036_immutable_update": (
                        "immutablemanualbillingactivation",
                    ),
                    "billing_manual_activations_0036_immutable_delete": (
                        "immutablemanualbillingactivation",
                    ),
                }
                if (
                    set(trigger_rows) != set(expected)
                    or not all(
                        all(_compact_sql(fragment) in trigger_rows[name] for fragment in fragments)
                        for name, fragments in expected.items()
                    )
                    or not all(
                        fragment in _compact_sql(table_sql)
                        for fragment in (
                            "unique(organization_id)",
                            "private_local_manual_billing_v1",
                            "off-platformpayments",
                        )
                    )
                ):
                    invalid_boundary()
                return True

            activation_present = bool(
                connection.scalar(
                    text("SELECT pg_catalog.to_regclass('public.billing_manual_activations')")
                )
            )
            authorization_view_present = bool(
                connection.scalar(
                    text(
                        "SELECT pg_catalog.to_regclass('public.billing_source_authorizations_0036')"
                    )
                )
            )
            bundle_function_present = bool(
                connection.scalar(
                    text(
                        "SELECT pg_catalog.to_regprocedure("
                        "'public.caresync_0036_bundle_validate()')"
                    )
                )
            )
            if not any((activation_present, authorization_view_present, bundle_function_present)):
                return False
            if not all((activation_present, authorization_view_present, bundle_function_present)):
                invalid_boundary()
            relation = connection.execute(
                text(
                    "SELECT relrowsecurity,relforcerowsecurity FROM pg_catalog.pg_class "
                    "WHERE oid='public.billing_manual_activations'::regclass"
                )
            ).one()
            columns = set(
                connection.execute(
                    text(
                        "SELECT attname FROM pg_catalog.pg_attribute WHERE attrelid="
                        "'public.billing_manual_activations'::regclass "
                        "AND attnum>0 AND NOT attisdropped"
                    )
                ).scalars()
            )
            if (
                not bool(relation.relrowsecurity)
                or not bool(relation.relforcerowsecurity)
                or columns
                != {
                    "id",
                    "organization_id",
                    "activated_by_user_id",
                    "activated_by_membership_id",
                    "activation_policy_version",
                    "review_attestation",
                    "activated_at",
                }
            ):
                invalid_boundary()
            policies = {
                str(row.polname): (
                    str(row.polcmd),
                    _compact_sql(str(row.using_expression or row.check_expression or "")),
                    row.using_expression,
                    row.check_expression,
                )
                for row in connection.execute(
                    text(
                        "SELECT policy.polname,policy.polcmd,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                        "using_expression,"
                        "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                        "check_expression FROM pg_catalog.pg_policy policy WHERE "
                        "policy.polrelid='public.billing_manual_activations'::regclass"
                    )
                )
            }
            if set(policies) != {
                "billing_manual_activations_0036_select",
                "billing_manual_activations_0036_insert",
            }:
                invalid_boundary()
            for name, command, authority_fragments in (
                (
                    "billing_manual_activations_0036_select",
                    "r",
                    ("'owner'", "'administrator'", "billing:read"),
                ),
                (
                    "billing_manual_activations_0036_insert",
                    "a",
                    ("'owner'", "billing:manage"),
                ),
            ):
                actual_command, expression, using_expression, check_expression = policies[name]
                if (
                    actual_command != command
                    or (command == "r" and check_expression is not None)
                    or (command == "a" and using_expression is not None)
                    or not all(
                        fragment in expression
                        for fragment in (
                            "app.current_organization_id",
                            "app.current_user_id",
                            *authority_fragments,
                        )
                    )
                ):
                    invalid_boundary()
            triggers = {
                str(row.tgname): (
                    str(row.proname),
                    str(row.tgenabled),
                    _compact_sql(str(row.definition or "")),
                )
                for row in connection.execute(
                    text(
                        "SELECT trigger.tgname,procedure.proname,trigger.tgenabled,"
                        "pg_catalog.pg_get_triggerdef(trigger.oid) definition "
                        "FROM pg_catalog.pg_trigger trigger JOIN pg_catalog.pg_proc procedure "
                        "ON procedure.oid=trigger.tgfoid WHERE trigger.tgrelid="
                        "'public.billing_manual_activations'::regclass "
                        "AND NOT trigger.tgisinternal"
                    )
                )
            }
            if (
                set(triggers)
                != {
                    "billing_manual_activations_0036_insert_guard",
                    "billing_manual_activations_0036_immutable",
                }
                or triggers["billing_manual_activations_0036_insert_guard"][:2]
                != ("caresync_0036_manual_activation_guard", "O")
                or triggers["billing_manual_activations_0036_immutable"][:2]
                != ("caresync_0036_manual_activation_immutable", "O")
                or "beforeinsert" not in triggers["billing_manual_activations_0036_insert_guard"][2]
                or "beforedeleteorupdate"
                not in triggers["billing_manual_activations_0036_immutable"][2]
            ):
                invalid_boundary()
            functions = {
                str(row.proname): row
                for row in connection.execute(
                    text(
                        "SELECT procedure.proname,procedure.provolatile,"
                        "procedure.prosecdef,procedure.proconfig,procedure.prosrc,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner))) acl "
                        "WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE') public_exec,"
                        "CASE WHEN EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE "
                        "rolname='caresync_basic_app') THEN pg_catalog.has_function_privilege("
                        "'caresync_basic_app',procedure.oid,'EXECUTE') ELSE false END app_exec "
                        "FROM pg_catalog.pg_proc procedure JOIN pg_catalog.pg_namespace namespace "
                        "ON namespace.oid=procedure.pronamespace WHERE namespace.nspname='public' "
                        "AND procedure.proname=ANY(CAST(:names AS text[]))"
                    ),
                    {
                        "names": [
                            "caresync_0036_bundle_validate",
                            "caresync_0036_manual_activation_guard",
                            "caresync_0036_manual_activation_immutable",
                        ]
                    },
                )
            }
            if set(functions) != {
                "caresync_0036_bundle_validate",
                "caresync_0036_manual_activation_guard",
                "caresync_0036_manual_activation_immutable",
            }:
                invalid_boundary()
            for function in functions.values():
                if (
                    str(function.provolatile) != "v"
                    or bool(function.prosecdef)
                    or set(function.proconfig or []) != {"search_path=pg_catalog, public"}
                    or bool(function.public_exec)
                    or bool(function.app_exec)
                ):
                    invalid_boundary()
            guard_source = _compact_sql(
                str(functions["caresync_0036_manual_activation_guard"].prosrc or "")
            )
            immutable_source = _compact_sql(
                str(functions["caresync_0036_manual_activation_immutable"].prosrc or "")
            )
            if (
                not all(
                    fragment in guard_source
                    for fragment in (
                        "role.key='owner'",
                        "billing:manage",
                        "billing_sandbox_source_attestations",
                        "billing_command_preparations",
                        "billing_accounts",
                    )
                )
                or "manualbillingactivationisimmutable" not in immutable_source
            ):
                invalid_boundary()
            view_row = connection.execute(
                text(
                    "SELECT relation.relkind,relation.reloptions,"
                    "pg_catalog.pg_get_viewdef(relation.oid,true) definition "
                    "FROM pg_catalog.pg_class relation WHERE relation.oid="
                    "'public.billing_source_authorizations_0036'::regclass"
                )
            ).one()
            view_definition = _compact_sql(str(view_row.definition or ""))
            if (
                str(view_row.relkind) != "v"
                or "security_invoker=true" not in set(view_row.reloptions or [])
                or not all(
                    fragment in view_definition
                    for fragment in (
                        "billing_sandbox_source_attestations",
                        "billing_manual_activations",
                        "families",
                        "guardians",
                        "children",
                        "enrollments",
                        "facilities",
                        "facility_programs",
                    )
                )
            ):
                invalid_boundary()
            if connection.scalar(
                text("SELECT 1 FROM pg_roles WHERE rolname='caresync_basic_app'")
            ) and (
                not bool(
                    connection.scalar(
                        text(
                            "SELECT has_table_privilege('caresync_basic_app',"
                            "'public.billing_manual_activations','SELECT,INSERT')"
                        )
                    )
                )
                or bool(
                    connection.scalar(
                        text(
                            "SELECT has_table_privilege('caresync_basic_app',"
                            "'public.billing_manual_activations',"
                            "'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
                        )
                    )
                )
                or not bool(
                    connection.scalar(
                        text(
                            "SELECT has_table_privilege('caresync_basic_app',"
                            "'public.billing_source_authorizations_0036','SELECT')"
                        )
                    )
                )
            ):
                invalid_boundary()
            return True

    @staticmethod
    def _validate_billing_role_permissions(role_rows, invalid_boundary) -> None:
        owner = {
            "billing:read",
            "billing:manage",
            "billing:issue",
            "billing:payments",
            "billing:adjust",
            "billing:close",
            "billing:recover",
        }
        administrator = {
            "billing:read",
            "billing:manage",
            "billing:issue",
            "billing:payments",
            "billing:recover",
        }
        for row in role_rows:
            raw = row.permissions
            permissions = set(json.loads(raw) if isinstance(raw, str) else (raw or []))
            billing = {value for value in permissions if value.startswith("billing:")}
            if (
                (row.key == "owner" and billing != owner)
                or (row.key == "administrator" and billing != administrator)
                or (row.key not in {"owner", "administrator"} and billing)
            ):
                invalid_boundary()

    def has_transport_registry_commands(self) -> bool:
        """Fail closed unless the complete 0032 command/runtime boundary exists."""

        def invalid_boundary() -> NoReturn:
            raise RuntimeError(
                "Partial or drifted 0032 transport command boundary; repair roles, "
                "schema, and runtime grants before startup"
            )

        new_tables = {
            "transport_registry_command_receipts",
            "staff_driver_qualification_evidence_objects",
            "staff_driver_qualification_review_decisions",
            "transport_vehicle_evidence_review_decisions",
            "transport_vehicle_evidence_scan_facts",
        }
        registry_tables = {
            "staff_driver_capability_versions",
            "staff_driver_qualification_versions",
            "staff_driver_authorization_decisions",
            "staff_driver_readiness_decisions",
            "transport_vehicles",
            "transport_vehicle_versions",
            "transport_vehicle_evidence_versions",
        }
        all_transport_tables = registry_tables | new_tables
        required_columns = {
            "transport_registry_command_receipts": {
                "organization_id",
                "actor_user_id",
                "client_operation_id",
                "command_kind",
                "request_sha256",
                "result_kind",
                "result_id",
                "operational_driver_ready",
                "dispatch_authorized",
            },
            "staff_driver_qualification_evidence_objects": {
                "organization_id",
                "membership_id",
                "qualification_version_id",
                "content_sha256",
                "ciphertext_sha256",
                "storage_reference",
                "scanner_engine",
                "scanner_version",
                "scanned_at",
                "recorded_by_user_id",
            },
            "staff_driver_qualification_review_decisions": {
                "organization_id",
                "membership_id",
                "source_qualification_version_id",
                "result_qualification_version_id",
                "decision",
                "reviewed_by_user_id",
            },
            "transport_vehicle_evidence_review_decisions": {
                "organization_id",
                "vehicle_id",
                "source_evidence_version_id",
                "result_evidence_version_id",
                "decision",
                "reviewed_by_user_id",
            },
            "transport_vehicle_evidence_scan_facts": {
                "organization_id",
                "vehicle_id",
                "evidence_version_id",
                "decision",
                "scanner_engine",
                "scanner_version",
                "scanned_at",
                "recorded_by_user_id",
            },
        }
        required_constraints = {
            "ck_transport_registry_receipt_command",
            "ck_transport_registry_receipt_request_sha256",
            "ck_transport_registry_receipt_not_operational",
            "ck_driver_qualification_evidence_content_sha256",
            "ck_driver_qualification_evidence_ciphertext_sha256",
            "ck_driver_qualification_evidence_scan_provenance",
            "ck_driver_qualification_evidence_not_operational",
            "ck_driver_qualification_review_decision",
            "ck_driver_qualification_review_not_operational",
            "ck_vehicle_evidence_review_decision",
            "ck_vehicle_evidence_review_not_operational",
            "ck_vehicle_evidence_scan_clean_only",
            "ck_vehicle_evidence_scan_provenance",
            "ck_vehicle_evidence_scan_not_operational",
        }
        insert_trigger_functions = {
            (
                "transport_registry_receipt_insert_guard",
                "transport_registry_command_receipts",
            ): "caresync_0032_receipt_guard",
            (
                "staff_driver_qualification_evidence_insert_guard",
                "staff_driver_qualification_evidence_objects",
            ): "caresync_0032_qualification_evidence_guard",
            (
                "staff_driver_qualification_review_insert_guard",
                "staff_driver_qualification_review_decisions",
            ): "caresync_0032_qualification_review_guard",
            (
                "transport_vehicle_evidence_review_insert_guard",
                "transport_vehicle_evidence_review_decisions",
            ): "caresync_0032_vehicle_review_guard",
            (
                "transport_vehicle_evidence_scan_insert_guard",
                "transport_vehicle_evidence_scan_facts",
            ): "caresync_0032_vehicle_scan_guard",
        }
        postgres_trigger_contracts = {
            (
                "staff_driver_capability_insert_guard",
                "staff_driver_capability_versions",
            ): ("caresync_0031_capability_guard", "INSERT"),
            (
                "staff_driver_capability_versions_immutable",
                "staff_driver_capability_versions",
            ): ("caresync_0031_immutable_fact", "DELETE OR UPDATE"),
            (
                "staff_driver_qualification_insert_guard",
                "staff_driver_qualification_versions",
            ): ("caresync_0031_qualification_guard", "INSERT"),
            (
                "staff_driver_qualification_versions_immutable",
                "staff_driver_qualification_versions",
            ): ("caresync_0031_immutable_fact", "DELETE OR UPDATE"),
            (
                "staff_driver_authorization_insert_guard",
                "staff_driver_authorization_decisions",
            ): ("caresync_0031_authorization_guard", "INSERT"),
            (
                "staff_driver_authorization_decisions_immutable",
                "staff_driver_authorization_decisions",
            ): ("caresync_0031_immutable_fact", "DELETE OR UPDATE"),
            (
                "staff_driver_readiness_insert_guard",
                "staff_driver_readiness_decisions",
            ): ("caresync_0031_readiness_guard", "INSERT"),
            (
                "staff_driver_readiness_decisions_immutable",
                "staff_driver_readiness_decisions",
            ): ("caresync_0031_immutable_fact", "DELETE OR UPDATE"),
            ("transport_vehicles_guard", "transport_vehicles"): (
                "caresync_0031_vehicle_guard",
                "DELETE OR UPDATE",
            ),
            (
                "transport_vehicle_versions_insert_guard",
                "transport_vehicle_versions",
            ): ("caresync_0031_vehicle_version_guard", "INSERT"),
            (
                "transport_vehicle_versions_immutable",
                "transport_vehicle_versions",
            ): ("caresync_0031_immutable_fact", "DELETE OR UPDATE"),
            (
                "transport_vehicle_evidence_insert_guard",
                "transport_vehicle_evidence_versions",
            ): ("caresync_0031_vehicle_evidence_guard", "INSERT"),
            (
                "transport_vehicle_evidence_versions_immutable",
                "transport_vehicle_evidence_versions",
            ): ("caresync_0031_immutable_fact", "DELETE OR UPDATE"),
            **{
                key: (function_name, "INSERT")
                for key, function_name in insert_trigger_functions.items()
            },
            **{
                (f"{table}_immutable", table): (
                    "caresync_0032_immutable_fact",
                    "DELETE OR UPDATE",
                )
                for table in new_tables
            },
        }
        postgres_trigger_functions = {
            key: contract[0] for key, contract in postgres_trigger_contracts.items()
        }
        guard_function_fragments = {
            "caresync_0032_immutable_fact()": ("immutable transport command fact",),
            "caresync_0032_receipt_guard()": ("result_bound", "authority boundary"),
            "caresync_0032_qualification_evidence_guard()": (
                "scanner_engine",
                "qualification evidence ownership",
            ),
            "caresync_0032_qualification_review_guard()": ("independently evidence-bound",),
            "caresync_0032_vehicle_review_guard()": ("independently evidence-bound",),
            "caresync_0032_vehicle_scan_guard()": ("scan provenance",),
        }
        writer_signature = "caresync_0032_execute_command(text,uuid,text,jsonb)"

        sqlite_trigger_fragments: dict[str, tuple[str, ...]] = {
            "transport_registry_receipt_insert_guard": ("result_id", "authority boundary"),
            "staff_driver_qualification_evidence_insert_guard": (
                "scanner_engine",
                "qualification evidence ownership",
            ),
            "staff_driver_qualification_review_insert_guard": ("independently evidence-bound",),
            "transport_vehicle_evidence_review_insert_guard": ("independently evidence-bound",),
            "transport_vehicle_evidence_scan_insert_guard": ("scan provenance",),
        }
        for table in new_tables:
            for operation in ("update", "delete"):
                sqlite_trigger_fragments[f"{table}_immutable_{operation}"] = (
                    "immutable transport command fact",
                )

        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                found = set(
                    connection.execute(
                        text(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(new_tables))
                            + ")"
                        )
                    ).scalars()
                )
                if not found:
                    orphaned = bool(
                        connection.scalar(
                            text(
                                "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                                "WHERE type='trigger' AND name IN ("
                                + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                                + "))"
                            )
                        )
                    )
                    if orphaned:
                        invalid_boundary()
                    return False
                if found != new_tables:
                    invalid_boundary()
                for table, expected in required_columns.items():
                    columns = {
                        str(row[1])
                        for row in connection.exec_driver_sql(f"PRAGMA table_info('{table}')")
                    }
                    if not expected.issubset(columns):
                        invalid_boundary()
                alembic_managed = bool(
                    connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM sqlite_master "
                            "WHERE type='table' AND name='alembic_version')"
                        )
                    )
                )
                trigger_rows = {
                    str(row.name): str(row.sql or "").lower()
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN ("
                            + ",".join(f"'{name}'" for name in sorted(sqlite_trigger_fragments))
                            + ")"
                        )
                    )
                }
                if (
                    not alembic_managed
                    and not trigger_rows
                    and self.settings.environment in {"development", "test"}
                ):
                    return False
                if set(trigger_rows) != set(sqlite_trigger_fragments):
                    invalid_boundary()
                # 0032 commands are a PostgreSQL repository capability.  SQLite
                # retains the schema/trigger proofs for portable tests only.
                return False

            found = set(
                connection.execute(
                    text(
                        "SELECT name FROM unnest(CAST(:names AS text[])) AS name "
                        "WHERE pg_catalog.to_regclass('public.' || name) IS NOT NULL"
                    ),
                    {"names": sorted(new_tables)},
                ).scalars()
            )
            functions_found = set(
                connection.execute(
                    text(
                        "SELECT signature FROM unnest(CAST(:signatures AS text[])) "
                        "AS signature WHERE pg_catalog.to_regprocedure("
                        "'public.' || signature) IS NOT NULL"
                    ),
                    {"signatures": sorted({*guard_function_fragments, writer_signature})},
                ).scalars()
            )
            if not found and not functions_found:
                orphaned = bool(
                    connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger AS trigger "
                            "WHERE NOT trigger.tgisinternal AND "
                            "trigger.tgname=ANY(CAST(:names AS text[])))"
                        ),
                        {"names": sorted({name for name, _ in postgres_trigger_functions})},
                    )
                )
                if orphaned:
                    invalid_boundary()
                return False
            if found != new_tables or functions_found != {
                *guard_function_fragments,
                writer_signature,
            }:
                invalid_boundary()
            for table, expected in required_columns.items():
                columns = set(
                    connection.execute(
                        text(
                            "SELECT attribute.attname FROM pg_catalog.pg_attribute AS attribute "
                            "WHERE attribute.attrelid=pg_catalog.to_regclass(:table) "
                            "AND attribute.attnum>0 AND NOT attribute.attisdropped"
                        ),
                        {"table": f"public.{table}"},
                    ).scalars()
                )
                if not expected.issubset(columns):
                    invalid_boundary()
            constraints = set(
                connection.execute(
                    text(
                        "SELECT constraint_record.conname FROM pg_catalog.pg_constraint "
                        "AS constraint_record WHERE constraint_record.conname="
                        "ANY(CAST(:names AS text[]))"
                    ),
                    {"names": sorted(required_constraints)},
                ).scalars()
            )
            if constraints != required_constraints:
                invalid_boundary()
            hardened = set(
                connection.execute(
                    text(
                        "SELECT relation.relname FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:names AS text[])) "
                        "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                    ),
                    {
                        "names": sorted(
                            all_transport_tables | {"audit_events", "user_notifications"}
                        )
                    },
                ).scalars()
            )
            if hardened != all_transport_tables | {"audit_events", "user_notifications"}:
                invalid_boundary()

            trigger_rows = {
                (str(row.tgname), str(row.relname)): row
                for row in connection.execute(
                    text(
                        "SELECT trigger.tgname,relation.relname,trigger.tgenabled,"
                        "trigger.tgtype,trigger.tgqual,trigger.tgnargs,"
                        "pg_catalog.pg_get_triggerdef(trigger.oid) AS trigger_definition,"
                        "procedure.proname,function_namespace.nspname AS function_schema "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                        "JOIN pg_catalog.pg_namespace AS function_namespace "
                        "ON function_namespace.oid=procedure.pronamespace "
                        "WHERE namespace.nspname='public' AND NOT trigger.tgisinternal "
                        "AND relation.relname=ANY(CAST(:tables AS text[]))"
                    ),
                    {"tables": sorted({table for _, table in postgres_trigger_contracts})},
                )
            }
            if set(trigger_rows) != set(postgres_trigger_contracts):
                invalid_boundary()
            for key, (function_name, events) in postgres_trigger_contracts.items():
                trigger_name, table = key
                row = trigger_rows[key]
                expected_type = 7 if events == "INSERT" else 27
                expected_definition = _compact_sql(
                    f"CREATE TRIGGER {trigger_name} BEFORE {events} ON public.{table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
                )
                if (
                    str(row.tgenabled) != "O"
                    or int(row.tgtype) != expected_type
                    or row.tgqual is not None
                    or int(row.tgnargs) != 0
                    or str(row.proname) != function_name
                    or str(row.function_schema) != "public"
                    or _compact_sql(str(row.trigger_definition or "")) != expected_definition
                ):
                    invalid_boundary()

            function_rows = {
                str(row.signature): row
                for row in connection.execute(
                    text(
                        "SELECT expected.signature,procedure.oid,procedure.provolatile,"
                        "procedure.prosecdef,procedure.proconfig,"
                        "pg_catalog.pg_get_userbyid(procedure.proowner) AS owner_name,"
                        "procedure.prosrc AS function_source,"
                        "pg_catalog.pg_get_functiondef(procedure.oid) AS definition,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner))) "
                        "AS privilege WHERE privilege.grantee=0 "
                        "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                        "COALESCE(pg_catalog.has_function_privilege("
                        "'caresync_basic_app',procedure.oid,'EXECUTE'),false) AS app_execute,"
                        "COALESCE(pg_catalog.has_function_privilege("
                        "'caresync_transport_evidence_ingest',procedure.oid,'EXECUTE'),false) "
                        "AS ingest_execute FROM unnest(CAST(:signatures AS text[])) "
                        "AS expected(signature) LEFT JOIN pg_catalog.pg_proc AS procedure "
                        "ON procedure.oid=pg_catalog.to_regprocedure("
                        "'public.' || expected.signature)"
                    ),
                    {"signatures": sorted(_TRANSPORT_CANONICAL_FUNCTION_SHA256)},
                )
            }
            if set(function_rows) != set(_TRANSPORT_CANONICAL_FUNCTION_SHA256):
                invalid_boundary()
            for signature, expected_hashes in _TRANSPORT_CANONICAL_FUNCTION_SHA256.items():
                row = function_rows[signature]
                observed_hashes = (
                    _canonical_sql_sha256(str(row.function_source or "")),
                    _canonical_sql_sha256(str(row.definition or "")),
                )
                if row.oid is None or observed_hashes != expected_hashes:
                    invalid_boundary()
            for signature, fragments in guard_function_fragments.items():
                row = function_rows[signature]
                definition = str(row.definition or "").lower()
                if (
                    row.oid is None
                    or str(row.provolatile) != "v"
                    or bool(row.prosecdef)
                    or set(row.proconfig or []) != {"search_path=pg_catalog, public"}
                    or bool(row.public_execute)
                    or bool(row.app_execute)
                    or bool(row.ingest_execute)
                    or not all(fragment in definition for fragment in fragments)
                ):
                    invalid_boundary()
            writer = function_rows[writer_signature]
            writer_definition = str(writer.definition or "").lower()
            if (
                writer.oid is None
                or str(writer.owner_name) != "caresync_transport_command_owner"
                or str(writer.provolatile) != "v"
                or not bool(writer.prosecdef)
                or set(writer.proconfig or []) != {"search_path=pg_catalog, public"}
                or bool(writer.public_execute)
                or not bool(writer.app_execute)
                or not bool(writer.ingest_execute)
                or not all(
                    fragment in writer_definition
                    for fragment in (
                        "session_user",
                        "caresync_basic_app",
                        "caresync_transport_evidence_ingest",
                        "transport_request_digest_mismatch",
                        "operational_driver_ready",
                        "dispatch_authorized",
                    )
                )
            ):
                invalid_boundary()

            role_rows = {
                str(row.rolname): row
                for row in connection.execute(
                    text(
                        "SELECT role.oid,role.rolname,role.rolcanlogin,role.rolsuper,"
                        "role.rolbypassrls,role.rolinherit,role.rolcreaterole,"
                        "role.rolcreatedb,role.rolreplication,role.rolconfig,"
                        "EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members AS edge "
                        "WHERE edge.member=role.oid OR edge.roleid=role.oid) AS membership,"
                        "EXISTS(SELECT 1 FROM pg_catalog.pg_db_role_setting AS setting "
                        "WHERE setting.setrole=role.oid AND setting.setdatabase<>0) "
                        "AS database_config FROM pg_catalog.pg_roles AS role "
                        "WHERE role.rolname=ANY(CAST(:roles AS text[]))"
                    ),
                    {
                        "roles": [
                            "caresync_transport_command_owner",
                            "caresync_transport_evidence_ingest",
                        ]
                    },
                )
            }
            if set(role_rows) != {
                "caresync_transport_command_owner",
                "caresync_transport_evidence_ingest",
            }:
                invalid_boundary()
            owner = role_rows["caresync_transport_command_owner"]
            ingest = role_rows["caresync_transport_evidence_ingest"]
            if (
                bool(owner.rolcanlogin)
                or bool(owner.rolsuper)
                or bool(owner.rolbypassrls)
                or bool(owner.rolinherit)
                or bool(owner.rolcreaterole)
                or bool(owner.rolcreatedb)
                or bool(owner.rolreplication)
                or owner.rolconfig is not None
                or bool(owner.membership)
                or bool(owner.database_config)
                or not bool(ingest.rolcanlogin)
                or bool(ingest.rolsuper)
                or bool(ingest.rolbypassrls)
                or bool(ingest.rolinherit)
                or bool(ingest.rolcreaterole)
                or bool(ingest.rolcreatedb)
                or bool(ingest.rolreplication)
                or set(ingest.rolconfig or []) != {"search_path=public, pg_catalog"}
                or bool(ingest.membership)
                or bool(ingest.database_config)
            ):
                invalid_boundary()

            ownership_rows = connection.execute(
                text(
                    "SELECT role.rolname,dependency.dbid,dependency.classid,dependency.objid "
                    "FROM pg_catalog.pg_roles AS role JOIN pg_catalog.pg_shdepend AS dependency "
                    "ON dependency.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass "
                    "AND dependency.refobjid=role.oid AND dependency.deptype='o' "
                    "WHERE role.rolname=ANY(CAST(:roles AS text[]))"
                ),
                {
                    "roles": [
                        "caresync_transport_command_owner",
                        "caresync_transport_evidence_ingest",
                    ]
                },
            ).all()
            owner_objects = [row for row in ownership_rows if row.rolname == owner.rolname]
            ingest_objects = [row for row in ownership_rows if row.rolname == ingest.rolname]
            database_oid = connection.scalar(
                text(
                    "SELECT oid FROM pg_catalog.pg_database "
                    "WHERE datname=pg_catalog.current_database()"
                )
            )
            if ingest_objects or len(owner_objects) != 1:
                invalid_boundary()
            owned = owner_objects[0]
            if (
                int(owned.dbid) != int(database_oid)
                or int(owned.classid)
                != int(connection.scalar(text("SELECT 'pg_catalog.pg_proc'::regclass::oid")))
                or int(owned.objid) != int(writer.oid)
            ):
                invalid_boundary()

            extra_ingest_execute = bool(
                connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_proc AS procedure "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=procedure.pronamespace "
                        "WHERE namespace.nspname !~ '^pg_' "
                        "AND namespace.nspname<>'information_schema' "
                        "AND procedure.oid<>:writer_oid "
                        "AND pg_catalog.has_function_privilege("
                        "'caresync_transport_evidence_ingest',procedure.oid,'EXECUTE'))"
                    ),
                    {"writer_oid": writer.oid},
                )
            )
            extra_owner_execute = bool(
                connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_proc AS procedure "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=procedure.pronamespace "
                        "WHERE namespace.nspname !~ '^pg_' "
                        "AND namespace.nspname<>'information_schema' "
                        "AND procedure.oid<>:writer_oid "
                        "AND pg_catalog.has_function_privilege("
                        "'caresync_transport_command_owner',procedure.oid,'EXECUTE'))"
                    ),
                    {"writer_oid": writer.oid},
                )
            )
            ingest_table_privilege = bool(
                connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname !~ '^pg_' "
                        "AND namespace.nspname<>'information_schema' "
                        "AND relation.relkind IN ('r','p') AND ("
                        "pg_catalog.has_table_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,'SELECT') OR "
                        "pg_catalog.has_table_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,'INSERT') OR "
                        "pg_catalog.has_table_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,'UPDATE') OR "
                        "pg_catalog.has_table_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,'DELETE') OR "
                        "pg_catalog.has_table_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,'TRUNCATE') OR "
                        "pg_catalog.has_table_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,'REFERENCES') OR "
                        "pg_catalog.has_table_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,'TRIGGER') OR "
                        "pg_catalog.has_any_column_privilege("
                        "'caresync_transport_evidence_ingest',relation.oid,"
                        "'SELECT,INSERT,UPDATE,REFERENCES')))"
                    )
                )
            )
            if extra_ingest_execute or extra_owner_execute or ingest_table_privilege:
                invalid_boundary()
            ingest_sequence_privilege = bool(
                connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_class AS sequence "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=sequence.relnamespace "
                        "WHERE namespace.nspname !~ '^pg_' "
                        "AND namespace.nspname<>'information_schema' "
                        "AND sequence.relkind='S' AND ("
                        "pg_catalog.has_sequence_privilege("
                        "'caresync_transport_evidence_ingest',sequence.oid,'USAGE') OR "
                        "pg_catalog.has_sequence_privilege("
                        "'caresync_transport_evidence_ingest',sequence.oid,'SELECT') OR "
                        "pg_catalog.has_sequence_privilege("
                        "'caresync_transport_evidence_ingest',sequence.oid,'UPDATE')))"
                    )
                )
            )
            if ingest_sequence_privilege:
                invalid_boundary()

            owner_acl_rows = connection.execute(
                text(
                    "SELECT relation.relname,"
                    "pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'SELECT') AS can_select,"
                    "pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'INSERT') AS can_insert,"
                    "pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'UPDATE') AS can_update,"
                    "pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'DELETE') AS can_delete,"
                    "pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'TRUNCATE') "
                    "AS can_truncate,pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'REFERENCES') "
                    "AS can_reference,pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'TRIGGER') "
                    "AS can_trigger,pg_catalog.has_any_column_privilege("
                    "'caresync_transport_command_owner',relation.oid,'UPDATE') "
                    "AS can_update_column FROM pg_catalog.pg_class AS relation "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid=relation.relnamespace "
                    "WHERE namespace.nspname !~ '^pg_' "
                    "AND namespace.nspname<>'information_schema' "
                    "AND relation.relkind IN ('r','p')"
                )
            ).all()
            owner_context_tables = {
                "notification_push_subscriptions",
                "users",
                "user_notification_preferences",
                "organizations",
                "organization_memberships",
                "roles",
            }
            owner_row_lock_tables = {
                "users",
                "organizations",
                "organization_memberships",
                "roles",
                "staff_driver_capability_versions",
                "staff_driver_qualification_versions",
                "staff_driver_authorization_decisions",
                "transport_vehicles",
                "transport_vehicle_versions",
                "transport_vehicle_evidence_versions",
            }
            owner_insert_only_tables = {
                "audit_events",
                "notification_deliveries",
                "realtime_events",
                "user_notifications",
                "user_realtime_events",
            }
            for row in owner_acl_rows:
                expected_select = row.relname in owner_context_tables | all_transport_tables
                expected_insert = row.relname in all_transport_tables | owner_insert_only_tables
                expected_update_column = row.relname in owner_row_lock_tables
                if (
                    bool(row.can_select) != expected_select
                    or bool(row.can_insert) != expected_insert
                    or bool(row.can_update)
                    or bool(row.can_delete)
                    or bool(row.can_truncate)
                    or bool(row.can_reference)
                    or bool(row.can_trigger)
                    or bool(row.can_update_column) != expected_update_column
                ):
                    invalid_boundary()
            owner_update_columns: dict[str, set[str]] = {}
            for table_name, column_name in connection.execute(
                text(
                    "SELECT relation.relname,attribute.attname "
                    "FROM pg_catalog.pg_attribute AS attribute "
                    "JOIN pg_catalog.pg_class AS relation "
                    "ON relation.oid=attribute.attrelid "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid=relation.relnamespace "
                    "WHERE namespace.nspname !~ '^pg_' "
                    "AND namespace.nspname<>'information_schema' "
                    "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                    "AND pg_catalog.has_column_privilege("
                    "'caresync_transport_command_owner',attribute.attrelid,"
                    "attribute.attnum,'UPDATE')"
                )
            ):
                owner_update_columns.setdefault(str(table_name), set()).add(str(column_name))
            expected_owner_update_columns = {table: {"id"} for table in owner_row_lock_tables}
            expected_owner_update_columns["transport_vehicles"].update(
                {"retired_at", "retired_by_user_id", "retirement_reason_code"}
            )
            if owner_update_columns != expected_owner_update_columns:
                invalid_boundary()
            owner_arbiter_select_columns: dict[str, set[str]] = {}
            for table_name, column_name in connection.execute(
                text(
                    "SELECT relation.relname,attribute.attname "
                    "FROM pg_catalog.pg_attribute AS attribute "
                    "JOIN pg_catalog.pg_class AS relation "
                    "ON relation.oid=attribute.attrelid "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid=relation.relnamespace "
                    "WHERE namespace.nspname !~ '^pg_' "
                    "AND namespace.nspname<>'information_schema' "
                    "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                    "AND pg_catalog.has_column_privilege("
                    "'caresync_transport_command_owner',attribute.attrelid,"
                    "attribute.attnum,'SELECT') AND NOT pg_catalog.has_table_privilege("
                    "'caresync_transport_command_owner',relation.oid,'SELECT')"
                )
            ):
                owner_arbiter_select_columns.setdefault(str(table_name), set()).add(
                    str(column_name)
                )
            if owner_arbiter_select_columns != {
                "user_realtime_events": {"id"},
                "notification_deliveries": {"notification_id", "subscription_id"},
            }:
                invalid_boundary()
            owner_sequence_rows = connection.execute(
                text(
                    "SELECT namespace.nspname,sequence.relname,"
                    "pg_catalog.has_sequence_privilege("
                    "'caresync_transport_command_owner',sequence.oid,'USAGE') AS can_use,"
                    "pg_catalog.has_sequence_privilege("
                    "'caresync_transport_command_owner',sequence.oid,'SELECT') AS can_select,"
                    "pg_catalog.has_sequence_privilege("
                    "'caresync_transport_command_owner',sequence.oid,'UPDATE') AS can_update "
                    "FROM pg_catalog.pg_class AS sequence "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid=sequence.relnamespace "
                    "WHERE namespace.nspname !~ '^pg_' "
                    "AND namespace.nspname<>'information_schema' "
                    "AND sequence.relkind='S'"
                )
            ).all()
            for row in owner_sequence_rows:
                expected_usage = row.nspname == "public" and row.relname in {
                    "realtime_events_sequence_id_seq",
                    "user_realtime_events_sequence_id_seq",
                }
                if (
                    bool(row.can_use) != expected_usage
                    or bool(row.can_select)
                    or bool(row.can_update)
                ):
                    invalid_boundary()

            transport_acl_rows = connection.execute(
                text(
                    "SELECT expected.name,"
                    "pg_catalog.has_table_privilege('caresync_basic_app',relation.oid,'SELECT') "
                    "AS app_select,"
                    "pg_catalog.has_table_privilege('caresync_basic_app',relation.oid,'INSERT') "
                    "AS app_insert,"
                    "pg_catalog.has_table_privilege('caresync_basic_app',relation.oid,'UPDATE') "
                    "AS app_update,"
                    "pg_catalog.has_table_privilege('caresync_basic_app',relation.oid,'DELETE') "
                    "AS app_delete FROM unnest(CAST(:names AS text[])) AS expected(name) "
                    "LEFT JOIN pg_catalog.pg_class AS relation "
                    "ON relation.oid=pg_catalog.to_regclass('public.' || expected.name)"
                ),
                {"names": sorted(all_transport_tables)},
            ).all()
            if len(transport_acl_rows) != len(all_transport_tables) or any(
                not bool(row.app_select)
                or bool(row.app_insert)
                or bool(row.app_update)
                or bool(row.app_delete)
                for row in transport_acl_rows
            ):
                invalid_boundary()

            policy_rows = {
                (str(row.relname), str(row.polname)): row
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,policy.polname,policy.polcmd,"
                        "policy.polpermissive,policy.polroles,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                        "AS using_expression,"
                        "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                        "AS check_expression FROM pg_catalog.pg_policy AS policy "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=policy.polrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:tables AS text[]))"
                    ),
                    {"tables": sorted(all_transport_tables)},
                )
            }
            expected_policy_keys = {
                (table, f"{table}_select") for table in all_transport_tables
            } | {(table, f"{table}_0032_writer") for table in all_transport_tables}
            if set(policy_rows) != expected_policy_keys:
                invalid_boundary()
            for table in all_transport_tables:
                writer_policy = policy_rows[(table, f"{table}_0032_writer")]
                if (
                    str(writer_policy.polcmd) != "*"
                    or not bool(writer_policy.polpermissive)
                    or tuple(int(role) for role in writer_policy.polroles) != (0,)
                    or not all(
                        _transport_writer_policy_is_exact(expression)
                        for expression in (
                            str(writer_policy.using_expression or ""),
                            str(writer_policy.check_expression or ""),
                        )
                    )
                ):
                    invalid_boundary()
            context_policy_rows = {
                (str(row.relname), str(row.polname)): row
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,policy.polname,policy.polcmd,"
                        "policy.polpermissive,policy.polroles,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                        "AS using_expression,"
                        "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                        "AS check_expression FROM pg_catalog.pg_policy AS policy "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=policy.polrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname=ANY(CAST(:tables AS text[]))"
                    ),
                    {
                        "tables": [
                            "users",
                            "organizations",
                            "organization_memberships",
                            "roles",
                        ]
                    },
                )
            }
            context_policy_tables = {
                "users",
                "organizations",
                "organization_memberships",
                "roles",
            }
            expected_context_policy_keys = {
                (table, f"{table}_0032_lock") for table in context_policy_tables
            } | {(table, f"{table}_0032_lock_no_mutation") for table in context_policy_tables}
            expected_context_table_policy_keys = expected_context_policy_keys | {
                ("organization_memberships", "memberships_identity"),
                ("organizations", "organizations_tenant"),
                ("roles", "roles_tenant"),
            }
            if set(context_policy_rows) != expected_context_table_policy_keys:
                invalid_boundary()
            for table, policy_name in expected_context_policy_keys:
                policy = context_policy_rows[(table, policy_name)]
                if (
                    str(policy.polcmd) != "w"
                    or tuple(int(role) for role in policy.polroles) != (0,)
                    or not _transport_context_lock_policy_is_exact(
                        table=table,
                        policy_name=policy_name,
                        permissive=bool(policy.polpermissive),
                        using_expression=str(policy.using_expression or ""),
                        check_expression=str(policy.check_expression or ""),
                    )
                ):
                    invalid_boundary()
            for table in new_tables:
                select_policy = policy_rows[(table, f"{table}_select")]
                if str(select_policy.polcmd) != "r" or "app.current_organization_id" not in str(
                    select_policy.using_expression or ""
                ):
                    invalid_boundary()
            side_effect_rows = {
                str(row.relname): row
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,policy.polcmd,"
                        "policy.polpermissive,policy.polroles,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                        "AS using_expression,"
                        "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                        "AS check_expression FROM pg_catalog.pg_policy AS policy "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=policy.polrelid "
                        "WHERE policy.polname=relation.relname || '_0032_writer' "
                        "AND relation.relname IN ('audit_events','user_notifications')"
                    )
                )
            }
            if set(side_effect_rows) != {"audit_events", "user_notifications"}:
                invalid_boundary()
            for row in side_effect_rows.values():
                if (
                    str(row.polcmd) != "*"
                    or not bool(row.polpermissive)
                    or tuple(int(role) for role in row.polroles) != (0,)
                    or not all(
                        _transport_writer_policy_is_exact(expression)
                        for expression in (
                            str(row.using_expression or ""),
                            str(row.check_expression or ""),
                        )
                    )
                ):
                    invalid_boundary()

            downstream_triggers = {
                (str(row.relname), str(row.tgname)): row
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,trigger.tgname,trigger.tgenabled,"
                        "pg_catalog.pg_get_triggerdef(trigger.oid) AS trigger_definition,"
                        "procedure.proname,procedure.prosecdef,procedure.provolatile,"
                        "procedure.proconfig,pg_catalog.pg_get_userbyid(procedure.proowner) "
                        "AS owner_name,function_namespace.nspname AS function_schema,"
                        "pg_catalog.pg_get_function_result(procedure.oid) "
                        "AS result_type,procedure.prosrc AS function_source,"
                        "EXISTS(SELECT 1 FROM "
                        "pg_catalog.aclexplode(COALESCE(procedure.proacl,"
                        "pg_catalog.acldefault('f',procedure.proowner))) AS privilege "
                        "WHERE privilege.grantee=0 AND privilege.privilege_type='EXECUTE') "
                        "AS public_execute,pg_catalog.has_function_privilege("
                        "'caresync_basic_app',procedure.oid,'EXECUTE') AS app_execute,"
                        "pg_catalog.has_function_privilege("
                        "'caresync_transport_evidence_ingest',procedure.oid,'EXECUTE') "
                        "AS ingest_execute,pg_catalog.has_function_privilege("
                        "'caresync_transport_command_owner',procedure.oid,'EXECUTE') "
                        "AS owner_execute FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                        "JOIN pg_catalog.pg_namespace AS function_namespace "
                        "ON function_namespace.oid=procedure.pronamespace "
                        "WHERE namespace.nspname='public' AND NOT trigger.tgisinternal "
                        "AND relation.relname IN ('audit_events','user_notifications')"
                    )
                )
            }
            expected_downstream_triggers = {
                ("audit_events", "audit_events_realtime"),
                ("user_notifications", "user_notifications_push_realtime"),
            }
            if set(downstream_triggers) != expected_downstream_triggers:
                invalid_boundary()
            audit_trigger = downstream_triggers[("audit_events", "audit_events_realtime")]
            notification_trigger = downstream_triggers[
                ("user_notifications", "user_notifications_push_realtime")
            ]
            audit_trigger_definition = _compact_sql(str(audit_trigger.trigger_definition or ""))
            notification_trigger_definition = _compact_sql(
                str(notification_trigger.trigger_definition or "")
            )
            terminal_function_acl_fields = (
                "public_execute",
                "app_execute",
                "ingest_execute",
                "owner_execute",
            )
            if not (
                audit_trigger.tgenabled == "O"
                and audit_trigger.proname == "realtime_from_audit_event"
                and audit_trigger.function_schema == "public"
                and not audit_trigger.prosecdef
                and audit_trigger.provolatile == "v"
                and set(audit_trigger.proconfig or []) == {"search_path=pg_catalog, public"}
                and audit_trigger.owner_name
                not in {
                    "caresync_basic_app",
                    "caresync_transport_command_owner",
                    "caresync_transport_evidence_ingest",
                }
                and str(audit_trigger.result_type).lower() == "trigger"
                and not any(
                    bool(getattr(audit_trigger, field)) for field in terminal_function_acl_fields
                )
                and "afterinsertonpublic.audit_eventsforeachrow" in audit_trigger_definition
                and "when(" not in audit_trigger_definition
                and _transport_audit_realtime_bridge_is_hardened(
                    str(audit_trigger.function_source or "")
                )
            ):
                invalid_boundary()
            if not (
                notification_trigger.tgenabled == "O"
                and notification_trigger.proname == "user_notification_enqueue_trigger"
                and notification_trigger.function_schema == "public"
                and not notification_trigger.prosecdef
                and notification_trigger.provolatile == "v"
                and set(notification_trigger.proconfig or []) == {"search_path=pg_catalog"}
                and notification_trigger.owner_name
                not in {
                    "caresync_basic_app",
                    "caresync_transport_command_owner",
                    "caresync_transport_evidence_ingest",
                }
                and str(notification_trigger.result_type).lower() == "trigger"
                and not any(
                    bool(getattr(notification_trigger, field))
                    for field in terminal_function_acl_fields
                )
                and "afterinsertonpublic.user_notificationsforeachrow"
                in notification_trigger_definition
                and "when(" not in notification_trigger_definition
                and _notification_enqueue_trigger_is_hardened(
                    str(notification_trigger.function_source or "")
                )
            ):
                invalid_boundary()

            downstream_hardened = set(
                connection.execute(
                    text(
                        "SELECT relation.relname FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' AND relation.relname IN "
                        "('user_realtime_events','notification_deliveries') "
                        "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                    )
                ).scalars()
            )
            if downstream_hardened != {
                "user_realtime_events",
                "notification_deliveries",
            }:
                invalid_boundary()
            downstream_insert_policies = {
                (str(row.relname), str(row.polname)): row
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,policy.polname,policy.polcmd,"
                        "policy.polpermissive,policy.polroles,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) "
                        "AS using_expression,pg_catalog.pg_get_expr("
                        "policy.polwithcheck,policy.polrelid) AS check_expression "
                        "FROM pg_catalog.pg_policy AS policy "
                        "JOIN pg_catalog.pg_class AS relation ON relation.oid=policy.polrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' AND relation.relname IN "
                        "('user_realtime_events','notification_deliveries') "
                        "AND policy.polcmd IN ('a','*')"
                    )
                )
            }
            expected_downstream_policies = {
                (
                    "user_realtime_events",
                    "user_realtime_events_context_insert",
                ),
                (
                    "notification_deliveries",
                    "notification_deliveries_context_insert",
                ),
            }
            if set(downstream_insert_policies) != expected_downstream_policies:
                invalid_boundary()
            for policy in downstream_insert_policies.values():
                if not (
                    policy.polcmd == "a"
                    and bool(policy.polpermissive)
                    and tuple(int(role) for role in policy.polroles) == (0,)
                    and policy.using_expression is None
                    and _notification_context_insert_policy_is_exact(
                        str(policy.check_expression or "")
                    )
                ):
                    invalid_boundary()
            return True

    def has_family_authority_kernel(self) -> bool:
        """Return true only when every 0029A authority table is present."""

        table_names = (
            "family_authority_people",
            "family_authority_person_versions",
            "family_authority_evidence",
            "family_authority_evidence_assessments",
            "child_authority_heads",
            "child_release_authorizations",
            "child_release_rules",
            "consent_policy_versions",
            "child_consent_decisions",
            "attendance_release_snapshots",
        )
        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                found = connection.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name IN "
                        "('family_authority_people','family_authority_person_versions',"
                        "'family_authority_evidence','family_authority_evidence_assessments',"
                        "'child_authority_heads',"
                        "'child_release_authorizations','child_release_rules',"
                        "'consent_policy_versions','child_consent_decisions',"
                        "'attendance_release_snapshots')"
                    )
                ).scalars()
            else:
                found = connection.execute(
                    text(
                        "SELECT name FROM unnest(CAST(:names AS text[])) AS name "
                        "WHERE pg_catalog.to_regclass('public.' || name) IS NOT NULL"
                    ),
                    {"names": list(table_names)},
                ).scalars()
            return set(found) == set(table_names)

    def has_family_evidence_vault(self) -> bool:
        """Return true only for the complete post-0029A private object boundary."""

        required_tables = {
            "family_authority_evidence_objects",
            "family_authority_evidence_object_assessments",
        }
        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                found = set(
                    connection.execute(
                        text(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                            "('family_authority_evidence_objects',"
                            "'family_authority_evidence_object_assessments')"
                        )
                    ).scalars()
                )
                evidence_columns = {
                    str(row[1])
                    for row in connection.exec_driver_sql(
                        "PRAGMA table_info('family_authority_evidence')"
                    )
                }
            else:
                found = set(
                    connection.execute(
                        text(
                            "SELECT name FROM unnest(CAST(:names AS text[])) AS name "
                            "WHERE pg_catalog.to_regclass('public.' || name) IS NOT NULL"
                        ),
                        {"names": sorted(required_tables)},
                    ).scalars()
                )
                evidence_columns = set(
                    connection.execute(
                        text(
                            "SELECT attname FROM pg_catalog.pg_attribute "
                            "WHERE attrelid='public.family_authority_evidence'::regclass "
                            "AND attnum>0 AND NOT attisdropped"
                        )
                    ).scalars()
                )
                hardened_relations = set(
                    connection.execute(
                        text(
                            "SELECT relation.relname FROM pg_catalog.pg_class relation "
                            "JOIN pg_catalog.pg_namespace namespace "
                            "ON namespace.oid=relation.relnamespace "
                            "WHERE namespace.nspname='public' "
                            "AND relation.relname IN "
                            "('family_authority_evidence_objects',"
                            "'family_authority_evidence_object_assessments') "
                            "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                        )
                    ).scalars()
                )
                trigger_rows = set(
                    connection.execute(
                        text(
                            "SELECT relation.relname,trigger.tgname,procedure.proname "
                            "FROM pg_catalog.pg_trigger trigger "
                            "JOIN pg_catalog.pg_class relation "
                            "ON relation.oid=trigger.tgrelid "
                            "JOIN pg_catalog.pg_namespace namespace "
                            "ON namespace.oid=relation.relnamespace "
                            "JOIN pg_catalog.pg_proc procedure "
                            "ON procedure.oid=trigger.tgfoid "
                            "WHERE namespace.nspname='public' AND NOT trigger.tgisinternal "
                            "AND trigger.tgenabled<>'D'"
                        )
                    )
                )
                expected_triggers = (
                    {
                        (
                            table_name,
                            f"trg_{table_name}_write_guard",
                            "caresync_family_evidence_object_write_guard",
                        )
                        for table_name in required_tables
                    }
                    | {
                        (
                            table_name,
                            f"trg_{table_name}_invariant",
                            "caresync_family_evidence_object_invariant",
                        )
                        for table_name in required_tables
                    }
                    | {
                        (
                            "family_authority_evidence",
                            "trg_family_authority_evidence_aaa_object_link_guard",
                            "caresync_family_evidence_object_link_guard",
                        ),
                        (
                            "family_authority_evidence",
                            "trg_family_authority_evidence_zzz_object_link_guard",
                            "caresync_family_evidence_object_link_guard",
                        ),
                        (
                            "family_authority_evidence_assessments",
                            "trg_family_authority_evidence_assessments_review_guard",
                            "caresync_family_evidence_review_guard",
                        ),
                    }
                )
                policy_rows = set(
                    connection.execute(
                        text(
                            "SELECT tablename,policyname FROM pg_catalog.pg_policies "
                            "WHERE schemaname='public' AND tablename IN "
                            "('family_authority_evidence_objects',"
                            "'family_authority_evidence_object_assessments') "
                            "AND qual LIKE "
                            "'%caresync_family_authority_actor_is_privileged%' "
                            "AND with_check LIKE "
                            "'%caresync_family_authority_actor_is_privileged%'"
                        )
                    )
                )
                expected_policies = {
                    (table_name, f"{table_name}_privileged_actor") for table_name in required_tables
                }
                postgres_boundary_ready = (
                    hardened_relations == required_tables
                    and expected_triggers <= trigger_rows
                    and expected_policies <= policy_rows
                )
        return (
            found == required_tables
            and "evidence_object_id" in evidence_columns
            and (self.settings.database_type == "sqlite" or postgres_boundary_ready)
        )

    def has_family_authority_activation(self) -> bool:
        """Return true only for the complete, hardened 0029A2 boundary."""

        activation_tables = {
            "child_release_authorizations",
            "child_release_rules",
            "consent_policy_versions",
            "child_consent_decisions",
        }
        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                table_sql = {
                    str(row[0]): str(row[1] or "").lower()
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master "
                            "WHERE type='table' AND name IN "
                            "('family_authority_evidence_objects',"
                            "'family_authority_evidence',"
                            "'child_release_authorizations','child_release_rules',"
                            "'consent_policy_versions','child_consent_decisions')"
                        )
                    )
                }
                policy_columns = {
                    str(row[1])
                    for row in connection.exec_driver_sql(
                        "PRAGMA table_info('consent_policy_versions')"
                    )
                }
                decision_columns = {
                    str(row[1])
                    for row in connection.exec_driver_sql(
                        "PRAGMA table_info('child_consent_decisions')"
                    )
                }
                normalized = {
                    name: "".join(sql.split()).replace('"', "") for name, sql in table_sql.items()
                }
                audit_bridge_sql = "".join(
                    str(
                        connection.scalar(
                            text(
                                "SELECT sql FROM sqlite_master "
                                "WHERE type='trigger' "
                                "AND name='audit_events_realtime'"
                            )
                        )
                        or ""
                    )
                    .lower()
                    .split()
                ).replace('"', "")
                return (
                    activation_tables <= set(table_sql)
                    and "content_text" in policy_columns
                    and {
                        "signer_authority_evidence_id",
                        "signer_authority_evidence_assessment_id",
                    }
                    <= decision_columns
                    and "signed_release_delegation"
                    in normalized.get("family_authority_evidence_objects", "")
                    and "signed_release_delegation"
                    in normalized.get("family_authority_evidence", "")
                    and "constraintck_release_authorizations_grantor_basischeck("
                    "grantor_authority_basisin('guardian_record',"
                    "'reviewed_custody_evidence','reviewed_delegation_evidence'))"
                    in normalized.get("child_release_authorizations", "")
                    and "constraintck_release_rules_kindcheck(rule_kindin('deny','manager_review'))"
                    in normalized.get("child_release_rules", "")
                    and "constraintck_release_rules_authority_basischeck("
                    "authority_basis_codein('guardian_record',"
                    "'reviewed_custody_evidence'))"
                    in normalized.get("child_release_rules", "")
                    and "constraintck_consent_policy_versions_signercheck("
                    "signer_authority_requirementin('guardian_record',"
                    "'legal_decision_maker'))"
                    in normalized.get("consent_policy_versions", "")
                    and "constraintck_child_consent_decisions_signer_basischeck("
                    "signer_authority_basisin('guardian_record',"
                    "'reviewed_custody_evidence'))"
                    in normalized.get("child_consent_decisions", "")
                    and "evidence_id<>signer_authority_evidence_id"
                    in normalized.get("child_consent_decisions", "")
                    and all(
                        f"new.actionnotlike'{prefix}%'" in audit_bridge_sql
                        for prefix in (
                            "family.authority.",
                            "child.release.",
                            "child.consent.",
                            "organization.consent.",
                        )
                    )
                )

            required_columns = {
                str(row[0])
                for row in connection.execute(
                    text(
                        "SELECT attribute.attname "
                        "FROM pg_catalog.pg_attribute AS attribute "
                        "WHERE attribute.attrelid="
                        "pg_catalog.to_regclass('public.child_consent_decisions') "
                        "AND attribute.attnum>0 AND NOT attribute.attisdropped"
                    )
                )
            }
            policy_columns = {
                str(row[0])
                for row in connection.execute(
                    text(
                        "SELECT attribute.attname "
                        "FROM pg_catalog.pg_attribute AS attribute "
                        "WHERE attribute.attrelid="
                        "pg_catalog.to_regclass('public.consent_policy_versions') "
                        "AND attribute.attnum>0 AND NOT attribute.attisdropped"
                    )
                )
            }
            function_row = connection.execute(
                text(
                    "SELECT procedure.prosecdef,procedure.proconfig,"
                    "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=0 "
                    "AND privilege.privilege_type='EXECUTE'),"
                    "pg_catalog.pg_get_functiondef(procedure.oid) "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.caresync_family_authority_activation_guard()')"
                )
            ).one_or_none()
            audit_bridge_row = connection.execute(
                text(
                    "SELECT procedure.proconfig,"
                    "pg_catalog.pg_get_functiondef(procedure.oid) "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.realtime_from_audit_event()')"
                )
            ).one_or_none()
            trigger_rows = set(
                connection.execute(
                    text(
                        "SELECT relation.relname,trigger.tgname,procedure.proname "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN pg_catalog.pg_proc AS procedure "
                        "ON procedure.oid=trigger.tgfoid "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname IN "
                        "('child_release_authorizations','child_release_rules',"
                        "'consent_policy_versions','child_consent_decisions') "
                        "AND NOT trigger.tgisinternal AND trigger.tgenabled<>'D'"
                    )
                )
            )
            expected_triggers = {
                (
                    table_name,
                    f"trg_{table_name}_activation_guard",
                    "caresync_family_authority_activation_guard",
                )
                for table_name in activation_tables
            }
            hardened_relations = set(
                connection.execute(
                    text(
                        "SELECT relation.relname FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname IN "
                        "('child_release_authorizations','child_release_rules',"
                        "'consent_policy_versions','child_consent_decisions') "
                        "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                    )
                ).scalars()
            )
            constraint_definitions = {
                str(row[0]): "".join(str(row[1]).lower().split()).replace('"', "")
                for row in connection.execute(
                    text(
                        "SELECT constraint_record.conname,"
                        "pg_catalog.pg_get_constraintdef(constraint_record.oid) "
                        "FROM pg_catalog.pg_constraint AS constraint_record "
                        "WHERE constraint_record.conname IN "
                        "('ck_authority_evidence_objects_kind',"
                        "'ck_authority_evidence_kind',"
                        "'ck_release_authorizations_grantor_basis',"
                        "'ck_release_rules_kind','ck_release_rules_authority_basis',"
                        "'ck_consent_policy_versions_signer',"
                        "'ck_consent_policy_versions_content',"
                        "'ck_child_consent_decisions_signer_basis',"
                        "'ck_child_consent_decisions_distinct_evidence')"
                    )
                )
            }
            privileges_ready = bool(
                connection.execute(
                    text(
                        "WITH runtime_role(rolname) AS ("
                        "SELECT rolname FROM pg_catalog.pg_roles "
                        "WHERE rolname='caresync_basic_app'"
                        "), activation_tables(relname) AS (VALUES "
                        "('child_release_authorizations'),('child_release_rules'),"
                        "('consent_policy_versions'),('child_consent_decisions')"
                        "), protected_tables(relname) AS ("
                        "SELECT relname FROM activation_tables UNION ALL "
                        "SELECT 'attendance_release_snapshots'"
                        "), expected_updates(relname,attname) AS (VALUES "
                        "('child_release_authorizations','version'),"
                        "('child_release_authorizations','revoked_at'),"
                        "('child_release_authorizations','revoked_operation_id'),"
                        "('child_release_authorizations','revocation_reason_code'),"
                        "('child_release_authorizations','updated_at'),"
                        "('child_release_rules','version'),"
                        "('child_release_rules','revoked_at'),"
                        "('child_release_rules','revoked_operation_id'),"
                        "('child_release_rules','revocation_reason_code'),"
                        "('child_release_rules','updated_at'),"
                        "('child_consent_decisions','version'),"
                        "('child_consent_decisions','withdrawn_at'),"
                        "('child_consent_decisions','withdrawn_operation_id'),"
                        "('child_consent_decisions','withdrawal_reason_code'),"
                        "('child_consent_decisions','updated_at')"
                        "), relations AS ("
                        "SELECT relation.oid,relation.relname "
                        "FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN protected_tables AS protected "
                        "ON protected.relname=relation.relname "
                        "WHERE namespace.nspname='public'"
                        ") SELECT EXISTS(SELECT 1 FROM runtime_role) "
                        "AND NOT EXISTS ("
                        "SELECT 1 FROM activation_tables AS activation "
                        "CROSS JOIN runtime_role AS role "
                        "LEFT JOIN relations AS relation "
                        "ON relation.relname=activation.relname "
                        "WHERE relation.oid IS NULL "
                        "OR NOT pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'SELECT') "
                        "OR NOT pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'INSERT') "
                        "OR pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'UPDATE') "
                        "OR pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'DELETE')"
                        ") AND NOT EXISTS ("
                        "SELECT 1 FROM runtime_role AS role "
                        "LEFT JOIN relations AS relation "
                        "ON relation.relname='attendance_release_snapshots' "
                        "WHERE relation.oid IS NULL "
                        "OR NOT pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'SELECT') "
                        "OR pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'INSERT') "
                        "OR pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'UPDATE') "
                        "OR pg_catalog.has_table_privilege("
                        "role.rolname,relation.oid,'DELETE')"
                        ") AND NOT EXISTS ("
                        "SELECT 1 FROM relations AS relation "
                        "JOIN pg_catalog.pg_attribute AS attribute "
                        "ON attribute.attrelid=relation.oid "
                        "CROSS JOIN runtime_role AS role "
                        "WHERE attribute.attnum>0 AND NOT attribute.attisdropped "
                        "AND pg_catalog.has_column_privilege("
                        "role.rolname,relation.oid,attribute.attnum,'UPDATE') "
                        "IS DISTINCT FROM EXISTS ("
                        "SELECT 1 FROM expected_updates AS expected "
                        "WHERE expected.relname=relation.relname "
                        "AND expected.attname=attribute.attname)"
                        ") AND NOT EXISTS ("
                        "SELECT 1 FROM expected_updates AS expected "
                        "LEFT JOIN relations AS relation "
                        "ON relation.relname=expected.relname "
                        "LEFT JOIN pg_catalog.pg_attribute AS attribute "
                        "ON attribute.attrelid=relation.oid "
                        "AND attribute.attname=expected.attname "
                        "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                        "WHERE attribute.attnum IS NULL"
                        ") AND NOT COALESCE((SELECT "
                        "pg_catalog.has_function_privilege("
                        "role.rolname,pg_catalog.to_regprocedure("
                        "'public.caresync_family_authority_activation_guard()'),"
                        "'EXECUTE') FROM runtime_role AS role),true)"
                    )
                ).scalar_one()
            )
            function_hardened = False
            if function_row is not None:
                search_path = {str(setting).replace(" ", "") for setting in (function_row[1] or [])}
                function_hardened = bool(
                    function_row[0]
                    and "search_path=pg_catalog,public" in search_path
                    and not function_row[2]
                    and "content_sha256" in str(function_row[3])
                    and "sha256" in str(function_row[3])
                )
            audit_bridge_hardened = False
            if audit_bridge_row is not None:
                bridge_search_path = {
                    str(setting).replace(" ", "") for setting in (audit_bridge_row[0] or [])
                }
                bridge_definition = str(audit_bridge_row[1]).lower()
                audit_bridge_hardened = bool(
                    "search_path=pg_catalog,public" in bridge_search_path
                    and "return new" in bridge_definition
                    and all(
                        f"'{prefix}%'" in bridge_definition
                        for prefix in (
                            "family.authority.",
                            "child.release.",
                            "child.consent.",
                            "organization.consent.",
                        )
                    )
                )
            return (
                {
                    "signer_authority_evidence_id",
                    "signer_authority_evidence_assessment_id",
                }
                <= required_columns
                and "content_text" in policy_columns
                and privileges_ready
                and function_hardened
                and audit_bridge_hardened
                and expected_triggers <= trigger_rows
                and hardened_relations == activation_tables
                and "signed_release_delegation"
                in constraint_definitions.get("ck_authority_evidence_objects_kind", "")
                and "signed_release_delegation"
                in constraint_definitions.get("ck_authority_evidence_kind", "")
                and "other_reviewed_authority"
                not in constraint_definitions.get("ck_release_authorizations_grantor_basis", "")
                and "supervised_only" not in constraint_definitions.get("ck_release_rules_kind", "")
                and "named_recipient_only"
                not in constraint_definitions.get("ck_release_rules_kind", "")
                and "specific_reviewed_authority"
                not in constraint_definitions.get("ck_consent_policy_versions_signer", "")
                and "content_text"
                in constraint_definitions.get("ck_consent_policy_versions_content", "")
                and "evidence_id<>signer_authority_evidence_id"
                in constraint_definitions.get("ck_child_consent_decisions_distinct_evidence", "")
            )

    def has_family_authority_release_context(self) -> bool:
        """Return true only for the complete hardened 0029B read boundary."""

        if not self.has_family_authority_activation():
            return False

        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                # SQLite has no RLS identity boundary, so readiness can verify
                # concrete system-role data. PostgreSQL startup intentionally
                # has no tenant GUC and the runtime role has no broad roles
                # SELECT; its detector therefore remains catalog-only.
                role_rows = list(
                    connection.execute(
                        text(
                            "SELECT key,permissions FROM roles "
                            "WHERE is_system=:is_system AND key IN "
                            "('owner','administrator','educator')"
                        ),
                        {"is_system": True},
                    )
                )
                for row in role_rows:
                    permissions = row.permissions
                    if isinstance(permissions, str):
                        try:
                            permissions = json.loads(permissions)
                        except json.JSONDecodeError:
                            return False
                    if not isinstance(permissions, list) or "release:read" not in permissions:
                        return False
                trigger_sql = {
                    str(row.name): "".join(str(row.sql or "").lower().split()).replace('"', "")
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                            "AND name IN "
                            "('child_authority_heads_release_context_insert',"
                            "'child_authority_heads_release_context_update')"
                        )
                    )
                }
                insert_sql = trigger_sql.get("child_authority_heads_release_context_insert", "")
                update_sql = trigger_sql.get("child_authority_heads_release_context_update", "")
                exact_event_tail = (
                    "new.organization_id,"
                    "'family_authority.release_context_invalidated',"
                    "'child_authority_head',null,current_timestamp,"
                    "json_object('source','authority_head','scope','release_context'))"
                )
                return bool(
                    "afterinsertonchild_authority_heads" in insert_sql
                    and "afterupdateofrevisiononchild_authority_heads" in update_sql
                    and "whenold.revisionisnotnew.revision" in update_sql
                    and exact_event_tail in insert_sql
                    and exact_event_tail in update_sql
                    and "new.child_id" not in insert_sql
                    and "new.child_id" not in update_sql
                    and "new.family_id" not in insert_sql
                    and "new.family_id" not in update_sql
                )

            projection_row = connection.execute(
                text(
                    "SELECT procedure.prosecdef AS security_definer,"
                    "procedure.proconfig AS configuration,"
                    "owner_role.rolname AS owner_name,"
                    "pg_catalog.pg_get_function_result(procedure.oid) AS result_type,"
                    "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=0 "
                    "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                    "COALESCE(pg_catalog.has_function_privilege("
                    "runtime_role.rolname,procedure.oid,'EXECUTE'),false) "
                    "AS runtime_execute,"
                    "(runtime_role.oid IS NOT NULL "
                    "AND EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=procedure.proowner "
                    "AND privilege.privilege_type='EXECUTE') "
                    "AND EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=runtime_role.oid "
                    "AND privilege.privilege_type='EXECUTE' "
                    "AND NOT privilege.is_grantable) "
                    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.privilege_type<>'EXECUTE' "
                    "OR privilege.grantee NOT IN "
                    "(procedure.proowner,runtime_role.oid) "
                    "OR privilege.grantor<>procedure.proowner "
                    "OR (privilege.grantee=runtime_role.oid "
                    "AND privilege.is_grantable))) AS acl_exact,"
                    "pg_catalog.pg_get_functiondef(procedure.oid) AS function_definition "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "JOIN pg_catalog.pg_roles AS owner_role "
                    "ON owner_role.oid=procedure.proowner "
                    "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                    "ON runtime_role.rolname='caresync_basic_app' "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.caresync_family_release_context_inputs(uuid,uuid)')"
                )
            ).one_or_none()
            trigger_function_row = connection.execute(
                text(
                    "SELECT procedure.prosecdef AS security_definer,"
                    "procedure.proconfig AS configuration,"
                    "owner_role.rolname AS owner_name,"
                    "pg_catalog.pg_get_function_result(procedure.oid) AS result_type,"
                    "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=0 "
                    "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                    "COALESCE(pg_catalog.has_function_privilege("
                    "runtime_role.rolname,procedure.oid,'EXECUTE'),false) "
                    "AS runtime_execute,"
                    "(EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=procedure.proowner "
                    "AND privilege.privilege_type='EXECUTE') "
                    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.privilege_type<>'EXECUTE' "
                    "OR privilege.grantee<>procedure.proowner "
                    "OR privilege.grantor<>procedure.proowner)) AS acl_exact,"
                    "pg_catalog.pg_get_functiondef(procedure.oid) AS function_definition "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "JOIN pg_catalog.pg_roles AS owner_role "
                    "ON owner_role.oid=procedure.proowner "
                    "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                    "ON runtime_role.rolname='caresync_basic_app' "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.caresync_release_context_from_authority_head()')"
                )
            ).one_or_none()
            trigger_row = connection.execute(
                text(
                    "SELECT trigger.tgenabled AS enabled,"
                    "pg_catalog.pg_get_triggerdef(trigger.oid) AS trigger_definition "
                    "FROM pg_catalog.pg_trigger AS trigger "
                    "WHERE trigger.tgrelid=pg_catalog.to_regclass("
                    "'public.child_authority_heads') "
                    "AND trigger.tgname="
                    "'child_authority_heads_release_context_invalidated' "
                    "AND NOT trigger.tgisinternal"
                )
            ).one_or_none()
            verification_policy_width_ready = bool(
                connection.scalar(
                    text(
                        "SELECT attribute.atttypid="
                        "pg_catalog.to_regtype('character varying') "
                        "AND attribute.atttypmod=68 "
                        "FROM pg_catalog.pg_attribute AS attribute "
                        "WHERE attribute.attrelid=pg_catalog.to_regclass("
                        "'public.child_release_authorizations') "
                        "AND attribute.attname='verification_policy_code' "
                        "AND attribute.attnum>0 AND NOT attribute.attisdropped"
                    )
                )
            )
            if projection_row is None or trigger_function_row is None or trigger_row is None:
                return False

            projection_search_path = {
                str(setting).replace(" ", "") for setting in (projection_row.configuration or [])
            }
            trigger_search_path = {
                str(setting).replace(" ", "")
                for setting in (trigger_function_row.configuration or [])
            }
            return bool(
                verification_policy_width_ready
                and projection_row.security_definer
                and projection_row.owner_name != "caresync_basic_app"
                and str(projection_row.result_type).lower() == "jsonb"
                and not projection_row.public_execute
                and projection_row.runtime_execute
                and projection_row.acl_exact
                and len(projection_row.configuration or []) == 1
                and projection_search_path == {"search_path=pg_catalog,public"}
                and _release_context_projection_definition_is_hardened(
                    str(projection_row.function_definition)
                )
                and trigger_function_row.security_definer
                and trigger_function_row.owner_name != "caresync_basic_app"
                and str(trigger_function_row.result_type).lower() == "trigger"
                and not trigger_function_row.public_execute
                and not trigger_function_row.runtime_execute
                and trigger_function_row.acl_exact
                and len(trigger_function_row.configuration or []) == 1
                and trigger_search_path == {"search_path=pg_catalog,public"}
                and trigger_row.enabled == "O"
                and _release_context_invalidation_definitions_are_hardened(
                    str(trigger_function_row.function_definition),
                    str(trigger_row.trigger_definition),
                )
            )

    def has_family_release_checkout_foundation(
        self,
        *,
        release_context_present: bool | None = None,
    ) -> bool:
        """Return true only for the complete dormant 0029C data boundary."""

        if release_context_present is None:
            release_context_present = self.has_family_authority_release_context()
        if not release_context_present:
            return False

        activation_columns_expected = {
            "id": ("UUID", True, 1),
            "organization_id": ("UUID", True, 0),
            "facility_id": ("UUID", True, 0),
            "activated_by_user_id": ("UUID", True, 0),
            "activated_by_membership_id": ("UUID", True, 0),
            "activated_by_role_id": ("UUID", True, 0),
            "activated_by_role_key": ("VARCHAR(50)", True, 0),
            "activation_operation_id": ("UUID", True, 0),
            "activation_policy_version": ("VARCHAR(40)", True, 0),
            "activated_at": ("DATETIME", True, 0),
        }
        snapshot_columns_expected = {
            "recipient_display_name": ("VARCHAR(302)", True, 0),
            "attendance_day_version": ("INTEGER", True, 0),
            "verification_policy_code": ("VARCHAR(64)", True, 0),
            "actor_membership_id": ("UUID", True, 0),
            "actor_role_id": ("UUID", True, 0),
            "actor_role_key": ("VARCHAR(50)", True, 0),
            "staff_shift_id": ("UUID", True, 0),
            "room_id": ("UUID", True, 0),
            "scope_basis": ("VARCHAR(32)", True, 0),
            "room_assignment_id": ("UUID", False, 0),
            "checked_out_at": ("DATETIME", True, 0),
        }
        with self.engine.connect() as connection:
            if self.settings.database_type == "sqlite":
                tables = {
                    str(row.name): str(row.sql or "")
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master WHERE type='table' "
                            "AND name IN "
                            "('facility_release_checkout_activations',"
                            "'attendance_release_snapshots','childcare_command_receipts')"
                        )
                    )
                }
                if set(tables) != {
                    "facility_release_checkout_activations",
                    "attendance_release_snapshots",
                    "childcare_command_receipts",
                }:
                    return False

                activation_columns = _sqlite_column_manifest(
                    connection, "facility_release_checkout_activations"
                )
                snapshot_columns = _sqlite_column_manifest(
                    connection, "attendance_release_snapshots"
                )
                sqlite_activation_columns_expected = {
                    name: (
                        "CHAR(32)" if specification[0] == "UUID" else specification[0],
                        specification[1],
                        specification[2],
                    )
                    for name, specification in activation_columns_expected.items()
                }
                sqlite_snapshot_columns_expected = {
                    name: (
                        "CHAR(32)" if specification[0] == "UUID" else specification[0],
                        specification[1],
                        specification[2],
                    )
                    for name, specification in snapshot_columns_expected.items()
                }
                if activation_columns != sqlite_activation_columns_expected or any(
                    snapshot_columns.get(name) != specification
                    for name, specification in sqlite_snapshot_columns_expected.items()
                ):
                    return False

                activation_foreign_keys_expected = {
                    (
                        "childcare_command_receipts",
                        ("organization_id", "activation_operation_id"),
                        ("organization_id", "client_operation_id"),
                        "NO ACTION",
                        "RESTRICT",
                        "NONE",
                    ),
                    (
                        "facilities",
                        ("organization_id", "facility_id"),
                        ("organization_id", "id"),
                        "NO ACTION",
                        "RESTRICT",
                        "NONE",
                    ),
                    (
                        "organization_memberships",
                        ("organization_id", "activated_by_membership_id"),
                        ("organization_id", "id"),
                        "NO ACTION",
                        "RESTRICT",
                        "NONE",
                    ),
                    (
                        "roles",
                        ("organization_id", "activated_by_role_id"),
                        ("organization_id", "id"),
                        "NO ACTION",
                        "RESTRICT",
                        "NONE",
                    ),
                    (
                        "users",
                        ("activated_by_user_id",),
                        ("id",),
                        "NO ACTION",
                        "RESTRICT",
                        "NONE",
                    ),
                }
                if _sqlite_foreign_key_manifest(
                    connection, "facility_release_checkout_activations"
                ) != activation_foreign_keys_expected or _sqlite_unique_manifest(
                    connection, "facility_release_checkout_activations"
                ) != {
                    ("organization_id", "id"),
                    ("organization_id", "facility_id"),
                    ("organization_id", "activation_operation_id"),
                }:
                    return False

                snapshot_sql = tables["attendance_release_snapshots"]
                activation_sql = tables["facility_release_checkout_activations"]
                receipt_sql = tables["childcare_command_receipts"]
                if any(
                    _named_check_expression(snapshot_sql, name) != expression
                    for name, expression in _SQLITE_RELEASE_SNAPSHOT_CHECKS.items()
                ) or any(
                    _named_check_expression(activation_sql, name) != expression
                    for name, expression in _SQLITE_RELEASE_ACTIVATION_CHECKS.items()
                ):
                    return False
                if (
                    _named_check_expression(receipt_sql, "ck_childcare_command_receipts_target")
                    != _SQLITE_RELEASE_RECEIPT_TARGET_CHECK
                ):
                    return False
                activation_compact = _compact_sql(activation_sql)
                named_unique_segments = (
                    "constraintuq_release_checkout_activations_org_idunique(organization_id,id)",
                    "constraintuq_release_checkout_activations_facility"
                    "unique(organization_id,facility_id)",
                    "constraintuq_release_checkout_activations_operation"
                    "unique(organization_id,activation_operation_id)",
                )
                named_foreign_key_segments = (
                    "constraintfk_release_checkout_activations_operation"
                    "foreignkey(organization_id,activation_operation_id)",
                    "constraintfk_release_checkout_activations_facility"
                    "foreignkey(organization_id,facility_id)",
                    "constraintfk_release_checkout_activations_membership"
                    "foreignkey(organization_id,activated_by_membership_id)",
                    "constraintfk_release_checkout_activations_role"
                    "foreignkey(organization_id,activated_by_role_id)",
                )
                if not all(
                    segment in activation_compact
                    for segment in (*named_unique_segments, *named_foreign_key_segments)
                ):
                    return False

                trigger_sql = {
                    str(row.name): _compact_sql(str(row.sql or ""))
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                            "AND tbl_name='facility_release_checkout_activations'"
                        )
                    )
                }
                expected_trigger_sql = {
                    "facility_release_checkout_activations_insert_guard": _compact_sql(
                        "CREATE TRIGGER facility_release_checkout_activations_insert_guard "
                        "BEFORE INSERT ON facility_release_checkout_activations "
                        "WHEN NOT EXISTS (SELECT 1 FROM organization_memberships AS membership "
                        "JOIN roles AS actor_role ON actor_role.organization_id = "
                        "membership.organization_id AND actor_role.id = membership.role_id "
                        "JOIN childcare_command_receipts AS receipt ON "
                        "receipt.organization_id = NEW.organization_id AND "
                        "receipt.client_operation_id = NEW.activation_operation_id "
                        "WHERE membership.organization_id = NEW.organization_id AND "
                        "membership.id = NEW.activated_by_membership_id AND "
                        "membership.user_id = NEW.activated_by_user_id AND "
                        "membership.role_id = NEW.activated_by_role_id AND "
                        "membership.status = 'active' AND "
                        "actor_role.organization_id = NEW.organization_id AND "
                        "actor_role.id = NEW.activated_by_role_id AND "
                        "actor_role.key = NEW.activated_by_role_key AND "
                        "receipt.command_type = 'facility.release_checkout.activate' AND "
                        "receipt.target_type = 'release_activation' AND "
                        "receipt.target_id = NEW.id AND "
                        "receipt.actor_user_id = NEW.activated_by_user_id AND "
                        "receipt.facility_id = NEW.facility_id AND "
                        "receipt.committed_version = 1) BEGIN SELECT RAISE(ABORT, "
                        "'release checkout activation relational consistency failed'); END"
                    ),
                    "facility_release_checkout_activations_no_update": _compact_sql(
                        "CREATE TRIGGER facility_release_checkout_activations_no_update "
                        "BEFORE UPDATE ON facility_release_checkout_activations BEGIN "
                        "SELECT RAISE(ABORT, "
                        "'release checkout activation is immutable'); END"
                    ),
                    "facility_release_checkout_activations_no_delete": _compact_sql(
                        "CREATE TRIGGER facility_release_checkout_activations_no_delete "
                        "BEFORE DELETE ON facility_release_checkout_activations BEGIN "
                        "SELECT RAISE(ABORT, "
                        "'release checkout activation is immutable'); END"
                    ),
                }
                if trigger_sql != expected_trigger_sql:
                    return False

                snapshot_trigger_sql = {
                    str(row.name): _compact_sql(str(row.sql or ""))
                    for row in connection.execute(
                        text(
                            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                            "AND tbl_name='attendance_release_snapshots' AND name IN "
                            "('attendance_release_snapshots_insert_guard',"
                            "'attendance_release_snapshots_no_update',"
                            "'attendance_release_snapshots_no_delete')"
                        )
                    )
                }
                expected_snapshot_trigger_sql = {
                    "attendance_release_snapshots_insert_guard": _compact_sql(
                        "CREATE TRIGGER attendance_release_snapshots_insert_guard "
                        "BEFORE INSERT ON attendance_release_snapshots WHEN NOT EXISTS ("
                        "SELECT 1 FROM organization_memberships AS membership "
                        "JOIN roles AS actor_role ON actor_role.organization_id = "
                        "membership.organization_id AND actor_role.id = membership.role_id "
                        "JOIN staff_shifts AS staff_shift ON staff_shift.organization_id = "
                        "NEW.organization_id AND staff_shift.id = NEW.staff_shift_id "
                        "JOIN childcare_command_receipts AS receipt ON "
                        "receipt.organization_id = NEW.organization_id AND "
                        "receipt.client_operation_id = NEW.client_operation_id "
                        "JOIN attendance_events AS checkout_event ON "
                        "checkout_event.organization_id = NEW.organization_id AND "
                        "checkout_event.id = NEW.checkout_event_id "
                        "WHERE membership.organization_id = NEW.organization_id AND "
                        "membership.id = NEW.actor_membership_id AND "
                        "membership.user_id = NEW.actor_user_id AND "
                        "membership.role_id = NEW.actor_role_id AND "
                        "membership.status = 'active' AND "
                        "actor_role.organization_id = NEW.organization_id AND "
                        "actor_role.id = NEW.actor_role_id AND "
                        "actor_role.key = NEW.actor_role_key AND "
                        "staff_shift.membership_id = NEW.actor_membership_id AND "
                        "staff_shift.facility_id = NEW.facility_id AND "
                        "receipt.command_type = 'attendance.release.checkout' AND "
                        "receipt.target_type = 'attendance_release' AND "
                        "receipt.target_id = NEW.id AND "
                        "receipt.actor_user_id = NEW.actor_user_id AND "
                        "receipt.facility_id = NEW.facility_id AND "
                        "receipt.request_hash = NEW.request_hash AND "
                        "receipt.committed_at = NEW.committed_at AND "
                        "receipt.committed_version = 1 AND "
                        "checkout_event.attendance_day_id = NEW.attendance_day_id AND "
                        "checkout_event.client_operation_id = NEW.client_operation_id AND "
                        "checkout_event.actor_user_id = NEW.actor_user_id AND "
                        "checkout_event.occurred_at = NEW.checked_out_at AND "
                        "checkout_event.event_type = 'check_out' AND ("
                        "NEW.room_assignment_id IS NULL OR EXISTS (SELECT 1 FROM "
                        "membership_room_assignments AS room_assignment WHERE "
                        "room_assignment.organization_id = NEW.organization_id AND "
                        "room_assignment.id = NEW.room_assignment_id AND "
                        "room_assignment.membership_id = NEW.actor_membership_id AND "
                        "room_assignment.facility_id = NEW.facility_id AND "
                        "room_assignment.room_id = NEW.room_id))) BEGIN SELECT RAISE(ABORT, "
                        "'attendance release snapshot relational consistency failed'); END"
                    ),
                    "attendance_release_snapshots_no_update": _compact_sql(
                        "CREATE TRIGGER attendance_release_snapshots_no_update "
                        "BEFORE UPDATE ON attendance_release_snapshots BEGIN "
                        "SELECT RAISE(ABORT, "
                        "'attendance release snapshot is immutable'); END"
                    ),
                    "attendance_release_snapshots_no_delete": _compact_sql(
                        "CREATE TRIGGER attendance_release_snapshots_no_delete "
                        "BEFORE DELETE ON attendance_release_snapshots BEGIN "
                        "SELECT RAISE(ABORT, "
                        "'attendance release snapshot is immutable'); END"
                    ),
                }
                if snapshot_trigger_sql != expected_snapshot_trigger_sql:
                    return False

                # SQLite can inspect existing tenant rows. Empty databases are valid;
                # every present system template must nevertheless carry C permission.
                role_rows = list(
                    connection.execute(
                        text(
                            "SELECT key,permissions FROM roles "
                            "WHERE is_system=:is_system "
                            "AND key IN ('owner','administrator','educator')"
                        ),
                        {"is_system": True},
                    )
                )
                for row in role_rows:
                    permissions = row.permissions
                    if isinstance(permissions, str):
                        try:
                            permissions = json.loads(permissions)
                        except json.JSONDecodeError:
                            return False
                    if not isinstance(permissions, list) or "release:checkout" not in permissions:
                        return False
                return True

            relation_rows = {
                str(row.relname): (
                    str(row.relkind),
                    bool(row.relrowsecurity),
                    bool(row.relforcerowsecurity),
                )
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,relation.relkind,"
                        "relation.relrowsecurity,relation.relforcerowsecurity "
                        "FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' AND relation.relname IN "
                        "('facility_release_checkout_activations',"
                        "'attendance_release_snapshots')"
                    )
                )
            }
            if relation_rows != {
                "facility_release_checkout_activations": ("r", True, True),
                "attendance_release_snapshots": ("r", True, True),
            }:
                return False

            column_rows = {
                (str(row.relname), str(row.attname)): (
                    str(row.formatted_type).upper(),
                    bool(row.attnotnull),
                )
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,attribute.attname,"
                        "pg_catalog.format_type(attribute.atttypid,attribute.atttypmod) "
                        "AS formatted_type,attribute.attnotnull "
                        "FROM pg_catalog.pg_attribute AS attribute "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=attribute.attrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname IN "
                        "('facility_release_checkout_activations',"
                        "'attendance_release_snapshots') "
                        "AND attribute.attnum>0 AND NOT attribute.attisdropped"
                    )
                )
            }
            postgres_activation_columns_expected = {
                name: (
                    specification[0]
                    .replace("VARCHAR", "CHARACTER VARYING")
                    .replace("DATETIME", "TIMESTAMP WITH TIME ZONE"),
                    specification[1],
                )
                for name, specification in activation_columns_expected.items()
            }
            postgres_snapshot_columns_expected = {
                name: (
                    specification[0]
                    .replace("VARCHAR", "CHARACTER VARYING")
                    .replace("DATETIME", "TIMESTAMP WITH TIME ZONE"),
                    specification[1],
                )
                for name, specification in snapshot_columns_expected.items()
            }
            activation_columns = {
                name: specification
                for (relation, name), specification in column_rows.items()
                if relation == "facility_release_checkout_activations"
            }
            snapshot_columns = {
                name: specification
                for (relation, name), specification in column_rows.items()
                if relation == "attendance_release_snapshots"
            }
            if activation_columns != postgres_activation_columns_expected or any(
                snapshot_columns.get(name) != specification
                for name, specification in postgres_snapshot_columns_expected.items()
            ):
                return False

            constraint_rows = {
                (str(row.relname), str(row.conname)): (
                    str(row.contype),
                    bool(row.convalidated),
                    str(row.definition),
                )
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,constraint_record.conname,"
                        "constraint_record.contype,constraint_record.convalidated,"
                        "pg_catalog.pg_get_constraintdef("
                        "constraint_record.oid) AS definition "
                        "FROM pg_catalog.pg_constraint AS constraint_record "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=constraint_record.conrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' AND relation.relname IN "
                        "('facility_release_checkout_activations',"
                        "'attendance_release_snapshots','childcare_command_receipts')"
                    )
                )
            }

            def constraint_definition(
                relation: str,
                name: str,
                constraint_type: str,
            ) -> str | None:
                row = constraint_rows.get((relation, name))
                if row is None or row[0] != constraint_type or not row[1]:
                    return None
                return row[2]

            activation_policy = constraint_definition(
                "facility_release_checkout_activations",
                "ck_release_checkout_activations_policy_version",
                "c",
            )
            activation_role = constraint_definition(
                "facility_release_checkout_activations",
                "ck_release_checkout_activations_privileged_role",
                "c",
            )
            day_version = constraint_definition(
                "attendance_release_snapshots",
                "ck_release_snapshots_attendance_day_version",
                "c",
            )
            scope_basis = constraint_definition(
                "attendance_release_snapshots",
                "ck_release_snapshots_scope_basis",
                "c",
            )
            verification_policy = constraint_definition(
                "attendance_release_snapshots",
                "ck_release_snapshots_executable_verification_policy",
                "c",
            )
            checkout_time = constraint_definition(
                "attendance_release_snapshots",
                "ck_release_snapshots_checkout_time_order",
                "c",
            )
            decision_policy = constraint_definition(
                "attendance_release_snapshots",
                "ck_release_snapshots_decision_policy_version",
                "c",
            )
            receipt_target = constraint_definition(
                "childcare_command_receipts",
                "ck_childcare_command_receipts_target",
                "c",
            )
            if any(
                definition is None
                for definition in (
                    activation_policy,
                    activation_role,
                    day_version,
                    scope_basis,
                    verification_policy,
                    checkout_time,
                    decision_policy,
                    receipt_target,
                )
            ):
                return False
            assert activation_policy is not None
            assert activation_role is not None
            assert day_version is not None
            assert scope_basis is not None
            assert verification_policy is not None
            assert checkout_time is not None
            assert decision_policy is not None
            assert receipt_target is not None
            if not (
                _sql_string_literals(activation_policy) == {"normal_verified_release_v1"}
                and "activation_policy_version" in _compact_sql(activation_policy)
                and _sql_string_literals(activation_role) == {"owner", "administrator"}
                and "activated_by_role_key" in _compact_sql(activation_role)
                and "attendance_day_version>=1" in _compact_sql(day_version)
                and _sql_string_literals(scope_basis) == {"organization_role", "room_assignment"}
                and all(
                    marker in _compact_sql(scope_basis)
                    for marker in (
                        "scope_basis",
                        "room_assignment_idisnull",
                        "room_assignment_idisnotnull",
                    )
                )
                and _sql_string_literals(verification_policy)
                == {
                    "government_photo_id",
                    "verified",
                    "documented_familiarity",
                    "government_photo_id_or_documented_familiarity",
                }
                and all(
                    marker in _compact_sql(verification_policy)
                    for marker in (
                        "verification_policy_code",
                        "verification_method",
                        "verification_result",
                    )
                )
                and all(
                    marker in _compact_sql(checkout_time)
                    for marker in (
                        "checked_out_at>=requested_at",
                        "committed_at=checked_out_at",
                    )
                )
                and _sql_string_literals(decision_policy) == {"release-context-v1"}
                and "decision_policy_version" in _compact_sql(decision_policy)
                and _sql_string_literals(receipt_target)
                == {
                    "family",
                    "child",
                    "enrollment",
                    "authority_person",
                    "authority_evidence",
                    "authority_evidence_object",
                    "release_authorization",
                    "release_rule",
                    "consent",
                    "release_activation",
                    "attendance_release",
                }
            ):
                return False

            def relation_constraint_definitions(
                relation: str,
                constraint_type: str,
            ) -> set[str]:
                return {
                    _compact_sql(definition).replace("public.", "")
                    for (row_relation, _), (
                        row_type,
                        validated,
                        definition,
                    ) in constraint_rows.items()
                    if row_relation == relation and row_type == constraint_type and validated
                }

            activation_foreign_keys = relation_constraint_definitions(
                "facility_release_checkout_activations", "f"
            )
            if activation_foreign_keys != {
                "foreignkey(organization_id,activation_operation_id)"
                "referenceschildcare_command_receipts(organization_id,client_operation_id)"
                "ondeleterestrict",
                "foreignkey(organization_id,facility_id)"
                "referencesfacilities(organization_id,id)ondeleterestrict",
                "foreignkey(organization_id,activated_by_membership_id)"
                "referencesorganization_memberships(organization_id,id)ondeleterestrict",
                "foreignkey(organization_id,activated_by_role_id)"
                "referencesroles(organization_id,id)ondeleterestrict",
                "foreignkey(activated_by_user_id)referencesusers(id)ondeleterestrict",
            }:
                return False
            if relation_constraint_definitions("facility_release_checkout_activations", "u") != {
                "unique(organization_id,id)",
                "unique(organization_id,facility_id)",
                "unique(organization_id,activation_operation_id)",
            }:
                return False
            required_snapshot_foreign_keys = {
                "foreignkey(organization_id,actor_membership_id)"
                "referencesorganization_memberships(organization_id,id)ondeleterestrict",
                "foreignkey(organization_id,actor_role_id)"
                "referencesroles(organization_id,id)ondeleterestrict",
                "foreignkey(organization_id,staff_shift_id)"
                "referencesstaff_shifts(organization_id,id)ondeleterestrict",
                "foreignkey(organization_id,facility_id,room_id)"
                "referencesrooms(organization_id,facility_id,id)ondeleterestrict",
                "foreignkey(organization_id,room_assignment_id)"
                "referencesmembership_room_assignments(organization_id,id)ondeleterestrict",
            }
            if not required_snapshot_foreign_keys <= relation_constraint_definitions(
                "attendance_release_snapshots", "f"
            ):
                return False

            immutable_trigger = connection.execute(
                text(
                    "SELECT trigger.tgenabled,"
                    "pg_catalog.pg_get_triggerdef(trigger.oid) AS trigger_definition,"
                    "procedure.proname,procedure.prosecdef,procedure.proconfig,"
                    "owner_role.rolname AS owner_name,"
                    "pg_catalog.pg_get_function_result(procedure.oid) AS result_type,"
                    "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=0 "
                    "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                    "COALESCE(pg_catalog.has_function_privilege("
                    "runtime_role.rolname,procedure.oid,'EXECUTE'),false) "
                    "AS runtime_execute,"
                    "(EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=procedure.proowner "
                    "AND privilege.privilege_type='EXECUTE') "
                    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.privilege_type<>'EXECUTE' "
                    "OR privilege.grantee<>procedure.proowner "
                    "OR privilege.grantor<>procedure.proowner)) AS acl_exact,"
                    "pg_catalog.pg_get_functiondef(procedure.oid) AS function_definition "
                    "FROM pg_catalog.pg_trigger AS trigger "
                    "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                    "JOIN pg_catalog.pg_roles AS owner_role "
                    "ON owner_role.oid=procedure.proowner "
                    "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                    "ON runtime_role.rolname='caresync_basic_app' "
                    "WHERE trigger.tgrelid=pg_catalog.to_regclass("
                    "'public.facility_release_checkout_activations') "
                    "AND trigger.tgname='facility_release_checkout_activations_immutable' "
                    "AND NOT trigger.tgisinternal"
                )
            ).one_or_none()
            if immutable_trigger is None:
                return False
            trigger_search_path = {
                str(item).replace(" ", "") for item in (immutable_trigger.proconfig or [])
            }
            if not (
                immutable_trigger.tgenabled == "O"
                and immutable_trigger.proname == "caresync_release_checkout_activation_immutable"
                and immutable_trigger.prosecdef
                and immutable_trigger.owner_name != "caresync_basic_app"
                and str(immutable_trigger.result_type).lower() == "trigger"
                and not immutable_trigger.public_execute
                and not immutable_trigger.runtime_execute
                and immutable_trigger.acl_exact
                and len(immutable_trigger.proconfig or []) == 1
                and trigger_search_path == {"search_path=pg_catalog,public"}
                and _release_checkout_activation_immutability_is_hardened(
                    str(immutable_trigger.function_definition),
                    str(immutable_trigger.trigger_definition),
                )
            ):
                return False

            snapshot_immutable_trigger = connection.execute(
                text(
                    "SELECT trigger.tgenabled,"
                    "pg_catalog.pg_get_triggerdef(trigger.oid) AS trigger_definition,"
                    "procedure.proname,procedure.prosecdef,procedure.proconfig,"
                    "owner_role.rolname AS owner_name,"
                    "pg_catalog.pg_get_function_result(procedure.oid) AS result_type,"
                    "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=0 "
                    "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                    "COALESCE(pg_catalog.has_function_privilege("
                    "runtime_role.rolname,procedure.oid,'EXECUTE'),false) "
                    "AS runtime_execute,"
                    "(EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.grantee=procedure.proowner "
                    "AND privilege.privilege_type='EXECUTE') "
                    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                    "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                    ")) AS privilege WHERE privilege.privilege_type<>'EXECUTE' "
                    "OR privilege.grantee<>procedure.proowner "
                    "OR privilege.grantor<>procedure.proowner)) AS acl_exact,"
                    "pg_catalog.pg_get_functiondef(procedure.oid) AS function_definition "
                    "FROM pg_catalog.pg_trigger AS trigger "
                    "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                    "JOIN pg_catalog.pg_roles AS owner_role "
                    "ON owner_role.oid=procedure.proowner "
                    "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                    "ON runtime_role.rolname='caresync_basic_app' "
                    "WHERE trigger.tgrelid=pg_catalog.to_regclass("
                    "'public.attendance_release_snapshots') "
                    "AND trigger.tgname='attendance_release_snapshots_immutable' "
                    "AND NOT trigger.tgisinternal"
                )
            ).one_or_none()
            if snapshot_immutable_trigger is None:
                return False
            snapshot_trigger_search_path = {
                str(item).replace(" ", "") for item in (snapshot_immutable_trigger.proconfig or [])
            }
            if not (
                snapshot_immutable_trigger.tgenabled == "O"
                and snapshot_immutable_trigger.proname == "caresync_release_snapshot_immutable"
                and snapshot_immutable_trigger.prosecdef
                and snapshot_immutable_trigger.owner_name != "caresync_basic_app"
                and str(snapshot_immutable_trigger.result_type).lower() == "trigger"
                and not snapshot_immutable_trigger.public_execute
                and not snapshot_immutable_trigger.runtime_execute
                and snapshot_immutable_trigger.acl_exact
                and len(snapshot_immutable_trigger.proconfig or []) == 1
                and snapshot_trigger_search_path == {"search_path=pg_catalog,public"}
                and _release_checkout_snapshot_immutability_is_hardened(
                    str(snapshot_immutable_trigger.function_definition),
                    str(snapshot_immutable_trigger.trigger_definition),
                )
            ):
                return False

            insert_guard_rows = {
                (str(row.relname), str(row.tgname)): row
                for row in connection.execute(
                    text(
                        "SELECT relation.relname,trigger.tgname,trigger.tgenabled,"
                        "pg_catalog.pg_get_triggerdef(trigger.oid) AS trigger_definition,"
                        "procedure.proname,procedure.prosecdef,procedure.proconfig,"
                        "owner_role.rolname AS owner_name,"
                        "pg_catalog.pg_get_function_result(procedure.oid) AS result_type,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                        ")) AS privilege WHERE privilege.grantee=0 "
                        "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                        "COALESCE(pg_catalog.has_function_privilege("
                        "runtime_role.rolname,procedure.oid,'EXECUTE'),false) "
                        "AS runtime_execute,"
                        "(EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                        ")) AS privilege WHERE privilege.grantee=procedure.proowner "
                        "AND privilege.privilege_type='EXECUTE') "
                        "AND NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                        ")) AS privilege WHERE privilege.privilege_type<>'EXECUTE' "
                        "OR privilege.grantee<>procedure.proowner "
                        "OR privilege.grantor<>procedure.proowner)) AS acl_exact,"
                        "pg_catalog.pg_get_functiondef(procedure.oid) AS function_definition "
                        "FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_class AS relation "
                        "ON relation.oid=trigger.tgrelid "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid=trigger.tgfoid "
                        "JOIN pg_catalog.pg_roles AS owner_role "
                        "ON owner_role.oid=procedure.proowner "
                        "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                        "ON runtime_role.rolname='caresync_basic_app' "
                        "WHERE namespace.nspname='public' AND NOT trigger.tgisinternal "
                        "AND ((relation.relname='facility_release_checkout_activations' "
                        "AND trigger.tgname="
                        "'facility_release_checkout_activations_insert_guard') "
                        "OR (relation.relname='attendance_release_snapshots' "
                        "AND trigger.tgname="
                        "'zz_attendance_release_snapshots_insert_guard'))"
                    )
                )
            }
            expected_insert_guard_keys = {
                (
                    "facility_release_checkout_activations",
                    "facility_release_checkout_activations_insert_guard",
                ),
                (
                    "attendance_release_snapshots",
                    "zz_attendance_release_snapshots_insert_guard",
                ),
            }
            if set(insert_guard_rows) != expected_insert_guard_keys:
                return False

            activation_insert_guard = insert_guard_rows[
                (
                    "facility_release_checkout_activations",
                    "facility_release_checkout_activations_insert_guard",
                )
            ]
            activation_insert_search_path = {
                str(item).replace(" ", "") for item in (activation_insert_guard.proconfig or [])
            }
            if not (
                activation_insert_guard.tgenabled == "O"
                and activation_insert_guard.proname
                == "caresync_release_checkout_activation_insert_guard"
                and activation_insert_guard.prosecdef
                and activation_insert_guard.owner_name != "caresync_basic_app"
                and str(activation_insert_guard.result_type).lower() == "trigger"
                and not activation_insert_guard.public_execute
                and not activation_insert_guard.runtime_execute
                and activation_insert_guard.acl_exact
                and len(activation_insert_guard.proconfig or []) == 1
                and activation_insert_search_path == {"search_path=pg_catalog,public"}
                and _release_checkout_activation_insert_guard_is_hardened(
                    str(activation_insert_guard.function_definition),
                    str(activation_insert_guard.trigger_definition),
                )
            ):
                return False

            snapshot_insert_guard = insert_guard_rows[
                (
                    "attendance_release_snapshots",
                    "zz_attendance_release_snapshots_insert_guard",
                )
            ]
            snapshot_insert_search_path = {
                str(item).replace(" ", "") for item in (snapshot_insert_guard.proconfig or [])
            }
            if not (
                snapshot_insert_guard.tgenabled == "O"
                and snapshot_insert_guard.proname == "caresync_release_snapshot_insert_guard"
                and snapshot_insert_guard.prosecdef
                and snapshot_insert_guard.owner_name != "caresync_basic_app"
                and str(snapshot_insert_guard.result_type).lower() == "trigger"
                and not snapshot_insert_guard.public_execute
                and not snapshot_insert_guard.runtime_execute
                and snapshot_insert_guard.acl_exact
                and len(snapshot_insert_guard.proconfig or []) == 1
                and snapshot_insert_search_path == {"search_path=pg_catalog,public"}
                and _release_checkout_snapshot_insert_guard_is_hardened(
                    str(snapshot_insert_guard.function_definition),
                    str(snapshot_insert_guard.trigger_definition),
                )
            ):
                return False

            policies = list(
                connection.execute(
                    text(
                        "SELECT policy.polname,policy.polcmd,policy.polroles,"
                        "pg_catalog.pg_get_expr(policy.polqual,policy.polrelid) AS using_expr,"
                        "pg_catalog.pg_get_expr(policy.polwithcheck,policy.polrelid) "
                        "AS check_expr FROM pg_catalog.pg_policy AS policy "
                        "WHERE policy.polrelid=pg_catalog.to_regclass("
                        "'public.facility_release_checkout_activations')"
                    )
                )
            )
            expected_policy_expressions = {
                "caresync_family_authority_actor_is_privileged(organization_id)",
                "public.caresync_family_authority_actor_is_privileged(organization_id)",
            }
            if len(policies) != 1:
                return False
            policy = policies[0]
            if not (
                policy.polname == "facility_release_checkout_activations_privileged_actor"
                and policy.polcmd == "*"
                and tuple(int(role) for role in policy.polroles) == (0,)
                and _compact_sql(str(policy.using_expr or "")) in expected_policy_expressions
                and _compact_sql(str(policy.check_expr or "")) in expected_policy_expressions
            ):
                return False

            runtime_role_has_no_activation_privilege = bool(
                connection.scalar(
                    text(
                        "SELECT runtime_role.oid IS NOT NULL "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.facility_release_checkout_activations',"
                        "'SELECT'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.facility_release_checkout_activations',"
                        "'INSERT'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.facility_release_checkout_activations',"
                        "'UPDATE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.facility_release_checkout_activations',"
                        "'DELETE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.facility_release_checkout_activations',"
                        "'TRUNCATE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.facility_release_checkout_activations',"
                        "'REFERENCES'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.facility_release_checkout_activations',"
                        "'TRIGGER'),false) FROM (SELECT 1) AS seed "
                        "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                        "ON runtime_role.rolname='caresync_basic_app'"
                    )
                )
            )
            # PostgreSQL startup is intentionally catalog-only: tenant role JSON
            # is not exposed to the runtime role. The atomic command must validate
            # release:checkout against the current membership at commit time.
            return runtime_role_has_no_activation_privilege

    def has_family_release_checkout_runtime(self) -> bool:
        """Return true only for the complete restricted PostgreSQL 0029D writer."""

        if self.settings.database_type != "postgres":
            return False
        if not self.has_family_release_checkout_foundation():
            return False

        callable_functions = {
            "public.caresync_release_checkout_activation_enabled(uuid)": (
                "boolean",
                "s",
            ),
            "public.caresync_release_checkout_replay(uuid)": (
                _RELEASE_RESOURCE_TABLE_RESULT,
                "s",
            ),
            (
                "public.caresync_family_release_context_inputs_at("
                "uuid,uuid,timestamp with time zone)"
            ): ("jsonb", "v"),
            (
                "public.caresync_release_checkout_insert_snapshot("
                "uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,"
                "integer,integer,text,text,text,text,timestamp with time zone,"
                "timestamp with time zone,text)"
            ): (_RELEASE_RESOURCE_TABLE_RESULT, "v"),
        }
        trigger_functions = {
            "public.caresync_release_snapshot_commit_time_guard()",
            "public.caresync_attendance_interval_verified_release_guard()",
        }

        with self.engine.connect() as connection:
            function_rows: dict[str, Any] = {}
            for signature in (*callable_functions, *trigger_functions):
                row = connection.execute(
                    text(
                        "SELECT procedure.prosecdef,procedure.provolatile,"
                        "procedure.proconfig,owner_role.rolname AS owner_name,"
                        "pg_catalog.pg_get_function_result(procedure.oid) "
                        "AS result_type,"
                        "pg_catalog.pg_get_functiondef(procedure.oid) AS definition,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                        ")) AS privilege WHERE privilege.grantee=0 "
                        "AND privilege.privilege_type='EXECUTE') AS public_execute,"
                        "COALESCE(pg_catalog.has_function_privilege("
                        "runtime_role.rolname,procedure.oid,'EXECUTE'),false) "
                        "AS runtime_execute,"
                        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                        ")) AS privilege WHERE privilege.grantee=procedure.proowner "
                        "AND privilege.grantor=procedure.proowner "
                        "AND privilege.privilege_type='EXECUTE') AS owner_execute,"
                        "NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE("
                        "procedure.proacl,pg_catalog.acldefault('f',procedure.proowner)"
                        ")) AS privilege WHERE privilege.privilege_type<>'EXECUTE' "
                        "OR privilege.grantor<>procedure.proowner "
                        "OR privilege.grantee NOT IN (procedure.proowner,"
                        "COALESCE(runtime_role.oid,0::oid))) AS acl_bounded "
                        "FROM pg_catalog.pg_proc AS procedure "
                        "JOIN pg_catalog.pg_roles AS owner_role "
                        "ON owner_role.oid=procedure.proowner "
                        "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                        "ON runtime_role.rolname='caresync_basic_app' "
                        "WHERE procedure.oid=pg_catalog.to_regprocedure(:signature)"
                    ),
                    {"signature": signature},
                ).one_or_none()
                if row is None:
                    return False
                function_rows[signature] = row

            for signature, (expected_result, expected_volatility) in callable_functions.items():
                row = function_rows[signature]
                search_path = {str(setting).replace(" ", "") for setting in (row.proconfig or [])}
                if not (
                    row.prosecdef
                    and row.provolatile == expected_volatility
                    and row.owner_name != "caresync_basic_app"
                    and _compact_sql(str(row.result_type)) == _compact_sql(expected_result)
                    and len(row.proconfig or []) == 1
                    and search_path == {"search_path=pg_catalog,public"}
                    and not row.public_execute
                    and row.runtime_execute
                    and row.owner_execute
                    and row.acl_bounded
                ):
                    return False

            for signature in trigger_functions:
                row = function_rows[signature]
                search_path = {str(setting).replace(" ", "") for setting in (row.proconfig or [])}
                if not (
                    row.prosecdef
                    and row.provolatile == "v"
                    and row.owner_name != "caresync_basic_app"
                    and str(row.result_type).lower() == "trigger"
                    and len(row.proconfig or []) == 1
                    and search_path == {"search_path=pg_catalog,public"}
                    and not row.public_execute
                    and not row.runtime_execute
                    and row.owner_execute
                    and row.acl_bounded
                ):
                    return False

            activation_definition = str(
                function_rows[
                    "public.caresync_release_checkout_activation_enabled(uuid)"
                ].definition
            )
            replay_row = function_rows["public.caresync_release_checkout_replay(uuid)"]
            writer_context_definition = str(
                function_rows[
                    "public.caresync_family_release_context_inputs_at("
                    "uuid,uuid,timestamp with time zone)"
                ].definition
            )
            repository_row = function_rows[
                "public.caresync_release_checkout_insert_snapshot("
                "uuid,uuid,uuid,uuid,uuid,integer,uuid,uuid,uuid,uuid,uuid,uuid,"
                "integer,integer,text,text,text,text,timestamp with time zone,"
                "timestamp with time zone,text)"
            ]
            if not (
                _release_checkout_activation_projection_is_hardened(activation_definition)
                and _release_checkout_replay_projection_is_hardened(
                    str(replay_row.definition),
                    str(replay_row.result_type),
                )
                and _release_context_projection_definition_is_hardened(writer_context_definition)
                and "requested_evaluated_at" in writer_context_definition
                and "statement_timestamp()" not in writer_context_definition
                and "transaction_timestamp()" not in writer_context_definition
                and _release_checkout_snapshot_repository_is_hardened(
                    str(repository_row.definition),
                    str(repository_row.result_type),
                )
            ):
                return False

            operation_guard_definition = connection.scalar(
                text(
                    "SELECT pg_catalog.pg_get_functiondef(procedure.oid) "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.caresync_childcare_operation_guard()')"
                )
            )
            operation_guard = _compact_sql(str(operation_guard_definition or ""))
            if not (
                "ifnew.command_type='attendance.release.checkout'then" in operation_guard
                and "ifnew.committed_atisnullornotpg_catalog.isfinite(new.committed_at)then"
                in operation_guard
                and "constraint='ck_release_checkout_receipt_time'" in operation_guard
                and "elsenew.committed_at:=transaction_timestamp();" in operation_guard
            ):
                return False

            trigger_rows = {
                str(row.tgname): row
                for row in connection.execute(
                    text(
                        "SELECT trigger.tgname,trigger.tgenabled,"
                        "pg_catalog.pg_get_triggerdef(trigger.oid) AS definition,"
                        "procedure.proname FROM pg_catalog.pg_trigger AS trigger "
                        "JOIN pg_catalog.pg_proc AS procedure "
                        "ON procedure.oid=trigger.tgfoid "
                        "WHERE NOT trigger.tgisinternal AND (("
                        "trigger.tgrelid=pg_catalog.to_regclass("
                        "'public.attendance_release_snapshots') "
                        "AND trigger.tgname="
                        "'zy_attendance_release_snapshots_commit_time') OR ("
                        "trigger.tgrelid=pg_catalog.to_regclass("
                        "'public.attendance_intervals') "
                        "AND trigger.tgname="
                        "'attendance_intervals_verified_release_guard'))"
                    )
                )
            }
            if set(trigger_rows) != {
                "zy_attendance_release_snapshots_commit_time",
                "attendance_intervals_verified_release_guard",
            }:
                return False
            snapshot_time_trigger = trigger_rows["zy_attendance_release_snapshots_commit_time"]
            interval_trigger = trigger_rows["attendance_intervals_verified_release_guard"]
            if not (
                snapshot_time_trigger.tgenabled == "O"
                and snapshot_time_trigger.proname == "caresync_release_snapshot_commit_time_guard"
                and interval_trigger.tgenabled == "O"
                and interval_trigger.proname
                == "caresync_attendance_interval_verified_release_guard"
                and _release_checkout_snapshot_time_guard_is_hardened(
                    str(
                        function_rows[
                            "public.caresync_release_snapshot_commit_time_guard()"
                        ].definition
                    ),
                    str(snapshot_time_trigger.definition),
                )
                and _release_checkout_interval_guard_is_hardened(
                    str(
                        function_rows[
                            "public.caresync_attendance_interval_verified_release_guard()"
                        ].definition
                    ),
                    str(interval_trigger.definition),
                )
            ):
                return False

            privileges_ready = bool(
                connection.scalar(
                    text(
                        "SELECT runtime_role.oid IS NOT NULL "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,"
                        "'public.facility_release_checkout_activations','SELECT'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,"
                        "'public.facility_release_checkout_activations','INSERT'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,"
                        "'public.facility_release_checkout_activations','UPDATE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,"
                        "'public.facility_release_checkout_activations','DELETE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,"
                        "'public.facility_release_checkout_activations','TRUNCATE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,"
                        "'public.facility_release_checkout_activations','REFERENCES'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,"
                        "'public.facility_release_checkout_activations','TRIGGER'),false) "
                        "AND COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.attendance_release_snapshots',"
                        "'SELECT'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.attendance_release_snapshots',"
                        "'INSERT'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.attendance_release_snapshots',"
                        "'UPDATE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.attendance_release_snapshots',"
                        "'DELETE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.attendance_release_snapshots',"
                        "'TRUNCATE'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.attendance_release_snapshots',"
                        "'REFERENCES'),false) "
                        "AND NOT COALESCE(pg_catalog.has_table_privilege("
                        "runtime_role.rolname,'public.attendance_release_snapshots',"
                        "'TRIGGER'),false) "
                        "AND NOT EXISTS (SELECT 1 "
                        "FROM pg_catalog.pg_attribute AS attribute "
                        "WHERE attribute.attrelid=pg_catalog.to_regclass("
                        "'public.attendance_release_snapshots') "
                        "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                        "AND (pg_catalog.has_column_privilege("
                        "runtime_role.rolname,attribute.attrelid,attribute.attnum,"
                        "'INSERT') OR pg_catalog.has_column_privilege("
                        "runtime_role.rolname,attribute.attrelid,attribute.attnum,"
                        "'UPDATE'))) FROM (SELECT 1) AS seed "
                        "LEFT JOIN pg_catalog.pg_roles AS runtime_role "
                        "ON runtime_role.rolname='caresync_basic_app'"
                    )
                )
            )
            return privileges_ready

    @staticmethod
    def validate_basic_runtime_role(
        *,
        configured_user: str,
        current_user: str,
        session_user: str,
        is_superuser: bool,
        bypasses_rls: bool,
        inherits_privileges: bool,
        can_create_role: bool,
        can_create_database: bool,
        can_replicate: bool,
        has_role_memberships: bool,
        owns_database_objects: bool,
        search_path_is_safe: bool,
        has_unsafe_role_configuration: bool,
        has_dangerous_privileges: bool,
        has_missing_required_privileges: bool,
    ) -> None:
        if (
            configured_user != "caresync_basic_app"
            or current_user != "caresync_basic_app"
            or session_user != "caresync_basic_app"
        ):
            raise RuntimeError(
                "Writable CareSync Basic PostgreSQL must run as caresync_basic_app; "
                "use the owner only for migrations"
            )
        if (
            is_superuser
            or bypasses_rls
            or inherits_privileges
            or can_create_role
            or can_create_database
            or can_replicate
        ):
            raise RuntimeError(
                "CareSync Basic runtime role must be NOSUPERUSER, NOBYPASSRLS, "
                "NOINHERIT, NOCREATEROLE, NOCREATEDB, and NOREPLICATION"
            )
        if has_role_memberships:
            raise RuntimeError(
                "CareSync Basic runtime role must not have direct or indirect SET ROLE paths"
            )
        if owns_database_objects:
            raise RuntimeError(
                "CareSync Basic runtime role must not own database or schema objects"
            )
        if not search_path_is_safe or has_unsafe_role_configuration:
            raise RuntimeError(
                "CareSync Basic runtime role must have only the pinned "
                "public,pg_catalog search_path configuration"
            )
        if has_dangerous_privileges:
            raise RuntimeError(
                "CareSync Basic runtime role has forbidden effective database privileges"
            )
        if has_missing_required_privileges:
            raise RuntimeError(
                "CareSync Basic runtime role is missing required effective database privileges"
            )

    def assert_basic_runtime_identity(self) -> None:
        settings = self.settings
        if (
            settings.database_type != "postgres"
            or settings.database_read_only
            or settings.enable_advanced_routes
        ):
            return
        if settings.database_user != "caresync_basic_app":
            self.validate_basic_runtime_role(
                configured_user=settings.database_user,
                current_user=settings.database_user,
                session_user=settings.database_user,
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
        # A present 0032 surface changes the legitimate read/function ACL
        # allowlist below.  Certify the complete role/schema boundary first;
        # partial objects must never be mistaken for an absent capability.
        self.has_transport_registry_commands()
        # The 0033 ledger likewise adds only exact SELECT/INSERT privileges.
        # Its detailed detector must certify the surface before those grants
        # enter the global runtime-role allowlist.
        self.has_billing_ledger()
        self.has_billing_manual_activation_boundary()
        # 0038 grants only SELECT on the public-safe outbox and its Alembic
        # release marker. Certify that exact trigger-owned boundary before
        # those reads enter the global runtime-role allowlist.
        self.has_public_job_catalog_outbox()
        # 0039 adds six tenant tables with SELECT/INSERT and exact
        # column-level UPDATE grants.  Certify the frozen admission boundary
        # before those narrowly scoped privileges enter this global allowlist.
        self.has_admissions_decision_spine()
        # 0041 adds four tenant tables with append-only ledgers and two exact
        # terminal/state update surfaces.
        self.has_live_room_presence_safety_board()
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    WITH RECURSIVE runtime_role AS (
                      SELECT role.oid, role.rolsuper, role.rolbypassrls,
                             role.rolinherit, role.rolcreaterole,
                             role.rolcreatedb, role.rolreplication, role.rolconfig
                      FROM pg_catalog.pg_roles AS role
                      WHERE role.rolname = current_user
                    ), outbound_roles(role_oid) AS (
                      SELECT membership.roleid
                      FROM pg_catalog.pg_auth_members AS membership
                      JOIN runtime_role AS role ON role.oid = membership.member
                      UNION
                      SELECT membership.roleid
                      FROM pg_catalog.pg_auth_members AS membership
                      JOIN outbound_roles AS path ON path.role_oid = membership.member
                    ), staff_screening_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.ats_job_screening_terms'
                      ) IS NOT NULL
                    ), driver_vehicle_registry_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.staff_driver_capability_versions'
                      ) IS NOT NULL
                    ), transport_registry_commands_enabled(enabled) AS (
                      SELECT pg_catalog.to_regprocedure(
                        'public.caresync_0032_execute_command(text,uuid,text,jsonb)'
                      ) IS NOT NULL
                    ), billing_ledger_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.billing_command_preparations'
                      ) IS NOT NULL
                    ), billing_manual_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.billing_manual_activations'
                      ) IS NOT NULL
                        AND pg_catalog.to_regclass(
                          'public.billing_source_authorizations_0036'
                        ) IS NOT NULL
                        AND pg_catalog.to_regprocedure(
                          'public.caresync_0036_bundle_validate()'
                        ) IS NOT NULL
                    ), public_job_catalog_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.public_job_catalog_events'
                      ) IS NOT NULL
                    ), admissions_decision_spine_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.admission_applications'
                      ) IS NOT NULL
                    ), live_room_presence_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.staff_room_presence_sessions'
                      ) IS NOT NULL
                    ), mutable_tables(relname) AS (
                      VALUES
                        ('users'), ('organizations'), ('roles'),
                        ('organization_memberships'), ('organization_onboarding'),
                        ('facilities'), ('facility_programs'), ('rooms'), ('families'),
                        ('children'), ('enrollments'), ('attendance_days'),
                        ('attendance_intervals'), ('daily_care_records'),
                        ('medication_plans'), ('medication_administrations'),
                        ('incident_records'), ('membership_room_assignments'),
                        ('staff_invitations'), ('staff_invitation_rooms'),
                        ('password_reset_challenges'), ('ats_jobs'), ('ats_candidates'),
                        ('ats_applications'), ('ats_candidate_invitations'), ('ats_offers'),
                        ('ats_staff_provisionings'), ('staff_shifts'),
                        ('staff_scheduled_shifts'), ('staff_availability_profiles'),
                        ('staff_time_off_requests'), ('staff_shift_templates'),
                        ('staff_coverage_target_profiles'), ('staff_rotation_patterns'),
                        ('staff_open_shifts'), ('staff_open_shift_engagements'),
                        ('staff_substitute_profiles'), ('staff_shift_swap_requests'),
                        ('realtime_tickets'), ('marketplace_profiles'),
                        ('marketplace_application_links'), ('marketplace_interests'),
                        ('marketplace_realtime_tickets'), ('ats_interviews'),
                        ('marketplace_onboarding_states'),
                        ('marketplace_document_analyses'),
                        ('marketplace_credential_documents'),
                        ('marketplace_credential_notifications'), ('user_notifications'),
                        ('user_notification_preferences'),
                        ('notification_push_subscriptions'), ('notification_deliveries'),
                        ('user_realtime_tickets')
                      UNION ALL
                      SELECT screening.relname
                      FROM (
                        VALUES
                          ('ats_job_screening_terms'),
                          ('marketplace_screening_profiles'),
                          ('staff_screening_documents'),
                          ('staff_screening_application_shares')
                      ) AS screening(relname)
                      CROSS JOIN staff_screening_enabled AS enabled
                      WHERE enabled.enabled
                    ), deletable_tables(relname) AS (
                      VALUES ('marketplace_jobs'), ('marketplace_profile_photos'),
                             ('child_profile_photos')
                      UNION ALL
                      SELECT 'marketplace_job_screening_terms'
                      FROM staff_screening_enabled AS enabled
                      WHERE enabled.enabled
                    ), contact_tables(relname) AS (
                      VALUES ('guardians'), ('emergency_contacts')
                    ), append_only_tables(relname) AS (
                      VALUES
                        ('attendance_events'), ('daily_care_record_events'),
                        ('medication_plan_events'),
                        ('medication_administration_events'),
                        ('incident_record_events'), ('audit_events'), ('ats_events'),
                        ('staff_shift_events'), ('staff_scheduled_shift_events'),
                        ('staff_workforce_events'), ('childcare_command_receipts'),
                        ('childcare_command_claims'),
                        ('childcare_command_reconciliation_proofs'),
                        ('realtime_events'), ('user_realtime_events')
                      UNION ALL
                      SELECT screening.relname
                      FROM (
                        VALUES
                          ('ats_application_screening_snapshots'),
                          ('ats_offer_screening_terms'),
                          ('staff_screening_document_versions'),
                          ('staff_screening_candidate_confirmations'),
                          ('staff_screening_employer_reviews'),
                          ('ats_offer_acknowledgments')
                      ) AS screening(relname)
                      CROSS JOIN staff_screening_enabled AS enabled
                      WHERE enabled.enabled
                    ), family_authority_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.family_authority_people'
                      ) IS NOT NULL
                    ), family_evidence_vault_enabled(enabled) AS (
                      SELECT pg_catalog.to_regclass(
                        'public.family_authority_evidence_objects'
                      ) IS NOT NULL
                    ), family_authority_activation_enabled(enabled) AS (
                      SELECT
                        pg_catalog.to_regclass(
                          'public.child_release_authorizations'
                        ) IS NOT NULL
                        AND pg_catalog.to_regclass(
                          'public.child_release_rules'
                        ) IS NOT NULL
                        AND pg_catalog.to_regclass(
                          'public.consent_policy_versions'
                        ) IS NOT NULL
                        AND pg_catalog.to_regclass(
                          'public.child_consent_decisions'
                        ) IS NOT NULL
                        AND pg_catalog.to_regprocedure(
                          'public.caresync_family_authority_activation_guard()'
                        ) IS NOT NULL
                        AND EXISTS (
                          SELECT 1 FROM pg_catalog.pg_attribute AS attribute
                          WHERE attribute.attrelid=pg_catalog.to_regclass(
                                  'public.consent_policy_versions'
                                )
                            AND attribute.attname='content_text'
                            AND attribute.attnum>0 AND NOT attribute.attisdropped
                        )
                        AND 2=(
                          SELECT count(*) FROM pg_catalog.pg_attribute AS attribute
                          WHERE attribute.attrelid=pg_catalog.to_regclass(
                                  'public.child_consent_decisions'
                                )
                            AND attribute.attname IN (
                              'signer_authority_evidence_id',
                              'signer_authority_evidence_assessment_id'
                            )
                            AND attribute.attnum>0 AND NOT attribute.attisdropped
                        )
                        AND pg_catalog.strpos(
                          pg_catalog.pg_get_functiondef(
                            pg_catalog.to_regprocedure(
                              'public.caresync_family_authority_activation_guard()'
                            )
                          ),'content_sha256'
                        )>0
                        AND pg_catalog.strpos(
                          pg_catalog.pg_get_functiondef(
                            pg_catalog.to_regprocedure(
                              'public.caresync_family_authority_activation_guard()'
                            )
                          ),'sha256'
                        )>0
                        AND 4=(
                          SELECT count(*)
                          FROM pg_catalog.pg_trigger AS trigger
                          JOIN pg_catalog.pg_class AS relation
                            ON relation.oid=trigger.tgrelid
                          JOIN pg_catalog.pg_namespace AS namespace
                            ON namespace.oid=relation.relnamespace
                          WHERE namespace.nspname='public'
                            AND relation.relname IN (
                              'child_release_authorizations','child_release_rules',
                              'consent_policy_versions','child_consent_decisions'
                            )
                            AND trigger.tgname=(
                              'trg_' || relation.relname || '_activation_guard'
                            )
                            AND NOT trigger.tgisinternal
                            AND trigger.tgenabled<>'D'
                        )
                        AND 4=(
                          SELECT count(*)
                          FROM pg_catalog.pg_class AS relation
                          JOIN pg_catalog.pg_namespace AS namespace
                            ON namespace.oid=relation.relnamespace
                          WHERE namespace.nspname='public'
                            AND relation.relname IN (
                              'child_release_authorizations','child_release_rules',
                              'consent_policy_versions','child_consent_decisions'
                            )
                            AND relation.relrowsecurity
                            AND relation.relforcerowsecurity
                        )
                    ), authority_insert_tables(relname) AS (
                      VALUES
                        ('family_authority_people'),
                        ('family_authority_person_versions'),
                        ('family_authority_evidence'),
                        ('family_authority_evidence_assessments'),
                        ('child_authority_heads')
                      UNION ALL
                      SELECT vault.relname
                      FROM (
                        VALUES
                          ('family_authority_evidence_objects'),
                          ('family_authority_evidence_object_assessments')
                      ) AS vault(relname)
                      CROSS JOIN family_evidence_vault_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT activation.relname
                      FROM (
                        VALUES
                          ('child_release_authorizations'),
                          ('child_release_rules'),
                          ('consent_policy_versions'),
                          ('child_consent_decisions')
                      ) AS activation(relname)
                      CROSS JOIN family_authority_activation_enabled AS enabled
                      WHERE enabled.enabled
                    ), authority_select_only_tables(relname) AS (
                      VALUES ('attendance_release_snapshots')
                      UNION ALL
                      SELECT scaffold.relname
                      FROM (
                        VALUES
                          ('child_release_authorizations'),
                          ('child_release_rules'),
                          ('consent_policy_versions'),
                          ('child_consent_decisions')
                      ) AS scaffold(relname)
                      CROSS JOIN family_authority_activation_enabled AS enabled
                      WHERE NOT enabled.enabled
                      UNION ALL
                      SELECT registry.relname
                      FROM (
                        VALUES
                          ('staff_driver_capability_versions'),
                          ('staff_driver_qualification_versions'),
                          ('staff_driver_authorization_decisions'),
                          ('staff_driver_readiness_decisions'),
                          ('transport_vehicles'),
                          ('transport_vehicle_versions'),
                          ('transport_vehicle_evidence_versions')
                      ) AS registry(relname)
                      CROSS JOIN driver_vehicle_registry_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT commands.relname
                      FROM (
                        VALUES
                          ('transport_registry_command_receipts'),
                          ('staff_driver_qualification_evidence_objects'),
                          ('staff_driver_qualification_review_decisions'),
                          ('transport_vehicle_evidence_review_decisions'),
                          ('transport_vehicle_evidence_scan_facts')
                      ) AS commands(relname)
                      CROSS JOIN transport_registry_commands_enabled AS enabled
                      WHERE enabled.enabled
                    ), billing_insert_tables(relname) AS (
                      SELECT billing.relname
                      FROM (
                        VALUES
                          ('billing_accounts'),
                          ('billing_account_payer_versions'),
                          ('billing_rate_plans'),
                          ('billing_rate_plan_versions'),
                          ('billing_agreements'),
                          ('billing_agreement_versions'),
                          ('billing_invoices'),
                          ('billing_invoice_lines'),
                          ('billing_payments'),
                          ('billing_allocations'),
                          ('billing_credits'),
                          ('billing_journal_entries'),
                          ('billing_journal_lines'),
                          ('billing_command_preparations'),
                          ('billing_command_receipts'),
                          ('billing_command_claims')
                      ) AS billing(relname)
                      CROSS JOIN billing_ledger_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT 'billing_manual_activations'
                      FROM billing_manual_enabled AS enabled
                      WHERE enabled.enabled
                    ), billing_select_only_tables(relname) AS (
                      SELECT billing.relname
                      FROM (
                        VALUES
                          ('billing_sandbox_source_attestations'),
                          ('billing_command_terminals'),
                          ('billing_reversals')
                      ) AS billing(relname)
                      CROSS JOIN billing_ledger_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT 'billing_source_authorizations_0036'
                      FROM billing_manual_enabled AS enabled
                      WHERE enabled.enabled
                    ), public_job_catalog_select_only_tables(relname) AS (
                      VALUES ('alembic_version')
                      UNION ALL
                      SELECT 'public_job_catalog_events'
                      FROM public_job_catalog_enabled AS enabled
                      WHERE enabled.enabled
                    ), admission_insert_tables(relname) AS (
                      SELECT admission.relname
                      FROM (
                        VALUES
                          ('admission_applications'),
                          ('admission_application_preferences'),
                          ('admission_waitlist_entries'),
                          ('admission_offers'),
                          ('admission_conversion_links'),
                          ('admission_application_events')
                      ) AS admission(relname)
                      CROSS JOIN admissions_decision_spine_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT presence.relname
                      FROM (
                        VALUES
                          ('staff_room_presence_sessions'),
                          ('staff_room_presence_events'),
                          ('room_operational_exception_heads'),
                          ('room_operational_exception_events')
                      ) AS presence(relname)
                      CROSS JOIN live_room_presence_enabled AS enabled
                      WHERE enabled.enabled
                    ), admission_update_columns(relname, attname) AS (
                      SELECT admission.relname,admission.attname
                      FROM (
                        VALUES
                          ('admission_applications', 'status'),
                          ('admission_applications', 'version'),
                          ('admission_applications', 'child_first_name'),
                          ('admission_applications', 'child_last_name'),
                          ('admission_applications', 'child_normalized_name'),
                          ('admission_applications', 'child_date_of_birth'),
                          ('admission_applications', 'contact_first_name'),
                          ('admission_applications', 'contact_last_name'),
                          ('admission_applications', 'contact_relationship'),
                          ('admission_applications', 'contact_email'),
                          ('admission_applications', 'contact_normalized_email'),
                          ('admission_applications', 'contact_telephone'),
                          ('admission_applications', 'contact_normalized_telephone'),
                          ('admission_applications', 'internal_note'),
                          ('admission_applications', 'updated_by_user_id'),
                          ('admission_applications', 'last_operation_id'),
                          ('admission_applications', 'submitted_at'),
                          ('admission_applications', 'review_started_at'),
                          ('admission_applications', 'terminal_at'),
                          ('admission_applications', 'updated_at'),
                          ('admission_application_preferences', 'current_rank'),
                          ('admission_application_preferences', 'current_lane_key'),
                          ('admission_application_preferences', 'retired_by_user_id'),
                          ('admission_application_preferences', 'retired_operation_id'),
                          ('admission_application_preferences', 'retired_at'),
                          ('admission_waitlist_entries', 'current_application_id'),
                          ('admission_waitlist_entries', 'status'),
                          ('admission_waitlist_entries', 'version'),
                          ('admission_waitlist_entries', 'closure_reason'),
                          ('admission_waitlist_entries', 'updated_by_user_id'),
                          ('admission_waitlist_entries', 'last_operation_id'),
                          ('admission_waitlist_entries', 'closed_at'),
                          ('admission_waitlist_entries', 'updated_at'),
                          ('admission_offers', 'open_application_id'),
                          ('admission_offers', 'status'),
                          ('admission_offers', 'version'),
                          ('admission_offers', 'updated_by_user_id'),
                          ('admission_offers', 'last_operation_id'),
                          ('admission_offers', 'withdrawn_at'),
                          ('admission_offers', 'declined_at'),
                          ('admission_offers', 'accepted_at'),
                          ('admission_offers', 'updated_at')
                      ) AS admission(relname,attname)
                      CROSS JOIN admissions_decision_spine_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT presence.relname,presence.attname
                      FROM (
                        VALUES
                          ('staff_room_presence_sessions','ended_at'),
                          ('staff_room_presence_sessions','end_reason'),
                          ('staff_room_presence_sessions','end_operation_id'),
                          ('staff_room_presence_sessions','ended_by_user_id'),
                          ('staff_room_presence_sessions','version'),
                          ('staff_room_presence_sessions','updated_at'),
                          ('room_operational_exception_heads','state'),
                          ('room_operational_exception_heads','current_fingerprint_sha256'),
                          ('room_operational_exception_heads','current_evidence'),
                          ('room_operational_exception_heads','last_changed_at'),
                          ('room_operational_exception_heads','acknowledged_at'),
                          ('room_operational_exception_heads','acknowledged_by_user_id'),
                          ('room_operational_exception_heads','acknowledgement_reason'),
                          ('room_operational_exception_heads','resolved_at'),
                          ('room_operational_exception_heads','version'),
                          ('room_operational_exception_heads','updated_at')
                      ) AS presence(relname,attname)
                      CROSS JOIN live_room_presence_enabled AS enabled
                      WHERE enabled.enabled
                    ), authority_update_columns(relname, attname) AS (
                      VALUES
                        ('family_authority_people', 'version'),
                        ('family_authority_people', 'status'),
                        ('family_authority_people', 'current_person_version_id'),
                        ('family_authority_people', 'last_operation_id'),
                        ('family_authority_people', 'retired_at'),
                        ('family_authority_people', 'retired_operation_id'),
                        ('family_authority_people', 'updated_at'),
                        ('family_authority_person_versions', 'closed_at'),
                        ('family_authority_person_versions', 'closed_operation_id'),
                        ('child_authority_heads', 'revision'),
                        ('child_authority_heads', 'last_operation_id'),
                        ('child_authority_heads', 'updated_at')
                      UNION ALL
                      SELECT 'family_authority_evidence_objects', 'status'
                      FROM family_evidence_vault_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT activation.relname,activation.attname
                      FROM (
                        VALUES
                          ('child_release_authorizations', 'version'),
                          ('child_release_authorizations', 'revoked_at'),
                          ('child_release_authorizations', 'revoked_operation_id'),
                          ('child_release_authorizations', 'revocation_reason_code'),
                          ('child_release_authorizations', 'updated_at'),
                          ('child_release_rules', 'version'),
                          ('child_release_rules', 'revoked_at'),
                          ('child_release_rules', 'revoked_operation_id'),
                          ('child_release_rules', 'revocation_reason_code'),
                          ('child_release_rules', 'updated_at'),
                          ('child_consent_decisions', 'version'),
                          ('child_consent_decisions', 'withdrawn_at'),
                          ('child_consent_decisions', 'withdrawn_operation_id'),
                          ('child_consent_decisions', 'withdrawal_reason_code'),
                          ('child_consent_decisions', 'updated_at')
                      ) AS activation(relname,attname)
                      CROSS JOIN family_authority_activation_enabled AS enabled
                      WHERE enabled.enabled
                    ), user_tables AS (
                      SELECT relation.oid, namespace.nspname, relation.relname
                      FROM pg_catalog.pg_class AS relation
                      JOIN pg_catalog.pg_namespace AS namespace
                        ON namespace.oid = relation.relnamespace
                      WHERE relation.relkind IN ('r', 'p', 'v')
                        AND namespace.nspname !~ '^pg_'
                        AND namespace.nspname <> 'information_schema'
                    ), user_sequences AS (
                      SELECT relation.oid, namespace.nspname, relation.relname
                      FROM pg_catalog.pg_class AS relation
                      JOIN pg_catalog.pg_namespace AS namespace
                        ON namespace.oid = relation.relnamespace
                      WHERE relation.relkind = 'S'
                        AND namespace.nspname !~ '^pg_'
                        AND namespace.nspname <> 'information_schema'
                    ), expected_guard_functions(signature) AS (
                      VALUES
                        ('public.caresync_charge_childcare_reconciliation(uuid,uuid,uuid)'),
                        ('public.caresync_childcare_operation_guard()'),
                        ('public.caresync_childcare_reconciliation_proof_guard()'),
                        ('public.caresync_childcare_immutable_ledger_guard()'),
                        ('public.caresync_childcare_contact_retirement_guard()')
                      UNION ALL
                      SELECT screening.signature
                      FROM (
                        VALUES
                          ('public.sync_marketplace_job_screening_from_terms()'),
                          ('public.sync_marketplace_job_screening_from_listing()'),
                          ('public.caresync_0030_immutable_fact()'),
                          ('public.caresync_0030_coverage_guard()'),
                          ('public.caresync_0030_snapshot_guard()'),
                          ('public.caresync_0030_share_insert_guard()'),
                          ('public.caresync_0030_review_insert_guard()'),
                          ('public.caresync_0030_document_guard()'),
                          ('public.caresync_0030_offer_terms_insert_guard()'),
                          ('public.caresync_0030_offer_terms_guard()'),
                          ('public.caresync_0030_share_guard()'),
                          ('public.caresync_0030_offer_ack_guard()')
                      ) AS screening(signature)
                      CROSS JOIN staff_screening_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT registry.signature
                      FROM (
                        VALUES
                          ('public.caresync_0031_immutable_fact()'),
                          ('public.caresync_0031_capability_guard()'),
                          ('public.caresync_0031_qualification_guard()'),
                          ('public.caresync_0031_authorization_guard()'),
                          ('public.caresync_0031_vehicle_guard()'),
                          ('public.caresync_0031_vehicle_version_guard()'),
                          ('public.caresync_0031_vehicle_evidence_guard()'),
                          ('public.caresync_0031_readiness_guard()')
                      ) AS registry(signature)
                      CROSS JOIN driver_vehicle_registry_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT commands.signature
                      FROM (
                        VALUES
                          ('public.caresync_0032_immutable_fact()'),
                          ('public.caresync_0032_receipt_guard()'),
                          ('public.caresync_0032_qualification_evidence_guard()'),
                          ('public.caresync_0032_qualification_review_guard()'),
                          ('public.caresync_0032_vehicle_review_guard()'),
                          ('public.caresync_0032_vehicle_scan_guard()')
                      ) AS commands(signature)
                      CROSS JOIN transport_registry_commands_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT billing.signature
                      FROM (
                        VALUES
                          ('public.caresync_0033_immutable_fact()'),
                          ('public.caresync_0033_role_permission_guard()'),
                          ('public.caresync_0033_source_attestation_guard()'),
                          ('public.caresync_0033_attested_source_immutable()'),
                          ('public.caresync_0033_actor_guard()'),
                          ('public.caresync_0033_version_guard()'),
                          ('public.caresync_0033_invoice_line_guard()'),
                          ('public.caresync_0033_allocation_guard()'),
                          ('public.caresync_0033_credit_guard()'),
                          ('public.caresync_0033_journal_sequence_guard()'),
                          ('public.caresync_0033_journal_validate()'),
                          ('public.caresync_0033_effect_open_guard()'),
                          ('public.caresync_0033_bundle_validate()'),
                          ('public.caresync_0033_receipt_guard()'),
                          ('public.caresync_0033_claim_guard()'),
                          ('public.caresync_0033_terminal_claim()')
                      ) AS billing(signature)
                      CROSS JOIN billing_ledger_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT manual.signature
                      FROM (
                        VALUES
                          ('public.caresync_0036_bundle_validate()'),
                          ('public.caresync_0036_manual_activation_guard()'),
                          ('public.caresync_0036_manual_activation_immutable()')
                      ) AS manual(signature)
                      CROSS JOIN billing_manual_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT admission.signature
                      FROM (
                        VALUES
                          ('public.caresync_0039_immutable_fact()'),
                          ('public.caresync_0039_waitlist_priority_guard()'),
                          ('public.caresync_0039_active_program_guard()'),
                          ('public.caresync_0039_conversion_coherence_guard()'),
                          ('public.caresync_0039_command_row_guard()'),
                          ('public.caresync_0039_command_bundle_guard()')
                      ) AS admission(signature)
                      CROSS JOIN admissions_decision_spine_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT presence.signature
                      FROM (
                        VALUES
                          ('public.caresync_0041_presence_row_guard()'),
                          ('public.caresync_0041_event_immutable_guard()'),
                          ('public.caresync_0041_presence_event_guard()'),
                          ('public.caresync_0041_presence_bundle_guard()'),
                          ('public.caresync_0041_exception_head_guard()'),
                          ('public.caresync_0041_exception_event_guard()'),
                          ('public.caresync_0041_exception_bundle_guard()')
                      ) AS presence(signature)
                      CROSS JOIN live_room_presence_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT authority.signature
                      FROM (
                        VALUES
                          ('public.caresync_family_authority_insert_guard()'),
                          ('public.caresync_family_authority_transition_guard()'),
                          ('public.caresync_family_authority_temporal_guard()'),
                          ('public.caresync_family_authority_person_invariant()'),
                          ('public.caresync_family_authority_child_revision_invariant()'),
                          ('public.caresync_family_authority_evidence_invariant()'),
                          ('public.caresync_family_authority_receipt_guard()'),
                          ('public.caresync_family_authority_receipt_invariant()')
                      ) AS authority(signature)
                      CROSS JOIN family_authority_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT vault.signature
                      FROM (
                        VALUES
                          ('public.caresync_family_evidence_object_write_guard()'),
                          ('public.caresync_family_evidence_object_invariant()'),
                          ('public.caresync_family_evidence_object_link_guard()'),
                          ('public.caresync_family_evidence_review_guard()')
                      ) AS vault(signature)
                      CROSS JOIN family_evidence_vault_enabled AS enabled
                      WHERE enabled.enabled
                      UNION ALL
                      SELECT activation.signature
                      FROM (
                        VALUES
                          ('public.caresync_family_authority_activation_guard()')
                      ) AS activation(signature)
                      CROSS JOIN family_authority_activation_enabled AS enabled
                      WHERE enabled.enabled
                    ), guard_functions AS (
                      SELECT pg_catalog.to_regprocedure(expected.signature) AS function_oid
                      FROM expected_guard_functions AS expected
                    ), authority_policy_function(
                      function_oid, definition_is_safe, public_can_execute
                    ) AS (
                      SELECT expected.function_oid,
                             COALESCE(
                               procedure.prosecdef
                               AND procedure.provolatile = 's'
                               AND pg_catalog.array_length(
                                 procedure.proconfig, 1
                               ) = 1
                               AND pg_catalog.replace(
                                 procedure.proconfig[1], ' ', ''
                               ) = 'search_path=pg_catalog,public',
                               false
                             ),
                             EXISTS (
                               SELECT 1
                               FROM pg_catalog.aclexplode(
                                 COALESCE(
                                   procedure.proacl,
                                   pg_catalog.acldefault(
                                     'f', procedure.proowner
                                   )
                                 )
                               ) AS privilege
                               WHERE privilege.grantee = 0
                                 AND privilege.privilege_type = 'EXECUTE'
                             )
                      FROM family_authority_enabled AS enabled
                      CROSS JOIN LATERAL (
                        SELECT pg_catalog.to_regprocedure(
                          'public.caresync_family_authority_actor_is_privileged(uuid)'
                        ) AS function_oid
                      ) AS expected
                      LEFT JOIN pg_catalog.pg_proc AS procedure
                        ON procedure.oid = expected.function_oid
                      WHERE enabled.enabled
                    )
                    SELECT current_user AS role_name,
                           session_user AS session_role_name,
                           role.rolsuper, role.rolbypassrls, role.rolinherit,
                           role.rolcreaterole, role.rolcreatedb, role.rolreplication,
                           (
                             EXISTS (SELECT 1 FROM outbound_roles)
                             OR EXISTS (
                               SELECT 1
                               FROM pg_catalog.pg_auth_members AS membership
                               WHERE membership.roleid = role.oid
                             )
                           ) AS has_role_memberships,
                           EXISTS (
                             SELECT 1
                             FROM pg_catalog.pg_shdepend AS dependency
                             WHERE dependency.refclassid =
                                   'pg_catalog.pg_authid'::pg_catalog.regclass
                               AND dependency.refobjid = role.oid
                               AND dependency.deptype = 'o'
                           ) AS owns_database_objects,
                           pg_catalog.replace(
                             pg_catalog.current_setting('search_path'), ' ', ''
                           ) = 'public,pg_catalog' AS search_path_is_safe,
                           (
                             CASE
                               WHEN pg_catalog.array_length(role.rolconfig, 1) IS NULL
                                 THEN 0
                               ELSE pg_catalog.array_length(role.rolconfig, 1)
                             END <> 1
                             OR pg_catalog.replace(role.rolconfig[1], ' ', '') <>
                                'search_path=public,pg_catalog'
                             OR EXISTS (
                               SELECT 1
                               FROM pg_catalog.pg_db_role_setting AS setting
                               WHERE setting.setrole = role.oid
                                 AND setting.setdatabase <> 0
                             )
                           ) AS has_unsafe_role_configuration,
                           (
                             pg_catalog.has_database_privilege(
                               current_user, pg_catalog.current_database(), 'CREATE'
                             )
                             OR pg_catalog.has_database_privilege(
                               current_user, pg_catalog.current_database(), 'TEMPORARY'
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM pg_catalog.pg_namespace AS namespace
                               WHERE namespace.nspname !~ '^pg_'
                                 AND namespace.nspname <> 'information_schema'
                                 AND pg_catalog.has_schema_privilege(
                                   current_user, namespace.oid, 'CREATE'
                                 )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM user_tables AS relation
                               WHERE (
                                 relation.nspname <> 'public'
                                 AND (
                                   pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'SELECT'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'INSERT'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'UPDATE'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'DELETE'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'TRUNCATE'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'REFERENCES'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'TRIGGER'
                                   )
                                   OR CASE
                                     WHEN pg_catalog.current_setting(
                                       'server_version_num'
                                     )::pg_catalog.int4 >= 170000
                                       THEN pg_catalog.has_table_privilege(
                                         current_user, relation.oid, 'MAINTAIN'
                                       )
                                     ELSE false
                                   END
                                   OR pg_catalog.has_any_column_privilege(
                                     current_user, relation.oid, 'SELECT'
                                   )
                                   OR pg_catalog.has_any_column_privilege(
                                     current_user, relation.oid, 'INSERT'
                                   )
                                   OR pg_catalog.has_any_column_privilege(
                                     current_user, relation.oid, 'UPDATE'
                                   )
                                   OR pg_catalog.has_any_column_privilege(
                                     current_user, relation.oid, 'REFERENCES'
                                   )
                                 )
                               ) OR (
                                 relation.nspname = 'public'
                                 AND (
                                   pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'TRUNCATE'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'REFERENCES'
                                   )
                                   OR pg_catalog.has_table_privilege(
                                     current_user, relation.oid, 'TRIGGER'
                                   )
                                   OR CASE
                                     WHEN pg_catalog.current_setting(
                                       'server_version_num'
                                     )::pg_catalog.int4 >= 170000
                                       THEN pg_catalog.has_table_privilege(
                                         current_user, relation.oid, 'MAINTAIN'
                                       )
                                     ELSE false
                                   END
                                   OR (
                                     pg_catalog.has_table_privilege(
                                       current_user, relation.oid, 'SELECT'
                                     ) AND NOT (
                                       EXISTS (SELECT 1 FROM mutable_tables allowed
                                               WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM deletable_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM contact_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM append_only_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM authority_insert_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM authority_select_only_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM billing_insert_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM billing_select_only_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (
                                         SELECT 1
                                         FROM public_job_catalog_select_only_tables allowed
                                         WHERE allowed.relname = relation.relname
                                       )
                                       OR EXISTS (
                                         SELECT 1 FROM admission_insert_tables allowed
                                         WHERE allowed.relname = relation.relname
                                       )
                                     )
                                   )
                                   OR (
                                     pg_catalog.has_table_privilege(
                                       current_user, relation.oid, 'INSERT'
                                     ) AND NOT (
                                       EXISTS (SELECT 1 FROM mutable_tables allowed
                                               WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM deletable_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM contact_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM append_only_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM authority_insert_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM billing_insert_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM admission_insert_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                     )
                                   )
                                   OR (
                                     pg_catalog.has_table_privilege(
                                       current_user, relation.oid, 'UPDATE'
                                     ) AND NOT (
                                       EXISTS (SELECT 1 FROM mutable_tables allowed
                                               WHERE allowed.relname = relation.relname)
                                       OR EXISTS (SELECT 1 FROM deletable_tables allowed
                                                  WHERE allowed.relname = relation.relname)
                                     )
                                   )
                                   OR (
                                     pg_catalog.has_table_privilege(
                                       current_user, relation.oid, 'DELETE'
                                     ) AND NOT EXISTS (
                                       SELECT 1 FROM deletable_tables allowed
                                       WHERE allowed.relname = relation.relname
                                     )
                                   )
                                   OR EXISTS (
                                     SELECT 1
                                     FROM pg_catalog.pg_attribute AS attribute
                                     WHERE attribute.attrelid = relation.oid
                                       AND attribute.attnum > 0
                                       AND NOT attribute.attisdropped
                                       AND (
                                         (
                                           pg_catalog.has_column_privilege(
                                             current_user, relation.oid,
                                             attribute.attnum, 'SELECT'
                                           ) AND NOT (
                                             EXISTS (SELECT 1 FROM mutable_tables allowed
                                                     WHERE allowed.relname = relation.relname)
                                             OR EXISTS (SELECT 1 FROM deletable_tables allowed
                                                        WHERE allowed.relname = relation.relname)
                                             OR EXISTS (SELECT 1 FROM contact_tables allowed
                                                        WHERE allowed.relname = relation.relname)
                                             OR EXISTS (SELECT 1 FROM append_only_tables allowed
                                                        WHERE allowed.relname = relation.relname)
                                             OR EXISTS (
                                               SELECT 1 FROM authority_insert_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                             OR EXISTS (
                                               SELECT 1 FROM authority_select_only_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                             OR EXISTS (
                                               SELECT 1 FROM billing_insert_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                             OR EXISTS (
                                               SELECT 1 FROM billing_select_only_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                             OR EXISTS (
                                               SELECT 1
                                               FROM public_job_catalog_select_only_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                             OR EXISTS (
                                               SELECT 1 FROM admission_insert_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                           )
                                         )
                                         OR (
                                           pg_catalog.has_column_privilege(
                                             current_user, relation.oid,
                                             attribute.attnum, 'INSERT'
                                           ) AND NOT (
                                             EXISTS (SELECT 1 FROM mutable_tables allowed
                                                     WHERE allowed.relname = relation.relname)
                                             OR EXISTS (SELECT 1 FROM deletable_tables allowed
                                                        WHERE allowed.relname = relation.relname)
                                             OR EXISTS (SELECT 1 FROM contact_tables allowed
                                                        WHERE allowed.relname = relation.relname)
                                             OR EXISTS (SELECT 1 FROM append_only_tables allowed
                                                        WHERE allowed.relname = relation.relname)
                                             OR EXISTS (
                                               SELECT 1 FROM authority_insert_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                             OR EXISTS (
                                               SELECT 1 FROM billing_insert_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                             OR EXISTS (
                                               SELECT 1 FROM admission_insert_tables allowed
                                               WHERE allowed.relname = relation.relname
                                             )
                                           )
                                         )
                                         OR (
                                           pg_catalog.has_column_privilege(
                                             current_user, relation.oid,
                                             attribute.attnum, 'UPDATE'
                                           ) AND NOT (
                                             EXISTS (SELECT 1 FROM mutable_tables allowed
                                                     WHERE allowed.relname = relation.relname)
                                             OR EXISTS (SELECT 1 FROM deletable_tables allowed
                                                        WHERE allowed.relname = relation.relname)
                                             OR (
                                               EXISTS (SELECT 1 FROM contact_tables allowed
                                               WHERE allowed.relname = relation.relname)
                                               AND attribute.attname IN
                                                   ('retired_at',
                                                    'retired_operation_id',
                                                    'updated_at')
                                             )
                                             OR EXISTS (
                                               SELECT 1
                                               FROM authority_update_columns AS allowed
                                               WHERE allowed.relname = relation.relname
                                                 AND allowed.attname = attribute.attname
                                             )
                                             OR EXISTS (
                                               SELECT 1
                                               FROM admission_update_columns AS allowed
                                               WHERE allowed.relname = relation.relname
                                                 AND allowed.attname = attribute.attname
                                             )
                                           )
                                         )
                                         OR pg_catalog.has_column_privilege(
                                           current_user, relation.oid,
                                           attribute.attnum, 'REFERENCES'
                                         )
                                       )
                                   )
                                 )
                               )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM user_sequences AS sequence
                               WHERE pg_catalog.has_sequence_privilege(
                                       current_user, sequence.oid, 'UPDATE'
                                     )
                                  OR (
                                    pg_catalog.has_sequence_privilege(
                                      current_user, sequence.oid, 'USAGE'
                                    ) AND NOT (
                                      sequence.nspname = 'public'
                                      AND sequence.relname IN (
                                        'ats_events_sequence_id_seq',
                                        'realtime_events_sequence_id_seq',
                                        'user_realtime_events_sequence_id_seq'
                                      )
                                    )
                                  )
                                  OR (
                                    pg_catalog.has_sequence_privilege(
                                      current_user, sequence.oid, 'SELECT'
                                    ) AND NOT (
                                      sequence.nspname = 'public'
                                      AND sequence.relname IN (
                                        'ats_events_sequence_id_seq',
                                        'realtime_events_sequence_id_seq',
                                        'user_realtime_events_sequence_id_seq'
                                      )
                                    )
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM guard_functions AS guard
                               WHERE guard.function_oid IS NULL
                                  OR pg_catalog.has_function_privilege(
                                    current_user, guard.function_oid, 'EXECUTE'
                                  )
                             )
                           ) AS has_dangerous_privileges,
                           (
                             NOT pg_catalog.has_schema_privilege(
                               current_user, 'public', 'USAGE'
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM mutable_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'INSERT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'UPDATE'
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM deletable_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'INSERT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'UPDATE'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'DELETE'
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM contact_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'INSERT'
                                  )
                                  OR EXISTS (
                                    SELECT 1
                                    FROM pg_catalog.pg_attribute AS attribute
                                    WHERE attribute.attrelid = relation.oid
                                      AND attribute.attname IN
                                          ('retired_at',
                                           'retired_operation_id',
                                           'updated_at')
                                      AND NOT pg_catalog.has_column_privilege(
                                        current_user, relation.oid,
                                        attribute.attnum, 'UPDATE'
                                      )
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM append_only_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'INSERT'
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM billing_insert_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'INSERT'
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM billing_select_only_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM public_job_catalog_select_only_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM admission_insert_tables AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               WHERE relation.oid IS NULL
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'SELECT'
                                  )
                                  OR NOT pg_catalog.has_table_privilege(
                                    current_user, relation.oid, 'INSERT'
                                  )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM admission_update_columns AS expected
                               LEFT JOIN user_tables AS relation
                                 ON relation.nspname = 'public'
                                AND relation.relname = expected.relname
                               LEFT JOIN pg_catalog.pg_attribute AS attribute
                                 ON attribute.attrelid = relation.oid
                                AND attribute.attname = expected.attname
                                AND attribute.attnum > 0
                                AND NOT attribute.attisdropped
                               WHERE relation.oid IS NULL
                                  OR attribute.attnum IS NULL
                                  OR NOT pg_catalog.has_column_privilege(
                                    current_user,
                                    relation.oid,
                                    attribute.attnum,
                                    'UPDATE'
                                  )
                             )
                             OR (
                               (SELECT enabled FROM family_authority_enabled)
                               AND (
                                 EXISTS (
                                   SELECT 1
                                   FROM authority_insert_tables AS expected
                                   LEFT JOIN user_tables AS relation
                                     ON relation.nspname = 'public'
                                    AND relation.relname = expected.relname
                                   WHERE relation.oid IS NULL
                                      OR NOT pg_catalog.has_table_privilege(
                                        current_user, relation.oid, 'SELECT'
                                      )
                                      OR NOT pg_catalog.has_table_privilege(
                                        current_user, relation.oid, 'INSERT'
                                      )
                                      OR EXISTS (
                                        SELECT 1
                                        FROM authority_update_columns AS expected_column
                                        LEFT JOIN pg_catalog.pg_attribute AS attribute
                                          ON attribute.attrelid = relation.oid
                                         AND attribute.attname = expected_column.attname
                                         AND attribute.attnum > 0
                                         AND NOT attribute.attisdropped
                                        WHERE expected_column.relname = expected.relname
                                          AND (
                                            attribute.attnum IS NULL
                                            OR NOT pg_catalog.has_column_privilege(
                                              current_user, relation.oid,
                                              attribute.attnum, 'UPDATE'
                                            )
                                          )
                                      )
                                 )
                                 OR EXISTS (
                                   SELECT 1
                                   FROM authority_select_only_tables AS expected
                                   LEFT JOIN user_tables AS relation
                                     ON relation.nspname = 'public'
                                    AND relation.relname = expected.relname
                                   WHERE relation.oid IS NULL
                                      OR NOT pg_catalog.has_table_privilege(
                                        current_user, relation.oid, 'SELECT'
                                      )
                                 )
                                 OR NOT COALESCE(
                                   pg_catalog.has_function_privilege(
                                     current_user,
                                     (SELECT function_oid
                                      FROM authority_policy_function),
                                     'EXECUTE'
                                   ),
                                   false
                                 )
                                 OR NOT COALESCE(
                                   (SELECT definition_is_safe
                                    FROM authority_policy_function),
                                   false
                                 )
                                 OR COALESCE(
                                   (SELECT public_can_execute
                                    FROM authority_policy_function),
                                   true
                                 )
                               )
                             )
                             OR EXISTS (
                               SELECT 1
                               FROM (
                                 VALUES
                                   ('ats_events_sequence_id_seq'),
                                   ('realtime_events_sequence_id_seq'),
                                   ('user_realtime_events_sequence_id_seq')
                               ) AS expected(relname)
                               LEFT JOIN user_sequences AS sequence
                                 ON sequence.nspname = 'public'
                                AND sequence.relname = expected.relname
                               WHERE sequence.oid IS NULL
                                  OR NOT pg_catalog.has_sequence_privilege(
                                    current_user, sequence.oid, 'USAGE'
                                  )
                                  OR NOT pg_catalog.has_sequence_privilege(
                                    current_user, sequence.oid, 'SELECT'
                                  )
                             )
                           ) AS has_missing_required_privileges
                    FROM runtime_role AS role
                    """
                )
            ).one_or_none()
        if row is None:
            raise RuntimeError("Unable to verify the CareSync Basic PostgreSQL runtime role")
        self.validate_basic_runtime_role(
            configured_user=settings.database_user,
            current_user=str(row.role_name),
            session_user=str(row.session_role_name),
            is_superuser=bool(row.rolsuper),
            bypasses_rls=bool(row.rolbypassrls),
            inherits_privileges=bool(row.rolinherit),
            can_create_role=bool(row.rolcreaterole),
            can_create_database=bool(row.rolcreatedb),
            can_replicate=bool(row.rolreplication),
            has_role_memberships=bool(row.has_role_memberships),
            owns_database_objects=bool(row.owns_database_objects),
            search_path_is_safe=bool(row.search_path_is_safe),
            has_unsafe_role_configuration=bool(row.has_unsafe_role_configuration),
            has_dangerous_privileges=bool(row.has_dangerous_privileges),
            has_missing_required_privileges=bool(row.has_missing_required_privileges),
        )

    def health(self) -> dict[str, Any]:
        """Verify connectivity and SQLite integrity without exposing record data."""

        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                integrity = "not_applicable"
                if self.settings.database_type == "sqlite":
                    integrity = str(connection.exec_driver_sql("PRAGMA quick_check").scalar_one())
            return {
                "connected": True,
                "integrity": integrity,
                "database_name": self.settings.database_name,
                "database_filename": (
                    self.settings.database_path.name
                    if self.settings.database_type == "sqlite"
                    else self.settings.database_name
                ),
            }
        except Exception:
            return {
                "connected": False,
                "integrity": "unavailable",
                "database_name": self.settings.database_name,
                "database_filename": (
                    self.settings.database_path.name
                    if self.settings.database_type == "sqlite"
                    else self.settings.database_name
                ),
            }

    def transport_evidence_ingest_runtime_available(self) -> bool:
        """Probe the separately authenticated server-only 0032 evidence identity."""

        if (
            self.settings.database_type != "postgres"
            or self.settings.database_read_only
            or self.settings.enable_advanced_routes
            or self.transport_evidence_engine is None
            or self.transport_evidence_session_factory is None
        ):
            return False
        try:
            with self.transport_evidence_engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT current_user AS current_user_name,"
                        "session_user AS session_user_name,"
                        "pg_catalog.replace(pg_catalog.current_setting('search_path'),' ','') "
                        "AS search_path,"
                        "pg_catalog.current_setting('transaction_read_only') AS read_only"
                    )
                ).one()
            return bool(
                str(row.current_user_name) == "caresync_transport_evidence_ingest"
                and str(row.session_user_name) == "caresync_transport_evidence_ingest"
                and str(row.search_path) == "public,pg_catalog"
                and str(row.read_only).lower() == "off"
            )
        except Exception:
            # Invalid/missing credentials keep evidence commands unavailable;
            # they never fall back to the ordinary basic runtime identity.
            return False

    def dispose(self) -> None:
        if self.transport_evidence_engine is not None:
            self.transport_evidence_engine.dispose()
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    """Provide one transaction-scoped session per request."""

    with request.app.state.database.session_factory() as session:
        yield session
