import { describe, expect, it } from 'vitest';
import { ChildAuthoritySummaryApiError, parseChildAuthoritySummary } from './childAuthoritySummaryApi';

const ORGANIZATION = '123e4567-e89b-42d3-a456-426614174000';
const FAMILY = '223e4567-e89b-42d3-a456-426614174000';
const CHILD = '323e4567-e89b-42d3-a456-426614174000';
const RECORD = '423e4567-e89b-42d3-a456-426614174000';
const PERSON = '523e4567-e89b-42d3-a456-426614174000';

function payload() {
  const authorization = {
    record_type: 'release_authorization', id: RECORD, child_id: CHILD,
    recipient: { id: PERSON, display_name: 'Amina Ali', relationship_kind: 'parent', status: 'active' },
    verification_policy_code: 'government_photo_id', effective_from: '2026-07-01T00:00:00Z', effective_until: '2026-08-01T00:00:00Z',
    version: 1, effective_status: 'effective', effective_now: true, authority_revision: 2,
  };
  return {
    schema_version: 'child-authority-summary-v1', organization_id: ORGANIZATION, family_id: FAMILY, child_id: CHILD,
    generated_at: '2026-07-22T12:00:00Z', reviewed: true, authority_revision: 2,
    release_authorizations: [authorization], release_rules: [], consent_decisions: [], focus: authorization,
  };
}

describe('parseChildAuthoritySummary', () => {
  it('accepts the minimum identity-bound projection and exact focus', () => {
    const result = parseChildAuthoritySummary(payload(), { organizationId: ORGANIZATION, familyId: FAMILY, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } });
    expect(result.focus?.id).toBe(RECORD);
    expect(result.release_authorizations[0].recipient.display_name).toBe('Amina Ali');
  });

  it('rejects sensitive or unexpected fields instead of silently accepting them', () => {
    const value = payload();
    Object.assign(value.release_authorizations[0].recipient, { primary_phone: '555-0100' });
    expect(() => parseChildAuthoritySummary(value, { organizationId: ORGANIZATION, familyId: FAMILY, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } })).toThrow(ChildAuthoritySummaryApiError);
  });

  it('rejects cross-child rows and a nearest-record fallback', () => {
    const wrongChild = payload();
    wrongChild.release_authorizations[0].child_id = FAMILY;
    expect(() => parseChildAuthoritySummary(wrongChild, { organizationId: ORGANIZATION, familyId: FAMILY, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } })).toThrow(/outside the requested child revision|crossed/);
    const wrongFocus = payload();
    wrongFocus.focus.id = PERSON;
    expect(() => parseChildAuthoritySummary(wrongFocus, { organizationId: ORGANIZATION, familyId: FAMILY, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } })).toThrow(/exact authority receipt target/);
  });

  it('rejects a mismatched family and timestamps without an explicit UTC offset', () => {
    expect(() => parseChildAuthoritySummary(payload(), { organizationId: ORGANIZATION, familyId: PERSON, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } })).toThrow(/family/);
    const localTime = payload();
    localTime.generated_at = '2026-07-22T12:00:00';
    expect(() => parseChildAuthoritySummary(localTime, { organizationId: ORGANIZATION, familyId: FAMILY, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } })).toThrow(/generation time/);
  });

  it('rejects normalized impossible dates and an unknown negative-zero offset', () => {
    const impossible = payload();
    impossible.generated_at = '2026-02-30T12:00:00Z';
    expect(() => parseChildAuthoritySummary(impossible, { organizationId: ORGANIZATION, familyId: FAMILY, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } })).toThrow(/generation time/);
    const unknownOffset = payload();
    unknownOffset.generated_at = '2026-07-22T12:00:00-00:00';
    expect(() => parseChildAuthoritySummary(unknownOffset, { organizationId: ORGANIZATION, familyId: FAMILY, childId: CHILD, focus: { kind: 'release_authorization', id: RECORD } })).toThrow(/generation time/);
  });
});
