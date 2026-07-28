import { describe, expect, it, vi } from 'vitest';
import { CommandOutcomeUnknownError } from '../../api/childcareCommand';
import type { FamilyDetailRecord, FamilyEditInput } from './types';
import { FamilyEditPlanError, runFamilyEditCommandPlan } from './familyCommandPlan';

function family(version = 1): FamilyDetailRecord {
  return {
    id: 'family-1',
    organization_id: 'org-1',
    name: 'River Family',
    status: 'active',
    file_number: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    version,
    replayed: false,
    children: [],
    guardians: [],
    photo_consent: false,
    field_trip_consent: false,
    emergency_medical_consent: false,
    additional_notes: null,
    emergency_contacts: [],
  };
}

describe('runFamilyEditCommandPlan', () => {
  it('builds each later stage from the canonical version returned by the prior stage', async () => {
    const baseline = family();
    const edit: FamilyEditInput = {
      name: 'River Household',
      status: 'active',
      file_number: '',
      consents: { photo_consent: false, field_trip_consent: false, emergency_medical_consent: false },
      additional_notes: '',
      primary_guardian: {
        first_name: 'Amina', last_name: 'River', relationship: 'Mother', guardian_type: 'primary',
        email: 'amina@example.com', cell_phone: '7805551111', home_phone: '', work_phone: '',
        address: '', city: '', postal_code: '', authorized_pickup: true,
      },
    };
    const updateCore = vi.fn(async () => family(3));
    const replaceGuardian = vi.fn(async (_id, _slot, command) => {
      expect(command.expectedVersion).toBe(3);
      return family(4);
    });
    const replaceEmergencyContacts = vi.fn(async () => family(5));

    await expect(runFamilyEditCommandPlan(
      { baseline, edit, organizationId: 'org-1' },
      { updateCore, replaceGuardian, replaceEmergencyContacts },
    )).resolves.toMatchObject({ version: 4 });
    expect(updateCore).toHaveBeenCalledTimes(1);
    expect(replaceGuardian).toHaveBeenCalledTimes(1);
  });

  it('stops after an unresolved durable stage and exposes no resend closure', async () => {
    const baseline = family();
    const edit: FamilyEditInput = {
      name: 'River Household',
      status: 'active',
      file_number: '',
      consents: {
        photo_consent: false,
        field_trip_consent: false,
        emergency_medical_consent: false,
      },
      additional_notes: '',
      primary_guardian: {
        first_name: 'Amina',
        last_name: 'River',
        relationship: 'Mother',
        guardian_type: 'primary',
        email: 'amina@example.com',
        cell_phone: '7805551111',
        home_phone: '',
        work_phone: '',
        address: '',
        city: '',
        postal_code: '',
        authorized_pickup: true,
      },
      secondary_guardian: undefined,
      emergency_contacts: [{
        client_id: 'contact-1',
        first_name: 'Muna',
        last_name: 'River',
        relationship: 'Aunt',
        cell_phone: '7805552222',
        home_phone: '',
        authorized_pickup: true,
      }],
    };
    const updateCore = vi.fn(async () => family(2));
    const guardianCommands: unknown[] = [];
    const replaceGuardian = vi.fn(async (_id, _slot, command) => {
      guardianCommands.push(command);
      if (guardianCommands.length === 1) {
        throw new CommandOutcomeUnknownError('unknown', new TypeError('network'));
      }
      return family(3);
    });
    const replaceEmergencyContacts = vi.fn(async () => family(4));

    let uncertain: FamilyEditPlanError | null = null;
    try {
      await runFamilyEditCommandPlan(
        { baseline, edit, organizationId: 'org-1' },
        { updateCore, replaceGuardian, replaceEmergencyContacts },
      );
    } catch (caught) {
      uncertain = caught as FamilyEditPlanError;
    }

    expect(uncertain).toBeInstanceOf(FamilyEditPlanError);
    expect(uncertain?.outcomeUnknown).toBe(true);
    expect(uncertain?.stage).toBe('primary_guardian');
    expect(uncertain?.confirmedStages).toEqual(['core']);
    expect(updateCore).toHaveBeenCalledTimes(1);
    expect(replaceGuardian).toHaveBeenCalledTimes(1);
    expect(guardianCommands).toHaveLength(1);
    expect(replaceEmergencyContacts).not.toHaveBeenCalled();
    expect(uncertain?.message).toContain('Check the saved result');
  });

  it('reports a known later failure without replaying an already confirmed stage', async () => {
    const baseline = family();
    const edit: FamilyEditInput = {
      name: 'River Household',
      status: 'active',
      file_number: '',
      consents: { photo_consent: false, field_trip_consent: false, emergency_medical_consent: false },
      additional_notes: '',
      primary_guardian: {
        first_name: 'Amina', last_name: 'River', relationship: 'Mother', guardian_type: 'primary',
        email: 'amina@example.com', cell_phone: '7805551111', home_phone: '', work_phone: '',
        address: '', city: '', postal_code: '', authorized_pickup: true,
      },
    };
    const updateCore = vi.fn(async () => family(2));
    const replaceGuardian = vi.fn(async () => { throw new Error('controlled validation failure'); });
    const replaceEmergencyContacts = vi.fn();

    const result = await runFamilyEditCommandPlan(
      { baseline, edit, organizationId: 'org-1' },
      { updateCore, replaceGuardian, replaceEmergencyContacts },
    ).catch((error) => error as FamilyEditPlanError);

    expect(result).toBeInstanceOf(FamilyEditPlanError);
    if (!(result instanceof FamilyEditPlanError)) throw new Error('Expected the staged plan to fail.');
    const caught = result;
    expect(caught.outcomeUnknown).toBe(false);
    expect(caught.confirmedStages).toEqual(['core']);
    expect(caught.message).toContain('family details is confirmed saved');
    expect(updateCore).toHaveBeenCalledTimes(1);
    expect(replaceGuardian).toHaveBeenCalledTimes(1);
  });
});
