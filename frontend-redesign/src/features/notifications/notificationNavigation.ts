import type { NotificationItem } from './notificationsApi';
import type { OrganizationChoice } from '../../api/client';
import { isSafeNotificationTargetId } from './notificationTarget';

const staticPaths = new Set([
  '/attendance',
  '/billing',
  '/dashboard',
  '/incidents',
  '/medications',
  '/rooms',
  '/settings',
  '/staff',
  '/staff-rota',
  '/today',
  '/transport-registry',
]);

// The backend notification ledger is shared by the admin portal and staff app.
// Translate only the exact, registered staff-app destinations into the admin
// portal's equivalent workforce screen. This repairs old ledger rows as well as
// new realtime-delivered notifications without treating the payload as a URL.
const staffAppPathAliases = new Map<string, string>([
  ['/shifts', '/staff-rota'],
  ['/shifts/time-off', '/staff-rota'],
  ['/staff/schedule', '/staff-rota'],
  ['/staff/self/exchange/open-shift-activity', '/staff-rota'],
  ['/staff/self/exchange/open-shifts', '/staff-rota'],
  ['/staff/self/exchange/swaps', '/staff-rota'],
]);

const staffPathEntityTypes = new Map<string, ReadonlySet<string>>([
  ['/shifts', new Set(['staff_schedule'])],
  ['/shifts/time-off', new Set(['staff_time_off'])],
  ['/staff/schedule', new Set(['staff_open_shift', 'staff_schedule'])],
  ['/staff/self/exchange/open-shift-activity', new Set(['staff_open_shift', 'staff_open_shift_engagement'])],
  ['/staff/self/exchange/open-shifts', new Set(['staff_open_shift'])],
  ['/staff/self/exchange/swaps', new Set(['staff_shift_swap'])],
]);

const staffRotaFocusEntities = new Set([
  'staff_availability',
  'staff_time_off',
  'staff_rotation_pattern',
  'staff_open_shift',
  'staff_open_shift_engagement',
  'staff_substitute_profile',
  'staff_shift_swap',
]);

const billingEntities = new Set([
  'billing_account',
  'billing_rate_plan',
  'billing_agreement',
  'billing_invoice',
  'billing_payment',
  'billing_allocation',
  'billing_credit',
]);

const jobViews = new Set(['listings', 'applicants', 'discover', 'offers', 'handoff']);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function focusedPath(path: string, key: 'incident' | 'schedule' | 'plan', entityId: string): string {
  const query = new URLSearchParams({ [key]: entityId });
  return `${path}?${query}`;
}

function focusedStaticPath(action: NonNullable<NotificationItem['action']>, path: string): string | null {
  if (path === '/rooms') {
    if (action.entity_type === 'room_operational_exception') {
      if (!uuid.test(action.entity_id)) return null;
      const query = new URLSearchParams({ view: 'live', exception: action.entity_id });
      return `${path}?${query}`;
    }
    if (!['enrollment', 'room'].includes(action.entity_type) || !isSafeNotificationTargetId(action.entity_id)) return null;
    return path;
  }
  if (path === '/billing') {
    if (!billingEntities.has(action.entity_type) || !isSafeNotificationTargetId(action.entity_id)) return null;
    const query = new URLSearchParams({ focus: action.entity_type, record: action.entity_id });
    return `${path}?${query}`;
  }
  if (path === '/incidents' && action.entity_type === 'incident_record') {
    return isSafeNotificationTargetId(action.entity_id) ? focusedPath(path, 'incident', action.entity_id) : null;
  }
  if (path === '/staff-rota' && action.entity_type === 'staff_schedule') {
    return isSafeNotificationTargetId(action.entity_id) ? focusedPath(path, 'schedule', action.entity_id) : null;
  }
  if (path === '/staff-rota' && staffRotaFocusEntities.has(action.entity_type)) {
    if (!isSafeNotificationTargetId(action.entity_id)) return null;
    const query = new URLSearchParams({ focus: action.entity_type, record: action.entity_id });
    return `${path}?${query}`;
  }
  if (path === '/staff-rota') return null;
  if (path === '/medications') {
    if (action.entity_type !== 'medication_plan' || !isSafeNotificationTargetId(action.entity_id)) return null;
    return focusedPath(path, 'plan', action.entity_id);
  }
  return path;
}

export function safeNotificationActionPath(action: NotificationItem['action']): string | null {
  if (!action || action.path.length > 500) return null;
  if (!action.path.startsWith('/') || action.path.startsWith('//')) return null;
  if (/[\\\u0000-\u001f\u007f]/.test(action.path)) return null;

  const staffPortalPath = staffAppPathAliases.get(action.path);
  if (staffPortalPath) {
    const allowedTypes = staffPathEntityTypes.get(action.path);
    if (!allowedTypes?.has(action.entity_type)) return null;
    return focusedStaticPath(action, staffPortalPath);
  }
  if (staticPaths.has(action.path)) return focusedStaticPath(action, action.path);
  if (/^\/(children|families)\/[A-Za-z0-9][A-Za-z0-9:_-]{0,199}$/.test(action.path)) return action.path;

  const admissionApplication = /^\/admissions\/applications\/([^/?#]+)$/.exec(action.path);
  if (admissionApplication) {
    const applicationId = admissionApplication[1];
    if (
      action.entity_type !== 'admission_application'
      || !uuid.test(applicationId)
      || action.entity_id.toLowerCase() !== applicationId.toLowerCase()
    ) return null;
    return `/admissions/applications/${applicationId}`;
  }

  const legacyApplication = /^\/jobs\/applications\/([^/]+)$/.exec(action.path);
  if (legacyApplication) {
    if (!uuid.test(legacyApplication[1])) return null;
    return `/jobs?view=applicants&application=${legacyApplication[1]}`;
  }

  if (action.path !== '/jobs' && !action.path.startsWith('/jobs?')) return null;
  let url: URL;
  try { url = new URL(action.path, 'https://caresync.invalid'); } catch { return null; }
  if (url.origin !== 'https://caresync.invalid' || url.pathname !== '/jobs' || url.hash) return null;
  const keys = [...url.searchParams.keys()];
  if (keys.some((key) => !['view', 'application'].includes(key))) return null;
  if (url.searchParams.getAll('view').length > 1 || url.searchParams.getAll('application').length > 1) return null;
  const view = url.searchParams.get('view');
  const application = url.searchParams.get('application');
  if (view && !jobViews.has(view)) return null;
  if (application && !isSafeNotificationTargetId(application)) return null;
  if (action.entity_type === 'application' && !isSafeNotificationTargetId(action.entity_id)) return null;
  if (application) url.searchParams.set('view', 'applicants');
  if (action.entity_type === 'application' && isSafeNotificationTargetId(action.entity_id)) {
    url.searchParams.set('view', 'applicants');
    url.searchParams.set('application', action.entity_id);
  }
  return `${url.pathname}${url.search}`;
}

export function notificationOrganizationTarget(
  notificationOrganizationId: string | null,
  currentOrganizationId: string | null,
  choices: OrganizationChoice[],
): 'current' | OrganizationChoice | null {
  if (!notificationOrganizationId || notificationOrganizationId === currentOrganizationId) return 'current';
  return choices.find((choice) => choice.organization_id === notificationOrganizationId) || null;
}
