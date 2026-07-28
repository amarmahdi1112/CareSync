import { describe, expect, it, vi } from 'vitest';
import {
  CommandOutcomeUnknownError,
  CommandRejectedBeforeCommitError,
  commandBoundToJournalOperation,
  createExactChildcareCommand,
  exactChildcareCommandBody,
  isCommandOutcomeUnknown,
  isCommandRejectedBeforeCommit,
} from './childcareCommand';

describe('exact childcare commands', () => {
  it('freezes one operation id, intent, and expected version for exact retry', () => {
    const command = createExactChildcareCommand({ first_name: 'Amina', tags: ['one'] }, 7);
    const first = exactChildcareCommandBody(command);
    const retry = exactChildcareCommandBody(command);

    expect(first).toEqual(retry);
    expect(first.client_operation_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    expect(first.expected_version).toBe(7);
    expect(Object.isFrozen(command)).toBe(true);
    expect(Object.isFrozen(command.intent)).toBe(true);
    expect(Object.isFrozen(command.intent.tags)).toBe(true);
  });

  it('distinguishes an unknown commit outcome from a controlled rejection', () => {
    expect(isCommandOutcomeUnknown(new CommandOutcomeUnknownError('Retry exact command.', new TypeError('offline')))).toBe(true);
    expect(isCommandOutcomeUnknown(new Error('Validation failed.'))).toBe(false);
  });

  it('keeps an authoritative pre-commit rejection distinct from every ambiguous outcome', () => {
    const rejected = new CommandRejectedBeforeCommitError('Scanner unavailable.', new Error('typed 503'));
    expect(isCommandRejectedBeforeCommit(rejected)).toBe(true);
    expect(isCommandRejectedBeforeCommit({ rejectedBeforeCommit: true })).toBe(false);
    expect(isCommandOutcomeUnknown(rejected)).toBe(false);
    expect(rejected.outcomeUnknown).toBe(false);
  });

  it('passes the exact command through only when its id is the journal operation id', () => {
    const command = createExactChildcareCommand({ first_name: 'Amina' });

    expect(commandBoundToJournalOperation(command, command.clientOperationId)).toBe(command);
  });

  it('blocks the send boundary before a different command id can be transmitted', () => {
    const command = createExactChildcareCommand({ first_name: 'Amina' });
    const send = vi.fn();

    expect(() => send(commandBoundToJournalOperation(
      command,
      '10000000-0000-4000-8000-000000000001',
    ))).toThrow('does not match the durable journal operation');
    expect(send).not.toHaveBeenCalled();
  });
});
