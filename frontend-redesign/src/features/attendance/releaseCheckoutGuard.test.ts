import { describe, expect, it } from 'vitest';
import attendanceApiSource from './attendanceApi.ts?raw';
import attendancePageSource from './AttendancePage.tsx?raw';
import manifestSource from '../../realtime/featureIntegrationManifest.ts?raw';
import coverageSource from '../../realtime/realtimeCoverage.ts?raw';

describe('attendance verified-release checkout guard', () => {
  it('reads the exact facility status and rejects organization or facility drift', () => {
    expect(attendanceApiSource).toContain('/release-checkout-activation');
    expect(attendanceApiSource).toContain("status.organization_id !== organizationId");
    expect(attendanceApiSource).toContain("status.facility_id !== facilityId");
    expect(attendanceApiSource).toContain("status.activated && status.legacy_checkout_allowed");
  });

  it('fails closed before creating or sending a legacy checkout operation', () => {
    const action = attendancePageSource.slice(
      attendancePageSource.indexOf("const act = async"),
      attendancePageSource.indexOf('const saved ='),
    );
    expect(action).toContain("if (action === 'out')");
    expect(action).toContain('if (!legacyCheckoutAllowed)');
    expect(action).toContain('await fetchAttendanceReleaseCheckoutActivation(facilityId, organizationId)');
    expect(action.indexOf('await fetchAttendanceReleaseCheckoutActivation')).toBeLessThan(action.indexOf('const operation: PendingAttendanceOperation'));
    expect(action.indexOf('latestActivation.activated')).toBeLessThan(action.indexOf('await checkOut('));
  });

  it('removes the legacy action after activation while retaining explicit staff-app guidance', () => {
    expect(attendancePageSource).toContain("presentation.primaryAction === 'check-out' && legacyCheckoutAllowed");
    expect(attendancePageSource).toContain("releaseActivation?.activated && <CheckoutHandoff>");
    expect(attendancePageSource).toContain('Complete every departure in the CareSync staff app.');
    expect(attendancePageSource).toContain('check-in, no-show, details, and permitted corrections remain available');
    expect(attendancePageSource).toContain('to="/settings?section=facility"');
  });

  it('refreshes the guard when irreversible activation arrives in realtime', () => {
    expect(manifestSource).toContain("attendance: portal('attendance', ['attendance_day', 'release_checkout_activation'])");
    expect(coverageSource).toContain("'verified-release activation status'");
    expect(coverageSource).toContain("'release_checkout_activation'");
    expect(attendancePageSource).toContain('fetchAttendanceReleaseCheckoutActivation(nextFacilityId, organizationId)');
  });
});
