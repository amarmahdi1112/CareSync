import { apiRequest } from '../../api/client';

export type NotificationCategory = 'hiring' | 'credential' | 'assignment' | 'operations' | 'system';
export interface NotificationItem { id: string; organization_id: string | null; category: NotificationCategory; severity: 'info' | 'success' | 'warning' | 'critical'; title: string; body: string; action: { path: string; entity_type: string; entity_id: string } | null; created_at: string; read_at: string | null; }
export interface NotificationPage { items: NotificationItem[]; page: number; page_size: number; total: number; has_more: boolean; }
export interface NotificationSummary { unread_total: number; by_category: Partial<Record<NotificationCategory, number>>; }
export interface NotificationPreferences { hiring_enabled: boolean; credential_enabled: boolean; assignment_enabled: boolean; operations_enabled: boolean; push_enabled: boolean; system_notifications_always_enabled: true; updated_at: string; }

class NotificationApiError extends Error {}
const object = (value: unknown, label: string): Record<string, unknown> => { if (!value || typeof value !== 'object' || Array.isArray(value)) throw new NotificationApiError(`The server returned invalid ${label}.`); return value as Record<string, unknown>; };
const text = (value: unknown, label: string) => { if (typeof value !== 'string' || !value.trim()) throw new NotificationApiError(`The server returned invalid ${label}.`); return value; };
const nullableText = (value: unknown, label: string) => value == null ? null : text(value, label);
const integer = (value: unknown, label: string) => { if (!Number.isInteger(value) || Number(value) < 0) throw new NotificationApiError(`The server returned invalid ${label}.`); return Number(value); };
const bool = (value: unknown, label: string) => { if (typeof value !== 'boolean') throw new NotificationApiError(`The server returned invalid ${label}.`); return value; };

export function parseNotification(value: unknown): NotificationItem {
  const row = object(value, 'notification');
  const category = text(row.category, 'notification category');
  const severity = text(row.severity, 'notification severity');
  if (!['hiring', 'credential', 'assignment', 'operations', 'system'].includes(category)) throw new NotificationApiError('The server returned an unsupported notification category.');
  if (!['info', 'success', 'warning', 'critical'].includes(severity)) throw new NotificationApiError('The server returned an unsupported notification severity.');
  const action = row.action == null ? null : object(row.action, 'notification action');
  return { id: text(row.id, 'notification id'), organization_id: nullableText(row.organization_id, 'notification organization'), category: category as NotificationCategory, severity: severity as NotificationItem['severity'], title: text(row.title, 'notification title'), body: text(row.body, 'notification body'), action: action ? { path: text(action.path, 'notification action path'), entity_type: text(action.entity_type, 'notification entity type'), entity_id: text(action.entity_id, 'notification entity id') } : null, created_at: text(row.created_at, 'notification creation time'), read_at: nullableText(row.read_at, 'notification read time') };
}
export function parseNotificationPage(value: unknown): NotificationPage { const row = object(value, 'notification page'); if (!Array.isArray(row.items)) throw new NotificationApiError('The server returned invalid notifications.'); return { items: row.items.map(parseNotification), page: integer(row.page, 'notification page'), page_size: integer(row.page_size, 'notification page size'), total: integer(row.total, 'notification total'), has_more: bool(row.has_more, 'notification continuation') }; }
export function parseSummary(value: unknown): NotificationSummary { const row = object(value, 'notification summary'); const counts = object(row.by_category, 'notification category counts'); const by_category: NotificationSummary['by_category'] = {}; for (const [key, value] of Object.entries(counts)) { if (!['hiring', 'credential', 'assignment', 'operations', 'system'].includes(key)) throw new NotificationApiError('The server returned an unsupported notification category count.'); by_category[key as NotificationCategory] = integer(value, 'notification category count'); } return { unread_total: integer(row.unread_total, 'unread notification total'), by_category }; }
export function parsePreferences(value: unknown): NotificationPreferences { const row = object(value, 'notification preferences'); if (row.system_notifications_always_enabled !== true) throw new NotificationApiError('System notifications must remain enabled.'); return { hiring_enabled: bool(row.hiring_enabled, 'hiring preference'), credential_enabled: bool(row.credential_enabled, 'credential preference'), assignment_enabled: bool(row.assignment_enabled, 'assignment preference'), operations_enabled: bool(row.operations_enabled, 'operations preference'), push_enabled: bool(row.push_enabled, 'push preference'), system_notifications_always_enabled: true, updated_at: text(row.updated_at, 'notification preference update time') }; }

export const notificationsApi = {
  list: async (signal?: AbortSignal) => parseNotificationPage(await apiRequest<unknown>('/notifications?page=1&page_size=50', { signal })),
  summary: async (signal?: AbortSignal) => parseSummary(await apiRequest<unknown>('/notifications/summary', { signal })),
  read: async (id: string) => parseNotification(await apiRequest<unknown>(`/notifications/items/${encodeURIComponent(id)}/read`, { method: 'POST' })),
  readAll: () => apiRequest<{ marked_read: number; read_at: string }>('/notifications/read-all', { method: 'POST' }),
  preferences: async (signal?: AbortSignal) => parsePreferences(await apiRequest<unknown>('/notifications/preferences', { signal })),
  updatePreferences: async (value: Pick<NotificationPreferences, 'hiring_enabled' | 'credential_enabled' | 'assignment_enabled' | 'operations_enabled' | 'push_enabled'>) => parsePreferences(await apiRequest<unknown>('/notifications/preferences', { method: 'PUT', body: JSON.stringify(value) })),
};
