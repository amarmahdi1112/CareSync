import { describe, expect, it } from 'vitest';
import {
  clearNotificationTarget,
  isSafeNotificationTargetId,
  resolveNotificationTarget,
} from './notificationTarget';

describe('notification work-item targets', () => {
  it('distinguishes an available target from a stale or malformed target', () => {
    expect(resolveNotificationTarget('record-1', ['record-1'])).toEqual({ status: 'available', id: 'record-1' });
    expect(resolveNotificationTarget('record-2', ['record-1'])).toEqual({ status: 'stale', id: 'record-2' });
    expect(resolveNotificationTarget('../record', ['../record'])).toEqual({ status: 'invalid', id: null });
    expect(resolveNotificationTarget(null, ['record-1'])).toEqual({ status: 'none', id: null });
  });

  it('bounds target ids and clears only the consumed query key', () => {
    expect(isSafeNotificationTargetId('staff_schedule:123')).toBe(true);
    expect(isSafeNotificationTargetId(`a${'b'.repeat(199)}`)).toBe(true);
    expect(isSafeNotificationTargetId(`a${'b'.repeat(200)}`)).toBe(false);
    expect(isSafeNotificationTargetId('record?redirect=/jobs')).toBe(false);
    const next = clearNotificationTarget(new URLSearchParams('view=applicants&application=app-1&keep=yes'), 'application');
    expect(next.toString()).toBe('view=applicants&keep=yes');
  });
});
