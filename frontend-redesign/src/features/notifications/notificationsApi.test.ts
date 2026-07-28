import { describe, expect, it } from 'vitest';
import { parseNotification, parsePreferences, parseSummary } from './notificationsApi';

describe('notification REST contracts', () => {
  it('parses the backend push preference without weakening mandatory system notices', () => {
    expect(parsePreferences({ hiring_enabled: true, credential_enabled: true, assignment_enabled: false, operations_enabled: true, push_enabled: false, system_notifications_always_enabled: true, updated_at: '2026-07-16T20:00:00Z' })).toMatchObject({ push_enabled: false, system_notifications_always_enabled: true });
    expect(() => parsePreferences({ hiring_enabled: true, credential_enabled: true, assignment_enabled: true, operations_enabled: true, push_enabled: true, system_notifications_always_enabled: false, updated_at: 'now' })).toThrow('System notifications');
  });

  it('keeps organization scope and action metadata for safe navigation checks', () => {
    expect(parseNotification({ id: 'notice-1', organization_id: 'org-b', category: 'hiring', severity: 'info', title: 'Update', body: 'Review securely', action: { path: '/jobs', entity_type: 'application', entity_id: 'app-1' }, created_at: '2026-07-16T20:00:00Z', read_at: null })).toMatchObject({ organization_id: 'org-b', action: { entity_id: 'app-1' } });
    expect(parseSummary({ unread_total: 3, by_category: { hiring: 2, system: 1 } })).toEqual({ unread_total: 3, by_category: { hiring: 2, system: 1 } });
  });
});
