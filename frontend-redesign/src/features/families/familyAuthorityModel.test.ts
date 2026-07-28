import { describe, expect, it } from 'vitest';
import type { AuthorityEvidence, AuthorityEvidenceObject, FamilyAuthorityWorkspaceRecord } from './familyAuthorityTypes';
import {
  currentConsentPolicies,
  effectiveRecordState,
  explicitlySelectedCurrentPerson,
  attachableEvidenceObjects,
  authorityWorkspaceTabForFocus,
  authorityWorkspaceCounts,
  authorityWorkspaceFocusExists,
  evidenceActions,
  evidenceReviewAssignment,
  evidenceObjectCanScan,
  normalizedAuthorityFacts,
  parseAuthorityDeepLink,
  personCanUseBasis,
  reviewEpistemicOptions,
  reviewedEvidenceForBasis,
  releaseRuleRequiresDirectingPerson,
  signedConsentEvidence,
  shouldClearAuthorityFocusForTabSelection,
  validateAuthorityPersonFacts,
} from './familyAuthorityModel';

const PERSON_ID = '10000000-0000-4000-8000-000000000001';
const EVIDENCE_ID = '20000000-0000-4000-8000-000000000002';
const OBJECT_ID = '30000000-0000-4000-8000-000000000003';
const ACTOR_ID = '60000000-0000-4000-8000-000000000006';
const REVIEWER_ID = '70000000-0000-4000-8000-000000000007';

function evidence(overrides: Partial<AuthorityEvidence> = {}): AuthorityEvidence {
  return {
    id: EVIDENCE_ID,
    organization_id: '40000000-0000-4000-8000-000000000004',
    family_id: '50000000-0000-4000-8000-000000000005',
    evidence_kind: 'identity_document',
    source_label: 'Internal identity review',
    recorded_by_user_id: ACTOR_ID,
    storage: null,
    evidence_object_id: OBJECT_ID,
    issued_at: null,
    captured_at: null,
    expires_at: null,
    created_at: '2026-07-17T12:00:00Z',
    version: 1,
    lifecycle_status: 'unreviewed',
    effective_status: 'unreviewed',
    valid_now: false,
    evaluated_at: '2026-07-17T12:00:00Z',
    current_assessment: null,
    ...overrides,
  };
}

function object(overrides: Partial<AuthorityEvidenceObject> = {}): AuthorityEvidenceObject {
  return {
    id: OBJECT_ID,
    organization_id: '40000000-0000-4000-8000-000000000004',
    family_id: '50000000-0000-4000-8000-000000000005',
    evidence_kind: 'identity_document',
    version: 1,
    lifecycle_status: 'quarantined',
    valid_for_evidence: false,
    object_version: 1,
    media_type: 'application/pdf',
    byte_size: 1_024,
    content_sha256: 'a'.repeat(64),
    original_filename: null,
    uploaded_by_user_id: ACTOR_ID,
    created_at: '2026-07-17T12:00:00Z',
    current_assessment: {
      id: '70000000-0000-4000-8000-000000000007',
      version_number: 1,
      decision: 'quarantined',
      scanner_engine: null,
      scanner_version: null,
      scanner_signature: null,
      reason_code: null,
      actor_user_id: ACTOR_ID,
      created_at: '2026-07-17T12:00:00Z',
    },
    ...overrides,
  };
}

function workspace(overrides: Partial<FamilyAuthorityWorkspaceRecord> = {}): FamilyAuthorityWorkspaceRecord {
  return {
    organization_id: '40000000-0000-4000-8000-000000000004',
    family_id: '50000000-0000-4000-8000-000000000005',
    generated_at: '2026-07-17T12:00:00Z',
    people: [],
    evidence_objects: [],
    evidence: [],
    children: [],
    ...overrides,
  };
}

describe('family authority workspace model', () => {
  it('accepts only opaque receipt deep links and supports quarantine objects', () => {
    expect(parseAuthorityDeepLink(`?authority_person_id=${PERSON_ID}`).focus).toEqual({ kind: 'person', id: PERSON_ID });
    expect(parseAuthorityDeepLink(`?authority_evidence_id=${EVIDENCE_ID}`).focus).toEqual({ kind: 'evidence', id: EVIDENCE_ID });
    expect(parseAuthorityDeepLink(`?authority_evidence_object_id=${OBJECT_ID}`).focus).toEqual({ kind: 'object', id: OBJECT_ID });
    expect(parseAuthorityDeepLink(`?release_authorization_id=${PERSON_ID}`).focus).toEqual({ kind: 'release_authorization', id: PERSON_ID });
    expect(parseAuthorityDeepLink(`?release_rule_id=${EVIDENCE_ID}`).focus?.kind).toBe('release_rule');
    expect(parseAuthorityDeepLink(`?consent_id=${OBJECT_ID}`).focus?.kind).toBe('consent');
    expect(parseAuthorityDeepLink(`?authority_person_id=${PERSON_ID}&authority_evidence_id=${EVIDENCE_ID}`).state).toBe('invalid');
    expect(parseAuthorityDeepLink(`?consent_id=${OBJECT_ID}&tab=decisions`).state).toBe('invalid');
    expect(parseAuthorityDeepLink(`?consent_id=${OBJECT_ID}&consent_id=${OBJECT_ID}`).state).toBe('invalid');
    expect(parseAuthorityDeepLink('?authority_person_id=private-name').state).toBe('invalid');
    expect(parseAuthorityDeepLink(`?toString=${PERSON_ID}`).state).toBe('none');
    expect(parseAuthorityDeepLink(`?constructor=${PERSON_ID}`).state).toBe('none');
    expect(parseAuthorityDeepLink(`?focus=family-status`).state).toBe('none');
  });

  it('clears receipt focus only when the user deliberately leaves its mapped tab', () => {
    const consentFocus = { kind: 'consent' as const, id: OBJECT_ID };
    const evidenceFocus = { kind: 'evidence' as const, id: EVIDENCE_ID };
    expect(authorityWorkspaceTabForFocus(consentFocus)).toBe('decisions');
    expect(authorityWorkspaceTabForFocus(evidenceFocus)).toBe('evidence');
    expect(shouldClearAuthorityFocusForTabSelection(consentFocus, 'decisions')).toBe(false);
    expect(shouldClearAuthorityFocusForTabSelection(consentFocus, 'people')).toBe(true);
    expect(shouldClearAuthorityFocusForTabSelection(null, 'people')).toBe(false);
  });

  it('normalizes facts and rejects an incoherent Other relationship', () => {
    const normalized = normalizedAuthorityFacts({
      first_name: '  Ada ', middle_name: ' ', last_name: ' Lovelace ', preferred_name: null,
      relationship_kind: 'parent', relationship_detail: 'must disappear', email: ' ada@example.test ', primary_phone: ' 555-0100 ',
    });
    expect(normalized).toMatchObject({ first_name: 'Ada', middle_name: null, last_name: 'Lovelace', relationship_detail: null, email: 'ada@example.test' });
    expect(validateAuthorityPersonFacts({ ...normalized, relationship_kind: 'other', relationship_detail: null })).toMatchObject({ relationship_detail: expect.any(String) });
  });

  it('allows scanning only the exact initial quarantine projection', () => {
    expect(evidenceObjectCanScan(object())).toBe(true);
    expect(evidenceObjectCanScan(object({ lifecycle_status: 'clean', valid_for_evidence: true }))).toBe(false);
    expect(evidenceObjectCanScan(object({ version: 2, current_assessment: { ...object().current_assessment, version_number: 2, decision: 'rejected', scanner_engine: 'clamav', scanner_version: '1', reason_code: 'invalid_document' } }))).toBe(false);
  });

  it('excludes already attached objects and exposes bounded lifecycle actions', () => {
    const clean = object({
      version: 2,
      lifecycle_status: 'clean',
      valid_for_evidence: true,
      current_assessment: { ...object().current_assessment, version_number: 2, decision: 'clean', scanner_engine: 'clamav', scanner_version: '1' },
    });
    expect(attachableEvidenceObjects(workspace({ evidence_objects: [clean] }), 'identity_document')).toEqual([clean]);
    expect(attachableEvidenceObjects(workspace({ evidence_objects: [clean], evidence: [evidence()] }), 'identity_document')).toEqual([]);
    const pending = evidence();
    expect(evidenceActions(pending, evidenceReviewAssignment(workspace({ evidence: [pending] }), pending, REVIEWER_ID))).toEqual(['review', 'reject']);
    expect(evidenceActions(evidence({ version: 2, lifecycle_status: 'reviewed', effective_status: 'reviewed', valid_now: true }), null)).toEqual(['invalidate', 'supersede']);
    expect(reviewEpistemicOptions('court_order')).toEqual(['document_observed']);
    expect(reviewEpistemicOptions('guardian_attestation')).toEqual(['reported']);
  });

  it('keeps makers out of Review while allowing independent owners to assess', () => {
    const pending = evidence();
    const next = workspace({ evidence_objects: [object()], evidence: [pending] });
    const maker = evidenceReviewAssignment(next, pending, ACTOR_ID);
    expect(maker).toMatchObject({ recordedByCurrentActor: true, uploadedByCurrentActor: true, requiresIndependentReviewer: true, canCurrentActorReview: false });
    expect(evidenceActions(pending, maker)).toEqual(['reject']);

    const independent = evidenceReviewAssignment(next, pending, REVIEWER_ID);
    expect(independent).toMatchObject({ requiresIndependentReviewer: false, canCurrentActorReview: true });
    expect(evidenceActions(pending, independent)).toEqual(['review', 'reject']);

    const uploaderOnlyEvidence = evidence({ recorded_by_user_id: REVIEWER_ID });
    expect(evidenceReviewAssignment(next, uploaderOnlyEvidence, ACTOR_ID).canCurrentActorReview).toBe(false);
  });

  it('labels child authority history without treating it as release readiness', () => {
    expect(authorityWorkspaceCounts(workspace({
      children: [
        { child_id: PERSON_ID, reviewed: false, authority_revision: 0, release_authorizations: [], release_rules: [], consent_decisions: [] },
        { child_id: EVIDENCE_ID, reviewed: true, authority_revision: 3, release_authorizations: [], release_rules: [], consent_decisions: [] },
      ],
    })).authorityHistoryChildren).toBe(1);
  });

  it('counts actor-specific review work and resolves only the exact decision lane', () => {
    const reviewerEvidence = evidence({ id: EVIDENCE_ID, recorded_by_user_id: REVIEWER_ID, evidence_object_id: null });
    const makerEvidence = evidence({ id: OBJECT_ID });
    const expiredEvidence = evidence({ id: REVIEWER_ID, recorded_by_user_id: REVIEWER_ID, evidence_object_id: null, effective_status: 'expired' });
    const authorization = { id: PERSON_ID } as FamilyAuthorityWorkspaceRecord['children'][number]['release_authorizations'][number];
    const rule = { id: EVIDENCE_ID } as FamilyAuthorityWorkspaceRecord['children'][number]['release_rules'][number];
    const consent = { id: OBJECT_ID } as FamilyAuthorityWorkspaceRecord['children'][number]['consent_decisions'][number];
    const next = workspace({
      evidence_objects: [object()],
      evidence: [reviewerEvidence, makerEvidence, expiredEvidence],
      children: [{ child_id: PERSON_ID, reviewed: true, authority_revision: 1, release_authorizations: [authorization], release_rules: [rule], consent_decisions: [consent] }],
    });
    expect(authorityWorkspaceCounts(next, ACTOR_ID)).toMatchObject({ unreviewedEvidence: 3, awaitingYourReview: 1, recordedByYouAwaitingReview: 1 });
    expect(authorityWorkspaceFocusExists(next, { kind: 'release_authorization', id: PERSON_ID })).toBe(true);
    expect(authorityWorkspaceFocusExists(next, { kind: 'release_rule', id: EVIDENCE_ID })).toBe(true);
    expect(authorityWorkspaceFocusExists(next, { kind: 'consent', id: OBJECT_ID })).toBe(true);
    expect(authorityWorkspaceFocusExists(next, { kind: 'consent', id: PERSON_ID })).toBe(false);
  });

  it('computes finite-window states and keeps only the latest currently effective policy version', () => {
    expect(effectiveRecordState({ effective_from: '2026-07-17T12:00:00Z', effective_until: '2026-08-17T12:00:00Z' }, Date.parse('2026-07-18T12:00:00Z'))).toBe('current');
    expect(effectiveRecordState({ effective_from: '2026-08-17T12:00:00Z', effective_until: '2026-09-17T12:00:00Z' }, Date.parse('2026-07-18T12:00:00Z'))).toBe('scheduled');
    expect(effectiveRecordState({ effective_from: '2026-07-01T12:00:00Z', effective_until: '2026-07-17T12:00:00Z' }, Date.parse('2026-07-18T12:00:00Z'))).toBe('expired');
    expect(effectiveRecordState({ effective_from: '2026-07-01T12:00:00Z', effective_until: '2026-08-17T12:00:00Z', revoked_at: '2026-07-16T12:00:00Z' }, Date.parse('2026-07-18T12:00:00Z'))).toBe('revoked');
    expect(effectiveRecordState({ effective_from: '2026-07-01T12:00:00Z', effective_until: '2026-08-17T12:00:00Z', effective_status: 'supporting_evidence_unavailable' }, Date.parse('2026-07-18T12:00:00Z'))).toBe('supporting_evidence_unavailable');
    const base = { organization_id: workspace().organization_id, purpose_code: 'off_site_activity' as const, title: 'Trip', content_text: 'Policy', content_reference: '/consent-policies/x', content_sha256: 'a'.repeat(64), signer_authority_requirement: 'guardian_record' as const, effective_from: '2026-07-01T00:00:00Z', effective_until: '2026-08-01T00:00:00Z', published_at: '2026-07-01T00:00:00Z' };
    const policies = [
      { ...base, id: PERSON_ID, version_number: 1 },
      { ...base, id: EVIDENCE_ID, version_number: 2 },
      { ...base, id: OBJECT_ID, purpose_code: 'marketing' as const, version_number: 1, effective_until: '2026-07-10T00:00:00Z' },
    ];
    expect(currentConsentPolicies(policies, Date.parse('2026-07-18T00:00:00Z'))).toEqual([policies[1]]);
  });

  it('enforces the locked evidence-kind matrix and excludes evidence reviewed by the activator', () => {
    const reviewer = '60000000-0000-4000-8000-000000000006';
    const reviewed = (kind: AuthorityEvidence['evidence_kind'], id: string, actor = reviewer): AuthorityEvidence => evidence({
      id, evidence_kind: kind, version: 2, lifecycle_status: 'reviewed', effective_status: 'reviewed', valid_now: true,
      current_assessment: { id: OBJECT_ID, evidence_id: id, version_number: 2, decision: 'reviewed', assessed_epistemic_status: kind === 'guardian_attestation' ? 'reported' : 'document_observed', reason_code: null, confidential_note: null, superseded_by_evidence_id: null, actor_user_id: actor, created_at: '2026-07-17T12:00:00Z' },
    });
    const custody = reviewed('custody_document', EVIDENCE_ID, PERSON_ID);
    const delegation = reviewed('signed_release_delegation', '70000000-0000-4000-8000-000000000007', PERSON_ID);
    const consent = reviewed('signed_consent', '80000000-0000-4000-8000-000000000008', PERSON_ID);
    const statement = reviewed('guardian_attestation', '90000000-0000-4000-8000-000000000009');
    const next = workspace({ evidence: [custody, delegation, consent, statement] });
    expect(reviewedEvidenceForBasis(next, 'reviewed_custody_evidence', reviewer)).toEqual([custody]);
    expect(reviewedEvidenceForBasis(next, 'reviewed_delegation_evidence', reviewer)).toEqual([delegation]);
    expect(reviewedEvidenceForBasis(next, 'guardian_record', reviewer)).toEqual([]);
    expect(reviewedEvidenceForBasis(next, 'other_reviewed_authority', reviewer)).toEqual([]);
    expect(signedConsentEvidence(next, reviewer)).toEqual([consent]);
    const basePerson = { status: 'active', source: { kind: 'manual' } } as unknown as FamilyAuthorityWorkspaceRecord['people'][number];
    const guardian = { ...basePerson, source: { kind: 'guardian', guardian_id: PERSON_ID } } as FamilyAuthorityWorkspaceRecord['people'][number];
    expect(personCanUseBasis(basePerson, 'reviewed_custody_evidence')).toBe(true);
    expect(personCanUseBasis(basePerson, 'reviewed_delegation_evidence')).toBe(false);
    expect(personCanUseBasis(guardian, 'reviewed_delegation_evidence')).toBe(true);
    expect(releaseRuleRequiresDirectingPerson('guardian_record')).toBe(true);
    expect(releaseRuleRequiresDirectingPerson('reviewed_custody_evidence')).toBe(false);
    const currentManual = { ...basePerson, id: PERSON_ID, current_version: { id: EVIDENCE_ID } } as FamilyAuthorityWorkspaceRecord['people'][number];
    const currentGuardian = { ...guardian, id: EVIDENCE_ID, current_version: { id: OBJECT_ID } } as FamilyAuthorityWorkspaceRecord['people'][number];
    expect(explicitlySelectedCurrentPerson([currentManual, currentGuardian], '')).toBeNull();
    expect(explicitlySelectedCurrentPerson([currentManual, currentGuardian], OBJECT_ID)).toBeNull();
    expect(explicitlySelectedCurrentPerson([currentManual, currentGuardian], PERSON_ID)).toBe(currentManual);
    expect(explicitlySelectedCurrentPerson([currentManual, currentGuardian], PERSON_ID, 'guardian_record')).toBeNull();
    expect(explicitlySelectedCurrentPerson([currentManual, currentGuardian], EVIDENCE_ID, 'guardian_record')).toBe(currentGuardian);
  });
});
