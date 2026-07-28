import { describe, expect, it } from 'vitest';
import {
  canUseDesktopNotifications,
  desktopNotificationCopy,
  organizationSafeToastCopy,
  readSeenNotificationIds,
  shouldDeliverActiveAlert,
  shouldShowDesktopNotification,
  writeSeenNotificationIds,
} from './notificationDelivery';

describe('notification delivery safety', () => {
  it('never places authenticated ledger content in an OS notification', () => {
    const copy = desktopNotificationCopy({ severity: 'critical' });
    expect(copy).toEqual({ title: 'CareSync needs attention', body: 'Open CareSync to review this update securely.' });
    expect(JSON.stringify(copy)).not.toContain('Child Name');
  });

  it('redacts cross-organization in-app content until the user switches', () => {
    expect(organizationSafeToastCopy({ organization_id: 'org-b', title: 'Candidate Hidaya', body: 'Interview scheduled' }, 'org-a', 'Second Centre')).toEqual({
      title: 'Update in Second Centre',
      body: 'Open notifications to review this update in its organization workspace.',
    });
    expect(organizationSafeToastCopy({ organization_id: 'org-a', title: 'Current update', body: 'Safe authenticated detail' }, 'org-a')).toEqual({ title: 'Current update', body: 'Safe authenticated detail' });
  });

  it('requires both a secure context and browser support', () => {
    const constructor = class FakeNotification {} as unknown as typeof Notification;
    expect(canUseDesktopNotifications(true, constructor)).toBe(true);
    expect(canUseDesktopNotifications(false, constructor)).toBe(false);
    expect(canUseDesktopNotifications(true, undefined)).toBe(false);
  });

  it('uses the in-app toast alone while the portal is foregrounded', () => {
    expect(shouldShowDesktopNotification('visible', true)).toBe(false);
    expect(shouldShowDesktopNotification('visible', false)).toBe(true);
    expect(shouldShowDesktopNotification('hidden', false)).toBe(true);
  });

  it('uses category preferences for active alerts while system alerts remain mandatory', () => {
    const preferences = { hiring_enabled: false, credential_enabled: true, assignment_enabled: false, operations_enabled: true };
    expect(shouldDeliverActiveAlert({ category: 'hiring' }, preferences)).toBe(false);
    expect(shouldDeliverActiveAlert({ category: 'credential' }, preferences)).toBe(true);
    expect(shouldDeliverActiveAlert({ category: 'assignment' }, preferences)).toBe(false);
    expect(shouldDeliverActiveAlert({ category: 'operations' }, preferences)).toBe(true);
    expect(shouldDeliverActiveAlert({ category: 'system' }, preferences)).toBe(true);
  });

  it('deduplicates and bounds persisted seen identifiers', () => {
    const values = new Map<string, string>();
    const storage = { getItem: (key: string) => values.get(key) || null, setItem: (key: string, value: string) => values.set(key, value) };
    writeSeenNotificationIds(storage, 'seen', ['a', 'a', ...Array.from({ length: 510 }, (_, index) => `n-${index}`)]);
    const seen = readSeenNotificationIds(storage, 'seen');
    expect(seen.size).toBe(500);
    expect(seen.has('n-509')).toBe(true);
  });
});
