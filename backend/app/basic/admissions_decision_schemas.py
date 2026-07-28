"""Strict schemas for the 0039 administrator admissions decision spine."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AdmissionApplicationStatus = Literal[
    "draft",
    "submitted",
    "under_review",
    "waitlisted",
    "offered",
    "accepted",
    "declined",
    "withdrawn",
]
AdmissionApplicationSource = Literal["administrator_entry"]
AdmissionWaitlistStatus = Literal["active", "offered", "closed"]
AdmissionWaitlistClosureReason = Literal[
    "facts_changed",
    "review_reopened",
    "application_declined",
    "application_withdrawn",
    "offer_declined",
    "application_accepted",
]
AdmissionOfferStatus = Literal["open", "accepted", "declined", "withdrawn"]
AdmissionPriorStatus = Literal["under_review", "waitlisted"]
AdmissionResolutionMode = Literal[
    "create_family_and_child",
    "reuse_family_create_child",
    "reuse_child",
]
AdmissionAllowedAction = Literal[
    "update",
    "submit",
    "start_review",
    "correct",
    "enter_waitlist",
    "reopen_review",
    "decline",
    "withdraw",
    "issue_offer",
    "withdraw_offer",
    "decline_offer",
    "accept_and_convert",
]
AdmissionEventReason = Literal[
    "create",
    "updated",
    "submitted",
    "review_started",
    "facts_changed",
    "waitlisted",
    "review_reopened",
    "provider_declined",
    "family_withdrawn",
    "offer_issued",
    "offer_withdrawn",
    "offer_declined",
    "offer_accepted",
]
AdmissionReceiptCommand = Literal[
    "admission.application.create",
    "admission.application.update",
    "admission.application.submit",
    "admission.application.review.start",
    "admission.application.correct",
    "admission.application.decline",
    "admission.application.withdraw",
    "admission.waitlist.enter",
    "admission.waitlist.reopen_review",
    "admission.offer.issue",
    "admission.offer.withdraw",
    "admission.offer.decline",
    "admission.offer.accept_and_convert",
]
AdmissionReceiptTarget = Literal[
    "admission_application",
    "admission_waitlist",
    "admission_offer",
]


class _ExactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AdmissionChildInput(_ExactModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date

class AdmissionContactInput(_ExactModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    relationship: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    telephone: str | None = Field(default=None, min_length=7, max_length=30)

    @field_validator("telephone")
    @classmethod
    def telephone_has_enough_digits(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if sum(character.isdigit() for character in value) < 7:
            raise ValueError("telephone must contain at least seven digits")
        return value

    @field_validator("email")
    @classmethod
    def email_has_safe_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        local, separator, domain = value.rpartition("@")
        if (
            not separator
            or not local
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
            or any(character.isspace() for character in value)
        ):
            raise ValueError("email must be a valid address")
        return value


class AdmissionPreferenceInput(_ExactModel):
    rank: int = Field(ge=1, le=20)
    facility_id: UUID
    program_id: UUID
    desired_start_date: date


class _AdmissionIntakeMutation(_ExactModel):
    child: AdmissionChildInput
    primary_contact: AdmissionContactInput
    internal_note: str | None = Field(default=None, max_length=2000)
    preferences: list[AdmissionPreferenceInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def ranks_and_lanes_are_unique(self) -> _AdmissionIntakeMutation:
        ranks = [preference.rank for preference in self.preferences]
        lanes = [
            (preference.facility_id, preference.program_id)
            for preference in self.preferences
        ]
        if len(ranks) != len(set(ranks)) or sorted(ranks) != list(
            range(1, len(ranks) + 1)
        ):
            raise ValueError("preference ranks must be contiguous and unique from one")
        if len(lanes) != len(set(lanes)):
            raise ValueError("preference facility/program lanes must be unique")
        return self


class AdmissionApplicationCreate(_AdmissionIntakeMutation):
    client_operation_id: UUID


class AdmissionApplicationUpdate(_AdmissionIntakeMutation):
    client_operation_id: UUID
    expected_application_version: int = Field(ge=1)


class AdmissionApplicationCorrect(AdmissionApplicationUpdate):
    pass


class AdmissionApplicationVersionCommand(_ExactModel):
    client_operation_id: UUID
    expected_application_version: int = Field(ge=1)
    reason_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9_.:-]*$",
    )


class AdmissionWaitlistEnter(AdmissionApplicationVersionCommand):
    facility_id: UUID
    program_id: UUID
    desired_start_date: date


class AdmissionWaitlistVersionCommand(AdmissionApplicationVersionCommand):
    expected_waitlist_version: int = Field(ge=1)


class AdmissionOfferIssue(AdmissionApplicationVersionCommand):
    expected_waitlist_version: int | None = Field(default=None, ge=1)
    facility_id: UUID
    program_id: UUID
    proposed_start_date: date
    respond_by_date: date | None = None

    @model_validator(mode="after")
    def response_date_is_not_before_start(self) -> AdmissionOfferIssue:
        if (
            self.respond_by_date is not None
            and self.respond_by_date > self.proposed_start_date
        ):
            raise ValueError("respond_by_date must not be after proposed_start_date")
        return self


class AdmissionOfferVersionCommand(AdmissionApplicationVersionCommand):
    expected_offer_version: int = Field(ge=1)


class AdmissionOfferAccept(AdmissionOfferVersionCommand):
    review_token: str = Field(min_length=1, max_length=4096)
    resolution_mode: AdmissionResolutionMode
    family_id: UUID | None = None
    expected_family_version: int | None = Field(default=None, ge=1)
    child_id: UUID | None = None
    expected_child_version: int | None = Field(default=None, ge=1)
    confirmed_distinct_person: bool = False
    distinct_person_reason: str | None = Field(
        default=None, min_length=1, max_length=500
    )

    @model_validator(mode="after")
    def resolution_identifiers_are_exact(self) -> AdmissionOfferAccept:
        if self.resolution_mode == "create_family_and_child":
            if any(
                value is not None
                for value in (
                    self.family_id,
                    self.expected_family_version,
                    self.child_id,
                    self.expected_child_version,
                )
            ):
                raise ValueError("create mode must not select canonical records")
            if self.confirmed_distinct_person and self.distinct_person_reason is None:
                raise ValueError(
                    "distinct_person_reason is required with distinct confirmation"
                )
            if not self.confirmed_distinct_person and self.distinct_person_reason:
                raise ValueError(
                    "distinct_person_reason requires distinct confirmation"
                )
            return self
        if self.confirmed_distinct_person or self.distinct_person_reason is not None:
            raise ValueError("distinct-person confirmation is only valid for create mode")
        if self.family_id is None or self.expected_family_version is None:
            raise ValueError("reuse mode requires family_id and expected_family_version")
        if self.resolution_mode == "reuse_family_create_child":
            if self.child_id is not None or self.expected_child_version is not None:
                raise ValueError("reuse-family mode must not select a child")
            return self
        if self.child_id is None or self.expected_child_version is None:
            raise ValueError("reuse-child mode requires child_id and expected_child_version")
        return self


AdmissionConversionMatchReason = Literal[
    "child_name_and_date_of_birth",
    "primary_contact_email",
    "primary_contact_telephone",
]


class AdmissionConversionFamilyCandidate(_ExactModel):
    id: UUID
    display_label: str
    version: int = Field(ge=1)
    status: Literal["pending", "active", "inactive", "archived"]
    match_reasons: list[AdmissionConversionMatchReason]


class AdmissionConversionChildCandidate(_ExactModel):
    id: UUID
    family_id: UUID
    display_label: str
    version: int = Field(ge=1)
    is_active: bool
    match_reasons: list[AdmissionConversionMatchReason]
    has_open_enrollment: bool


class AdmissionConversionCandidateReview(_ExactModel):
    application_id: UUID
    application_version: int = Field(ge=1)
    offer_id: UUID
    offer_version: int = Field(ge=1)
    families: list[AdmissionConversionFamilyCandidate]
    children: list[AdmissionConversionChildCandidate]
    review_token: str = Field(min_length=1, max_length=4096)
    expires_at: datetime


class AdmissionChildProjection(_ExactModel):
    first_name: str
    last_name: str
    date_of_birth: date


class AdmissionContactProjection(_ExactModel):
    first_name: str
    last_name: str
    relationship: str
    email: str | None
    telephone: str | None


class AdmissionPreferenceProjection(_ExactModel):
    id: UUID
    rank: int
    facility_id: UUID
    facility_name: str
    program_id: UUID
    program_name: str
    requested_start_date: date
    application_version: int


class AdmissionWaitlistProjection(_ExactModel):
    id: UUID
    status: AdmissionWaitlistStatus
    version: int
    facility_id: UUID
    facility_name: str
    program_id: UUID
    program_name: str
    requested_start_date: date
    priority_at: datetime
    position: int | None
    closure_reason: AdmissionWaitlistClosureReason | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class AdmissionOfferProjection(_ExactModel):
    id: UUID
    status: AdmissionOfferStatus
    version: int
    facility_id: UUID
    facility_name: str
    program_id: UUID
    program_name: str
    proposed_start_date: date
    respond_by_date: date | None
    prior_application_status: AdmissionPriorStatus
    issued_at: datetime
    withdrawn_at: datetime | None
    declined_at: datetime | None
    accepted_at: datetime | None


class AdmissionConversionProjection(_ExactModel):
    id: UUID
    resolution_mode: AdmissionResolutionMode
    family_id: UUID
    child_id: UUID
    enrollment_id: UUID
    converted_at: datetime


class AdmissionTimelineEvent(_ExactModel):
    id: UUID
    application_version: int
    command: str = Field(min_length=1, max_length=80)
    from_status: AdmissionApplicationStatus | None
    to_status: AdmissionApplicationStatus
    reason_code: AdmissionEventReason | None
    actor_user_id: UUID
    client_operation_id: UUID
    occurred_at: datetime


class AdmissionCommittedVersions(_ExactModel):
    application: int
    waitlist: int | None
    offer: int | None


class AdmissionReplayReceipt(_ExactModel):
    command_type: AdmissionReceiptCommand
    target_type: AdmissionReceiptTarget
    target_id: UUID
    committed_version: int = Field(ge=1)


class AdmissionDetail(_ExactModel):
    id: UUID
    organization_id: UUID
    reference: str = Field(pattern=r"^ADM-[0-9A-F]{12}$")
    source: AdmissionApplicationSource
    status: AdmissionApplicationStatus
    version: int
    child: AdmissionChildProjection
    contact: AdmissionContactProjection
    internal_note: str | None
    preferences: list[AdmissionPreferenceProjection]
    waitlist: AdmissionWaitlistProjection | None
    offer: AdmissionOfferProjection | None
    conversion: AdmissionConversionProjection | None
    timeline: list[AdmissionTimelineEvent]
    timeline_total: int = Field(ge=0)
    allowed_actions: list[AdmissionAllowedAction]
    committed_versions: AdmissionCommittedVersions
    replayed: bool = False
    replay_receipt: AdmissionReplayReceipt | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    review_started_at: datetime | None
    terminal_at: datetime | None


class AdmissionCurrentLane(_ExactModel):
    facility_id: UUID
    program_id: UUID


class AdmissionListItem(_ExactModel):
    id: UUID
    reference: str
    status: AdmissionApplicationStatus
    version: int
    source: AdmissionApplicationSource
    preference_count: int = Field(ge=0)
    submitted_at: datetime | None
    updated_at: datetime
    current_lane: AdmissionCurrentLane | None
    offer_status: AdmissionOfferStatus | None


class AdmissionDirectoryResponse(_ExactModel):
    items: list[AdmissionListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class AdmissionPipelineCounts(_ExactModel):
    draft: int = 0
    submitted: int = 0
    under_review: int = 0
    waitlisted: int = 0
    offered: int = 0
    accepted: int = 0
    declined: int = 0
    withdrawn: int = 0


class AdmissionWorkspaceLane(_ExactModel):
    status: AdmissionApplicationStatus
    count: int = Field(ge=0)
    applications: list[AdmissionListItem]


class AdmissionWorkspaceResponse(_ExactModel):
    counts: AdmissionPipelineCounts
    lanes: list[AdmissionWorkspaceLane]
    waitlist_lane_count: int = Field(ge=0)


class AdmissionWaitlistItem(_ExactModel):
    entry_id: UUID
    application_id: UUID
    application_reference: str
    status: AdmissionWaitlistStatus
    version: int
    facility_id: UUID
    program_id: UUID
    desired_start_date: date
    priority_at: datetime
    position: int


class AdmissionWaitlistResponse(_ExactModel):
    items: list[AdmissionWaitlistItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class AdmissionLaneProgram(_ExactModel):
    id: UUID
    name: str
    program_type: Literal["daycare", "out_of_school_care"]


class AdmissionLaneFacility(_ExactModel):
    id: UUID
    name: str
    programs: list[AdmissionLaneProgram]


class AdmissionLaneDirectory(_ExactModel):
    facilities: list[AdmissionLaneFacility]


class AdmissionConversionUnavailable(_ExactModel):
    code: Literal["admission_conversion_unavailable"] = (
        "admission_conversion_unavailable"
    )
    message: str
