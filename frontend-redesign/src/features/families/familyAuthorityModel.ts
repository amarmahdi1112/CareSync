import type { FamilyDetailRecord } from './types';
import type {
  AuthorityEvidence,
  AuthorityEvidenceEpistemicStatus,
  AuthorityEvidenceKind,
  AuthorityEvidenceObject,
  AuthorityRecordEffectiveStatus,
  AuthorityPerson,
  AuthorityPersonFacts,
  AuthorityPersonSource,
  ConsentPolicyVersion,
  ReviewedAuthorityBasis,
  FamilyAuthorityWorkspaceRecord,
} from './familyAuthorityTypes';

export const AUTHORITY_RELATIONSHIPS = [
  'parent', 'legal_guardian', 'foster_parent', 'grandparent', 'adult_sibling',
  'aunt_uncle', 'family_friend', 'caseworker', 'transport_provider', 'other',
] as const;

export const AUTHORITY_EVIDENCE_KINDS = [
  'identity_document', 'custody_document', 'court_order', 'guardian_attestation',
  'signed_consent', 'signed_release_delegation', 'staff_witness', 'other_document',
] as const;

export const DOCUMENT_EVIDENCE_KINDS = new Set<AuthorityEvidenceKind>([
  'identity_document', 'custody_document', 'court_order', 'signed_consent', 'signed_release_delegation', 'other_document',
]);

export const REJECTION_REASONS = [
  'insufficient_evidence', 'information_mismatch', 'unreadable', 'unsupported',
  'entered_in_error', 'other',
] as const;

export const INVALIDATION_REASONS = [
  'authority_changed', 'document_revoked', 'information_corrected', 'entered_in_error', 'other',
] as const;

export const RELEASE_VERIFICATION_POLICIES = [
  'government_photo_id', 'documented_familiarity',
  'government_photo_id_or_documented_familiarity',
  'government_photo_id_and_secondary_check',
] as const;
export const RELEASE_REVOCATION_REASONS = ['authority_withdrawn', 'safety_change', 'superseded', 'entered_in_error'] as const;
export const RELEASE_RULE_KINDS = ['deny', 'manager_review'] as const;
export const RELEASE_AUTHORITY_BASES = ['guardian_record', 'reviewed_custody_evidence', 'reviewed_delegation_evidence'] as const;
export const RESTRICTION_AUTHORITY_BASES = ['guardian_record', 'reviewed_custody_evidence'] as const;
export const CONSENT_PURPOSES = ['off_site_activity', 'emergency_health_care', 'medication_administration', 'internal_media', 'external_media', 'marketing', 'research', 'optional_service', 'information_sharing'] as const;
export const CONSENT_SIGNER_REQUIREMENTS = ['guardian_record', 'legal_decision_maker'] as const;
export const CONSENT_WITHDRAWAL_REASONS = ['signer_withdrew', 'authority_changed', 'superseded', 'entered_in_error'] as const;

export type EffectiveRecordState = 'scheduled' | 'current' | 'expired' | 'revoked' | 'withdrawn' | 'supporting_evidence_unavailable';

export function effectiveRecordState(record: { effective_from: string; effective_until: string; effective_status?: AuthorityRecordEffectiveStatus; revoked_at?: string | null; withdrawn_at?: string | null }, now = Date.now()): EffectiveRecordState {
  if (record.effective_status) {
    return record.effective_status === 'effective' ? 'current' : record.effective_status;
  }
  if (record.revoked_at) return 'revoked';
  if (record.withdrawn_at) return 'withdrawn';
  if (Date.parse(record.effective_from) > now) return 'scheduled';
  if (Date.parse(record.effective_until) <= now) return 'expired';
  return 'current';
}

export function activeAuthorityPeople(workspace: FamilyAuthorityWorkspaceRecord): AuthorityPerson[] {
  return workspace.people.filter((person) => person.status === 'active' && Boolean(person.current_version));
}

export function explicitlySelectedCurrentPerson(
  people: readonly AuthorityPerson[],
  personId: string,
  basis?: ReviewedAuthorityBasis,
): AuthorityPerson | null {
  if (!personId) return null;
  return people.find((person) => person.id === personId
    && person.status === 'active'
    && Boolean(person.current_version)
    && (!basis || personCanUseBasis(person, basis))) || null;
}

export function reviewedEvidenceForBasis(workspace: FamilyAuthorityWorkspaceRecord, basis: ReviewedAuthorityBasis, actorUserId?: string): AuthorityEvidence[] {
  const evidenceKind = basis === 'guardian_record'
    ? 'guardian_attestation'
    : basis === 'reviewed_custody_evidence'
      ? 'custody_document'
      : basis === 'reviewed_delegation_evidence'
        ? 'signed_release_delegation'
        : null;
  if (!evidenceKind) return [];
  return workspace.evidence.filter((item) => item.evidence_kind === evidenceKind
    && item.valid_now
    && item.lifecycle_status === 'reviewed'
    && Boolean(item.current_assessment)
    && (!actorUserId || item.current_assessment?.actor_user_id !== actorUserId));
}

export function signedConsentEvidence(workspace: FamilyAuthorityWorkspaceRecord, actorUserId?: string): AuthorityEvidence[] {
  return workspace.evidence.filter((item) => item.evidence_kind === 'signed_consent'
    && item.valid_now
    && item.lifecycle_status === 'reviewed'
    && Boolean(item.current_assessment)
    && (!actorUserId || item.current_assessment?.actor_user_id !== actorUserId));
}

export function personCanUseBasis(person: AuthorityPerson, basis: ReviewedAuthorityBasis): boolean {
  return !['guardian_record', 'reviewed_delegation_evidence'].includes(basis) || person.source.kind === 'guardian';
}

export function releaseRuleRequiresDirectingPerson(basis: ReviewedAuthorityBasis): boolean {
  return basis === 'guardian_record';
}

export function currentConsentPolicies(policies: readonly ConsentPolicyVersion[], now = Date.now()): ConsentPolicyVersion[] {
  const current = policies.filter((policy) => Date.parse(policy.effective_from) <= now && now < Date.parse(policy.effective_until));
  const latest = new Map<string, ConsentPolicyVersion>();
  current.forEach((policy) => {
    const existing = latest.get(policy.purpose_code);
    if (!existing || policy.version_number > existing.version_number) latest.set(policy.purpose_code, policy);
  });
  return [...latest.values()].sort((left, right) => left.title.localeCompare(right.title));
}

export function authorityLabel(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

export function emptyAuthorityPersonFacts(): AuthorityPersonFacts {
  return {
    first_name: '', middle_name: null, last_name: '', preferred_name: null,
    relationship_kind: 'parent', relationship_detail: null, email: null, primary_phone: null,
  };
}

export interface AuthorityPersonSourceOption {
  key: string;
  label: string;
  source: AuthorityPersonSource;
  facts: AuthorityPersonFacts;
  disabled: boolean;
}

export function authorityPersonSourceOptions(detail: FamilyDetailRecord, people: readonly AuthorityPerson[]): AuthorityPersonSourceOption[] {
  const linkedGuardianIds = new Set(people.flatMap((person) => person.source.kind === 'guardian' ? [person.source.guardian_id] : []));
  const linkedContactIds = new Set(people.flatMap((person) => person.source.kind === 'emergency_contact' ? [person.source.emergency_contact_id] : []));
  const manual: AuthorityPersonSourceOption = { key: 'manual', label: 'Enter a new authority person', source: { kind: 'manual' }, facts: emptyAuthorityPersonFacts(), disabled: false };
  const guardians = detail.guardians.map((guardian): AuthorityPersonSourceOption => ({
    key: `guardian:${guardian.id}`,
    label: `${guardian.first_name} ${guardian.last_name} · saved guardian`,
    source: { kind: 'guardian', guardian_id: guardian.id },
    facts: {
      first_name: guardian.first_name,
      middle_name: null,
      last_name: guardian.last_name,
      preferred_name: null,
      relationship_kind: 'parent',
      relationship_detail: null,
      email: guardian.email || null,
      primary_phone: guardian.cell_phone || null,
    },
    disabled: linkedGuardianIds.has(guardian.id),
  }));
  const contacts = detail.emergency_contacts.map((contact): AuthorityPersonSourceOption => ({
    key: `emergency_contact:${contact.id}`,
    label: `${contact.first_name} ${contact.last_name} · saved emergency contact`,
    source: { kind: 'emergency_contact', emergency_contact_id: contact.id },
    facts: {
      first_name: contact.first_name,
      middle_name: null,
      last_name: contact.last_name,
      preferred_name: null,
      relationship_kind: 'other',
      relationship_detail: contact.relationship,
      email: null,
      primary_phone: contact.cell_phone || null,
    },
    disabled: linkedContactIds.has(contact.id),
  }));
  return [manual, ...guardians, ...contacts];
}

export function validateAuthorityPersonFacts(facts: AuthorityPersonFacts): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!facts.first_name.trim()) errors.first_name = 'Enter a first name.';
  if (!facts.last_name.trim()) errors.last_name = 'Enter a last name.';
  if (facts.first_name.trim().length > 100) errors.first_name = 'Use 100 characters or fewer.';
  if (facts.last_name.trim().length > 100) errors.last_name = 'Use 100 characters or fewer.';
  if (facts.relationship_kind === 'other' && !facts.relationship_detail?.trim()) errors.relationship_detail = 'Describe this relationship.';
  if (facts.relationship_kind !== 'other' && facts.relationship_detail !== null) errors.relationship_detail = 'Relationship detail is allowed only for Other.';
  if (facts.email && (!facts.email.includes('@') || facts.email.length > 320)) errors.email = 'Enter a valid email address.';
  if (facts.primary_phone && facts.primary_phone.length > 30) errors.primary_phone = 'Use 30 characters or fewer.';
  return errors;
}

export function normalizedAuthorityFacts(facts: AuthorityPersonFacts): AuthorityPersonFacts {
  const optional = (value: string | null) => value?.trim() || null;
  return {
    first_name: facts.first_name.trim(),
    middle_name: optional(facts.middle_name),
    last_name: facts.last_name.trim(),
    preferred_name: optional(facts.preferred_name),
    relationship_kind: facts.relationship_kind,
    relationship_detail: facts.relationship_kind === 'other' ? optional(facts.relationship_detail) : null,
    email: optional(facts.email),
    primary_phone: optional(facts.primary_phone),
  };
}

export interface EvidenceReviewAssignment {
  recordedByCurrentActor: boolean;
  uploadedByCurrentActor: boolean;
  requiresIndependentReviewer: boolean;
  canCurrentActorReview: boolean;
}

export function evidenceReviewAssignment(
  workspace: FamilyAuthorityWorkspaceRecord,
  evidence: AuthorityEvidence,
  actorUserId: string,
): EvidenceReviewAssignment {
  const evidenceObject = evidence.evidence_object_id
    ? workspace.evidence_objects.find((item) => item.id === evidence.evidence_object_id)
    : null;
  const recordedByCurrentActor = Boolean(actorUserId) && evidence.recorded_by_user_id === actorUserId;
  const uploadedByCurrentActor = Boolean(actorUserId) && evidenceObject?.uploaded_by_user_id === actorUserId;
  const requiresIndependentReviewer = recordedByCurrentActor || uploadedByCurrentActor;
  return {
    recordedByCurrentActor,
    uploadedByCurrentActor,
    requiresIndependentReviewer,
    canCurrentActorReview: Boolean(actorUserId) && !requiresIndependentReviewer,
  };
}

export function evidenceActions(
  evidence: AuthorityEvidence,
  assignment: EvidenceReviewAssignment | null,
): readonly ('review' | 'reject' | 'invalidate' | 'supersede')[] {
  if (evidence.lifecycle_status === 'unreviewed' && evidence.effective_status === 'unreviewed') {
    return assignment?.canCurrentActorReview ? ['review', 'reject'] : ['reject'];
  }
  if (evidence.lifecycle_status === 'reviewed') return ['invalidate', 'supersede'];
  return [];
}

export function reviewEpistemicOptions(kind: AuthorityEvidenceKind): readonly AuthorityEvidenceEpistemicStatus[] {
  return DOCUMENT_EVIDENCE_KINDS.has(kind) ? ['document_observed'] : ['reported'];
}

export function evidenceObjectCanScan(object: AuthorityEvidenceObject): boolean {
  return object.version === 1
    && object.lifecycle_status === 'quarantined'
    && !object.valid_for_evidence
    && object.current_assessment?.version_number === 1
    && object.current_assessment.decision === 'quarantined';
}

export function attachableEvidenceObjects(workspace: FamilyAuthorityWorkspaceRecord, kind: AuthorityEvidenceKind): AuthorityEvidenceObject[] {
  const used = new Set(workspace.evidence.map((item) => item.evidence_object_id).filter((value): value is string => Boolean(value)));
  return workspace.evidence_objects.filter((item) => item.evidence_kind === kind && item.valid_for_evidence && !used.has(item.id));
}

export function reviewedReplacementEvidence(workspace: FamilyAuthorityWorkspaceRecord, excludedEvidenceId: string): AuthorityEvidence[] {
  return workspace.evidence.filter((item) => item.id !== excludedEvidenceId && item.valid_now && item.lifecycle_status === 'reviewed');
}

export type AuthorityFocusKind =
  | 'person'
  | 'evidence'
  | 'object'
  | 'release_authorization'
  | 'release_rule'
  | 'consent';

export interface AuthorityDeepLink {
  kind: AuthorityFocusKind;
  id: string;
}

export type AuthorityWorkspaceTab = 'people' | 'evidence' | 'documents' | 'decisions';

export function authorityWorkspaceTabForFocus(focus: AuthorityDeepLink): AuthorityWorkspaceTab {
  if (focus.kind === 'person') return 'people';
  if (focus.kind === 'evidence') return 'evidence';
  if (focus.kind === 'object') return 'documents';
  return 'decisions';
}

export function shouldClearAuthorityFocusForTabSelection(
  focus: AuthorityDeepLink | null,
  selectedTab: AuthorityWorkspaceTab,
): boolean {
  return Boolean(focus && selectedTab !== authorityWorkspaceTabForFocus(focus));
}

export type AuthorityDecisionFocus = {
  kind: 'release_authorization' | 'release_rule' | 'consent';
  id: string;
};

export function isAuthorityDecisionFocus(focus: AuthorityDeepLink | null): focus is AuthorityDecisionFocus {
  return focus?.kind === 'release_authorization' || focus?.kind === 'release_rule' || focus?.kind === 'consent';
}

export type AuthorityRouteFocus =
  | { state: 'none'; focus: null; message: null }
  | { state: 'valid'; focus: AuthorityDeepLink; message: null }
  | { state: 'invalid'; focus: null; message: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const AUTHORITY_ROUTE_KEYS = {
  authority_person_id: 'person',
  authority_evidence_id: 'evidence',
  authority_evidence_object_id: 'object',
  release_authorization_id: 'release_authorization',
  release_rule_id: 'release_rule',
  consent_id: 'consent',
} as const satisfies Record<string, AuthorityFocusKind>;

export function parseAuthorityDeepLink(search: string): AuthorityRouteFocus {
  const parameters = new URLSearchParams(search);
  const entries = [...parameters.entries()];
  const authorityEntries = entries.filter(([key]) => Object.prototype.hasOwnProperty.call(AUTHORITY_ROUTE_KEYS, key));
  if (!authorityEntries.length) return { state: 'none', focus: null, message: null };
  if (authorityEntries.length !== 1 || entries.length !== 1) {
    return {
      state: 'invalid',
      focus: null,
      message: 'This authority link is ambiguous or contains unsupported parameters. CareSync did not select a different record.',
    };
  }
  const [key, rawId] = authorityEntries[0];
  if (!UUID.test(rawId)) {
    return {
      state: 'invalid',
      focus: null,
      message: 'This authority link contains an invalid record identifier. CareSync did not select a different record.',
    };
  }
  return {
    state: 'valid',
    focus: {
      kind: AUTHORITY_ROUTE_KEYS[key as keyof typeof AUTHORITY_ROUTE_KEYS],
      id: rawId.toLowerCase(),
    },
    message: null,
  };
}

export function authorityWorkspaceFocusExists(
  workspace: FamilyAuthorityWorkspaceRecord,
  focus: AuthorityDeepLink,
): boolean {
  if (focus.kind === 'person') return workspace.people.some((item) => item.id === focus.id);
  if (focus.kind === 'evidence') return workspace.evidence.some((item) => item.id === focus.id);
  if (focus.kind === 'object') return workspace.evidence_objects.some((item) => item.id === focus.id);
  return workspace.children.some((child) => {
    if (focus.kind === 'release_authorization') return child.release_authorizations.some((item) => item.id === focus.id);
    if (focus.kind === 'release_rule') return child.release_rules.some((item) => item.id === focus.id);
    return child.consent_decisions.some((item) => item.id === focus.id);
  });
}

export function authorityWorkspaceCounts(workspace: FamilyAuthorityWorkspaceRecord, actorUserId = '') {
  const unreviewed = workspace.evidence.filter((item) => item.lifecycle_status === 'unreviewed');
  const actionableAssignments = unreviewed
    .filter((item) => item.effective_status === 'unreviewed')
    .map((item) => evidenceReviewAssignment(workspace, item, actorUserId));
  return {
    activePeople: workspace.people.filter((item) => item.status === 'active').length,
    unreviewedEvidence: unreviewed.length,
    awaitingYourReview: actionableAssignments.filter((item) => item.canCurrentActorReview).length,
    recordedByYouAwaitingReview: actionableAssignments.filter((item) => item.requiresIndependentReviewer).length,
    validEvidence: workspace.evidence.filter((item) => item.valid_now).length,
    authorityHistoryChildren: workspace.children.filter((item) => item.authority_revision > 0).length,
  };
}
