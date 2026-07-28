import type { FeatureId } from '../config/productFeatures';

export interface RealtimeRouteCoverage {
  path: string;
  canonicalSources: readonly string[];
  entities: readonly string[];
  behavior: string;
}

export const realtimeRouteCoverage = {
  onboarding: { path: '/onboarding', canonicalSources: ['onboarding snapshot', 'programs', 'rooms'], entities: ['organization', 'organization_onboarding', 'facility', 'facility_program', 'room'], behavior: 'Refreshes remote truth; preserves a dirty local draft and raises an explicit conflict banner.' },
  dashboard: {
    path: '/dashboard',
    canonicalSources: ['family stats', 'room workspace', 'attendance rosters', 'bounded 0041 live room summary when capability-advertised'],
    entities: ['family', 'child', 'enrollment', 'facility', 'facility_program', 'room', 'attendance_day', 'staff_shift', 'staff_coverage_target', 'staff_room_presence', 'room_operational_exception', 'organization_membership'],
    behavior: 'Rebuilds the complete command snapshot; a mounted 0041 summary also refreshes its canonical live-board projection before cursor commit.',
  },
  admissions: { path: '/admissions', canonicalSources: ['canonical admission decision workspace', 'application detail and event timeline', 'ordered waitlist register', 'derived current intake queue', 'facility directory', 'enrollment-to-billing readiness projection'], entities: ['admission_application', 'admission_waitlist', 'admission_offer', 'family', 'child', 'enrollment', 'facility', 'facility_program', 'room', 'billing_account', 'billing_rate_plan', 'billing_agreement'], behavior: 'Reloads the canonical decision workspace, application detail, waitlist, intake, and finance-readiness projections before the realtime cursor commits; command versions remain server-owned.' },
  today: {
    path: '/today',
    canonicalSources: ['room workspace', 'care room-day', 'room daily-close preview', 'bounded 0041 live room summary when capability-advertised'],
    entities: ['daily_care_record', 'medication_administration', 'incident_record', 'attendance_day', 'attendance_release', 'enrollment', 'child', 'room', 'facility', 'facility_program', 'organization_membership', 'staff_shift', 'staff_coverage_target', 'staff_room_presence', 'room_operational_exception'],
    behavior: 'Replaces the selected room-day from canonical REST; the daily-close subview and mounted 0041 summary refresh before cursor commit, and program or assignment changes cannot leave care actions or room scope stale.',
  },
  families: { path: '/families and /families/:id', canonicalSources: ['family directory/detail', 'private family-authority workspace', 'organization consent-policy versions', 'family-level billing settlement projection'], entities: ['family', 'child', 'enrollment', 'facility_program', 'authority_person', 'authority_evidence', 'authority_evidence_object', 'release_authorization', 'release_rule', 'consent', 'consent_policy', 'child_authority_head', 'billing_account', 'billing_rate_plan', 'billing_agreement', 'billing_invoice', 'billing_payment', 'billing_allocation', 'billing_credit'], behavior: 'Refreshes the family profile, protected authority workspace, and family-level financial truth from canonical REST before the realtime cursor commits.' },
  children: { path: '/children and /children/:id', canonicalSources: ['child roster/profile', 'program directory', 'minimum-necessary child authority summary', 'family finance with child charge attribution'], entities: ['child', 'family', 'enrollment', 'facility', 'facility_program', 'room', 'release_authorization', 'release_rule', 'consent', 'child_authority_head', 'billing_account', 'billing_rate_plan', 'billing_agreement', 'billing_invoice', 'billing_payment', 'billing_allocation', 'billing_credit'], behavior: 'Refreshes child identity, enrollment, authority, family settlement truth, and child charge attribution from canonical REST before the realtime cursor commits.' },
  rooms: {
    path: '/rooms',
    canonicalSources: [
      'room workspace',
      'facility roster',
      '0041 canonical live room projection while Live operations is mounted',
      'bounded room operational exception episodes while Live operations is mounted',
    ],
    entities: [
      'organization',
      'facility',
      'facility_program',
      'room',
      'enrollment',
      'child',
      'attendance_day',
      'staff_shift',
      'staff_schedule',
      'staff_coverage_target',
      'organization_membership',
      'staff_room_presence',
      'room_operational_exception',
    ],
    behavior: 'Refreshes structure and the selected facility roster as one commit; the mounted Live operations mode additionally rebuilds its canonical board and exception page before the realtime cursor advances.',
  },
  attendance: { path: '/attendance', canonicalSources: ['facility directory', 'attendance roster', 'verified-release activation status'], entities: ['attendance_day', 'attendance_release', 'release_checkout_activation', 'enrollment', 'child', 'room', 'facility'], behavior: 'Reconciles the exact roster and facility release mode, including pending idempotent actions; irreversible activation removes legacy checkout and routes verified-recipient departures to the staff app.' },
  medications: { path: '/medications', canonicalSources: ['room workspace', 'medication room-day', 'exact notification-target plan while focused'], entities: ['medication_plan', 'medication_administration', 'attendance_day', 'enrollment', 'child', 'room', 'facility', 'organization_membership'], behavior: 'Refreshes plans, administrations, eligibility, room context, assigned operational scope, and any retained exact-plan focus before the cursor advances.' },
  incidents: { path: '/incidents', canonicalSources: ['room workspace', 'incident room context', 'incident list'], entities: ['incident_record', 'attendance_day', 'enrollment', 'child', 'room', 'facility', 'organization_membership'], behavior: 'Refreshes the complete selected incident workspace and assigned operational scope.' },
  staff: { path: '/staff', canonicalSources: ['staff workspace'], entities: ['staff_invitation', 'organization_membership', 'user', 'staff_shift', 'credential', 'room', 'facility'], behavior: 'Refreshes access, assignment, credential, and shift facts.' },
  'staff-rota': { path: '/staff-rota', canonicalSources: ['staff workspace', 'scheduled staff shifts', 'clock reconciliation', 'staff availability', 'time-off requests', 'shift templates', 'operational coverage targets', '15-minute coverage projection', 'recurring rotation patterns', 'open-shift postings', 'open-shift engagements', 'substitute discovery profiles', 'peer shift swaps'], entities: ['staff_schedule', 'staff_shift', 'staff_availability', 'staff_time_off', 'staff_shift_template', 'staff_coverage_target', 'staff_rotation_pattern', 'staff_open_shift', 'staff_open_shift_engagement', 'staff_substitute_profile', 'staff_shift_swap', 'organization_membership', 'room', 'facility'], behavior: 'Reloads the canonical weekly plan, reconciliation, workforce constraints, immutable rotation snapshots, coverage opportunities, engagement evidence, safe substitute discovery, and atomic swap decisions before the realtime cursor commits.' },
  hiring: { path: '/jobs', canonicalSources: ['ATS workspace', 'credential notifications', 'consent-based candidate discovery while mounted'], entities: ['job', 'candidate', 'application', 'interview', 'offer', 'credential', 'marketplace_interest', 'organization_membership', 'screening_share'], behavior: 'Refreshes the full employer ATS and provisioning/screening handoff, plus the active Discover Talent projection, before the event cursor commits.' },
  billing: { path: '/billing', canonicalSources: ['manual activation boundary', 'billing overview', 'family account register', 'immutable billing documents', 'payment and allocation register', 'effective-dated rates and agreements', 'family, enrollment, facility, and program source facts'], entities: ['billing_manual_activation', 'billing_account', 'billing_rate_plan', 'billing_agreement', 'billing_invoice', 'billing_payment', 'billing_allocation', 'billing_credit', 'family', 'child', 'enrollment', 'facility', 'facility_program'], behavior: 'Refreshes capability after immutable manual activation, then rebuilds the complete financial workspace from canonical REST after every committed ledger or relevant care-contract fact while preserving protected exact-retry command state.' },
  'transport-registry': { path: '/transport-registry', canonicalSources: ['0032 transport registry workspace'], entities: ['transport_registry'], behavior: 'Reloads the exact bounded staff, qualification, authorization, readiness, vehicle, evidence, and review projection before the realtime cursor commits; dirty command forms and durable retry records are not replaced.' },
  settings: { path: '/settings', canonicalSources: ['organization settings', 'facility settings', 'verified-release activation status'], entities: ['organization', 'organization_onboarding', 'facility', 'facility_program', 'release_checkout_activation', 'room', 'user', 'organization_membership'], behavior: 'Refreshes manageable settings, current account facts, and the one-way verified-release activation status while keeping the confirmed organization boundary.' },
} as const satisfies Partial<Record<FeatureId, RealtimeRouteCoverage>>;
