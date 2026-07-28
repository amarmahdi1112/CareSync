import { describe, expect, it } from 'vitest';
import type { ApiUser } from '../api/client';
import { buildNavigation, searchNavigation } from './navigation';

const user = (key: string, permissions: string[]): ApiUser => ({
  id: `user-${key}`,
  email: `${key}@example.com`,
  first_name: 'Care',
  last_name: key,
  organization_id: 'organization',
  role: { id: `role-${key}`, key, name: key, permissions },
  membership_id: `membership-${key}`,
  membership_status: 'active',
  assigned_facility_ids: key === 'educator' ? ['facility'] : [],
  assigned_room_ids: key === 'educator' ? ['room'] : [],
  is_active: true,
  email_verification_status: 'verified',
  email_verified_at: '2026-07-14T22:30:00Z',
  email_verification_method: 'temporary_auto_approval',
});

describe('permission-aware command navigation', () => {
  it('gives the owner the complete Basic navigation', () => {
    const navigation = buildNavigation(user('owner', []));
    expect(navigation.all.map((item) => item.id)).toEqual(['dashboard', 'admissions', 'today', 'families', 'children', 'rooms', 'attendance', 'medications', 'incidents', 'staff', 'staff-rota', 'hiring', 'settings']);
    expect(navigation.groups.map((group) => group.label)).toEqual(['Command', 'Care operations', 'Administration']);
  });

  it('keeps runtime-controlled transport absent until both capability and permission are explicit', () => {
    expect(buildNavigation(user('owner', [])).all.map((item) => item.id)).not.toContain('transport-registry');
    expect(buildNavigation(user('owner', []), new Set(['transport_registry'])).all.map((item) => item.id)).toContain('transport-registry');
    expect(buildNavigation(user('administrator', ['transport:read'])).all.map((item) => item.id)).not.toContain('transport-registry');
    expect(buildNavigation(user('administrator', ['transport:read']), new Set(['transport_registry'])).all.map((item) => item.id)).not.toContain('transport-registry');
    expect(buildNavigation(user('administrator', ['transport:manage']), new Set(['transport_registry'])).all.map((item) => item.id)).toContain('transport-registry');
    expect(buildNavigation(user('administrator', []), new Set(['transport_registry'])).all.map((item) => item.id)).not.toContain('transport-registry');
  });

  it('exposes billing only when the ledger capability and permission are both explicit', () => {
    expect(buildNavigation(user('administrator', ['billing:read'])).all.map((item) => item.id)).not.toContain('billing');
    expect(buildNavigation(user('administrator', ['billing:read']), new Set(['billing_ledger'])).all.map((item) => item.id)).toContain('billing');
    expect(buildNavigation(user('administrator', []), new Set(['billing_ledger'])).all.map((item) => item.id)).not.toContain('billing');
    expect(buildNavigation(user('educator', ['billing:read']), new Set(['billing_ledger'])).all.map((item) => item.id)).not.toContain('billing');
  });

  it('marks billing live only when the runtime supplies the reviewed manual status', () => {
    const capabilities = new Set<'billing_ledger'>(['billing_ledger']);
    const preview = buildNavigation(user('owner', ['billing:read']), capabilities);
    const live = buildNavigation(
      user('owner', ['billing:read']),
      capabilities,
      { billing: 'live' },
    );
    expect(preview.all.find((item) => item.id === 'billing')?.status).toBe('preview');
    expect(live.all.find((item) => item.id === 'billing')?.status).toBe('live');
  });

  it('limits educators to their operational surfaces', () => {
    const navigation = buildNavigation(user('educator', ['facility:read', 'care_roster:read', 'attendance:read', 'attendance:record', 'care:read', 'child_safety:read']));
    expect(navigation.all.map((item) => item.id)).toEqual(['dashboard', 'today', 'rooms', 'attendance', 'settings']);
    expect(searchNavigation('family', navigation.all)).toEqual([]);
    expect(searchNavigation('room', navigation.all).map((item) => item.id)).toEqual(['today', 'rooms']);
  });

  it('lets administrators manage educators without exposing family records unless granted', () => {
    const navigation = buildNavigation(user('administrator', ['facility:read', 'facility:manage', 'attendance:read', 'attendance:manage', 'staff:manage_educators']));
    expect(navigation.all.map((item) => item.id)).toEqual(['dashboard', 'rooms', 'attendance', 'staff', 'staff-rota', 'settings']);
  });

  it('fails closed for suspended memberships', () => {
    const suspended = { ...user('educator', ['facility:read', 'attendance:read']), membership_status: 'suspended' as const };
    expect(buildNavigation(suspended).all).toEqual([]);
  });
});
