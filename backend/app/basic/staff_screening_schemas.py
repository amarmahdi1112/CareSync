"""Strict 0030 candidate screening and structured-duty contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.basic.schemas import (
    StaffPathway,
    _normalize_licence_class,
    _normalize_licence_jurisdiction,
)

ScreeningCoverage = Literal["criminal_record_check", "vulnerable_sector_search"]
VehicleAccess = Literal["none", "organization_vehicle_only", "personal_vehicle", "either"]


class DriverDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    willing_to_drive: bool = False
    licence_jurisdiction: str | None = Field(default=None, max_length=20)
    licence_jurisdiction_other: str | None = Field(default=None, max_length=100)
    licence_class: str | None = Field(default=None, max_length=30)
    vehicle_access: VehicleAccess = "none"
    preferred_service_radius_km: int | None = Field(default=None, ge=0, le=1000)
    candidate_provided: Literal[True] = True

    @field_validator("licence_jurisdiction")
    @classmethod
    def normalize_jurisdiction(cls, value: str | None) -> str | None:
        return _normalize_licence_jurisdiction(value)

    @field_validator("licence_class")
    @classmethod
    def normalize_class(cls, value: str | None) -> str | None:
        return _normalize_licence_class(value)

    @model_validator(mode="after")
    def validate_jurisdiction(self) -> DriverDeclaration:
        if self.licence_jurisdiction_other is not None:
            self.licence_jurisdiction_other = self.licence_jurisdiction_other.strip() or None
        if self.licence_jurisdiction == "OTHER":
            if not self.licence_jurisdiction_other:
                raise ValueError("OTHER licence jurisdiction requires a description")
        elif self.licence_jurisdiction_other is not None:
            raise ValueError("licence jurisdiction description is only valid for OTHER")
        return self

    def is_empty(self) -> bool:
        return (
            self.licence_jurisdiction is None
            and self.licence_jurisdiction_other is None
            and self.licence_class is None
            and self.vehicle_access == "none"
            and self.preferred_service_radius_km is None
        )

    def is_complete(self) -> bool:
        return bool(
            self.willing_to_drive
            and self.licence_jurisdiction
            and self.licence_class
            and self.vehicle_access != "none"
        )


class ScreeningProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pathway: StaffPathway
    driver_declaration: DriverDeclaration = Field(default_factory=DriverDeclaration)
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_pathway(self) -> ScreeningProfileUpdate:
        driver_pathway = self.pathway in {"driver", "educator_driver"}
        declaration = self.driver_declaration
        if driver_pathway:
            if not declaration.willing_to_drive:
                raise ValueError("driver pathways require willingness to drive")
            if not declaration.is_empty() and not declaration.is_complete():
                raise ValueError("driver declaration must be empty or complete")
        elif declaration.willing_to_drive or not declaration.is_empty():
            raise ValueError("non-driver pathways cannot contain a driver declaration")
        return self


class ScreeningProfileResponse(BaseModel):
    user_id: UUID
    pathway: StaffPathway
    driver_declaration: DriverDeclaration
    screening_profile_complete: bool
    operational_driver_ready: Literal[False] = False
    version: int
    created_at: datetime
    updated_at: datetime


class ScreeningDocumentVersionResponse(BaseModel):
    id: UUID
    version_number: int
    declared_coverage: list[ScreeningCoverage]
    original_filename: str | None
    media_type: Literal["application/pdf", "image/png", "image/jpeg"]
    size_bytes: int
    sha256: str
    subject_name: str | None
    account_name_snapshot: str | None
    subject_name_match: bool | None
    mismatch_resolution: Literal["matched", "candidate_attests_same_person"] | None
    issue_date: date | None
    expiry_date: date | None
    candidate_confirmed_at: datetime | None
    evidence_valid: bool
    validity_as_of: date
    created_at: datetime
    content_url: str


class ScreeningDocumentResponse(BaseModel):
    id: UUID
    status: Literal[
        "uploaded",
        "analysis_pending",
        "candidate_review",
        "confirmed",
        "expired",
        "superseded",
        "withdrawn",
    ]
    current_version_number: int
    declared_coverage: list[ScreeningCoverage]
    current_version: ScreeningDocumentVersionResponse
    versions: list[ScreeningDocumentVersionResponse]
    created_at: datetime
    updated_at: datetime


class ScreeningDocumentConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    subject_name: str = Field(min_length=1, max_length=200)
    issue_date: date | None = None
    expiry_date: date | None = None
    mismatch_resolution: Literal["candidate_attests_same_person"] | None = None

    @model_validator(mode="after")
    def validate_confirmation(self) -> ScreeningDocumentConfirm:
        self.subject_name = " ".join(self.subject_name.split())
        if (
            self.expiry_date is not None
            and self.issue_date is not None
            and self.expiry_date < self.issue_date
        ):
            raise ValueError("expiry_date cannot precede issue_date")
        return self


class ScreeningShareUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_version_ids: list[UUID] = Field(max_length=20)
    screening_profile_version: int = Field(ge=1)
    acknowledge_profile_snapshot: Literal[True]

    @field_validator("document_version_ids")
    @classmethod
    def unique_versions(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("document_version_ids cannot contain duplicates")
        return value


class EmployerScreeningReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_class: ScreeningCoverage
    decision: Literal["accepted", "rejected"]
    reason_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    note: str | None = Field(default=None, max_length=2000)


class EmployerScreeningReviewResponse(BaseModel):
    id: UUID
    requirement_class: ScreeningCoverage
    decision: Literal["accepted", "rejected"]
    reason_code: str
    note: str | None
    reviewer_user_id: UUID
    review_sequence: int
    reviewed_at: datetime
