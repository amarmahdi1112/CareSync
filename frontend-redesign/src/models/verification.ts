export const TEMPORARY_AUTO_APPROVAL = 'temporary_auto_approval' as const;

export type EmailVerificationStatus = 'pending' | 'verified';
export type DaycareVerificationStatus = 'pending' | 'under_review' | 'verified' | 'rejected';

export interface EmailVerificationFields {
  email_verification_status: EmailVerificationStatus;
  email_verified_at: string | null;
  email_verification_method: string | null;
}

export interface DaycareVerificationFields {
  verification_status: DaycareVerificationStatus;
  verified_at: string | null;
  verification_method: string | null;
}

export type VerificationTone = 'success' | 'warning' | 'info' | 'neutral';

export interface VerificationPresentation {
  label: string;
  note: string;
  tone: VerificationTone;
}

type InvalidContract = (message: string) => never;

const defaultInvalid: InvalidContract = (message) => {
  throw new Error(message);
};

function nullableTimestamp(value: unknown, label: string, invalid: InvalidContract): string | null {
  if (value === null) return null;
  if (typeof value !== 'string' || !value.trim() || Number.isNaN(Date.parse(value))) {
    return invalid(`The server returned an invalid ${label}.`);
  }
  return value;
}

function nullableMethod(value: unknown, label: string, invalid: InvalidContract): string | null {
  if (value === null) return null;
  if (typeof value !== 'string' || !value.trim()) {
    return invalid(`The server returned an invalid ${label}.`);
  }
  return value;
}

export function parseEmailVerificationFields(
  data: Record<string, unknown>,
  invalid: InvalidContract = defaultInvalid,
): EmailVerificationFields {
  const status = data.email_verification_status;
  if (status !== 'pending' && status !== 'verified') {
    return invalid('The server returned an invalid email verification status.');
  }
  const verifiedAt = nullableTimestamp(data.email_verified_at, 'email verification time', invalid);
  const method = nullableMethod(data.email_verification_method, 'email verification method', invalid);
  if ((status === 'verified') !== Boolean(verifiedAt && method)) {
    return invalid('The server returned an inconsistent email verification state.');
  }
  return {
    email_verification_status: status,
    email_verified_at: verifiedAt,
    email_verification_method: method,
  };
}

export function parseDaycareVerificationFields(
  data: Record<string, unknown>,
  label: 'organization' | 'facility',
  invalid: InvalidContract = defaultInvalid,
): DaycareVerificationFields {
  const status = data.verification_status;
  if (!['pending', 'under_review', 'verified', 'rejected'].includes(String(status))) {
    return invalid(`The server returned an invalid ${label} verification status.`);
  }
  const verifiedAt = nullableTimestamp(data.verified_at, `${label} verification time`, invalid);
  const method = nullableMethod(data.verification_method, `${label} verification method`, invalid);
  if ((status === 'verified') !== Boolean(verifiedAt && method)) {
    return invalid(`The server returned an inconsistent ${label} verification state.`);
  }
  return {
    verification_status: status as DaycareVerificationStatus,
    verified_at: verifiedAt,
    verification_method: method,
  };
}

export function emailVerificationPresentation(
  verification: EmailVerificationFields,
): VerificationPresentation {
  if (
    verification.email_verification_status === 'verified'
    && verification.email_verification_method === TEMPORARY_AUTO_APPROVAL
  ) {
    return {
      label: 'Email auto-verified',
      note: 'Auto-verified for this local phase. No confirmation email was sent.',
      tone: 'info',
    };
  }
  if (verification.email_verification_status === 'verified') {
    return {
      label: 'Email verified',
      note: 'This account email has completed the configured confirmation process.',
      tone: 'success',
    };
  }
  return {
    label: 'Email confirmation pending',
    note: 'Email confirmation will be required when the production mail flow is enabled.',
    tone: 'warning',
  };
}

export function daycareVerificationPresentation(
  verification: DaycareVerificationFields,
  subject: 'Organization' | 'Facility',
): VerificationPresentation {
  if (
    verification.verification_status === 'verified'
    && verification.verification_method === TEMPORARY_AUTO_APPROVAL
  ) {
    return {
      label: `${subject} auto-approved`,
      note: 'Auto-verified for this local phase. This is not a government or licensing verification.',
      tone: 'info',
    };
  }
  if (verification.verification_status === 'verified') {
    return {
      label: `${subject} verified`,
      note: `${subject} verification has completed through the configured review process.`,
      tone: 'success',
    };
  }
  if (verification.verification_status === 'under_review') {
    return {
      label: `${subject} under review`,
      note: `${subject} verification is being reviewed separately from its operating status.`,
      tone: 'warning',
    };
  }
  if (verification.verification_status === 'rejected') {
    return {
      label: `${subject} review needs attention`,
      note: `${subject} verification was not approved. Its operating status is tracked separately.`,
      tone: 'warning',
    };
  }
  return {
    label: `${subject} verification pending`,
    note: `${subject} verification is pending and remains separate from its operating status.`,
    tone: 'neutral',
  };
}
