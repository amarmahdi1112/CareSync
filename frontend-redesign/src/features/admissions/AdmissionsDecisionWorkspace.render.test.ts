import { createElement } from 'react';
import { act, create, type ReactTestRenderer, type ReactTestInstance } from 'react-test-renderer';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from 'styled-components';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { theme } from '../../styles/theme';

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ORGANIZATION_ONE = '11111111-1111-4111-8111-111111111111';
const ORGANIZATION_TWO = '22222222-2222-4222-8222-222222222222';
const APPLICATION_ID = '33333333-3333-4333-8333-333333333333';
const FACILITY_ID = '44444444-4444-4444-8444-444444444444';
const PROGRAM_ID = '55555555-5555-4555-8555-555555555555';

const harness = vi.hoisted(() => ({
  session: {
    status: 'authenticated',
    organizationUnavailable: false,
    organization: { id: '11111111-1111-4111-8111-111111111111' },
    user: {
      id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      organization_id: '11111111-1111-4111-8111-111111111111',
      membership_status: 'active',
      role: {
        key: 'administrator',
        permissions: ['admissions:read', 'admissions:manage', 'admissions:decide'],
      },
    },
  } as any,
  recovery: {
    activeEntry: null,
    blockReason: null,
    checking: false,
    ready: true,
    laneBlocked: false,
    lastResolved: null,
    lastFinalAbsenceAcknowledgedOperationId: null,
    execute: vi.fn(async (_metadata: unknown, send: (id: string) => Promise<unknown>) => (
      send('66666666-6666-4666-8666-666666666666')
    )),
    checkSavedResult: vi.fn(),
    acknowledgeFinalAbsence: vi.fn(),
    dismissResolved: vi.fn(),
  } as any,
  createApplication: vi.fn(async () => ({ id: '33333333-3333-4333-8333-333333333333' })),
  fetchWorkspace: vi.fn(),
  fetchApplications: vi.fn(),
  fetchWaitlist: vi.fn(),
  fetchLaneDirectory: vi.fn(),
}));

vi.mock('../../auth/SessionContext', () => ({
  useSession: () => harness.session,
}));

vi.mock('../../childcare-commands/ChildcareCommandRecoveryContext', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../childcare-commands/ChildcareCommandRecoveryContext')>();
  return {
    ...original,
    useChildcareCommandRecovery: () => harness.recovery,
  };
});

vi.mock('../../realtime/RealtimeContext', () => ({
  useRealtimeRefresh: () => undefined,
}));

vi.mock('./admissionsDecisionApi', async (importOriginal) => {
  const original = await importOriginal<typeof import('./admissionsDecisionApi')>();
  return {
    ...original,
    createAdmissionApplication: harness.createApplication,
    fetchAdmissionWorkspace: harness.fetchWorkspace,
    fetchAdmissionApplications: harness.fetchApplications,
    fetchAdmissionWaitlist: harness.fetchWaitlist,
    fetchAdmissionLaneDirectory: harness.fetchLaneDirectory,
  };
});

import AdmissionsDecisionWorkspace from './AdmissionsDecisionWorkspace';

const statuses = [
  'draft',
  'submitted',
  'under_review',
  'waitlisted',
  'offered',
  'accepted',
  'declined',
  'withdrawn',
] as const;

function canonicalWorkspace(reference = 'ADM-AAAA') {
  return {
    counts: Object.fromEntries(statuses.map((status) => [status, status === 'draft' ? 1 : 0])),
    lanes: statuses.map((status) => ({
      status,
      count: status === 'draft' ? 1 : 0,
      applications: status === 'draft' ? [{
        id: APPLICATION_ID,
        reference,
        status: 'draft',
        version: 1,
        source: 'administrator_entry',
        preference_count: 1,
        submitted_at: null,
        updated_at: '2026-07-23T03:00:00Z',
        current_lane: null,
        offer_status: null,
      }] : [],
    })),
    waitlist_lane_count: 0,
  };
}

function page(reference = 'ADM-AAAA') {
  return {
    items: [{
      id: APPLICATION_ID,
      reference,
      status: 'draft',
      version: 1,
      source: 'administrator_entry',
      preference_count: 1,
      submitted_at: null,
      updated_at: '2026-07-23T03:00:00Z',
      current_lane: null,
      offer_status: null,
    }],
    total: 26,
    limit: 25,
    offset: 0,
  };
}

function text(node: ReactTestInstance): string {
  return node.children.map((child) => typeof child === 'string' ? child : text(child)).join('');
}

function button(renderer: ReactTestRenderer, label: string): ReactTestInstance {
  const match = renderer.root.findAll((node) => node.type === 'button' && text(node).includes(label))[0];
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}

async function renderWorkspace(
  focusedTabs: string[] = [],
): Promise<ReactTestRenderer> {
  let renderer!: ReactTestRenderer;
  await act(async () => {
    renderer = create(
      createElement(
        ThemeProvider,
        { theme },
        createElement(MemoryRouter, null, createElement(AdmissionsDecisionWorkspace)),
      ),
      {
        createNodeMock: (element) => {
          const props = element.props as Record<string, unknown>;
          return element.type === 'button' && typeof props.id === 'string'
            ? { focus: () => focusedTabs.push(props.id as string) }
            : null;
        },
      },
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  return renderer;
}

beforeEach(() => {
  harness.session.organization = { id: ORGANIZATION_ONE };
  harness.session.user.organization_id = ORGANIZATION_ONE;
  harness.session.user.role.permissions = ['admissions:read', 'admissions:manage', 'admissions:decide'];
  harness.recovery.laneBlocked = false;
  harness.recovery.lastResolved = null;
  harness.recovery.lastFinalAbsenceAcknowledgedOperationId = null;
  harness.recovery.execute.mockClear();
  harness.createApplication.mockClear();
  harness.fetchWorkspace.mockReset().mockResolvedValue(canonicalWorkspace());
  harness.fetchApplications.mockReset().mockResolvedValue(page());
  harness.fetchWaitlist.mockReset().mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
  harness.fetchLaneDirectory.mockReset().mockResolvedValue({
    facilities: [{
      id: FACILITY_ID,
      name: 'North Centre',
      programs: [{ id: PROGRAM_ID, name: 'Daycare', program_type: 'daycare' }],
    }],
  });
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
});

describe('AdmissionsDecisionWorkspace rendered behavior', () => {
  it('renders accessible tabs, a 25-row reachable register, and 100-row waitlist paging controls', async () => {
    const focusedTabs: string[] = [];
    const renderer = await renderWorkspace(focusedTabs);
    const tabs = renderer.root.findAll((node) => node.type === 'button' && node.props.role === 'tab');
    expect(tabs.map(text)).toEqual(expect.arrayContaining([' Pipeline', ' Waitlist', ' New application']));
    expect(tabs.every((tab) => typeof tab.props['aria-selected'] === 'boolean')).toBe(true);
    expect(tabs.map((tab) => tab.props.tabIndex)).toEqual([0, -1, -1]);
    expect(tabs.map((tab) => tab.props['aria-controls'])).toEqual([
      'admissions-panel-pipeline',
      'admissions-panel-waitlist',
      'admissions-panel-new',
    ]);
    expect(renderer.root.findByProps({ role: 'tabpanel' }).props).toMatchObject({
      id: 'admissions-panel-pipeline',
      'aria-labelledby': 'admissions-tab-pipeline',
    });
    expect(renderer.root.find((node) => (
      node.type === 'input' && node.props['aria-label'] === 'Search by application reference'
    )).props.maxLength).toBe(16);
    expect(text(renderer.root)).toContain('Showing 1–1 of 26');

    const preventDefault = vi.fn();
    await act(async () => {
      tabs[0].props.onKeyDown({ key: 'ArrowRight', preventDefault });
    });
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(focusedTabs).toEqual(['admissions-tab-waitlist']);
    expect(text(renderer.root)).toContain('Deterministic waitlist');
    expect(renderer.root.findByProps({ role: 'tabpanel' }).props).toMatchObject({
      id: 'admissions-panel-waitlist',
      'aria-labelledby': 'admissions-tab-waitlist',
    });
    expect(renderer.root.findAll((node) => node.type === 'button' && node.props.role === 'tab').map((tab) => tab.props.tabIndex)).toEqual([-1, 0, -1]);

    await act(async () => {
      renderer.root.findAll((node) => node.type === 'button' && node.props.role === 'tab')[1].props.onKeyDown({
        key: 'End',
        preventDefault,
      });
    });
    expect(focusedTabs.at(-1)).toBe('admissions-tab-new');
    expect(text(renderer.root)).toContain('Create an admission application');
  });

  it('does not render or enable intake controls without admissions:manage', async () => {
    harness.session.user.role.permissions = ['admissions:read'];
    const renderer = await renderWorkspace();
    expect(renderer.root.findAll((node) => node.type === 'button' && node.props.role === 'tab').map(text)).not.toContain(' New application');
    expect(text(renderer.root)).not.toContain('Create an admission application');
  });

  it('prepares the admission create command before send with no PII in journal metadata', async () => {
    const renderer = await renderWorkspace();
    await act(async () => {
      button(renderer, 'New application').props.onClick();
    });

    const originalFormData = globalThis.FormData;
    class StubFormData {
      get(name: string): string {
        return ({
          child_first_name: 'Amina',
          child_last_name: 'Noor',
          date_of_birth: '2023-04-15',
          contact_first_name: 'Samira',
          contact_last_name: 'Noor',
          relationship: 'Mother',
          email: 'samira@example.com',
          telephone: '',
          internal_note: 'Private note',
        } as Record<string, string>)[name] ?? '';
      }
    }
    vi.stubGlobal('FormData', StubFormData as unknown as typeof FormData);

    const selects = renderer.root.findAllByType('select');
    const facilitySelect = selects.find((node) => text(node).includes('Choose facility'));
    if (!facilitySelect) throw new Error('Facility select missing');
    await act(async () => {
      facilitySelect.props.onChange({ target: { value: FACILITY_ID } });
    });
    const programSelect = renderer.root.findAllByType('select').find((node) => text(node).includes('Choose program'));
    if (!programSelect) throw new Error('Program select missing');
    await act(async () => {
      programSelect.props.onChange({ target: { value: PROGRAM_ID } });
    });
    const requestedStart = renderer.root.findAllByType('input').find((node) => node.props.type === 'date' && !node.props.max);
    if (!requestedStart) throw new Error('Requested start input missing');
    await act(async () => {
      requestedStart.props.onChange({ target: { value: '2026-09-01' } });
    });

    const form = renderer.root.findAllByType('form').find((node) => text(node).includes('Create draft'));
    if (!form) throw new Error('Create form missing');
    await act(async () => {
      await form.props.onSubmit({ preventDefault: () => undefined, currentTarget: {} });
    });
    vi.stubGlobal('FormData', originalFormData);

    const metadata = harness.recovery.execute.mock.calls[0][0] as Record<string, unknown>;
    expect(metadata).toMatchObject({
      commandType: 'admission.application.create',
      targetType: 'admission_application',
      expectedTargetId: null,
      expectedActionOwnerId: null,
    });
    expect(JSON.stringify(metadata)).not.toMatch(/Amina|Samira|example|Private note/);
    expect(harness.createApplication).toHaveBeenCalledWith(
      ORGANIZATION_ONE,
      '66666666-6666-4666-8666-666666666666',
      expect.objectContaining({ child: expect.objectContaining({ first_name: 'Amina' }) }),
    );
  });

  it('drops a late organization response instead of repainting the new workspace', async () => {
    let resolveFirst!: (value: ReturnType<typeof canonicalWorkspace>) => void;
    harness.fetchWorkspace.mockReset().mockImplementation((organizationId: string) => (
      organizationId === ORGANIZATION_ONE
        ? new Promise((resolve) => { resolveFirst = resolve; })
        : Promise.resolve(canonicalWorkspace('ADM-SECOND'))
    ));
    harness.fetchApplications.mockReset().mockImplementation((organizationId: string) => (
      Promise.resolve(organizationId === ORGANIZATION_ONE ? page('ADM-FIRST') : page('ADM-SECOND'))
    ));

    const renderer = await renderWorkspace();
    harness.session.organization = { id: ORGANIZATION_TWO };
    harness.session.user.organization_id = ORGANIZATION_TWO;
    await act(async () => {
      renderer.update(createElement(
        ThemeProvider,
        { theme },
        createElement(MemoryRouter, null, createElement(AdmissionsDecisionWorkspace)),
      ));
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      resolveFirst(canonicalWorkspace('ADM-FIRST'));
    });

    expect(text(renderer.root)).toContain('ADM-SECOND');
    expect(text(renderer.root)).not.toContain('ADM-FIRST');
  });
});
