import { describe, expect, it } from 'vitest';
import { facilityPatch, organizationPatch, validateFacilityDraft, validateOrganizationDraft, validatePasswordDraft, validateProfileDraft, type FacilityDraft, type OrganizationDraft } from './settingsValidation';

const organization: OrganizationDraft = {
  name: 'Discoverers Daycare', legal_name: '', email: 'office@example.com', phone: '', timezone: 'America/Edmonton',
};

const facility: FacilityDraft = {
  name: 'Main centre', license_number: '', email: '', phone: '', street_address: '', city: 'Edmonton', province: 'AB', postal_code: '', timezone: 'America/Edmonton', licensed_capacity: '140', opening_time: '06:00', closing_time: '18:00', status: 'active',
};

describe('settings validation', () => {
  it('accepts valid organization and facility settings', () => {
    expect(validateOrganizationDraft(organization)).toEqual([]);
    expect(validateFacilityDraft({ ...facility, licensed_capacity: '-1', opening_time: '19:00' })).toEqual([
      'Licensed capacity must be a non-negative whole number.',
      'Closing time must be later than opening time.',
    ]);
  });

  it('never normalizes required fields to null', () => {
    expect(organizationPatch({ ...organization, legal_name: '  ' })).toEqual({
      name: 'Discoverers Daycare', legal_name: null, email: 'office@example.com', phone: null, timezone: 'America/Edmonton',
    });
    expect(facilityPatch(facility)).toMatchObject({ name: 'Main centre', province: 'AB', timezone: 'America/Edmonton', licensed_capacity: 140, status: 'active' });
  });

  it('requires a complete operator identity', () => {
    expect(validateProfileDraft({ first_name: '', last_name: '', email: 'bad' })).toHaveLength(3);
  });

  it('requires a confirmed, distinct password of at least ten characters', () => {
    expect(validatePasswordDraft({ current: 'current123', next: 'new-password', confirm: 'new-password' })).toEqual([]);
    expect(validatePasswordDraft({ current: 'samevalue1', next: 'samevalue1', confirm: 'different' })).toHaveLength(2);
  });
});
