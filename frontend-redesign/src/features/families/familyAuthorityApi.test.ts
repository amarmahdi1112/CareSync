import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isCommandOutcomeUnknown, isCommandRejectedBeforeCommit } from '../../api/childcareCommand';
import {
  FamilyAuthorityApiError,
  parseAuthorityEvidence,
  parseAuthorityEvidenceObject,
  parseChildConsentDecision,
  parseConsentPolicy,
  parseFamilyAuthorityWorkspace,
  parseReleaseAuthorization,
  parseReleaseRule,
  publishConsentPolicy,
  scanAuthorityEvidenceObject,
} from './familyAuthorityApi';

const ORGANIZATION_ID = '10000000-0000-4000-8000-000000000001';
const FAMILY_ID = '20000000-0000-4000-8000-000000000002';
const OBJECT_ID = '30000000-0000-4000-8000-000000000003';
const ACTOR_ID = '40000000-0000-4000-8000-000000000004';
const ASSESSMENT_ID = '50000000-0000-4000-8000-000000000005';
const CHILD_ID = '70000000-0000-4000-8000-000000000007';
const PERSON_ID = '80000000-0000-4000-8000-000000000008';
const PERSON_VERSION_ID = '90000000-0000-4000-8000-000000000009';
const EVIDENCE_ID = 'a0000000-0000-4000-8000-00000000000a';

function quarantinedObject(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: OBJECT_ID,
    organization_id: ORGANIZATION_ID,
    family_id: FAMILY_ID,
    evidence_kind: 'identity_document',
    version: 1,
    lifecycle_status: 'quarantined',
    valid_for_evidence: false,
    object_version: 1,
    media_type: 'application/pdf',
    byte_size: 4096,
    content_sha256: 'a'.repeat(64),
    original_filename: null,
    uploaded_by_user_id: ACTOR_ID,
    created_at: '2026-07-17T12:00:00Z',
    current_assessment: {
      id: ASSESSMENT_ID,
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

function unreviewedEvidence(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: '60000000-0000-4000-8000-000000000006',
    organization_id: ORGANIZATION_ID,
    family_id: FAMILY_ID,
    evidence_kind: 'guardian_attestation',
    source_label: 'Guardian statement',
    recorded_by_user_id: ACTOR_ID,
    storage: null,
    evidence_object_id: null,
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

describe('family authority API adapters', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => key === 'caresync-redesign-organization' ? ORGANIZATION_ID : 'test-token',
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('accepts the exact initial quarantine object including a redacted filename', () => {
    expect(parseAuthorityEvidenceObject(quarantinedObject())).toMatchObject({
      id: OBJECT_ID,
      object_version: 1,
      original_filename: null,
      lifecycle_status: 'quarantined',
      current_assessment: { version_number: 1, decision: 'quarantined', scanner_engine: null },
    });
  });

  it('requires the immutable recorder identity on every evidence projection', () => {
    expect(parseAuthorityEvidence(unreviewedEvidence())).toMatchObject({
      recorded_by_user_id: ACTOR_ID,
      lifecycle_status: 'unreviewed',
    });
    const missingRecorder = unreviewedEvidence();
    delete missingRecorder.recorded_by_user_id;
    expect(() => parseAuthorityEvidence(missingRecorder)).toThrow(
      'unexpected authority evidence shape',
    );
    expect(() =>
      parseAuthorityEvidence(
        unreviewedEvidence({ recorded_by_user_id: 'not-a-user-id' }),
      ),
    ).toThrow(FamilyAuthorityApiError);
  });

  it('accepts an exact clean scan and rejects forged or incoherent scan projections', () => {
    const clean = quarantinedObject({
      version: 2,
      lifecycle_status: 'clean',
      valid_for_evidence: true,
      current_assessment: {
        id: ASSESSMENT_ID,
        version_number: 2,
        decision: 'clean',
        scanner_engine: 'clamav',
        scanner_version: '1.4',
        scanner_signature: null,
        reason_code: null,
        actor_user_id: ACTOR_ID,
        created_at: '2026-07-17T12:01:00Z',
      },
    });
    expect(parseAuthorityEvidenceObject(clean).valid_for_evidence).toBe(true);
    expect(() => parseAuthorityEvidenceObject({ ...clean, valid_for_evidence: false })).toThrow('incoherent authority-evidence object projection');
    expect(() => parseAuthorityEvidenceObject({ ...clean, object_version: '1' })).toThrow(FamilyAuthorityApiError);
    expect(() => parseAuthorityEvidenceObject({ ...clean, secret_storage_path: '/private/file' })).toThrow('unexpected authority-evidence object shape');
  });

  it('fails closed when a workspace or nested object crosses its authenticated boundary', () => {
    const workspace = {
      organization_id: ORGANIZATION_ID,
      family_id: FAMILY_ID,
      generated_at: '2026-07-17T12:00:00Z',
      people: [],
      evidence_objects: [quarantinedObject()],
      evidence: [],
      children: [],
    };
    expect(parseFamilyAuthorityWorkspace(workspace, ORGANIZATION_ID, FAMILY_ID).evidence_objects).toHaveLength(1);
    expect(() => parseFamilyAuthorityWorkspace({ ...workspace, organization_id: ACTOR_ID }, ORGANIZATION_ID, FAMILY_ID)).toThrow('crossed the authenticated record boundary');
    expect(() => parseFamilyAuthorityWorkspace({ ...workspace, evidence_objects: [quarantinedObject({ family_id: ACTOR_ID })] }, ORGANIZATION_ID, FAMILY_ID)).toThrow('cross-boundary record');
  });

  it.each([
    'configured_scanner_unavailable',
    'malware_scanner_unavailable',
    'malware_scanner_failed',
    'malware_scanner_definitions_unverified',
    'malware_scanner_definitions_stale',
    'family_authority_unavailable',
    'family_evidence_vault_unavailable',
  ])('treats the scan route\'s exact %s 503 contract as an authoritative pre-commit rejection', async (code) => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: { code } }),
    })));

    const caught = await scanAuthorityEvidenceObject(
      FAMILY_ID,
      OBJECT_ID,
      1,
      ORGANIZATION_ID,
      '60000000-0000-4000-8000-000000000006',
    ).catch((error) => error);

    expect(isCommandRejectedBeforeCommit(caught)).toBe(true);
    expect(isCommandOutcomeUnknown(caught)).toBe(false);
    expect(caught).toMatchObject({ cause: { status: 503, code, origin: 'http' } });
  });

  it('keeps an unrecognized or malformed scan 503 in unknown-outcome reconciliation', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: { code: 'scanner_busy' } }) })
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => { throw new SyntaxError('bad json'); } });
    vi.stubGlobal('fetch', fetchMock);

    for (const operation of [
      '60000000-0000-4000-8000-000000000006',
      '60000000-0000-4000-8000-000000000007',
    ]) {
      const caught = await scanAuthorityEvidenceObject(
        FAMILY_ID,
        OBJECT_ID,
        1,
        ORGANIZATION_ID,
        operation,
      ).catch((error) => error);
      expect(isCommandRejectedBeforeCommit(caught)).toBe(false);
      expect(isCommandOutcomeUnknown(caught)).toBe(true);
    }
  });

  it('strictly parses release grants and restrictions with finite windows and exact safe codes', () => {
    const grant = {
      id: OBJECT_ID, organization_id: ORGANIZATION_ID, family_id: FAMILY_ID, child_id: CHILD_ID,
      recipient_person_id: PERSON_ID, verification_policy_code: 'government_photo_id',
      grantor: { person_id: PERSON_ID, person_version_id: PERSON_VERSION_ID, authority_basis: 'guardian_record', basis_evidence_id: EVIDENCE_ID, basis_evidence_assessment_id: ASSESSMENT_ID },
      effective_from: '2026-07-17T12:00:00Z', effective_until: '2026-08-17T12:00:00Z', version: 1,
      revoked_at: null, revocation_reason_code: null, effective_status: 'effective', effective_now: true, evaluated_at: '2026-07-18T12:00:00Z', authority_revision: 1,
      created_at: '2026-07-17T12:00:00Z', updated_at: '2026-07-17T12:00:00Z',
    };
    expect(parseReleaseAuthorization(grant)).toMatchObject({ child_id: CHILD_ID, grantor: { basis_evidence_assessment_id: ASSESSMENT_ID } });
    expect(() => parseReleaseAuthorization({ ...grant, effective_until: grant.effective_from })).toThrow('effective window');
    expect(() => parseReleaseAuthorization({ ...grant, private_note: 'leak' })).toThrow('unexpected release authorization shape');

    const rule = {
      id: OBJECT_ID, organization_id: ORGANIZATION_ID, family_id: FAMILY_ID, child_id: CHILD_ID,
      rule_kind: 'deny', scope: { kind: 'all_recipients' }, directing_person: null,
      authority_basis_code: 'reviewed_custody_evidence', basis_evidence_id: EVIDENCE_ID, basis_evidence_assessment_id: ASSESSMENT_ID,
      safe_explanation_code: 'release_restricted', confidential_reason: 'Admin-only safety review',
      effective_from: '2026-07-17T12:00:00Z', effective_until: '2026-08-17T12:00:00Z', version: 1,
      revoked_at: null, revocation_reason_code: null, effective_status: 'supporting_evidence_unavailable', effective_now: false, evaluated_at: '2026-07-18T12:00:00Z', authority_revision: 2,
      created_at: '2026-07-17T12:00:00Z', updated_at: '2026-07-17T12:00:00Z',
    };
    expect(parseReleaseRule(rule)).toMatchObject({ rule_kind: 'deny', safe_explanation_code: 'release_restricted' });
    expect(() => parseReleaseRule({ ...rule, safe_explanation_code: 'manager_review_required' })).toThrow('incoherent release-rule projection');
  });

  it('requires derived consent-policy identity and two exact child-consent evidence tuples', () => {
    const policy = {
      id: OBJECT_ID, organization_id: ORGANIZATION_ID, purpose_code: 'off_site_activity', version_number: 1,
      title: 'Field trip consent', content_text: 'I authorize the described field trip.', content_reference: `/consent-policies/${OBJECT_ID}`,
      content_sha256: 'b'.repeat(64), signer_authority_requirement: 'guardian_record',
      effective_from: '2026-07-17T12:00:00Z', effective_until: '2027-07-17T12:00:00Z', published_at: '2026-07-17T12:00:00Z',
    };
    expect(parseConsentPolicy(policy)).toMatchObject({ content_text: expect.stringContaining('authorize'), content_sha256: 'b'.repeat(64) });
    expect(() => parseConsentPolicy({ ...policy, content_sha256: 'B'.repeat(64) })).toThrow('content hash');
    expect(() => parseConsentPolicy({ ...policy, content_reference: '/public/policy' })).toThrow('content reference');

    const decision = {
      id: OBJECT_ID, organization_id: ORGANIZATION_ID, family_id: FAMILY_ID, child_id: CHILD_ID,
      purpose_code: 'off_site_activity', policy_version_id: OBJECT_ID,
      signer: { person_id: PERSON_ID, person_version_id: PERSON_VERSION_ID, authority_basis: 'guardian_record', authority_evidence_id: EVIDENCE_ID, authority_evidence_assessment_id: ASSESSMENT_ID },
      evidence_id: 'b0000000-0000-4000-8000-00000000000b', evidence_assessment_id: 'c0000000-0000-4000-8000-00000000000c',
      decision: 'granted', scope: { kind: 'policy' }, effective_from: '2026-07-17T12:00:00Z', effective_until: '2026-08-17T12:00:00Z',
      version: 1, withdrawn_at: null, withdrawal_reason_code: null, effective_status: 'effective', effective_now: true, evaluated_at: '2026-07-18T12:00:00Z', authority_revision: 3,
      created_at: '2026-07-17T12:00:00Z', updated_at: '2026-07-17T12:00:00Z',
    };
    expect(parseChildConsentDecision(decision)).toMatchObject({ signer: { authority_evidence_id: EVIDENCE_ID }, evidence_id: 'b0000000-0000-4000-8000-00000000000b' });
    const missingSignerEvidence = { ...decision, signer: { person_id: PERSON_ID, person_version_id: PERSON_VERSION_ID, authority_basis: 'guardian_record' } };
    expect(() => parseChildConsentDecision(missingSignerEvidence)).toThrow('unexpected child-consent signer shape');
  });

  it('publishes plain policy content while accepting only the server-derived reference and digest', async () => {
    const operationId = 'd0000000-0000-4000-8000-00000000000d';
    const policy = {
      id: OBJECT_ID, organization_id: ORGANIZATION_ID, purpose_code: 'off_site_activity', version_number: 2,
      title: 'Field trip consent', content_text: 'Plain reviewed policy content.', content_reference: `/consent-policies/${OBJECT_ID}`,
      content_sha256: 'd'.repeat(64), signer_authority_requirement: 'guardian_record',
      effective_from: '2026-07-17T12:00:00Z', effective_until: '2027-07-17T12:00:00Z', published_at: '2026-07-17T12:00:00Z',
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
      ok: true, status: 201,
      json: async () => ({
        resource: policy,
        receipt: { organization_id: ORGANIZATION_ID, client_operation_id: operationId, command_type: 'organization.consent.policy.publish', target_type: 'consent', target_id: OBJECT_ID, committed_version: 2, committed_at: '2026-07-17T12:00:00Z', facility_id: null, action_route: `/consent-policies/${OBJECT_ID}` },
        replayed: false,
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(publishConsentPolicy({ purpose_code: 'off_site_activity', version_number: 2, title: 'Field trip consent', content_text: 'Plain reviewed policy content.', signer_authority_requirement: 'guardian_record', effective_from: '2026-07-17T12:00:00Z', effective_until: '2027-07-17T12:00:00Z' }, ORGANIZATION_ID, operationId)).resolves.toMatchObject({ resource: { content_reference: `/consent-policies/${OBJECT_ID}`, content_sha256: 'd'.repeat(64) } });
    const body = JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body));
    expect(body).toMatchObject({ client_operation_id: operationId, content_text: 'Plain reviewed policy content.' });
    expect(body).not.toHaveProperty('content_reference');
    expect(body).not.toHaveProperty('content_sha256');
  });

  it('treats the disabled A2 gate as an authoritative pre-commit rejection', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ detail: { code: 'family_authority_activation_unavailable' } }) })));
    const caught = await publishConsentPolicy({ purpose_code: 'off_site_activity', version_number: 1, title: 'Policy', content_text: 'Content', signer_authority_requirement: 'guardian_record', effective_from: '2026-07-17T12:00:00Z', effective_until: '2027-07-17T12:00:00Z' }, ORGANIZATION_ID, 'd0000000-0000-4000-8000-00000000000d').catch((caughtError) => caughtError);
    expect(isCommandRejectedBeforeCommit(caught)).toBe(true);
    expect(isCommandOutcomeUnknown(caught)).toBe(false);
  });
});
