import { addOrganizationHeader, notifyAuthorizationDenied, SESSION_TOKEN_KEY } from '../../api/client';
import type { ChildAuthorityFocus, ChildAuthorityFocusKind } from './childAuthorityFocus';

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:3002/api/v1').replace(/\/$/, '');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const UTC_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|\+00:00)$/;
const EFFECTIVE_STATUSES = ['scheduled', 'effective', 'expired', 'revoked', 'withdrawn', 'supporting_evidence_unavailable'] as const;
const PERSON_STATUSES = ['active', 'retired'] as const;
const RELATIONSHIPS = ['parent', 'legal_guardian', 'foster_parent', 'grandparent', 'adult_sibling', 'aunt_uncle', 'family_friend', 'caseworker', 'transport_provider', 'other'] as const;
const VERIFICATION_POLICIES = ['government_photo_id', 'documented_familiarity', 'government_photo_id_or_documented_familiarity', 'government_photo_id_and_secondary_check'] as const;
const RULE_KINDS = ['deny', 'supervised_only', 'named_recipient_only', 'manager_review'] as const;
const SAFE_EXPLANATIONS = ['release_restricted', 'supervision_required', 'named_recipient_only', 'manager_review_required'] as const;
const CONSENT_PURPOSES = ['off_site_activity', 'emergency_health_care', 'medication_administration', 'internal_media', 'external_media', 'marketing', 'research', 'optional_service', 'information_sharing'] as const;
const CONSENT_DECISIONS = ['granted', 'declined'] as const;

type EffectiveStatus = typeof EFFECTIVE_STATUSES[number];
type RelationshipKind = typeof RELATIONSHIPS[number];

export class ChildAuthoritySummaryApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null = null,
    public readonly code: string | null = null,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ChildAuthoritySummaryApiError';
  }
}

export function isChildAuthoritySummaryUnavailable(caught: unknown): boolean {
  return caught instanceof ChildAuthoritySummaryApiError
    && caught.status === 503
    && ['family_authority_unavailable', 'family_authority_activation_unavailable'].includes(caught.code || '');
}

export interface ChildAuthorityPersonSummary {
  id: string;
  display_name: string;
  relationship_kind: RelationshipKind;
  status: typeof PERSON_STATUSES[number];
}

interface EffectiveSummaryRecord {
  id: string;
  child_id: string;
  effective_from: string;
  effective_until: string;
  version: number;
  effective_status: EffectiveStatus;
  effective_now: boolean;
  authority_revision: number;
}

export interface ChildReleaseAuthorizationSummary extends EffectiveSummaryRecord {
  record_type: 'release_authorization';
  recipient: ChildAuthorityPersonSummary;
  verification_policy_code: typeof VERIFICATION_POLICIES[number];
}

export interface ChildReleaseRuleSummary extends EffectiveSummaryRecord {
  record_type: 'release_rule';
  rule_kind: typeof RULE_KINDS[number];
  safe_explanation_code: typeof SAFE_EXPLANATIONS[number];
  scope_kind: 'all_recipients' | 'specific_person';
  scoped_person: ChildAuthorityPersonSummary | null;
}

export type ChildConsentScope =
  | { kind: 'policy' }
  | { kind: 'facility'; facility_id: string }
  | { kind: 'named_activity'; reference: string };

export interface ChildConsentDecisionSummary extends EffectiveSummaryRecord {
  record_type: 'consent';
  purpose_code: typeof CONSENT_PURPOSES[number];
  policy: { id: string; title: string; version_number: number };
  decision: typeof CONSENT_DECISIONS[number];
  scope: ChildConsentScope;
}

export type ChildAuthoritySummaryRecord = ChildReleaseAuthorizationSummary | ChildReleaseRuleSummary | ChildConsentDecisionSummary;

export interface ChildAuthoritySummary {
  schema_version: 'child-authority-summary-v1';
  organization_id: string;
  family_id: string;
  child_id: string;
  generated_at: string;
  reviewed: boolean;
  authority_revision: number;
  release_authorizations: ChildReleaseAuthorizationSummary[];
  release_rules: ChildReleaseRuleSummary[];
  consent_decisions: ChildConsentDecisionSummary[];
  focus: ChildAuthoritySummaryRecord | null;
}

function exact(value: unknown, keys: readonly string[], label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  const row = value as Record<string, unknown>;
  const actual = Object.keys(row).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) throw new ChildAuthoritySummaryApiError(`The server returned an unexpected ${label} shape.`);
  return row;
}

function string(value: unknown, label: string, maximum = 2_048): string {
  if (typeof value !== 'string' || !value.trim() || value.length > maximum) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  return value;
}

function uuid(value: unknown, label: string): string {
  const parsed = string(value, label, 64);
  if (!UUID.test(parsed)) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  return parsed.toLowerCase();
}

function timestamp(value: unknown, label: string): string {
  const parsed = string(value, label, 64);
  const match = UTC_TIMESTAMP.exec(parsed);
  const instant = new Date(parsed);
  if (!match || !Number.isFinite(instant.getTime())) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
  if (
    year < 1
    || instant.getUTCFullYear() !== year
    || instant.getUTCMonth() + 1 !== month
    || instant.getUTCDate() !== day
    || instant.getUTCHours() !== hour
    || instant.getUTCMinutes() !== minute
    || instant.getUTCSeconds() !== second
  ) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  return parsed;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  return Number(value);
}

function bool(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  return value;
}

function oneOf<Value extends string>(value: unknown, options: readonly Value[], label: string): Value {
  if (!options.includes(value as Value)) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  return value as Value;
}

function parsePerson(value: unknown): ChildAuthorityPersonSummary {
  const row = exact(value, ['id', 'display_name', 'relationship_kind', 'status'], 'authority person summary');
  return {
    id: uuid(row.id, 'authority person id'),
    display_name: string(row.display_name, 'authority person display name', 305),
    relationship_kind: oneOf(row.relationship_kind, RELATIONSHIPS, 'authority person relationship'),
    status: oneOf(row.status, PERSON_STATUSES, 'authority person status'),
  };
}

function parseEffective(row: Record<string, unknown>, label: string): EffectiveSummaryRecord {
  const status = oneOf(row.effective_status, EFFECTIVE_STATUSES, `${label} effective status`);
  const effectiveNow = bool(row.effective_now, `${label} effective flag`);
  const effectiveFrom = timestamp(row.effective_from, `${label} start time`);
  const effectiveUntil = timestamp(row.effective_until, `${label} end time`);
  if (Date.parse(effectiveUntil) <= Date.parse(effectiveFrom) || effectiveNow !== (status === 'effective')) throw new ChildAuthoritySummaryApiError(`The server returned an incoherent ${label}.`);
  return {
    id: uuid(row.id, `${label} id`),
    child_id: uuid(row.child_id, `${label} child`),
    effective_from: effectiveFrom,
    effective_until: effectiveUntil,
    version: integer(row.version, `${label} version`, 1),
    effective_status: status,
    effective_now: effectiveNow,
    authority_revision: integer(row.authority_revision, `${label} authority revision`, 1),
  };
}

function parseAuthorization(value: unknown): ChildReleaseAuthorizationSummary {
  const row = exact(value, ['record_type', 'id', 'child_id', 'recipient', 'verification_policy_code', 'effective_from', 'effective_until', 'version', 'effective_status', 'effective_now', 'authority_revision'], 'release authorization summary');
  if (row.record_type !== 'release_authorization') throw new ChildAuthoritySummaryApiError('The server returned an invalid release authorization record type.');
  return { record_type: 'release_authorization', ...parseEffective(row, 'release authorization'), recipient: parsePerson(row.recipient), verification_policy_code: oneOf(row.verification_policy_code, VERIFICATION_POLICIES, 'release verification policy') };
}

function parseRule(value: unknown): ChildReleaseRuleSummary {
  const row = exact(value, ['record_type', 'id', 'child_id', 'rule_kind', 'safe_explanation_code', 'scope_kind', 'scoped_person', 'effective_from', 'effective_until', 'version', 'effective_status', 'effective_now', 'authority_revision'], 'release rule summary');
  if (row.record_type !== 'release_rule') throw new ChildAuthoritySummaryApiError('The server returned an invalid release rule record type.');
  const scopeKind = oneOf(row.scope_kind, ['all_recipients', 'specific_person'] as const, 'release rule scope');
  const scopedPerson = row.scoped_person === null ? null : parsePerson(row.scoped_person);
  if ((scopeKind === 'specific_person') !== Boolean(scopedPerson)) throw new ChildAuthoritySummaryApiError('The server returned an incoherent release rule scope.');
  return { record_type: 'release_rule', ...parseEffective(row, 'release rule'), rule_kind: oneOf(row.rule_kind, RULE_KINDS, 'release rule kind'), safe_explanation_code: oneOf(row.safe_explanation_code, SAFE_EXPLANATIONS, 'release rule explanation'), scope_kind: scopeKind, scoped_person: scopedPerson };
}

function parseConsentScope(value: unknown): ChildConsentScope {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ChildAuthoritySummaryApiError('The server returned an invalid consent scope.');
  const kind = (value as Record<string, unknown>).kind;
  if (kind === 'policy') { exact(value, ['kind'], 'policy consent scope'); return { kind }; }
  if (kind === 'facility') { const row = exact(value, ['kind', 'facility_id'], 'facility consent scope'); return { kind, facility_id: uuid(row.facility_id, 'consent scope facility') }; }
  if (kind === 'named_activity') { const row = exact(value, ['kind', 'reference'], 'activity consent scope'); return { kind, reference: string(row.reference, 'consent scope activity', 160) }; }
  throw new ChildAuthoritySummaryApiError('The server returned an invalid consent scope kind.');
}

function parseConsent(value: unknown): ChildConsentDecisionSummary {
  const row = exact(value, ['record_type', 'id', 'child_id', 'purpose_code', 'policy', 'decision', 'scope', 'effective_from', 'effective_until', 'version', 'effective_status', 'effective_now', 'authority_revision'], 'consent decision summary');
  if (row.record_type !== 'consent') throw new ChildAuthoritySummaryApiError('The server returned an invalid consent record type.');
  const policy = exact(row.policy, ['id', 'title', 'version_number'], 'consent policy summary');
  return { record_type: 'consent', ...parseEffective(row, 'consent decision'), purpose_code: oneOf(row.purpose_code, CONSENT_PURPOSES, 'consent purpose'), policy: { id: uuid(policy.id, 'consent policy id'), title: string(policy.title, 'consent policy title', 180), version_number: integer(policy.version_number, 'consent policy version', 1) }, decision: oneOf(row.decision, CONSENT_DECISIONS, 'consent decision'), scope: parseConsentScope(row.scope) };
}

function parseRecord(value: unknown): ChildAuthoritySummaryRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ChildAuthoritySummaryApiError('The server returned an invalid focused authority record.');
  const type = (value as Record<string, unknown>).record_type;
  if (type === 'release_authorization') return parseAuthorization(value);
  if (type === 'release_rule') return parseRule(value);
  if (type === 'consent') return parseConsent(value);
  throw new ChildAuthoritySummaryApiError('The server returned an invalid focused authority record type.');
}

function parseArray<T>(value: unknown, label: string, parser: (item: unknown) => T): T[] {
  if (!Array.isArray(value) || value.length > 200) throw new ChildAuthoritySummaryApiError(`The server returned an invalid ${label}.`);
  return value.map(parser);
}

export function parseChildAuthoritySummary(
  value: unknown,
  expected: { organizationId: string; familyId: string; childId: string; focus: ChildAuthorityFocus | null },
): ChildAuthoritySummary {
  const row = exact(value, ['schema_version', 'organization_id', 'family_id', 'child_id', 'generated_at', 'reviewed', 'authority_revision', 'release_authorizations', 'release_rules', 'consent_decisions', 'focus'], 'child authority summary');
  if (row.schema_version !== 'child-authority-summary-v1') throw new ChildAuthoritySummaryApiError('The server returned an unsupported child authority summary version.');
  const result: ChildAuthoritySummary = {
    schema_version: row.schema_version,
    organization_id: uuid(row.organization_id, 'authority summary organization'),
    family_id: uuid(row.family_id, 'authority summary family'),
    child_id: uuid(row.child_id, 'authority summary child'),
    generated_at: timestamp(row.generated_at, 'authority summary generation time'),
    reviewed: bool(row.reviewed, 'authority summary reviewed state'),
    authority_revision: integer(row.authority_revision, 'authority summary revision'),
    release_authorizations: parseArray(row.release_authorizations, 'release authorization summary list', parseAuthorization),
    release_rules: parseArray(row.release_rules, 'release rule summary list', parseRule),
    consent_decisions: parseArray(row.consent_decisions, 'consent decision summary list', parseConsent),
    focus: row.focus === null ? null : parseRecord(row.focus),
  };
  if (result.organization_id !== expected.organizationId.toLowerCase() || result.family_id !== expected.familyId.toLowerCase() || result.child_id !== expected.childId.toLowerCase()) throw new ChildAuthoritySummaryApiError('The authority summary crossed the requested organization, family, or child boundary.');
  if (result.reviewed !== (result.authority_revision > 0)) throw new ChildAuthoritySummaryApiError('The server returned an incoherent authority review state.');
  const records = [...result.release_authorizations, ...result.release_rules, ...result.consent_decisions];
  if (new Set(records.map((record) => `${record.record_type}:${record.id}`)).size !== records.length) throw new ChildAuthoritySummaryApiError('The server returned duplicate authority summary rows.');
  if (records.some((record) => record.child_id !== result.child_id || record.authority_revision !== result.authority_revision)) throw new ChildAuthoritySummaryApiError('The server returned authority rows outside the requested child revision.');
  if (expected.focus) {
    if (!result.focus || result.focus.record_type !== expected.focus.kind || result.focus.id !== expected.focus.id.toLowerCase()) throw new ChildAuthoritySummaryApiError('The server did not return the exact authority receipt target.');
  } else if (result.focus !== null) {
    throw new ChildAuthoritySummaryApiError('The server returned an unsolicited focused authority record.');
  }
  if (result.focus && (result.focus.child_id !== result.child_id || result.focus.authority_revision !== result.authority_revision)) throw new ChildAuthoritySummaryApiError('The focused authority record crossed the requested child revision.');
  return result;
}

function statusMessage(status: number, code: string | null): string {
  if (code === 'child_authority_focus_not_found') return 'The exact authority record from this receipt no longer exists in this child boundary.';
  if (code === 'invalid_child_authority_summary_query') return 'The authority receipt request was malformed and was not followed.';
  if (status === 401 || status === 403) return 'Your current role cannot open this private authority summary.';
  if (status === 404) return 'This child authority summary could not be found.';
  if (status === 503) return 'The verified authority summary is not enabled for this deployment yet.';
  return `The child authority summary request failed (${status}).`;
}

export async function fetchChildAuthoritySummary(
  childId: string,
  familyId: string,
  organizationId: string,
  focus: ChildAuthorityFocus | null,
  signal?: AbortSignal,
): Promise<ChildAuthoritySummary> {
  const token = localStorage.getItem(SESSION_TOKEN_KEY);
  if (!token) throw new ChildAuthoritySummaryApiError('A secure CareSync session is required.', 401, null);
  const headers = addOrganizationHeader(new Headers({ Accept: 'application/json', Authorization: `Bearer ${token}` }), organizationId);
  const query = focus ? `?${new URLSearchParams({ focus: focus.kind, record_id: focus.id })}` : '';
  let response: Response;
  try {
    response = await fetch(`${API_URL}/children/${encodeURIComponent(childId)}/authority-summary${query}`, { headers, signal, cache: 'no-store' });
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === 'AbortError') throw caught;
    throw new ChildAuthoritySummaryApiError('CareSync could not reach the child authority summary.', null, null, caught);
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && !Array.isArray(payload) ? (payload as Record<string, unknown>).detail : null;
    const code = detail && typeof detail === 'object' && !Array.isArray(detail) && typeof (detail as Record<string, unknown>).code === 'string' ? String((detail as Record<string, unknown>).code) : null;
    if (response.status === 401 || response.status === 403) notifyAuthorizationDenied();
    throw new ChildAuthoritySummaryApiError(statusMessage(response.status, code), response.status, code, payload);
  }
  return parseChildAuthoritySummary(payload, { organizationId, familyId, childId, focus });
}

export function authorityFocusQueryKind(value: ChildAuthoritySummaryRecord): ChildAuthorityFocusKind {
  return value.record_type;
}
