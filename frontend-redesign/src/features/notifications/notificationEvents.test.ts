import { describe, expect, it } from 'vitest';
import { buildNotificationSocketUrl, commitNotificationCursor, parseNotificationFrame, parseNotificationTicket } from './notificationEvents';

describe('user-private notification realtime contract', () => {
  it('parses the one-use ticket and keeps the socket on the configured API origin', () => {
    expect(parseNotificationTicket({ ticket: 'opaque', expires_at: '2026-07-16T20:00:00Z', websocket_path: '/api/v1/notifications/realtime/ws', max_replay: 500 }).max_replay).toBe(500);
    const url = new URL(buildNotificationSocketUrl('/api/v1/notifications/realtime/ws', 'opaque', 12));
    expect(url.pathname).toBe('/api/v1/notifications/realtime/ws'); expect(url.searchParams.get('after')).toBe('12'); expect(url.searchParams.get('ticket')).toBe('opaque');
    expect(() => buildNotificationSocketUrl('https://evil.test/ws', 'opaque', 0)).toThrow('origin');
  });

  it('rejects cross-user ready frames and unsafe reset semantics', () => {
    expect(parseNotificationFrame({ type: 'ready', user_id: 'user-a', cursor: 0, heartbeat_seconds: 15, max_replay: 500 }, 'user-a')).toMatchObject({ type: 'ready', user_id: 'user-a' });
    expect(() => parseNotificationFrame({ type: 'ready', user_id: 'user-b', cursor: 0, heartbeat_seconds: 15, max_replay: 500 }, 'user-a')).toThrow('user boundary');
    expect(parseNotificationFrame({ type: 'reset_required', reason: 'cursor_ahead', requested_after: 42, latest_available_cursor: 3, cursor_must_not_advance: true }, 'user-a')).toMatchObject({ reason: 'cursor_ahead', requested_after: 42, latest_available_cursor: 3 });
    expect(() => parseNotificationFrame({ type: 'reset_required', reason: 'cursor_ahead', requested_after: 3, latest_available_cursor: 3, cursor_must_not_advance: true }, 'user-a')).toThrow('cursor-ahead');
    expect(() => parseNotificationFrame({ type: 'reset_required', reason: 'replay_limit_exceeded', requested_after: 2, resume_from: 2, latest_available_cursor: 8, cursor_must_not_advance: false, max_replay: 500 }, 'user-a')).toThrow('reset contract');
  });

  it('accepts safe metadata events without requiring or exposing ledger content', () => {
    expect(parseNotificationFrame({ type: 'event', cursor: 4, event: { id: 'evt', type: 'notification.created', entity_type: 'notification', entity_id: 'notification-id', occurred_at: '2026-07-16T20:00:00Z', payload: { category: 'operations', severity: 'warning' } } }, 'user-a')).toMatchObject({ type: 'event', cursor: 4, event: { type: 'notification.created' } });
    expect(() => parseNotificationFrame({ type: 'event', cursor: 4, event: { id: 'evt', type: 'notification.created', entity_type: 'notification', entity_id: null, occurred_at: 'now', payload: { nested: { pii: true } } } }, 'user-a')).toThrow('payload');
  });

  it('persists the private cursor only after the canonical ledger refresh succeeds', async () => {
    const values = new Map<string, string>();
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const applying = commitNotificationCursor(() => pending, { setItem: (key, value) => values.set(key, value) }, 'cursor', 7);
    await Promise.resolve(); expect(values.get('cursor')).toBeUndefined(); release(); await applying; expect(values.get('cursor')).toBe('7');
    await commitNotificationCursor(async () => undefined, { setItem: (key, value) => values.set(key, value) }, 'cursor', 2);
    expect(values.get('cursor')).toBe('2');
    await expect(commitNotificationCursor(async () => { throw new Error('ledger failed'); }, { setItem: (key, value) => values.set(key, value) }, 'cursor', 8)).rejects.toThrow('ledger failed');
    expect(values.get('cursor')).toBe('2');
  });
});
