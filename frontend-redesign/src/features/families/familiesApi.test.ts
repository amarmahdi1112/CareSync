import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isCommandOutcomeUnknown } from '../../api/childcareCommand';
import {
  FamiliesApiError,
  buildFamilyCoreUpdateCommand,
  buildFamilyCreateCommand,
  buildFamilyEmergencyContactsReplacementCommand,
  buildFamilyGuardianReplacementCommand,
  createFamily,
  fetchFamilyDirectoryPage,
  fetchFamiliesSnapshot,
  fetchFamilyDetail,
  replaceFamilyEmergencyContacts,
  replaceFamilyGuardian,
  updateFamily,
} from './familiesApi';
import { emptyEmergencyContact, emptyFamilyRegistration, emptyGuardian } from './familyForms';

const familyResponse = {
  id: 'family-1',
  organization_id: 'org-a',
  name: 'River Family',
  status: 'active',
  file_number: null,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:00:00Z',
  version: 2,
  replayed: false,
  photo_consent: false,
  field_trip_consent: false,
  emergency_medical_consent: false,
  additional_notes: null,
  children: [],
  guardians: [],
  emergency_contacts: [],
};

const directoryItem = {
  id: 'family-1',
  organization_id: 'org-a',
  name: 'River Family',
  file_number: 'F-100',
  status: 'active',
  version: 2,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:00:00Z',
  primary_contact: {
    id: 'guardian-1', first_name: 'Mina', last_name: 'River', email: 'mina@example.ca', cell_phone: '7805550100',
  },
  active_children: [{ id: 'child-1', first_name: 'Amina', last_name: 'River', age_group: 'Preschool' }],
  active_child_count: 1,
};

function directoryPage(items: unknown[], total = items.length, limit = 50, offset = 0) {
  return { items, total, limit, offset };
}

function okJson(value: unknown, status = 200) {
  return { ok: true, status, json: async () => value };
}

describe('dedicated families CRUD adapter', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(okJson(familyResponse));
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => key === 'caresync-redesign-organization' ? 'org-a' : 'test-token',
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('registers an exact command through POST /families', async () => {
    const draft = emptyFamilyRegistration();
    draft.name = 'River Family';
    draft.include_primary_guardian = false;
    const command = buildFamilyCreateCommand(draft);
    await createFamily(command, 'org-a');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(url).toMatch(/\/families$/);
    expect(url).not.toContain('/resources/');
    expect(init.method).toBe('POST');
    expect(body.client_operation_id).toBe(command.clientOperationId);
    expect(body).not.toHaveProperty('expected_version');
  });

  it('updates only core fields with an expected version', async () => {
    const edit = {
      name: 'River Family',
      status: 'active',
      file_number: '',
      consents: { photo_consent: false, field_trip_consent: false, emergency_medical_consent: false },
      additional_notes: '',
    };
    const command = buildFamilyCoreUpdateCommand(edit, 1);
    await updateFamily('family-1', command, 'org-a');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(url).toMatch(/\/families\/family-1$/);
    expect(init.method).toBe('PATCH');
    expect(body).toMatchObject({ client_operation_id: command.clientOperationId, expected_version: 1 });
    expect(body).not.toHaveProperty('primary_guardian');
    expect(body).not.toHaveProperty('secondary_guardian');
    expect(body).not.toHaveProperty('emergency_contacts');
  });

  it('rejects a fresh family response that skips the exact next version', async () => {
    fetchMock.mockResolvedValueOnce(okJson({ ...familyResponse, version: 3, replayed: false }));
    const command = buildFamilyCoreUpdateCommand({
      name: 'River Family', status: 'active', file_number: '',
      consents: { photo_consent: false, field_trip_consent: false, emergency_medical_consent: false },
      additional_notes: '',
    }, 1);
    const caught = await updateFamily('family-1', command, 'org-a').catch((error) => error);
    expect(isCommandOutcomeUnknown(caught)).toBe(true);
  });

  it('uses named, version-chained care-network replacement routes', async () => {
    const guardian = { ...emptyGuardian('primary'), first_name: 'Mina', last_name: 'River', relationship: 'Mother', email: 'mina@example.ca', cell_phone: '7805550100' };
    const guardianCommand = buildFamilyGuardianReplacementCommand(guardian, 2);
    fetchMock.mockResolvedValueOnce(okJson({
      ...familyResponse,
      version: 3,
      guardians: [{
        id: 'guardian-live-1', family_id: 'family-1', first_name: 'Mina', last_name: 'River',
        relationship: 'Mother', guardian_type: 'primary', email: 'mina@example.ca', cell_phone: '7805550100',
        home_phone: null, work_phone: null, address: null, city: null, postal_code: null, authorized_pickup: true,
      }],
    }));
    const withGuardian = await replaceFamilyGuardian('family-1', 'primary', guardianCommand, 'org-a');

    const contact = { ...emptyEmergencyContact('contact-old'), first_name: 'Sara', last_name: 'Lee', relationship: 'Aunt', cell_phone: '7805550101' };
    const contactCommand = buildFamilyEmergencyContactsReplacementCommand([contact], withGuardian.version);
    fetchMock.mockResolvedValueOnce(okJson({
      ...familyResponse,
      version: 4,
      emergency_contacts: [{
        id: 'contact-live-1', family_id: 'family-1', first_name: 'Sara', last_name: 'Lee',
        relationship: 'Aunt', cell_phone: '7805550101', home_phone: null, authorized_pickup: true,
      }],
    }));
    const saved = await replaceFamilyEmergencyContacts('family-1', contactCommand, 'org-a');

    const [guardianUrl, guardianInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(guardianUrl).toMatch(/\/families\/family-1\/guardians\/primary$/);
    expect(guardianInit.method).toBe('PUT');
    expect(JSON.parse(String(guardianInit.body))).toMatchObject({ expected_version: 2, guardian: { first_name: 'Mina' } });
    const [contactUrl, contactInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(contactUrl).toMatch(/\/families\/family-1\/emergency-contacts$/);
    expect(contactInit.method).toBe('PUT');
    expect(JSON.parse(String(contactInit.body))).toMatchObject({ expected_version: 3, emergency_contacts: [{ first_name: 'Sara' }] });
    expect(JSON.stringify(contactInit.body)).not.toContain('contact-old');
    expect(saved.emergency_contacts[0].id).toBe('contact-live-1');
  });

  it('requests an encoded server search/status/page and keeps stats separate', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/families/stats')) return Promise.resolve(okJson({ families: 51, active_families: 51, children: 1, active_children: 1, pending_families: 0, by_age_group: {} }));
      if (url.includes('/families/directory?')) return Promise.resolve(okJson(directoryPage([directoryItem], 51, 50, 50)));
      throw new Error(`Unexpected URL ${url}`);
    });

    const snapshot = await fetchFamiliesSnapshot('org-a', { search: ' Noor & Co ', status: 'active', limit: 50, offset: 50 });
    expect(snapshot.directory).toMatchObject({ total: 51, limit: 50, offset: 50 });
    expect(snapshot.stats?.families).toBe(51);
    const directoryUrl = new URL(String(fetchMock.mock.calls.find(([url]) => String(url).includes('/families/directory?'))?.[0]));
    expect(directoryUrl.searchParams.get('search')).toBe('Noor & Co');
    expect(directoryUrl.searchParams.get('status')).toBe('active');
    expect(directoryUrl.searchParams.get('limit')).toBe('50');
    expect(directoryUrl.searchParams.get('offset')).toBe('50');
  });

  it.each([
    ['an unavailable summary endpoint', { ok: false, status: 500, json: async () => ({ detail: 'summary unavailable' }) }],
    ['a malformed summary projection', okJson({ families: 51 })],
  ])('keeps the live directory usable during %s', async (_label, statsResponse) => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/families/stats')) return Promise.resolve(statsResponse);
      if (url.includes('/families/directory?')) return Promise.resolve(okJson(directoryPage([directoryItem])));
      throw new Error(`Unexpected URL ${url}`);
    });

    const snapshot = await fetchFamiliesSnapshot('org-a');

    expect(snapshot.directory.items).toEqual([directoryItem]);
    expect(snapshot.stats).toBeNull();
  });

  it.each([401, 403])('still fails closed when family-summary authorization returns %s', async (status) => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/families/stats')) return Promise.resolve({ ok: false, status, json: async () => ({ detail: 'authorization denied' }) });
      if (url.includes('/families/directory?')) return Promise.resolve(okJson(directoryPage([directoryItem])));
      throw new Error(`Unexpected URL ${url}`);
    });

    await expect(fetchFamiliesSnapshot('org-a')).rejects.toMatchObject({ status });
  });

  it('accepts the privacy-minimized directory item without assuming a replay field', async () => {
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([directoryItem])));
    const page = await fetchFamilyDirectoryPage('org-a');
    const directoryUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(directoryUrl.searchParams.has('status')).toBe(false);
    expect(page.items[0]).toEqual(directoryItem);
    expect(page.items[0]).not.toHaveProperty('replayed');
    expect(page.items[0]).not.toHaveProperty('guardians');
    expect(page.items[0]).not.toHaveProperty('consents');
  });

  it('accepts an imported primary contact whose surname was not recorded', async () => {
    const importedContact = {
      ...directoryItem,
      primary_contact: { ...directoryItem.primary_contact, last_name: '' },
    };
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([importedContact])));

    const page = await fetchFamilyDirectoryPage('org-a');

    expect(page.items[0].primary_contact).toMatchObject({ first_name: 'Mina', last_name: '' });
  });

  it('still rejects a primary-contact name with a non-string value', async () => {
    const malformedContact = {
      ...directoryItem,
      primary_contact: { ...directoryItem.primary_contact, last_name: null },
    };
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([malformedContact])));

    await expect(fetchFamilyDirectoryPage('org-a')).rejects.toBeInstanceOf(FamiliesApiError);
  });

  it('rejects cross-tenant directory rows', async () => {
    fetchMock.mockResolvedValueOnce(okJson(directoryPage([{ ...directoryItem, organization_id: 'org-b' }])));
    await expect(fetchFamilyDirectoryPage('org-a')).rejects.toMatchObject({ status: 403 });
  });

  it.each([
    ['unexpected page keys', { ...directoryPage([directoryItem]), replayed: false }],
    ['more than four preview children', directoryPage([{ ...directoryItem, active_children: Array.from({ length: 5 }, (_, index) => ({ id: `child-${index}`, first_name: 'A', last_name: String(index), age_group: null })), active_child_count: 5 }])],
    ['incomplete declared page', directoryPage([], 1)],
  ])('rejects malformed directory pages: %s', async (_label, payload) => {
    fetchMock.mockResolvedValueOnce(okJson(payload));
    await expect(fetchFamilyDirectoryPage('org-a')).rejects.toBeInstanceOf(FamiliesApiError);
  });

  it.each([
    ['AbortError', () => { const error = new Error('aborted'); error.name = 'AbortError'; throw error; }],
    ['invalid JSON', () => { throw new SyntaxError('bad json'); }],
  ])('locks an exact mutation when the outcome is ambiguous: %s', async (_label, failure) => {
    fetchMock.mockImplementationOnce(async () => failure());
    const draft = emptyFamilyRegistration();
    draft.name = 'River Family';
    draft.include_primary_guardian = false;
    await expect(createFamily(buildFamilyCreateCommand(draft), 'org-a'))
      .rejects.toSatisfy((caught: unknown) => isCommandOutcomeUnknown(caught));
  });

  it('locks the exact family command when a 2xx mutation projection crosses tenants', async () => {
    fetchMock.mockResolvedValueOnce(okJson({ ...familyResponse, organization_id: 'org-b' }));
    const draft = emptyFamilyRegistration();
    draft.name = 'River Family';
    draft.include_primary_guardian = false;
    await expect(createFamily(buildFamilyCreateCommand(draft), 'org-a'))
      .rejects.toSatisfy((caught: unknown) => isCommandOutcomeUnknown(caught));
  });

  it.each([401, 403, 409, 422])('keeps a genuine HTTP %s mutation rejection definite', async (status) => {
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => ({ detail: 'definite rejection' }) });
    const draft = emptyFamilyRegistration();
    draft.name = 'River Family';
    draft.include_primary_guardian = false;
    const caught = await createFamily(buildFamilyCreateCommand(draft), 'org-a').catch((error) => error);
    expect(caught).toBeInstanceOf(FamiliesApiError);
    expect(caught).toMatchObject({ status, origin: 'http' });
    expect(isCommandOutcomeUnknown(caught)).toBe(false);
  });

  it('keeps a controlled stale 409 as a resolved error rather than an unknown outcome', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ detail: { code: 'stale_childcare_resource', current_version: 7 } }),
    });
    const command = buildFamilyCoreUpdateCommand({
      name: 'River Family', status: 'active', file_number: '',
      consents: { photo_consent: false, field_trip_consent: false, emergency_medical_consent: false },
      additional_notes: '',
    }, 2);
    const caught = await updateFamily('family-1', command, 'org-a').catch((error) => error);
    expect(caught).toBeInstanceOf(FamiliesApiError);
    expect(caught.status).toBe(409);
    expect(isCommandOutcomeUnknown(caught)).toBe(false);
  });

  it.each([408, 425, 500])('locks the exact family command after ambiguous HTTP %s', async (status) => {
    fetchMock.mockResolvedValueOnce({ ok: false, status, json: async () => ({ detail: 'response not confirmed' }) });
    const draft = emptyFamilyRegistration();
    draft.name = 'River Family';
    draft.include_primary_guardian = false;
    const caught = await createFamily(buildFamilyCreateCommand(draft), 'org-a').catch((error) => error);
    expect(isCommandOutcomeUnknown(caught)).toBe(true);
  });

  it('rejects nested children outside the family, organization, version, or protected photo boundary', async () => {
    fetchMock.mockResolvedValueOnce(okJson({
      ...familyResponse,
      children: [{
        id: 'child-1', organization_id: 'org-a', family_id: 'family-1', first_name: 'Amina', middle_name: null,
        last_name: 'River', date_of_birth: '2022-04-12', gender: null, age_group: 'Preschool', is_active: true,
        profile_photo_url: 'https://example.com/api/v1/children/child-1/photo', profile_photo_updated_at: '2026-07-15T12:00:00Z',
        created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-14T00:00:00Z', version: 1, replayed: false,
      }],
    }));
    await expect(fetchFamilyDetail('family-1', 'org-a')).rejects.toThrow('unexpected family-detail response');
  });
});
