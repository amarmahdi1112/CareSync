"""Typed HTTP contracts for the CareSync Basic release boundary."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.basic.programs import ProgramType


class FromOrm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PermissionRoleResponse(FromOrm):
    id: UUID
    key: str
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class UserResponse(FromOrm):
    id: UUID
    email: str
    first_name: str
    last_name: str
    role: PermissionRoleResponse
    organization_id: UUID
    membership_id: UUID
    membership_status: str
    assigned_facility_ids: list[UUID] = Field(default_factory=list)
    assigned_room_ids: list[UUID] = Field(default_factory=list)
    is_active: bool
    email_verification_status: Literal["pending", "verified"]
    email_verified_at: datetime | None
    email_verification_method: str | None
    profile_complete: bool | None = None
    missing_profile_fields: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=10, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    organization_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: str
    password: str
    organization_id: UUID | None = None


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class OrganizationResponse(FromOrm):
    id: UUID
    name: str
    legal_name: str | None
    status: str
    verification_status: Literal["pending", "under_review", "verified", "rejected"]
    verified_at: datetime | None
    verification_method: str | None
    email: str | None
    phone: str | None
    timezone: str
    preferences: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class OrganizationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)


class FacilityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    license_number: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    street_address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    province: str = Field(default="Alberta", min_length=1, max_length=50)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str = Field(default="America/Edmonton", min_length=1, max_length=100)
    licensed_capacity: int = Field(default=0, ge=0)
    opening_time: time | None = None
    closing_time: time | None = None
    status: str = "draft"
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    shift_clock_radius_meters: int = Field(default=150, ge=25, le=5000)

    @model_validator(mode="after")
    def validate_hours(self) -> FacilityCreate:
        if self.opening_time and self.closing_time and self.closing_time <= self.opening_time:
            raise ValueError("closing_time must be after opening_time")
        if self.status not in {"draft", "active", "inactive"}:
            raise ValueError("invalid facility status")
        return self


class FacilityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    license_number: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    street_address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, min_length=1, max_length=50)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    licensed_capacity: int | None = Field(default=None, ge=0)
    opening_time: time | None = None
    closing_time: time | None = None
    status: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    shift_clock_radius_meters: int | None = Field(default=None, ge=25, le=5000)
    deactivation_confirmation: str | None = Field(default=None, max_length=255)
    deactivation_reason: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in {"draft", "active", "inactive"}:
            raise ValueError("invalid facility status")
        return value


class FacilityResponse(FromOrm):
    id: UUID
    organization_id: UUID
    name: str
    license_number: str | None
    status: str
    verification_status: Literal["pending", "under_review", "verified", "rejected"]
    verified_at: datetime | None
    verification_method: str | None
    email: str | None
    phone: str | None
    street_address: str | None
    city: str | None
    province: str
    postal_code: str | None
    timezone: str
    licensed_capacity: int
    opening_time: time | None
    closing_time: time | None
    latitude: float | None
    longitude: float | None
    shift_clock_radius_meters: int
    created_at: datetime
    updated_at: datetime


class DeactivationImpactResponse(BaseModel):
    organization_id: UUID
    entity_type: Literal["facility", "room"]
    entity_id: UUID
    entity_name: str
    active_programs: int = 0
    active_rooms: int = 0
    open_enrollments: int = 0
    open_attendance_intervals: int = 0
    active_staff_assignments: int = 0
    open_staff_shifts: int = 0
    open_staff_room_presences: int = 0
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    can_deactivate: bool
    confirmation_text: str


class ProgramCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facility_id: UUID
    name: str = Field(min_length=1, max_length=150)
    program_type: ProgramType
    capacity: int = Field(default=0, ge=0)
    minimum_age_months: int | None = Field(default=None, ge=0)
    maximum_age_months: int | None = Field(default=None, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_ages(self) -> ProgramCreate:
        if (
            self.minimum_age_months is not None
            and self.maximum_age_months is not None
            and self.maximum_age_months < self.minimum_age_months
        ):
            raise ValueError("maximum age must be greater than or equal to minimum age")
        return self


class ProgramPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=150)
    program_type: ProgramType | None = None
    capacity: int | None = Field(default=None, ge=0)
    minimum_age_months: int | None = Field(default=None, ge=0)
    maximum_age_months: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("program_type")
    @classmethod
    def program_type_cannot_be_null(cls, value: ProgramType | None) -> ProgramType:
        if value is None:
            raise ValueError("program_type cannot be null")
        return value

    @field_validator("name", "capacity", "is_active")
    @classmethod
    def required_values_cannot_be_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class ProgramResponse(FromOrm):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    name: str
    program_type: ProgramType
    capacity: int
    minimum_age_months: int | None
    maximum_age_months: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RoomCreate(BaseModel):
    facility_id: UUID
    program_id: UUID
    name: str = Field(min_length=1, max_length=150)
    capacity: int = Field(gt=0)
    age_group: str | None = Field(default=None, max_length=100)
    minimum_age_months: int | None = Field(default=None, ge=0)
    maximum_age_months: int | None = Field(default=None, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_age_range(self) -> RoomCreate:
        if (self.minimum_age_months is None) != (self.maximum_age_months is None):
            raise ValueError("minimum and maximum room ages must both be set or both be blank")
        if (
            self.minimum_age_months is not None
            and self.maximum_age_months is not None
            and self.maximum_age_months < self.minimum_age_months
        ):
            raise ValueError("maximum room age must be greater than or equal to minimum age")
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("room name cannot be blank")
        return normalized


class RoomPatch(BaseModel):
    program_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    capacity: int | None = Field(default=None, gt=0)
    age_group: str | None = Field(default=None, max_length=100)
    minimum_age_months: int | None = Field(default=None, ge=0)
    maximum_age_months: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    deactivation_confirmation: str | None = Field(default=None, max_length=255)
    deactivation_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_age_range_update(self) -> RoomPatch:
        minimum_present = "minimum_age_months" in self.model_fields_set
        maximum_present = "maximum_age_months" in self.model_fields_set
        if minimum_present != maximum_present:
            raise ValueError("minimum and maximum room ages must be updated together")
        if minimum_present and (self.minimum_age_months is None) != (
            self.maximum_age_months is None
        ):
            raise ValueError("minimum and maximum room ages must both be set or both be blank")
        if (
            self.minimum_age_months is not None
            and self.maximum_age_months is not None
            and self.maximum_age_months < self.minimum_age_months
        ):
            raise ValueError("maximum room age must be greater than or equal to minimum age")
        return self

    @field_validator("program_id")
    @classmethod
    def program_id_cannot_be_null(cls, value: UUID | None) -> UUID:
        if value is None:
            raise ValueError("program_id cannot be null")
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("room name cannot be null")
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("room name cannot be blank")
        return normalized

    @field_validator("capacity", "is_active")
    @classmethod
    def required_values_cannot_be_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class RoomResponse(FromOrm):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    program_id: UUID | None
    name: str
    capacity: int
    age_group: str | None
    minimum_age_months: int | None
    maximum_age_months: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OnboardingPatch(BaseModel):
    current_step: str | None = Field(default=None, max_length=50)
    completed_steps: list[str] | None = None
    draft: dict[str, Any] | None = None


class OnboardingResponse(BaseModel):
    organization_id: UUID
    status: str
    current_step: str
    completed_steps: list[str]
    draft: dict[str, Any]
    completed_at: datetime | None
    organization: OrganizationResponse
    facilities: list[FacilityResponse]


class ConsentInput(BaseModel):
    photo_consent: bool = False
    field_trip_consent: bool = False
    emergency_medical_consent: bool = False


class GuardianInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    relationship: str | None = Field(default=None, max_length=100)
    email: str = Field(default="", max_length=320)
    cell_phone: str = Field(default="", max_length=30)
    home_phone: str | None = Field(default=None, max_length=30)
    work_phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    authorized_pickup: bool = False


class EmergencyContactInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    relationship: str = Field(min_length=1, max_length=100)
    cell_phone: str = Field(min_length=1, max_length=30)
    home_phone: str | None = Field(default=None, max_length=30)
    authorized_pickup: bool = False


class FamilyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    name: str = Field(min_length=1, max_length=255)
    file_number: str | None = Field(default=None, max_length=80)
    status: str = "active"
    additional_notes: str | None = None
    consents: ConsentInput = Field(default_factory=ConsentInput)
    primary_guardian: GuardianInput | None = None
    secondary_guardian: GuardianInput | None = None
    emergency_contacts: list[EmergencyContactInput] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"pending", "active", "inactive", "archived"}:
            raise ValueError("invalid family status")
        return value


class FamilyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    file_number: str | None = Field(default=None, max_length=80)
    status: str | None = None
    additional_notes: str | None = None
    consents: ConsentInput | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in {"pending", "active", "inactive", "archived"}:
            raise ValueError("invalid family status")
        return value

    @model_validator(mode="after")
    def require_domain_change(self) -> FamilyPatch:
        domain_fields = self.model_fields_set - {"client_operation_id", "expected_version"}
        if not domain_fields:
            raise ValueError("at least one family field must be provided")
        for field_name in ("name", "status", "consents"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class GuardianResponse(FromOrm):
    id: UUID
    family_id: UUID
    first_name: str
    last_name: str
    relationship: str | None
    guardian_type: str
    email: str
    cell_phone: str
    home_phone: str | None
    work_phone: str | None
    address: str | None
    city: str | None
    postal_code: str | None
    is_primary: bool
    authorized_pickup: bool


class EmergencyContactResponse(FromOrm):
    id: UUID
    family_id: UUID
    first_name: str
    last_name: str
    relationship: str
    cell_phone: str
    home_phone: str | None
    authorized_pickup: bool


class FamilyDirectoryPrimaryContact(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    cell_phone: str


class FamilyDirectoryChildPreview(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    age_group: str | None


class FamilyDirectoryItem(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    file_number: str | None
    status: str
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    primary_contact: FamilyDirectoryPrimaryContact | None
    active_children: list[FamilyDirectoryChildPreview] = Field(default_factory=list)
    active_child_count: int = Field(ge=0)


class FamilyDirectoryPage(BaseModel):
    items: list[FamilyDirectoryItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=50)
    offset: int = Field(ge=0)


class FamilyOption(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    status: str


class FamilyOptionsPage(BaseModel):
    items: list[FamilyOption]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class FamilyBillingGuardian(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    guardian_type: Literal["primary"]
    email: str
    address: str | None
    city: str | None
    postal_code: str | None


class FamilyBillingOption(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    status: str
    guardians: list[FamilyBillingGuardian] = Field(default_factory=list, max_length=1)


class FamilyBillingOptionsPage(BaseModel):
    items: list[FamilyBillingOption]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class EnrollmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    facility_id: UUID
    start_date: date


class EnrollmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    end_date: date | None = None
    status: str | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is not None and value not in {"pending", "active", "paused", "ended"}:
            raise ValueError("invalid enrollment status")
        return value

    @model_validator(mode="after")
    def require_domain_change(self) -> EnrollmentPatch:
        domain_fields = self.model_fields_set - {"client_operation_id", "expected_version"}
        if not domain_fields:
            raise ValueError("at least one enrollment field must be provided")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class EnrollmentResponse(FromOrm):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    child_id: UUID
    program_id: UUID | None
    room_id: UUID | None
    placement_effective_date: date | None
    start_date: date
    end_date: date | None
    status: str
    version: int = Field(ge=1)
    replayed: bool = False
    is_active: bool
    facility_name: str | None = None
    program_name: str | None = None
    program_type: ProgramType | None = None
    room_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ChildcareCommandReceiptResponse(BaseModel):
    organization_id: UUID
    client_operation_id: UUID
    command_type: str
    target_type: Literal[
        "family",
        "child",
        "enrollment",
        "authority_person",
        "authority_evidence",
        "authority_evidence_object",
        "release_authorization",
        "release_rule",
        "consent",
        "attendance_release",
        "admission_application",
        "admission_waitlist",
        "admission_offer",
    ]
    target_id: UUID
    committed_version: int = Field(ge=1)
    committed_at: datetime
    facility_id: UUID | None
    action_route: str


ChildDirectoryPlacementState = Literal["current", "reserved", "unassigned", "needs_review"]
ChildDirectoryCareLane = Literal[
    "daycare",
    "out_of_school_care",
    "unassigned",
    "needs_review",
]


class ChildDirectoryOpenEnrollment(BaseModel):
    id: UUID
    organization_id: UUID
    child_id: UUID
    facility_id: UUID
    facility_name: str
    program_id: UUID | None
    program_name: str | None
    program_type: ProgramType | None
    room_id: UUID | None
    room_name: str | None
    placement_effective_date: date | None
    start_date: date
    end_date: date | None
    status: str
    version: int = Field(ge=1)
    placement_state: ChildDirectoryPlacementState


class ChildDirectoryItem(BaseModel):
    id: UUID
    organization_id: UUID
    family_id: UUID
    family_name: str
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date
    age_group: str | None
    is_active: bool
    version: int = Field(ge=1)
    profile_photo_url: str | None
    profile_photo_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    care_lane: ChildDirectoryCareLane
    open_enrollment: ChildDirectoryOpenEnrollment | None


class ChildDirectoryCounts(BaseModel):
    total: int = Field(ge=0)
    active: int = Field(ge=0)
    inactive: int = Field(ge=0)
    daycare: int = Field(ge=0)
    out_of_school_care: int = Field(ge=0)
    unassigned: int = Field(ge=0)
    reserved: int = Field(ge=0)
    needs_review: int = Field(ge=0)


class ChildDirectoryPage(BaseModel):
    items: list[ChildDirectoryItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    counts: ChildDirectoryCounts


class RoomRosterChildResponse(BaseModel):
    child_id: UUID
    enrollment_id: UUID
    family_id: UUID
    family_name: str
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date
    age_group: str | None
    child_is_active: bool
    profile_photo_url: str | None = None
    facility_id: UUID
    program_id: UUID | None
    room_id: UUID | None
    enrollment_status: str
    enrollment_version: int = Field(ge=1)
    start_date: date
    placement_effective_date: date | None
    end_date: date | None


class RoomRosterResponse(BaseModel):
    room_id: UUID
    facility_id: UUID
    program_id: UUID | None
    name: str
    capacity: int
    is_active: bool
    occupancy: int
    children: list[RoomRosterChildResponse] = Field(default_factory=list)
    reserved_children: list[RoomRosterChildResponse] = Field(default_factory=list)


class RoomRosterWorkspaceResponse(BaseModel):
    facility_id: UUID
    facility_date: date
    rooms: list[RoomRosterResponse] = Field(default_factory=list)
    unassigned_children: list[RoomRosterChildResponse] = Field(default_factory=list)


class RoomPlacementCandidateResponse(BaseModel):
    room_id: UUID
    room_name: str
    room_age_group: str | None
    minimum_age_months: int
    maximum_age_months: int
    capacity: int
    occupancy: int
    available_places: int
    program_id: UUID
    program_name: str
    program_type: ProgramType


class RoomPlacementReviewResponse(BaseModel):
    organization_id: UUID
    facility_id: UUID
    enrollment_id: UUID
    enrollment_version: int = Field(ge=1)
    child_id: UUID
    child_first_name: str
    child_middle_name: str | None
    child_last_name: str
    date_of_birth: date
    enrollment_start_date: date
    effective_date: date
    age_months: int
    suggestion_state: Literal["none", "one", "multiple"]
    candidates: list[RoomPlacementCandidateResponse] = Field(default_factory=list)


class RoomPlacementApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    room_id: UUID
    effective_date: date


class RoomPlacementBatchItem(RoomPlacementApprovalRequest):
    enrollment_id: UUID


class RoomPlacementBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    placements: list[RoomPlacementBatchItem] = Field(min_length=1, max_length=250)


class RoomPlacementApprovalResponse(BaseModel):
    organization_id: UUID
    facility_id: UUID
    enrollment_id: UUID
    child_id: UUID
    program_id: UUID
    room_id: UUID
    effective_date: date
    age_months: int
    approved_at: datetime
    version: int = Field(ge=1)
    replayed: bool = False


class RoomPlacementBatchResponse(BaseModel):
    approvals: list[EnrollmentResponse]


class ChildCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    family_id: UUID
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    gender: str | None = Field(default=None, max_length=30)
    age_group: str | None = Field(default=None, max_length=50)
    is_active: bool = True
    health_care_number: str | None = Field(default=None, max_length=100)
    allergies: str | None = None
    medical_conditions: str | None = None
    medications: str | None = None
    immunization_up_to_date: bool | None = None
    doctor_name: str | None = Field(default=None, max_length=255)
    doctor_phone: str | None = Field(default=None, max_length=30)


class ChildPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    family_id: UUID | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    age_group: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    health_care_number: str | None = Field(default=None, max_length=100)
    allergies: str | None = None
    medical_conditions: str | None = None
    medications: str | None = None
    immunization_up_to_date: bool | None = None
    doctor_name: str | None = Field(default=None, max_length=255)
    doctor_phone: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def require_domain_change(self) -> ChildPatch:
        domain_fields = self.model_fields_set - {"client_operation_id", "expected_version"}
        if not domain_fields:
            raise ValueError("at least one child field must be provided")
        for field_name in (
            "family_id",
            "first_name",
            "last_name",
            "date_of_birth",
            "is_active",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class ChildResponse(FromOrm):
    id: UUID
    organization_id: UUID
    family_id: UUID
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date
    gender: str | None
    age_group: str | None
    is_active: bool
    version: int = Field(ge=1)
    replayed: bool = False
    health_care_number: str | None
    allergies: str | None
    medical_conditions: str | None
    medications: str | None
    immunization_up_to_date: bool | None
    doctor_name: str | None
    doctor_phone: str | None
    profile_photo_url: str | None = None
    profile_photo_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    family_name: str | None = None
    enrollments: list[EnrollmentResponse] = Field(default_factory=list)


class ChildFamilyProfileResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    file_number: str | None
    status: str
    version: int = Field(ge=1)
    replayed: bool = False
    additional_notes: str | None
    photo_consent: bool
    field_trip_consent: bool
    emergency_medical_consent: bool
    guardians: list[GuardianResponse] = Field(default_factory=list)
    emergency_contacts: list[EmergencyContactResponse] = Field(default_factory=list)


class ChildProfileResponse(ChildResponse):
    family: ChildFamilyProfileResponse
    current_enrollment: EnrollmentResponse | None = None


class ChildProfilePhotoResponse(BaseModel):
    child_id: UUID
    url: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    original_filename: str | None
    updated_at: datetime


class FamilyResponse(FromOrm):
    id: UUID
    organization_id: UUID
    name: str
    file_number: str | None
    status: str
    version: int = Field(ge=1)
    replayed: bool = False
    additional_notes: str | None
    photo_consent: bool
    field_trip_consent: bool
    emergency_medical_consent: bool
    created_at: datetime
    updated_at: datetime
    guardians: list[GuardianResponse] = Field(default_factory=list)
    emergency_contacts: list[EmergencyContactResponse] = Field(default_factory=list)
    children: list[ChildResponse] = Field(default_factory=list)


class FamilyStatsResponse(BaseModel):
    families: int
    active_families: int
    children: int
    active_children: int
    pending_families: int
    by_age_group: dict[str, int]


class GuardianSectionReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    guardian: GuardianInput | None


class EmergencyContactsReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    emergency_contacts: list[EmergencyContactInput] = Field(max_length=50)


ChildRecordReadinessCode = Literal[
    "missing_primary_guardian",
    "unreachable_guardian_telephone",
    "missing_emergency_contact",
    "inactive_family_active_records",
    "open_unassigned_enrollment",
    "enrollment_placement_incoherent",
    "unknown_immunization_status",
    "duplicate_open_enrollment",
]
ChildRecordReadinessSeverity = Literal["critical", "warning", "info"]


class ChildRecordReadinessItem(BaseModel):
    key: str
    code: ChildRecordReadinessCode
    severity: ChildRecordReadinessSeverity
    family_id: UUID | None = None
    child_id: UUID | None = None
    enrollment_id: UUID | None = None
    facility_id: UUID | None = None
    title: str
    message: str
    action_route: str


class ChildRecordReadinessCounts(BaseModel):
    critical: int = 0
    warning: int = 0
    info: int = 0


class ChildRecordReadinessResponse(BaseModel):
    items: list[ChildRecordReadinessItem]
    total: int
    limit: int
    offset: int
    counts: ChildRecordReadinessCounts


class CheckInRequest(BaseModel):
    client_operation_id: UUID
    child_id: UUID
    facility_id: UUID
    occurred_at: datetime | None = None


class CheckOutRequest(CheckInRequest):
    pass


class AbsenceRequest(BaseModel):
    child_id: UUID
    facility_id: UUID
    date: date
    reason: str = Field(min_length=1, max_length=1000)


class CorrectionRequest(BaseModel):
    interval_id: UUID
    checked_in_at: datetime
    checked_out_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_order(self) -> CorrectionRequest:
        if self.checked_out_at is not None and self.checked_out_at < self.checked_in_at:
            raise ValueError("checked_out_at cannot precede checked_in_at")
        return self


class AttendanceStatusCorrectionRequest(BaseModel):
    status: str
    reason: str = Field(min_length=1, max_length=1000)
    absence_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_status(self) -> AttendanceStatusCorrectionRequest:
        if self.status not in {"present", "absent"}:
            raise ValueError("status must be present or absent")
        if self.status == "absent" and not (self.absence_reason or "").strip():
            raise ValueError("absence_reason is required when status is absent")
        return self


class AttendanceIntervalResponse(FromOrm):
    id: UUID
    sequence: int
    checked_in_at: datetime
    checked_out_at: datetime | None


class AttendanceEventResponse(FromOrm):
    id: UUID
    client_operation_id: UUID | None
    event_type: str
    occurred_at: datetime
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class AttendanceDayResponse(FromOrm):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    child_id: UUID
    enrollment_id: UUID
    room_id: UUID | None
    service_date: date
    status: str
    absence_reason: str | None
    notes: str | None
    version: int
    child_name: str
    intervals: list[AttendanceIntervalResponse]
    events: list[AttendanceEventResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AttendanceRosterItem(BaseModel):
    child_id: UUID
    child_name: str
    profile_photo_url: str | None = None
    enrollment_id: UUID
    room_id: UUID | None
    room_name: str | None
    program_name: str | None
    attendance_day: AttendanceDayResponse | None


class CarePayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeedingCarePayload(CarePayloadBase):
    kind: Literal["meal", "snack", "bottle"]
    intake: Literal["none", "some", "most", "all"]
    volume_ml: int | None = Field(default=None, ge=0, le=2000)

    @model_validator(mode="after")
    def volume_is_only_for_bottles(self) -> FeedingCarePayload:
        if self.kind != "bottle" and self.volume_ml is not None:
            raise ValueError("volume_ml is only valid for bottle feeding")
        if self.intake == "none" and (self.volume_ml or 0) > 0:
            raise ValueError("volume_ml must be zero when intake is none")
        return self


class DiaperCarePayload(CarePayloadBase):
    outcome: Literal["dry", "wet", "soiled", "both"]


class ToiletCarePayload(CarePayloadBase):
    outcome: Literal["attempt", "success", "accident"]


class SleepCarePayload(CarePayloadBase):
    pass


class MoodCarePayload(CarePayloadBase):
    value: Literal["calm", "happy", "sad", "upset", "tired", "energetic"]


class ActivityCarePayload(CarePayloadBase):
    kind: Literal["indoor", "outdoor", "learning", "creative", "physical"]


CarePayload = (
    FeedingCarePayload
    | DiaperCarePayload
    | ToiletCarePayload
    | SleepCarePayload
    | MoodCarePayload
    | ActivityCarePayload
)
CareType = Literal["feeding", "diaper", "toilet", "sleep", "mood", "activity"]

CARE_PAYLOAD_MODELS: dict[str, type[CarePayloadBase]] = {
    "feeding": FeedingCarePayload,
    "diaper": DiaperCarePayload,
    "toilet": ToiletCarePayload,
    "sleep": SleepCarePayload,
    "mood": MoodCarePayload,
    "activity": ActivityCarePayload,
}


def _aware_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone offset")
    return value


def _canonical_care_payload(care_type: str, payload: CarePayload) -> CarePayloadBase:
    expected = CARE_PAYLOAD_MODELS[care_type]
    values = payload.model_dump(exclude_none=True)
    return expected.model_validate(values)


class DailyCareRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attendance_day_id: UUID
    care_type: CareType
    occurred_at: datetime
    payload: CarePayload
    note: str | None = Field(default=None, max_length=500)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_entry(self) -> DailyCareRecordCreate:
        _aware_datetime(self.occurred_at, "occurred_at")
        self.payload = _canonical_care_payload(self.care_type, self.payload)
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class DailyCareSleepFinishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ended_at: datetime
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_end_time(self) -> DailyCareSleepFinishRequest:
        _aware_datetime(self.ended_at, "ended_at")
        return self


class DailyCareCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    ended_at: datetime | None = None
    payload: CarePayload
    note: str | None = Field(default=None, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_times_and_reason(self) -> DailyCareCorrectionRequest:
        _aware_datetime(self.occurred_at, "occurred_at")
        _aware_datetime(self.ended_at, "ended_at")
        if self.ended_at is not None and self.ended_at < self.occurred_at:
            raise ValueError("ended_at cannot precede occurred_at")
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason cannot be blank")
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class DailyCareVoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @field_validator("reason")
    @classmethod
    def non_blank_reason(cls, value: str) -> str:
        resolved = value.strip()
        if not resolved:
            raise ValueError("reason cannot be blank")
        return resolved


class DailyCareRecordResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    room_id: UUID
    child_id: UUID
    enrollment_id: UUID
    attendance_day_id: UUID
    service_date: date
    care_type: CareType
    occurred_at: datetime
    ended_at: datetime | None
    payload: dict[str, Any]
    note: str | None
    created_by_user_id: UUID
    created_by_name: str
    version: int
    voided_at: datetime | None
    voided_by_user_id: UUID | None
    void_reason: str | None
    last_event_type: Literal[
        "recorded",
        "sleep_finished",
        "corrected",
        "voided",
        "auto_finished_at_checkout",
    ]
    recorded_client_operation_id: UUID
    was_corrected: bool
    created_at: datetime
    updated_at: datetime


class DailyCareRecordEventResponse(BaseModel):
    id: UUID
    care_record_id: UUID
    actor_user_id: UUID
    actor_name: str
    client_operation_id: UUID
    event_type: Literal[
        "recorded",
        "sleep_finished",
        "corrected",
        "voided",
        "auto_finished_at_checkout",
    ]
    occurred_at: datetime
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class ChildSafetySummary(BaseModel):
    allergies: str | None
    medical_conditions: str | None
    medication_awareness: str | None
    emergency_medical_consent: bool


class ChildSafetyContact(BaseModel):
    id: UUID
    contact_type: Literal["primary_guardian", "emergency_contact"]
    name: str
    relationship: str | None
    phone: str
    authorized_pickup: bool


class ChildSafetyCardResponse(BaseModel):
    child_id: UUID
    child_name: str
    profile_photo_url: str | None
    age_group: str | None
    facility_id: UUID
    room_id: UUID
    safety: ChildSafetySummary
    contacts: list[ChildSafetyContact]


class CareDayChildResponse(BaseModel):
    child_id: UUID
    child_name: str
    profile_photo_url: str | None
    enrollment_id: UUID
    attendance_day_id: UUID | None
    attendance_state: Literal["not_recorded", "on_site", "checked_out", "no_show"]
    safety: ChildSafetySummary
    records: list[DailyCareRecordResponse]


class CareRoomDayResponse(BaseModel):
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID
    room_name: str
    service_date: date
    generated_at: datetime
    safety_as_of: datetime
    children: list[CareDayChildResponse]


DailyCloseAttendanceState = Literal["not_recorded", "on_site", "checked_out", "no_show"]
DailyCloseAttentionFlag = Literal[
    "open_sleep",
    "medication_refused",
    "medication_omitted",
    "incident_draft",
    "incident_under_review",
]


class DailyCloseCareCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feeding: int = Field(ge=0)
    diaper: int = Field(ge=0)
    toilet: int = Field(ge=0)
    sleep: int = Field(ge=0)
    mood: int = Field(ge=0)
    activity: int = Field(ge=0)


class DailyCloseMedicationOutcomeCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    administered: int = Field(ge=0)
    refused: int = Field(ge=0)
    omitted: int = Field(ge=0)


class DailyCloseIncidentStatusCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: int = Field(ge=0)
    under_review: int = Field(ge=0)
    finalized: int = Field(ge=0)


class DailyCloseAttendanceStateCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    not_recorded: int = Field(ge=0)
    on_site: int = Field(ge=0)
    checked_out: int = Field(ge=0)
    no_show: int = Field(ge=0)


class DailyCloseAttentionFlagCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_sleep: int = Field(ge=0)
    medication_refused: int = Field(ge=0)
    medication_omitted: int = Field(ge=0)
    incident_draft: int = Field(ge=0)
    incident_under_review: int = Field(ge=0)


class RoomDailyCloseChildResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: UUID
    child_name: str
    profile_photo_url: str | None
    enrollment_id: UUID
    attendance_day_id: UUID | None
    attendance_state: DailyCloseAttendanceState
    first_check_in_at: datetime | None
    last_checkout_at: datetime | None
    accumulated_minutes: int = Field(ge=0)
    currently_on_site: bool
    care_counts: DailyCloseCareCounts
    open_sleep: bool
    most_recent_care_at: datetime | None
    medication_administration_counts: DailyCloseMedicationOutcomeCounts
    most_recent_medication_at: datetime | None
    incident_status_counts: DailyCloseIncidentStatusCounts
    most_recent_incident_at: datetime | None
    attention_flags: list[DailyCloseAttentionFlag]


class RoomDailyCloseTotalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_count: int = Field(ge=0)
    attendance_state_counts: DailyCloseAttendanceStateCounts
    accumulated_minutes: int = Field(ge=0)
    currently_on_site: int = Field(ge=0)
    care_counts: DailyCloseCareCounts
    open_sleep: int = Field(ge=0)
    medication_administration_counts: DailyCloseMedicationOutcomeCounts
    incident_status_counts: DailyCloseIncidentStatusCounts
    attention_flag_counts: DailyCloseAttentionFlagCounts


class RoomDailyClosePreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID
    room_name: str
    service_date: date
    generated_at: datetime
    totals: RoomDailyCloseTotalsResponse
    children: list[RoomDailyCloseChildResponse]


MedicationRoute = Literal["oral", "topical", "inhaled", "injected", "other"]
MedicationKind = Literal["non_emergency", "emergency"]
MedicationStorageMethod = Literal["locked_inaccessible", "emergency_accessible_per_plan"]
MedicationPlanStatus = Literal["draft", "active", "archived"]
MedicationAuthorizationStatus = Literal["not_recorded", "verified", "revoked"]
MedicationOutcome = Literal["administered", "refused", "omitted"]


def _strip_required(value: str, field_name: str) -> str:
    resolved = value.strip()
    if not resolved:
        raise ValueError(f"{field_name} cannot be blank")
    return resolved


class MedicationGuardianOption(BaseModel):
    id: UUID
    name: str
    relationship: str | None


class MedicationPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facility_id: UUID
    child_id: UUID
    medication_name: str = Field(min_length=1, max_length=255)
    dosage: str = Field(min_length=1, max_length=255)
    route: MedicationRoute
    label_directions: str = Field(min_length=1, max_length=3000)
    scheduled_times: list[time] = Field(default_factory=list, max_length=24)
    as_needed: bool = False
    start_date: date
    end_date: date | None = None
    medication_kind: MedicationKind
    storage_method: MedicationStorageMethod
    storage_instructions: str = Field(min_length=1, max_length=2000)
    emergency_plan_reference: str | None = Field(default=None, max_length=255)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_plan(self) -> MedicationPlanCreate:
        for field_name in (
            "medication_name",
            "dosage",
            "label_directions",
            "storage_instructions",
        ):
            setattr(self, field_name, _strip_required(getattr(self, field_name), field_name))
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot precede start_date")
        if len(set(self.scheduled_times)) != len(self.scheduled_times):
            raise ValueError("scheduled_times cannot contain duplicates")
        self.scheduled_times = sorted(self.scheduled_times)
        if not self.as_needed and not self.scheduled_times:
            raise ValueError("A scheduled plan requires at least one scheduled time")
        if self.medication_kind == "non_emergency":
            if self.storage_method != "locked_inaccessible":
                raise ValueError("Non-emergency medication must use locked inaccessible storage")
            if self.emergency_plan_reference is not None:
                raise ValueError("emergency_plan_reference is only valid for emergency medication")
        else:
            if self.storage_method != "emergency_accessible_per_plan":
                raise ValueError("Emergency medication must use the agreed accessible plan")
            if self.emergency_plan_reference is None:
                raise ValueError("emergency_plan_reference is required for emergency medication")
            self.emergency_plan_reference = _strip_required(
                self.emergency_plan_reference, "emergency_plan_reference"
            )
        return self


class MedicationPlanUpdate(MedicationPlanCreate):
    client_operation_id: UUID
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_update(self) -> MedicationPlanUpdate:
        self.reason = _strip_required(self.reason, "reason")
        return self


class MedicationAuthorizationRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guardian_id: UUID
    signed_authorization_reference: str = Field(min_length=1, max_length=255)
    authorization_signed_at: datetime
    valid_until: date | None = None
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_authorization(self) -> MedicationAuthorizationRecordRequest:
        _aware_datetime(self.authorization_signed_at, "authorization_signed_at")
        self.signed_authorization_reference = _strip_required(
            self.signed_authorization_reference, "signed_authorization_reference"
        )
        return self


class MedicationAuthorizationRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _strip_required(value, "reason")


class MedicationPlanActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_labelled_container_confirmed: Literal[True]
    label_directions_confirmed: Literal[True]
    expected_version: int = Field(ge=1)
    client_operation_id: UUID


class MedicationPlanArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _strip_required(value, "reason")


class MedicationPlanResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    child_id: UUID
    child_name: str
    medication_name: str
    dosage: str
    route: MedicationRoute
    label_directions: str
    scheduled_times: list[str]
    as_needed: bool
    start_date: date
    end_date: date | None
    medication_kind: MedicationKind
    storage_method: MedicationStorageMethod
    storage_instructions: str
    emergency_plan_reference: str | None
    status: MedicationPlanStatus
    authorization_status: MedicationAuthorizationStatus
    authorization_is_current: bool
    signed_authorization_required: Literal[True] = True
    signed_authorization_reference: str | None
    authorization_guardian_id: UUID | None
    authorization_guardian_name: str | None
    authorization_signed_at: datetime | None
    authorization_valid_until: date | None
    authorization_verified_at: datetime | None
    authorization_verified_by_user_id: UUID | None
    authorization_revoked_at: datetime | None
    authorization_revocation_reason: str | None
    original_labelled_container_verified_at: datetime | None
    label_directions_verified_at: datetime | None
    created_by_user_id: UUID
    created_by_name: str
    eligible_guardians: list[MedicationGuardianOption]
    version: int
    archived_at: datetime | None
    archive_reason: str | None
    last_event_type: Literal[
        "created",
        "updated",
        "authorization_verified",
        "authorization_revoked",
        "activated",
        "archived",
    ]
    created_at: datetime
    updated_at: datetime


class MedicationPlanEventResponse(BaseModel):
    id: UUID
    medication_plan_id: UUID
    actor_user_id: UUID
    actor_name: str
    client_operation_id: UUID
    event_type: Literal[
        "created",
        "updated",
        "authorization_verified",
        "authorization_revoked",
        "activated",
        "archived",
    ]
    occurred_at: datetime
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class MedicationAdministrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medication_plan_id: UUID
    attendance_day_id: UUID
    outcome: MedicationOutcome
    scheduled_for: time | None = None
    occurred_at: datetime
    amount: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_outcome(self) -> MedicationAdministrationCreate:
        _aware_datetime(self.occurred_at, "occurred_at")
        if self.outcome == "administered":
            if self.amount is None:
                raise ValueError("amount is required when medication is administered")
            self.amount = _strip_required(self.amount, "amount")
            if self.reason is not None:
                raise ValueError("reason is only valid for a refusal or omission")
        else:
            if self.amount is not None:
                raise ValueError("amount is only valid when medication is administered")
            if self.reason is None:
                raise ValueError("reason is required for a refusal or omission")
            self.reason = _strip_required(self.reason, "reason")
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class MedicationAdministrationCorrection(MedicationAdministrationCreate):
    medication_plan_id: UUID
    attendance_day_id: UUID
    correction_reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_correction(self) -> MedicationAdministrationCorrection:
        self.correction_reason = _strip_required(self.correction_reason, "correction_reason")
        return self


class MedicationAdministrationVoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _strip_required(value, "reason")


class MedicationPlanSnapshot(BaseModel):
    medication_name: str
    dosage: str
    route: MedicationRoute
    label_directions: str
    scheduled_times: list[str]
    as_needed: bool
    medication_kind: MedicationKind
    storage_method: MedicationStorageMethod
    authorization_status: MedicationAuthorizationStatus
    signed_authorization_reference: str
    authorization_guardian_name: str
    authorization_signed_at: datetime
    authorization_valid_until: date | None
    plan_version: int


class MedicationAdministrationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    room_id: UUID
    child_id: UUID
    enrollment_id: UUID
    attendance_day_id: UUID
    service_date: date
    medication_plan_id: UUID
    plan_version: int
    plan_snapshot: MedicationPlanSnapshot
    outcome: MedicationOutcome
    scheduled_for: str | None
    occurred_at: datetime
    amount: str | None
    reason: str | None
    note: str | None
    staff_name_snapshot: str
    staff_initials_snapshot: str
    created_by_user_id: UUID
    created_by_name: str
    version: int
    voided_at: datetime | None
    voided_by_user_id: UUID | None
    void_reason: str | None
    last_event_type: Literal["recorded", "corrected", "voided"]
    was_corrected: bool
    created_at: datetime
    updated_at: datetime


class MedicationAdministrationEventResponse(BaseModel):
    id: UUID
    medication_administration_id: UUID
    actor_user_id: UUID
    actor_name: str
    client_operation_id: UUID
    event_type: Literal["recorded", "corrected", "voided"]
    occurred_at: datetime
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class MedicationDayChildResponse(BaseModel):
    child_id: UUID
    child_name: str
    profile_photo_url: str | None
    enrollment_id: UUID
    attendance_day_id: UUID | None
    attendance_state: Literal["not_recorded", "on_site", "checked_out", "no_show"]
    eligible_guardians: list[MedicationGuardianOption]
    plans: list[MedicationPlanResponse]
    administrations: list[MedicationAdministrationResponse]


class MedicationRoomDayResponse(BaseModel):
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID
    room_name: str
    service_date: date
    generated_at: datetime
    children: list[MedicationDayChildResponse]


IncidentCategory = Literal[
    "injury",
    "illness",
    "missing_child",
    "unauthorized_release",
    "allegation",
    "emergency",
    "other",
]
IncidentSeverity = Literal["minor", "moderate", "serious", "critical"]
IncidentStatus = Literal["draft", "under_review", "finalized"]
IncidentReportability = Literal["unassessed", "not_reportable", "other_reportable", "critical"]
IncidentExternalStatus = Literal["not_assessed", "not_required", "pending", "recorded"]
IncidentMedicalAttention = Literal[
    "none", "first_aid", "medical_practitioner", "emergency_services"
]
IncidentParentNotificationStatus = Literal[
    "pending", "notified", "unable_to_reach", "not_applicable"
]
IncidentAuthority = Literal[
    "emergency_services", "police", "child_intervention", "child_care_connect", "other"
]


def _validate_incident_notification(
    status: IncidentParentNotificationStatus,
    notified_at: datetime | None,
    notes: str | None,
) -> tuple[datetime | None, str | None]:
    _aware_datetime(notified_at, "parent_notified_at")
    if status == "notified":
        if notified_at is None or notes is None:
            raise ValueError("Notified parent records require time and notes")
        notes = _strip_required(notes, "parent_notification_notes")
    elif status == "unable_to_reach":
        if notified_at is not None or notes is None:
            raise ValueError("Unable-to-reach records require notes and no notified time")
        notes = _strip_required(notes, "parent_notification_notes")
    elif notified_at is not None or notes is not None:
        raise ValueError("Pending/not-applicable notification cannot include time or notes")
    return notified_at, notes


class IncidentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facility_id: UUID
    room_id: UUID
    attendance_day_id: UUID | None = None
    occurred_at: datetime
    category: IncidentCategory
    severity: IncidentSeverity
    summary: str = Field(min_length=1, max_length=5000)
    immediate_actions: str = Field(min_length=1, max_length=5000)
    medical_attention: IncidentMedicalAttention
    parent_notification_status: IncidentParentNotificationStatus
    parent_notified_at: datetime | None = None
    parent_notification_notes: str | None = Field(default=None, max_length=3000)
    authorities_contacted: list[IncidentAuthority] = Field(default_factory=list, max_length=5)
    staff_present: list[str] = Field(default_factory=list, max_length=50)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_incident(self) -> IncidentCreateRequest:
        _aware_datetime(self.occurred_at, "occurred_at")
        self.summary = _strip_required(self.summary, "summary")
        self.immediate_actions = _strip_required(self.immediate_actions, "immediate_actions")
        self.parent_notified_at, self.parent_notification_notes = _validate_incident_notification(
            self.parent_notification_status,
            self.parent_notified_at,
            self.parent_notification_notes,
        )
        self.authorities_contacted = list(dict.fromkeys(self.authorities_contacted))
        cleaned_staff = [_strip_required(value, "staff_present") for value in self.staff_present]
        self.staff_present = list(dict.fromkeys(cleaned_staff))
        return self


class IncidentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    category: IncidentCategory
    severity: IncidentSeverity
    summary: str = Field(min_length=1, max_length=5000)
    immediate_actions: str = Field(min_length=1, max_length=5000)
    medical_attention: IncidentMedicalAttention
    parent_notification_status: IncidentParentNotificationStatus
    parent_notified_at: datetime | None = None
    parent_notification_notes: str | None = Field(default=None, max_length=3000)
    authorities_contacted: list[IncidentAuthority] = Field(default_factory=list, max_length=5)
    staff_present: list[str] = Field(default_factory=list, max_length=50)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)
    client_operation_id: UUID

    @model_validator(mode="after")
    def validate_incident(self) -> IncidentUpdateRequest:
        _aware_datetime(self.occurred_at, "occurred_at")
        for field_name in ("summary", "immediate_actions", "reason"):
            setattr(self, field_name, _strip_required(getattr(self, field_name), field_name))
        self.parent_notified_at, self.parent_notification_notes = _validate_incident_notification(
            self.parent_notification_status,
            self.parent_notified_at,
            self.parent_notification_notes,
        )
        self.authorities_contacted = list(dict.fromkeys(self.authorities_contacted))
        cleaned_staff = [_strip_required(value, "staff_present") for value in self.staff_present]
        self.staff_present = list(dict.fromkeys(cleaned_staff))
        return self


class IncidentTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    client_operation_id: UUID


class IncidentReturnDraftRequest(IncidentTransitionRequest):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _strip_required(value, "reason")


class IncidentFinalizeRequest(IncidentTransitionRequest):
    reportability_assessment: Literal["not_reportable", "other_reportable", "critical"]
    reviewer_note: str = Field(min_length=1, max_length=3000)

    @field_validator("reviewer_note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        return _strip_required(value, "reviewer_note")


class IncidentExternalReportRequest(IncidentTransitionRequest):
    reported_at: datetime
    confirmation_reference: str = Field(min_length=1, max_length=255)
    submission_channel: Literal["alberta_licensing_portal", "child_care_connect_then_portal"]
    submitted_by_name: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_report(self) -> IncidentExternalReportRequest:
        _aware_datetime(self.reported_at, "reported_at")
        self.confirmation_reference = _strip_required(
            self.confirmation_reference, "confirmation_reference"
        )
        self.submitted_by_name = _strip_required(self.submitted_by_name, "submitted_by_name")
        return self


class IncidentResponse(BaseModel):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID
    room_name: str
    child_id: UUID | None
    child_name: str | None
    enrollment_id: UUID | None
    attendance_day_id: UUID | None
    service_date: date
    occurred_at: datetime
    category: IncidentCategory
    severity: IncidentSeverity
    summary: str
    immediate_actions: str
    medical_attention: IncidentMedicalAttention
    parent_notification_status: IncidentParentNotificationStatus
    parent_notified_at: datetime | None
    parent_notification_notes: str | None
    authorities_contacted: list[IncidentAuthority]
    staff_present: list[str]
    status: IncidentStatus
    reportability_assessment: IncidentReportability
    reporting_timeline: Literal[
        "not_assessed",
        "not_reportable",
        "as_soon_as_possible_no_later_than_24_hours",
        "within_2_business_days",
    ]
    reviewer_note: str | None
    finalized_at: datetime | None
    finalized_by_user_id: UUID | None
    external_report_status: IncidentExternalStatus
    external_reported_at: datetime | None
    external_confirmation_reference: str | None
    external_submission_channel: (
        Literal["alberta_licensing_portal", "child_care_connect_then_portal"] | None
    )
    external_submitted_by_name: str | None
    external_report_recorded_by_user_id: UUID | None
    external_submission_performed_by_caresync: Literal[False] = False
    created_by_user_id: UUID
    created_by_name: str
    version: int
    last_event_type: Literal[
        "drafted",
        "updated",
        "submitted_for_review",
        "returned_to_draft",
        "finalized",
        "external_report_recorded",
    ]
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    organization_id: UUID
    generated_at: datetime
    incidents: list[IncidentResponse]


class IncidentAttendanceOption(BaseModel):
    attendance_day_id: UUID
    child_id: UUID
    child_name: str
    attendance_state: Literal["on_site", "checked_out"]


class IncidentRoomContextResponse(BaseModel):
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    facility_timezone: str
    room_id: UUID
    room_name: str
    service_date: date
    generated_at: datetime
    attendance_options: list[IncidentAttendanceOption]


class IncidentEventResponse(BaseModel):
    id: UUID
    incident_record_id: UUID
    actor_user_id: UUID
    actor_name: str
    client_operation_id: UUID
    event_type: Literal[
        "drafted",
        "updated",
        "submitted_for_review",
        "returned_to_draft",
        "finalized",
        "external_report_recorded",
    ]
    occurred_at: datetime
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class SettingsResponse(BaseModel):
    organization_id: UUID
    timezone: str
    preferences: dict[str, Any]


class SettingsPatch(BaseModel):
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    preferences: dict[str, Any] | None = None


class StaffRoleResponse(FromOrm):
    id: UUID
    key: str
    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class StaffFacilityResponse(FromOrm):
    id: UUID
    organization_id: UUID
    name: str
    status: str
    timezone: str


class StaffRoomResponse(FromOrm):
    id: UUID
    organization_id: UUID
    facility_id: UUID
    name: str
    is_active: bool


class StaffCredentialSummary(BaseModel):
    certification_type: str | None
    certification_number: str | None
    expiry_date: date | None
    verification_status: Literal["unverified", "pending", "verified", "rejected"]
    ready: bool


class StaffShiftSummary(BaseModel):
    id: UUID
    facility_id: UUID
    scheduled_shift_id: UUID | None = None
    status: Literal["open", "closed"]
    clocked_in_at: datetime
    clocked_out_at: datetime | None


class StaffAssignmentSummary(BaseModel):
    facility_id: UUID
    facility_name: str
    room_id: UUID
    room_name: str


class StaffMemberResponse(BaseModel):
    membership_id: UUID
    organization_id: UUID
    user_id: UUID
    email: str
    first_name: str
    last_name: str
    role: StaffRoleResponse
    membership_status: Literal["active", "suspended"]
    assigned_facility_ids: list[UUID] = Field(default_factory=list)
    assigned_room_ids: list[UUID] = Field(default_factory=list)
    active_assignments: list[StaffAssignmentSummary] = Field(default_factory=list)
    credential: StaffCredentialSummary | None = None
    current_shift: StaffShiftSummary | None = None
    private_hr_fields_exposed: Literal[False] = False
    joined_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StaffInvitationResponse(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    first_name: str
    last_name: str
    role: StaffRoleResponse
    status: Literal["pending", "accepted", "revoked", "expired"]
    assigned_facility_ids: list[UUID] = Field(default_factory=list)
    assigned_room_ids: list[UUID] = Field(default_factory=list)
    expires_at: datetime
    created_at: datetime


class StaffWorkspaceResponse(BaseModel):
    organization_id: UUID
    roles: list[StaffRoleResponse]
    facilities: list[StaffFacilityResponse]
    rooms: list[StaffRoomResponse]
    members: list[StaffMemberResponse]
    invitations: list[StaffInvitationResponse]


class StaffInvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role_id: UUID
    assigned_facility_ids: list[UUID] = Field(default_factory=list)
    assigned_room_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_scope_ids(self) -> StaffInvitationCreate:
        if len(set(self.assigned_facility_ids)) != len(self.assigned_facility_ids):
            raise ValueError("assigned_facility_ids must be unique")
        if len(set(self.assigned_room_ids)) != len(self.assigned_room_ids):
            raise ValueError("assigned_room_ids must be unique")
        return self


class StaffOneTimeActivationResponse(BaseModel):
    invitation: StaffInvitationResponse
    activation_url: str


class StaffMemberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: UUID
    assigned_facility_ids: list[UUID] = Field(default_factory=list)
    assigned_room_ids: list[UUID] = Field(default_factory=list)
    membership_status: Literal["active", "suspended"] | None = None

    @model_validator(mode="after")
    def unique_scope_ids(self) -> StaffMemberPatch:
        if len(set(self.assigned_facility_ids)) != len(self.assigned_facility_ids):
            raise ValueError("assigned_facility_ids must be unique")
        if len(set(self.assigned_room_ids)) != len(self.assigned_room_ids):
            raise ValueError("assigned_room_ids must be unique")
        return self


class OneTimeTokenRequest(BaseModel):
    """One-time secret transported in an HTTPS request body, never a URL."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=400)


class StaffActivationPreview(BaseModel):
    organization_name: str
    email: str
    first_name: str
    last_name: str
    role_name: str
    expires_at: datetime
    assigned_room_names: list[str]


class StaffActivationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=400)
    password: str = Field(min_length=12, max_length=128)


class StaffPasswordResetResponse(BaseModel):
    reset_url: str
    expires_at: datetime


class PasswordResetPreview(BaseModel):
    organization_name: str
    email: str
    expires_at: datetime


class PasswordResetComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=400)
    password: str = Field(min_length=12, max_length=128)


StaffPathway = Literal["educator", "student_educator", "driver", "educator_driver"]
PositionShape = Literal["educator_only", "driver_only", "educator_driver"]
DrivingRequirement = Literal["not_applicable", "preferred", "required"]
VehicleExpectation = Literal["none", "organization_vehicle", "personal_vehicle", "either"]


class AtsServiceWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[
        Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    ] = Field(min_length=1, max_length=7)
    start_time: time
    end_time: time
    timezone: str = Field(default="America/Edmonton", min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_window(self) -> AtsServiceWindow:
        if len(set(self.days)) != len(self.days):
            raise ValueError("service window days cannot contain duplicates")
        if self.start_time == self.end_time:
            raise ValueError("service window start and end times must differ")
        self.timezone = self.timezone.strip()
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("service window timezone must be a named IANA zone") from None
        return self


def _normalize_licence_jurisdiction(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized == "OTHER":
        return normalized
    if re.fullmatch(r"[A-Z]{2}", normalized):
        normalized = f"CA-{normalized}"
    if not re.fullmatch(r"[A-Z]{2}(?:-[A-Z0-9]{1,3})?", normalized):
        raise ValueError("licence jurisdiction must be ISO-like (for example CA-AB) or OTHER")
    return normalized


def _normalize_licence_class(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().upper().split())
    if not re.fullmatch(r"[A-Z0-9](?:[A-Z0-9 .+/-]{0,28}[A-Z0-9])?", normalized):
        raise ValueError("licence class contains unsupported characters")
    return normalized


class AtsStructuredTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_shape: PositionShape = "educator_only"
    driving_requirement: DrivingRequirement = "not_applicable"
    vehicle_expectation: VehicleExpectation = "none"
    required_licence_jurisdiction: str | None = Field(default=None, max_length=20)
    required_licence_jurisdiction_other: str | None = Field(default=None, max_length=100)
    required_licence_class: str | None = Field(default=None, max_length=30)
    minimum_driving_experience_months: int = Field(default=0, ge=0, le=1200)
    service_area: str | None = Field(default=None, max_length=500)
    service_windows: list[AtsServiceWindow] = Field(default_factory=list, max_length=50)
    mileage_policy: str | None = Field(default=None, max_length=5000)
    driving_time_paid: bool = False
    screening_conditions: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("required_licence_jurisdiction")
    @classmethod
    def normalize_jurisdiction(cls, value: str | None) -> str | None:
        return _normalize_licence_jurisdiction(value)

    @field_validator("required_licence_class")
    @classmethod
    def normalize_class(cls, value: str | None) -> str | None:
        return _normalize_licence_class(value)

    @model_validator(mode="after")
    def validate_driving_terms(self) -> AtsStructuredTerms:
        if self.required_licence_jurisdiction_other is not None:
            self.required_licence_jurisdiction_other = (
                self.required_licence_jurisdiction_other.strip() or None
            )
        if self.service_area is not None:
            self.service_area = self.service_area.strip() or None
        if self.mileage_policy is not None:
            self.mileage_policy = self.mileage_policy.strip() or None
        self.screening_conditions = list(
            dict.fromkeys(item.strip() for item in self.screening_conditions if item.strip())
        )
        if self.required_licence_jurisdiction == "OTHER":
            if not self.required_licence_jurisdiction_other:
                raise ValueError("OTHER licence jurisdiction requires a description")
        elif self.required_licence_jurisdiction_other is not None:
            raise ValueError("licence jurisdiction description is only valid for OTHER")
        if self.position_shape == "educator_only":
            if any(
                (
                    self.driving_requirement != "not_applicable",
                    self.vehicle_expectation != "none",
                    self.required_licence_jurisdiction is not None,
                    self.required_licence_class is not None,
                    self.minimum_driving_experience_months,
                    self.service_area,
                    self.service_windows,
                    self.mileage_policy,
                    self.driving_time_paid,
                )
            ):
                raise ValueError("educator-only positions cannot contain driving duties")
            return self
        if self.driving_requirement == "not_applicable" or self.vehicle_expectation == "none":
            raise ValueError("driver positions require driving and vehicle expectations")
        if self.position_shape == "driver_only" and self.driving_requirement != "required":
            raise ValueError("driver-only positions must require driving")
        if self.required_licence_jurisdiction is None or self.required_licence_class is None:
            raise ValueError("driver positions require a normalized licence jurisdiction and class")
        if self.vehicle_expectation in {"personal_vehicle", "either"} and not self.mileage_policy:
            raise ValueError("personal-vehicle positions require a mileage/expense policy")
        return self


class AtsJobCreate(AtsStructuredTerms):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1, max_length=20000)
    employment_type: str = Field(min_length=1, max_length=50)
    facility_id: UUID | None = None
    location: str | None = Field(default=None, max_length=255)
    requirements: list[str] = Field(default_factory=list, max_length=100)
    openings: int = Field(default=1, ge=1, le=1000)


class AtsJobPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, min_length=1, max_length=20000)
    employment_type: str | None = Field(default=None, min_length=1, max_length=50)
    facility_id: UUID | None = None
    location: str | None = Field(default=None, max_length=255)
    requirements: list[str] | None = Field(default=None, max_length=100)
    openings: int | None = Field(default=None, ge=1, le=1000)
    position_shape: PositionShape | None = None
    driving_requirement: DrivingRequirement | None = None
    vehicle_expectation: VehicleExpectation | None = None
    required_licence_jurisdiction: str | None = Field(default=None, max_length=20)
    required_licence_jurisdiction_other: str | None = Field(default=None, max_length=100)
    required_licence_class: str | None = Field(default=None, max_length=30)
    minimum_driving_experience_months: int | None = Field(default=None, ge=0, le=1200)
    service_area: str | None = Field(default=None, max_length=500)
    service_windows: list[AtsServiceWindow] | None = Field(default=None, max_length=50)
    mileage_policy: str | None = Field(default=None, max_length=5000)
    driving_time_paid: bool | None = None
    screening_conditions: list[str] | None = Field(default=None, max_length=50)
    expected_version: int = Field(ge=1)

    @field_validator("required_licence_jurisdiction")
    @classmethod
    def normalize_patch_jurisdiction(cls, value: str | None) -> str | None:
        return _normalize_licence_jurisdiction(value)

    @field_validator("required_licence_class")
    @classmethod
    def normalize_patch_class(cls, value: str | None) -> str | None:
        return _normalize_licence_class(value)


class AtsJobStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "paused", "closed"]
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)


class AtsJobResponse(FromOrm):
    id: UUID
    organization_id: UUID
    facility_id: UUID | None
    title: str
    description: str
    employment_type: str
    location: str | None
    requirements: list[str]
    position_shape: PositionShape = "educator_only"
    driving_requirement: DrivingRequirement = "not_applicable"
    vehicle_expectation: VehicleExpectation = "none"
    required_licence_jurisdiction: str | None = None
    required_licence_jurisdiction_other: str | None = None
    required_licence_class: str | None = None
    minimum_driving_experience_months: int = 0
    service_area: str | None = None
    service_windows: list[AtsServiceWindow] = Field(default_factory=list)
    mileage_policy: str | None = None
    driving_time_paid: bool = False
    screening_conditions: list[str] = Field(default_factory=list)
    openings: int
    status: Literal["draft", "open", "paused", "closed"]
    published_at: datetime | None
    closed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class AtsCandidateInviteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)


class AtsCandidateResponse(FromOrm):
    id: UUID
    organization_id: UUID
    email: str
    first_name: str
    last_name: str
    phone: str | None
    status: str
    notes: str | None
    onboarding_status: str
    certification_type: str | None
    certification_number: str | None
    certification_expiry_date: date | None
    certification_verification_status: str
    certification_verified_at: datetime | None
    certification_verified_by_user_id: UUID | None
    certification_review_note: str | None
    work_history: list[dict[str, Any]]
    certification_provenance: Literal["manual", "local_ocr"] | None
    certification_candidate_confirmed_at: datetime | None
    work_history_provenance: Literal["manual", "local_ocr"] | None
    work_history_candidate_confirmed_at: datetime | None
    candidate_type: Literal["certified_educator", "student"] | None
    institution: str | None
    program: str | None
    expected_graduation_date: date | None
    pathway: StaffPathway | None = None
    driver_declaration: dict[str, Any] | None = None
    operational_driver_ready: Literal[False] = False
    created_at: datetime
    updated_at: datetime


class AtsInvitationResponse(BaseModel):
    id: UUID
    application_id: UUID
    expires_at: datetime
    status: Literal["pending", "accepted", "revoked", "expired"]


class AtsInviteResult(BaseModel):
    candidate: AtsCandidateResponse
    application: AtsApplicationResponse
    invitation: AtsInvitationResponse
    invitation_url: str


class AtsApplicationStageChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["applied", "screening", "interview", "rejected", "withdrawn"]
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)


class AtsApplicationResponse(FromOrm):
    id: UUID
    organization_id: UUID
    job_id: UUID
    candidate_id: UUID
    status: str
    stage_notes: str | None
    hire_handoff_requested_at: datetime | None
    hire_handoff_requested_by_user_id: UUID | None
    version: int
    source: Literal["private_invitation", "marketplace_application", "employer_interest"]
    candidate_consent_status: Literal["requested", "accepted", "declined"]
    created_at: datetime
    updated_at: datetime


class AtsOfferCreate(AtsStructuredTerms):
    model_config = ConfigDict(extra="forbid")
    position_title: str = Field(min_length=1, max_length=180)
    start_date: date | None = None
    compensation: str | None = Field(default=None, max_length=255)
    terms: str = Field(min_length=1, max_length=30000)
    expires_at: datetime | None = None
    expected_application_version: int = Field(ge=1)


class AtsOfferCreateAndSend(AtsOfferCreate):
    """Atomic, retry-safe command for publishing a new offer version."""

    client_operation_id: UUID


class AtsOfferDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accepted", "declined", "withdrawn"]
    reason: str = Field(min_length=3, max_length=2000)


class AtsOfferResponse(FromOrm):
    id: UUID
    organization_id: UUID
    application_id: UUID
    version: int
    client_operation_id: UUID | None
    status: str
    position_title: str
    start_date: date | None
    compensation: str | None
    terms: str
    position_shape: PositionShape = "educator_only"
    driving_requirement: DrivingRequirement = "not_applicable"
    vehicle_expectation: VehicleExpectation = "none"
    required_licence_jurisdiction: str | None = None
    required_licence_jurisdiction_other: str | None = None
    required_licence_class: str | None = None
    minimum_driving_experience_months: int = 0
    service_area: str | None = None
    service_windows: list[AtsServiceWindow] = Field(default_factory=list)
    mileage_policy: str | None = None
    driving_time_paid: bool = False
    screening_conditions: list[str] = Field(default_factory=list)
    terms_digest: str | None = None
    sent_at: datetime | None
    expires_at: datetime | None
    accepted_at: datetime | None
    terminal_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AtsHireHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)


class AtsHireHandoffResponse(BaseModel):
    application: AtsApplicationResponse
    membership_created: Literal[False] = False
    next_step: str = (
        "Create or invite the staff member through the controlled staff access workflow."
    )


class AtsWorkspaceResponse(BaseModel):
    screening_schema_version: Literal["0030"] | None = None
    jobs: list[AtsJobResponse]
    candidates: list[AtsCandidateResponse]
    applications: list[AtsApplicationResponse]
    offers: list[AtsOfferResponse]
    interviews: list[AtsInterviewResponse] = Field(default_factory=list)


class AtsInterviewResponse(FromOrm):
    id: UUID
    organization_id: UUID
    application_id: UUID
    scheduled_at: datetime
    timezone: str
    location_or_link: str
    status: Literal[
        "requested",
        "confirmed",
        "declined",
        "cancelled",
        "candidate_proposed",
        "proposal_declined",
    ]
    candidate_proposed_at: datetime | None = None
    candidate_proposal_note: str | None = None
    created_at: datetime
    updated_at: datetime


class AtsProvisionStaffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    expected_version: int = Field(ge=1)


class AtsProvisionStaffResponse(BaseModel):
    application: AtsApplicationResponse
    membership_id: UUID
    user_id: UUID
    role_key: Literal["educator"] = "educator"
    assigned_room_ids: list[UUID] = Field(default_factory=list)
    membership_created: bool
    provisioning_id: UUID


class AtsCertificationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "verified", "rejected"]
    reason: str = Field(min_length=3, max_length=2000)
