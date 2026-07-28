"""Family, child, guardian, and emergency-contact response contracts."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChildResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date
    start_date: date
    gender: str | None
    age_group: str | None
    is_active: bool
    need_invoice: bool
    fscd_file_number: str | None
    schedule_start_time: str | None
    schedule_end_time: str | None
    created_at: datetime
    updated_at: datetime


class ChildListResponse(ChildResponse):
    family_name: str


class GuardianResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    first_name: str
    last_name: str
    relationship: str | None = Field(validation_alias="relationship_")
    guardian_type: str
    email: str
    cell_phone: str
    home_phone: str | None
    work_phone: str | None
    address: str | None
    city: str | None
    postal_code: str | None


class EmergencyContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    first_name: str
    last_name: str
    relationship: str = Field(validation_alias="relationship_")
    cell_phone: str
    home_phone: str | None
    authorized_pickup: bool


class FamilyListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    status: str
    file_number: str | None
    is_recurring_billing: bool
    created_at: datetime
    updated_at: datetime


class FamilySummaryResponse(FamilyListResponse):
    children: list[ChildResponse]
    guardians: list[GuardianResponse]


class FamilyDetailResponse(FamilyListResponse):
    photo_consent: bool
    field_trip_consent: bool
    emergency_medical_consent: bool
    additional_notes: str | None
    additional_fees: list[dict] | dict
    recurring_funding_source_id: str | None
    children: list[ChildResponse]
    guardians: list[GuardianResponse]
    emergency_contacts: list[EmergencyContactResponse]


class FamilyStatsResponse(BaseModel):
    families: int
    active_families: int
    children: int
    active_children: int
    pending_families: int
    by_age_group: dict[str, int]


class GuardianCreate(BaseModel):
    first_name: str
    last_name: str
    relationship: str | None = None
    guardian_type: str = "primary"
    email: str
    cell_phone: str
    home_phone: str | None = None
    work_phone: str | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None


class ChildCreate(BaseModel):
    first_name: str
    middle_name: str | None = None
    last_name: str
    date_of_birth: date
    start_date: date
    gender: str | None = None
    health_care_number: str | None = None
    allergies: str | None = None
    medical_conditions: str | None = None
    medications: str | None = None
    immunization_up_to_date: bool | None = None
    doctor_name: str | None = None
    doctor_phone: str | None = None


class EmergencyContactCreate(BaseModel):
    first_name: str
    last_name: str
    relationship: str
    cell_phone: str
    home_phone: str | None = None
    authorized_pickup: bool = True


class ConsentCreate(BaseModel):
    photo_consent: bool = False
    field_trip_consent: bool = False
    emergency_medical_consent: bool = False


class FamilyRegistrationRequest(BaseModel):
    primary_guardian: GuardianCreate
    secondary_guardian: GuardianCreate | None = None
    children: list[ChildCreate]
    emergency_contacts: list[EmergencyContactCreate] = Field(default_factory=list)
    consents: ConsentCreate
    additional_notes: str | None = None
