import { describe, expect, it } from 'vitest';
import appSource from '../../App.tsx?raw';
import decisionClientSource from './admissionsDecisionApi.ts?raw';
import pageSource from './AdmissionApplicationPage.tsx?raw';

describe('AdmissionApplicationPage release wiring', () => {
  it('owns an exact full-page route before the admissions wildcard', () => {
    const detailRoute = appSource.indexOf('path="admissions/applications/:applicationId"');
    const wildcardRoute = appSource.indexOf('path="admissions/*"');

    expect(detailRoute).toBeGreaterThan(-1);
    expect(wildcardRoute).toBeGreaterThan(detailRoute);
    expect(pageSource).not.toContain('Drawer');
  });

  it('rebuilds from the private canonical detail after realtime invalidation and commands', () => {
    expect(decisionClientSource).toContain("cache: 'no-store'");
    expect(pageSource).toContain('featureIntegrationManifest.admissions.realtimeEntities');
    expect(pageSource).toContain('await loadApplication();');
    expect(pageSource).toContain('const operationId = crypto.randomUUID();');
  });

  it('requires signed duplicate review before atomic acceptance conversion', () => {
    expect(pageSource).toContain('fetchAdmissionConversionCandidates');
    expect(pageSource).toContain('acceptAdmissionOffer');
    expect(pageSource).toContain("commandType: 'admission.offer.accept_and_convert'");
    expect(pageSource).toContain('Room placement remains a separate approval');
    expect(pageSource).toContain('confirmedDistinct');
  });

  it('makes update and correction full, versioned facts replacements', () => {
    expect(pageSource).toContain("allowedActions.has(kind)");
    expect(pageSource).toContain("ACCESS.admissionsManage");
    expect(pageSource).toContain("ACCESS.admissionsDecide");
    expect(pageSource).toContain("updateAdmissionApplication(organizationId");
    expect(pageSource).toContain("correctAdmissionApplication(organizationId");
    expect(pageSource).toContain("factsEditor.preferences.length >= 5");
    expect(pageSource).toContain("rank: index + 1");
    expect(pageSource).toContain("Each ranked facility/program lane must be unique.");
    expect(pageSource).toContain("returns the application to review and closes any active waitlist entry");
    expect(pageSource).toContain("application.version !== factsEditor.applicationVersion");
  });

  it('uses the frozen facts command request names and nullable closed waitlist position', () => {
    const correctStart = decisionClientSource.indexOf('export async function correctAdmissionApplication');
    const correctEnd = decisionClientSource.indexOf('export async function runAdmissionCommand', correctStart);
    const correctSource = decisionClientSource.slice(correctStart, correctEnd);

    expect(correctSource).toContain('expected_application_version: application.version');
    expect(correctSource).toContain('primary_contact: input.primary_contact');
    expect(correctSource).toContain('preferences: input.preferences');
    expect(correctSource).not.toContain('expected_waitlist_version');
    expect(decisionClientSource).toContain('position: number | null');
    expect(pageSource).toContain("application.waitlist.position === null");
  });
});
