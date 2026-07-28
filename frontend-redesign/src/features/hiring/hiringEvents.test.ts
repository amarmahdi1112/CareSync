import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildSocketUrl, commitReplayReset, isAuthorizationBoundaryClose, parseRealtimeTicket, parseServerFrame, subscribeHiringEvents } from './hiringEvents';

describe('authenticated resumable ATS WebSocket contract', () => {
  it('parses short-lived ticket metadata without accepting a bearer field', () => expect(parseRealtimeTicket({ ticket: 'opaque-single-use-ticket', expires_at: '2026-07-15T20:00:00Z', websocket_path: '/api/v1/realtime/ws', max_replay: 500 })).toMatchObject({ max_replay: 500 }));
  it('builds a same-origin socket URL with only the opaque ticket and cursor', () => { const url = new URL(buildSocketUrl('/api/v1/realtime/ws', 'opaque-ticket', 17)); expect(url.protocol).toBe('ws:'); expect(url.searchParams.get('ticket')).toBe('opaque-ticket'); expect(url.searchParams.get('after')).toBe('17'); expect(url.search).not.toContain('bearer'); });
  it('rejects a cross-origin socket path before disclosing its ticket', () => expect(() => buildSocketUrl('https://evil.example/ws', 'secret-ticket', 0)).toThrow('API origin'));
  it('rejects a ready frame for another organization', () => expect(() => parseServerFrame({ type: 'ready', organization_id: 'org-2', cursor: 0, heartbeat_seconds: 15, max_replay: 500 }, 'org-1')).toThrow('organization'));
  it('treats the stable 4403 close as an authorization boundary, not a transport retry', () => { expect(isAuthorizationBoundaryClose(4403)).toBe(true); expect(isAuthorizationBoundaryClose(1006)).toBe(false); });
  it('parses canonical events and both safe no-advance reset contracts', () => {
    expect(parseServerFrame({ type: 'event', cursor: 9, event: { id: 'event-9', type: 'offer.sent', entity_type: 'offer', entity_id: 'offer-1', occurred_at: '2026-07-15T20:00:00Z', payload: {} } }, 'org-1')).toMatchObject({ type: 'event', cursor: 9 });
    expect(parseServerFrame({ type: 'reset_required', reason: 'replay_limit_exceeded', requested_after: 2, resume_from: 2, latest_available_cursor: 900, cursor_must_not_advance: true, max_replay: 500 }, 'org-1')).toMatchObject({ type: 'reset_required', latest_available_cursor: 900, cursor_must_not_advance: true });
    expect(parseServerFrame({ type: 'reset_required', reason: 'cursor_ahead', requested_after: 900, latest_available_cursor: 17, cursor_must_not_advance: true }, 'org-1')).toMatchObject({ type: 'reset_required', reason: 'cursor_ahead', requested_after: 900, latest_available_cursor: 17 });
    expect(() => parseServerFrame({ type: 'reset_required', reason: 'cursor_ahead', requested_after: 17, latest_available_cursor: 17, cursor_must_not_advance: true }, 'org-1')).toThrow('cursor-ahead');
    expect(() => parseServerFrame({ type: 'reset_required', reason: 'replay_limit_exceeded', requested_after: 2, resume_from: 2, latest_available_cursor: 900, cursor_must_not_advance: false, max_replay: 500 }, 'org-1')).toThrow('reset contract');
  });

  it('persists an event cursor only after canonical invalidation is applied', async () => {
    const sessionValues = new Map<string, string>(); let release: (() => void) | undefined;
    vi.stubGlobal('localStorage', { getItem: () => 'long-lived-bearer', setItem: () => undefined, removeItem: () => undefined });
    vi.stubGlobal('sessionStorage', { getItem: (key: string) => sessionValues.get(key) || null, setItem: (key: string, value: string) => sessionValues.set(key, value), removeItem: (key: string) => sessionValues.delete(key) });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ ticket: 'short-ticket', expires_at: '2026-07-15T20:00:00Z', websocket_path: '/api/v1/realtime/ws', max_replay: 500 }), { status: 200, headers: { 'Content-Type': 'application/json' } })); vi.stubGlobal('fetch', fetchMock);
    class FakeSocket { static CLOSED = 3; static instances: FakeSocket[] = []; readyState = 1; onmessage: ((event: { data: string }) => void) | null = null; onclose: ((event: { code: number }) => void) | null = null; onerror: (() => void) | null = null; constructor(public url: string) { FakeSocket.instances.push(this); } close() { this.readyState = 3; } }
    vi.stubGlobal('WebSocket', FakeSocket);
    const subscription = subscribeHiringEvents({ organizationId: 'org-1', onState: () => undefined, onInvalidate: () => new Promise<void>((resolve) => { release = resolve; }) });
    await new Promise((resolve) => setTimeout(resolve, 0)); const socket = FakeSocket.instances[0];
    expect(socket.url).toContain('ticket=short-ticket'); expect(socket.url).not.toContain('long-lived-bearer');
    socket.onmessage?.({ data: JSON.stringify({ type: 'event', cursor: 12, event: { id: 'event-12', type: 'job.updated', entity_type: 'job', entity_id: 'job-1', occurred_at: '2026-07-15T20:00:00Z', payload: {} } }) });
    await Promise.resolve(); expect(sessionValues.get('caresync:ats-ws-cursor:org-1')).toBeUndefined(); release?.(); await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sessionValues.get('caresync:ats-ws-cursor:org-1')).toBe('12'); subscription.close();
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toBeDefined();
  });
  it('replaces a reset cursor only after the complete canonical snapshot succeeds', async () => { const values = new Map([['cursor', '2']]); let release!: () => void; const refresh = new Promise<void>((resolve) => { release = resolve; }); const applying = commitReplayReset(() => refresh, { setItem: (key, value) => values.set(key, value) }, 'cursor', 900); await Promise.resolve(); expect(values.get('cursor')).toBe('2'); release(); await applying; expect(values.get('cursor')).toBe('900'); await commitReplayReset(async () => undefined, { setItem: (key, value) => values.set(key, value) }, 'cursor', 17); expect(values.get('cursor')).toBe('17'); const failed = commitReplayReset(async () => { throw new Error('snapshot failed'); }, { setItem: (key, value) => values.set(key, value) }, 'cursor', 18); await expect(failed).rejects.toThrow('snapshot failed'); expect(values.get('cursor')).toBe('17'); });
});

afterEach(() => vi.unstubAllGlobals());
