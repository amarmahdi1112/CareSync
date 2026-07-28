import { realtimeRouteCoverage } from './realtimeCoverage';

/**
 * The integration spine is deliberately separate from the notification inbox.
 *
 * - `realtimeEntities` are quiet invalidation hints. A matching screen must
 *   rebuild itself from canonical REST before the socket cursor advances.
 * - `attention` is reserved for a person who must make or review a decision.
 *   Routine synchronization must never create an alert merely to make two
 *   screens agree.
 */
export type PortalIntegrationId =
  | 'session-shell'
  | 'onboarding'
  | 'dashboard'
  | 'admissions'
  | 'today'
  | 'families'
  | 'children'
  | 'rooms'
  | 'attendance'
  | 'medications'
  | 'incidents'
  | 'staff'
  | 'staff-rota'
  | 'hiring'
  | 'billing'
  | 'transport-registry'
  | 'settings';

export type MobileIntegrationId =
  | 'candidate-onboarding'
  | 'candidate-jobs'
  | 'candidate-applications'
  | 'candidate-profile'
  | 'staff-room'
  | 'staff-attendance'
  | 'staff-daily-care'
  | 'staff-medications'
  | 'staff-incidents'
  | 'staff-daily-close'
  | 'staff-clock'
  | 'staff-rota-view'
  | 'staff-workforce'
  | 'staff-exchange'
  | 'staff-transport'
  | 'notification-inbox';

export type IntegrationId = PortalIntegrationId | MobileIntegrationId;
type PortalRouteIntegrationId = Exclude<PortalIntegrationId, 'session-shell'>;

export interface AttentionContract {
  /** Human decisions only; an empty list means quiet synchronization. */
  reasons: readonly string[];
  /** Closed internal routes, never arbitrary URLs. */
  exactDestinations: readonly string[];
}

export interface FeatureIntegrationContract {
  surface: 'portal' | 'mobile';
  canonicalSources: readonly string[];
  /** Canonical entity types that commands on this surface can change. */
  produces: readonly string[];
  /** Realtime invalidations that force a canonical rebuild on this surface. */
  realtimeEntities: readonly string[];
  attention: AttentionContract;
}

const portal = (
  id: PortalRouteIntegrationId,
  produces: readonly string[],
  reasons: readonly string[] = [],
  exactDestinations: readonly string[] = [],
): FeatureIntegrationContract => ({
  surface: 'portal',
  canonicalSources: realtimeRouteCoverage[id].canonicalSources,
  produces,
  realtimeEntities: realtimeRouteCoverage[id].entities,
  attention: { reasons, exactDestinations },
});

const mobile = (
  canonicalSources: readonly string[],
  produces: readonly string[],
  realtimeEntities: readonly string[],
  reasons: readonly string[] = [],
  exactDestinations: readonly string[] = [],
): FeatureIntegrationContract => ({
  surface: 'mobile', canonicalSources, produces, realtimeEntities,
  attention: { reasons, exactDestinations },
});

export const featureIntegrationManifest = {
  'session-shell': {
    surface: 'portal',
    canonicalSources: ['authenticated organization record', 'selectable organization contexts'],
    produces: [],
    realtimeEntities: ['organization', 'organization_membership'],
    attention: { reasons: [], exactDestinations: [] },
  },
  onboarding: portal('onboarding', ['organization', 'organization_onboarding', 'facility', 'facility_program', 'room']),
  dashboard: portal('dashboard', []),
  admissions: portal(
    'admissions',
    ['admission_application', 'admission_waitlist', 'admission_offer', 'family', 'child', 'enrollment'],
    ['application submitted', 'admissions decision required', 'offer response required', 'conversion needs review'],
    ['/admissions/applications/:application_id'],
  ),
  today: portal('today', ['daily_care_record']),
  families: portal('families', ['family', 'authority_person', 'authority_evidence', 'authority_evidence_object', 'release_authorization', 'release_rule', 'consent', 'consent_policy', 'child_authority_head']),
  children: portal('children', ['child', 'enrollment']),
  rooms: portal(
    'rooms',
    [
      'facility',
      'facility_program',
      'room',
      'enrollment',
      'room_operational_exception',
    ],
    ['room operational signal needs manager review'],
    ['/rooms'],
  ),
  attendance: portal('attendance', ['attendance_day', 'release_checkout_activation']),
  medications: portal(
    'medications',
    ['medication_plan', 'medication_administration'],
    ['authorization revoked', 'authorized plan activated'],
    ['/medications?plan=:medication_plan_id'],
  ),
  incidents: portal(
    'incidents',
    ['incident_record'],
    ['review requested', 'returned for changes', 'review finalized', 'external follow-up required'],
    ['/incidents?incident=:incident_id'],
  ),
  staff: portal(
    'staff',
    ['staff_invitation', 'organization_membership', 'user'],
    ['staff scope changed'],
    ['/today'],
  ),
  'staff-rota': portal(
    'staff-rota',
    ['staff_schedule', 'staff_availability', 'staff_time_off', 'staff_shift_template', 'staff_coverage_target', 'staff_rotation_pattern', 'staff_open_shift', 'staff_open_shift_engagement', 'staff_substitute_profile', 'staff_shift_swap'],
    ['published shift needs response', 'time-off decision', 'coverage response', 'shift-trade decision'],
    [
      '/staff-rota?schedule=:schedule_id',
      '/staff-rota?focus=:entity_type&record=:entity_id',
    ],
  ),
  hiring: portal(
    'hiring',
    ['job', 'candidate', 'application', 'interview', 'offer', 'credential', 'marketplace_interest', 'organization_membership', 'screening_share'],
    ['new application', 'interview response', 'offer response', 'credential changed', 'screening review'],
    ['/jobs?view=applicants&application=:application_id'],
  ),
  billing: portal(
    'billing',
    ['billing_manual_activation', 'billing_account', 'billing_rate_plan', 'billing_agreement', 'billing_invoice', 'billing_payment', 'billing_allocation', 'billing_credit'],
    ['billing exception requires review', 'unallocated payment requires review'],
    ['/billing'],
  ),
  'transport-registry': portal(
    'transport-registry',
    ['transport_registry'],
    ['evidence or readiness review required'],
    ['/transport-registry'],
  ),
  settings: portal('settings', ['organization', 'organization_onboarding', 'facility', 'facility_program', 'release_checkout_activation', 'room', 'user']),

  'candidate-onboarding': mobile(
    ['candidate onboarding state', 'credential analyses', 'screening profile'],
    ['candidate', 'credential', 'screening_share'],
    ['candidate', 'credential', 'screening_share', 'user'],
  ),
  'candidate-jobs': mobile(
    ['public job listings', 'candidate marketplace profile'],
    [],
    ['job', 'candidate', 'marketplace_profile'],
  ),
  'candidate-applications': mobile(
    ['candidate application timeline', 'interviews', 'offers'],
    ['application', 'interview', 'offer', 'marketplace_interest'],
    ['job', 'application', 'interview', 'offer', 'marketplace_interest', 'screening_share', 'organization_membership'],
    ['interview response required', 'offer response required', 'application status changed'],
    ['candidate_applications'],
  ),
  'candidate-profile': mobile(
    ['candidate profile', 'credential history', 'screening documents'],
    ['candidate', 'credential', 'marketplace_profile', 'user'],
    ['candidate', 'credential', 'marketplace_profile', 'user'],
    ['credential review or identity mismatch'],
    ['candidate_profile'],
  ),
  'staff-room': mobile(
    ['staff bootstrap', 'assigned room roster', 'release context', 'published schedules', 'operational coverage targets', 'current room presence', 'current-room live safety projection'],
    ['staff_room_presence'],
    ['organization_membership', 'room', 'facility', 'child', 'enrollment', 'attendance_day', 'attendance_release', 'release_authorization', 'release_rule', 'consent', 'child_authority_head', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'staff_room_presence', 'room_operational_exception'],
  ),
  'staff-attendance': mobile(
    ['assigned room roster', 'attendance day', 'current room presence'],
    ['attendance_day', 'attendance_release'],
    ['attendance_day', 'attendance_release', 'child', 'enrollment', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'organization_membership', 'facility', 'room', 'staff_room_presence', 'room_operational_exception'],
  ),
  'staff-daily-care': mobile(
    ['care room-day', 'attendance day', 'current room presence'],
    ['daily_care_record'],
    ['daily_care_record', 'attendance_day', 'attendance_release', 'child', 'enrollment', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'organization_membership', 'facility', 'room', 'staff_room_presence', 'room_operational_exception'],
  ),
  'staff-medications': mobile(
    ['medication room-day', 'attendance day', 'current room presence'],
    ['medication_plan', 'medication_administration'],
    ['medication_plan', 'medication_administration', 'attendance_day', 'child', 'enrollment', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'organization_membership', 'facility', 'room', 'staff_room_presence', 'room_operational_exception'],
    ['authorization or plan status requires review'],
    ['staff_medications'],
  ),
  'staff-incidents': mobile(
    ['incident room context', 'incident records', 'current room presence'],
    ['incident_record'],
    ['incident_record', 'attendance_day', 'child', 'enrollment', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'organization_membership', 'facility', 'room', 'staff_room_presence', 'room_operational_exception'],
    ['incident review result'],
    ['staff_incidents'],
  ),
  'staff-daily-close': mobile(
    ['room daily-close preview', 'current room presence'],
    [],
    ['attendance_day', 'attendance_release', 'daily_care_record', 'medication_administration', 'incident_record', 'child', 'enrollment', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'organization_membership', 'facility', 'room', 'staff_room_presence', 'room_operational_exception'],
  ),
  'staff-clock': mobile(
    ['published schedules', 'actual shifts', 'current room presence'],
    ['staff_shift', 'staff_schedule', 'staff_room_presence'],
    ['attendance_day', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'organization_membership', 'facility', 'room', 'staff_room_presence', 'room_operational_exception'],
    ['published shift or schedule response'],
    ['staff_clock'],
  ),
  'staff-rota-view': mobile(
    ['published schedules', 'actual shift reconciliation'],
    [],
    ['attendance_day', 'staff_shift', 'staff_schedule', 'staff_coverage_target', 'organization_membership', 'facility', 'room', 'staff_room_presence', 'room_operational_exception'],
  ),
  'staff-workforce': mobile(
    ['availability', 'time off'],
    ['staff_availability', 'staff_time_off'],
    ['staff_availability', 'staff_time_off', 'organization_membership'],
    ['time-off decision'],
    ['staff_workforce'],
  ),
  'staff-exchange': mobile(
    ['open shifts', 'engagements', 'peer swaps'],
    ['staff_open_shift_engagement', 'staff_shift_swap'],
    ['staff_open_shift', 'staff_open_shift_engagement', 'staff_shift_swap', 'staff_schedule'],
    ['coverage offer or shift-trade response'],
    ['staff_open_shifts', 'staff_shift_swaps'],
  ),
  'staff-transport': mobile(
    ['personal transport registry projection'],
    ['transport_registry'],
    ['transport_registry'],
    ['evidence or readiness review required'],
    ['staff_more'],
  ),
  'notification-inbox': mobile(
    ['user-private notification ledger'],
    ['notification', 'notification_preference', 'push_subscription'],
    ['notification', 'notification_delivery', 'notification_preference'],
  ),
} as const satisfies Record<IntegrationId, FeatureIntegrationContract>;

export interface CrossFeatureDependency {
  producer: IntegrationId;
  entity: string;
  consumers: readonly IntegrationId[];
  reason: string;
}

/**
 * Explicit organ-to-organ edges. These are the relationships most likely to
 * cause operationally dangerous stale state if a consumer forgets an entity.
 */
export const crossFeatureDependencies = [
  { producer: 'settings', entity: 'organization', consumers: ['session-shell', 'onboarding', 'rooms', 'settings'], reason: 'Organization identity and timezone must update the persistent shell and every mounted organization editor without replacing a valid authenticated session.' },
  { producer: 'settings', entity: 'facility_program', consumers: ['onboarding', 'dashboard', 'admissions', 'today', 'families', 'children', 'rooms', 'billing', 'settings'], reason: 'Program type and lifecycle drive room choice, child placement, care actions, and the eligible effective-dated billing plan.' },
  { producer: 'settings', entity: 'facility', consumers: ['onboarding', 'dashboard', 'admissions', 'today', 'children', 'rooms', 'attendance', 'medications', 'incidents', 'staff', 'staff-rota', 'settings'], reason: 'Facility identity, lifecycle, and timezone are rendered across care and workforce projections.' },
  { producer: 'rooms', entity: 'room', consumers: ['dashboard', 'admissions', 'today', 'children', 'rooms', 'attendance', 'medications', 'incidents', 'staff', 'staff-rota', 'settings', 'staff-room', 'staff-attendance', 'staff-daily-care', 'staff-medications', 'staff-incidents', 'staff-daily-close', 'staff-clock', 'staff-rota-view'], reason: 'Room scope connects enrollment, care, attendance, medications, incidents, and workforce assignment.' },
  { producer: 'families', entity: 'family', consumers: ['dashboard', 'admissions', 'families', 'children', 'billing'], reason: 'Family lifecycle gates whether linked child enrollment and its financial account are operational.' },
  { producer: 'families', entity: 'child_authority_head', consumers: ['families', 'children', 'staff-room'], reason: 'Every authority revision must refresh the private family workspace, minimum child summary, and staff release-context bootstrap from canonical truth.' },
  { producer: 'children', entity: 'child', consumers: ['dashboard', 'admissions', 'families', 'children', 'rooms', 'attendance', 'today', 'medications', 'incidents', 'billing', 'staff-room', 'staff-attendance', 'staff-daily-care', 'staff-medications', 'staff-incidents', 'staff-daily-close'], reason: 'One child identity is shared by every care, placement, and child-attributed billing projection.' },
  { producer: 'children', entity: 'enrollment', consumers: ['dashboard', 'admissions', 'families', 'children', 'rooms', 'attendance', 'today', 'medications', 'incidents', 'billing', 'staff-room', 'staff-attendance', 'staff-daily-care', 'staff-medications', 'staff-incidents', 'staff-daily-close'], reason: 'Enrollment is the bridge from a child to program, facility, room, roster, care eligibility, and effective billing agreement.' },
  { producer: 'attendance', entity: 'attendance_day', consumers: ['dashboard', 'today', 'attendance', 'medications', 'incidents', 'staff-room', 'staff-attendance', 'staff-daily-care', 'staff-medications', 'staff-incidents', 'staff-daily-close'], reason: 'Presence gates care updates and contributes to daily close.' },
  { producer: 'staff-daily-care', entity: 'daily_care_record', consumers: ['today', 'staff-daily-care', 'staff-daily-close'], reason: 'The room daybook and daily close must agree after every care record.' },
  { producer: 'staff-medications', entity: 'medication_administration', consumers: ['today', 'medications', 'staff-medications', 'staff-daily-close'], reason: 'Medication outcome is both a live workflow fact and a daily-close attention fact.' },
  { producer: 'staff-incidents', entity: 'incident_record', consumers: ['today', 'incidents', 'staff-incidents', 'staff-daily-close'], reason: 'Incident status drives both review work and daily-close attention.' },
  { producer: 'staff', entity: 'organization_membership', consumers: ['session-shell', 'staff', 'staff-rota', 'hiring', 'settings', 'staff-room', 'staff-attendance', 'staff-clock', 'staff-rota-view', 'staff-workforce'], reason: 'Membership is the authority and room-scope bridge between hiring, staff access, and operational screens; the session shell must immediately refresh the current identity after authority changes.' },
  { producer: 'staff-rota', entity: 'staff_schedule', consumers: ['staff-rota', 'staff-clock', 'staff-rota-view', 'staff-exchange'], reason: 'Published plans, staff responses, actual clocks, and exchange workflows share one schedule fact.' },
  { producer: 'hiring', entity: 'application', consumers: ['hiring', 'candidate-applications'], reason: 'Employer pipeline and candidate timeline must converge on one application state.' },
  { producer: 'hiring', entity: 'interview', consumers: ['hiring', 'candidate-applications'], reason: 'Interview proposals and responses are a two-sided workflow.' },
  { producer: 'hiring', entity: 'offer', consumers: ['hiring', 'candidate-applications'], reason: 'Offer state is shared between employer and candidate and can lead to staff provisioning.' },
  { producer: 'billing', entity: 'billing_account', consumers: ['admissions', 'families', 'children', 'billing'], reason: 'Enrollment readiness and every family financial projection must converge on one tenant-scoped account identity.' },
  { producer: 'billing', entity: 'billing_rate_plan', consumers: ['admissions', 'families', 'children', 'billing'], reason: 'Published effective-dated care rates must immediately refresh enrollment readiness and profile finance projections.' },
  { producer: 'billing', entity: 'billing_agreement', consumers: ['admissions', 'families', 'children', 'billing'], reason: 'The reviewed enrollment agreement connects intake readiness, family finance, child charge attribution, and invoice issue.' },
  { producer: 'billing', entity: 'billing_invoice', consumers: ['families', 'children', 'billing'], reason: 'Issued family financial documents and receivable totals must refresh together from immutable source facts.' },
  { producer: 'billing', entity: 'billing_payment', consumers: ['families', 'children', 'billing'], reason: 'Family-level payments, unapplied funds and allocations must reconcile in one canonical financial checkpoint.' },
  { producer: 'billing', entity: 'billing_allocation', consumers: ['families', 'children', 'billing'], reason: 'An allocation changes family invoice settlement without inventing a child-level payment or outstanding balance.' },
  { producer: 'billing', entity: 'billing_credit', consumers: ['families', 'children', 'billing'], reason: 'Credits change family invoice settlement and must refresh every profile that shows that family-level financial truth.' },
  { producer: 'transport-registry', entity: 'transport_registry', consumers: ['transport-registry', 'staff-transport'], reason: 'Manager review and staff evidence views share one non-operational registry projection.' },
] as const satisfies readonly CrossFeatureDependency[];

export function downstreamConsumersFor(entity: string): IntegrationId[] {
  return (Object.entries(featureIntegrationManifest) as Array<[IntegrationId, FeatureIntegrationContract]>)
    .filter(([, contract]) => contract.realtimeEntities.includes(entity))
    .map(([id]) => id);
}

export const portalIntegrationIds = Object.entries(featureIntegrationManifest)
  .filter(([, contract]) => contract.surface === 'portal')
  .map(([id]) => id as PortalIntegrationId);
