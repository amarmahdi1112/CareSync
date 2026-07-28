import { apiRequest } from './client';

export type ChildcareCommandTargetType =
  | 'family'
  | 'child'
  | 'enrollment'
  | 'authority_person'
  | 'authority_evidence'
  | 'authority_evidence_object'
  | 'release_authorization'
  | 'release_rule'
  | 'consent'
  | 'admission_application'
  | 'admission_waitlist'
  | 'admission_offer';

export const CHILDCARE_COMMAND_TYPES = [
  'family.create',
  'family.update',
  'family.guardian.primary.replace',
  'family.guardian.secondary.replace',
  'family.emergency_contacts.replace',
  'child.create',
  'child.update',
  'enrollment.create',
  'enrollment.update',
  'enrollment.placement.approve',
  'family.authority.person.create',
  'family.authority.person.replace',
  'family.authority.person.retire',
  'family.authority.evidence_object.upload',
  'family.authority.evidence_object.scan',
  'family.authority.evidence.record',
  'family.authority.evidence.review',
  'family.authority.evidence.reject',
  'family.authority.evidence.invalidate',
  'family.authority.evidence.supersede',
  'child.release.authorization.grant',
  'child.release.authorization.revoke',
  'child.release.rule.create',
  'child.release.rule.revoke',
  'organization.consent.policy.publish',
  'child.consent.record',
  'child.consent.withdraw',
  'admission.application.create',
  'admission.application.update',
  'admission.application.submit',
  'admission.application.review.start',
  'admission.application.decline',
  'admission.application.withdraw',
  'admission.application.correct',
  'admission.waitlist.enter',
  'admission.waitlist.reopen_review',
  'admission.offer.issue',
  'admission.offer.withdraw',
  'admission.offer.decline',
  'admission.offer.accept_and_convert',
] as const;

export type ChildcareCommandType = (typeof CHILDCARE_COMMAND_TYPES)[number];

export const CHILDCARE_COMMAND_TARGETS: Readonly<Record<ChildcareCommandType, ChildcareCommandTargetType>> = {
  'family.create': 'family',
  'family.update': 'family',
  'family.guardian.primary.replace': 'family',
  'family.guardian.secondary.replace': 'family',
  'family.emergency_contacts.replace': 'family',
  'child.create': 'child',
  'child.update': 'child',
  'enrollment.create': 'enrollment',
  'enrollment.update': 'enrollment',
  'enrollment.placement.approve': 'enrollment',
  'family.authority.person.create': 'authority_person',
  'family.authority.person.replace': 'authority_person',
  'family.authority.person.retire': 'authority_person',
  'family.authority.evidence_object.upload': 'authority_evidence_object',
  'family.authority.evidence_object.scan': 'authority_evidence_object',
  'family.authority.evidence.record': 'authority_evidence',
  'family.authority.evidence.review': 'authority_evidence',
  'family.authority.evidence.reject': 'authority_evidence',
  'family.authority.evidence.invalidate': 'authority_evidence',
  'family.authority.evidence.supersede': 'authority_evidence',
  'child.release.authorization.grant': 'release_authorization',
  'child.release.authorization.revoke': 'release_authorization',
  'child.release.rule.create': 'release_rule',
  'child.release.rule.revoke': 'release_rule',
  'organization.consent.policy.publish': 'consent',
  'child.consent.record': 'consent',
  'child.consent.withdraw': 'consent',
  'admission.application.create': 'admission_application',
  'admission.application.update': 'admission_application',
  'admission.application.submit': 'admission_application',
  'admission.application.review.start': 'admission_application',
  'admission.application.decline': 'admission_application',
  'admission.application.withdraw': 'admission_application',
  'admission.application.correct': 'admission_application',
  'admission.waitlist.enter': 'admission_waitlist',
  'admission.waitlist.reopen_review': 'admission_waitlist',
  'admission.offer.issue': 'admission_offer',
  'admission.offer.withdraw': 'admission_offer',
  'admission.offer.decline': 'admission_offer',
  'admission.offer.accept_and_convert': 'admission_offer',
};

export interface ChildcareCommandReceipt {
  readonly organizationId: string;
  readonly clientOperationId: string;
  readonly commandType: ChildcareCommandType;
  readonly targetType: ChildcareCommandTargetType;
  readonly targetId: string;
  readonly committedVersion: number;
  readonly committedAt: string;
  readonly facilityId: string | null;
  readonly actionRoute: string;
}

export class ChildcareCommandReceiptProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChildcareCommandReceiptProtocolError';
  }
}

const RECEIPT_KEYS = [
  'organization_id',
  'client_operation_id',
  'command_type',
  'target_type',
  'target_id',
  'committed_version',
  'committed_at',
  'facility_id',
  'action_route',
] as const;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const RFC3339_WITH_OFFSET_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function protocol(message: string): never {
  throw new ChildcareCommandReceiptProtocolError(message);
}

function exactObject(value: unknown, label: string, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return protocol(`The server returned an invalid ${label}.`);
  }
  const row = value as Record<string, unknown>;
  const actual = Object.keys(row).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    return protocol(`The server returned an unexpected ${label} shape.`);
  }
  return row;
}

function uuid(value: unknown, label: string): string {
  if (typeof value !== 'string' || !UUID_PATTERN.test(value)) {
    return protocol(`The server returned an invalid ${label}.`);
  }
  return value.toLowerCase();
}

function commandType(value: unknown): ChildcareCommandType {
  if (!CHILDCARE_COMMAND_TYPES.includes(value as ChildcareCommandType)) {
    return protocol('The server returned an invalid childcare command type.');
  }
  return value as ChildcareCommandType;
}

function targetType(value: unknown): ChildcareCommandTargetType {
  if (![
    'family',
    'child',
    'enrollment',
    'authority_person',
    'authority_evidence',
    'authority_evidence_object',
    'release_authorization',
    'release_rule',
    'consent',
    'admission_application',
    'admission_waitlist',
    'admission_offer',
  ].includes(String(value))) {
    return protocol('The server returned an invalid childcare command target type.');
  }
  return value as ChildcareCommandTargetType;
}

function timestamp(value: unknown): string {
  if (
    typeof value !== 'string'
    || value.length > 64
    || !RFC3339_WITH_OFFSET_PATTERN.test(value)
    || !Number.isFinite(Date.parse(value))
  ) {
    return protocol('The server returned an invalid childcare command commit time.');
  }
  return value;
}

/**
 * Accept only same-origin application paths. The value is deliberately never
 * persisted by the command journal; it is used only after a fresh receipt read.
 */
export function parseSafeLocalActionRoute(value: unknown): string {
  if (
    typeof value !== 'string'
    || value.length === 0
    || value.length > 2_048
    || !value.startsWith('/')
    || value.startsWith('//')
    || value.includes('\\')
    || value.includes('#')
    || [...value].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
  ) {
    return protocol('The server returned an unsafe childcare command action route.');
  }

  let parsed: URL;
  let decodedPath: string;
  try {
    parsed = new URL(value, 'https://caresync.invalid');
    decodedPath = decodeURIComponent(value.split('?')[0]);
  } catch {
    return protocol('The server returned an invalid childcare command action route.');
  }
  if (
    parsed.origin !== 'https://caresync.invalid'
    || parsed.username
    || parsed.password
    || decodedPath.startsWith('//')
    || decodedPath.includes('\\')
    || decodedPath.split('/').some((segment) => segment === '..')
    || [...decodedPath].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
  ) {
    return protocol('The server returned an unsafe childcare command action route.');
  }
  return value;
}

export function assertChildcareCommandActionRouteBinding(
  receipt: Pick<ChildcareCommandReceipt, 'commandType' | 'targetType' | 'targetId' | 'actionRoute'>,
): void {
  const parsed = new URL(parseSafeLocalActionRoute(receipt.actionRoute), 'https://caresync.invalid');
  const targetId = uuid(receipt.targetId, 'childcare command target');
  if (receipt.targetType === 'family') {
    if (parsed.pathname !== `/families/${targetId}` || parsed.search !== '') {
      protocol('The childcare command action route does not match its family target.');
    }
    return;
  }
  if (receipt.targetType === 'child') {
    if (parsed.pathname !== `/children/${targetId}` || parsed.search !== '') {
      protocol('The childcare command action route does not match its child target.');
    }
    return;
  }

  if (receipt.targetType === 'authority_person' || receipt.targetType === 'authority_evidence' || receipt.targetType === 'authority_evidence_object') {
    const familyRouteMatch = /^\/families\/([0-9a-f-]+)$/i.exec(parsed.pathname);
    const expectedParameter = receipt.targetType === 'authority_person'
      ? 'authority_person_id'
      : receipt.targetType === 'authority_evidence'
        ? 'authority_evidence_id'
        : 'authority_evidence_object_id';
    const parameters = [...parsed.searchParams.entries()];
    if (
      !familyRouteMatch
      || !UUID_PATTERN.test(familyRouteMatch[1])
      || parameters.length !== 1
      || parameters[0][0] !== expectedParameter
      || parameters[0][1].toLowerCase() !== targetId
    ) {
      protocol('The childcare command action route does not match its family-authority target.');
    }
    return;
  }

  if (receipt.targetType === 'release_authorization' || receipt.targetType === 'release_rule' || (receipt.targetType === 'consent' && receipt.commandType !== 'organization.consent.policy.publish')) {
    const childRouteMatch = /^\/children\/([0-9a-f-]+)$/i.exec(parsed.pathname);
    const expectedParameter = receipt.targetType === 'release_authorization'
      ? 'release_authorization_id'
      : receipt.targetType === 'release_rule'
        ? 'release_rule_id'
        : 'consent_id';
    const parameters = [...parsed.searchParams.entries()];
    if (
      !childRouteMatch
      || !UUID_PATTERN.test(childRouteMatch[1])
      || parameters.length !== 1
      || parameters[0][0] !== expectedParameter
      || parameters[0][1].toLowerCase() !== targetId
    ) {
      protocol('The childcare command action route does not match its child-authority target.');
    }
    return;
  }

  if (receipt.targetType === 'consent') {
    if (parsed.pathname !== `/consent-policies/${targetId}` || parsed.search !== '') {
      protocol('The childcare command action route does not match its consent-policy target.');
    }
    return;
  }

  if (receipt.targetType === 'admission_application') {
    if (parsed.pathname !== `/admissions/applications/${targetId}` || parsed.search !== '') {
      protocol('The childcare command action route does not match its admission-application target.');
    }
    return;
  }

  if (receipt.targetType === 'admission_waitlist' || receipt.targetType === 'admission_offer') {
    const applicationRouteMatch = /^\/admissions\/applications\/([0-9a-f-]+)$/i.exec(parsed.pathname);
    if (!applicationRouteMatch || !UUID_PATTERN.test(applicationRouteMatch[1]) || parsed.search !== '') {
      protocol('The childcare command action route does not identify its owning admission application.');
    }
    return;
  }

  const childRouteMatch = /^\/children\/([0-9a-f-]+)$/i.exec(parsed.pathname);
  const parameters = [...parsed.searchParams.entries()];
  if (
    !childRouteMatch
    || !UUID_PATTERN.test(childRouteMatch[1])
    || parameters.length !== 1
    || parameters[0][0] !== 'enrollment_id'
    || parameters[0][1].toLowerCase() !== targetId
  ) {
    protocol('The childcare command action route does not match its enrollment target.');
  }
}

/** Return the application whose private profile owns a waitlist or offer receipt. */
export function childcareCommandAdmissionOwnerId(
  receipt: Pick<ChildcareCommandReceipt, 'commandType' | 'targetType' | 'targetId' | 'actionRoute'>,
): string {
  if (receipt.targetType !== 'admission_waitlist' && receipt.targetType !== 'admission_offer') {
    throw new ChildcareCommandReceiptProtocolError('Only admission waitlist and offer receipts have an owning application route.');
  }
  assertChildcareCommandActionRouteBinding(receipt);
  const match = /^\/admissions\/applications\/([0-9a-f-]+)$/i.exec(
    new URL(receipt.actionRoute, 'https://caresync.invalid').pathname,
  );
  if (!match) return protocol('The admission action route did not identify its owning application.');
  return uuid(match[1], 'admission action owner');
}

export function childcareCommandAuthorityFamilyId(
  receipt: Pick<ChildcareCommandReceipt, 'commandType' | 'targetType' | 'targetId' | 'actionRoute'>,
): string {
  if (!['authority_person', 'authority_evidence', 'authority_evidence_object'].includes(receipt.targetType)) {
    throw new ChildcareCommandReceiptProtocolError('Only family-authority receipts have an owning family action route.');
  }
  assertChildcareCommandActionRouteBinding(receipt);
  const match = /^\/families\/([0-9a-f-]+)$/i.exec(new URL(receipt.actionRoute, 'https://caresync.invalid').pathname);
  if (!match) return protocol('The family-authority action route did not identify its owning family.');
  return uuid(match[1], 'family-authority action owner');
}

/** Return the child whose canonical profile owns an enrollment receipt route. */
export function childcareCommandEnrollmentOwnerId(
  receipt: Pick<ChildcareCommandReceipt, 'commandType' | 'targetType' | 'targetId' | 'actionRoute'>,
): string {
  if (receipt.targetType !== 'enrollment') {
    throw new ChildcareCommandReceiptProtocolError('Only enrollment receipts have an owning child action route.');
  }
  assertChildcareCommandActionRouteBinding(receipt);
  const parsed = new URL(receipt.actionRoute, 'https://caresync.invalid');
  const match = /^\/children\/([0-9a-f-]+)$/i.exec(parsed.pathname);
  if (!match) return protocol('The enrollment action route did not identify its owning child.');
  return uuid(match[1], 'enrollment action owner');
}

export function childcareCommandChildAuthorityOwnerId(
  receipt: Pick<ChildcareCommandReceipt, 'commandType' | 'targetType' | 'targetId' | 'actionRoute'>,
): string {
  if (receipt.targetType !== 'release_authorization'
    && receipt.targetType !== 'release_rule'
    && !(receipt.targetType === 'consent' && receipt.commandType !== 'organization.consent.policy.publish')) {
    throw new ChildcareCommandReceiptProtocolError('Only child-authority receipts have an owning child action route.');
  }
  assertChildcareCommandActionRouteBinding(receipt);
  const match = /^\/children\/([0-9a-f-]+)$/i.exec(new URL(receipt.actionRoute, 'https://caresync.invalid').pathname);
  if (!match) return protocol('The child-authority action route did not identify its owning child.');
  return uuid(match[1], 'child-authority action owner');
}

export function parseChildcareCommandReceipt(value: unknown): ChildcareCommandReceipt {
  const row = exactObject(value, 'childcare command receipt', RECEIPT_KEYS);
  if (!Number.isInteger(row.committed_version) || Number(row.committed_version) < 1) {
    return protocol('The server returned an invalid childcare command committed version.');
  }
  if (row.facility_id !== null && row.facility_id !== undefined && typeof row.facility_id !== 'string') {
    return protocol('The server returned an invalid childcare command facility.');
  }
  const receipt = Object.freeze({
    organizationId: uuid(row.organization_id, 'childcare command organization'),
    clientOperationId: uuid(row.client_operation_id, 'childcare command operation'),
    commandType: commandType(row.command_type),
    targetType: targetType(row.target_type),
    targetId: uuid(row.target_id, 'childcare command target'),
    committedVersion: Number(row.committed_version),
    committedAt: timestamp(row.committed_at),
    facilityId: row.facility_id === null
      ? null
      : uuid(row.facility_id, 'childcare command facility'),
    actionRoute: parseSafeLocalActionRoute(row.action_route),
  });
  if (CHILDCARE_COMMAND_TARGETS[receipt.commandType] !== receipt.targetType) {
    return protocol('The childcare command target type does not match its command type.');
  }
  assertChildcareCommandActionRouteBinding(receipt);
  return receipt;
}

export async function fetchChildcareCommandReceipt(
  clientOperationId: string,
): Promise<ChildcareCommandReceipt> {
  const operationId = uuid(clientOperationId, 'childcare command operation');
  const response = await apiRequest<unknown>(
    `/childcare-commands/${encodeURIComponent(operationId)}`,
    {
      method: 'GET',
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-store',
        Pragma: 'no-cache',
      },
    },
  );
  return parseChildcareCommandReceipt(response);
}
