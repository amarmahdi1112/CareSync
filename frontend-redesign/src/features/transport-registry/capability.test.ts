import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  parseTransportRegistryCapability,
  TRANSPORT_REGISTRY_CAPABILITY_ENDPOINT,
  TRANSPORT_REGISTRY_WORKSPACE_PATH,
  transportRegistryCapabilityApi,
  TransportRegistryCapabilityError,
} from './capability';

afterEach(() => vi.unstubAllGlobals());

const marker = {
  schema_version: '0032',
  runtime_available: true,
  manager_available: true,
  workspace_path: TRANSPORT_REGISTRY_WORKSPACE_PATH,
  evidence_upload_available: true,
  operational_driver_ready: false,
  dispatch_authorized: false,
} as const;

describe('transport registry manager runtime capability', () => {
  it('uses a manager-only probe that cannot be activated by the 0031 self marker', () => {
    expect(TRANSPORT_REGISTRY_CAPABILITY_ENDPOINT).toBe('/staff/transport-registry/capability');
    expect(parseTransportRegistryCapability(marker)).toEqual(marker);
  });

  it.each([
    null,
    {},
    { driver_vehicle_registry: marker },
    { ...marker, schema_version: '0031' },
    { ...marker, runtime_available: false },
    { ...marker, manager_available: false },
    { ...marker, workspace_path: '/api/v1/staff/self/transport-registry' },
    { ...marker, evidence_upload_available: 'yes' },
    { ...marker, operational_driver_ready: true },
    { ...marker, dispatch_authorized: true },
    { ...marker, manager_command_path: '/api/v1/staff/transport-registry' },
  ])('fails closed for old, inactive, authority-granting, or inexact capability %#', (value) => {
    expect(() => parseTransportRegistryCapability(value)).toThrow(TransportRegistryCapabilityError);
  });

  it('accepts a read-only evidence-pipeline outage without widening authority', () => {
    expect(parseTransportRegistryCapability({ ...marker, evidence_upload_available: false }).evidence_upload_available).toBe(false);
  });

  it('fails closed on a retained-schema 403 without starting a global authorization recheck', async () => {
    const events: string[] = [];
    vi.stubGlobal('localStorage', { getItem: (key: string) => key === 'caresync-redesign-organization' ? 'org-a' : 'token' });
    vi.stubGlobal('window', { dispatchEvent: (event: Event) => { events.push(event.type); } });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Not Found' }), { status: 403, headers: { 'Content-Type': 'application/json' } })));

    await expect(transportRegistryCapabilityApi.get()).rejects.toMatchObject({ status: 403 });
    expect(events).toEqual([]);
  });
});
