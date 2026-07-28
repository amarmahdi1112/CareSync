import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  CHILDCARE_COMMAND_TARGETS,
  CHILDCARE_COMMAND_TYPES,
  childcareCommandAdmissionOwnerId,
  childcareCommandAuthorityFamilyId,
  childcareCommandChildAuthorityOwnerId,
  childcareCommandEnrollmentOwnerId,
  ChildcareCommandReceiptProtocolError,
  fetchChildcareCommandReceipt,
  parseChildcareCommandReceipt,
  parseSafeLocalActionRoute,
} from './childcareCommandReceipt';

const ORGANIZATION_ID = '10000000-0000-4000-8000-000000000001';
const OPERATION_ID = '20000000-0000-4000-8000-000000000002';
const TARGET_ID = '30000000-0000-4000-8000-000000000003';
const CHILD_ID = '40000000-0000-4000-8000-000000000004';
const FACILITY_ID = '50000000-0000-4000-8000-000000000005';

function response(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    organization_id: ORGANIZATION_ID,
    client_operation_id: OPERATION_ID,
    command_type: 'family.update',
    target_type: 'family',
    target_id: TARGET_ID,
    committed_version: 4,
    committed_at: '2026-07-17T06:30:00Z',
    facility_id: null,
    action_route: `/families/${TARGET_ID}`,
    ...overrides,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('childcare command receipt contract', () => {
  it('accepts every exact childcare command and its locked target type', () => {
    for (const commandType of CHILDCARE_COMMAND_TYPES) {
      const targetType = CHILDCARE_COMMAND_TARGETS[commandType];
      const actionRoute = targetType === 'family'
        ? `/families/${TARGET_ID}`
        : targetType === 'child'
          ? `/children/${TARGET_ID}`
          : targetType === 'admission_application'
            ? `/admissions/applications/${TARGET_ID}`
            : targetType === 'admission_waitlist' || targetType === 'admission_offer'
              ? `/admissions/applications/${CHILD_ID}`
          : targetType === 'enrollment'
            ? `/children/${CHILD_ID}?enrollment_id=${TARGET_ID}`
            : targetType === 'release_authorization'
              ? `/children/${CHILD_ID}?release_authorization_id=${TARGET_ID}`
              : targetType === 'release_rule'
                ? `/children/${CHILD_ID}?release_rule_id=${TARGET_ID}`
                : targetType === 'consent'
                  ? commandType === 'organization.consent.policy.publish' ? `/consent-policies/${TARGET_ID}` : `/children/${CHILD_ID}?consent_id=${TARGET_ID}`
                  : `/families/${CHILD_ID}?${targetType === 'authority_person' ? 'authority_person_id' : targetType === 'authority_evidence' ? 'authority_evidence_id' : 'authority_evidence_object_id'}=${TARGET_ID}`;
      expect(parseChildcareCommandReceipt(response({
        command_type: commandType,
        target_type: targetType,
        action_route: actionRoute,
      })).commandType).toBe(commandType);
    }
  });

  it('binds admission targets to the application profile without PII or query metadata', () => {
    const application = parseChildcareCommandReceipt(response({
      command_type: 'admission.application.update',
      target_type: 'admission_application',
      action_route: `/admissions/applications/${TARGET_ID}`,
    }));
    expect(application.targetId).toBe(TARGET_ID);

    for (const [commandType, targetType] of [
      ['admission.waitlist.reopen_review', 'admission_waitlist'],
      ['admission.offer.withdraw', 'admission_offer'],
    ] as const) {
      const receipt = parseChildcareCommandReceipt(response({
        command_type: commandType,
        target_type: targetType,
        action_route: `/admissions/applications/${CHILD_ID}`,
      }));
      expect(childcareCommandAdmissionOwnerId(receipt)).toBe(CHILD_ID);
      expect(receipt.actionRoute).not.toMatch(/name|email|phone|note/i);
      expect(() => parseChildcareCommandReceipt(response({
        command_type: commandType,
        target_type: targetType,
        action_route: `/admissions/applications/${CHILD_ID}?name=private`,
      }))).toThrow('owning admission application');
    }
  });

  it('rejects extra fields, unknown commands, malformed versions, and timestamps without offsets', () => {
    expect(() => parseChildcareCommandReceipt({ ...response(), actor_user_id: 'secret' })).toThrow(ChildcareCommandReceiptProtocolError);
    expect(() => parseChildcareCommandReceipt(response({ command_type: 'family.delete' }))).toThrow('invalid childcare command type');
    expect(() => parseChildcareCommandReceipt(response({ committed_version: 0 }))).toThrow('committed version');
    expect(() => parseChildcareCommandReceipt(response({ committed_at: '2026-07-17T06:30:00' }))).toThrow('commit time');
  });

  it('allows only local, non-traversing, fragment-free routes', () => {
    expect(parseSafeLocalActionRoute('/children/one?tab=enrollment')).toBe('/children/one?tab=enrollment');
    for (const route of [
      'https://evil.example/children/one',
      '//evil.example/children/one',
      '/children/../security',
      '/children/%2e%2e/security',
      '/children/one#secret',
      '/children\\evil',
      '/%2f%2fevil.example',
    ]) {
      expect(() => parseSafeLocalActionRoute(route)).toThrow(ChildcareCommandReceiptProtocolError);
    }
  });

  it('binds family and child routes exactly to target_id', () => {
    expect(() => parseChildcareCommandReceipt(response({ action_route: `/families/${CHILD_ID}` }))).toThrow('does not match its family target');
    expect(() => parseChildcareCommandReceipt(response({
      command_type: 'child.update',
      target_type: 'child',
      action_route: `/children/${CHILD_ID}`,
    }))).toThrow('does not match its child target');
    expect(parseChildcareCommandReceipt(response({
      command_type: 'child.update',
      target_type: 'child',
      action_route: `/children/${TARGET_ID}`,
    })).targetId).toBe(TARGET_ID);
  });

  it('requires an enrollment route to carry the receipt target as its only enrollment_id', () => {
    const enrollmentReceipt = parseChildcareCommandReceipt(response({
      command_type: 'enrollment.placement.approve',
      target_type: 'enrollment',
      facility_id: FACILITY_ID,
      action_route: `/children/${CHILD_ID}?enrollment_id=${TARGET_ID}`,
    }));
    expect(enrollmentReceipt.facilityId).toBe(FACILITY_ID);
    expect(childcareCommandEnrollmentOwnerId(enrollmentReceipt)).toBe(CHILD_ID);
    for (const actionRoute of [
      `/children/${CHILD_ID}`,
      `/children/${CHILD_ID}?enrollment_id=${CHILD_ID}`,
      `/children/${CHILD_ID}?enrollment_id=${TARGET_ID}&extra=1`,
      `/families/${TARGET_ID}?enrollment_id=${TARGET_ID}`,
    ]) {
      expect(() => parseChildcareCommandReceipt(response({
        command_type: 'enrollment.update',
        target_type: 'enrollment',
        action_route: actionRoute,
      }))).toThrow('does not match its enrollment target');
    }
  });

  it('binds family-authority targets to an owning family without putting private facts in the route', () => {
    for (const [commandType, targetType, parameter] of [
      ['family.authority.person.replace', 'authority_person', 'authority_person_id'],
      ['family.authority.evidence.review', 'authority_evidence', 'authority_evidence_id'],
      ['family.authority.evidence_object.scan', 'authority_evidence_object', 'authority_evidence_object_id'],
    ] as const) {
      const receipt = parseChildcareCommandReceipt(response({
        command_type: commandType,
        target_type: targetType,
        action_route: `/families/${CHILD_ID}?${parameter}=${TARGET_ID}`,
      }));
      expect(childcareCommandAuthorityFamilyId(receipt)).toBe(CHILD_ID);
      expect(receipt.actionRoute).not.toMatch(/name|email|phone|filename/i);
      expect(() => parseChildcareCommandReceipt(response({
        command_type: commandType,
        target_type: targetType,
        action_route: `/families/${CHILD_ID}?${parameter}=${TARGET_ID}&name=private`,
      }))).toThrow('does not match its family-authority target');
    }
  });

  it('binds child authority and consent-policy routes without private outcome metadata', () => {
    for (const [commandType, targetType, parameter] of [
      ['child.release.authorization.revoke', 'release_authorization', 'release_authorization_id'],
      ['child.release.rule.revoke', 'release_rule', 'release_rule_id'],
      ['child.consent.withdraw', 'consent', 'consent_id'],
    ] as const) {
      const receipt = parseChildcareCommandReceipt(response({ command_type: commandType, target_type: targetType, action_route: `/children/${CHILD_ID}?${parameter}=${TARGET_ID}` }));
      expect(childcareCommandChildAuthorityOwnerId(receipt)).toBe(CHILD_ID);
      expect(() => parseChildcareCommandReceipt(response({ command_type: commandType, target_type: targetType, action_route: `/children/${CHILD_ID}?${parameter}=${TARGET_ID}&name=private` }))).toThrow('does not match its child-authority target');
    }
    expect(parseChildcareCommandReceipt(response({ command_type: 'organization.consent.policy.publish', target_type: 'consent', action_route: `/consent-policies/${TARGET_ID}` })).targetId).toBe(TARGET_ID);
    expect(() => parseChildcareCommandReceipt(response({ command_type: 'organization.consent.policy.publish', target_type: 'consent', action_route: `/children/${CHILD_ID}?consent_id=${TARGET_ID}` }))).toThrow('does not match its consent-policy target');
  });

  it('fetches actor-private receipts with no-store request semantics', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response()), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const receipt = await fetchChildcareCommandReceipt(OPERATION_ID);

    expect(receipt.clientOperationId).toBe(OPERATION_ID);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/childcare-commands/${OPERATION_ID}`);
    expect(init.method).toBe('GET');
    expect(init.cache).toBe('no-store');
    expect(new Headers(init.headers).get('Cache-Control')).toBe('no-store');
  });
});
