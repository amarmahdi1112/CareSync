"""Canonical structured-duty values and exact offer digest helpers for 0030."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

STRUCTURED_TERM_FIELDS = (
    "position_shape",
    "driving_requirement",
    "vehicle_expectation",
    "required_licence_jurisdiction",
    "required_licence_jurisdiction_other",
    "required_licence_class",
    "minimum_driving_experience_months",
    "service_area",
    "service_windows",
    "mileage_policy",
    "driving_time_paid",
    "screening_conditions",
)


def default_structured_terms() -> dict[str, Any]:
    return {
        "position_shape": "educator_only",
        "driving_requirement": "not_applicable",
        "vehicle_expectation": "none",
        "required_licence_jurisdiction": None,
        "required_licence_jurisdiction_other": None,
        "required_licence_class": None,
        "minimum_driving_experience_months": 0,
        "service_area": None,
        "service_windows": [],
        "mileage_policy": None,
        "driving_time_paid": False,
        "screening_conditions": [],
    }


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return normalized.isoformat().replace("+00:00", "Z")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def structured_terms_from_model(value: Any) -> dict[str, Any]:
    if value is None:
        return default_structured_terms()
    result = {}
    for field in STRUCTURED_TERM_FIELDS:
        item = getattr(value, field, default_structured_terms()[field])
        result[field] = json_value(item)
    return result


def structured_terms_from_payload(value: Any) -> dict[str, Any]:
    dumped = value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)
    defaults = default_structured_terms()
    return {
        field: json_value(dumped.get(field, defaults[field]))
        for field in STRUCTURED_TERM_FIELDS
    }


def offer_terms_digest(
    offer: Any, structured_terms: dict[str, Any], *, candidate_id: Any
) -> str:
    payload = {
        "schema": "caresync-offer-terms-v1",
        "organization_id": str(offer.organization_id),
        "application_id": str(offer.application_id),
        "candidate_id": str(candidate_id),
        "offer_id": str(offer.id),
        "offer_version": int(offer.version),
        "position_title": offer.position_title,
        "start_date": json_value(offer.start_date),
        "compensation": offer.compensation,
        "hourly_rate": json_value(offer.hourly_rate),
        "notes": offer.notes,
        "terms": offer.terms,
        "expires_at": json_value(offer.expires_at),
        "structured_terms": json_value(structured_terms),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def driver_declaration_snapshot(profile: Any) -> dict[str, Any]:
    return {
        "willing_to_drive": bool(profile.willing_to_drive),
        "licence_jurisdiction": profile.licence_jurisdiction,
        "licence_jurisdiction_other": profile.licence_jurisdiction_other,
        "licence_class": profile.licence_class,
        "vehicle_access": profile.vehicle_access,
        "preferred_service_radius_km": profile.preferred_service_radius_km,
        "candidate_provided": True,
        "operational_driver_ready": False,
    }


def screening_profile_complete(profile: Any) -> bool:
    if profile.pathway not in {"driver", "educator_driver"}:
        return True
    return bool(
        profile.willing_to_drive
        and profile.licence_jurisdiction
        and profile.licence_class
        and profile.vehicle_access != "none"
    )


def structured_terms_match_application_snapshot(
    *,
    pathway: str,
    driver_declaration: dict[str, Any],
    structured_terms: dict[str, Any],
) -> bool:
    """Return whether offer duties remain inside the candidate's disclosed pathway.

    This is deliberately a compatibility check, not an operational driving
    authorization.  The declaration is candidate-provided application evidence;
    licence/insurance/vehicle verification belongs to a later transport boundary.
    """

    position_shape = structured_terms.get("position_shape")
    compatible_pathways = {
        "educator_only": {"educator", "student_educator", "educator_driver"},
        "driver_only": {"driver", "educator_driver"},
        "educator_driver": {"educator_driver"},
    }
    if pathway not in compatible_pathways.get(position_shape, set()):
        return False
    if position_shape == "educator_only":
        return True
    if not driver_declaration.get("willing_to_drive"):
        return False
    if driver_declaration.get("operational_driver_ready") is not False:
        return False
    if (
        driver_declaration.get("licence_jurisdiction")
        != structured_terms.get("required_licence_jurisdiction")
        or driver_declaration.get("licence_class")
        != structured_terms.get("required_licence_class")
    ):
        return False
    if structured_terms.get("required_licence_jurisdiction") == "OTHER" and (
        driver_declaration.get("licence_jurisdiction_other")
        != structured_terms.get("required_licence_jurisdiction_other")
    ):
        return False
    if structured_terms.get("vehicle_expectation") == "personal_vehicle":
        return driver_declaration.get("vehicle_access") in {"personal_vehicle", "either"}
    return driver_declaration.get("vehicle_access") != "none"
