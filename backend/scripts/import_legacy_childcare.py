"""Import legacy family and child records into CareSync Basic safely.

The command is a dry run unless ``--apply`` is supplied. Source connections are
forced read-only, source identifiers are retained as stable import identities,
and a rerun never overwrites a row that is already present in the target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

TABLES = ("families", "guardians", "emergency_contacts", "children")
OPEN_ENROLLMENT_STATUSES = ("pending", "active", "paused")


@dataclass(frozen=True)
class Placement:
    enrollment_id: UUID
    child_id: UUID
    facility_id: UUID
    program_id: UUID | None
    room_id: UUID | None
    start_date: date
    status: str


@dataclass
class ImportPlan:
    source_organization_id: UUID
    target_organization_id: UUID
    source_fingerprint: str
    rows: dict[str, list[dict[str, Any]]]
    placements: list[Placement]
    skipped: Counter[str]
    unassigned_by_age_group: Counter[str]

    def summary(self, *, mode: str) -> dict[str, Any]:
        return {
            "mode": mode,
            "source_organization_id": str(self.source_organization_id),
            "target_organization_id": str(self.target_organization_id),
            "source_fingerprint": self.source_fingerprint,
            "insert": {key: len(value) for key, value in self.rows.items()},
            "active_enrollments": len(self.placements),
            "unassigned_active_children": sum(self.unassigned_by_age_group.values()),
            "unassigned_by_age_group": dict(sorted(self.unassigned_by_age_group.items())),
            "already_present": dict(sorted(self.skipped.items())),
        }


def _connection_uri(host: str, port: int, user: str, database: str) -> str:
    return f"postgresql://{user}@{host}:{port}/{database}"


def _single_organization(connection: psycopg.Connection, name: str, *, source: bool):
    rows = connection.execute(
        "SELECT id, name FROM organizations WHERE lower(trim(name)) = lower(trim(%s))",
        (name,),
    ).fetchall()
    if len(rows) != 1:
        side = "source" if source else "target"
        raise RuntimeError(f"Expected exactly one {side} organization named {name!r}")
    return rows[0]


def _source_rows(connection: psycopg.Connection, organization_id: UUID):
    families = connection.execute(
        "SELECT id, name, file_number, status, additional_notes, photo_consent, "
        "field_trip_consent, emergency_medical_consent, created_at, updated_at "
        "FROM families WHERE organization_id = %s ORDER BY id",
        (organization_id,),
    ).fetchall()
    family_ids = [row["id"] for row in families]
    if not family_ids:
        raise RuntimeError("The selected source organization has no families")
    guardians = connection.execute(
        "SELECT id, family_id, first_name, last_name, relationship, guardian_type, "
        "email, cell_phone, home_phone, work_phone, address, city, postal_code, "
        "created_at, updated_at FROM guardians WHERE family_id = ANY(%s) ORDER BY id",
        (family_ids,),
    ).fetchall()
    contacts = connection.execute(
        "SELECT id, family_id, first_name, last_name, relationship, cell_phone, "
        "home_phone, authorized_pickup, created_at, updated_at "
        "FROM emergency_contacts WHERE family_id = ANY(%s) ORDER BY id",
        (family_ids,),
    ).fetchall()
    children = connection.execute(
        "SELECT id, family_id, first_name, middle_name, last_name, date_of_birth, "
        "start_date, gender, age_group, health_care_number, allergies, medical_conditions, "
        "medications, immunization_up_to_date, doctor_name, doctor_phone, is_active, "
        "created_at, updated_at FROM children WHERE family_id = ANY(%s) ORDER BY id",
        (family_ids,),
    ).fetchall()
    return {
        "families": [dict(row) for row in families],
        "guardians": [dict(row) for row in guardians],
        "emergency_contacts": [dict(row) for row in contacts],
        "children": [dict(row) for row in children],
    }


def _fingerprint(rows: dict[str, list[dict[str, Any]]]) -> str:
    digest = hashlib.sha256()
    for table in TABLES:
        digest.update(table.encode())
        for row in rows[table]:
            payload = {key: str(value) if value is not None else None for key, value in row.items()}
            digest.update(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def _existing_id_owners(connection: psycopg.Connection, table: str) -> dict[UUID, UUID]:
    return {
        row["id"]: row["organization_id"]
        for row in connection.execute(f"SELECT id, organization_id FROM {table}").fetchall()
    }


def _room_preferences(age_group: str | None, rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_age = (age_group or "").strip().lower()
    program_type = "out_of_school_care" if normalized_age == "school-age" else "daycare"
    candidates = [room for room in rooms if room["program_type"] == program_type]
    keywords = {
        "infant": ("infant", "mixed"),
        "toddler": ("toddler", "mixed"),
        "preschool": ("preschool", "kinder", "mixed"),
        "school-age": ("osc", "school", "mixed"),
    }.get(normalized_age, ("mixed",))

    def score(room: dict[str, Any]) -> tuple[int, str, str]:
        name = room["name"].strip().lower()
        keyword_rank = next((index for index, word in enumerate(keywords) if word in name), 99)
        return keyword_rank, name, str(room["id"])

    return sorted(candidates, key=score)


def _target_structure(connection: psycopg.Connection, organization_id: UUID):
    facilities = connection.execute(
        "SELECT id, name FROM facilities WHERE organization_id = %s AND status = 'active' "
        "ORDER BY id FOR UPDATE",
        (organization_id,),
    ).fetchall()
    if len(facilities) != 1:
        raise RuntimeError("Legacy import requires exactly one active target facility")
    facility = dict(facilities[0])
    rooms = [
        dict(row)
        for row in connection.execute(
            "SELECT r.id, r.name, r.capacity, r.program_id, p.program_type "
            "FROM rooms r JOIN facility_programs p "
            "ON p.organization_id = r.organization_id AND p.id = r.program_id "
            "WHERE r.organization_id = %s AND r.facility_id = %s "
            "AND r.is_active = true AND p.is_active = true ORDER BY r.id FOR UPDATE OF r",
            (organization_id, facility["id"]),
        ).fetchall()
    ]
    occupancy = Counter(
        {
            row["room_id"]: row["occupancy"]
            for row in connection.execute(
                "SELECT room_id, count(*)::int AS occupancy FROM enrollments "
                "WHERE organization_id = %s AND facility_id = %s "
                "AND room_id IS NOT NULL AND status = ANY(%s) "
                "AND (end_date IS NULL OR end_date >= CURRENT_DATE) GROUP BY room_id",
                (organization_id, facility["id"], list(OPEN_ENROLLMENT_STATUSES)),
            ).fetchall()
        }
    )
    return facility, rooms, occupancy


def build_plan(
    source: psycopg.Connection,
    target: psycopg.Connection,
    *,
    source_organization_name: str,
    target_organization_name: str,
) -> ImportPlan:
    source_organization = _single_organization(
        source, source_organization_name, source=True
    )
    target_organization = _single_organization(
        target, target_organization_name, source=False
    )
    source_rows = _source_rows(source, source_organization["id"])
    skipped: Counter[str] = Counter()
    insert_rows: dict[str, list[dict[str, Any]]] = {table: [] for table in TABLES}

    for table in TABLES:
        existing = _existing_id_owners(target, table)
        for source_row in source_rows[table]:
            owner = existing.get(source_row["id"])
            if owner is not None:
                if owner != target_organization["id"]:
                    raise RuntimeError(f"{table} identifier collides with another target tenant")
                skipped[table] += 1
                continue
            row = dict(source_row)
            row["organization_id"] = target_organization["id"]
            if table == "guardians":
                row["is_primary"] = row.pop("guardian_type") == "primary"
                # The legacy table has no explicit guardian pickup authorization fact.
                row["authorized_pickup"] = False
            insert_rows[table].append(row)

    facility, _rooms, _occupancy = _target_structure(target, target_organization["id"])
    existing_enrollment_owners = _existing_id_owners(target, "enrollments")
    placements: list[Placement] = []
    unassigned: Counter[str] = Counter()
    age_order = {"Infant": 0, "Toddler": 1, "Preschool": 2, "School-Age": 3}
    active_children = sorted(
        (row for row in source_rows["children"] if row["is_active"]),
        key=lambda row: (
            age_order.get(row["age_group"], 99),
            row["last_name"].casefold(),
            row["first_name"].casefold(),
            str(row["id"]),
        ),
    )
    for child in active_children:
        enrollment_id = uuid5(
            NAMESPACE_URL,
            f"caresync:legacy-enrollment:{facility['id']}:{child['id']}",
        )
        owner = existing_enrollment_owners.get(enrollment_id)
        if owner is not None:
            if owner != target_organization["id"]:
                raise RuntimeError("Deterministic enrollment identifier collides across tenants")
            skipped["enrollments"] += 1
            continue
        # Import establishes the historical enrollment fact, but never guesses a
        # care placement. DOB-based compatible rooms are shown in the explicit
        # review queue and a manager must approve one after import.
        program_id = None
        room_id = None
        unassigned[child["age_group"] or "Unknown"] += 1
        placements.append(
            Placement(
                enrollment_id=enrollment_id,
                child_id=child["id"],
                facility_id=facility["id"],
                program_id=program_id,
                room_id=room_id,
                start_date=child["start_date"],
                status="active",
            )
        )

    return ImportPlan(
        source_organization_id=source_organization["id"],
        target_organization_id=target_organization["id"],
        source_fingerprint=_fingerprint(source_rows),
        rows=insert_rows,
        placements=placements,
        skipped=skipped,
        unassigned_by_age_group=unassigned,
    )


def _insert_rows(connection: psycopg.Connection, plan: ImportPlan) -> None:
    family_columns = (
        "id", "organization_id", "name", "file_number", "status", "additional_notes",
        "photo_consent", "field_trip_consent", "emergency_medical_consent", "created_at",
        "updated_at",
    )
    guardian_columns = (
        "id", "organization_id", "family_id", "first_name", "last_name", "relationship",
        "email", "cell_phone", "home_phone", "work_phone", "address", "city", "postal_code",
        "is_primary", "authorized_pickup", "created_at", "updated_at",
    )
    contact_columns = (
        "id", "organization_id", "family_id", "first_name", "last_name", "relationship",
        "cell_phone", "home_phone", "authorized_pickup", "created_at", "updated_at",
    )
    child_columns = (
        "id", "organization_id", "family_id", "first_name", "middle_name", "last_name",
        "date_of_birth", "gender", "age_group", "is_active", "health_care_number", "allergies",
        "medical_conditions", "medications", "immunization_up_to_date", "doctor_name",
        "doctor_phone", "created_at", "updated_at",
    )
    definitions = {
        "families": family_columns,
        "guardians": guardian_columns,
        "emergency_contacts": contact_columns,
        "children": child_columns,
    }
    for table in TABLES:
        columns = definitions[table]
        placeholders = ", ".join(["%s"] * len(columns))
        statement = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        for row in plan.rows[table]:
            connection.execute(statement, tuple(row[column] for column in columns))
    for placement in plan.placements:
        connection.execute(
            "INSERT INTO enrollments "
            "(id, organization_id, facility_id, child_id, program_id, room_id, start_date, "
            "end_date, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                placement.enrollment_id,
                plan.target_organization_id,
                placement.facility_id,
                placement.child_id,
                placement.program_id,
                placement.room_id,
                placement.start_date,
                placement.status,
            ),
        )
    changed = bool(plan.placements or any(plan.rows.values()))
    if changed:
        connection.execute(
            "INSERT INTO audit_events "
            "(id, organization_id, facility_id, actor_user_id, action, entity_type, entity_id, "
            "details) VALUES (%s, %s, NULL, NULL, %s, %s, %s, %s)",
            (
                uuid4(),
                plan.target_organization_id,
                "migration.legacy_childcare.imported",
                "organization",
                plan.target_organization_id,
                Jsonb(plan.summary(mode="applied")),
            ),
        )


def queue_existing_placements_for_review(
    source: psycopg.Connection,
    target: psycopg.Connection,
    plan: ImportPlan,
) -> int:
    """Unassign only deterministic legacy enrollments created by this importer."""

    source_rows = _source_rows(source, plan.source_organization_id)
    active_child_ids = [row["id"] for row in source_rows["children"] if row["is_active"]]
    facility = target.execute(
        "SELECT id FROM facilities WHERE organization_id = %s AND status = 'active' "
        "ORDER BY id FOR UPDATE",
        (plan.target_organization_id,),
    ).fetchall()
    if len(facility) != 1:
        raise RuntimeError("Placement review conversion requires one active target facility")
    enrollment_ids = [
        uuid5(
            NAMESPACE_URL,
            f"caresync:legacy-enrollment:{facility[0]['id']}:{child_id}",
        )
        for child_id in active_child_ids
    ]
    enrollments = target.execute(
        "SELECT id, child_id, program_id, room_id FROM enrollments "
        "WHERE organization_id = %s AND id = ANY(%s) FOR UPDATE",
        (plan.target_organization_id, enrollment_ids),
    ).fetchall()
    if len(enrollments) != len(enrollment_ids):
        raise RuntimeError("Placement review conversion found missing imported enrollments")
    if {row["child_id"] for row in enrollments} != set(active_child_ids):
        raise RuntimeError("Placement review conversion found an enrollment identity mismatch")

    open_attendance = target.execute(
        "SELECT count(*)::int AS count FROM attendance_intervals i "
        "JOIN attendance_days d ON d.organization_id = i.organization_id "
        "AND d.id = i.attendance_day_id "
        "WHERE d.organization_id = %s AND d.enrollment_id = ANY(%s) "
        "AND i.checked_out_at IS NULL",
        (plan.target_organization_id, enrollment_ids),
    ).fetchone()["count"]
    if open_attendance:
        raise RuntimeError(
            "Check out imported children before moving their placements into review"
        )

    changed_ids = [
        row["id"]
        for row in enrollments
        if row["program_id"] is not None or row["room_id"] is not None
    ]
    if not changed_ids:
        return 0
    target.execute(
        "UPDATE enrollments SET program_id = NULL, room_id = NULL, "
        "updated_at = CURRENT_TIMESTAMP WHERE organization_id = %s AND id = ANY(%s)",
        (plan.target_organization_id, changed_ids),
    )
    target.execute(
        "INSERT INTO audit_events "
        "(id, organization_id, facility_id, actor_user_id, action, entity_type, entity_id, "
        "details) VALUES (%s, %s, %s, NULL, %s, %s, %s, %s)",
        (
            uuid4(),
            plan.target_organization_id,
            facility[0]["id"],
            "migration.legacy_childcare.placement_review_queued",
            "organization",
            plan.target_organization_id,
            Jsonb(
                {
                    "enrollment_count": len(changed_ids),
                    "source_fingerprint": plan.source_fingerprint,
                    "approval_required": True,
                }
            ),
        ),
    )
    return len(changed_ids)


def verify_import(
    source: psycopg.Connection,
    target: psycopg.Connection,
    plan: ImportPlan,
) -> dict[str, int]:
    """Prove every mapped source fact and active-child enrollment is present."""

    source_rows = _source_rows(source, plan.source_organization_id)
    source_by_table = {
        table: {row["id"]: row for row in rows}
        for table, rows in source_rows.items()
    }
    columns = {
        "families": (
            "name", "file_number", "status", "additional_notes", "photo_consent",
            "field_trip_consent", "emergency_medical_consent",
        ),
        "guardians": (
            "family_id", "first_name", "last_name", "relationship", "email", "cell_phone",
            "home_phone", "work_phone", "address", "city", "postal_code",
        ),
        "emergency_contacts": (
            "family_id", "first_name", "last_name", "relationship", "cell_phone",
            "home_phone", "authorized_pickup",
        ),
        "children": (
            "family_id", "first_name", "middle_name", "last_name", "date_of_birth", "gender",
            "age_group", "is_active", "health_care_number", "allergies", "medical_conditions",
            "medications", "immunization_up_to_date", "doctor_name", "doctor_phone",
        ),
    }
    verified: dict[str, int] = {}
    for table in TABLES:
        ids = list(source_by_table[table])
        extra_columns = ("is_primary", "authorized_pickup") if table == "guardians" else ()
        selected = ", ".join(("id", "organization_id", *columns[table], *extra_columns))
        actual_rows = target.execute(
            f"SELECT {selected} FROM {table} WHERE id = ANY(%s)",
            (ids,),
        ).fetchall()
        actual_by_id = {row["id"]: row for row in actual_rows}
        if set(actual_by_id) != set(ids):
            raise RuntimeError(f"Import verification failed: missing {table} identifiers")
        for row_id, source_row in source_by_table[table].items():
            actual = actual_by_id[row_id]
            if actual["organization_id"] != plan.target_organization_id:
                raise RuntimeError(f"Import verification failed: cross-tenant {table} row")
            for column in columns[table]:
                if actual[column] != source_row[column]:
                    raise RuntimeError(
                        f"Import verification failed: {table}.{column} differs for {row_id}"
                    )
            if table == "guardians":
                if actual["is_primary"] != (source_row["guardian_type"] == "primary"):
                    raise RuntimeError("Import verification failed: guardian role differs")
                if actual["authorized_pickup"]:
                    raise RuntimeError(
                        "Import verification failed: unknown pickup fact became true"
                    )
        verified[table] = len(actual_rows)

    active_children = {
        row["id"]: row for row in source_rows["children"] if row["is_active"]
    }
    facility_id = target.execute(
        "SELECT id FROM facilities WHERE organization_id = %s AND status = 'active' "
        "ORDER BY id LIMIT 1",
        (plan.target_organization_id,),
    ).fetchone()["id"]
    expected_enrollment_ids = {
        uuid5(
            NAMESPACE_URL,
            f"caresync:legacy-enrollment:{facility_id}:{child_id}",
        ): child_id
        for child_id in active_children
    }
    enrollment_rows = target.execute(
        "SELECT id, organization_id, child_id, start_date, status, program_id, room_id "
        "FROM enrollments WHERE id = ANY(%s)",
        (list(expected_enrollment_ids),),
    ).fetchall()
    if len(enrollment_rows) != len(active_children):
        raise RuntimeError("Import verification failed: active enrollment count differs")
    for enrollment in enrollment_rows:
        child_id = expected_enrollment_ids[enrollment["id"]]
        if (
            enrollment["organization_id"] != plan.target_organization_id
            or enrollment["child_id"] != child_id
            or enrollment["start_date"] != active_children[child_id]["start_date"]
            or enrollment["status"] != "active"
            or enrollment["program_id"] is not None
            or enrollment["room_id"] is not None
        ):
            raise RuntimeError("Import verification failed: active enrollment differs")
    verified["active_enrollments"] = len(enrollment_rows)
    return verified


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--user", default="amarmuha")
    parser.add_argument("--source-database", default="caresync")
    parser.add_argument("--target-database", default="caresync")
    parser.add_argument("--source-port", type=int, default=5433)
    parser.add_argument("--target-port", type=int, default=5434)
    parser.add_argument("--source-organization", default="Discoverers' Daycare")
    parser.add_argument("--target-organization", default="Discoverers' Daycare")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--queue-existing-placements-for-review", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.source_port == args.target_port:
        raise RuntimeError("Source and target database endpoints must be different")
    if args.queue_existing_placements_for_review and not args.apply:
        raise RuntimeError("Placement review conversion requires --apply")
    source_uri = _connection_uri(
        args.host, args.source_port, args.user, args.source_database
    )
    target_uri = _connection_uri(
        args.host, args.target_port, args.user, args.target_database
    )
    with (
        psycopg.connect(source_uri, row_factory=dict_row) as source,
        psycopg.connect(target_uri, row_factory=dict_row) as target,
    ):
        source.execute("SET TRANSACTION READ ONLY")
        target.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        plan = build_plan(
            source,
            target,
            source_organization_name=args.source_organization,
            target_organization_name=args.target_organization,
        )
        if args.apply:
            queued_placements = (
                queue_existing_placements_for_review(source, target, plan)
                if args.queue_existing_placements_for_review
                else 0
            )
            _insert_rows(target, plan)
            target.commit()
            verification = verify_import(source, target, plan)
            mode = "applied"
        else:
            target.rollback()
            verification = None
            mode = "dry-run"
        summary = plan.summary(mode=mode)
        if verification is not None:
            summary["verified"] = verification
        if args.queue_existing_placements_for_review:
            summary["queued_existing_placements"] = queued_placements
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
