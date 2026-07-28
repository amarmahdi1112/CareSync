import { describe, expect, it } from 'vitest';
import dashboardSource from '../hooks/useCommandData.ts?raw';
import admissionsSource from '../features/admissions/AdmissionsPage.tsx?raw';
import onboardingSource from '../features/onboarding/OnboardingPage.tsx?raw';
import familiesSource from '../features/families/useFamilies.ts?raw';
import familyProfileSource from '../features/families/FamilyProfilePage.tsx?raw';
import todaySource from '../features/daily-care/TodayPage.tsx?raw';
import childrenSource from '../features/children/useChildren.ts?raw';
import childProfileSource from '../features/children/ChildProfilePage.tsx?raw';
import roomsSource from '../features/rooms/RoomsPage.tsx?raw';
import attendanceSource from '../features/attendance/AttendancePage.tsx?raw';
import medicationsSource from '../features/medications/MedicationPage.tsx?raw';
import incidentsSource from '../features/incidents/IncidentsPage.tsx?raw';
import staffSource from '../features/staff/StaffPage.tsx?raw';
import rotaSource from '../features/staff-rota/StaffRotaPage.tsx?raw';
import hiringSource from '../features/hiring/JobsPage.tsx?raw';
import billingSource from '../features/billing/BillingPage.tsx?raw';
import transportRegistrySource from '../features/transport-registry/TransportRegistryPage.tsx?raw';
import settingsSource from '../features/settings/SettingsPage.tsx?raw';
import realtimeProviderSource from './RealtimeContext.tsx?raw';

const occurrenceCount = (source: string, value: string): number =>
  source.split(value).length - 1;

describe('mounted feature integration wiring', () => {
  it('refreshes persistent session-shell facts from the executable organization selector', () => {
    expect(realtimeProviderSource).toContain("featureIntegrationManifest['session-shell'].realtimeEntities");
    expect(realtimeProviderSource).toContain('session.refreshOrganizationFacts()');
  });

  it('keeps organization saves authenticated while the shell refreshes canonical facts', () => {
    const saveOrganization = settingsSource.slice(
      settingsSource.indexOf('const saveOrganization'),
      settingsSource.indexOf('const saveFacility'),
    );
    expect(saveOrganization).toContain('session.refreshOrganizationFacts()');
    expect(saveOrganization).not.toContain('session.retry()');
  });

  it.each([
    ['Dashboard', dashboardSource, 'featureIntegrationManifest.dashboard.realtimeEntities'],
    ['Admissions', admissionsSource, 'featureIntegrationManifest.admissions.realtimeEntities'],
    ['Onboarding', onboardingSource, 'featureIntegrationManifest.onboarding.realtimeEntities'],
    ['Families directory', familiesSource, 'featureIntegrationManifest.families.realtimeEntities'],
    ['Family profile', familyProfileSource, 'featureIntegrationManifest.families.realtimeEntities'],
    ['Children directory', childrenSource, 'featureIntegrationManifest.children.realtimeEntities'],
    ['Child profile', childProfileSource, 'featureIntegrationManifest.children.realtimeEntities'],
    ['Rooms', roomsSource, 'featureIntegrationManifest.rooms.realtimeEntities'],
    ['Attendance', attendanceSource, 'featureIntegrationManifest.attendance.realtimeEntities'],
    ['Medication', medicationsSource, 'featureIntegrationManifest.medications.realtimeEntities'],
    ['Incidents', incidentsSource, 'featureIntegrationManifest.incidents.realtimeEntities'],
    ['Staff', staffSource, 'featureIntegrationManifest.staff.realtimeEntities'],
    ['Rota', rotaSource, "featureIntegrationManifest['staff-rota'].realtimeEntities"],
    ['Hiring', hiringSource, 'featureIntegrationManifest.hiring.realtimeEntities'],
    ['Billing', billingSource, 'featureIntegrationManifest.billing.realtimeEntities'],
    ['Transport registry', transportRegistrySource, "featureIntegrationManifest['transport-registry'].realtimeEntities"],
    ['Settings', settingsSource, 'featureIntegrationManifest.settings.realtimeEntities'],
  ])('%s consumes its manifest selector at runtime', (_label, source, selector) => {
    expect(source).toContain('featureIntegrationManifest');
    expect(source).toContain(`entityTypes: ${selector}`);
  });

  it('drives both the Today daybook and Daily Close refresh from the same manifest contract', () => {
    const selector = 'entityTypes: featureIntegrationManifest.today.realtimeEntities';
    expect(todaySource).toContain("from '../../realtime/featureIntegrationManifest'");
    expect(occurrenceCount(todaySource, selector)).toBe(2);
    expect(todaySource).not.toContain('DAILY_CLOSE_REALTIME_ENTITIES');
  });

  it('does not acknowledge a child event with an older initial directory request still authoritative', () => {
    const registration = childrenSource.slice(
      childrenSource.indexOf('useRealtimeRefresh({'),
      childrenSource.indexOf('useEffect(() => {', childrenSource.indexOf('useRealtimeRefresh({')),
    );
    expect(registration).toContain('refreshChildrenRequest(');
    expect(registration).not.toContain("state.phase !== 'ready'");
    expect(registration).not.toContain('state.requestKey !== requestKey');
  });

  it('refreshes conditional canonical projections that outlive or sit outside their base workspace', () => {
    expect(medicationsSource).toContain('fetchMedicationRealtimeSnapshot({');
    expect(medicationsSource).toContain('focusedPlanId');
    expect(hiringSource).toContain('fetchHiringRealtimeSnapshot(');
    expect(hiringSource).toContain("refreshDiscovery ? cityQuery : null");
  });
});
