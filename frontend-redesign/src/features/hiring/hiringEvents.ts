import { API_URL, ApiError, apiRequest, notifyAuthorizationDenied } from '../../api/client';
import { createCheckpointedEventQueue } from '../../realtime/checkpointedEventQueue';

export type HiringStreamState = 'connecting' | 'connected' | 'reconnecting' | 'manual';
export interface HiringEvent { id: string; cursor: number; type: string; entity_type: string; entity_id: string | null; occurred_at: string; payload: unknown; }
export interface HiringEventSubscription { close: () => void; }
export interface HiringEventOptions { organizationId: string; cursorScope?: string; onInvalidate: (event: HiringEvent) => Promise<void>; onState: (state: HiringStreamState) => void; random?: () => number; }
interface RealtimeTicket { ticket: string; expires_at: string; websocket_path: string; max_replay: number; }
type ResetFrame =
  | { type: 'reset_required'; reason: 'replay_limit_exceeded'; requested_after: number; resume_from: number; latest_available_cursor: number; cursor_must_not_advance: true; max_replay: number }
  | { type: 'reset_required'; reason: 'cursor_ahead'; requested_after: number; resume_from?: number; latest_available_cursor: number; cursor_must_not_advance: true; max_replay?: number };
type ServerFrame = { type: 'ready'; organization_id: string; cursor: number; heartbeat_seconds: number; max_replay: number } | { type: 'event'; cursor: number; event: Omit<HiringEvent, 'cursor'> } | { type: 'heartbeat'; cursor: number; server_time: string } | ResetFrame;

const object = (value: unknown, label: string): Record<string, unknown> => { if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`Invalid ${label}.`); return value as Record<string, unknown>; };
const text = (value: unknown, label: string) => { if (typeof value !== 'string' || !value.trim()) throw new Error(`Invalid ${label}.`); return value; };
const integer = (value: unknown, label: string, minimum = 0) => { if (!Number.isInteger(value) || Number(value) < minimum) throw new Error(`Invalid ${label}.`); return Number(value); };

export function parseRealtimeTicket(value: unknown): RealtimeTicket { const row = object(value, 'realtime ticket'); return { ticket: text(row.ticket, 'ticket'), expires_at: text(row.expires_at, 'ticket expiry'), websocket_path: text(row.websocket_path, 'WebSocket path'), max_replay: integer(row.max_replay, 'maximum replay', 1) }; }
export function parseServerFrame(value: unknown, organizationId: string): ServerFrame {
  const row = object(value, 'realtime frame'); const type = text(row.type, 'frame type');
  if (type === 'ready') { if (row.organization_id !== organizationId) throw new Error('Realtime frame crossed the active organization boundary.'); return { type, organization_id: organizationId, cursor: integer(row.cursor, 'ready cursor'), heartbeat_seconds: integer(row.heartbeat_seconds, 'heartbeat interval', 1), max_replay: integer(row.max_replay, 'maximum replay', 1) }; }
  if (type === 'heartbeat') return { type, cursor: integer(row.cursor, 'heartbeat cursor'), server_time: text(row.server_time, 'server time') };
  if (type === 'reset_required') {
    if (row.cursor_must_not_advance !== true) throw new Error('Unsupported realtime reset contract.');
    const requested = integer(row.requested_after, 'requested cursor');
    const latest = integer(row.latest_available_cursor, 'latest available cursor');
    if (row.reason === 'replay_limit_exceeded') {
      const resume = integer(row.resume_from, 'resume cursor');
      if (resume !== requested || latest < requested) throw new Error('Realtime reset cursor contract is invalid.');
      return { type, reason: row.reason, requested_after: requested, resume_from: resume, latest_available_cursor: latest, cursor_must_not_advance: true, max_replay: integer(row.max_replay, 'maximum replay', 1) };
    }
    if (row.reason === 'cursor_ahead') {
      if (latest >= requested) throw new Error('Realtime cursor-ahead reset contract is invalid.');
      const resume = row.resume_from == null ? undefined : integer(row.resume_from, 'resume cursor');
      const maxReplay = row.max_replay == null ? undefined : integer(row.max_replay, 'maximum replay', 1);
      if (resume !== undefined && resume !== latest) throw new Error('Realtime cursor-ahead reset contract is invalid.');
      return { type, reason: row.reason, requested_after: requested, resume_from: resume, latest_available_cursor: latest, cursor_must_not_advance: true, max_replay: maxReplay };
    }
    throw new Error('Unsupported realtime reset contract.');
  }
  if (type === 'event') { const event = object(row.event, 'realtime event'); return { type, cursor: integer(row.cursor, 'event cursor', 1), event: { id: text(event.id, 'event id'), type: text(event.type, 'event type'), entity_type: text(event.entity_type, 'entity type'), entity_id: event.entity_id == null ? null : text(event.entity_id, 'entity id'), occurred_at: text(event.occurred_at, 'event time'), payload: event.payload } }; }
  throw new Error('Unsupported realtime frame.');
}
export const buildSocketUrl = (path: string, ticket: string, after: number) => { const api = new URL(API_URL); const url = new URL(path, api); if (url.origin !== api.origin) throw new Error('Realtime socket path crossed the API origin.'); url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'; url.search = ''; url.searchParams.set('ticket', ticket); url.searchParams.set('after', String(after)); return url.toString(); };
const ticket = async () => parseRealtimeTicket(await apiRequest<unknown>('/realtime/tickets', { method: 'POST', body: JSON.stringify({}) }));
export async function commitReplayReset(refresh: () => Promise<void>, storage: Pick<Storage, 'setItem'>, cursorKey: string, latestAvailableCursor: number): Promise<void> { await refresh(); storage.setItem(cursorKey, String(latestAvailableCursor)); }
export const isAuthorizationBoundaryClose = (code: number) => code === 4403;

/** Ticket-authenticated resumable WebSocket. Bearer credentials are used only by the ticket POST. */
export function subscribeHiringEvents(options: HiringEventOptions): HiringEventSubscription {
  if (typeof WebSocket === 'undefined') { options.onState('manual'); return { close: () => undefined }; }
  const scope = options.cursorScope?.replace(/[^a-z0-9_-]/gi, '-');
  const cursorKey = scope ? `caresync:${scope}-ws-cursor:${options.organizationId}` : `caresync:ats-ws-cursor:${options.organizationId}`; const random = options.random || Math.random;
  let stopped = false; let socket: WebSocket | null = null; let timer: ReturnType<typeof setTimeout> | undefined; let heartbeatTimer: ReturnType<typeof setTimeout> | undefined; let failures = 0; let resetChain = Promise.resolve(); let resetPending = false; let queuedCursor = 0;
  const persistedCursor = () => { const value = Number(sessionStorage.getItem(cursorKey) || 0); return Number.isSafeInteger(value) && value >= 0 ? value : 0; };
  const schedule = () => { if (stopped) return; failures += 1; options.onState('reconnecting'); const base = Math.min(30_000, 1_000 * (2 ** Math.min(failures - 1, 5))); timer = setTimeout(connect, Math.round(base * (.75 + random() * .5))); };
  const armHeartbeat = () => { if (heartbeatTimer) clearTimeout(heartbeatTimer); heartbeatTimer = setTimeout(() => socket?.close(4000, 'Server frame timeout'), 35_000); };
  const eventQueue = createCheckpointedEventQueue<HiringEvent>({
    apply: options.onInvalidate,
    collapse: (events, checkpoint) => ({
      id: `coalesced-${checkpoint}`,
      cursor: checkpoint,
      type: 'reset_required',
      entity_type: 'workspace',
      entity_id: options.organizationId,
      occurred_at: new Date().toISOString(),
      payload: { reason: 'event_burst', event_count: events.length, first_cursor: events[0].cursor, latest_available_cursor: checkpoint },
    }),
    commit: (checkpoint) => sessionStorage.setItem(cursorKey, String(checkpoint)),
    onError: () => socket?.close(4002, 'Workspace apply failed'),
  });
  const connect = async () => {
    if (stopped) return; options.onState(failures ? 'reconnecting' : 'connecting');
    try {
      const issued = await ticket(); if (stopped) return; const after = persistedCursor(); queuedCursor = after;
      socket = new WebSocket(buildSocketUrl(issued.websocket_path, issued.ticket, after));
      socket.onmessage = (message) => {
        let frame: ServerFrame; try { frame = parseServerFrame(JSON.parse(String(message.data)), options.organizationId); } catch { socket?.close(4408, 'Invalid frame'); return; }
        armHeartbeat();
        if (frame.type === 'ready') { failures = 0; options.onState('connected'); return; }
        if (frame.type === 'heartbeat') return;
        if (frame.type === 'reset_required') { resetPending = true; resetChain = resetChain.then(async () => { await eventQueue.whenIdle(); await commitReplayReset(() => options.onInvalidate({ id: 'reset', cursor: frame.requested_after, type: 'reset_required', entity_type: 'workspace', entity_id: options.organizationId, occurred_at: new Date().toISOString(), payload: { reason: frame.reason, requested_after: frame.requested_after, latest_available_cursor: frame.latest_available_cursor } }), sessionStorage, cursorKey, frame.latest_available_cursor); queuedCursor = frame.latest_available_cursor; resetPending = false; const alreadyClosed = !socket || socket.readyState === WebSocket.CLOSED; socket?.close(4001, 'Canonical refresh applied'); if (alreadyClosed) schedule(); }).catch(() => { resetPending = false; const alreadyClosed = !socket || socket.readyState === WebSocket.CLOSED; socket?.close(4002, 'Workspace reset failed'); if (alreadyClosed) schedule(); }); return; }
        if (resetPending) return;
        if (frame.cursor <= queuedCursor) return; queuedCursor = frame.cursor;
        eventQueue.enqueue({ ...frame.event, cursor: frame.cursor });
      };
      socket.onclose = (event) => { if (heartbeatTimer) clearTimeout(heartbeatTimer); if (stopped || resetPending) return; if (isAuthorizationBoundaryClose(event.code)) { options.onState('manual'); stopped = true; notifyAuthorizationDenied(); return; } schedule(); };
      socket.onerror = () => socket?.close();
    } catch (caught) { if (stopped) return; if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) { options.onState('manual'); stopped = true; return; } schedule(); }
  };
  void connect();
  return { close: () => { stopped = true; if (timer) clearTimeout(timer); if (heartbeatTimer) clearTimeout(heartbeatTimer); socket?.close(1000, 'Page closed'); } };
}
