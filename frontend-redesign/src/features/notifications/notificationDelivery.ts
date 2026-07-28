import type { NotificationItem, NotificationPreferences } from './notificationsApi';

export const DESKTOP_NOTIFICATION_PREFIX = 'caresync:desktop-notifications';
export const SEEN_NOTIFICATION_PREFIX = 'caresync:seen-notifications';

export function desktopPreferenceKey(userId: string, organizationId: string): string {
  return `${DESKTOP_NOTIFICATION_PREFIX}:${userId}:${organizationId}`;
}

export function seenNotificationKey(userId: string): string {
  return `${SEEN_NOTIFICATION_PREFIX}:${userId}`;
}

export function readSeenNotificationIds(storage: Pick<Storage, 'getItem'>, key: string): Set<string> {
  try {
    const parsed: unknown = JSON.parse(storage.getItem(key) || '[]');
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((value): value is string => typeof value === 'string' && value.length <= 200).slice(-500));
  } catch {
    return new Set();
  }
}

export function writeSeenNotificationIds(storage: Pick<Storage, 'setItem'>, key: string, ids: Iterable<string>): void {
  try { storage.setItem(key, JSON.stringify([...new Set(ids)].slice(-500))); } catch { /* Dedupe storage must never block the canonical ledger refresh. */ }
}

export function canUseDesktopNotifications(
  secureContext: boolean,
  notificationConstructor: typeof Notification | undefined,
): boolean {
  return secureContext && typeof notificationConstructor !== 'undefined';
}

export function shouldShowDesktopNotification(visibility: DocumentVisibilityState, hasFocus: boolean): boolean {
  return visibility !== 'visible' || !hasFocus;
}

export function shouldDeliverActiveAlert(
  item: Pick<NotificationItem, 'category'>,
  preferences: Pick<NotificationPreferences, 'hiring_enabled' | 'credential_enabled' | 'assignment_enabled' | 'operations_enabled'>,
): boolean {
  if (item.category === 'system') return true;
  const preferenceByCategory = {
    hiring: preferences.hiring_enabled,
    credential: preferences.credential_enabled,
    assignment: preferences.assignment_enabled,
    operations: preferences.operations_enabled,
  } as const;
  return preferenceByCategory[item.category];
}

/** Deliberately generic: operating-system surfaces must not leak child, family, or candidate PII. */
export function desktopNotificationCopy(item: Pick<NotificationItem, 'severity'>): { title: string; body: string } {
  return {
    title: item.severity === 'critical' ? 'CareSync needs attention' : 'New CareSync update',
    body: 'Open CareSync to review this update securely.',
  };
}

export function organizationSafeToastCopy(
  item: Pick<NotificationItem, 'organization_id' | 'title' | 'body'>,
  currentOrganizationId: string,
  organizationName?: string,
): { title: string; body: string } {
  if (!item.organization_id || item.organization_id === currentOrganizationId) {
    return { title: item.title, body: item.body };
  }
  return {
    title: organizationName ? `Update in ${organizationName}` : 'Update in another workspace',
    body: 'Open notifications to review this update in its organization workspace.',
  };
}
