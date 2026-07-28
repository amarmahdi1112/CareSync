import { describe, expect, it } from 'vitest';
import {
  daycareVerificationPresentation,
  emailVerificationPresentation,
  parseDaycareVerificationFields,
  parseEmailVerificationFields,
} from './verification';

const timestamp = '2026-07-14T22:30:00Z';

describe('verification contract', () => {
  it('accepts coherent temporary approvals and describes their limits truthfully', () => {
    const email = parseEmailVerificationFields({
      email_verification_status: 'verified',
      email_verified_at: timestamp,
      email_verification_method: 'temporary_auto_approval',
    });
    const daycare = parseDaycareVerificationFields({
      verification_status: 'verified',
      verified_at: timestamp,
      verification_method: 'temporary_auto_approval',
    }, 'facility');

    expect(emailVerificationPresentation(email)).toEqual(expect.objectContaining({
      label: 'Email auto-verified',
      note: expect.stringContaining('No confirmation email was sent'),
    }));
    expect(daycareVerificationPresentation(daycare, 'Facility')).toEqual(expect.objectContaining({
      label: 'Facility auto-approved',
      note: expect.stringContaining('not a government or licensing verification'),
    }));
  });

  it('rejects missing, malformed, and internally inconsistent fields', () => {
    expect(() => parseEmailVerificationFields({})).toThrow(/email verification status/i);
    expect(() => parseEmailVerificationFields({
      email_verification_status: 'verified',
      email_verified_at: null,
      email_verification_method: 'temporary_auto_approval',
    })).toThrow(/inconsistent email verification state/i);
    expect(() => parseDaycareVerificationFields({
      verification_status: 'verified',
      verified_at: 'not-a-date',
      verification_method: 'temporary_auto_approval',
    }, 'organization')).toThrow(/verification time/i);
  });

  it('keeps operational and verification status language separate', () => {
    const pending = parseDaycareVerificationFields({
      verification_status: 'pending',
      verified_at: null,
      verification_method: null,
    }, 'organization');
    const copy = daycareVerificationPresentation(pending, 'Organization');
    expect(copy.label).toBe('Organization verification pending');
    expect(copy.note).toContain('separate from its operating status');
  });
});
