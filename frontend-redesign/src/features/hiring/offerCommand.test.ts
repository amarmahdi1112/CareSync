import { afterEach, describe, expect, it, vi } from 'vitest';
import { hiringApi } from './hiringApi';

describe('atomic create-and-send offer command', () => {
  it('preserves the same client operation id across an ambiguous retry', async () => {
    vi.stubGlobal('localStorage', { getItem: (key: string) => key === 'caresync-redesign-organization' ? 'org-1' : 'token' });
    const operationId = '11111111-1111-4111-8111-111111111111';
    const response = { id: 'offer', organization_id: 'org-1', application_id: 'application', client_operation_id: operationId, version: 1, status: 'sent', position_title: 'Educator', start_date: null, compensation: null, terms: 'Terms', sent_at: '2026-07-16T12:00:00Z', expires_at: '2026-07-30T12:00:00Z', accepted_at: null, terminal_at: null, created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z' };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(response), { status: 201, headers: { 'Content-Type': 'application/json' } })); vi.stubGlobal('fetch', fetchMock);
    const payload = { position_title: 'Educator', terms: 'Terms', expires_at: response.expires_at, expected_application_version: 1, client_operation_id: operationId };
    await hiringApi.createAndSendOffer('application', payload); await hiringApi.createAndSendOffer('application', payload);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const call of fetchMock.mock.calls) { const init = call[1]; expect(JSON.parse(String(init?.body))).toMatchObject({ client_operation_id: operationId, expected_application_version: 1 }); }
  });
});
afterEach(() => vi.unstubAllGlobals());
