"""Strict public contracts for the append-only 0033 CAD billing ledger."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

MAX_CAD_MINOR = 9_000_000_000_000
SYNTHETIC_BILLING_LABEL = "TEST/SYNTHETIC — NOT A REAL INVOICE"
PRIVATE_MANUAL_BILLING_LABEL = "PRIVATE/MANUAL — OFF-PLATFORM RECORD"
MANUAL_BILLING_REVIEW_ATTESTATION = (
    "I reviewed the private manual billing boundary and understand that CareSync will "
    "only record off-platform payments."
)
BillingRuntimeMode = Literal["shadow", "sandbox", "manual"]
BillingProvenanceLabel = Literal[
    "TEST/SYNTHETIC — NOT A REAL INVOICE",
    "PRIVATE/MANUAL — OFF-PLATFORM RECORD",
]
MinorAmount = Annotated[int, Field(ge=0, le=MAX_CAD_MINOR)]
PositiveMinorAmount = Annotated[int, Field(gt=0, le=MAX_CAD_MINOR)]
ShortText = Annotated[str, Field(min_length=1, max_length=80)]
BillingUnit = Literal["weekly_period", "biweekly_period", "monthly_period", "service_event"]
BillingFrequency = Literal["weekly", "biweekly", "monthly", "per_service"]
PaymentMethod = Literal["cash", "cheque", "e_transfer", "other"]
BillingReadinessStatus = Literal[
    "setup_ready",
    "needs_account",
    "needs_payer",
    "needs_current_enrollment",
    "needs_rate_plan",
    "needs_agreement",
    "agreement_scope_conflict",
    "needs_review",
]
BillingReadinessReasonCode = Literal[
    "billing_setup_ready",
    "billing_family_not_active",
    "billing_account_missing",
    "billing_payer_missing",
    "current_enrollment_missing",
    "applicable_rate_plan_missing",
    "billing_agreement_missing",
    "billing_agreement_enrollment_conflict",
    "billing_agreement_review_required",
    "billing_projection_inconsistent",
    "multiple_applicable_rate_plans",
]
BillingReadinessBatchWave = Literal[
    "account_payer",
    "rate_plan",
    "agreement",
    "ready",
    "manual_review",
]
BillingReadinessActionableWave = Literal[
    "account_payer",
    "rate_plan",
    "agreement",
]


class StrictBillingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StrictBillingCommand(StrictBillingModel):
    client_operation_id: UUID


class BillingProvenanceResponse(StrictBillingModel):
    """Mode/provenance pair shared by every record-bearing billing response."""

    billing_mode: BillingRuntimeMode = "sandbox"
    sandbox: StrictBool = True
    provenance_label: BillingProvenanceLabel = SYNTHETIC_BILLING_LABEL

    @model_validator(mode="after")
    def validate_provenance(self):
        manual = self.billing_mode == "manual"
        expected_label = (
            PRIVATE_MANUAL_BILLING_LABEL if manual else SYNTHETIC_BILLING_LABEL
        )
        if self.sandbox is manual or self.provenance_label != expected_label:
            raise ValueError("billing mode and provenance must describe the same boundary")
        return self


class BillingCapabilityResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    sandbox: StrictBool = True
    provenance_label: BillingProvenanceLabel = SYNTHETIC_BILLING_LABEL
    runtime_available: bool
    writes_available: StrictBool
    billing_mode: Literal["disabled", "shadow", "sandbox", "manual"]
    manual_activation_required: StrictBool = False
    manual_activated: StrictBool = False
    currency: Literal["CAD"] = "CAD"
    organization_timezone: str
    organization_local_date: date
    server_time: datetime
    processor_enabled: Literal[False] = False
    money_movement_enabled: Literal[False] = False
    automatic_issue_enabled: Literal[False] = False
    tax_advice_enabled: Literal[False] = False
    off_platform_payment_methods: list[PaymentMethod] = Field(
        default_factory=lambda: ["cash", "cheque", "e_transfer", "other"]
    )
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_provenance(self):
        manual = self.billing_mode == "manual"
        expected_label = (
            PRIVATE_MANUAL_BILLING_LABEL if manual else SYNTHETIC_BILLING_LABEL
        )
        if self.sandbox is manual or self.provenance_label != expected_label:
            raise ValueError("billing capability provenance is inconsistent")
        if self.manual_activated and not manual:
            raise ValueError("manual activation cannot be advertised outside manual mode")
        return self


class ActivateManualBillingCommand(StrictBillingModel):
    activation_policy_version: Literal["private_local_manual_billing_v1"]
    review_attestation: Literal[
        "I reviewed the private manual billing boundary and understand that CareSync will "
        "only record off-platform payments."
    ]


class BillingManualActivationResponse(StrictBillingModel):
    schema_version: Literal["0036"] = "0036"
    organization_id: UUID
    billing_mode: Literal["manual"]
    server_attested: StrictBool
    organization_allowlisted: StrictBool
    activated: StrictBool
    activation_policy_version: Literal["private_local_manual_billing_v1"] | None = None
    activated_by_user_id: UUID | None = None
    activated_at: datetime | None = None
    immutable: Literal[True] = True
    processor_enabled: Literal[False] = False
    money_movement_enabled: Literal[False] = False
    automatic_issue_enabled: Literal[False] = False
    delivery_enabled: Literal[False] = False
    tax_advice_enabled: Literal[False] = False


class BillingCommandReceiptResponse(BillingProvenanceResponse):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    client_operation_id: UUID
    command_type: Literal[
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
        "invoice_issue",
        "payment_record",
        "payment_allocate",
        "credit_issue",
    ]
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    result_kind: Literal[
        "billing_account",
        "billing_rate_plan",
        "billing_agreement",
        "billing_invoice",
        "billing_payment",
        "billing_allocation",
        "billing_credit",
    ]
    result_id: UUID
    committed_at: datetime
    exact_retry: bool
    action_path: str


class BillingAbsenceClaimResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    client_operation_id: UUID
    command_type: Literal[
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
        "invoice_issue",
        "payment_record",
        "payment_allocate",
        "credit_issue",
    ]
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    target_scope: str
    reason_code: Literal["operator_confirmed_not_committed"]
    finalized_at: datetime
    exact_retry: bool


class PrepareBillingCommand(StrictBillingModel):
    command_type: Literal[
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
        "invoice_issue",
        "payment_record",
        "payment_allocate",
        "credit_issue",
    ]
    request_payload: dict[str, object]


class BillingCommandPreparationResponse(BillingProvenanceResponse):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    client_operation_id: UUID
    command_type: Literal[
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
        "invoice_issue",
        "payment_record",
        "payment_allocate",
        "credit_issue",
    ]
    target_scope: str
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    prepared_at: datetime
    exact_retry: bool


class FinalizeBillingCommandAbsenceCommand(StrictBillingModel):
    expected_request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    reason_code: Literal["operator_confirmed_not_committed"]


class OpenBillingAccountCommand(StrictBillingCommand):
    family_id: UUID
    payer_guardian_id: UUID


class AssignBillingAccountPayerCommand(StrictBillingCommand):
    account_id: UUID
    payer_guardian_id: UUID
    expected_latest_payer_version_id: UUID
    expected_latest_payer_version_number: int = Field(ge=1)


class PublishRatePlanVersionCommand(StrictBillingCommand):
    rate_plan_id: UUID | None = None
    expected_latest_version_id: UUID | None = None
    expected_latest_version_number: int | None = Field(default=None, ge=1)
    code: Annotated[str | None, Field(default=None, min_length=1, max_length=40)]
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=160)]
    program_type: Literal["daycare", "out_of_school_care"] | None = None
    charge_kind: Literal["core_care"] | None = None
    age_group: Annotated[str | None, Field(default=None, min_length=1, max_length=100)]
    facility_id: UUID | None = None
    program_id: UUID | None = None
    billing_unit: BillingUnit
    unit_amount_minor: MinorAmount
    tax_rate_basis_points: Literal[0] = 0
    effective_from: date
    effective_until: date | None = None
    description: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]

    @model_validator(mode="after")
    def validate_plan_identity(self):
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("effective_until cannot precede effective_from")
        if self.rate_plan_id is None and (
            self.code is None
            or self.name is None
            or self.program_type is None
            or self.charge_kind != "core_care"
            or self.facility_id is None
            or self.program_id is None
        ):
            raise ValueError(
                "A new rate plan requires code, name, program_type, and core_care charge_kind"
            )
        if self.rate_plan_id is None and (
            self.expected_latest_version_id is not None
            or self.expected_latest_version_number is not None
        ):
            raise ValueError("A new rate plan cannot have an expected latest version")
        if self.rate_plan_id is not None and (
            self.expected_latest_version_id is None or self.expected_latest_version_number is None
        ):
            raise ValueError("A rate revision requires the expected latest version")
        if self.rate_plan_id is not None and any(
            value is not None
            for value in (
                self.code,
                self.name,
                self.program_type,
                self.charge_kind,
                self.age_group,
                self.facility_id,
                self.program_id,
            )
        ):
            raise ValueError("Existing rate plans retain their immutable care identity")
        return self


class EstablishBillingAgreementCommand(StrictBillingCommand):
    agreement_id: UUID | None = None
    expected_latest_version_id: UUID | None = None
    expected_latest_version_number: int | None = Field(default=None, ge=1)
    account_id: UUID
    child_id: UUID
    enrollment_id: UUID | None = None
    rate_plan_version_id: UUID
    billing_frequency: BillingFrequency
    effective_from: date
    effective_until: date | None = None
    family_amount_minor_per_unit: MinorAmount
    funding_amount_minor_per_unit: Literal[0] = 0
    reviewed: Literal[True]

    @model_validator(mode="after")
    def validate_agreement_identity(self):
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("effective_until cannot precede effective_from")
        if self.agreement_id is None and (
            self.expected_latest_version_id is not None
            or self.expected_latest_version_number is not None
        ):
            raise ValueError("A new agreement cannot have an expected latest version")
        if self.agreement_id is not None and (
            self.expected_latest_version_id is None or self.expected_latest_version_number is None
        ):
            raise ValueError("An agreement revision requires the expected latest version")
        return self


class InvoiceAgreementSelection(StrictBillingModel):
    agreement_id: UUID
    agreement_version_id: UUID


class IssueBillingInvoiceCommand(StrictBillingCommand):
    account_id: UUID
    issue_date: date
    due_date: date
    service_period_start: date
    service_period_end: date
    agreements: Annotated[list[InvoiceAgreementSelection], Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def validate_invoice_dates_and_lines(self):
        if self.due_date < self.issue_date:
            raise ValueError("due_date cannot precede issue_date")
        if self.service_period_end < self.service_period_start:
            raise ValueError("service_period_end cannot precede service_period_start")
        agreement_ids = [selection.agreement_id for selection in self.agreements]
        version_ids = [selection.agreement_version_id for selection in self.agreements]
        if len(agreement_ids) != len(set(agreement_ids)) or len(version_ids) != len(
            set(version_ids)
        ):
            raise ValueError("agreement and agreement-version selections must be unique")
        return self


class RecordBillingPaymentCommand(StrictBillingCommand):
    account_id: UUID
    payer_guardian_id: UUID
    amount_minor: PositiveMinorAmount
    method: PaymentMethod
    received_at: datetime
    external_reference: Annotated[str, Field(min_length=1, max_length=120)]
    memo: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]
    operator_confirmation_note: Annotated[
        str | None, Field(default=None, min_length=1, max_length=500)
    ]

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at requires a timezone")
        return value

    @model_validator(mode="after")
    def require_payment_evidence(self):
        if self.method in {"cash", "other"} and self.operator_confirmation_note is None:
            raise ValueError("Cash and other payments require operator_confirmation_note")
        return self


class AllocateBillingPaymentCommand(StrictBillingCommand):
    payment_id: UUID
    invoice_id: UUID
    amount_minor: PositiveMinorAmount
    expected_payment_unapplied_minor: MinorAmount
    expected_invoice_outstanding_minor: MinorAmount


class IssueBillingCreditCommand(StrictBillingCommand):
    invoice_id: UUID
    amount_minor: PositiveMinorAmount
    expected_invoice_outstanding_minor: MinorAmount
    reason_code: ShortText
    note: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]


class BillingOverviewResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    as_of: datetime
    account_count: int
    open_account_count: int
    issued_invoice_count: int
    outstanding_minor: MinorAmount
    settled_payments_minor: MinorAmount
    unapplied_payments_minor: MinorAmount
    credits_minor: MinorAmount


class BillingAccountSummary(StrictBillingModel):
    organization_id: UUID
    id: UUID
    family_id: UUID
    payer_guardian_id: UUID
    latest_payer_version_id: UUID
    latest_payer_version_number: int
    family_name: str
    account_number: str
    status: Literal["open"]
    currency: Literal["CAD"]
    opened_at: datetime
    invoiced_minor: MinorAmount
    allocated_minor: MinorAmount
    credits_minor: MinorAmount
    outstanding_minor: MinorAmount
    unapplied_minor: MinorAmount


class BillingAccountListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    items: list[BillingAccountSummary]
    total: int


class BillingAccountPayerVersionResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    billing_account_id: UUID
    family_id: UUID
    payer_guardian_id: UUID
    version_number: int
    assigned_by_user_id: UUID
    assigned_at: datetime


class BillingAccountPayerVersionListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    items: list[BillingAccountPayerVersionResponse]
    total: int


class BillingInvoiceLineResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    agreement_version_id: UUID
    child_id: UUID
    line_number: int
    description: str
    child_name: str
    rate_plan_name: str
    billing_unit: BillingUnit
    service_period_start: date
    service_period_end: date
    quantity: int
    gross_unit_amount_minor: MinorAmount
    funding_unit_amount_minor: MinorAmount
    unit_amount_minor: MinorAmount
    tax_rate_basis_points: int
    gross_subtotal_minor: MinorAmount
    funding_minor: MinorAmount
    subtotal_minor: MinorAmount
    tax_minor: MinorAmount
    total_minor: MinorAmount


class BillingInvoiceResponse(BillingProvenanceResponse):
    organization_id: UUID
    document_label: BillingProvenanceLabel = SYNTHETIC_BILLING_LABEL
    id: UUID
    billing_account_id: UUID
    family_id: UUID
    billing_account_payer_version_id: UUID
    payer_guardian_id: UUID
    invoice_number: str
    lifecycle_status: Literal[
        "open", "partially_settled", "settled_paid", "settled_credited", "settled_mixed"
    ]
    currency: Literal["CAD"]
    issue_date: date
    due_date: date
    service_period_start: date
    service_period_end: date
    family_name: str
    payer_name: str
    payer_email: str | None
    payer_address: str | None
    gross_subtotal_minor: MinorAmount
    funding_minor: MinorAmount
    subtotal_minor: MinorAmount
    tax_minor: MinorAmount
    total_minor: PositiveMinorAmount
    allocated_minor: MinorAmount
    credits_minor: MinorAmount
    outstanding_minor: MinorAmount
    issued_at: datetime
    lines: list[BillingInvoiceLineResponse] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_document_label(self):
        if self.document_label != self.provenance_label:
            raise ValueError("invoice document label must match its provenance")
        return self


class BillingInvoiceListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    items: list[BillingInvoiceResponse]
    total: int


class BillingInvoiceDocumentOrganizationResponse(StrictBillingModel):
    id: UUID
    display_name: str
    legal_name: str | None
    email: str | None
    phone: str | None


class BillingInvoiceDocumentPayerSnapshotResponse(StrictBillingModel):
    payer_version_id: UUID
    guardian_id: UUID
    name: str
    email: str | None
    address: str | None


class BillingInvoiceDocumentAllocationResponse(StrictBillingModel):
    id: UUID
    payment_id: UUID
    amount_minor: PositiveMinorAmount
    allocated_at: datetime


class BillingInvoiceDocumentCreditResponse(StrictBillingModel):
    id: UUID
    amount_minor: PositiveMinorAmount
    reason_code: str
    note: str | None
    issued_at: datetime


class BillingInvoiceDocumentSettlementResponse(StrictBillingModel):
    currency: Literal["CAD"] = "CAD"
    total_minor: PositiveMinorAmount
    allocated_minor: MinorAmount
    credits_minor: MinorAmount
    outstanding_minor: MinorAmount

    @model_validator(mode="after")
    def validate_conservation(self):
        if self.allocated_minor + self.credits_minor + self.outstanding_minor != self.total_minor:
            raise ValueError("invoice settlement amounts must conserve the invoice total")
        return self


class BillingInvoiceDocumentResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    billing_account_id: UUID
    family_id: UUID
    billing_account_payer_version_id: UUID
    payer_guardian_id: UUID
    invoice_number: str
    status: Literal["issued"]
    currency: Literal["CAD"]
    issue_date: date
    due_date: date
    service_period_start: date
    service_period_end: date
    family_name: str
    gross_subtotal_minor: MinorAmount
    funding_minor: MinorAmount
    subtotal_minor: MinorAmount
    tax_minor: MinorAmount
    total_minor: PositiveMinorAmount
    issued_at: datetime
    lines: list[BillingInvoiceLineResponse] = Field(default_factory=list)


class BillingInvoiceDocumentPreviewResponse(BillingProvenanceResponse):
    """Canonical read-only rendering source; never a delivery or money-movement command."""

    schema_version: Literal["0033"] = "0033"
    document_version: Literal["billing-invoice-preview-v1"] = "billing-invoice-preview-v1"
    organization_id: UUID
    invoice_id: UUID
    read_only: Literal[True] = True
    download_enabled: Literal[False] = False
    delivery_enabled: Literal[False] = False
    generated_at: datetime
    data_through_at: datetime
    data_through_realtime_sequence: int = Field(ge=0)
    organization: BillingInvoiceDocumentOrganizationResponse
    invoice: BillingInvoiceDocumentResponse
    payer_snapshot: BillingInvoiceDocumentPayerSnapshotResponse
    allocations: list[BillingInvoiceDocumentAllocationResponse] = Field(default_factory=list)
    credits: list[BillingInvoiceDocumentCreditResponse] = Field(default_factory=list)
    settlement: BillingInvoiceDocumentSettlementResponse
    canonical_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BillingPaymentResponse(BillingProvenanceResponse):
    organization_id: UUID
    id: UUID
    billing_account_id: UUID
    family_id: UUID
    payer_guardian_id: UUID
    payer_name: str
    payer_email: str | None
    lifecycle_status: Literal["settled", "partially_allocated", "fully_allocated"]
    method: PaymentMethod
    currency: Literal["CAD"]
    amount_minor: PositiveMinorAmount
    allocated_minor: MinorAmount
    unapplied_minor: MinorAmount
    external_reference: str
    memo: str | None
    operator_confirmation_note: str | None
    received_at: datetime
    recorded_at: datetime


class BillingPaymentListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    items: list[BillingPaymentResponse]
    total: int


class BillingAllocationResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    billing_account_id: UUID
    payment_id: UUID
    invoice_id: UUID
    amount_minor: PositiveMinorAmount
    allocated_by_user_id: UUID
    allocated_at: datetime
    client_operation_id: UUID
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BillingAllocationListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    items: list[BillingAllocationResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class BillingCreditResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    billing_account_id: UUID
    invoice_id: UUID
    status: Literal["issued"]
    currency: Literal["CAD"]
    amount_minor: PositiveMinorAmount
    reason_code: str
    note: str | None
    issued_by_user_id: UUID
    issued_at: datetime
    client_operation_id: UUID
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BillingCreditListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    items: list[BillingCreditResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class BillingRatePlanVersionResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    rate_plan_id: UUID
    version_number: int
    status: Literal["published"]
    billing_unit: BillingUnit
    unit_amount_minor: MinorAmount
    tax_rate_basis_points: int
    currency: Literal["CAD"]
    effective_from: date
    effective_until: date | None
    description: str | None
    published_at: datetime


class BillingRatePlanResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    code: str
    name: str
    program_type: Literal["daycare", "out_of_school_care"]
    charge_kind: Literal["core_care"]
    age_group: str | None
    facility_id: UUID | None
    program_id: UUID | None
    created_at: datetime
    latest_version: BillingRatePlanVersionResponse
    versions: list[BillingRatePlanVersionResponse] = Field(default_factory=list)


class BillingRatePlanListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    items: list[BillingRatePlanResponse]
    total: int


class BillingAgreementVersionResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    agreement_id: UUID
    rate_plan_version_id: UUID
    version_number: int
    billing_frequency: BillingFrequency
    family_amount_minor_per_unit: MinorAmount
    funding_amount_minor_per_unit: MinorAmount
    effective_from: date
    effective_until: date | None
    review_status: Literal["reviewed"]
    reviewed_at: datetime


class BillingAgreementResponse(StrictBillingModel):
    organization_id: UUID
    id: UUID
    billing_account_id: UUID
    family_id: UUID
    child_id: UUID
    child_name: str
    enrollment_id: UUID | None
    facility_id: UUID | None
    created_at: datetime
    latest_version: BillingAgreementVersionResponse
    versions: list[BillingAgreementVersionResponse] = Field(default_factory=list)


class BillingAgreementListResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    items: list[BillingAgreementResponse]
    total: int


class BillingAccountDetailResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    currency: Literal["CAD"] = "CAD"
    account: BillingAccountSummary
    payer_versions: list[BillingAccountPayerVersionResponse]
    invoices: list[BillingInvoiceResponse]
    payments: list[BillingPaymentResponse]
    agreements: list[BillingAgreementResponse]


class BillingSourceGuardian(StrictBillingModel):
    organization_id: UUID
    id: UUID
    family_id: UUID
    first_name: str
    last_name: str
    email: str
    cell_phone: str


class BillingSourceChild(StrictBillingModel):
    organization_id: UUID
    id: UUID
    family_id: UUID
    first_name: str
    last_name: str
    age_group: str | None
    enrollment_id: UUID | None
    facility_id: UUID | None
    program_id: UUID | None
    program_type: Literal["daycare", "out_of_school_care"] | None


class BillingSourceFamily(StrictBillingModel):
    organization_id: UUID
    id: UUID
    name: str
    status: Literal["active"]
    guardians: list[BillingSourceGuardian]
    children: list[BillingSourceChild]


class BillingSourceProgram(StrictBillingModel):
    organization_id: UUID
    facility_id: UUID
    facility_name: str
    program_id: UUID
    program_name: str
    program_type: Literal["daycare", "out_of_school_care"]
    minimum_age_months: int | None
    maximum_age_months: int | None


class BillingSourceOptionsResponse(StrictBillingModel):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    items: list[BillingSourceFamily]
    programs: list[BillingSourceProgram]
    total: int
    limit: int
    offset: int


class BillingCollectionPage(StrictBillingModel):
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    returned: int = Field(ge=0)
    total: int = Field(ge=0)
    has_more: bool
    next_offset: int | None = Field(default=None, ge=0)


class BillingWorkspacePaging(StrictBillingModel):
    snapshot_token: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    accounts: BillingCollectionPage
    payer_versions: BillingCollectionPage
    invoices: BillingCollectionPage
    payments: BillingCollectionPage
    rate_plans: BillingCollectionPage
    agreements: BillingCollectionPage
    allocations: BillingCollectionPage
    credits: BillingCollectionPage


class BillingWorkspaceResponse(BillingProvenanceResponse):
    schema_version: Literal["0033"] = "0033"
    organization_id: UUID
    complete: bool
    canonical_collection_limit: int = Field(ge=1, le=500)
    generated_at: datetime
    data_through_realtime_sequence: int = Field(ge=0)
    paging: BillingWorkspacePaging
    overview: BillingOverviewResponse
    accounts: BillingAccountListResponse
    payer_versions: BillingAccountPayerVersionListResponse
    invoices: BillingInvoiceListResponse
    payments: BillingPaymentListResponse
    rate_plans: BillingRatePlanListResponse
    agreements: BillingAgreementListResponse
    allocations: BillingAllocationListResponse
    credits: BillingCreditListResponse


class BillingReadinessCounts(StrictBillingModel):
    total: int = Field(ge=0)
    setup_ready: int = Field(ge=0)
    needs_account: int = Field(ge=0)
    needs_payer: int = Field(ge=0)
    needs_current_enrollment: int = Field(ge=0)
    needs_rate_plan: int = Field(ge=0)
    needs_agreement: int = Field(ge=0)
    agreement_scope_conflict: int = Field(ge=0)
    needs_review: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self):
        resolved = (
            self.setup_ready
            + self.needs_account
            + self.needs_payer
            + self.needs_current_enrollment
            + self.needs_rate_plan
            + self.needs_agreement
            + self.agreement_scope_conflict
            + self.needs_review
        )
        if resolved != self.total:
            raise ValueError("billing readiness counts must reconcile to total")
        return self


class BillingReadinessItem(StrictBillingModel):
    family_id: UUID
    family_name: str
    child_id: UUID
    child_name: str
    enrollment_id: UUID | None
    facility_id: UUID | None
    program_id: UUID | None
    billing_account_id: UUID | None
    payer_guardian_id: UUID | None
    rate_plan_id: UUID | None
    rate_plan_version_id: UUID | None
    agreement_id: UUID | None
    agreement_version_id: UUID | None
    status: BillingReadinessStatus
    reason_codes: Annotated[
        list[BillingReadinessReasonCode],
        Field(min_length=1, max_length=1),
    ]
    action_path: Annotated[str, Field(min_length=1, max_length=500)]

    @field_validator("action_path")
    @classmethod
    def require_local_action_path(cls, value: str) -> str:
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "\\" in value
            or "#" in value
            or any(ord(character) < 32 for character in value)
            or any(segment == ".." for segment in value.split("?")[0].split("/"))
        ):
            raise ValueError("billing readiness action_path must be a local safe path")
        return value


class BillingReadinessResponse(StrictBillingModel):
    schema_version: Literal["billing-projection-v1"] = "billing-projection-v1"
    organization_id: UUID
    generated_at: datetime
    as_of_date: date
    data_through_realtime_sequence: int = Field(ge=0)
    currency: Literal["CAD"] = "CAD"
    counts: BillingReadinessCounts
    items: list[BillingReadinessItem]

    @model_validator(mode="after")
    def validate_items(self):
        if len(self.items) != self.counts.total:
            raise ValueError("billing readiness items must reconcile to total")
        return self


class BillingReadinessBatchAffectedChild(StrictBillingModel):
    family_id: UUID
    family_name: Annotated[str, Field(min_length=1, max_length=255)]
    child_id: UUID
    child_name: Annotated[str, Field(min_length=1, max_length=255)]
    enrollment_id: UUID | None


class BillingReadinessBatchPayerOption(StrictBillingModel):
    guardian_id: UUID
    display_name: Annotated[str, Field(min_length=1, max_length=201)]
    is_primary: StrictBool


class BillingReadinessBatchRatePlanOption(StrictBillingModel):
    rate_plan_id: UUID
    code: Annotated[str, Field(min_length=1, max_length=40)]
    name: Annotated[str, Field(min_length=1, max_length=160)]
    age_group: Annotated[str | None, Field(default=None, min_length=1, max_length=100)]
    latest_version_id: UUID | None
    latest_version_number: int | None = Field(default=None, ge=1)
    latest_billing_unit: BillingUnit | None = None
    latest_unit_amount_minor: int | None = Field(
        default=None,
        ge=0,
        le=MAX_CAD_MINOR,
    )
    latest_effective_from: date | None = None
    latest_effective_until: date | None = None
    revision_can_resolve_as_of_date: StrictBool

    @model_validator(mode="after")
    def validate_latest_version_pair(self):
        if (self.latest_version_id is None) != (self.latest_version_number is None):
            raise ValueError("latest rate-plan version id and number must be paired")
        version_terms = (
            self.latest_billing_unit,
            self.latest_unit_amount_minor,
            self.latest_effective_from,
        )
        if self.latest_version_id is None and any(
            value is not None for value in version_terms
        ):
            raise ValueError("missing rate versions cannot expose version terms")
        if self.latest_version_id is not None and any(
            value is None for value in version_terms
        ):
            raise ValueError("latest rate versions require complete terms")
        return self


class BillingReadinessBatchPlanGroup(StrictBillingModel):
    group_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    wave: BillingReadinessBatchWave
    readiness_status: BillingReadinessStatus
    reason_codes: Annotated[
        list[BillingReadinessReasonCode],
        Field(min_length=1, max_length=1),
    ]
    actionable: StrictBool
    block_code: Annotated[str | None, Field(default=None, min_length=1, max_length=80)]
    suggested_command_type: Literal[
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
    ] | None
    family_id: UUID | None
    family_name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    billing_account_id: UUID | None
    latest_payer_version_id: UUID | None
    latest_payer_version_number: int | None = Field(default=None, ge=1)
    facility_id: UUID | None
    facility_name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    program_id: UUID | None
    program_name: Annotated[str | None, Field(default=None, min_length=1, max_length=150)]
    program_type: Literal["daycare", "out_of_school_care"] | None
    age_group: Annotated[str | None, Field(default=None, min_length=1, max_length=100)]
    rate_plan_id: UUID | None
    rate_plan_version_id: UUID | None
    rate_billing_unit: BillingUnit | None = None
    rate_unit_amount_minor: int | None = Field(
        default=None,
        ge=0,
        le=MAX_CAD_MINOR,
    )
    rate_effective_from: date | None = None
    rate_effective_until: date | None = None
    agreement_effective_from_min: date | None = None
    agreement_effective_until_max: date | None = None
    agreement_effective_until_required: StrictBool = False
    affected_count: int = Field(ge=1)
    affected_membership_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    affected_children: Annotated[
        list[BillingReadinessBatchAffectedChild],
        Field(min_length=1, max_length=25),
    ]
    affected_children_truncated: StrictBool
    payer_options: Annotated[list[BillingReadinessBatchPayerOption], Field(max_length=50)]
    rate_plan_options: Annotated[
        list[BillingReadinessBatchRatePlanOption],
        Field(max_length=50),
    ]
    action_path: Annotated[str, Field(min_length=1, max_length=500)]

    @model_validator(mode="after")
    def validate_group_contract(self):
        if (self.latest_payer_version_id is None) != (
            self.latest_payer_version_number is None
        ):
            raise ValueError("latest payer version id and number must be paired")
        if self.actionable != (self.suggested_command_type is not None):
            raise ValueError("actionable groups require exactly one suggested command")
        if self.actionable and self.block_code is not None:
            raise ValueError("actionable groups cannot carry a block code")
        if not self.actionable and self.block_code is None and self.wave != "ready":
            raise ValueError("non-ready blocked groups require a block code")
        if self.affected_count < len(self.affected_children):
            raise ValueError("affected count cannot be smaller than its bounded preview")
        if self.affected_children_truncated != (
            self.affected_count > len(self.affected_children)
        ):
            raise ValueError("affected-child truncation flag must reconcile")
        rate_fields = (
            self.rate_billing_unit,
            self.rate_unit_amount_minor,
            self.rate_effective_from,
        )
        if any(value is not None for value in rate_fields) and any(
            value is None for value in rate_fields
        ):
            raise ValueError("selected rate version terms must be complete")
        if self.agreement_effective_until_required != (
            self.agreement_effective_until_max is not None
        ):
            raise ValueError("agreement end-date requirement must match its upper bound")
        return self

    @field_validator("action_path")
    @classmethod
    def require_local_group_action_path(cls, value: str) -> str:
        return BillingReadinessItem.require_local_action_path(value)


class BillingReadinessBatchWaveCounts(StrictBillingModel):
    total: int = Field(ge=0)
    account_payer: int = Field(ge=0)
    rate_plan: int = Field(ge=0)
    agreement: int = Field(ge=0)
    ready: int = Field(ge=0)
    manual_review: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_total(self):
        if self.total != (
            self.account_payer
            + self.rate_plan
            + self.agreement
            + self.ready
            + self.manual_review
        ):
            raise ValueError("billing readiness batch wave counts must reconcile")
        return self


class BillingReadinessBatchPlanResponse(StrictBillingModel):
    schema_version: Literal["billing-readiness-batch-plan-v1"] = (
        "billing-readiness-batch-plan-v1"
    )
    organization_id: UUID
    generated_at: datetime
    as_of_date: date
    data_through_realtime_sequence: int = Field(ge=0)
    snapshot_token: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    read_only: Literal[True] = True
    apply_available: StrictBool
    manual_activation_required: StrictBool
    counts: BillingReadinessBatchWaveCounts
    page: BillingCollectionPage
    items: list[BillingReadinessBatchPlanGroup]

    @model_validator(mode="after")
    def validate_page(self):
        if len(self.items) != self.page.returned:
            raise ValueError("batch-plan items must reconcile to the page")
        return self


class BillingReadinessBatchPreviewSelection(StrictBillingModel):
    group_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    client_operation_id: UUID
    payer_guardian_id: UUID | None = None
    rate_plan_id: UUID | None = None
    code: Annotated[str | None, Field(default=None, min_length=1, max_length=40)]
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=160)]
    billing_unit: BillingUnit | None = None
    unit_amount_minor: int | None = Field(default=None, ge=0, le=MAX_CAD_MINOR)
    effective_from: date | None = None
    effective_until: date | None = None
    description: Annotated[str | None, Field(default=None, min_length=1, max_length=500)]
    billing_frequency: BillingFrequency | None = None
    family_amount_minor_per_unit: int | None = Field(
        default=None,
        ge=0,
        le=MAX_CAD_MINOR,
    )


class PreviewBillingReadinessBatchCommand(StrictBillingModel):
    snapshot_token: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    wave: BillingReadinessActionableWave
    selections: Annotated[
        list[BillingReadinessBatchPreviewSelection],
        Field(min_length=1, max_length=100),
    ]

    @model_validator(mode="after")
    def validate_wave_inputs(self):
        group_ids = [selection.group_id for selection in self.selections]
        operation_ids = [selection.client_operation_id for selection in self.selections]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("batch preview group selections must be unique")
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("batch preview operation ids must be unique")
        selected_rate_plan_ids = [
            selection.rate_plan_id
            for selection in self.selections
            if selection.rate_plan_id is not None
        ]
        if len(selected_rate_plan_ids) != len(set(selected_rate_plan_ids)):
            raise ValueError(
                "one preview cannot revise the same rate plan more than once"
            )
        new_rate_codes = [
            selection.code.casefold()
            for selection in self.selections
            if selection.rate_plan_id is None and selection.code is not None
        ]
        if len(new_rate_codes) != len(set(new_rate_codes)):
            raise ValueError("new rate-plan codes must be unique within a preview")
        for selection in self.selections:
            rate_values = (
                selection.rate_plan_id,
                selection.code,
                selection.name,
                selection.billing_unit,
                selection.unit_amount_minor,
                selection.description,
            )
            agreement_values = (
                selection.billing_frequency,
                selection.family_amount_minor_per_unit,
            )
            if self.wave == "account_payer":
                if (
                    selection.payer_guardian_id is None
                    or any(value is not None for value in rate_values)
                    or any(value is not None for value in agreement_values)
                    or selection.effective_from is not None
                    or selection.effective_until is not None
                ):
                    raise ValueError(
                        "account/payer preview requires only payer_guardian_id"
                    )
            elif self.wave == "rate_plan":
                if (
                    selection.payer_guardian_id is not None
                    or any(value is not None for value in agreement_values)
                    or selection.billing_unit is None
                    or selection.unit_amount_minor is None
                    or selection.effective_from is None
                ):
                    raise ValueError(
                        "rate-plan preview requires rate terms and no payer/agreement inputs"
                    )
                if selection.rate_plan_id is None:
                    if selection.code is None or selection.name is None:
                        raise ValueError("new rate plans require code and name")
                elif selection.code is not None or selection.name is not None:
                    raise ValueError(
                        "existing rate plans retain their immutable code and name"
                    )
            elif (
                selection.payer_guardian_id is not None
                or any(value is not None for value in rate_values)
                or selection.billing_frequency is None
                or selection.family_amount_minor_per_unit is None
                or selection.effective_from is None
            ):
                raise ValueError(
                    "agreement preview requires agreement terms and no payer/rate inputs"
                )
            if (
                selection.effective_from is not None
                and selection.effective_until is not None
                and selection.effective_until < selection.effective_from
            ):
                raise ValueError("effective_until cannot precede effective_from")
        return self


class BillingReadinessBatchPrepareRequest(StrictBillingModel):
    command_type: Literal[
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
    ]
    request_payload: dict[str, object]


class BillingReadinessBatchPreviewIntent(StrictBillingModel):
    sequence: int = Field(ge=1, le=100)
    group_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    label: Annotated[str, Field(min_length=1, max_length=255)]
    command_type: Literal[
        "account_open",
        "account_payer_assign",
        "rate_version_publish",
        "agreement_establish",
    ]
    client_operation_id: UUID
    target_scope: Annotated[str, Field(min_length=1, max_length=100)]
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    request_payload: dict[str, object]
    prepare_request: BillingReadinessBatchPrepareRequest
    execute_path: Annotated[str, Field(min_length=1, max_length=500)]
    affected_count: int = Field(ge=1)

    @field_validator("execute_path")
    @classmethod
    def require_local_execute_path(cls, value: str) -> str:
        if not value.startswith("/api/v1/billing/") or "//" in value or "\\" in value:
            raise ValueError("batch preview execute_path must be a local billing API path")
        return value


class BillingReadinessBatchPreviewBlock(StrictBillingModel):
    group_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    code: Annotated[str, Field(min_length=1, max_length=80)]
    message: Annotated[str, Field(min_length=1, max_length=255)]


class BillingReadinessBatchPreviewResponse(StrictBillingModel):
    schema_version: Literal["billing-readiness-batch-preview-v1"] = (
        "billing-readiness-batch-preview-v1"
    )
    organization_id: UUID
    snapshot_token: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    wave: BillingReadinessActionableWave
    previewed_at: datetime
    data_through_realtime_sequence: int = Field(ge=0)
    read_only: Literal[True] = True
    apply_available: StrictBool
    manual_activation_required: StrictBool
    requires_sequential_execution: Literal[True] = True
    requires_canonical_refresh_after_each_intent: Literal[True] = True
    intents: Annotated[list[BillingReadinessBatchPreviewIntent], Field(max_length=100)]
    blocked: Annotated[list[BillingReadinessBatchPreviewBlock], Field(max_length=100)]

    @model_validator(mode="after")
    def validate_outcomes(self):
        if not self.intents and not self.blocked:
            raise ValueError("batch preview requires at least one outcome")
        group_ids = [intent.group_id for intent in self.intents] + [
            block.group_id for block in self.blocked
        ]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("batch preview group outcomes must be unique")
        if [intent.sequence for intent in self.intents] != list(
            range(1, len(self.intents) + 1)
        ):
            raise ValueError("batch preview intent sequence must be contiguous")
        return self


class BillingFamilyIdentityResponse(StrictBillingModel):
    id: UUID
    name: str
    status: Literal["pending", "active", "inactive", "archived"]


class BillingFamilyAccountResponse(StrictBillingModel):
    id: UUID
    account_number: str
    status: Literal["open"]
    payer_guardian_id: UUID
    payer_name: str


class BillingFamilyInvoiceSummary(StrictBillingModel):
    invoice_count: int = Field(ge=0)
    open_invoice_count: int = Field(ge=0)
    settled_invoice_count: int = Field(ge=0)
    total_minor: MinorAmount
    allocated_minor: MinorAmount
    credits_minor: MinorAmount
    outstanding_minor: MinorAmount

    @model_validator(mode="after")
    def validate_settlement(self):
        if self.open_invoice_count + self.settled_invoice_count != self.invoice_count:
            raise ValueError("invoice lifecycle counts must reconcile")
        if self.allocated_minor + self.credits_minor + self.outstanding_minor != self.total_minor:
            raise ValueError("family invoice settlement amounts must conserve invoice total")
        return self


class BillingFamilyPaymentSummary(StrictBillingModel):
    payment_count: int = Field(ge=0)
    recorded_minor: MinorAmount
    allocated_minor: MinorAmount
    unapplied_minor: MinorAmount

    @model_validator(mode="after")
    def validate_settlement(self):
        if self.allocated_minor + self.unapplied_minor != self.recorded_minor:
            raise ValueError("family payment amounts must conserve recorded payments")
        return self


class BillingChildChargeAttribution(StrictBillingModel):
    """Invoice-line attribution only; payment settlement remains family/invoice scoped."""

    invoice_count: int = Field(ge=0)
    line_count: int = Field(ge=0)
    gross_minor: MinorAmount
    funding_minor: MinorAmount
    subtotal_minor: MinorAmount
    tax_minor: MinorAmount
    total_minor: MinorAmount

    @model_validator(mode="after")
    def validate_charges(self):
        if self.gross_minor != self.funding_minor + self.subtotal_minor:
            raise ValueError("child charge attribution gross amount must reconcile")
        if self.total_minor != self.subtotal_minor + self.tax_minor:
            raise ValueError("child charge attribution total must reconcile")
        return self


class BillingFamilyChildFinanceResponse(StrictBillingModel):
    child_id: UUID
    child_name: str
    is_active: StrictBool
    current_enrollment_id: UUID | None
    readiness_status: BillingReadinessStatus | None
    charge_attribution: BillingChildChargeAttribution


class BillingFamilyFinanceSummaryResponse(StrictBillingModel):
    schema_version: Literal["billing-projection-v1"] = "billing-projection-v1"
    organization_id: UUID
    generated_at: datetime
    as_of_date: date
    data_through_realtime_sequence: int = Field(ge=0)
    currency: Literal["CAD"] = "CAD"
    family: BillingFamilyIdentityResponse
    account: BillingFamilyAccountResponse | None
    invoice_summary: BillingFamilyInvoiceSummary
    payment_summary: BillingFamilyPaymentSummary
    children: list[BillingFamilyChildFinanceResponse]
