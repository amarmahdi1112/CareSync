import { describe, expect, it } from 'vitest';
import {
  SettingsApiError,
  parseApplicationSettings,
  parseFacilitySettings,
  parseOrganizationSettings,
  parseProfile,
  parseReleaseCheckoutActivationResponse,
  parseReleaseCheckoutActivationStatus,
} from './settingsApi';

const activationStatus = {
  schema_version: 'release-checkout-activation-status-v1',
  organization_id: 'org',
  facility_id: 'facility',
  facility_name: 'Main',
  runtime_available: true,
  activation_command_available: true,
  database_writable: true,
  actor_authorized: true,
  facility_active: true,
  activated: false,
  legacy_checkout_allowed: true,
  activation_policy_version: null,
  open_enrollment_children: 2,
  release_ready_children: 2,
  children_needing_authority_review: 0,
  prerequisites: [
    { code: 'runtime_available', label: 'Runtime', satisfied: true },
    { code: 'activation_command_available', label: 'Command', satisfied: true },
    { code: 'database_writable', label: 'Writable', satisfied: true },
    { code: 'facility_active', label: 'Facility', satisfied: true },
    { code: 'privileged_actor', label: 'Actor', satisfied: true },
    { code: 'authority_records_complete', label: 'Authority', satisfied: true },
    { code: 'not_already_activated', label: 'Inactive', satisfied: true },
  ],
  can_activate: true,
  confirmation_text: 'ACTIVATE VERIFIED RELEASE CHECKOUT',
};

describe('settings API adapters', () => {
  it('accepts the non-null Basic settings contract', () => {
    const verification = { verification_status: 'verified', verified_at: '2026-07-14T22:30:00Z', verification_method: 'temporary_auto_approval' };
    const emailVerification = { email_verification_status: 'verified', email_verified_at: '2026-07-14T22:30:00Z', email_verification_method: 'temporary_auto_approval' };
    expect(parseOrganizationSettings({ id: 'org', name: 'Daycare', legal_name: null, status: 'active', email: null, phone: null, timezone: 'America/Edmonton', preferences: {}, created_at: 'now', updated_at: 'now', ...verification }).name).toBe('Daycare');
    expect(parseFacilitySettings({ id: 'facility', organization_id: 'org', name: 'Main', license_number: null, status: 'active', email: null, phone: null, street_address: null, city: null, province: 'AB', postal_code: null, timezone: 'America/Edmonton', licensed_capacity: 0, opening_time: null, closing_time: null, created_at: 'now', updated_at: 'now', ...verification }).licensed_capacity).toBe(0);
    expect(parseApplicationSettings({ organization_id: 'org', timezone: 'America/Edmonton', preferences: {} }).organization_id).toBe('org');
    expect(parseProfile({ id: 'user', email: 'owner@example.com', first_name: 'Care', last_name: 'Owner', organization_id: 'org', role: { id: 'role', key: 'owner', name: 'Owner', permissions: ['settings:manage'] }, membership_id: 'membership', membership_status: 'active', assigned_facility_ids: [], assigned_room_ids: [], is_active: true, ...emailVerification }).role.name).toBe('Owner');
  });

  it('rejects null required fields and malformed preferences', () => {
    expect(() => parseApplicationSettings({ organization_id: 'org', timezone: null, preferences: {} })).toThrow(SettingsApiError);
    expect(() => parseApplicationSettings({ organization_id: 'org', timezone: 'America/Edmonton', preferences: [] })).toThrow(SettingsApiError);
    expect(() => parseOrganizationSettings({ id: 'org', name: 'Daycare' })).toThrow(SettingsApiError);
  });

  it('accepts a coherent activation status and committed immutable receipt', () => {
    expect(parseReleaseCheckoutActivationStatus(activationStatus).can_activate).toBe(true);
    const committedStatus = {
      ...activationStatus,
      activated: true,
      legacy_checkout_allowed: false,
      activation_policy_version: 'normal_verified_release_v1',
      prerequisites: activationStatus.prerequisites.map((item) => item.code === 'not_already_activated' ? { ...item, satisfied: false } : item),
      can_activate: false,
    };
    const response = parseReleaseCheckoutActivationResponse({
      schema_version: 'release-checkout-activation-v1',
      status: committedStatus,
      receipt: {
        organization_id: 'org',
        facility_id: 'facility',
        activation_id: 'activation',
        client_operation_id: 'operation',
        committed_at: '2026-07-22T20:00:00.000000Z',
        action_route: '/settings?section=facility',
      },
      replayed: false,
    });
    expect(response.status.activated).toBe(true);
    expect(response.receipt.activation_id).toBe('activation');
  });

  it('rejects inconsistent readiness, duplicate prerequisites and unsafe receipt routes', () => {
    expect(() => parseReleaseCheckoutActivationStatus({ ...activationStatus, release_ready_children: 1 })).toThrow(SettingsApiError);
    expect(() => parseReleaseCheckoutActivationStatus({ ...activationStatus, prerequisites: [...activationStatus.prerequisites, activationStatus.prerequisites[0]] })).toThrow(SettingsApiError);
    expect(() => parseReleaseCheckoutActivationResponse({
      schema_version: 'release-checkout-activation-v1',
      status: activationStatus,
      receipt: {
        organization_id: 'org',
        facility_id: 'facility',
        activation_id: 'activation',
        client_operation_id: 'operation',
        committed_at: 'now',
        action_route: 'https://outside.example',
      },
      replayed: false,
    })).toThrow(SettingsApiError);
  });
});
