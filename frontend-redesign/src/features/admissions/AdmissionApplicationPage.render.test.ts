import { createElement } from 'react';
import { act, create, type ReactTestInstance, type ReactTestRenderer } from 'react-test-renderer';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ThemeProvider } from 'styled-components';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { theme } from '../../styles/theme';
import pageSource from './AdmissionApplicationPage.tsx?raw';
import type {
  AdmissionConversionCandidateReview,
  AdmissionDetail,
} from './admissionsDecisionApi';

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ORGANIZATION_ID = '11111111-1111-4111-8111-111111111111';
const APPLICATION_ID = '22222222-2222-4222-8222-222222222222';
const PREFERENCE_ID = '33333333-3333-4333-8333-333333333333';
const FACILITY_ID = '44444444-4444-4444-8444-444444444444';
const PROGRAM_ID = '55555555-5555-4555-8555-555555555555';
const WAITLIST_ID = '66666666-6666-4666-8666-666666666666';
const OFFER_ID = '77777777-7777-4777-8777-777777777777';
const FAMILY_ID = '88888888-8888-4888-8888-888888888888';
const CHILD_ID = '99999999-9999-4999-8999-999999999999';
const JOURNAL_OPERATION_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const harness = vi.hoisted(() => ({
  session: {
    status: 'authenticated',
    organizationUnavailable: false,
    organization: { id: '11111111-1111-4111-8111-111111111111' },
    user: {
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      organization_id: '11111111-1111-4111-8111-111111111111',
      membership_status: 'active',
      assigned_facility_ids: [],
      assigned_room_ids: [],
      role: {
        key: 'admissions_test_role',
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
    execute: vi.fn(),
    checkSavedResult: vi.fn(),
    acknowledgeFinalAbsence: vi.fn(),
    dismissResolved: vi.fn(),
  } as any,
  fetchApplication: vi.fn(),
  fetchLaneDirectory: vi.fn(),
  createOffer: vi.fn(),
  fetchCandidates: vi.fn(),
  acceptOffer: vi.fn(),
  runCommand: vi.fn(),
  runOfferCommand: vi.fn(),
  waitlistApplication: vi.fn(),
  reopenReview: vi.fn(),
  updateApplication: vi.fn(),
  correctApplication: vi.fn(),
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
    fetchAdmissionApplication: harness.fetchApplication,
    fetchAdmissionLaneDirectory: harness.fetchLaneDirectory,
    createAdmissionOffer: harness.createOffer,
    fetchAdmissionConversionCandidates: harness.fetchCandidates,
    acceptAdmissionOffer: harness.acceptOffer,
    runAdmissionCommand: harness.runCommand,
    runAdmissionOfferCommand: harness.runOfferCommand,
    waitlistAdmissionApplication: harness.waitlistApplication,
    reopenAdmissionReview: harness.reopenReview,
    updateAdmissionApplication: harness.updateApplication,
    correctAdmissionApplication: harness.correctApplication,
  };
});

import AdmissionApplicationPage from './AdmissionApplicationPage';

function canonicalDetail(
  state: 'waitlisted' | 'offered' | 'accepted' = 'waitlisted',
): AdmissionDetail {
  const waitlisted = state === 'waitlisted';
  const offered = state === 'offered';
  return {
    id: APPLICATION_ID,
    organization_id: ORGANIZATION_ID,
    reference: 'ADM-1234ABCDEF56',
    source: 'administrator_entry',
    status: state,
    version: waitlisted ? 4 : offered ? 5 : 6,
    child: { first_name: 'Amina', last_name: 'Noor', date_of_birth: '2023-04-15' },
    contact: {
      first_name: 'Samira',
      last_name: 'Noor',
      relationship: 'Mother',
      email: 'samira@example.com',
      telephone: null,
    },
    internal_note: null,
    preferences: [{
      id: PREFERENCE_ID,
      rank: 1,
      facility_id: FACILITY_ID,
      facility_name: 'North Centre',
      program_id: PROGRAM_ID,
      program_name: 'Daycare',
      requested_start_date: '2026-09-01',
      application_version: waitlisted ? 4 : 5,
    }],
    waitlist: {
      id: WAITLIST_ID,
      status: waitlisted ? 'active' : 'offered',
      version: 8,
      facility_id: FACILITY_ID,
      facility_name: 'North Centre',
      program_id: PROGRAM_ID,
      program_name: 'Daycare',
      requested_start_date: '2026-09-01',
      priority_at: '2026-07-23T03:00:00Z',
      position: 1,
      closure_reason: null,
      created_at: '2026-07-23T03:00:00Z',
      updated_at: '2026-07-23T03:00:00Z',
      closed_at: null,
    },
    offer: waitlisted ? null : {
      id: OFFER_ID,
      status: offered ? 'open' : 'accepted',
      version: 3,
      facility_id: FACILITY_ID,
      facility_name: 'North Centre',
      program_id: PROGRAM_ID,
      program_name: 'Daycare',
      proposed_start_date: '2026-09-01',
      respond_by_date: '2026-08-25',
      prior_application_status: 'waitlisted',
      issued_at: '2026-07-23T04:00:00Z',
      withdrawn_at: null,
      declined_at: null,
      accepted_at: offered ? null : '2026-07-23T05:00:00Z',
    },
    conversion: state === 'accepted' ? {
      id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      resolution_mode: 'create_family_and_child',
      family_id: FAMILY_ID,
      child_id: CHILD_ID,
      enrollment_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
      converted_at: '2026-07-23T05:00:00Z',
    } : null,
    timeline: [],
    timeline_total: 0,
    allowed_actions: waitlisted
      ? ['issue_offer', 'reopen_review']
      : offered
        ? ['withdraw_offer', 'decline_offer', 'accept_and_convert']
        : [],
    committed_versions: {
      application: waitlisted ? 4 : offered ? 5 : 6,
      waitlist: 8,
      offer: waitlisted ? null : 3,
    },
    replayed: false,
    replay_receipt: null,
    created_at: '2026-07-23T03:00:00Z',
    updated_at: '2026-07-23T04:00:00Z',
    submitted_at: '2026-07-23T03:10:00Z',
    review_started_at: '2026-07-23T03:20:00Z',
    terminal_at: state === 'accepted' ? '2026-07-23T05:00:00Z' : null,
  };
}

function candidateReview(): AdmissionConversionCandidateReview {
  return {
    application_id: APPLICATION_ID,
    application_version: 5,
    offer_id: OFFER_ID,
    offer_version: 3,
    families: [{
      id: FAMILY_ID,
      display_label: 'Samira N. · family candidate',
      version: 2,
      status: 'active',
      match_reasons: ['primary_contact_email'],
    }],
    children: [{
      id: CHILD_ID,
      family_id: FAMILY_ID,
      display_label: 'Amina N. · 15 Apr 2023',
      version: 4,
      is_active: true,
      match_reasons: ['child_name_and_date_of_birth'],
      has_open_enrollment: false,
    }],
    review_token: 'signed-review-token',
    expires_at: '2026-07-23T05:15:00Z',
  };
}

function text(node: ReactTestInstance): string {
  return node.children.map((child) => typeof child === 'string' ? child : text(child)).join('');
}

function hostButton(renderer: ReactTestRenderer, label: string): ReactTestInstance {
  const match = renderer.root.findAll((node) => (
    node.type === 'button' && text(node).includes(label)
  ))[0];
  if (!match) throw new Error(`Button not found: ${label}`);
  return match;
}

function labelledControl(
  renderer: ReactTestRenderer,
  label: string,
  type: 'select' | 'input' | 'textarea',
): ReactTestInstance {
  const field = renderer.root.findAll((node) => (
    node.type === 'label' && text(node).includes(label)
  ))[0];
  if (!field) throw new Error(`Field not found: ${label}`);
  return field.findByType(type);
}

async function renderDetail(
  focused: string[] = [],
): Promise<ReactTestRenderer> {
  let renderer!: ReactTestRenderer;
  await act(async () => {
    renderer = create(
      createElement(
        ThemeProvider,
        { theme },
        createElement(
          MemoryRouter,
          { initialEntries: [`/admissions/applications/${APPLICATION_ID}`] },
          createElement(
            Routes,
            null,
            createElement(Route, {
              path: '/admissions/applications/:applicationId',
              element: createElement(AdmissionApplicationPage),
            }),
          ),
        ),
      ),
      {
        createNodeMock: (element) => {
          const props = element.props as Record<string, unknown>;
          return element.type === 'div' && props.tabIndex === -1
            ? { focus: () => focused.push('next-valid-action') }
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
  harness.session.organization = { id: ORGANIZATION_ID };
  harness.session.user.organization_id = ORGANIZATION_ID;
  harness.session.user.role.permissions = ['admissions:read', 'admissions:manage', 'admissions:decide'];
  harness.recovery.laneBlocked = false;
  harness.recovery.lastResolved = null;
  harness.recovery.lastFinalAbsenceAcknowledgedOperationId = null;
  harness.recovery.execute.mockReset().mockImplementation(
    async (_metadata: unknown, send: (operationId: string) => Promise<unknown>) => (
      send(JOURNAL_OPERATION_ID)
    ),
  );
  harness.fetchApplication.mockReset().mockResolvedValue(canonicalDetail());
  harness.fetchLaneDirectory.mockReset().mockResolvedValue({
    facilities: [{
      id: FACILITY_ID,
      name: 'North Centre',
      programs: [{ id: PROGRAM_ID, name: 'Daycare', program_type: 'daycare' }],
    }],
  });
  harness.createOffer.mockReset().mockResolvedValue(canonicalDetail('offered'));
  harness.fetchCandidates.mockReset().mockResolvedValue(candidateReview());
  harness.acceptOffer.mockReset().mockResolvedValue(canonicalDetail('accepted'));
  harness.runCommand.mockReset().mockResolvedValue(canonicalDetail());
  harness.runOfferCommand.mockReset().mockResolvedValue(canonicalDetail('offered'));
  harness.waitlistApplication.mockReset().mockResolvedValue(canonicalDetail());
  harness.reopenReview.mockReset().mockResolvedValue(canonicalDetail());
  harness.updateApplication.mockReset().mockResolvedValue(canonicalDetail());
  harness.correctApplication.mockReset().mockResolvedValue(canonicalDetail());
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal('innerWidth', 390);
});

describe('AdmissionApplicationPage rendered release behavior', () => {
  it('enforces the exact manage-versus-decide permission for each offer control', async () => {
    harness.fetchApplication.mockResolvedValue(canonicalDetail('offered'));
    harness.session.user.role.permissions = ['admissions:read', 'admissions:manage'];
    const manageRenderer = await renderDetail();
    expect(hostButton(manageRenderer, 'Record offer decline').props.disabled).toBe(false);
    expect(hostButton(manageRenderer, 'Withdraw offer').props.disabled).toBe(true);
    expect(hostButton(manageRenderer, 'Review and accept offer').props.disabled).toBe(true);
    await act(async () => {
      manageRenderer.unmount();
    });

    harness.session.user.role.permissions = ['admissions:read', 'admissions:decide'];
    const decideRenderer = await renderDetail();
    expect(hostButton(decideRenderer, 'Record offer decline').props.disabled).toBe(true);
    expect(hostButton(decideRenderer, 'Withdraw offer').props.disabled).toBe(false);
    expect(hostButton(decideRenderer, 'Review and accept offer').props.disabled).toBe(false);
  });

  it('renders the 390px-safe offer flow, locks a waitlisted lane, and prepares its journal before send', async () => {
    const order: string[] = [];
    harness.session.user.role.permissions = ['admissions:read', 'admissions:decide'];
    harness.recovery.execute.mockImplementation(
      async (_metadata: unknown, send: (operationId: string) => Promise<unknown>) => {
        order.push('journal');
        return send(JOURNAL_OPERATION_ID);
      },
    );
    harness.createOffer.mockImplementation(async () => {
      order.push('send');
      return canonicalDetail('offered');
    });
    const renderer = await renderDetail();

    await act(async () => {
      hostButton(renderer, 'Issue offer').props.onClick();
    });
    const facility = labelledControl(renderer, 'Facility', 'select');
    const program = labelledControl(renderer, 'Program', 'select');
    const start = labelledControl(renderer, 'Proposed start date', 'input');
    const respondBy = labelledControl(renderer, 'Respond by', 'input');
    expect(facility.props).toMatchObject({ disabled: true, value: FACILITY_ID });
    expect(program.props).toMatchObject({ disabled: true, value: PROGRAM_ID });
    expect(start.props.value).toBe('2026-09-01');
    expect(respondBy.props.max).toBe('2026-09-01');
    expect(pageSource).toContain('@media (max-width: 520px) { grid-template-columns: 1fr; }');

    const confirmation = renderer.root.findAll((node) => (
      node.type === 'input' && node.props.type === 'checkbox'
    ))[0];
    await act(async () => {
      confirmation.props.onChange({ target: { checked: true } });
    });
    const form = renderer.root.findAllByType('form').find((node) => (
      text(node).includes('Issue a program offer?')
    ));
    if (!form) throw new Error('Offer form missing');
    await act(async () => {
      await form.props.onSubmit({ preventDefault: () => undefined });
    });

    expect(order).toEqual(['journal', 'send']);
    expect(harness.recovery.execute.mock.calls[0][0]).toMatchObject({
      commandType: 'admission.offer.issue',
      targetType: 'admission_offer',
      expectedTargetId: null,
      expectedActionOwnerId: APPLICATION_ID,
    });
    const sentApplication = harness.createOffer.mock.calls[0][1] as AdmissionDetail;
    expect(sentApplication.status).toBe('waitlisted');
    expect(sentApplication.waitlist?.version).toBe(8);
    expect(harness.createOffer.mock.calls[0][2]).toBe(JOURNAL_OPERATION_ID);
    expect(harness.createOffer.mock.calls[0][3]).toMatchObject({
      facility_id: FACILITY_ID,
      program_id: PROGRAM_ID,
      proposed_start_date: '2026-09-01',
    });
  });

  it('renders reviewed duplicate choices, restores focus, announces unsafe resolution, and then commits the explicit decision', async () => {
    const order: string[] = [];
    const focused: string[] = [];
    harness.fetchApplication.mockResolvedValue(canonicalDetail('offered'));
    harness.session.user.role.permissions = ['admissions:read', 'admissions:decide'];
    harness.recovery.execute.mockImplementation(
      async (_metadata: unknown, send: (operationId: string) => Promise<unknown>) => {
        order.push('journal');
        return send(JOURNAL_OPERATION_ID);
      },
    );
    harness.acceptOffer.mockImplementation(async () => {
      order.push('send');
      return canonicalDetail('accepted');
    });
    const renderer = await renderDetail(focused);

    await act(async () => {
      await hostButton(renderer, 'Review and accept offer').props.onClick();
    });
    expect(focused).toContain('next-valid-action');
    expect(text(renderer.root)).toContain('Samira N. · family candidate');
    expect(text(renderer.root)).toContain('Amina N. · 15 Apr 2023');

    const resolution = labelledControl(renderer, 'Resolution', 'select');
    await act(async () => {
      resolution.props.onChange({ target: { value: 'create_family_and_child' } });
    });
    let checkboxes = renderer.root.findAll((node) => node.type === 'input' && node.props.type === 'checkbox');
    await act(async () => {
      checkboxes.at(-1)!.props.onChange({ target: { checked: true } });
    });
    let conversionForm = renderer.root.findAllByType('form').find((node) => (
      text(node).includes('Resolve reviewed people and accept')
    ));
    if (!conversionForm) throw new Error('Conversion form missing');
    await act(async () => {
      await conversionForm!.props.onSubmit({ preventDefault: () => undefined });
    });
    const alert = renderer.root.findAll((node) => (
      node.type === 'div' && node.props.role === 'alert'
    ))[0];
    expect(text(alert)).toContain('record why this is a distinct person');
    expect(harness.acceptOffer).not.toHaveBeenCalled();

    checkboxes = renderer.root.findAll((node) => node.type === 'input' && node.props.type === 'checkbox');
    await act(async () => {
      checkboxes[0].props.onChange({ target: { checked: true } });
    });
    const reason = labelledControl(renderer, 'Distinct-person reason', 'textarea');
    await act(async () => {
      reason.props.onChange({ target: { value: 'Same surname, but verified as a different household and child.' } });
    });
    checkboxes = renderer.root.findAll((node) => node.type === 'input' && node.props.type === 'checkbox');
    await act(async () => {
      checkboxes.at(-1)!.props.onChange({ target: { checked: true } });
    });
    conversionForm = renderer.root.findAllByType('form').find((node) => (
      text(node).includes('Resolve reviewed people and accept')
    ));
    await act(async () => {
      await conversionForm!.props.onSubmit({ preventDefault: () => undefined });
    });

    expect(order).toEqual(['journal', 'send']);
    expect(harness.recovery.execute.mock.calls[0][0]).toMatchObject({
      commandType: 'admission.offer.accept_and_convert',
      targetType: 'admission_offer',
      expectedTargetId: OFFER_ID,
      expectedActionOwnerId: APPLICATION_ID,
    });
    expect(harness.acceptOffer.mock.calls[0][2]).toMatchObject({
      application_id: APPLICATION_ID,
      application_version: 5,
      offer_id: OFFER_ID,
      offer_version: 3,
      review_token: 'signed-review-token',
    });
    expect(harness.acceptOffer.mock.calls[0][4]).toEqual({
      resolution_mode: 'create_family_and_child',
      confirmed_distinct_person: true,
      distinct_person_reason: 'Same surname, but verified as a different household and child.',
    });
    expect(focused.length).toBeGreaterThanOrEqual(2);
  });

  it('keeps a delayed historical offer receipt separate from the current actionable offer projection', async () => {
    const delayed = canonicalDetail('offered');
    const historicalOfferId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
    delayed.replayed = true;
    delayed.replay_receipt = {
      command_type: 'admission.offer.issue',
      target_type: 'admission_offer',
      target_id: historicalOfferId,
      committed_version: 1,
    };
    harness.fetchApplication.mockResolvedValue(delayed);
    harness.session.user.role.permissions = ['admissions:read', 'admissions:decide'];
    const renderer = await renderDetail();

    expect(text(renderer.root)).toContain('Offer · Open');
    await act(async () => {
      await hostButton(renderer, 'Review and accept offer').props.onClick();
    });
    const reviewedApplication = harness.fetchCandidates.mock.calls[0][1] as AdmissionDetail;
    expect(reviewedApplication.replay_receipt?.target_id).toBe(historicalOfferId);
    expect(reviewedApplication.offer?.id).toBe(OFFER_ID);
    expect(text(renderer.root)).toContain('Resolve reviewed people and accept');
  });
});
