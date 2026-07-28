"""TimeSavr family CSV parsing, sibling detection, and transactional imports."""

import csv
import re
from datetime import date
from io import StringIO
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request, status
from sqlalchemy import delete

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import Children, EmergencyContacts, Families, Guardians

router = APIRouter(prefix="/csv-imports", tags=["CSV imports"])
MONTHS = dict(
    zip(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        (f"{month:02d}" for month in range(1, 13)),
        strict=True,
    )
)


def _ensure_writable(request: Request) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )


def _organization_id(current_user: CurrentUser):
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An organization is required for CSV imports",
        )
    return current_user.organization_id


def _full_name(value: str | None) -> tuple[str, str, str]:
    parts = (value or "").strip().split()
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def _title(value: str | None) -> str:
    return " ".join(part.capitalize() for part in (value or "").strip().split())


def _parse_date(value: str | None) -> str:
    raw = (value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    match = re.fullmatch(r"(\w{3})\s+(\d{1,2}),?\s+(\d{4})", raw)
    if match and match.group(1).title() in MONTHS:
        return f"{match.group(3)}-{MONTHS[match.group(1).title()]}-{match.group(2).zfill(2)}"
    return ""


def _phone(value: str | None) -> str:
    raw = (value or "").strip()
    digits = re.sub(r"\D", "", raw)
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}" if len(digits) == 10 else raw


def _address(value: str | None) -> tuple[str, str, str]:
    raw = (value or "").strip()
    postal_match = re.search(r"([A-Za-z]\d[A-Za-z]\s*\d[A-Za-z]\d)\s*$", raw)
    postal_code = ""
    remaining = raw
    if postal_match:
        compact = re.sub(r"\s", "", postal_match.group(1)).upper()
        postal_code = f"{compact[:3]} {compact[3:]}"
        remaining = raw[: postal_match.start()].strip()
    city_match = re.search(
        r",?\s*([A-Za-z]+)\s+(?:AB|BC|SK|MB|ON|QC|NB|NS|PE|NL|YT|NT|NU)\s*$",
        remaining,
        re.I,
    )
    if not city_match:
        return remaining or "Address Update Required", "Unknown", postal_code
    street = remaining[: city_match.start()].rstrip(" ,")
    return street or "Address Update Required", city_match.group(1).title(), postal_code


def _gender(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if normalized in {"m", "male"}:
        return "male"
    if normalized in {"f", "female"}:
        return "female"
    return None


def _age_group(birth_date: date) -> str:
    today = date.today()
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    months -= today.day < birth_date.day
    if months < 19:
        return "infant"
    if months < 36:
        return "toddler"
    if months < 60:
        return "preschool"
    return "school-age"


def _parse_csv(content: str) -> dict:
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames:
        return {"totalRows": 0, "families": [], "warnings": ["CSV file is empty"]}
    reader.fieldnames = [header.strip() for header in reader.fieldnames]
    families: list[dict[str, Any]] = []
    warnings: list[str] = []
    today = date.today().isoformat()
    for index, raw_row in enumerate(reader):
        row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items()}
        child_first, child_middle, child_last = _full_name(row.get("Child Name"))
        child_first = _title(child_first) or f"Unknown{index + 1}"
        child_last = _title(child_last) or f"Person{index + 1}"
        mother_first, mother_middle, mother_last = _full_name(row.get("Mother Name"))
        mother_first = _title(mother_first) or f"Unknown{index + 1}"
        mother_last = _title(mother_last or mother_middle) or child_last
        mother_phone = _phone(row.get("Mother Phone"))
        mother_email = row.get("Mother Email", "").lower()
        missing: list[str] = []
        if not mother_phone:
            mother_phone = "000-000-0000"
            missing.append("phone")
        if not mother_email:
            safe_first = re.sub(r"[^a-z]", "", mother_first.lower()) or "unknown"
            safe_last = re.sub(r"[^a-z]", "", mother_last.lower()) or "person"
            mother_email = f"{safe_first}.{safe_last}.{index + 1}@update-required.local"
            missing.append("email")
        street, city, postal_code = _address(row.get("Address"))
        if street == "Address Update Required":
            missing.append("address")
        birth = _parse_date(row.get("Birth Date"))
        start = _parse_date(row.get("Start Date"))
        if not birth:
            birth = today
            missing.append("birth_date")
        if not start:
            start = today
            missing.append("start_date")
        secondary = None
        if row.get("Father Name"):
            first, middle, last = _full_name(row["Father Name"])
            secondary = {
                "firstName": _title(first) or f"Unknown{index + 1}",
                "lastName": _title(last or middle) or mother_last,
                "phone": _phone(row.get("Father Phone")),
                "email": row.get("Father Email", "").lower(),
                "relationship": "Father",
            }
        emergency = None
        if row.get("Emergency Contact Name"):
            first, _, last = _full_name(row["Emergency Contact Name"])
            emergency = {
                "firstName": _title(first) or "Emergency",
                "lastName": _title(last) or "Contact",
                "phone": _phone(row.get("Emergency Contact Phone")) or "000-000-0000",
            }
        family = {
            "familyKey": f"row-{index}",
            "familyName": f"{child_last} Family",
            "address": street,
            "city": city,
            "postalCode": postal_code,
            "primaryGuardian": {
                "firstName": mother_first,
                "lastName": mother_last,
                "phone": mother_phone,
                "email": mother_email,
                "relationship": "Mother",
            },
            "secondaryGuardian": secondary,
            "children": [
                {
                    "firstName": child_first,
                    "middleName": _title(child_middle),
                    "lastName": child_last,
                    "dateOfBirth": birth,
                    "startDate": start,
                    "gender": _gender(row.get("Sex")),
                    "healthCareNumber": row.get("Health Care #", ""),
                    "doctorName": row.get("Physician", ""),
                    "allergies": row.get("Medical Details (Allergies/Diet/Concerns)", ""),
                    "immunizationUpToDate": row.get("Immunization Up To Date", "").lower() == "yes",
                }
            ],
            "emergencyContact": emergency,
        }
        families.append(family)
        if missing:
            warnings.append(
                f"Row {index + 2}: {family['familyName']} - Missing data "
                f"(placeholders used): {', '.join(missing)}"
            )
    return {"totalRows": len(families), "families": families, "warnings": warnings}


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _pair_match(left: dict, right: dict) -> tuple[int, list[str]]:
    left_guardian, right_guardian = left["primaryGuardian"], right["primaryGuardian"]
    evidence: list[str] = []
    same_phone = left_guardian["phone"] != "000-000-0000" and _normalized(
        left_guardian["phone"]
    ) == _normalized(right_guardian["phone"])
    same_email = (
        "@update-required" not in left_guardian["email"]
        and left_guardian["email"] == right_guardian["email"]
    )
    same_last = left["children"][0]["lastName"].lower() == right["children"][0]["lastName"].lower()
    same_address = left["address"] != "Address Update Required" and _normalized(
        left["address"]
    ) == _normalized(right["address"])
    left_name = f"{left_guardian['firstName']} {left_guardian['lastName']}".lower()
    right_name = f"{right_guardian['firstName']} {right_guardian['lastName']}".lower()
    same_guardian = left_name == right_name and "unknown" not in left_name
    if same_phone:
        return 95, [f"Same phone: {left_guardian['phone']}"]
    if same_email:
        return 95, [f"Same email: {left_guardian['email']}"]
    if same_guardian:
        evidence.append(f"Same guardian: {left_name.title()}")
    if same_last:
        evidence.append(f"Same last name: {left['children'][0]['lastName']}")
    if same_address:
        evidence.append("Same address")
    if same_guardian and same_last:
        return 85, evidence
    if same_address and same_last:
        return 80, evidence
    if same_guardian and same_address:
        return 75, evidence
    return 0, []


def _detect(families: list[dict]) -> list[dict]:
    parents = list(range(len(families)))

    def find(value: int) -> int:
        while parents[value] != value:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value

    pair_results: dict[tuple[int, int], tuple[int, list[str]]] = {}
    for left in range(len(families)):
        for right in range(left + 1, len(families)):
            score, evidence = _pair_match(families[left], families[right])
            if score:
                left_root, right_root = find(left), find(right)
                parents[right_root] = left_root
                pair_results[(left, right)] = (score, evidence)
    clusters: dict[int, list[int]] = {}
    for index in range(len(families)):
        clusters.setdefault(find(index), []).append(index)
    matches: list[dict] = []
    for indices in clusters.values():
        if len(indices) < 2:
            continue
        evidence: list[str] = []
        score = 0
        for left_pos, left in enumerate(indices):
            for right in indices[left_pos + 1 :]:
                pair_score, pair_evidence = pair_results.get((left, right), (0, []))
                score = max(score, pair_score)
                evidence.extend(item for item in pair_evidence if item not in evidence)
        matches.append(
            {
                "id": f"match-{len(matches)}",
                "familyIndices": indices,
                "familyNames": [families[index]["familyName"] for index in indices],
                "childNames": [
                    f"{child['firstName']} {child['lastName']}"
                    for index in indices
                    for child in families[index]["children"]
                ],
                "confidenceScore": score,
                "evidence": evidence,
            }
        )
    return sorted(matches, key=lambda match: match["confidenceScore"], reverse=True)


def _merge(families: list[dict], groups: list[list[int]]) -> list[dict]:
    if not groups:
        return families
    parents: dict[int, int] = {}

    def find(value: int) -> int:
        parents.setdefault(value, value)
        if parents[value] != value:
            parents[value] = find(parents[value])
        return parents[value]

    for group in groups:
        for value in group[1:]:
            parents[find(value)] = find(group[0])
    clusters: dict[int, list[int]] = {}
    for group in groups:
        for value in group:
            if 0 <= value < len(families):
                clusters.setdefault(find(value), []).append(value)
    processed: set[int] = set()
    result: list[dict] = []
    for raw_indices in clusters.values():
        indices = sorted(set(raw_indices))
        base = {**families[indices[0]], "children": []}
        for index in indices:
            base["children"].extend(families[index]["children"])
            processed.add(index)
        last_names = list(dict.fromkeys(child["lastName"] for child in base["children"]))
        base["familyName"] = " & ".join(last_names) + " Family"
        result.append(base)
    result.extend(family for index, family in enumerate(families) if index not in processed)
    return result


def _import_families(
    families: list[dict], current_user: CurrentUser, session: SessionDependency
) -> dict:
    created_families = 0
    created_children = 0
    errors: list[dict] = []
    for row_number, parsed in enumerate(families, start=1):
        try:
            with session.begin_nested():
                family = Families(
                    organization_id=_organization_id(current_user),
                    name=parsed["familyName"],
                    status="active",
                    photo_consent=True,
                    field_trip_consent=True,
                    emergency_medical_consent=True,
                )
                session.add(family)
                session.flush()
                guardians = [parsed["primaryGuardian"]]
                if parsed.get("secondaryGuardian"):
                    guardians.append(parsed["secondaryGuardian"])
                for position, guardian in enumerate(guardians):
                    session.add(
                        Guardians(
                            family_id=family.id,
                            first_name=guardian["firstName"],
                            last_name=guardian["lastName"],
                            relationship_=guardian["relationship"],
                            guardian_type="primary" if position == 0 else "secondary",
                            email=guardian["email"],
                            cell_phone=guardian["phone"],
                            address=parsed["address"],
                            city=parsed["city"],
                            postal_code=parsed["postalCode"],
                        )
                    )
                for child in parsed["children"]:
                    birth_date = date.fromisoformat(child["dateOfBirth"])
                    session.add(
                        Children(
                            family_id=family.id,
                            first_name=child["firstName"],
                            middle_name=child.get("middleName") or None,
                            last_name=child["lastName"],
                            date_of_birth=birth_date,
                            start_date=date.fromisoformat(child["startDate"]),
                            is_active=True,
                            age_group=_age_group(birth_date),
                            gender=child.get("gender"),
                            health_care_number=child.get("healthCareNumber") or None,
                            doctor_name=child.get("doctorName") or None,
                            allergies=child.get("allergies") or None,
                            immunization_up_to_date=child.get("immunizationUpToDate"),
                        )
                    )
                emergency = parsed.get("emergencyContact") or {
                    "firstName": "Emergency",
                    "lastName": "Contact",
                    "phone": "000-000-0000",
                }
                session.add(
                    EmergencyContacts(
                        family_id=family.id,
                        first_name=emergency["firstName"],
                        last_name=emergency["lastName"],
                        relationship_=(
                            "Family Friend" if parsed.get("emergencyContact") else "Update Required"
                        ),
                        cell_phone=emergency["phone"],
                        authorized_pickup=True,
                    )
                )
                session.flush()
            created_families += 1
            created_children += len(parsed["children"])
        except Exception as exc:
            errors.append(
                {"row": row_number, "childName": parsed["familyName"], "message": str(exc)}
            )
    session.commit()
    return {
        "success": not errors,
        "totalRows": len(families),
        "familiesCreated": created_families,
        "childrenCreated": created_children,
        "familiesSkipped": 0,
        "childrenSkipped": 0,
        "errors": errors,
        "skippedReasons": [],
    }


@router.post("/detect")
def detect_siblings(current_user: CurrentUser, payload: Annotated[dict[str, str], Body()]) -> dict:
    _organization_id(current_user)
    parsed = _parse_csv(payload.get("csvContent", ""))
    return {
        "families": parsed["families"],
        "siblingMatches": _detect(parsed["families"]),
        "warnings": parsed["warnings"],
    }


@router.post("/import")
def import_csv(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict:
    _ensure_writable(request)
    parsed = _parse_csv(payload.get("csvContent", ""))
    return _import_families(
        _merge(parsed["families"], payload.get("mergeGroups") or []),
        current_user,
        session,
    )


@router.post("/import-direct")
def import_csv_direct(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict:
    _ensure_writable(request)
    organization_id = _organization_id(current_user)
    if payload.get("deleteExisting"):
        session.execute(delete(Families).where(Families.organization_id == organization_id))
        session.flush()
    parsed = _parse_csv(payload.get("csvContent", ""))
    return _import_families(parsed["families"], current_user, session)
