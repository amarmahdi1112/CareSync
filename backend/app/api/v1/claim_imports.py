"""PDF claim parsing and organization-scoped imported-claim batches."""

import base64
import calendar
import difflib
import re
import unicodedata
from datetime import date
from io import BytesIO
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Request, status
from pypdf import PdfReader
from sqlalchemy import delete, func, insert, select, update

from app.api.dependencies import CurrentUser, SessionDependency
from app.models.generated_legacy import Base

router = APIRouter(prefix="/claim-imports", tags=["claim imports"])
tables = Base.metadata.tables
MONTHS = {name.lower(): f"{index:02d}" for index, name in enumerate(calendar.month_abbr) if name}


def _organization_id(current_user: CurrentUser) -> UUID:
    if current_user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An organization is required for claim imports",
        )
    return current_user.organization_id


def _ensure_writable(request: Request) -> None:
    if request.app.state.settings.database_read_only:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Database writes are disabled; create a backup and set DATABASE_READ_ONLY=false",
        )


def _care_category(context: str) -> str:
    value = context.lower()
    if any(term in value for term in ("out-of-school", "school-aged", "grade 1-6")):
        return "SchoolAge"
    if any(
        term in value for term in ("infant", "less than 12 months", "12 months to less than 19")
    ):
        return "Infant"
    if "19 months" in value or "less than 3 years" in value:
        return "Toddler"
    if any(term in value for term in ("3 years", "4 years", "kindergarten", "daycare")):
        return "Preschool"
    return "Unknown"


def _dob(context: str) -> str | None:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", context)
    if match and 2005 <= int(match.group(1)[:4]) <= date.today().year:
        return match.group(1)
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", context)
    if match and 2005 <= int(match.group(3)) <= date.today().year:
        return f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
    match = re.search(
        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d{2})\b",
        context,
        re.I,
    )
    if match and 2005 <= int(match.group(3)) <= date.today().year:
        return f"{match.group(3)}-{MONTHS[match.group(2).lower()]}-{match.group(1).zfill(2)}"
    match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(20\d{2})\b",
        context,
        re.I,
    )
    if match and 2005 <= int(match.group(3)) <= date.today().year:
        return f"{match.group(3)}-{MONTHS[match.group(1).lower()]}-{match.group(2).zfill(2)}"
    return None


def _parsed_claim(name: str, hours: int, context: str, dob: str | None = None) -> dict:
    return {
        "pdfName": name.strip(),
        "matchedChildId": None,
        "matchedChildName": None,
        "hours": hours,
        "careCategory": _care_category(context),
        "dateOfBirth": dob or _dob(context),
        "attendanceDays": None,
        "confidence": "none",
        "score": 0,
        "suggestManualReview": True,
        "reason": "No automatic database match was applied",
    }


def _name_variants(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = re.sub(r"[^a-zA-Z0-9,]+", " ", normalized).strip().lower()
    variants = {re.sub(r"\s+", " ", normalized.replace(",", " ")).strip()}
    if "," in normalized:
        last, given = (part.strip() for part in normalized.split(",", maxsplit=1))
        variants.add(re.sub(r"\s+", " ", f"{given} {last}").strip())
    for candidate in tuple(variants):
        parts = candidate.split()
        if len(parts) >= 2:
            variants.add(" ".join(sorted(parts)))
        if len(parts) > 2:
            variants.add(f"{parts[0]} {parts[-1]}")
    return {variant for variant in variants if variant}


def _match_claims(
    claims: list[dict], organization_id: UUID, session: SessionDependency
) -> list[dict]:
    child_table = tables["children"]
    family_table = tables["families"]
    rows = session.execute(
        select(
            child_table.c.id,
            child_table.c.first_name,
            child_table.c.middle_name,
            child_table.c.last_name,
            child_table.c.date_of_birth,
        )
        .select_from(child_table.join(family_table, child_table.c.family_id == family_table.c.id))
        .where(
            family_table.c.organization_id == organization_id,
            child_table.c.is_active.is_(True),
        )
    ).mappings()
    candidates = []
    for row in rows:
        full_name = " ".join(
            str(value).strip()
            for value in (row["first_name"], row["middle_name"], row["last_name"])
            if value
        )
        short_name = f"{row['first_name']} {row['last_name']}".strip()
        candidates.append(
            {
                "id": row["id"],
                "name": full_name,
                "variants": _name_variants(full_name) | _name_variants(short_name),
                "dob": row["date_of_birth"],
            }
        )

    for claim in claims:
        if claim.get("matchedChildId"):
            continue
        claim_variants = _name_variants(claim["pdfName"])
        claim_dob = date.fromisoformat(claim["dateOfBirth"]) if claim.get("dateOfBirth") else None
        ranked = []
        for candidate in candidates:
            score = max(
                difflib.SequenceMatcher(None, source, target).ratio()
                for source in claim_variants
                for target in candidate["variants"]
            )
            dob_match = bool(claim_dob and candidate["dob"] == claim_dob)
            ranked.append((score, dob_match, candidate))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not ranked:
            continue
        best_score, best_dob_match, best = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0
        exact = [item for item in ranked if item[0] == 1]
        if len(exact) > 1 and claim_dob:
            exact_dob = [item for item in exact if item[1]]
            if len(exact_dob) == 1:
                best_score, best_dob_match, best = exact_dob[0]
                exact = exact_dob
        safe_exact = best_score == 1 and len(exact) == 1
        safe_fuzzy = best_score >= 0.9 and best_score - runner_up >= 0.06
        safe_dob = best_dob_match and best_score >= 0.72 and best_score - runner_up >= 0.04
        if not (safe_exact or safe_fuzzy or safe_dob):
            claim["reason"] = "No unique high-confidence child match; manual review required"
            continue
        confidence = "exact" if safe_exact else "high"
        claim.update(
            {
                "matchedChildId": str(best["id"]),
                "matchedChildName": best["name"],
                "confidence": confidence,
                "score": round(
                    1.0 if safe_exact else min(1.0, best_score + (0.08 if best_dob_match else 0)), 4
                ),
                "suggestManualReview": False,
                "reason": (
                    "Exact normalized name match"
                    if safe_exact
                    else "High-confidence name match confirmed by date of birth"
                    if best_dob_match
                    else "Unique high-confidence normalized name match"
                ),
            }
        )
    return claims


def _parse_new_format(text: str) -> list[dict]:
    normalized = re.sub(r"\s+", " ", text.replace("\n", " "))
    pattern = re.compile(
        r"(\d{5,8})\s*([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)*?)(?=\s+(?:Daycare|Out-of-school|Direct\s+child))",
        re.I,
    )
    invalid = {
        "infants",
        "kindergarten",
        "total",
        "child",
        "school",
        "toddler",
        "preschool",
        "daycare",
        "children",
        "summary",
        "subsidized",
        "reporting",
        "affordability",
        "grant",
        "educator",
        "out",
    }
    matches = [
        match for match in pattern.finditer(normalized) if match.group(2).lower() not in invalid
    ]
    claims: list[dict] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else match.start() + 500
        context = normalized[match.start() : min(end, match.start() + 500)]
        if "direct child care" in context.lower():
            continue
        hours = 0
        hours_match = re.search(r"-\s*(\d{1,3})\s*\$", context)
        if hours_match:
            hours = int(hours_match.group(1))
        if not hours:
            hours_match = re.search(r"20\d{2}(\d{2,3})\$", context)
            if hours_match and 1 <= int(hours_match.group(1)) <= 200:
                hours = int(hours_match.group(1))
        if not hours:
            hours_match = re.search(r"(\d{1,3})\s*\$", context)
            if hours_match and 1 <= int(hours_match.group(1)) <= 200:
                hours = int(hours_match.group(1))
        claims.append(_parsed_claim(match.group(2), hours, context))
    return claims


def _parse_old_format(text: str) -> list[dict]:
    claims: list[dict] = []
    header_terms = (
        "child participation",
        "hours claimed",
        "monthly fee",
        "maximum subsidy",
        "attendance summary",
        "projected hours",
    )
    eligibility_terms = ("AFF GR", "NO AFF", "GRANT - NOT ELIGIBLE", ">=100HRS", "REG SCHOOL")
    concat = re.compile(
        r"(\d{4}-\d{2}-\d{2})\d{7,8}[\d.]+([A-Z][A-Z'\s-]+,\s*[A-Z][A-Z'\s-]+?)([1-9]\d{0,2}|0)(\d+\.\d{2})",
        re.I,
    )
    fallback = re.compile(
        r"([A-Z][A-Z'\s-]+,\s*[A-Z][A-Z'\s-]+?)([1-9]\d{0,2}|0)(\d+\.\d{2})", re.I
    )
    for line in (line.strip() for line in text.splitlines() if line.strip()):
        if any(term in line.lower() for term in header_terms) or any(
            term in line.upper() for term in eligibility_terms
        ):
            continue
        match = concat.search(line)
        if match:
            claims.append(_parsed_claim(match.group(2), int(match.group(3)), line, match.group(1)))
            continue
        match = fallback.search(line)
        if match and len(match.group(1).strip()) > 5:
            claims.append(_parsed_claim(match.group(1), int(match.group(2)), line))
    return claims


def _claim_row(row) -> dict:
    return {
        "id": row["id"],
        "childName": row["child_name"],
        "hoursClaimed": row["hours_claimed"],
        "careCategory": row["care_category"],
        "dateOfBirth": row["date_of_birth"],
        "claimMonth": row["claim_month"],
        "claimYear": row["claim_year"],
        "importBatchId": row["import_batch_id"],
        "sourceFilename": row["source_filename"],
        "matchedChildId": row["matched_child_id"],
        "matchConfidence": row["match_confidence"],
        "manuallyVerified": row["manually_verified"],
        "importedAt": row["imported_at"],
    }


@router.post("/parse")
def parse_pdf_claims(
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, str], Body()],
) -> dict:
    organization_id = _organization_id(current_user)
    try:
        pdf_bytes = base64.b64decode(payload.get("pdfBase64", ""), validate=True)
        reader = PdfReader(BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        new_format = any(
            marker in text
            for marker in (
                "CHILD CARE CLAIMS",
                "Submitted claim report",
                "Children participation",
                "Enrolment Category",
            )
        )
        claims = _parse_new_format(text) if new_format else _parse_old_format(text)
        if not claims:
            return {
                "success": False,
                "totalEntriesFound": 0,
                "matchedCount": 0,
                "unmatchedCount": 0,
                "reviewRequiredCount": 0,
                "claims": [],
                "errors": ["No claim entries found in PDF"],
            }
        claims = _match_claims(claims, organization_id, session)
        matched_count = sum(bool(claim.get("matchedChildId")) for claim in claims)
        review_count = sum(bool(claim.get("suggestManualReview")) for claim in claims)
        return {
            "success": True,
            "totalEntriesFound": len(claims),
            "matchedCount": matched_count,
            "unmatchedCount": len(claims) - matched_count,
            "reviewRequiredCount": review_count,
            "claims": claims,
            "errors": [],
        }
    except Exception as exc:  # PDF readers raise several format-specific exception classes.
        return {
            "success": False,
            "totalEntriesFound": 0,
            "matchedCount": 0,
            "unmatchedCount": 0,
            "reviewRequiredCount": 0,
            "claims": [],
            "errors": [f"Failed to parse PDF: {exc}"],
        }


@router.get("/batches")
def list_batches(current_user: CurrentUser, session: SessionDependency) -> list[dict]:
    imported = tables["imported_claims"]
    rows = session.execute(
        select(
            imported.c.import_batch_id,
            func.max(imported.c.claim_month).label("claim_month"),
            func.max(imported.c.claim_year).label("claim_year"),
            func.count().label("total_claims"),
            func.count(imported.c.matched_child_id).label("matched_count"),
            func.sum(imported.c.hours_claimed).label("total_hours"),
            func.max(imported.c.source_filename).label("source_filename"),
            func.max(imported.c.imported_at).label("imported_at"),
        )
        .where(imported.c.organization_id == _organization_id(current_user))
        .group_by(imported.c.import_batch_id)
        .order_by(func.max(imported.c.imported_at).desc())
    ).mappings()
    return [
        {
            "batchId": row["import_batch_id"],
            "claimMonth": row["claim_month"],
            "claimYear": row["claim_year"],
            "totalClaims": row["total_claims"],
            "matchedCount": row["matched_count"],
            "unmatchedCount": row["total_claims"] - row["matched_count"],
            "totalHours": row["total_hours"] or 0,
            "sourceFilename": row["source_filename"],
            "importedAt": row["imported_at"],
        }
        for row in rows
    ]


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, current_user: CurrentUser, session: SessionDependency) -> list[dict]:
    imported = tables["imported_claims"]
    rows = session.execute(
        select(imported)
        .where(
            imported.c.organization_id == _organization_id(current_user),
            imported.c.import_batch_id == batch_id,
        )
        .order_by(imported.c.child_name.asc())
    ).mappings()
    return [_claim_row(row) for row in rows]


@router.post("/batches", status_code=status.HTTP_201_CREATED)
def save_batch(
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
    payload: Annotated[dict[str, Any], Body()],
) -> dict:
    _ensure_writable(request)
    imported = tables["imported_claims"]
    batch_id = str(uuid4())
    claims = payload.get("claims") or []
    matched_claims = _match_claims(
        [
            {
                "pdfName": claim["childName"],
                "dateOfBirth": claim.get("dateOfBirth"),
                "matchedChildId": claim.get("matchedChildId"),
                "matchedChildName": None,
                "suggestManualReview": not bool(claim.get("matchedChildId")),
                "reason": "",
                "confidence": "none",
                "score": float(claim.get("matchConfidence") or 0),
            }
            for claim in claims
        ],
        _organization_id(current_user),
        session,
    )
    values = [
        {
            "organization_id": _organization_id(current_user),
            "child_name": claim["childName"],
            "hours_claimed": round(float(claim["hoursClaimed"])),
            "care_category": claim.get("careCategory"),
            "date_of_birth": date.fromisoformat(claim["dateOfBirth"])
            if claim.get("dateOfBirth")
            else None,
            "claim_month": int(payload["claimMonth"]),
            "claim_year": int(payload["claimYear"]),
            "import_batch_id": batch_id,
            "source_filename": payload.get("sourceFilename"),
            "matched_child_id": UUID(matched["matchedChildId"])
            if matched.get("matchedChildId")
            else None,
            "match_confidence": matched.get("score") or claim.get("matchConfidence"),
            "manually_verified": False,
        }
        for claim, matched in zip(claims, matched_claims, strict=True)
    ]
    if values:
        session.execute(insert(imported), values)
        session.commit()
    matched_count = sum(value["matched_child_id"] is not None for value in values)
    return {
        "success": True,
        "batchId": batch_id,
        "savedCount": len(values),
        "matchedCount": matched_count,
        "unmatchedCount": len(values) - matched_count,
        "errors": [],
    }


@router.post("/batches/{batch_id}/rematch")
def rematch_batch(
    batch_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> dict[str, int | str | bool]:
    _ensure_writable(request)
    imported = tables["imported_claims"]
    organization_id = _organization_id(current_user)
    rows = list(
        session.execute(
            select(imported).where(
                imported.c.organization_id == organization_id,
                imported.c.import_batch_id == batch_id,
            )
        ).mappings()
    )
    claims = _match_claims(
        [
            {
                "pdfName": row["child_name"],
                "dateOfBirth": row["date_of_birth"].isoformat() if row["date_of_birth"] else None,
                "matchedChildId": str(row["matched_child_id"]) if row["matched_child_id"] else None,
                "matchedChildName": None,
                "suggestManualReview": row["matched_child_id"] is None,
                "reason": "",
                "confidence": "none",
                "score": float(row["match_confidence"] or 0),
            }
            for row in rows
        ],
        organization_id,
        session,
    )
    updated_count = 0
    for row, claim in zip(rows, claims, strict=True):
        if row["matched_child_id"] or not claim.get("matchedChildId"):
            continue
        session.execute(
            update(imported)
            .where(
                imported.c.id == row["id"],
                imported.c.organization_id == organization_id,
            )
            .values(
                matched_child_id=UUID(claim["matchedChildId"]),
                match_confidence=claim["score"],
            )
        )
        updated_count += 1
    session.commit()
    matched_count = sum(
        bool(row["matched_child_id"] or claim.get("matchedChildId"))
        for row, claim in zip(rows, claims, strict=True)
    )
    return {
        "success": True,
        "batchId": batch_id,
        "totalCount": len(rows),
        "matchedCount": matched_count,
        "unmatchedCount": len(rows) - matched_count,
        "updatedCount": updated_count,
    }


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(
    batch_id: str,
    request: Request,
    current_user: CurrentUser,
    session: SessionDependency,
) -> None:
    _ensure_writable(request)
    imported = tables["imported_claims"]
    session.execute(
        delete(imported).where(
            imported.c.organization_id == _organization_id(current_user),
            imported.c.import_batch_id == batch_id,
        )
    )
    session.commit()
