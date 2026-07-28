import { describe, expect, it } from 'vitest';
import type { ApiUser } from '../api/client';
import { ACCESS, canAccessFeature, canAdministerFamilyAuthority, hasExplicitPermission, hasPermission, isAssignedToFacility, isAssignedToRoom } from './accessModel';

const user = (key: string, permissions: string[], status: ApiUser['membership_status'] = 'active'): ApiUser => ({
  id: `user-${key}`,
  email: `${key}@example.com`,
  first_name: 'Care',
  last_name: 'Operator',
  organization_id: 'organization',
  role: { id: `role-${key}`, key, name: key, permissions },
  membership_id: `membership-${key}`,
  membership_status: status,
  assigned_facility_ids: ['facility-a'],
  assigned_room_ids: ['room-a'],
  is_active: status === 'active',
  email_verification_status: 'verified',
  email_verified_at: '2026-07-14T22:30:00Z',
  email_verification_method: 'temporary_auto_approval',
});

describe('access model', () => {
  it('treats owner as full access without role-name matching', () => {
    const owner = user('owner', []);
    expect(hasPermission(owner, ACCESS.settingsManage)).toBe(true);
    expect(canAccessFeature(owner, 'staff')).toBe(true);
    expect(canAccessFeature({ ...owner, role: { ...owner.role, key: 'not-owner', name: 'Owner' } }, 'staff')).toBe(false);
  });

  it('requires an explicit finance grant even for an owner', () => {
    expect(hasPermission(user('owner', []), ACCESS.billingRead)).toBe(true);
    expect(hasExplicitPermission(user('owner', []), ACCESS.billingRead)).toBe(false);
    expect(canAccessFeature(user('owner', []), 'billing')).toBe(false);
    expect(canAccessFeature(user('owner', [ACCESS.billingRead]), 'billing')).toBe(true);
    expect(canAccessFeature(user('administrator', [ACCESS.billingRead]), 'billing')).toBe(true);
    expect(canAccessFeature(user('educator', [ACCESS.billingRead]), 'billing')).toBe(false);
  });

  it('keeps finance recovery behind its own literal grant', () => {
    const owner = user('owner', [ACCESS.billingRead]);
    expect(hasPermission(owner, ACCESS.billingRecover)).toBe(true);
    expect(hasExplicitPermission(owner, ACCESS.billingRecover)).toBe(false);
    expect(
      hasExplicitPermission(
        user('owner', [ACCESS.billingRead, ACCESS.billingRecover]),
        ACCESS.billingRecover,
      ),
    ).toBe(true);
  });

  it('supports explicit manage-to-read implications only', () => {
    const administrator = user('administrator', [ACCESS.facilityManage, ACCESS.attendanceManage, ACCESS.staffManageEducators]);
    expect(hasPermission(administrator, ACCESS.facilityRead)).toBe(true);
    expect(hasPermission(administrator, ACCESS.attendanceRecord)).toBe(true);
    expect(hasPermission(administrator, ACCESS.attendanceCorrect)).toBe(true);
    expect(canAccessFeature(administrator, 'staff')).toBe(true);
    expect(canAccessFeature(administrator, 'families')).toBe(false);
  });

  it('requires both daybook read and minimized safety access for Today', () => {
    expect(canAccessFeature(user('care-reader', [ACCESS.careRead]), 'today')).toBe(false);
    expect(
      canAccessFeature(
        user('care-reader', [ACCESS.careRead, ACCESS.childSafetyRead]),
        'today',
      ),
    ).toBe(true);
  });

  it('keeps admissions on its dedicated backend-matched permission boundary', () => {
    expect(canAccessFeature(user('intake-reader', [ACCESS.admissionsRead]), 'admissions')).toBe(true);
    expect(canAccessFeature(user('intake-manager', [ACCESS.admissionsManage]), 'admissions')).toBe(true);
    expect(canAccessFeature(user('childcare-manager', [ACCESS.childcareManage]), 'admissions')).toBe(false);
    expect(canAccessFeature(user('facility-reader', [ACCESS.facilityRead]), 'admissions')).toBe(false);
  });

  it('fails closed for suspended members including assignment helpers', () => {
    const suspended = user('educator', [ACCESS.facilityRead, ACCESS.attendanceRead], 'suspended');
    expect(canAccessFeature(suspended, 'dashboard')).toBe(false);
    expect(isAssignedToFacility(suspended, 'facility-a')).toBe(false);
    expect(isAssignedToRoom(suspended, 'room-a')).toBe(false);
  });

  it('scopes educators to their assigned records', () => {
    const educator = user('educator', [ACCESS.facilityRead, ACCESS.careRosterRead, ACCESS.attendanceRead, ACCESS.attendanceRecord]);
    expect(isAssignedToFacility(educator, 'facility-a')).toBe(true);
    expect(isAssignedToFacility(educator, 'facility-b')).toBe(false);
    expect(isAssignedToRoom(educator, 'room-a')).toBe(true);
    expect(isAssignedToRoom(educator, 'room-b')).toBe(false);
  });

  it('keeps private family authority limited to active owners and administrators', () => {
    expect(canAdministerFamilyAuthority(user('owner', []))).toBe(true);
    expect(canAdministerFamilyAuthority(user('administrator', []))).toBe(true);
    expect(canAdministerFamilyAuthority(user('educator', [ACCESS.childcareManage]))).toBe(false);
    expect(canAdministerFamilyAuthority(user('owner', [], 'suspended'))).toBe(false);
    expect(canAdministerFamilyAuthority(null)).toBe(false);
  });
});
