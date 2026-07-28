import { describe, expect, it } from 'vitest';
import {
  adminProvisioningPolicy,
  DRIVER_PROVISIONING_DEFERRED_COPY,
  EDUCATOR_DRIVER_AUTHORITY_COPY,
  EMPLOYER_ECE_REVIEW_CONFIRMED_COPY,
  EMPLOYER_ECE_REVIEW_REQUIRED_COPY,
  STUDENT_PROVISIONING_DEFERRED_COPY,
} from './provisioningPolicy';

describe('0030 admin provisioning policy', () => {
  it('blocks the generic educator provisioner for a pure driver pathway', () => {
    expect(adminProvisioningPolicy('0030', 'driver', 'unverified')).toEqual({
      canProvisionEducator: false,
      guidance: DRIVER_PROVISIONING_DEFERRED_COPY,
      actionLabel: 'Driver provisioning deferred',
    });
  });

  it('limits educator-driver provisioning copy to educator access without transport authority', () => {
    const policy = adminProvisioningPolicy('0030', 'educator_driver', 'verified');

    expect(policy.canProvisionEducator).toBe(true);
    expect(policy.actionLabel).toBe('Provision educator only');
    expect(policy.guidance).toBe(EDUCATOR_DRIVER_AUTHORITY_COPY);
    expect(policy.guidance).toContain('Transport authority is not granted');
  });

  it('defers the supervised student pathway instead of granting an educator role', () => {
    expect(adminProvisioningPolicy('0030', 'student_educator', 'unverified')).toEqual({
      canProvisionEducator: false,
      guidance: STUDENT_PROVISIONING_DEFERRED_COPY,
      actionLabel: 'Student provisioning deferred',
    });
  });

  it.each(['unverified', 'pending', 'rejected'] as const)(
    'requires an employer-accepted ECE review when certification is %s',
    (status) => {
      expect(adminProvisioningPolicy('0030', 'educator', status)).toEqual({
        canProvisionEducator: false,
        guidance: EMPLOYER_ECE_REVIEW_REQUIRED_COPY,
        actionLabel: 'Employer ECE review required',
      });
    },
  );

  it('makes the recorded employer review explicit for a ready educator', () => {
    expect(adminProvisioningPolicy('0030', 'educator', 'verified')).toEqual({
      canProvisionEducator: true,
      guidance: EMPLOYER_ECE_REVIEW_CONFIRMED_COPY,
      actionLabel: null,
    });
  });

  it('preserves legacy 0028 provisioning behavior regardless of pathway', () => {
    expect(adminProvisioningPolicy(null, 'driver', 'unverified')).toEqual({
      canProvisionEducator: true,
      guidance: null,
      actionLabel: null,
    });
  });
});
