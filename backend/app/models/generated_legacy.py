"""Generated compatibility mappings. Do not edit by hand."""

from typing import Optional
import datetime
import decimal
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Double, ForeignKeyConstraint, Index, Integer, JSON, Numeric, PrimaryKeyConstraint, String, Table, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class ChildAiMessages(Base):
    __tablename__ = 'child_ai_messages'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_0cc5e85e4660140db5abe6afddf'),
        Index('IDX_263438131ec275a5e4fdda76ff', 'child_id', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    child_id: Mapped[str] = mapped_column(String, nullable=False)
    organization_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    image_base64: Mapped[Optional[str]] = mapped_column(Text)
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(50))
    images_json: Mapped[Optional[str]] = mapped_column(Text)


class Letterheads(Base):
    __tablename__ = 'letterheads'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_5c311a586c089dc4f93c852cdc1'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    letter_body: Mapped[str] = mapped_column(Text, nullable=False)
    signature_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'typed'::character varying"))
    theme: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'modern_teal'::character varying"))
    accent_color: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'#0d9488'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    date: Mapped[Optional[str]] = mapped_column(String(100))
    ref_no: Mapped[Optional[str]] = mapped_column(String(100))
    subject: Mapped[Optional[str]] = mapped_column(String(255))
    recipient_name: Mapped[Optional[str]] = mapped_column(String(255))
    recipient_title: Mapped[Optional[str]] = mapped_column(String(255))
    recipient_org: Mapped[Optional[str]] = mapped_column(String(255))
    recipient_address: Mapped[Optional[str]] = mapped_column(Text)
    signatory_name: Mapped[Optional[str]] = mapped_column(String(255))
    signatory_title: Mapped[Optional[str]] = mapped_column(String(255))
    signature_text: Mapped[Optional[str]] = mapped_column(String(255))
    signature_url: Mapped[Optional[str]] = mapped_column(Text)
    footer_text: Mapped[Optional[str]] = mapped_column(Text)


class MilestoneTemplates(Base):
    __tablename__ = 'milestone_templates'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_21f0bf56686b846d2b2e3a40ed8'),
        Index('IDX_42c33b73e9ae080335375eb2c9', 'age_group'),
        Index('IDX_9ee235d9c06a873b374245f6fd', 'domain'),
        Index('IDX_c5b77bdb4b692ae543d3828f4b', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    age_group: Mapped[str] = mapped_column(String(50), nullable=False)
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    is_system_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    description: Mapped[Optional[str]] = mapped_column(Text)
    typical_age_months_start: Mapped[Optional[int]] = mapped_column(Integer)
    typical_age_months_end: Mapped[Optional[int]] = mapped_column(Integer)


class Organizations(Base):
    __tablename__ = 'organizations'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_6b031fcd0863e3f6b44230163f9'),
        UniqueConstraint('email', name='UQ_4ad920935f4d4eb73fc58b40f72'),
        Index('IDX_4ad920935f4d4eb73fc58b40f7', 'email'),
        Index('IDX_601f0fb2b032df8d8bc368c608', 'license_number'),
        Index('IDX_9b7ca6d30b94fef571cff87688', 'name'),
        Index('IDX_f3770f157bd77d83ab022e92fc', 'status')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'daycare'::character varying"))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'pending'::character varying"))
    primary_contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    street_address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    province: Mapped[str] = mapped_column(String(50), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'Canada'::character varying"))
    license_number: Mapped[str] = mapped_column(String(100), nullable=False)
    licensed_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_time: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'07:00'::character varying"))
    closing_time: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'18:00'::character varying"))
    age_groups_served: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'::text"))
    accreditation_status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'none'::character varying"))
    programs_offered: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'::text"))
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'America/Edmonton'::character varying"))
    subscription_plan: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'trial'::character varying"))
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    license_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    secondary_contact_name: Mapped[Optional[str]] = mapped_column(String(255))
    secondary_contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    secondary_contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    business_number: Mapped[Optional[str]] = mapped_column(String(100))
    tax_id: Mapped[Optional[str]] = mapped_column(String(100))
    insurance_provider: Mapped[Optional[str]] = mapped_column(String(255))
    insurance_policy_number: Mapped[Optional[str]] = mapped_column(String(100))
    insurance_expiry_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    accreditation_body: Mapped[Optional[str]] = mapped_column(String(255))
    accreditation_expiry_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    description: Mapped[Optional[str]] = mapped_column(Text)
    billing_email: Mapped[Optional[str]] = mapped_column(String(255))
    social_media: Mapped[Optional[str]] = mapped_column(Text)
    subscription_expires_at: Mapped[Optional[datetime.date]] = mapped_column(Date)
    trial_ends_at: Mapped[Optional[datetime.date]] = mapped_column(Date)
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    notification_preferences: Mapped[Optional[str]] = mapped_column(Text)
    system_preferences: Mapped[Optional[str]] = mapped_column(Text)

    activity_logs: Mapped[list['ActivityLogs']] = relationship('ActivityLogs', back_populates='organization')
    claim_generation_configurations: Mapped[list['ClaimGenerationConfigurations']] = relationship('ClaimGenerationConfigurations', back_populates='organization')
    daycare_pricing: Mapped[list['DaycarePricing']] = relationship('DaycarePricing', back_populates='organization')
    families: Mapped[list['Families']] = relationship('Families', back_populates='organization')
    funding_sources: Mapped[list['FundingSources']] = relationship('FundingSources', back_populates='organization')
    generated_claim_reports: Mapped[list['GeneratedClaimReports']] = relationship('GeneratedClaimReports', back_populates='organization')
    imported_claims: Mapped[list['ImportedClaims']] = relationship('ImportedClaims', back_populates='organization')
    invoice_templates: Mapped[list['InvoiceTemplates']] = relationship('InvoiceTemplates', back_populates='organization')
    provider_settings: Mapped['ProviderSettings'] = relationship('ProviderSettings', uselist=False, back_populates='organization')
    users: Mapped[list['Users']] = relationship('Users', back_populates='organization')
    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='organization')
    organization_members: Mapped[list['OrganizationMembers']] = relationship('OrganizationMembers', back_populates='organization')
    rate_schedules: Mapped[list['RateSchedules']] = relationship('RateSchedules', back_populates='organization')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='organization')
    recurring_invoices: Mapped[list['RecurringInvoices']] = relationship('RecurringInvoices', back_populates='organization')
    credit_notes: Mapped[list['CreditNotes']] = relationship('CreditNotes', back_populates='organization')


class Permissions(Base):
    __tablename__ = 'permissions'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_920331560282b8bd21bb02290df'),
        UniqueConstraint('name', name='UQ_48ce552495d14eae9b187bb6716'),
        Index('IDX_48ce552495d14eae9b187bb671', 'name')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    role: Mapped[list['Roles']] = relationship('Roles', secondary='role_permissions', back_populates='permission')


class Roles(Base):
    __tablename__ = 'roles'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_c1433d71a4838793a49dcad46ab'),
        UniqueConstraint('name', name='UQ_648e3f5447f725579d7d4ffdfb7')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    permission: Mapped[list['Permissions']] = relationship('Permissions', secondary='role_permissions', back_populates='role')
    users: Mapped[list['Users']] = relationship('Users', back_populates='role')


class ScheduledAttendance(Base):
    __tablename__ = 'scheduled_attendance'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_f9af391b032e6caa5abb106fa47'),
        Index('IDX_1e9d8d3bef2fd7d044e15ef864', 'date'),
        Index('IDX_515c19618180e3285411a9ccc9', 'batch_id'),
        Index('IDX_8094cee7caeaf45d065c378650', 'child_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    child_id: Mapped[str] = mapped_column(String(255), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    startTime1: Mapped[Optional[str]] = mapped_column(String(10))
    endTime1: Mapped[Optional[str]] = mapped_column(String(10))
    startTime2: Mapped[Optional[str]] = mapped_column(String(10))
    endTime2: Mapped[Optional[str]] = mapped_column(String(10))
    source_claim_batch_id: Mapped[Optional[str]] = mapped_column(String(100))


class UniversalPrompts(Base):
    __tablename__ = 'universal_prompts'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='PK_737191551b9f425f79d13f7cf76'),
        UniqueConstraint('organization_id', name='UQ_d032945d926278e8ea55a7a3e3b')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[str] = mapped_column(String, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))


class ActivityLogs(Base):
    __tablename__ = 'activity_logs'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_f2a5695f730cbe9bf16eeb74342'),
        PrimaryKeyConstraint('id', name='PK_f25287b6140c5ba18d38776a796'),
        Index('IDX_22a8ceffff1ef5bcfdecfe25d3', 'user_id', 'created_at'),
        Index('IDX_4c9eee65dd51f3bdb1cc5440f0', 'activity_type', 'created_at'),
        Index('IDX_a78aef7d92c030d5c80583875c', 'organization_id', 'created_at')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    user_name: Mapped[Optional[str]] = mapped_column(String(255))
    user_email: Mapped[Optional[str]] = mapped_column(String(255))
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    entity_name: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='activity_logs')


class ClaimGenerationConfigurations(Base):
    __tablename__ = 'claim_generation_configurations'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_6deb456acde136a2bd8b96305bd'),
        PrimaryKeyConstraint('id', name='PK_adc2fc145d61be074c8cc4de817')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    operating_hours: Mapped[decimal.Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    hour_tiers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    school_break_periods: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    behavioral_profiles: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='claim_generation_configurations')


class DaycarePricing(Base):
    __tablename__ = 'daycare_pricing'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_d6c64e36db42b6e491cb33710ad'),
        PrimaryKeyConstraint('id', name='PK_aa034ab856eeeed6bd4a9bca16d'),
        Index('IDX_d6c64e36db42b6e491cb33710a', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    rate_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'daily'::character varying"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    infant_full_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    infant_half_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    infant_hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    toddler_full_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    toddler_half_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    toddler_hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    preschool_full_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    preschool_half_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    preschool_hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    kinder_full_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    kinder_half_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    kinder_hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    osc_full_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    osc_half_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    osc_hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    osc_before_school_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    osc_after_school_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    registration_fee: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    late_pickup_fee_per_minute: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    supplies_fee_monthly: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    effective_from: Mapped[Optional[datetime.date]] = mapped_column(Date)
    infant_parent_portion: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    toddler_parent_portion: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    preschool_parent_portion: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    kinder_parent_portion: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    osc_parent_portion: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='daycare_pricing')


class Families(Base):
    __tablename__ = 'families'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_41cdd4ce27c2b9e8ab21cf09ac9'),
        PrimaryKeyConstraint('id', name='PK_70414ac0c8f45664cf71324b9bb'),
        Index('IDX_083e295fc64ec128618c5e3713', 'name'),
        Index('IDX_41cdd4ce27c2b9e8ab21cf09ac', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'pending'::character varying"))
    photo_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    field_trip_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    emergency_medical_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    is_recurring_billing: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    additional_fees: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    additional_notes: Mapped[Optional[str]] = mapped_column(Text)
    recurring_funding_source_id: Mapped[Optional[str]] = mapped_column(String)
    file_number: Mapped[Optional[str]] = mapped_column(String(50))

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='families')
    children: Mapped[list['Children']] = relationship('Children', back_populates='family')
    emergency_contacts: Mapped[list['EmergencyContacts']] = relationship('EmergencyContacts', back_populates='family')
    guardians: Mapped[list['Guardians']] = relationship('Guardians', back_populates='family')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='family')
    recurring_invoices: Mapped[list['RecurringInvoices']] = relationship('RecurringInvoices', back_populates='family')
    credit_notes: Mapped[list['CreditNotes']] = relationship('CreditNotes', back_populates='family')


class FundingSources(Base):
    __tablename__ = 'funding_sources'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_81b8faa47cefda17a03afa7b3c2'),
        PrimaryKeyConstraint('id', name='PK_6e23f297c64fa46177b5f7e9533'),
        Index('IDX_81b8faa47cefda17a03afa7b3c', 'organization_id'),
        Index('IDX_ea744896bd1d017bd7a4d42327', 'name')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    funding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    default_coverage_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'fixed_amount'::character varying"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('10'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    is_parent_source: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255))
    contact_email: Mapped[Optional[str]] = mapped_column(String(255))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50))
    billing_address: Mapped[Optional[str]] = mapped_column(Text)
    default_coverage_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    default_coverage_percentage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='funding_sources')
    rate_schedules: Mapped[list['RateSchedules']] = relationship('RateSchedules', back_populates='funding_source')
    child_funding: Mapped[list['ChildFunding']] = relationship('ChildFunding', back_populates='funding_source')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='recipient')
    invoice_allocations: Mapped[list['InvoiceAllocations']] = relationship('InvoiceAllocations', back_populates='funding_source')


class GeneratedClaimReports(Base):
    __tablename__ = 'generated_claim_reports'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_3c1b6a64432308566dc3e222505'),
        PrimaryKeyConstraint('id', name='PK_40ccab6d90689f4b5cfdfb69bba')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    report_name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_month: Mapped[int] = mapped_column(Integer, nullable=False)
    target_year: Mapped[int] = mapped_column(Integer, nullable=False)
    report_status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'draft'::character varying"))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    operating_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    hour_tiers: Mapped[dict] = mapped_column(JSON, nullable=False)
    behavioral_profiles: Mapped[dict] = mapped_column(JSON, nullable=False)
    total_children_processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    total_projected_hours: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("'0'::numeric"))
    average_hours_per_child: Mapped[decimal.Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default=text("'0'::numeric"))
    full_time_children: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    school_age_children: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    prorated_children: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    total_business_days_in_month: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    school_break_days_in_month: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    regular_school_days_in_month: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    total_capacity_hours: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("'0'::numeric"))
    capacity_utilized: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    children_with_capacity_issues: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    school_break_periods: Mapped[Optional[dict]] = mapped_column(JSON)
    behavioral_profile_distribution: Mapped[Optional[dict]] = mapped_column(JSON)
    daily_capacity_utilization: Mapped[Optional[dict]] = mapped_column(JSON)
    created_by: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='generated_claim_reports')
    generated_claims: Mapped[list['GeneratedClaims']] = relationship('GeneratedClaims', back_populates='report')


class ImportedClaims(Base):
    __tablename__ = 'imported_claims'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_89076ad80ef2a8edf8319452842'),
        PrimaryKeyConstraint('id', name='PK_0d2f3d86bc1b49ebf0992382943'),
        Index('IDX_28bd328ae0372bdb7c32e1e527', 'child_name'),
        Index('IDX_3627f14bbdf026f469135e0b5c', 'import_batch_id'),
        Index('IDX_89076ad80ef2a8edf831945284', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    child_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hours_claimed: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_month: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_year: Mapped[int] = mapped_column(Integer, nullable=False)
    import_batch_id: Mapped[str] = mapped_column(String(100), nullable=False)
    manually_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    imported_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    care_category: Mapped[Optional[str]] = mapped_column(String(50))
    date_of_birth: Mapped[Optional[datetime.date]] = mapped_column(Date)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255))
    matched_child_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    match_confidence: Mapped[Optional[float]] = mapped_column(Double(53))
    corrected_child_name: Mapped[Optional[str]] = mapped_column(String(255))
    corrected_hours: Mapped[Optional[int]] = mapped_column(Integer)
    correction_notes: Mapped[Optional[str]] = mapped_column(Text)

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='imported_claims')


class InvoiceTemplates(Base):
    __tablename__ = 'invoice_templates'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_4fba551e6bb4eade4fd7bd873da'),
        PrimaryKeyConstraint('id', name='PK_3a8370502b9ce87ef136481ddcf'),
        Index('IDX_4fba551e6bb4eade4fd7bd873d', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    due_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('30'))
    default_tax_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("'0'::numeric"))
    default_discount_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)
    default_discount_percentage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    line_items: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='invoice_templates')
    recurring_invoices: Mapped[list['RecurringInvoices']] = relationship('RecurringInvoices', back_populates='template')


class ProviderSettings(Base):
    __tablename__ = 'provider_settings'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_63fa05e5bd6d49095a827b0e323'),
        PrimaryKeyConstraint('id', name='PK_c92615abb81fa35e14e3e9ad0d0'),
        UniqueConstraint('organization_id', name='UQ_63fa05e5bd6d49095a827b0e323'),
        Index('IDX_63fa05e5bd6d49095a827b0e32', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    currency_symbol: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'$'::character varying"))
    invoice_prefix: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'INV-'::character varying"))
    next_invoice_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    default_tax_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("'0'::numeric"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    smtp_encryption: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'tls'::character varying"))
    smtp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    tax_name: Mapped[Optional[str]] = mapped_column(String(50))
    default_notes: Mapped[Optional[str]] = mapped_column(Text)
    default_terms: Mapped[Optional[str]] = mapped_column(Text)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(255))
    smtp_port: Mapped[Optional[int]] = mapped_column(Integer)
    smtp_username: Mapped[Optional[str]] = mapped_column(String(255))
    smtp_password: Mapped[Optional[str]] = mapped_column(String(255))
    smtp_from_email: Mapped[Optional[str]] = mapped_column(String(255))
    smtp_from_name: Mapped[Optional[str]] = mapped_column(String(255))

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='provider_settings')


t_role_permissions = Table(
    'role_permissions', Base.metadata,
    Column('role_id', Integer, primary_key=True),
    Column('permission_id', Integer, primary_key=True),
    ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE', onupdate='CASCADE', name='FK_17022daf3f885f7d35423e9971e'),
    ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE', onupdate='CASCADE', name='FK_178199805b901ccd220ab7740ec'),
    PrimaryKeyConstraint('role_id', 'permission_id', name='PK_25d24010f53bb80b78e412c9656'),
    Index('IDX_17022daf3f885f7d35423e9971', 'permission_id'),
    Index('IDX_178199805b901ccd220ab7740e', 'role_id')
)


class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='FK_21a659804ed7bf61eb91688dea7'),
        ForeignKeyConstraint(['role_id'], ['roles.id'], name='FK_a2cecd1a3531c0b041e29ba46e1'),
        PrimaryKeyConstraint('id', name='PK_a3ffb1c0c8416b9fc6f907b7433'),
        UniqueConstraint('email', name='UQ_97672ac88f789774dd47f7c8be3'),
        Index('IDX_21a659804ed7bf61eb91688dea', 'organization_id'),
        Index('IDX_97672ac88f789774dd47f7c8be', 'email')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'local'::character varying"))
    role_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    password: Mapped[Optional[str]] = mapped_column(String(255))
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    organization: Mapped[Optional['Organizations']] = relationship('Organizations', back_populates='users')
    role: Mapped['Roles'] = relationship('Roles', back_populates='users')
    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='user')
    organization_members: Mapped[list['OrganizationMembers']] = relationship('OrganizationMembers', back_populates='user')
    staff_education: Mapped[list['StaffEducation']] = relationship('StaffEducation', back_populates='user')
    staff_profiles: Mapped['StaffProfiles'] = relationship('StaffProfiles', uselist=False, back_populates='user')


class Children(Base):
    __tablename__ = 'children'
    __table_args__ = (
        ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE', name='FK_4ed868923e68a6f087f3b4455cf'),
        PrimaryKeyConstraint('id', name='PK_8c5a7cbebf2c702830ef38d22b0'),
        Index('IDX_0ae3439fae1fdf5a07fcc70178', 'first_name'),
        Index('IDX_df35396c316aacfb39e2238206', 'last_name')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    need_invoice: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    middle_name: Mapped[Optional[str]] = mapped_column(String(255))
    gender: Mapped[Optional[str]] = mapped_column(String(20))
    age_group: Mapped[Optional[str]] = mapped_column(String(50))
    health_care_number: Mapped[Optional[str]] = mapped_column(String(100))
    allergies: Mapped[Optional[str]] = mapped_column(Text)
    medical_conditions: Mapped[Optional[str]] = mapped_column(Text)
    medications: Mapped[Optional[str]] = mapped_column(Text)
    immunization_up_to_date: Mapped[Optional[bool]] = mapped_column(Boolean)
    doctor_name: Mapped[Optional[str]] = mapped_column(String(255))
    doctor_phone: Mapped[Optional[str]] = mapped_column(String(50))
    fscd_file_number: Mapped[Optional[str]] = mapped_column(String(100))
    schedule_start_time: Mapped[Optional[str]] = mapped_column(String(10))
    schedule_end_time: Mapped[Optional[str]] = mapped_column(String(10))

    family: Mapped['Families'] = relationship('Families', back_populates='children')
    child_funding: Mapped[list['ChildFunding']] = relationship('ChildFunding', back_populates='child')
    generated_claims: Mapped[list['GeneratedClaims']] = relationship('GeneratedClaims', back_populates='child')
    portfolios: Mapped[list['Portfolios']] = relationship('Portfolios', back_populates='child')
    invoice_line_items: Mapped[list['InvoiceLineItems']] = relationship('InvoiceLineItems', back_populates='child')


class EmergencyContacts(Base):
    __tablename__ = 'emergency_contacts'
    __table_args__ = (
        ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE', name='FK_058cea278b7f415c22e3e05d782'),
        PrimaryKeyConstraint('id', name='PK_8be191845b6fca1c4e5ba5bd7d1')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_: Mapped[str] = mapped_column('relationship', String(100), nullable=False)
    cell_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    authorized_pickup: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    home_phone: Mapped[Optional[str]] = mapped_column(String(50))

    family: Mapped['Families'] = relationship('Families', back_populates='emergency_contacts')


class Guardians(Base):
    __tablename__ = 'guardians'
    __table_args__ = (
        ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE', name='FK_da710cc986fc207c8dbf41aeb0b'),
        PrimaryKeyConstraint('id', name='PK_3dcf02f3dc96a2c017106f280be'),
        Index('IDX_2822ea52513239fdd508c016e3', 'email')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    guardian_type: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    cell_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    relationship_: Mapped[Optional[str]] = mapped_column('relationship', String(100))
    home_phone: Mapped[Optional[str]] = mapped_column(String(50))
    work_phone: Mapped[Optional[str]] = mapped_column(String(50))
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))

    family: Mapped['Families'] = relationship('Families', back_populates='guardians')
    invoices: Mapped[list['Invoices']] = relationship('Invoices', back_populates='guardian')
    recurring_invoices: Mapped[list['RecurringInvoices']] = relationship('RecurringInvoices', back_populates='guardian')
    signatures: Mapped[list['Signatures']] = relationship('Signatures', back_populates='guardian')


class Notifications(Base):
    __tablename__ = 'notifications'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_cb7b1fb018b296f2107e998b2ff'),
        ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='FK_9a8a82462cab47c73d25f49261f'),
        PrimaryKeyConstraint('id', name='PK_6a72c3c0f683f6462415e653c3a'),
        Index('IDX_9a8a82462cab47c73d25f49261', 'user_id'),
        Index('IDX_a17edcb3b8e39c52a7d0554d31', 'user_id', 'read'),
        Index('IDX_cb7b1fb018b296f2107e998b2f', 'organization_id'),
        Index('IDX_f5cacff71c093b12d786d5a586', 'organization_id', 'created_at')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'normal'::character varying"))
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    message: Mapped[Optional[str]] = mapped_column(Text)
    read_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    action_url: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB)

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='notifications')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='notifications')


class OrganizationMembers(Base):
    __tablename__ = 'organization_members'
    __table_args__ = (
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='FK_7062a4fbd9bab22ffd918e5d3d9'),
        ForeignKeyConstraint(['user_id'], ['users.id'], name='FK_89bde91f78d36ca41e9515d91c6'),
        PrimaryKeyConstraint('id', name='PK_c2b39d5d072886a4d9c8105eb9a'),
        Index('IDX_7062a4fbd9bab22ffd918e5d3d', 'organization_id'),
        Index('IDX_89bde91f78d36ca41e9515d91c', 'user_id'),
        Index('IDX_f4812f00736e35131a65d6032d', 'user_id', 'organization_id', unique=True)
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'::character varying"))
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'educator'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    hire_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    release_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    title: Mapped[Optional[str]] = mapped_column(String(100))
    payroll_type: Mapped[Optional[str]] = mapped_column(String(20))
    employee_number: Mapped[Optional[str]] = mapped_column(String(50))
    hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    annual_salary: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    invited_by: Mapped[Optional[str]] = mapped_column(String)
    invite_method: Mapped[Optional[str]] = mapped_column(String(50))
    invite_code: Mapped[Optional[str]] = mapped_column(String(100))
    joined_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='organization_members')
    user: Mapped['Users'] = relationship('Users', back_populates='organization_members')


class RateSchedules(Base):
    __tablename__ = 'rate_schedules'
    __table_args__ = (
        ForeignKeyConstraint(['funding_source_id'], ['funding_sources.id'], ondelete='SET NULL', name='FK_eb04c188cba5303dc85c0f8be26'),
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_a80ef4d201eccf2b9af8de2e4f7'),
        PrimaryKeyConstraint('id', name='PK_9767561fc7e15008f57f4dcd695'),
        Index('IDX_a80ef4d201eccf2b9af8de2e4f', 'organization_id'),
        Index('IDX_f14e6233ac1946c9bdeb1145f6', 'name')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    age_group: Mapped[str] = mapped_column(String(50), nullable=False)
    rate_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'daily'::character varying"))
    rate_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    effective_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)
    funding_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    half_day_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    effective_to: Mapped[Optional[datetime.date]] = mapped_column(Date)

    funding_source: Mapped[Optional['FundingSources']] = relationship('FundingSources', back_populates='rate_schedules')
    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='rate_schedules')


class StaffEducation(Base):
    __tablename__ = 'staff_education'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], name='FK_0af00f6656e25bb2059efdb7450'),
        PrimaryKeyConstraint('id', name='PK_8af60c0083d2f9d2d8d90172453'),
        Index('IDX_0af00f6656e25bb2059efdb745', 'user_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    certification_number: Mapped[Optional[str]] = mapped_column(String(100))
    institution_name: Mapped[Optional[str]] = mapped_column(String(255))
    course_name: Mapped[Optional[str]] = mapped_column(String(255))
    pd_hours: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 2))
    issue_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    expiry_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    completion_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    document_url: Mapped[Optional[str]] = mapped_column(String(500))
    verified_by: Mapped[Optional[str]] = mapped_column(String)
    verified_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    user: Mapped['Users'] = relationship('Users', back_populates='staff_education')


class StaffProfiles(Base):
    __tablename__ = 'staff_profiles'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], name='FK_223deb3f390b28562fad70eefed'),
        PrimaryKeyConstraint('id', name='PK_6d4c6c0b447e39147b4a6dcbede'),
        UniqueConstraint('user_id', name='REL_223deb3f390b28562fad70eefe'),
        Index('IDX_223deb3f390b28562fad70eefe', 'user_id', unique=True)
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    country: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'Canada'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    date_of_birth: Mapped[Optional[datetime.date]] = mapped_column(Date)
    sex: Mapped[Optional[str]] = mapped_column(String(20))
    photo_url: Mapped[Optional[str]] = mapped_column(String(500))
    cell_phone: Mapped[Optional[str]] = mapped_column(String(20))
    home_phone: Mapped[Optional[str]] = mapped_column(String(20))
    street_address: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    province: Mapped[Optional[str]] = mapped_column(String(50))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    staff_color: Mapped[Optional[str]] = mapped_column(String(10))

    user: Mapped['Users'] = relationship('Users', back_populates='staff_profiles')


class ChildFunding(Base):
    __tablename__ = 'child_funding'
    __table_args__ = (
        ForeignKeyConstraint(['child_id'], ['children.id'], ondelete='CASCADE', name='FK_765fee11c4079b3e737baa757bf'),
        ForeignKeyConstraint(['funding_source_id'], ['funding_sources.id'], ondelete='CASCADE', name='FK_3334215105bc1a671b6ebeb95f8'),
        PrimaryKeyConstraint('id', name='PK_8e255d97b891eae3f7c71fff229'),
        Index('IDX_3334215105bc1a671b6ebeb95f', 'funding_source_id'),
        Index('IDX_765fee11c4079b3e737baa757b', 'child_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    child_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    funding_source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    coverage_type: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    coverage_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    coverage_percentage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    approval_reference: Mapped[Optional[str]] = mapped_column(String(255))
    effective_to: Mapped[Optional[datetime.date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    child: Mapped['Children'] = relationship('Children', back_populates='child_funding')
    funding_source: Mapped['FundingSources'] = relationship('FundingSources', back_populates='child_funding')


class GeneratedClaims(Base):
    __tablename__ = 'generated_claims'
    __table_args__ = (
        ForeignKeyConstraint(['child_id'], ['children.id'], ondelete='CASCADE', name='FK_c6d961b6368de416f4065d041e6'),
        ForeignKeyConstraint(['report_id'], ['generated_claim_reports.id'], ondelete='CASCADE', name='FK_a2264833f61c5d60edaeb787069'),
        PrimaryKeyConstraint('id', name='PK_203e73dde03b1e89722db1d82de')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    child_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    child_name: Mapped[str] = mapped_column(String(255), nullable=False)
    age_in_years: Mapped[int] = mapped_column(Integer, nullable=False)
    age_in_months: Mapped[int] = mapped_column(Integer, nullable=False)
    care_category: Mapped[str] = mapped_column(String(20), nullable=False)
    behavioral_profile: Mapped[str] = mapped_column(String(20), nullable=False)
    projected_hours: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    projected_attendance_days: Mapped[int] = mapped_column(Integer, nullable=False)
    base_hours_before_proration: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_prorated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    total_business_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    school_break_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    regular_school_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    average_hours_per_day: Mapped[decimal.Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default=text("'0'::numeric"))
    capacity_limited_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    proration_factor: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 4))
    enrollment_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    eligible_business_days: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    daily_hours: Mapped[Optional[str]] = mapped_column(Text)

    child: Mapped['Children'] = relationship('Children', back_populates='generated_claims')
    report: Mapped['GeneratedClaimReports'] = relationship('GeneratedClaimReports', back_populates='generated_claims')


class Invoices(Base):
    __tablename__ = 'invoices'
    __table_args__ = (
        ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='SET NULL', name='FK_cd9a6993d138b538fb6c83e7330'),
        ForeignKeyConstraint(['guardian_id'], ['guardians.id'], ondelete='SET NULL', name='FK_299c831ca339e824feafbca6cd2'),
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_d4e095bcd100de447d3c27708f9'),
        ForeignKeyConstraint(['recipient_id'], ['funding_sources.id'], ondelete='SET NULL', name='FK_d9061d1072decf37cd2a485b7ba'),
        PrimaryKeyConstraint('id', name='PK_668cef7c22a427fd822cc1be3ce'),
        UniqueConstraint('invoice_number', name='UQ_d8f8d3788694e1b3f96c42c36fb'),
        Index('IDX_ac0f09364e3701d9ed35435288', 'status'),
        Index('IDX_cd9a6993d138b538fb6c83e733', 'family_id'),
        Index('IDX_d4e095bcd100de447d3c27708f', 'organization_id'),
        Index('IDX_d8f8d3788694e1b3f96c42c36f', 'invoice_number'),
        Index('IDX_d9061d1072decf37cd2a485b7b', 'recipient_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    discount_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    tax_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("'0'::numeric"))
    tax_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    total_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    amount_paid: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    balance_due: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'draft'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    file_number: Mapped[Optional[str]] = mapped_column(String(100))
    family_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    guardian_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    client_name: Mapped[Optional[str]] = mapped_column(String(255))
    client_email: Mapped[Optional[str]] = mapped_column(String(255))
    client_address: Mapped[Optional[str]] = mapped_column(Text)
    period_start: Mapped[Optional[datetime.date]] = mapped_column(Date)
    period_end: Mapped[Optional[datetime.date]] = mapped_column(Date)
    discount_percentage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)
    recipient_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    family: Mapped[Optional['Families']] = relationship('Families', back_populates='invoices')
    guardian: Mapped[Optional['Guardians']] = relationship('Guardians', back_populates='invoices')
    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='invoices')
    recipient: Mapped[Optional['FundingSources']] = relationship('FundingSources', back_populates='invoices')
    credit_notes: Mapped[list['CreditNotes']] = relationship('CreditNotes', back_populates='invoice')
    invoice_allocations: Mapped[list['InvoiceAllocations']] = relationship('InvoiceAllocations', back_populates='invoice')
    invoice_line_items: Mapped[list['InvoiceLineItems']] = relationship('InvoiceLineItems', back_populates='invoice')
    payments: Mapped[list['Payments']] = relationship('Payments', back_populates='invoice')
    credit_applications: Mapped[list['CreditApplications']] = relationship('CreditApplications', back_populates='invoice')


class Portfolios(Base):
    __tablename__ = 'portfolios'
    __table_args__ = (
        ForeignKeyConstraint(['child_id'], ['children.id'], ondelete='CASCADE', name='FK_2e374d904f9826dc6537d76bfc5'),
        PrimaryKeyConstraint('id', name='PK_488aa6e9b219d1d9087126871ae'),
        Index('IDX_2e374d904f9826dc6537d76bfc', 'child_id'),
        Index('IDX_cbd81b1f46519ac0c7c505b60f', 'organization_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    child_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'active'::character varying"))
    total_entries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    milestones_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    milestones_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    last_entry_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    child: Mapped['Children'] = relationship('Children', back_populates='portfolios')
    portfolio_entries: Mapped[list['PortfolioEntries']] = relationship('PortfolioEntries', back_populates='portfolio')


class RecurringInvoices(Base):
    __tablename__ = 'recurring_invoices'
    __table_args__ = (
        ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='SET NULL', name='FK_1bd44e6cd74eeb8da57d6556ad3'),
        ForeignKeyConstraint(['guardian_id'], ['guardians.id'], ondelete='SET NULL', name='FK_5a5d37ceda402537c8f19182157'),
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_0ca3c76bd3cebcc6298ad42b935'),
        ForeignKeyConstraint(['template_id'], ['invoice_templates.id'], ondelete='SET NULL', name='FK_725537b29b4e514eaa1c6467882'),
        PrimaryKeyConstraint('id', name='PK_8a156fda29720c5fc4f86c89081'),
        Index('IDX_0ca3c76bd3cebcc6298ad42b93', 'organization_id'),
        Index('IDX_19f7d4899c59a8a54fd55ed607', 'status'),
        Index('IDX_1bd44e6cd74eeb8da57d6556ad', 'family_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'monthly'::character varying"))
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    day_of_period: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    due_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('30'))
    tax_rate: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("'0'::numeric"))
    discount_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    auto_send: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    send_reminder: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    reminder_days_before: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('7'))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'::character varying"))
    invoices_generated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    family_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    guardian_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    client_name: Mapped[Optional[str]] = mapped_column(String(255))
    client_email: Mapped[Optional[str]] = mapped_column(String(255))
    client_address: Mapped[Optional[str]] = mapped_column(Text)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    next_invoice_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    last_invoice_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    line_items: Mapped[Optional[str]] = mapped_column(Text)
    discount_percentage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    terms: Mapped[Optional[str]] = mapped_column(Text)
    max_occurrences: Mapped[Optional[int]] = mapped_column(Integer)

    family: Mapped[Optional['Families']] = relationship('Families', back_populates='recurring_invoices')
    guardian: Mapped[Optional['Guardians']] = relationship('Guardians', back_populates='recurring_invoices')
    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='recurring_invoices')
    template: Mapped[Optional['InvoiceTemplates']] = relationship('InvoiceTemplates', back_populates='recurring_invoices')


class Signatures(Base):
    __tablename__ = 'signatures'
    __table_args__ = (
        ForeignKeyConstraint(['guardian_id'], ['guardians.id'], ondelete='CASCADE', name='FK_af3a2b327ae4f6c9e09bf4e5018'),
        PrimaryKeyConstraint('id', name='PK_f56eb3cd344ce7f9ae28ce814eb'),
        Index('IDX_af3a2b327ae4f6c9e09bf4e501', 'guardian_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    image_data: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    guardian_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    label: Mapped[Optional[str]] = mapped_column(String(255))

    guardian: Mapped[Optional['Guardians']] = relationship('Guardians', back_populates='signatures')


class CreditNotes(Base):
    __tablename__ = 'credit_notes'
    __table_args__ = (
        ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='SET NULL', name='FK_fe7f08d244fecd662b7c7f68ab8'),
        ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='SET NULL', name='FK_ab75ae7ceab2ad0e3c77768c373'),
        ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE', name='FK_fd9c443bea371731f2205ed3592'),
        PrimaryKeyConstraint('id', name='PK_4933888a20b5469e119ad74b9e9'),
        UniqueConstraint('credit_note_number', name='UQ_a7078fae5ed0ec6e160f4319331'),
        Index('IDX_66db5673fe29da2f8ed778fa96', 'status'),
        Index('IDX_a7078fae5ed0ec6e160f431933', 'credit_note_number'),
        Index('IDX_fd9c443bea371731f2205ed359', 'organization_id'),
        Index('IDX_fe7f08d244fecd662b7c7f68ab', 'family_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    credit_note_number: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount_applied: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    balance: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    reason: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'other'::character varying"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    family_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    client_name: Mapped[Optional[str]] = mapped_column(String(255))
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    description: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    family: Mapped[Optional['Families']] = relationship('Families', back_populates='credit_notes')
    invoice: Mapped[Optional['Invoices']] = relationship('Invoices', back_populates='credit_notes')
    organization: Mapped['Organizations'] = relationship('Organizations', back_populates='credit_notes')
    credit_applications: Mapped[list['CreditApplications']] = relationship('CreditApplications', back_populates='credit_note')


class InvoiceAllocations(Base):
    __tablename__ = 'invoice_allocations'
    __table_args__ = (
        ForeignKeyConstraint(['funding_source_id'], ['funding_sources.id'], ondelete='CASCADE', name='FK_a6c469b8d43d00e71da8b813316'),
        ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE', name='FK_60992310bede0daa77cb5c9ffd0'),
        PrimaryKeyConstraint('id', name='PK_fdfeb318a6aac2e3ba61013c653'),
        Index('IDX_60992310bede0daa77cb5c9ffd', 'invoice_id'),
        Index('IDX_a6c469b8d43d00e71da8b81331', 'funding_source_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    funding_source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    allocated_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    paid_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'0'::numeric"))
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'pending'::character varying"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    payment_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    funding_source: Mapped['FundingSources'] = relationship('FundingSources', back_populates='invoice_allocations')
    invoice: Mapped['Invoices'] = relationship('Invoices', back_populates='invoice_allocations')


class InvoiceLineItems(Base):
    __tablename__ = 'invoice_line_items'
    __table_args__ = (
        ForeignKeyConstraint(['child_id'], ['children.id'], ondelete='SET NULL', name='FK_16102d1cd0768af9d15ecaf9824'),
        ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE', name='FK_e554609a06b180dac66a9a977c5'),
        PrimaryKeyConstraint('id', name='PK_4e8ccaadaf5d0619db9d219b061'),
        Index('IDX_e554609a06b180dac66a9a977c', 'invoice_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'service_flat'::character varying"))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("'1'::numeric"))
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    child_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    child_name: Mapped[Optional[str]] = mapped_column(String(255))
    full_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    subsidy_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    hours: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    unit_price: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    service_date_from: Mapped[Optional[datetime.date]] = mapped_column(Date)
    service_date_to: Mapped[Optional[datetime.date]] = mapped_column(Date)
    parent_portion: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    reg_fee: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    rate_description: Mapped[Optional[str]] = mapped_column(String(255))

    child: Mapped[Optional['Children']] = relationship('Children', back_populates='invoice_line_items')
    invoice: Mapped['Invoices'] = relationship('Invoices', back_populates='invoice_line_items')


class Payments(Base):
    __tablename__ = 'payments'
    __table_args__ = (
        ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE', name='FK_563a5e248518c623eebd987d43e'),
        PrimaryKeyConstraint('id', name='PK_197ab7af18c93fbb0c9b28b4a59'),
        Index('IDX_563a5e248518c623eebd987d43', 'invoice_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    reference_number: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    invoice: Mapped['Invoices'] = relationship('Invoices', back_populates='payments')


class PortfolioEntries(Base):
    __tablename__ = 'portfolio_entries'
    __table_args__ = (
        ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE', name='FK_b6632ca8840004073ed49a5a322'),
        PrimaryKeyConstraint('id', name='PK_31a03d4c03f8aa5da254a4fc49b'),
        Index('IDX_14a61683ad8740f4b2d26f211a', 'organization_id'),
        Index('IDX_b6632ca8840004073ed49a5a32', 'portfolio_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    portfolio_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    entry_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    shared_with_parents: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)
    developmental_domain: Mapped[Optional[str]] = mapped_column(String(50))
    age_group: Mapped[Optional[str]] = mapped_column(String(50))
    milestone_status: Mapped[Optional[str]] = mapped_column(String(50))
    milestone_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    media_url: Mapped[Optional[str]] = mapped_column(Text)
    media_type: Mapped[Optional[str]] = mapped_column(String(50))
    recorded_by: Mapped[Optional[str]] = mapped_column(String(255))
    shared_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    parent_comment: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB)

    portfolio: Mapped['Portfolios'] = relationship('Portfolios', back_populates='portfolio_entries')
    portfolio_images: Mapped[list['PortfolioImages']] = relationship('PortfolioImages', back_populates='entry')


class CreditApplications(Base):
    __tablename__ = 'credit_applications'
    __table_args__ = (
        ForeignKeyConstraint(['credit_note_id'], ['credit_notes.id'], ondelete='CASCADE', name='FK_f9d23346900a25450f5562b1b82'),
        ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE', name='FK_3e7b1956a761b7acf318978caa6'),
        PrimaryKeyConstraint('id', name='PK_1943980f81286bd5dc733b5119c'),
        Index('IDX_3e7b1956a761b7acf318978caa', 'invoice_id'),
        Index('IDX_f9d23346900a25450f5562b1b8', 'credit_note_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    credit_note_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    applied_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    credit_note: Mapped['CreditNotes'] = relationship('CreditNotes', back_populates='credit_applications')
    invoice: Mapped['Invoices'] = relationship('Invoices', back_populates='credit_applications')


class PortfolioImages(Base):
    __tablename__ = 'portfolio_images'
    __table_args__ = (
        ForeignKeyConstraint(['entry_id'], ['portfolio_entries.id'], ondelete='CASCADE', name='FK_dfe896442321d4f4d322f6074c1'),
        PrimaryKeyConstraint('id', name='PK_4fb584b54f9368be1a6612a4e83'),
        Index('IDX_dfe896442321d4f4d322f6074c', 'entry_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    public_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, server_default=text('now()'))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    format: Mapped[Optional[str]] = mapped_column(String(20))
    bytes: Mapped[Optional[int]] = mapped_column(Integer)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255))
    caption: Mapped[Optional[str]] = mapped_column(Text)

    entry: Mapped['PortfolioEntries'] = relationship('PortfolioEntries', back_populates='portfolio_images')
