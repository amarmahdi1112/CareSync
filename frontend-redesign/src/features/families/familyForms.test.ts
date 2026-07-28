import { describe, expect, it } from 'vitest';
import {
  emptyEmergencyContact,
  emptyFamilyRegistration,
  toFamilyEditInput,
  toFamilyPatchInput,
  toFamilyRegistrationPayload,
  toFamilyUpdatePayload,
  validateFamilyEdit,
  validateFamilyRegistration,
} from './familyForms';
import type { FamilyDetailRecord } from './types';

const editableFamily: FamilyDetailRecord = {
  id: 'family-1',
  organization_id: 'org-a',
  name: 'Stone Family',
  status: 'active',
  file_number: 'F-100',
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:00:00Z',
  version: 1,
  replayed: false,
  photo_consent: true,
  field_trip_consent: false,
  emergency_medical_consent: true,
  additional_notes: 'Call before pickup',
  children: [],
  guardians: [
    {
      id: 'guardian-primary', family_id: 'family-1', first_name: 'Mina', last_name: 'Stone',
      relationship: 'Mother', guardian_type: 'primary', email: 'mina@example.ca', cell_phone: '7805550100',
      home_phone: null, work_phone: '7805550199', address: '1 Main St', city: 'Edmonton', postal_code: 'T5A 1A1',
      authorized_pickup: false,
    },
    {
      id: 'guardian-secondary', family_id: 'family-1', first_name: 'Noah', last_name: 'Stone',
      relationship: 'Kinship Caregiver', guardian_type: 'secondary', email: 'noah@example.ca', cell_phone: '7805550101',
      home_phone: '7805550102', work_phone: null, address: null, city: null, postal_code: null,
      authorized_pickup: true,
    },
  ],
  emergency_contacts: [
    {
      id: 'contact-1', family_id: 'family-1', first_name: 'Sara', last_name: 'Lee',
      relationship: 'Trusted Neighbour', cell_phone: '7805550103', home_phone: null, authorized_pickup: true,
    },
  ],
};

describe('Basic family form contract', () => {
  it('keeps directory registration active but starts the explicit intake entry pending', () => {
    expect(emptyFamilyRegistration().status).toBe('active');
    expect(emptyFamilyRegistration('pending').status).toBe('pending');
  });

  it('starts every legacy pickup and consent marker false', () => {
    const draft = emptyFamilyRegistration();

    expect(draft.primary_guardian.authorized_pickup).toBe(false);
    expect(draft.secondary_guardian.authorized_pickup).toBe(false);
    expect(emptyEmergencyContact('test-contact').authorized_pickup).toBe(false);
    expect(draft.consents).toEqual({
      photo_consent: false,
      field_trip_consent: false,
      emergency_medical_consent: false,
    });
  });

  it('allows an honest family-only registration and emits no child or billing fields', () => {
    const draft = emptyFamilyRegistration();
    draft.name = 'River Family';
    draft.include_primary_guardian = false;

    expect(validateFamilyRegistration(draft)).toEqual({});
    const payload = toFamilyRegistrationPayload(draft);
    expect(payload).toMatchObject({
      name: 'River Family',
      status: 'active',
      primary_guardian: null,
      secondary_guardian: null,
      emergency_contacts: [],
    });
    expect(payload).not.toHaveProperty('children');
    expect(payload).not.toHaveProperty('is_recurring_billing');
  });

  it('validates an included guardian and normalizes the transactional payload', () => {
    const draft = emptyFamilyRegistration();
    draft.name = '  Noor Household  ';
    draft.primary_guardian = {
      ...draft.primary_guardian,
      first_name: '  Amina ',
      last_name: ' Noor ',
      relationship: 'Mother',
      email: ' AMINA@EXAMPLE.CA ',
      cell_phone: '780-555-0100',
    };

    expect(validateFamilyRegistration(draft)).toEqual({});
    expect(toFamilyRegistrationPayload(draft)).toMatchObject({
      name: 'Noor Household',
      primary_guardian: {
        first_name: 'Amina',
        last_name: 'Noor',
        relationship: 'Mother',
        email: 'amina@example.ca',
      },
    });
  });

  it('requires a relationship for every included guardian', () => {
    const draft = emptyFamilyRegistration();
    draft.name = 'River Family';
    draft.primary_guardian = {
      ...draft.primary_guardian,
      first_name: 'Avery',
      last_name: 'River',
      relationship: '',
      email: 'avery@example.ca',
      cell_phone: '7805550101',
    };
    expect(validateFamilyRegistration(draft)['primary_guardian.relationship']).toBe('Relationship is required.');

    draft.include_primary_guardian = false;
    expect(validateFamilyRegistration(draft)['primary_guardian.relationship']).toBeUndefined();
  });

  it('preserves preloaded and custom relationship text in the transactional payload', () => {
    const draft = emptyFamilyRegistration();
    draft.name = 'Kinship Household';
    draft.primary_guardian = {
      ...draft.primary_guardian,
      first_name: 'Mina', last_name: 'Stone', relationship: 'Legal Guardian', email: 'mina@example.ca', cell_phone: '7805550102',
    };
    draft.include_secondary_guardian = true;
    draft.secondary_guardian = {
      ...draft.secondary_guardian,
      first_name: 'Noah', last_name: 'Stone', relationship: 'Kinship Caregiver', email: 'noah@example.ca', cell_phone: '7805550103',
    };
    draft.emergency_contacts = [
      { client_id: 'known', first_name: 'Sara', last_name: 'Lee', relationship: 'Social Worker', cell_phone: '7805550104', home_phone: '', authorized_pickup: false },
      { client_id: 'custom', first_name: 'Omar', last_name: 'Ali', relationship: 'Trusted Neighbour', cell_phone: '7805550105', home_phone: '', authorized_pickup: true },
    ];

    expect(validateFamilyRegistration(draft)).toEqual({});
    const payload = toFamilyRegistrationPayload(draft);
    expect(payload.primary_guardian).toMatchObject({ relationship: 'Legal Guardian' });
    expect(payload.secondary_guardian).toMatchObject({ relationship: 'Kinship Caregiver' });
    expect(payload.emergency_contacts.map((contact) => contact.relationship)).toEqual(['Social Worker', 'Trusted Neighbour']);
  });

  it('keeps the Basic PATCH payload limited to core family fields and consents', () => {
    const payload = toFamilyUpdatePayload({
      name: 'Stone Family',
      status: 'archived',
      file_number: '',
      consents: {
        photo_consent: true,
        field_trip_consent: false,
        emergency_medical_consent: true,
      },
      additional_notes: '  Historical record  ',
    });

    expect(payload).toEqual({
      name: 'Stone Family',
      status: 'archived',
      file_number: null,
      consents: {
        photo_consent: true,
        field_trip_consent: false,
        emergency_medical_consent: true,
      },
      additional_notes: 'Historical record',
    });
    expect(payload).not.toHaveProperty('primary_guardian');
    expect(payload).not.toHaveProperty('secondary_guardian');
    expect(payload).not.toHaveProperty('emergency_contacts');
  });

  it('hydrates the complete care network without losing live record identities or custom relationships', () => {
    const draft = toFamilyEditInput(editableFamily);

    expect(draft.primary_guardian).toMatchObject({
      record_id: 'guardian-primary',
      guardian_type: 'primary',
      relationship: 'Mother',
      work_phone: '7805550199',
      authorized_pickup: false,
    });
    expect(draft.secondary_guardian).toMatchObject({
      record_id: 'guardian-secondary',
      guardian_type: 'secondary',
      relationship: 'Kinship Caregiver',
    });
    expect(draft.emergency_contacts).toEqual([
      expect.objectContaining({
        client_id: 'contact-1',
        record_id: 'contact-1',
        relationship: 'Trusted Neighbour',
      }),
    ]);
    expect(draft.consents).toEqual({
      photo_consent: true,
      field_trip_consent: false,
      emergency_medical_consent: true,
    });
  });

  it('writes explicit care-network edits while stripping client and server identities', () => {
    const draft = toFamilyEditInput(editableFamily);
    if (draft.primary_guardian) draft.primary_guardian.first_name = '  Amina  ';
    const payload = toFamilyUpdatePayload(draft);

    expect(payload.primary_guardian).toMatchObject({
      first_name: 'Amina',
      relationship: 'Mother',
      email: 'mina@example.ca',
      authorized_pickup: false,
    });
    expect(payload.secondary_guardian).toMatchObject({ relationship: 'Kinship Caregiver' });
    expect(payload.emergency_contacts).toEqual([
      expect.objectContaining({ relationship: 'Trusted Neighbour', authorized_pickup: true }),
    ]);
    expect(JSON.stringify(payload)).not.toContain('guardian-primary');
    expect(JSON.stringify(payload)).not.toContain('guardian-secondary');
    expect(JSON.stringify(payload)).not.toContain('contact-1');
    expect(payload.primary_guardian).not.toHaveProperty('guardian_type');
  });

  it('omits unchanged care sections so a core-only edit preserves live guardian and contact IDs', () => {
    const patch = toFamilyPatchInput(toFamilyEditInput(editableFamily), editableFamily);

    expect(patch).not.toHaveProperty('primary_guardian');
    expect(patch).not.toHaveProperty('secondary_guardian');
    expect(patch).not.toHaveProperty('emergency_contacts');
  });

  it('includes only the care-network section whose normalized values changed', () => {
    const draft = toFamilyEditInput(editableFamily);
    if (draft.emergency_contacts?.[0]) draft.emergency_contacts[0].relationship = 'Family Friend';
    const patch = toFamilyPatchInput(draft, editableFamily);

    expect(patch).not.toHaveProperty('primary_guardian');
    expect(patch).not.toHaveProperty('secondary_guardian');
    expect(patch.emergency_contacts?.[0]).toMatchObject({ relationship: 'Family Friend', record_id: 'contact-1' });
  });

  it('does not block a core-only edit because an unchanged legacy guardian is incomplete', () => {
    const legacyDetail: FamilyDetailRecord = {
      ...editableFamily,
      guardians: [{
        ...editableFamily.guardians[0],
        relationship: null,
        email: '',
        cell_phone: '',
      }],
    };
    const draft = toFamilyEditInput(legacyDetail);
    draft.name = 'Updated Stone Family';
    const patch = toFamilyPatchInput(draft, legacyDetail);

    expect(patch).not.toHaveProperty('primary_guardian');
    expect(validateFamilyEdit(patch)).toEqual({});
  });

  it('preserves explicit null and empty-list removal semantics', () => {
    const draft = toFamilyEditInput(editableFamily);
    draft.primary_guardian = null;
    draft.secondary_guardian = null;
    draft.emergency_contacts = [];
    const patch = toFamilyPatchInput(draft, editableFamily);

    expect(patch).toMatchObject({
      primary_guardian: null,
      secondary_guardian: null,
      emergency_contacts: [],
    });
    expect(toFamilyUpdatePayload(patch)).toMatchObject({
      primary_guardian: null,
      secondary_guardian: null,
      emergency_contacts: [],
    });
  });

  it('validates every guardian and emergency contact before a care-network PATCH', () => {
    const draft = toFamilyEditInput(editableFamily);
    if (draft.secondary_guardian) draft.secondary_guardian.relationship = '';
    if (draft.emergency_contacts?.[0]) draft.emergency_contacts[0].cell_phone = '123';

    expect(validateFamilyEdit(draft)).toMatchObject({
      'secondary_guardian.relationship': 'Relationship is required.',
      'emergency_contacts.0.cell_phone': 'Enter at least seven phone digits.',
    });
  });

  it('preflights backend string limits instead of waiting for a 422 response', () => {
    const draft = emptyFamilyRegistration();
    draft.name = 'F'.repeat(256);
    draft.file_number = 'N'.repeat(81);
    draft.primary_guardian = {
      ...draft.primary_guardian,
      first_name: 'A'.repeat(101),
      last_name: 'Stone',
      relationship: 'Mother',
      email: 'a'.repeat(321),
      cell_phone: '7'.repeat(31),
      home_phone: '7'.repeat(31),
      work_phone: '7'.repeat(31),
      address: 'A'.repeat(256),
      city: 'C'.repeat(101),
      postal_code: 'P'.repeat(21),
    };
    draft.emergency_contacts = [{
      client_id: 'too-long',
      first_name: 'Sara',
      last_name: 'Lee',
      relationship: 'R'.repeat(101),
      cell_phone: '7'.repeat(31),
      home_phone: '7'.repeat(31),
      authorized_pickup: true,
    }];

    expect(validateFamilyRegistration(draft)).toMatchObject({
      name: 'Use 255 characters or fewer.',
      file_number: 'Use 80 characters or fewer.',
      'primary_guardian.first_name': 'Use 100 characters or fewer.',
      'primary_guardian.email': 'Use 320 characters or fewer.',
      'primary_guardian.cell_phone': 'Use 30 characters or fewer.',
      'primary_guardian.home_phone': 'Use 30 characters or fewer.',
      'primary_guardian.work_phone': 'Use 30 characters or fewer.',
      'primary_guardian.address': 'Use 255 characters or fewer.',
      'primary_guardian.city': 'Use 100 characters or fewer.',
      'primary_guardian.postal_code': 'Use 20 characters or fewer.',
      'emergency_contacts.0.relationship': 'Use 100 characters or fewer.',
      'emergency_contacts.0.cell_phone': 'Use 30 characters or fewer.',
      'emergency_contacts.0.home_phone': 'Use 30 characters or fewer.',
    });
  });
});
