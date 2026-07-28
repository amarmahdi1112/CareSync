import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/client';
import { createOperationId, mutationFailureDisposition } from './mutationPolicy';

describe('workforce mutation policy', () => {
  it('retains exact intent for ambiguous, authentication, throttling and malformed-receipt outcomes', () => {
    [0, 401, 403, 408, 425, 429, 500, 503].forEach((status) => {
      expect(mutationFailureDisposition(new ApiError(status, 'failed'))).toBe('retain_exact');
    });
    expect(mutationFailureDisposition(new Error('receipt parser rejected the response'))).toBe('retain_exact');
  });

  it('requires canonical refresh before clearing stale conflict intent', () => {
    expect(mutationFailureDisposition(new ApiError(409, 'stale'))).toBe('refresh_then_reset');
    expect(mutationFailureDisposition(new ApiError(422, 'no longer eligible'))).toBe('refresh_then_reset');
  });

  it('resets a definitive non-conflict client failure', () => {
    expect(mutationFailureDisposition(new ApiError(400, 'bad request'))).toBe('reset');
    expect(mutationFailureDisposition(new ApiError(404, 'not found'))).toBe('reset');
  });

  it('uses the browser cryptographic UUID source', () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'operation-1' });
    expect(createOperationId()).toBe('operation-1');
    vi.unstubAllGlobals();
  });
});

