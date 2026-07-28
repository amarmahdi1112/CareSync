import { describe, expect, it, vi } from 'vitest';
import {
  TransportOperationPendingError,
  clearTransportOperation,
  prepareTransportOperation,
  transportIntentFingerprint,
  withTransportOperation,
} from './transportOperationJournal';

const scope = {
  actorUserId: '11111111-1111-4111-8111-111111111111',
  organizationId: '22222222-2222-4222-8222-222222222222',
};
const fingerprintA = 'a'.repeat(64);
const fingerprintB = 'b'.repeat(64);

class MemoryStorage {
  readonly values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}

describe('transport exact-retry operation journal', () => {
  it('reuses the durable operation only for the exact same lane and fingerprint', () => {
    const storage = new MemoryStorage();
    const first = prepareTransportOperation(scope, 'vehicle:abc:version', fingerprintA, storage, () => new Date('2026-07-21T17:00:00Z'));
    const retry = prepareTransportOperation(scope, 'vehicle:abc:version', fingerprintA, storage);
    expect(retry).toEqual({ operationId: first.operationId, exactRetry: true });
    expect(storage.values.size).toBe(1);
  });

  it('never overwrites an unresolved operation with a different intent', () => {
    const storage = new MemoryStorage();
    const first = prepareTransportOperation(scope, 'staff:member:authorization', fingerprintA, storage, () => new Date('2026-07-21T17:00:00Z'));
    const before = [...storage.values.values()][0];
    expect(() => prepareTransportOperation(scope, 'staff:member:authorization', fingerprintB, storage)).toThrow(TransportOperationPendingError);
    expect([...storage.values.values()][0]).toBe(before);
    try { prepareTransportOperation(scope, 'staff:member:authorization', fingerprintB, storage); } catch (caught) {
      expect(caught).toMatchObject({ operationId: first.operationId, createdAt: '2026-07-21T17:00:00.000Z' });
    }
  });

  it('requires the exact operation identity before a saved retry can be cleared', () => {
    const storage = new MemoryStorage();
    const prepared = prepareTransportOperation(scope, 'vehicle:create:ab:abc123', fingerprintA, storage);
    clearTransportOperation(scope, 'vehicle:create:ab:abc123', '33333333-3333-4333-8333-333333333333', storage);
    expect(storage.values.size).toBe(1);
    clearTransportOperation(scope, 'vehicle:create:ab:abc123', prepared.operationId, storage);
    expect(storage.values.size).toBe(0);
  });

  it('keeps ambiguous failures durable, retries the same id, and clears only after a bound receipt', async () => {
    const original = globalThis.localStorage;
    const storage = new MemoryStorage();
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
    const send = vi.fn().mockRejectedValueOnce(new Error('network lost')).mockImplementationOnce(async (operationId: string) => ({ client_operation_id: operationId }));
    try {
      await expect(withTransportOperation({ scope, lane: 'vehicle:abc:retire', intent: { reason_code: 'sold' }, send })).rejects.toThrow('network lost');
      expect(storage.values.size).toBe(1);
      await expect(withTransportOperation({ scope, lane: 'vehicle:abc:retire', intent: { reason_code: 'sold' }, send })).resolves.toMatchObject({ client_operation_id: expect.any(String) });
      expect(send.mock.calls[1]?.[0]).toBe(send.mock.calls[0]?.[0]);
      expect(storage.values.size).toBe(0);
    } finally {
      Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: original });
    }
  });
});

describe('upload intent fingerprint', () => {
  it('binds full file bytes, MIME type, size, and normalized original filename', async () => {
    const base = new File([new Uint8Array([1, 2, 3])], 'licence.pdf', { type: 'application/pdf' });
    const same = new File([new Uint8Array([1, 2, 3])], 'licence.pdf', { type: 'application/pdf' });
    const renamed = new File([new Uint8Array([1, 2, 3])], 'driver-licence.pdf', { type: 'application/pdf' });
    const changed = new File([new Uint8Array([1, 2, 4])], 'licence.pdf', { type: 'application/pdf' });
    expect(await transportIntentFingerprint({ type: 'driver_licence' }, same)).toBe(await transportIntentFingerprint({ type: 'driver_licence' }, base));
    expect(await transportIntentFingerprint({ type: 'driver_licence' }, renamed)).not.toBe(await transportIntentFingerprint({ type: 'driver_licence' }, base));
    expect(await transportIntentFingerprint({ type: 'driver_licence' }, changed)).not.toBe(await transportIntentFingerprint({ type: 'driver_licence' }, base));
  });

  it('normalizes canonically equivalent Unicode filenames', async () => {
    const composed = new File(['same'], 'caf\u00e9.pdf', { type: 'application/pdf' });
    const decomposed = new File(['same'], 'cafe\u0301.pdf', { type: 'application/pdf' });
    expect(await transportIntentFingerprint({}, composed)).toBe(await transportIntentFingerprint({}, decomposed));
  });
});
