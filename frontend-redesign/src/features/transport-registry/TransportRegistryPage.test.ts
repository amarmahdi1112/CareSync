import { describe, expect, it } from 'vitest';
import pageSource from './TransportRegistryPage.tsx?raw';
import dialogSource from './TransportRegistryDialog.tsx?raw';
import capabilitySource from './capability.tsx?raw';
import appSource from '../../App.tsx?raw';

describe('transport registry manager presentation boundary', () => {
  it('keeps the route behind exact 0032 capability and manage permission', () => {
    expect(appSource).toContain('if (!capability.enabled) return <NotFoundPage />');
    expect(appSource).toContain('<TransportRegistryRoute><TransportRegistryPage /></TransportRegistryRoute>');
    expect(capabilitySource).toContain('ACCESS.transportManage');
    expect(capabilitySource).not.toContain('ACCESS.transportRead');
  });

  it('loads only canonical manager data and invalidates it for registry events', () => {
    expect(pageSource).toContain('transportRegistryApi.workspace');
    expect(pageSource).toContain("eventPrefixes: ['transport_registry.']");
    expect(pageSource).toContain("entityTypes: featureIntegrationManifest['transport-registry'].realtimeEntities");
    expect(pageSource).not.toContain('apiRequest');
  });

  it('keeps declaration and qualification uploads on the signed-in membership only', () => {
    expect(pageSource).toContain('staff.membership_id === ownMembershipId');
    expect(dialogSource).toContain('transportRegistryApi.declareSelf');
    expect(dialogSource).toContain('transportRegistryApi.uploadSelfQualification');
    expect(dialogSource).not.toMatch(/declare(?:Driver)?For/i);
  });

  it('gates every upload control with evidence_upload_available', () => {
    expect(pageSource).toContain('capability?.evidence_upload_available');
    expect(dialogSource).toContain("throw new Error('Evidence uploads are temporarily unavailable.')");
    expect(dialogSource).toContain('disabled={!evidenceUploadAvailable}');
  });

  it('does not promise that encrypted source retrieval survives every upload outage', () => {
    expect(pageSource).toContain('Uploads paused');
    expect(pageSource).toContain('exact source retrieval is checked when opened');
    expect(dialogSource).toContain('Existing metadata remains available; exact source retrieval is checked when opened.');
    expect(pageSource).not.toContain('Private content remains viewable when uploads pause');
    expect(dialogSource).not.toContain('Existing records remain readable.');
  });

  it('does not invite a duplicate immutable command when its confirmed refresh fails', () => {
    expect(pageSource).toContain('The server confirmed this immutable change, but the canonical refresh is pending. Do not submit it again');
    expect(pageSource).toContain('appliedWorkspaceGeneration');
  });

  it('requires an explicit one-way confirmation before vehicle retirement', () => {
    expect(dialogSource).toContain('name="confirm_retire"');
    expect(dialogSource).toContain("data.get('confirm_retire') !== 'confirmed'");
    expect(dialogSource).toContain('Retire vehicle permanently');
  });

  it('states and preserves the excluded operational boundary', () => {
    for (const label of ['children', 'addresses', 'routes', 'manifests', 'trips', 'dispatch', 'gps', 'live location']) {
      expect(pageSource.toLowerCase()).toContain(label);
    }
    expect(pageSource).toContain('Operational driver ready: false');
    expect(pageSource).not.toContain('operational_driver_ready: true');
    expect(pageSource).not.toContain('dispatch_authorized: true');
  });
});
