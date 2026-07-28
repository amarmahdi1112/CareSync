export const NOTIFICATION_TARGET_ID = /^[A-Za-z0-9][A-Za-z0-9:_-]{0,199}$/;
export type NotificationTargetKey =
  | 'application'
  | 'incident'
  | 'schedule'
  | 'plan'
  | 'focus'
  | 'record';

export type NotificationTargetResolution =
  | { status: 'none'; id: null }
  | { status: 'invalid'; id: null }
  | { status: 'stale'; id: string }
  | { status: 'available'; id: string };

export function isSafeNotificationTargetId(value: string): boolean {
  return NOTIFICATION_TARGET_ID.test(value);
}

export function resolveNotificationTarget(
  value: string | null,
  availableIds: Iterable<string>,
): NotificationTargetResolution {
  if (value == null) return { status: 'none', id: null };
  if (!isSafeNotificationTargetId(value)) return { status: 'invalid', id: null };
  const available = availableIds instanceof Set ? availableIds : new Set(availableIds);
  return available.has(value)
    ? { status: 'available', id: value }
    : { status: 'stale', id: value };
}

export function clearNotificationTarget(
  current: URLSearchParams,
  key: NotificationTargetKey,
): URLSearchParams {
  const next = new URLSearchParams(current);
  next.delete(key);
  return next;
}

export function clearNotificationTargets(
  current: URLSearchParams,
  keys: readonly NotificationTargetKey[],
): URLSearchParams {
  const next = new URLSearchParams(current);
  keys.forEach((key) => next.delete(key));
  return next;
}
