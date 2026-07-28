import { describe, expect, it } from 'vitest';
import {
  ChildcareCommandJournalCorruptionError,
  ChildcareCommandJournalUnavailableError,
  ChildcareCommandLaneBlockedError,
  createMemoryCommandJournalState,
  IndexedDbChildcareCommandJournalAdapter,
  MemoryChildcareCommandJournalAdapter,
} from './childcareCommandJournal';

const ACTOR_ID = '10000000-0000-4000-8000-000000000001';
const OTHER_ACTOR_ID = '10000000-0000-4000-8000-000000000002';
const ORGANIZATION_ID = '20000000-0000-4000-8000-000000000001';
const OTHER_ORGANIZATION_ID = '20000000-0000-4000-8000-000000000002';
const OPERATION_ID = '30000000-0000-4000-8000-000000000001';
const OTHER_OPERATION_ID = '30000000-0000-4000-8000-000000000002';
const TARGET_ID = '40000000-0000-4000-8000-000000000001';

function input(overrides: Record<string, unknown> = {}) {
  return {
    actorUserId: ACTOR_ID,
    organizationId: ORGANIZATION_ID,
    clientOperationId: OPERATION_ID,
    commandType: 'family.update' as const,
    targetType: 'family' as const,
    expectedTargetId: TARGET_ID,
    expectedActionOwnerId: null,
    createdAt: '2026-07-17T07:00:00Z',
    ...overrides,
  };
}

describe('durable childcare command journal', () => {
  it('survives an adapter reload through shared durable state', async () => {
    const state = createMemoryCommandJournalState();
    const firstPage = new MemoryChildcareCommandJournalAdapter(state);
    await firstPage.createPrepared(input());

    const reloadedPage = new MemoryChildcareCommandJournalAdapter(state);
    const restored = await reloadedPage.get(input());

    expect(restored).toMatchObject({
      actorUserId: ACTOR_ID,
      organizationId: ORGANIZATION_ID,
      clientOperationId: OPERATION_ID,
      commandType: 'family.update',
      targetType: 'family',
      expectedTargetId: TARGET_ID,
      status: 'prepared',
    });
  });

  it('serializes only the allow-listed non-PII reconciliation metadata', async () => {
    const state = createMemoryCommandJournalState();
    const adapter = new MemoryChildcareCommandJournalAdapter(state);
    const unsafeCallerObject = {
      ...input(),
      intent: { first_name: 'Private Name', health_care_number: '123456789' },
      bearerToken: 'long-lived-secret',
      actionRoute: '/browser/supplied',
      targetScope: 'secret-scope',
    };

    await adapter.createPrepared(unsafeCallerObject);
    const stored = [...state.entries.values()][0] as Record<string, unknown>;

    expect(Object.keys(stored).sort()).toEqual([
      'actor_user_id',
      'client_operation_id',
      'command_type',
      'created_at',
      'expected_action_owner_id',
      'expected_target_id',
      'key',
      'organization_id',
      'schema_version',
      'status',
      'target_type',
    ]);
    const serialized = JSON.stringify(stored);
    expect(serialized).not.toContain('Private Name');
    expect(serialized).not.toContain('health_care_number');
    expect(serialized).not.toContain('long-lived-secret');
    expect(serialized).not.toContain('/browser/supplied');
    expect(serialized).not.toContain('secret-scope');
  });

  it('atomically blocks a second unresolved mutation in the same actor and organization lane', async () => {
    const state = createMemoryCommandJournalState();
    const firstTab = new MemoryChildcareCommandJournalAdapter(state);
    const secondTab = new MemoryChildcareCommandJournalAdapter(state);
    const blocking = await firstTab.createPrepared(input());

    await expect(secondTab.createPrepared(input({ clientOperationId: OTHER_OPERATION_ID })))
      .rejects.toSatisfy((error: unknown) => (
        error instanceof ChildcareCommandLaneBlockedError
        && error.blockingEntry.key === blocking.key
      ));
    expect(state.entries.size).toBe(1);
  });

  it('isolates actor and organization lanes while keeping exact scoped reads private', async () => {
    const state = createMemoryCommandJournalState();
    const adapter = new MemoryChildcareCommandJournalAdapter(state);
    await adapter.createPrepared(input());
    await adapter.createPrepared(input({ actorUserId: OTHER_ACTOR_ID, clientOperationId: OTHER_OPERATION_ID }));
    await adapter.createPrepared(input({ organizationId: OTHER_ORGANIZATION_ID, clientOperationId: '30000000-0000-4000-8000-000000000003' }));

    expect(await adapter.listLane({ actorUserId: ACTOR_ID, organizationId: ORGANIZATION_ID })).toHaveLength(1);
    expect(await adapter.listLane({ actorUserId: OTHER_ACTOR_ID, organizationId: ORGANIZATION_ID })).toHaveLength(1);
    expect(await adapter.get({ actorUserId: OTHER_ACTOR_ID, organizationId: ORGANIZATION_ID, clientOperationId: OPERATION_ID })).toBeNull();
  });

  it('fails closed on a corrupt row instead of making the damaged command invisible', async () => {
    const state = createMemoryCommandJournalState();
    state.entries.set('damaged-key', { key: 'damaged-key', status: 'prepared' });
    const adapter = new MemoryChildcareCommandJournalAdapter(state);

    await expect(adapter.get(input())).rejects.toBeInstanceOf(ChildcareCommandJournalCorruptionError);
    await expect(adapter.createPrepared(input())).rejects.toBeInstanceOf(ChildcareCommandJournalCorruptionError);
    expect(state.entries.has('damaged-key')).toBe(true);
  });

  it('fails closed on a legacy v1 row whose enrollment action owner was never recorded', async () => {
    const state = createMemoryCommandJournalState();
    const legacyKey = `v1:${ACTOR_ID}:${ORGANIZATION_ID}:${OPERATION_ID}`;
    state.entries.set(legacyKey, {
      schema_version: 1,
      key: legacyKey,
      actor_user_id: ACTOR_ID,
      organization_id: ORGANIZATION_ID,
      client_operation_id: OPERATION_ID,
      command_type: 'family.update',
      target_type: 'family',
      expected_target_id: TARGET_ID,
      created_at: '2026-07-17T07:00:00Z',
      status: 'prepared',
    });
    const adapter = new MemoryChildcareCommandJournalAdapter(state);

    await expect(adapter.listLane(input())).rejects.toBeInstanceOf(ChildcareCommandJournalCorruptionError);
    await expect(adapter.createPrepared(input({ clientOperationId: OTHER_OPERATION_ID })))
      .rejects.toBeInstanceOf(ChildcareCommandJournalCorruptionError);
    expect(state.entries.has(legacyKey)).toBe(true);
  });

  it('requires enrollment and family-authority commands to bind their owning record and rejects owners on other targets', async () => {
    const adapter = new MemoryChildcareCommandJournalAdapter();

    await expect(adapter.createPrepared(input({
      commandType: 'enrollment.update',
      targetType: 'enrollment',
      expectedActionOwnerId: null,
    }))).rejects.toThrow('require their owning child');
    await expect(adapter.createPrepared(input({ expectedActionOwnerId: TARGET_ID })))
      .rejects.toThrow('cannot declare one');
    await expect(adapter.createPrepared(input({
      commandType: 'family.authority.person.replace',
      targetType: 'authority_person',
      expectedActionOwnerId: null,
    }))).rejects.toThrow('require their owning family');
    await expect(adapter.createPrepared(input({
      commandType: 'family.authority.evidence.review',
      targetType: 'authority_evidence',
      expectedActionOwnerId: TARGET_ID,
    }))).resolves.toMatchObject({ expectedActionOwnerId: TARGET_ID });
    await expect(new MemoryChildcareCommandJournalAdapter().createPrepared(input({
      commandType: 'child.release.authorization.grant',
      targetType: 'release_authorization',
      expectedActionOwnerId: null,
    }))).rejects.toThrow('require their owning');
    await expect(new MemoryChildcareCommandJournalAdapter().createPrepared(input({
      commandType: 'child.consent.record',
      targetType: 'consent',
      expectedActionOwnerId: TARGET_ID,
    }))).resolves.toMatchObject({ expectedActionOwnerId: TARGET_ID });
    await expect(new MemoryChildcareCommandJournalAdapter().createPrepared(input({
      commandType: 'organization.consent.policy.publish',
      targetType: 'consent',
      expectedActionOwnerId: TARGET_ID,
    }))).rejects.toThrow('cannot declare one');
    await expect(new MemoryChildcareCommandJournalAdapter().createPrepared(input({
      commandType: 'organization.consent.policy.publish',
      targetType: 'consent',
      expectedActionOwnerId: null,
    }))).resolves.toMatchObject({ expectedActionOwnerId: null });
  });

  it('fails closed on corrupt cross-tab lease state', async () => {
    const state = createMemoryCommandJournalState();
    state.leases.set('damaged-lease', { lane_key: 'damaged-lease', owner_id: 'not-a-uuid' });
    const adapter = new MemoryChildcareCommandJournalAdapter(state);
    await expect(adapter.acquireLease(input(), '50000000-0000-4000-8000-000000000001', Date.now(), 3_000))
      .rejects.toBeInstanceOf(ChildcareCommandJournalCorruptionError);
    expect(state.leases.has('damaged-lease')).toBe(true);
  });

  it('fails before any command can be sent when IndexedDB is unavailable', async () => {
    const adapter = new IndexedDbChildcareCommandJournalAdapter(undefined);
    await expect(adapter.createPrepared(input())).rejects.toBeInstanceOf(ChildcareCommandJournalUnavailableError);
  });

  it('keeps committed refresh and final-absence retirement as separate explicit deletion gates', async () => {
    const adapter = new MemoryChildcareCommandJournalAdapter();
    await adapter.createPrepared(input());
    await expect(adapter.deleteCommittedAfterRefresh(input())).rejects.toThrow('Only a committed command');
    await expect(adapter.deleteFinalAbsenceAfterAcknowledgement(input())).rejects.toThrow('Only a server-finalized absent command');
    await adapter.transition(input(), ['prepared'], 'absent_final');
    await expect(adapter.deleteCommittedAfterRefresh(input())).rejects.toThrow('Only a committed command');
    expect(await adapter.get(input())).toMatchObject({ status: 'absent_final' });
    await adapter.deleteFinalAbsenceAfterAcknowledgement(input());
    expect(await adapter.get(input())).toBeNull();
  });

  it('clears an authoritative rejection only while its exact row is still prepared', async () => {
    const adapter = new MemoryChildcareCommandJournalAdapter();
    await adapter.createPrepared(input());
    await adapter.deletePreparedAfterAuthoritativeRejection(input());
    expect(await adapter.get(input())).toBeNull();

    await adapter.createPrepared(input());
    await adapter.transition(input(), ['prepared'], 'blocked');
    await expect(adapter.deletePreparedAfterAuthoritativeRejection(input()))
      .rejects.toThrow('Only a prepared command with an authoritative pre-commit rejection');
    expect(await adapter.get(input())).toMatchObject({ status: 'blocked' });
  });
});
