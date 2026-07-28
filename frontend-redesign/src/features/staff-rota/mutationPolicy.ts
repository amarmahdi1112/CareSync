import { ApiError } from '../../api/client';

export type MutationFailureDisposition =
  | 'retain_exact'
  | 'refresh_then_reset'
  | 'reset';

/**
 * Classifies a failure only after a mutation request has started.
 *
 * A missing or malformed success receipt is intentionally ambiguous: the
 * server may already have committed, so callers must retain the exact command.
 */
export function mutationFailureDisposition(error: unknown): MutationFailureDisposition {
  if (!(error instanceof ApiError)) return 'retain_exact';
  if ([401, 403, 408, 425, 429].includes(error.status) || error.status >= 500 || error.status === 0) {
    return 'retain_exact';
  }
  if ([409, 422].includes(error.status)) return 'refresh_then_reset';
  return 'reset';
}

export function createOperationId(): string {
  if (!globalThis.crypto?.randomUUID) {
    throw new Error('This browser cannot create a secure operation identifier.');
  }
  return globalThis.crypto.randomUUID();
}

