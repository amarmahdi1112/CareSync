import { describe, expect, it } from 'vitest';
import type { ApiUser } from '../../api/client';
import {
  canOpenDailyClosePreview,
  createDailyCloseRequestGate,
  dailyCloseBoundaryKey,
  nextTodayView,
  settleQuietDailyCloseFailure,
} from './todayViewModel';
import { dailyClosePreviewFixture } from './dailyCloseTestData';

function user(permissions: string[]): ApiUser {
  return {
    id: 'user-1',
    email: 'educator@example.com',
    first_name: 'Eden',
    last_name: 'North',
    organization_id: 'org-1',
    membership_id: 'membership-1',
    membership_status: 'active',
    email_verification_status: 'verified',
    email_verified_at: '2026-07-15T12:00:00Z',
    email_verification_method: 'development_auto_verify',
    role: { id: 'role-1', key: 'custom', name: 'Custom', permissions },
    assigned_facility_ids: ['facility-1'],
    assigned_room_ids: ['room-1'],
  };
}

describe('Today daily-close view model', () => {
  it('requires the exact four-read permission intersection', () => {
    const required = ['care:read', 'child_safety:read', 'medication:read', 'incident:read'];
    expect(canOpenDailyClosePreview(user(required))).toBe(true);
    for (const missing of required) {
      expect(canOpenDailyClosePreview(user(required.filter((permission) => permission !== missing)))).toBe(false);
    }
  });

  it('supports wrapping arrow navigation plus Home and End without entering a disabled tab', () => {
    expect(nextTodayView('daybook', 'ArrowRight', true)).toBe('daily_close');
    expect(nextTodayView('daily_close', 'ArrowRight', true)).toBe('daybook');
    expect(nextTodayView('daybook', 'ArrowLeft', true)).toBe('daily_close');
    expect(nextTodayView('daybook', 'End', true)).toBe('daily_close');
    expect(nextTodayView('daily_close', 'Home', true)).toBe('daybook');
    expect(nextTodayView('daybook', 'ArrowRight', false)).toBe('daybook');
  });

  it('invalidates stale and cross-boundary refresh tickets', () => {
    const gate = createDailyCloseRequestGate();
    const firstBoundary = dailyCloseBoundaryKey('org-1', 'facility-1', 'room-1', '2026-07-15');
    const secondBoundary = dailyCloseBoundaryKey('org-1', 'facility-1', 'room-2', '2026-07-15');
    const first = gate.begin(firstBoundary);
    const second = gate.begin(firstBoundary);
    expect(gate.isCurrent(first, firstBoundary)).toBe(false);
    expect(gate.isCurrent(second, firstBoundary)).toBe(true);
    expect(gate.isCurrent(second, secondBoundary)).toBe(false);
    gate.invalidate();
    expect(gate.isCurrent(second, firstBoundary)).toBe(false);
  });

  it('keeps a last-good snapshot visible after a quiet refresh failure', () => {
    const key = dailyCloseBoundaryKey('org-1', 'facility-1', 'room-1', '2026-07-15');
    expect(settleQuietDailyCloseFailure({
      key,
      status: 'refreshing',
      data: dailyClosePreviewFixture,
      error: '',
    }, key, 'Network unavailable')).toEqual({
      key,
      status: 'ready',
      data: dailyClosePreviewFixture,
      error: '',
    });
    expect(settleQuietDailyCloseFailure({
      key: '', status: 'idle', data: null, error: '',
    }, key, 'Network unavailable')).toEqual({
      key, status: 'error', data: null, error: 'Network unavailable',
    });
  });
});
