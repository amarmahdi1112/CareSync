import type { Candidate, CandidatePathway, ScreeningSchemaVersion } from './hiringApi';

export const DRIVER_PROVISIONING_DEFERRED_COPY =
  'Least-privilege driver provisioning is deferred. Driver-only access cannot be provisioned from Jobs yet, and this action will not create a generic Educator membership.';

export const EDUCATOR_DRIVER_AUTHORITY_COPY =
  'Employer-accepted ECE certification review is recorded. Only Educator access can be provisioned for this educator + driver pathway. Transport authority is not granted by this action.';

export const STUDENT_PROVISIONING_DEFERRED_COPY =
  'Least-privilege supervised student provisioning is deferred. A dedicated trainee/student role is not available from Jobs yet, and this action will not create a generic Educator membership.';

export const EMPLOYER_ECE_REVIEW_REQUIRED_COPY =
  'An employer-accepted, current ECE certification review is required before Educator access can be provisioned. Candidate confirmation or OCR extraction alone is not sufficient.';

export const EMPLOYER_ECE_REVIEW_CONFIRMED_COPY =
  'Employer-accepted ECE certification review is recorded. Candidate confirmation or OCR extraction alone would not be sufficient.';

export interface AdminProvisioningPolicy {
  canProvisionEducator: boolean;
  guidance: string | null;
  actionLabel: string | null;
}

export function adminProvisioningPolicy(
  screeningSchemaVersion: ScreeningSchemaVersion,
  pathway: CandidatePathway | null,
  certificationVerificationStatus: Candidate['certification_verification_status'],
): AdminProvisioningPolicy {
  if (screeningSchemaVersion !== '0030')
    return {
      canProvisionEducator: true,
      guidance: null,
      actionLabel: null,
    };

  if (pathway === 'driver')
    return {
      canProvisionEducator: false,
      guidance: DRIVER_PROVISIONING_DEFERRED_COPY,
      actionLabel: 'Driver provisioning deferred',
    };

  if (pathway === 'student_educator')
    return {
      canProvisionEducator: false,
      guidance: STUDENT_PROVISIONING_DEFERRED_COPY,
      actionLabel: 'Student provisioning deferred',
    };

  if (
    (pathway === 'educator' || pathway === 'educator_driver') &&
    certificationVerificationStatus !== 'verified'
  )
    return {
      canProvisionEducator: false,
      guidance: EMPLOYER_ECE_REVIEW_REQUIRED_COPY,
      actionLabel: 'Employer ECE review required',
    };

  if (pathway === 'educator_driver')
    return {
      canProvisionEducator: true,
      guidance: EDUCATOR_DRIVER_AUTHORITY_COPY,
      actionLabel: 'Provision educator only',
    };

  if (pathway === 'educator')
    return {
      canProvisionEducator: true,
      guidance: EMPLOYER_ECE_REVIEW_CONFIRMED_COPY,
      actionLabel: null,
    };

  return {
    canProvisionEducator: true,
    guidance: null,
    actionLabel: null,
  };
}
