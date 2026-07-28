export interface ExactChildcareCommand<Intent extends object> {
  readonly clientOperationId: string;
  readonly intent: Readonly<Intent>;
  readonly expectedVersion?: number;
}

export class CommandOutcomeUnknownError extends Error {
  readonly outcomeUnknown = true;

  constructor(message: string, public readonly cause: unknown) {
    super(message);
    this.name = 'CommandOutcomeUnknownError';
  }
}

/**
 * The server returned a route-specific, contractually authoritative response
 * proving that this exact command was rejected before commit. This is not a
 * transport failure: callers may retire only the matching prepared journal
 * row, while every ambiguous response continues through normal reconciliation.
 */
export class CommandRejectedBeforeCommitError extends Error {
  readonly outcomeUnknown = false;
  readonly rejectedBeforeCommit = true;

  constructor(message: string, public readonly cause: unknown) {
    super(message);
    this.name = 'CommandRejectedBeforeCommitError';
  }
}

function fallbackUuid(): string {
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    throw new Error('Secure random operation identifiers are unavailable in this browser.');
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function createClientOperationId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : fallbackUuid();
}

function deepFreeze<Value>(value: Value): Value {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value as Record<string, unknown>).forEach(deepFreeze);
  }
  return value;
}

function cloneIntent<Intent extends object>(intent: Intent): Readonly<Intent> {
  return deepFreeze(JSON.parse(JSON.stringify(intent)) as Intent);
}

export function createExactChildcareCommand<Intent extends object>(
  intent: Intent,
  expectedVersion?: number,
): ExactChildcareCommand<Intent> {
  if (expectedVersion !== undefined && (!Number.isInteger(expectedVersion) || expectedVersion < 1)) {
    throw new Error('A positive expected version is required for this command.');
  }
  return Object.freeze({
    clientOperationId: createClientOperationId(),
    intent: cloneIntent(intent),
    ...(expectedVersion === undefined ? {} : { expectedVersion }),
  });
}

export function exactChildcareCommandBody<Intent extends object>(
  command: ExactChildcareCommand<Intent>,
): Intent & { client_operation_id: string; expected_version?: number } {
  return {
    ...(command.intent as Intent),
    client_operation_id: command.clientOperationId,
    ...(command.expectedVersion === undefined ? {} : { expected_version: command.expectedVersion }),
  } as Intent & { client_operation_id: string; expected_version?: number };
}

/**
 * Bind the outbound command to the identifier assigned to its durable journal
 * operation. This assertion lives immediately at the send boundary so a future
 * refactor cannot accidentally journal one UUID and transmit another.
 */
export function commandBoundToJournalOperation<
  Intent extends object,
  Command extends ExactChildcareCommand<Intent>,
>(command: Command, journalOperationId: string): Command {
  if (command.clientOperationId !== journalOperationId) {
    throw new Error('The command operation does not match the durable journal operation. No request was sent.');
  }
  return command;
}

export function isCommandOutcomeUnknown(caught: unknown): caught is CommandOutcomeUnknownError {
  return caught instanceof CommandOutcomeUnknownError
    || Boolean(caught && typeof caught === 'object' && (caught as { outcomeUnknown?: unknown }).outcomeUnknown === true);
}

export function isCommandRejectedBeforeCommit(caught: unknown): caught is CommandRejectedBeforeCommitError {
  // This predicate authorizes deletion of one prepared durable-journal row.
  // Keep it nominal: an arbitrary thrown object must not be able to imitate
  // the server-contract wrapper by setting a public boolean property.
  return caught instanceof CommandRejectedBeforeCommitError;
}

export function commandFailureMessage(caught: unknown, fallback: string): string {
  if (caught instanceof Error && caught.message.trim()) return caught.message;
  return fallback;
}
