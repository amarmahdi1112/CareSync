import { API_URL, ApiError, apiRequest } from '../../api/client';
import { createCheckpointedEventQueue } from '../../realtime/checkpointedEventQueue';
import type { HiringStreamState } from '../hiring/hiringEvents';

export interface NotificationRealtimeEvent { id: string; cursor: number; type: string; entity_type: string; entity_id: string | null; occurred_at: string; payload: Record<string, string | number | boolean>; }
interface Ticket { ticket: string; expires_at: string; websocket_path: string; max_replay: number }
type Frame =
  | { type: 'ready'; user_id: string; cursor: number; heartbeat_seconds: number; max_replay: number }
  | { type: 'event'; cursor: number; event: Omit<NotificationRealtimeEvent, 'cursor'> }
  | { type: 'heartbeat'; cursor: number; server_time: string }
  | { type: 'reset_required'; reason: 'replay_limit_exceeded'; requested_after: number; resume_from: number; latest_available_cursor: number; cursor_must_not_advance: true; max_replay: number }
  | { type: 'reset_required'; reason: 'cursor_ahead'; requested_after: number; resume_from?: number; latest_available_cursor: number; cursor_must_not_advance: true; max_replay?: number };

const object = (value: unknown, label: string): Record<string, unknown> => { if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`Invalid ${label}.`); return value as Record<string, unknown>; };
const text = (value: unknown, label: string): string => { if (typeof value !== 'string' || !value.trim()) throw new Error(`Invalid ${label}.`); return value; };
const integer = (value: unknown, label: string, minimum = 0): number => { if (!Number.isInteger(value) || Number(value) < minimum) throw new Error(`Invalid ${label}.`); return Number(value); };

export function parseNotificationTicket(value: unknown): Ticket {
  const row = object(value, 'notification realtime ticket');
  return { ticket: text(row.ticket, 'ticket'), expires_at: text(row.expires_at, 'ticket expiry'), websocket_path: text(row.websocket_path, 'WebSocket path'), max_replay: integer(row.max_replay, 'maximum replay', 1) };
}

export function parseNotificationFrame(value: unknown, userId: string): Frame {
  const row = object(value, 'notification realtime frame'); const type = text(row.type, 'frame type');
  if (type === 'ready') { if (row.user_id !== userId) throw new Error('Notification realtime frame crossed the signed-in user boundary.'); return { type, user_id: userId, cursor: integer(row.cursor, 'ready cursor'), heartbeat_seconds: integer(row.heartbeat_seconds, 'heartbeat interval', 1), max_replay: integer(row.max_replay, 'maximum replay', 1) }; }
  if (type === 'heartbeat') return { type, cursor: integer(row.cursor, 'heartbeat cursor'), server_time: text(row.server_time, 'server time') };
  if (type === 'reset_required') {
    if (row.cursor_must_not_advance !== true) throw new Error('Unsupported notification reset contract.');
    const requested = integer(row.requested_after, 'requested cursor');
    const latest = integer(row.latest_available_cursor, 'latest available cursor');
    if (row.reason === 'replay_limit_exceeded') {
      const resume = integer(row.resume_from, 'resume cursor');
      if (resume !== requested || latest < requested) throw new Error('Notification reset cursor contract is invalid.');
      return { type, reason: row.reason, requested_after: requested, resume_from: resume, latest_available_cursor: latest, cursor_must_not_advance: true, max_replay: integer(row.max_replay, 'maximum replay', 1) };
    }
    if (row.reason === 'cursor_ahead') {
      if (latest >= requested) throw new Error('Notification cursor-ahead reset contract is invalid.');
      const resume = row.resume_from == null ? undefined : integer(row.resume_from, 'resume cursor');
      const maxReplay = row.max_replay == null ? undefined : integer(row.max_replay, 'maximum replay', 1);
      if (resume !== undefined && resume !== latest) throw new Error('Notification cursor-ahead reset contract is invalid.');
      return { type, reason: row.reason, requested_after: requested, resume_from: resume, latest_available_cursor: latest, cursor_must_not_advance: true, max_replay: maxReplay };
    }
    throw new Error('Unsupported notification reset contract.');
  }
  if (type === 'event') {
    const source = object(row.event, 'notification realtime event'); const payload = object(source.payload, 'notification event payload');
    if (Object.values(payload).some((item) => !['string', 'number', 'boolean'].includes(typeof item))) throw new Error('Invalid notification event payload.');
    return { type, cursor: integer(row.cursor, 'event cursor', 1), event: { id: text(source.id, 'event id'), type: text(source.type, 'event type'), entity_type: text(source.entity_type, 'entity type'), entity_id: source.entity_id == null ? null : text(source.entity_id, 'entity id'), occurred_at: text(source.occurred_at, 'event time'), payload: payload as Record<string, string | number | boolean> } };
  }
  throw new Error('Unsupported notification realtime frame.');
}

export function buildNotificationSocketUrl(path: string, ticket: string, after: number): string {
  const api = new URL(API_URL); const url = new URL(path, api);
  if (url.origin !== api.origin) throw new Error('Notification socket path crossed the API origin.');
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'; url.search = ''; url.searchParams.set('ticket', ticket); url.searchParams.set('after', String(after)); return url.toString();
}

export interface NotificationRealtimeSubscription { close: () => void }
export interface NotificationRealtimeOptions { userId: string; onInvalidate: (event: NotificationRealtimeEvent) => Promise<void>; onState?: (state: HiringStreamState) => void; random?: () => number }

export async function commitNotificationCursor(refresh: () => Promise<void>, storage: Pick<Storage, 'setItem'>, key: string, cursor: number): Promise<void> {
  await refresh();
  storage.setItem(key, String(cursor));
}

export function subscribeNotificationEvents(options: NotificationRealtimeOptions): NotificationRealtimeSubscription {
  if (typeof WebSocket === 'undefined') { options.onState?.('manual'); return { close: () => undefined }; }
  const cursorKey = `caresync:notification-ws-cursor:${options.userId}`; const random = options.random || Math.random;
  let stopped = false; let socket: WebSocket | null = null; let timer: ReturnType<typeof setTimeout> | undefined; let heartbeat: ReturnType<typeof setTimeout> | undefined; let failures = 0; let resetChain = Promise.resolve(); let resetPending = false; let queuedCursor = 0;
  const cursor = () => { const value = Number(sessionStorage.getItem(cursorKey) || 0); return Number.isSafeInteger(value) && value >= 0 ? value : 0; };
  const schedule = () => { if (stopped) return; failures += 1; options.onState?.('reconnecting'); const base = Math.min(30_000, 1_000 * (2 ** Math.min(failures - 1, 5))); timer = setTimeout(connect, Math.round(base * (.75 + random() * .5))); };
  const arm = () => { if (heartbeat) clearTimeout(heartbeat); heartbeat = setTimeout(() => socket?.close(4000, 'Notification frame timeout'), 35_000); };
  const eventQueue = createCheckpointedEventQueue<NotificationRealtimeEvent>({
    apply: options.onInvalidate,
    collapse: (events, checkpoint) => ({
      id: `notification-coalesced-${checkpoint}`,
      cursor: checkpoint,
      type: 'reset_required',
      entity_type: 'notification',
      entity_id: null,
      occurred_at: new Date().toISOString(),
      payload: { reason: 'event_burst', event_count: events.length, first_cursor: events[0].cursor, latest_available_cursor: checkpoint },
    }),
    commit: (checkpoint) => sessionStorage.setItem(cursorKey, String(checkpoint)),
    onError: () => socket?.close(4002, 'Notification refresh failed'),
  });
  const connect = async () => {
    if (stopped) return; options.onState?.(failures ? 'reconnecting' : 'connecting');
    try {
      const issued = parseNotificationTicket(await apiRequest<unknown>('/notifications/realtime/tickets', { method: 'POST', body: JSON.stringify({}) }));
      if (stopped) return; const after = cursor(); queuedCursor = after; socket = new WebSocket(buildNotificationSocketUrl(issued.websocket_path, issued.ticket, after));
      socket.onmessage = (message) => {
        let frame: Frame; try { frame = parseNotificationFrame(JSON.parse(String(message.data)), options.userId); } catch { socket?.close(4408, 'Invalid notification frame'); return; }
        arm();
        if (frame.type === 'ready') { failures = 0; options.onState?.('connected'); return; }
        if (frame.type === 'heartbeat') return;
        if (frame.type === 'reset_required') {
          resetPending = true;
          resetChain = resetChain.then(async () => {
            await eventQueue.whenIdle();
            await commitNotificationCursor(() => options.onInvalidate({ id: 'notification-reset', cursor: frame.requested_after, type: 'reset_required', entity_type: 'notification', entity_id: null, occurred_at: new Date().toISOString(), payload: { reason: frame.reason, requested_after: frame.requested_after, latest_available_cursor: frame.latest_available_cursor } }), sessionStorage, cursorKey, frame.latest_available_cursor); queuedCursor = frame.latest_available_cursor; resetPending = false;
            const closed = !socket || socket.readyState === WebSocket.CLOSED; socket?.close(4001, 'Notification snapshot refreshed'); if (closed) schedule();
          }).catch(() => { resetPending = false; const closed = !socket || socket.readyState === WebSocket.CLOSED; socket?.close(4002, 'Notification snapshot refresh failed'); if (closed) schedule(); });
          return;
        }
        if (resetPending) return;
        if (frame.cursor <= queuedCursor) return; queuedCursor = frame.cursor;
        eventQueue.enqueue({ ...frame.event, cursor: frame.cursor });
      };
      socket.onclose = () => { if (heartbeat) clearTimeout(heartbeat); if (!stopped && !resetPending) schedule(); };
      socket.onerror = () => socket?.close();
    } catch (caught) {
      if (stopped) return;
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) { options.onState?.('manual'); stopped = true; return; }
      schedule();
    }
  };
  void connect();
  return { close: () => { stopped = true; if (timer) clearTimeout(timer); if (heartbeat) clearTimeout(heartbeat); socket?.close(1000, 'Notification consumer closed'); } };
}
