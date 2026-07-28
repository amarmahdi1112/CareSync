"""Strict read-only contracts for the fail-closed 0031 transport registry."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class DriverVehicleRegistryCapability(BaseModel):
    schema_version: Literal["0031", "0032"] | None
    runtime_available: bool
    self_service_available: bool
    read_path: Literal["/api/v1/staff/self/transport-registry"] | None
    declaration_path: Literal[
        "/api/v1/staff/self/transport-registry/declarations"
    ] | None = None
    qualification_evidence_path: Literal[
        "/api/v1/staff/self/transport-registry/qualification-evidence"
    ] | None = None
    personal_vehicle_path: Literal[
        "/api/v1/staff/self/transport-registry/vehicles"
    ] | None = None
    vehicle_version_path_template: Literal[
        "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/versions"
    ] | None = None
    vehicle_retirement_path_template: Literal[
        "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/retire"
    ] | None = None
    vehicle_evidence_path_template: Literal[
        "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/evidence"
    ] | None = None
    evidence_upload_available: bool = False
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False


class DriverCapabilityProjection(BaseModel):
    id: UUID
    version_number: int
    status: Literal["declared", "withdrawn"]
    willing_to_drive: bool
    licence_jurisdiction: str | None
    licence_jurisdiction_other: str | None
    licence_class: str | None
    vehicle_access: Literal["none", "organization_vehicle_only", "personal_vehicle", "either"]
    preferred_service_radius_km: int | None
    source_kind: Literal["screening_profile", "staff_self", "manager_recorded", "offer_acceptance"]
    source_screening_profile_version: int | None
    effective_at: datetime
    recorded_at: datetime


class DriverQualificationProjection(BaseModel):
    id: UUID
    qualification_type: Literal[
        "driver_licence",
        "driver_abstract",
        "police_check",
        "vulnerable_sector_search",
        "first_aid",
        "vehicle_insurance_permission",
    ]
    version_number: int
    status: Literal["declared", "verified", "rejected", "expired", "revoked"]
    jurisdiction: str | None
    qualification_class: str | None
    identifier_last4: str | None
    issue_date: date | None
    expiry_date: date | None
    evidence_present: bool
    content_path: str | None
    effective_at: datetime
    recorded_at: datetime


class DriverAuthorizationProjection(BaseModel):
    id: UUID
    decision_sequence: int
    capability_version_id: UUID
    qualification_version_ids: list[UUID]
    decision: Literal["needs_review", "authorized", "denied", "revoked"]
    reason_code: str
    authorization_valid_from: datetime | None
    authorization_valid_until: datetime | None
    reviewed_at: datetime
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False


class VehicleVersionProjection(BaseModel):
    id: UUID
    version_number: int
    make: str
    model: str
    model_year: int
    color: str | None
    plate_token: str
    plate_jurisdiction: str
    passenger_capacity: int
    child_passenger_capacity: int
    wheelchair_accessible: bool
    effective_at: datetime
    recorded_at: datetime


class VehicleEvidenceProjection(BaseModel):
    id: UUID
    evidence_type: Literal["registration", "insurance", "inspection", "maintenance"]
    version_number: int
    status: Literal["provided", "verified", "rejected", "expired", "revoked"]
    issue_date: date | None
    expiry_date: date | None
    original_filename: str | None
    media_type: Literal["application/pdf", "image/png", "image/jpeg"]
    byte_size: int
    content_path: str | None
    recorded_at: datetime


class StaffPersonalVehicleProjection(BaseModel):
    id: UUID
    owner_kind: Literal["staff_personal"] = "staff_personal"
    retired_at: datetime | None
    current_version: VehicleVersionProjection | None
    evidence: list[VehicleEvidenceProjection]


class DriverReadinessProjection(BaseModel):
    id: UUID
    decision_sequence: int
    capability_version_id: UUID
    authorization_decision_id: UUID
    vehicle_id: UUID | None
    vehicle_version_id: UUID | None
    vehicle_evidence_version_ids: list[UUID]
    decision: Literal["incomplete", "needs_review", "blocked"]
    reason_codes: list[str]
    evaluated_at: datetime
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False


class SelfTransportRegistryResponse(BaseModel):
    schema_version: Literal["0031", "0032"] = "0031"
    organization_id: UUID
    membership_id: UUID
    user_id: UUID
    generated_at: datetime
    driver_capability: DriverCapabilityProjection | None
    qualifications: list[DriverQualificationProjection]
    authorizations: list[DriverAuthorizationProjection]
    authorizations_truncated: bool
    vehicles: list[StaffPersonalVehicleProjection]
    vehicles_truncated: bool
    latest_readiness_decision: DriverReadinessProjection | None
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False
