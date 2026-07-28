"""Strict 0032 transport-registry command and receipt contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

OperationId = Annotated[UUID, Field(description="Client-generated exact-retry operation id")]
ShortText = Annotated[str, Field(min_length=1, max_length=80)]


class StrictCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation_id: OperationId


class TransportCommandReceiptResponse(BaseModel):
    schema_version: Literal["0032"] = "0032"
    client_operation_id: UUID
    command_kind: Literal[
        "driver_declaration",
        "qualification_evidence",
        "qualification_review",
        "driver_authorization",
        "vehicle_create",
        "vehicle_version",
        "vehicle_retire",
        "vehicle_evidence",
        "vehicle_evidence_review",
        "readiness_evaluation",
    ]
    result_kind: Literal[
        "driver_capability",
        "driver_qualification",
        "driver_authorization",
        "vehicle",
        "vehicle_version",
        "vehicle_evidence",
        "driver_readiness",
    ]
    result_id: UUID
    committed_at: datetime
    exact_retry: bool
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False


class TransportRegistryCommandCapability(BaseModel):
    schema_version: Literal["0032"] = "0032"
    runtime_available: Literal[True] = True
    manager_available: Literal[True] = True
    workspace_path: Literal["/api/v1/staff/transport-registry"] = (
        "/api/v1/staff/transport-registry"
    )
    evidence_upload_available: bool
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False


class DriverDeclarationCommand(StrictCommand):
    status: Literal["declared", "withdrawn"]
    willing_to_drive: bool
    licence_jurisdiction: str | None = Field(default=None, min_length=2, max_length=20)
    licence_jurisdiction_other: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    licence_class: str | None = Field(default=None, min_length=1, max_length=30)
    vehicle_access: Literal[
        "none", "organization_vehicle_only", "personal_vehicle", "either"
    ]
    preferred_service_radius_km: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def declaration_shape(self):
        if self.status == "withdrawn":
            if (
                self.willing_to_drive
                or self.licence_jurisdiction is not None
                or self.licence_jurisdiction_other is not None
                or self.licence_class is not None
                or self.vehicle_access != "none"
                or self.preferred_service_radius_km is not None
            ):
                raise ValueError("A withdrawn declaration cannot retain driving details")
            return self
        if (
            not self.willing_to_drive
            or self.licence_jurisdiction is None
            or self.licence_class is None
            or self.vehicle_access == "none"
        ):
            raise ValueError("A declared driver requires licence and vehicle-access details")
        if (self.licence_jurisdiction == "OTHER") != (
            self.licence_jurisdiction_other is not None
        ):
            raise ValueError("OTHER jurisdiction requires its explicit jurisdiction name")
        return self


QualificationType = Literal[
    "driver_licence",
    "driver_abstract",
    "police_check",
    "vulnerable_sector_search",
    "first_aid",
    "vehicle_insurance_permission",
]


class QualificationEvidenceFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation_id: OperationId
    qualification_type: QualificationType
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=20)
    qualification_class: str | None = Field(default=None, min_length=1, max_length=40)
    identifier_last4: str | None = Field(default=None, min_length=2, max_length=8)
    issue_date: date | None = None
    expiry_date: date | None = None

    @model_validator(mode="after")
    def qualification_shape(self):
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            raise ValueError("expiry_date cannot precede issue_date")
        if self.qualification_type == "driver_licence" and (
            self.jurisdiction is None
            or self.qualification_class is None
            or self.expiry_date is None
        ):
            raise ValueError("Driver licence evidence requires jurisdiction, class, and expiry")
        return self


class QualificationReviewCommand(StrictCommand):
    source_qualification_version_id: UUID
    decision: Literal["verified", "rejected"]
    reason_code: ShortText


class DriverAuthorizationCommand(StrictCommand):
    capability_version_id: UUID
    qualification_version_ids: Annotated[list[UUID], Field(min_length=1, max_length=20)]
    decision: Literal["needs_review", "authorized", "denied", "revoked"]
    reason_code: ShortText
    authorization_valid_from: datetime | None = None
    authorization_valid_until: datetime | None = None

    @model_validator(mode="after")
    def authorization_shape(self):
        if len(set(self.qualification_version_ids)) != len(self.qualification_version_ids):
            raise ValueError("qualification_version_ids must be unique")
        if self.decision == "authorized":
            if self.authorization_valid_from is None or self.authorization_valid_until is None:
                raise ValueError("An authorized decision requires a finite validity window")
            if (
                self.authorization_valid_from.tzinfo is None
                or self.authorization_valid_from.utcoffset() is None
                or self.authorization_valid_until.tzinfo is None
                or self.authorization_valid_until.utcoffset() is None
            ):
                raise ValueError("Authorization validity timestamps require a timezone")
            if self.authorization_valid_until <= self.authorization_valid_from:
                raise ValueError("authorization_valid_until must follow its start")
        elif (
            self.authorization_valid_from is not None
            or self.authorization_valid_until is not None
        ):
            raise ValueError("Only authorized decisions may include a validity window")
        return self


class VehicleFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    make: Annotated[str, Field(min_length=1, max_length=80)]
    model: Annotated[str, Field(min_length=1, max_length=80)]
    model_year: int = Field(ge=1900, le=2100)
    color: str | None = Field(default=None, min_length=1, max_length=40)
    plate_token: Annotated[str, Field(min_length=2, max_length=24)]
    plate_jurisdiction: Annotated[str, Field(min_length=2, max_length=20)]
    passenger_capacity: int = Field(ge=1, le=30)
    child_passenger_capacity: int = Field(ge=0, le=29)
    wheelchair_accessible: bool = False

    @model_validator(mode="after")
    def capacity_shape(self):
        if self.child_passenger_capacity >= self.passenger_capacity:
            raise ValueError("Child capacity must be lower than total passenger capacity")
        return self


class PersonalVehicleCreateCommand(StrictCommand, VehicleFacts):
    pass


class OrganizationVehicleCreateCommand(StrictCommand, VehicleFacts):
    pass


class VehicleVersionCommand(StrictCommand, VehicleFacts):
    pass


class VehicleRetireCommand(StrictCommand):
    reason_code: ShortText


VehicleEvidenceType = Literal["registration", "insurance", "inspection", "maintenance"]


class VehicleEvidenceFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation_id: OperationId
    evidence_type: VehicleEvidenceType
    issue_date: date | None = None
    expiry_date: date | None = None

    @model_validator(mode="after")
    def evidence_shape(self):
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            raise ValueError("expiry_date cannot precede issue_date")
        if self.evidence_type in {"registration", "insurance", "inspection"} and (
            self.expiry_date is None
        ):
            raise ValueError("This evidence type requires an expiry date")
        return self


class VehicleEvidenceReviewCommand(StrictCommand):
    source_evidence_version_id: UUID
    decision: Literal["verified", "rejected"]
    reason_code: ShortText


class ReadinessEvaluationCommand(StrictCommand):
    vehicle_id: UUID | None = None


class WorkspaceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceCapabilityVersion(WorkspaceProjection):
    id: UUID
    version_number: int
    status: Literal["declared", "withdrawn"]
    willing_to_drive: bool
    licence_jurisdiction: str | None
    licence_class: str | None
    vehicle_access: Literal[
        "none", "organization_vehicle_only", "personal_vehicle", "either"
    ]
    preferred_service_radius_km: int | None
    effective_at: datetime


class WorkspaceQualificationVersion(WorkspaceProjection):
    id: UUID
    qualification_type: QualificationType
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


class WorkspaceQualificationReview(WorkspaceProjection):
    id: UUID
    source_qualification_version_id: UUID
    result_qualification_version_id: UUID
    decision: Literal["verified", "rejected"]
    reason_code: str
    reviewed_at: datetime


class WorkspaceAuthorization(WorkspaceProjection):
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


class WorkspaceReadiness(WorkspaceProjection):
    id: UUID
    decision_sequence: int
    decision: Literal["incomplete", "needs_review", "blocked"]
    reason_codes: list[str]
    vehicle_id: UUID | None
    evaluated_at: datetime
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False


class WorkspaceStaffRecord(WorkspaceProjection):
    membership_id: UUID
    first_name: str
    last_name: str
    capabilities: list[WorkspaceCapabilityVersion]
    qualifications: list[WorkspaceQualificationVersion]
    qualification_reviews: list[WorkspaceQualificationReview]
    authorizations: list[WorkspaceAuthorization]
    readiness: list[WorkspaceReadiness]
    capabilities_truncated: bool
    qualification_types_truncated: list[QualificationType]
    qualification_reviews_truncated: bool
    authorizations_truncated: bool
    readiness_truncated: bool


class WorkspaceVehicleVersion(WorkspaceProjection):
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


class WorkspaceVehicleEvidence(WorkspaceProjection):
    id: UUID
    vehicle_version_id: UUID
    evidence_type: VehicleEvidenceType
    version_number: int
    status: Literal["provided", "verified", "rejected", "expired", "revoked"]
    issue_date: date | None
    expiry_date: date | None
    original_filename: str | None
    media_type: Literal["application/pdf", "image/png", "image/jpeg"]
    byte_size: int
    content_path: str
    recorded_at: datetime


class WorkspaceVehicleEvidenceReview(WorkspaceProjection):
    id: UUID
    source_evidence_version_id: UUID
    result_evidence_version_id: UUID
    decision: Literal["verified", "rejected"]
    reason_code: str
    reviewed_at: datetime


class WorkspaceVehicleRecord(WorkspaceProjection):
    id: UUID
    owner_kind: Literal["organization", "staff_personal"]
    staff_owner_membership_id: UUID | None
    retired_at: datetime | None
    versions: list[WorkspaceVehicleVersion]
    evidence: list[WorkspaceVehicleEvidence]
    evidence_reviews: list[WorkspaceVehicleEvidenceReview]
    versions_truncated: bool
    evidence_types_truncated: list[VehicleEvidenceType]
    evidence_reviews_truncated: bool


class TransportRegistryWorkspaceResponse(WorkspaceProjection):
    schema_version: Literal["0032"] = "0032"
    generated_at: datetime
    staff: list[WorkspaceStaffRecord]
    vehicles: list[WorkspaceVehicleRecord]
    staff_truncated: bool
    vehicles_truncated: bool
    operational_driver_ready: Literal[False] = False
    dispatch_authorized: Literal[False] = False
