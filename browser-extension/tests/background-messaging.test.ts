import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

type Listener = (
  message: Record<string, unknown>,
  sender: Record<string, unknown>,
  sendResponse: (response: Record<string, unknown>) => void,
) => boolean;

const STORAGE_KEY = 'caresyncAttendanceState';
const stored: Record<string, unknown> = {};
let listener: Listener;

const sendMessage = vi.fn();
const executeScript = vi.fn(async () => undefined);
const fetchMock = vi.fn();
const getTab = vi.fn(async (tabId: number) => ({ id: tabId, url: 'https://web.kinderlogix.com/content.php' }));
const queryTabs = vi.fn(async () => [] as Array<Record<string, unknown>>);

function startableState() {
  return {
    version: 1,
    status: 'ready',
    connection: {
      tabId: 41,
      origin: 'https://web.kinderlogix.com',
      url: 'https://web.kinderlogix.com/content.php',
      scriptId: 'caresync-test',
      connectedAt: '2026-07-14T00:00:00.000Z',
    },
    dataset: {
      id: 'dataset-1',
      children: [{ id: 'source-1', name: 'Jitu Regassa' }],
      records: [{
        date: '2026-07-13',
        sourceChildId: 'source-1',
        sourceChildName: 'Jitu Regassa',
        sessions: [{ start: '08:00', end: '16:00' }],
      }],
    },
    portal: {
      isPortal: true,
      pageGroupId: '42850',
      children: [{ id: 'portal-1', name: 'Jitu Regassa' }],
    },
    mappings: { 'source-1': 'portal-1' },
    mappingMemory: {},
    settings: { overwriteExisting: false, timeoutMs: 20_000, retryLimit: 2 },
    logs: [],
  };
}

function portalScanResponse() {
  return {
    ok: true,
    portal: {
      isPortal: true,
      pageGroupId: '42850',
      children: [{ id: 'portal-1', name: 'Jitu Regassa' }],
    },
  };
}

function dispatch(
  message: Record<string, unknown>,
  sender: Record<string, unknown> = {},
): Promise<Record<string, any>> {
  return new Promise((resolve) => {
    const keepAlive = listener(message, sender, resolve);
    expect(keepAlive).toBe(true);
  });
}

beforeAll(async () => {
  const chromeMock = {
    storage: {
      local: {
        get: vi.fn(async (key: string) => ({ [key]: stored[key] })),
        set: vi.fn(async (value: Record<string, unknown>) => {
          Object.assign(stored, value);
        }),
      },
    },
    runtime: {
      onInstalled: { addListener: vi.fn() },
      onMessage: {
        addListener: vi.fn((value: Listener) => {
          listener = value;
        }),
      },
    },
    sidePanel: { setPanelBehavior: vi.fn(async () => undefined) },
    tabs: {
      sendMessage,
      get: getTab,
      query: queryTabs,
    },
    scripting: {
      executeScript,
      getRegisteredContentScripts: vi.fn(async () => []),
      unregisterContentScripts: vi.fn(async () => undefined),
      registerContentScripts: vi.fn(async () => undefined),
    },
  };
  vi.stubGlobal('chrome', chromeMock);
  vi.stubGlobal('fetch', fetchMock);
  await import('../src/background');
});

beforeEach(() => {
  stored[STORAGE_KEY] = startableState();
  sendMessage.mockReset();
  executeScript.mockClear();
  fetchMock.mockReset();
  getTab.mockReset();
  getTab.mockImplementation(async (tabId: number) => ({ id: tabId, url: 'https://web.kinderlogix.com/content.php' }));
  queryTabs.mockReset();
  queryTabs.mockResolvedValue([]);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('stale Chrome tab recovery', () => {
  it('clears a dead saved tab on panel load while preserving durable data and checkpoints', async () => {
    const state = startableState() as Record<string, any>;
    state.mappingMemory = {
      'source-1': {
        sourceId: 'source-1',
        sourceName: 'Jitu Regassa',
        portalId: 'portal-1',
        portalName: 'Jitu Regassa',
        pageGroupId: '42850',
        savedAt: '2026-07-14T00:00:00.000Z',
      },
    };
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-1',
      portalChildName: 'Jitu Regassa',
      pageGroupId: '42850',
      confidence: 0.93,
      reason: 'Rejected pair',
      deniedAt: '2026-07-14T01:00:00.000Z',
    }];
    state.aiSuggestions = [{
      sourceChildId: 'source-1',
      portalChildId: 'portal-1',
      confidence: 0.93,
      reason: 'Pending stale suggestion',
    }];
    state.checkpoint = { dateIndex: 3, recordIndex: 5, sessionIndex: 0, phase: 'save_start' };
    stored[STORAGE_KEY] = state;
    getTab.mockRejectedValue(new Error('No tab with id: 1910166309'));

    const response = await dispatch({ type: 'GET_STATE' });

    expect(response.ok).toBe(true);
    expect(response.state).toMatchObject({
      status: 'idle',
      dataset: expect.objectContaining({ id: 'dataset-1' }),
      portal: null,
      mappings: {},
      mappingMemory: expect.objectContaining({ 'source-1': expect.any(Object) }),
      aiDeniedSuggestions: [expect.objectContaining({ sourceChildId: 'source-1' })],
      checkpoint: expect.objectContaining({ dateIndex: 3, recordIndex: 5 }),
    });
    expect(response.state.connection).toBeUndefined();
    expect(response.state.aiSuggestions).toBeUndefined();

    const unsolicitedReady = await dispatch(
      { type: 'CONTENT_READY', portal: portalScanResponse().portal },
      { tab: { id: 52, url: 'https://web.kinderlogix.com/content.php' } },
    );
    expect(unsolicitedReady.ok).toBe(true);
    expect(unsolicitedReady.state.connection).toBeUndefined();
    expect(unsolicitedReady.state.portal).toBeNull();
  });

  it('uses the active KinderLogix tab when an explicit preferred tab ID is stale', async () => {
    const staleTabId = 1910166309;
    const currentTab = { id: 52, url: 'https://web.kinderlogix.com/content.php' };
    stored[STORAGE_KEY] = { ...startableState(), connection: { ...startableState().connection, tabId: staleTabId } };
    getTab.mockImplementation(async (tabId: number) => {
      if (tabId === staleTabId) throw new Error(`No tab with id: ${tabId}`);
      return { id: tabId, url: currentTab.url };
    });
    queryTabs
      .mockResolvedValueOnce([currentTab])
      .mockResolvedValueOnce([currentTab]);
    sendMessage.mockResolvedValueOnce(portalScanResponse());

    const response = await dispatch({ type: 'CONNECT_PORTAL', tabId: staleTabId });

    expect(response.ok).toBe(true);
    expect(response.state.connection.tabId).toBe(currentTab.id);
    expect(response.state.portal).toMatchObject({ isPortal: true, pageGroupId: '42850' });
    expect(sendMessage).toHaveBeenCalledWith(currentTab.id, { type: 'SCAN_PORTAL' });
  });

  it('self-heals Scan by reconnecting an inactive stale connection to the current portal tab', async () => {
    const staleTabId = 1910166309;
    const currentTab = { id: 52, url: 'https://web.kinderlogix.com/content.php' };
    stored[STORAGE_KEY] = { ...startableState(), connection: { ...startableState().connection, tabId: staleTabId } };
    getTab.mockImplementation(async (tabId: number) => {
      if (tabId === staleTabId) throw new Error(`No tab with id: ${tabId}`);
      return { id: tabId, url: currentTab.url };
    });
    queryTabs
      .mockResolvedValueOnce([currentTab])
      .mockResolvedValueOnce([currentTab]);
    sendMessage.mockResolvedValueOnce(portalScanResponse());

    const response = await dispatch({ type: 'SCAN_PORTAL' });

    expect(response.ok).toBe(true);
    expect(response.state.connection.tabId).toBe(currentTab.id);
    expect(response.state.portal).toMatchObject({ isPortal: true, pageGroupId: '42850' });
  });

  it('reconnects a dead running tab as paused instead of silently continuing', async () => {
    const staleTabId = 1910166309;
    const currentTab = { id: 52, url: 'https://web.kinderlogix.com/content.php' };
    stored[STORAGE_KEY] = {
      ...startableState(),
      status: 'running',
      connection: { ...startableState().connection, tabId: staleTabId },
      checkpoint: { dateIndex: 2, recordIndex: 4, sessionIndex: 0, phase: 'save_start' },
    };
    getTab.mockImplementation(async (tabId: number) => {
      if (tabId === staleTabId) throw new Error(`No tab with id: ${tabId}`);
      return { id: tabId, url: currentTab.url };
    });
    sendMessage.mockResolvedValueOnce(portalScanResponse());

    const response = await dispatch({ type: 'CONNECT_PORTAL', tabId: currentTab.id });

    expect(response.ok).toBe(true);
    expect(response.state).toMatchObject({
      status: 'paused',
      connection: { tabId: currentTab.id },
      checkpoint: expect.objectContaining({ dateIndex: 2, recordIndex: 4 }),
    });
    expect(response.state.status).not.toBe('running');
  });

  it('refuses to start on a dead tab and clears only the stale connection state', async () => {
    stored[STORAGE_KEY] = startableState();
    getTab.mockRejectedValue(new Error('No tab with id: 41'));

    const response = await dispatch({
      type: 'START_RUN',
      mappings: { 'source-1': 'portal-1' },
      includedSourceChildIds: ['source-1'],
      overwriteAcknowledged: true,
    });

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/closed or no longer shows KinderLogix/i);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(executeScript).not.toHaveBeenCalled();
    expect(stored[STORAGE_KEY]).toMatchObject({
      status: 'idle',
      dataset: expect.objectContaining({ id: 'dataset-1' }),
      portal: null,
      mappings: {},
    });
    expect((stored[STORAGE_KEY] as Record<string, any>).connection).toBeUndefined();
  });

  it('preserves a paused checkpoint and requires reconnect before Resume', async () => {
    stored[STORAGE_KEY] = {
      ...startableState(),
      status: 'paused',
      checkpoint: {
        stage: 'daily',
        dayStage: 'entry',
        dateIndex: 4,
        recordIndex: 7,
        sessionIndex: 1,
        phase: 'save_end',
        attempt: 2,
      },
    };
    getTab.mockRejectedValue(new Error('No tab with id: 41'));

    const response = await dispatch({ type: 'RESUME_RUN' });

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/closed/i);
    expect(stored[STORAGE_KEY]).toMatchObject({
      status: 'paused',
      portal: null,
      mappings: {},
      checkpoint: {
        dateIndex: 4,
        recordIndex: 7,
        sessionIndex: 1,
        phase: 'save_end',
      },
      error: expect.stringMatching(/checkpoint/i),
    });
    expect((stored[STORAGE_KEY] as Record<string, any>).connection).toBeUndefined();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it('allows Stop locally while clearing a dead connected tab', async () => {
    stored[STORAGE_KEY] = {
      ...startableState(),
      status: 'running',
      checkpoint: { dateIndex: 2, recordIndex: 4, sessionIndex: 0, phase: 'save_start' },
    };
    getTab.mockRejectedValue(new Error('No tab with id: 41'));

    const response = await dispatch({ type: 'STOP_RUN' });

    expect(response.ok).toBe(true);
    expect(response.state).toMatchObject({
      status: 'stopped',
      portal: null,
      mappings: {},
      checkpoint: expect.objectContaining({ dateIndex: 2, recordIndex: 4 }),
    });
    expect(response.state.connection).toBeUndefined();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it('treats a reused tab ID that navigated away from KinderLogix as stale', async () => {
    stored[STORAGE_KEY] = startableState();
    getTab.mockResolvedValue({ id: 41, url: 'https://example.com/' });

    const response = await dispatch({ type: 'GET_STATE' });

    expect(response.ok).toBe(true);
    expect(response.state.connection).toBeUndefined();
    expect(response.state.portal).toBeNull();
    expect(response.state.mappings).toEqual({});
  });
});

describe('denied AI name recommendation rematching', () => {
  function aiReviewState(): Record<string, any> {
    return {
      ...startableState(),
      mappings: {},
      portal: {
        isPortal: true,
        pageGroupId: '42850',
        children: [
          { id: 'portal-1', name: 'Jitu Regasa' },
          { id: 'portal-2', name: 'Jitu Ragassa' },
        ],
      },
      aiSuggestions: [{
        sourceChildId: 'source-1',
        sourceChildName: 'Jitu Regassa',
        portalChildId: 'portal-1',
        portalChildName: 'Jitu Regasa',
        pageGroupId: '42850',
        confidence: 0.96,
        reason: 'Likely spelling variation',
      }],
      aiMatch: {
        model: 'deepseek-chat',
        threshold: 0.92,
        acceptedCount: 0,
        suggestionCount: 1,
        remainingCount: 1,
        matchedAt: '2026-07-14T01:00:00.000Z',
      },
      aiDeniedSuggestions: [],
    };
  }

  function successfulAiResponse(matches: Array<Record<string, unknown>>) {
    return {
      ok: true,
      json: async () => ({
        model: 'deepseek-chat',
        threshold: 0.92,
        chunkCount: 1,
        matches,
      }),
    };
  }

  it('persists the exact denied pair and removes it from pending review', async () => {
    stored[STORAGE_KEY] = aiReviewState();

    const response = await dispatch({
      type: 'DISMISS_AI_SUGGESTION',
      sourceId: 'source-1',
      portalId: 'portal-1',
    });

    expect(response.ok).toBe(true);
    expect(response.state.aiSuggestions).toEqual([]);
    expect(response.state.aiDeniedSuggestions).toEqual([
      expect.objectContaining({
        sourceChildId: 'source-1',
        sourceChildName: 'Jitu Regassa',
        portalChildId: 'portal-1',
        portalChildName: 'Jitu Regasa',
        pageGroupId: '42850',
      }),
    ]);
  });

  it('rejects a stale denial that is not the exact pending pair', async () => {
    stored[STORAGE_KEY] = aiReviewState();

    const response = await dispatch({
      type: 'DISMISS_AI_SUGGESTION',
      sourceId: 'source-1',
      portalId: 'portal-2',
    });

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/no longer pending/i);
    expect((stored[STORAGE_KEY] as Record<string, any>).aiDeniedSuggestions).toEqual([]);
    expect((stored[STORAGE_KEY] as Record<string, any>).aiSuggestions).toHaveLength(1);
  });

  it('does not let a concurrent portal-ready refresh resurrect a denied suggestion', async () => {
    stored[STORAGE_KEY] = aiReviewState();
    const portal = (stored[STORAGE_KEY] as Record<string, any>).portal;

    const [denied, refreshed] = await Promise.all([
      dispatch({
        type: 'DISMISS_AI_SUGGESTION',
        sourceId: 'source-1',
        portalId: 'portal-1',
      }),
      dispatch(
        { type: 'CONTENT_READY', portal },
        { tab: { id: 41, url: 'https://web.kinderlogix.com/content.php' } },
      ),
    ]);

    expect(denied.ok).toBe(true);
    expect(refreshed.ok).toBe(true);
    expect((stored[STORAGE_KEY] as Record<string, any>).aiSuggestions).toEqual([]);
    expect((stored[STORAGE_KEY] as Record<string, any>).aiDeniedSuggestions).toEqual([
      expect.objectContaining({ sourceChildId: 'source-1', portalChildId: 'portal-1' }),
    ]);
  });

  it('rematches only denied children and sends every rejected pair as an exclusion', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    state.dataset.children.push({ id: 'source-2', name: 'Already Approved Child' });
    state.portal.children.push({ id: 'portal-3', name: 'Already Approved Child' });
    state.mappings = { 'source-2': 'portal-3' };
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-1',
      portalChildName: 'Jitu Regasa',
      pageGroupId: '42850',
      confidence: 0.96,
      reason: 'Likely spelling variation',
      deniedAt: '2026-07-14T01:05:00.000Z',
    }];
    stored[STORAGE_KEY] = state;
    fetchMock.mockResolvedValueOnce(successfulAiResponse([{
      sourceChildId: 'source-1',
      portalChildId: 'portal-2',
      confidence: 0.94,
      reason: 'Alternative spelling variation',
    }]));

    const response = await dispatch({ type: 'REMATCH_DENIED' });

    expect(response.ok).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:3002/api/v1/ai/name-matches');
    const request = JSON.parse(String(fetchMock.mock.calls[0][1].body));
    expect(request.sourceChildren).toEqual([{ id: 'source-1', name: 'Jitu Regassa' }]);
    expect(request.excludedPairs).toEqual([{ sourceChildId: 'source-1', portalChildId: 'portal-1' }]);
    expect(response.state.mappings).toEqual({ 'source-2': 'portal-3' });
    expect(response.state.aiDeniedSuggestions).toHaveLength(1);
    expect(response.state.aiSuggestions).toEqual([
      expect.objectContaining({ sourceChildId: 'source-1', portalChildId: 'portal-2' }),
    ]);
  });

  it('clears a source denial history when the operator approves its alternative', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-2',
      portalChildName: 'Jitu Ragassa',
      pageGroupId: '42850',
      confidence: 0.94,
      reason: 'Alternative spelling variation',
    }];
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-1',
      portalChildName: 'Jitu Regasa',
      pageGroupId: '42850',
      confidence: 0.96,
      reason: 'Likely spelling variation',
      deniedAt: '2026-07-14T01:05:00.000Z',
    }];
    stored[STORAGE_KEY] = state;

    const response = await dispatch({
      type: 'SET_MAPPING',
      sourceId: 'source-1',
      portalId: 'portal-2',
    });

    expect(response.ok).toBe(true);
    expect(response.state.mappings).toEqual({ 'source-1': 'portal-2' });
    expect(response.state.aiSuggestions).toEqual([]);
    expect(response.state.aiDeniedSuggestions).toEqual([]);
    expect(response.state.aiMatch.acceptedCount).toBe(1);
  });

  it('cannot recreate a denied pair even if a backend response violates the exclusion', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-1',
      portalChildName: 'Jitu Regasa',
      pageGroupId: '42850',
      confidence: 0.96,
      reason: 'Likely spelling variation',
      deniedAt: '2026-07-14T01:05:00.000Z',
    }];
    stored[STORAGE_KEY] = state;
    fetchMock.mockResolvedValueOnce(successfulAiResponse([{
      sourceChildId: 'source-1',
      portalChildId: 'portal-1',
      confidence: 0.99,
      reason: 'Repeated forbidden pair',
    }]));

    const response = await dispatch({ type: 'REMATCH_DENIED' });

    expect(response.ok).toBe(true);
    expect(response.state.aiSuggestions).toEqual([]);
    expect(response.state.aiDeniedSuggestions).toHaveLength(1);
  });

  it('discards an in-flight recommendation response after the dataset changes', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    stored[STORAGE_KEY] = state;
    let releaseFetch: ((response: unknown) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => {
      releaseFetch = resolve;
    }));

    const matching = dispatch({ type: 'AI_MATCH' });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const replaced = await dispatch({
      type: 'SET_DATASET',
      dataset: { ...state.dataset, id: 'dataset-replaced-during-match' },
    });
    expect(replaced.ok).toBe(true);
    releaseFetch?.(successfulAiResponse([{
      sourceChildId: 'source-1',
      portalChildId: 'portal-2',
      confidence: 0.94,
      reason: 'Obsolete response',
    }]));

    const response = await matching;

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/changed while DeepSeek was matching/i);
    expect((stored[STORAGE_KEY] as Record<string, any>).dataset.id).toBe('dataset-replaced-during-match');
    expect((stored[STORAGE_KEY] as Record<string, any>).aiSuggestions ?? []).toEqual([]);
  });

  it('preserves approved mappings and denied pairs when DeepSeek truncates its response', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    state.dataset.children.push({ id: 'source-2', name: 'Already Approved Child' });
    state.portal.children.push({ id: 'portal-3', name: 'Already Approved Child' });
    state.mappings = { 'source-2': 'portal-3' };
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-1',
      portalChildName: 'Jitu Regasa',
      pageGroupId: '42850',
      confidence: 0.96,
      reason: 'Likely spelling variation',
      deniedAt: '2026-07-14T01:05:00.000Z',
    }];
    stored[STORAGE_KEY] = state;
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 502,
      json: async () => ({ detail: 'DeepSeek name-matching response was truncated' }),
    });

    const response = await dispatch({ type: 'REMATCH_DENIED' });

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/truncated/i);
    expect(stored[STORAGE_KEY]).toMatchObject({
      mappings: { 'source-2': 'portal-3' },
      aiDeniedSuggestions: [expect.objectContaining({ sourceChildId: 'source-1', portalChildId: 'portal-1' })],
      aiSuggestions: [],
      aiMatchRecovery: {
        requestMode: 'denied',
        error: expect.stringMatching(/truncated/i),
        attempt: 1,
      },
    });
  });

  it.each([408, 429, 500, 502, 599])(
    'persists transient HTTP %s failures for a durable retry',
    async (status) => {
      const state = aiReviewState();
      state.aiSuggestions = [];
      stored[STORAGE_KEY] = state;
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status,
        json: async () => ({ detail: `Transient DeepSeek failure ${status}` }),
      });

      const response = await dispatch({ type: 'AI_MATCH' });

      expect(response.ok).toBe(false);
      expect(response.error).toBe(`Transient DeepSeek failure ${status}`);
      expect((stored[STORAGE_KEY] as Record<string, any>).aiMatchRecovery).toMatchObject({
        requestMode: 'all',
        error: `Transient DeepSeek failure ${status}`,
        attempt: 1,
      });
    },
  );

  it.each([400, 401, 403, 404, 409, 422])(
    'does not offer retry for non-transient HTTP %s failures',
    async (status) => {
      const state = aiReviewState();
      state.aiSuggestions = [];
      state.aiMatchRecovery = {
        requestMode: 'all',
        error: 'Earlier transient failure',
        failedAt: '2026-07-14T01:10:00.000Z',
        attempt: 1,
      };
      stored[STORAGE_KEY] = state;
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status,
        json: async () => ({ detail: `Request cannot be retried ${status}` }),
      });

      const response = await dispatch({ type: 'AI_MATCH' });

      expect(response.ok).toBe(false);
      expect(response.error).toBe(`Request cannot be retried ${status}`);
      expect((stored[STORAGE_KEY] as Record<string, any>).aiMatchRecovery).toBeUndefined();
    },
  );

  it.each([
    {
      label: 'unreadable JSON',
      response: { ok: true, status: 200, json: async () => { throw new SyntaxError('invalid JSON'); } },
      message: /unreadable recommendation response/i,
    },
    {
      label: 'an invalid response shape',
      response: { ok: true, status: 200, json: async () => ({ threshold: 0.92, chunkCount: 1, matches: 'invalid' }) },
      message: /invalid recommendation response/i,
    },
  ])('persists $label from a successful response for retry', async ({ response: backendResponse, message }) => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    stored[STORAGE_KEY] = state;
    fetchMock.mockResolvedValueOnce(backendResponse);

    const response = await dispatch({ type: 'AI_MATCH' });

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(message);
    expect((stored[STORAGE_KEY] as Record<string, any>).aiMatchRecovery).toMatchObject({
      requestMode: 'all',
      error: expect.stringMatching(message),
      attempt: 1,
    });
  });

  it('aborts a hung whole request after five minutes and preserves a durable retry', async () => {
    vi.useFakeTimers();
    const state = aiReviewState();
    state.aiSuggestions = [];
    stored[STORAGE_KEY] = state;
    let requestSignal: AbortSignal | undefined;
    fetchMock.mockImplementationOnce((_url: string, options: RequestInit) => {
      requestSignal = options.signal as AbortSignal;
      return new Promise((_resolve, reject) => {
        requestSignal?.addEventListener(
          'abort',
          () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })),
          { once: true },
        );
      });
    });

    const pending = dispatch({ type: 'AI_MATCH' });
    for (let attempt = 0; attempt < 10 && fetchMock.mock.calls.length === 0; attempt += 1) {
      await Promise.resolve();
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(5 * 60_000);
    const response = await pending;

    expect(requestSignal?.aborted).toBe(true);
    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/timed out after 5 minutes/i);
    expect((stored[STORAGE_KEY] as Record<string, any>).aiMatchRecovery).toMatchObject({
      requestMode: 'all',
      error: expect.stringMatching(/timed out after 5 minutes/i),
      attempt: 1,
    });
  });

  it('keeps pre-request operator errors non-recoverable', async () => {
    const state = startableState() as Record<string, any>;
    state.aiMatchRecovery = {
      requestMode: 'all',
      error: 'Earlier transient failure',
      failedAt: '2026-07-14T01:10:00.000Z',
      attempt: 1,
    };
    stored[STORAGE_KEY] = state;

    const response = await dispatch({ type: 'AI_MATCH' });

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/already matched/i);
    expect((stored[STORAGE_KEY] as Record<string, any>).aiMatchRecovery).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('retries the preserved request mode and clears recovery only after a valid complete response', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-1',
      portalChildName: 'Jitu Regasa',
      pageGroupId: '42850',
      confidence: 0.96,
      reason: 'Likely spelling variation',
      deniedAt: '2026-07-14T01:05:00.000Z',
    }];
    state.aiMatchRecovery = {
      requestMode: 'denied',
      error: 'DeepSeek name-matching response was truncated',
      failedAt: '2026-07-14T01:10:00.000Z',
      attempt: 1,
    };
    stored[STORAGE_KEY] = state;
    fetchMock.mockResolvedValueOnce(successfulAiResponse([{
      sourceChildId: 'source-1',
      portalChildId: 'portal-2',
      confidence: 0.94,
      reason: 'Alternative spelling variation',
    }]));

    const response = await dispatch({ type: 'REMATCH_DENIED' });

    expect(response.ok).toBe(true);
    expect(response.state.aiMatchRecovery).toBeUndefined();
    expect(response.state.aiDeniedSuggestions).toHaveLength(1);
    expect(response.state.aiSuggestions).toEqual([
      expect.objectContaining({ sourceChildId: 'source-1', portalChildId: 'portal-2' }),
    ]);
  });

  it('coalesces duplicate concurrent DeepSeek requests into one backend call', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    stored[STORAGE_KEY] = state;
    let releaseFetch: ((response: unknown) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => {
      releaseFetch = resolve;
    }));

    const first = dispatch({ type: 'AI_MATCH' });
    const duplicate = dispatch({ type: 'AI_MATCH' });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    releaseFetch?.(successfulAiResponse([{
      sourceChildId: 'source-1',
      portalChildId: 'portal-2',
      confidence: 0.94,
      reason: 'Likely spelling variation',
    }]));

    const [firstResponse, duplicateResponse] = await Promise.all([first, duplicate]);

    expect(firstResponse.ok).toBe(true);
    expect(duplicateResponse.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(firstResponse.state.aiSuggestions).toEqual(duplicateResponse.state.aiSuggestions);
  });

  it('clears a denial when its remembered mapping becomes visible and is restored', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    state.portal.children = [{ id: 'portal-2', name: 'Jitu Ragassa' }];
    state.mappingMemory = {
      'source-1': {
        sourceId: 'source-1',
        sourceName: 'Jitu Regassa',
        portalId: 'portal-1',
        portalName: 'Jitu Regasa',
        pageGroupId: '42850',
        savedAt: '2026-07-13T00:00:00.000Z',
      },
    };
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-2',
      portalChildName: 'Jitu Ragassa',
      pageGroupId: '42850',
      confidence: 0.93,
      reason: 'Rejected temporary candidate',
      deniedAt: '2026-07-14T01:05:00.000Z',
    }];
    stored[STORAGE_KEY] = state;

    const response = await dispatch(
      {
        type: 'CONTENT_READY',
        portal: {
          ...state.portal,
          children: [
            { id: 'portal-1', name: 'Jitu Regasa' },
            { id: 'portal-2', name: 'Jitu Ragassa' },
          ],
        },
      },
      { tab: { id: 41, url: 'https://web.kinderlogix.com/content.php' } },
    );

    expect(response.ok).toBe(true);
    expect(response.state.mappings).toEqual({ 'source-1': 'portal-1' });
    expect(response.state.aiDeniedSuggestions).toEqual([]);
  });

  it('preserves denials across dataset clearing and removes them with name-decision clearing', async () => {
    const state = aiReviewState();
    state.aiSuggestions = [];
    state.aiDeniedSuggestions = [{
      sourceChildId: 'source-1',
      sourceChildName: 'Jitu Regassa',
      portalChildId: 'portal-1',
      portalChildName: 'Jitu Regasa',
      pageGroupId: '42850',
      confidence: 0.96,
      reason: 'Likely spelling variation',
      deniedAt: '2026-07-14T01:05:00.000Z',
    }];
    stored[STORAGE_KEY] = state;

    const replacedDataset = await dispatch({
      type: 'SET_DATASET',
      dataset: { ...state.dataset, id: 'dataset-next-month' },
    });
    expect(replacedDataset.ok).toBe(true);
    expect(replacedDataset.state.aiDeniedSuggestions).toHaveLength(1);

    const clearedDataset = await dispatch({ type: 'CLEAR_DATASET_CACHE' });
    expect(clearedDataset.ok).toBe(true);
    expect(clearedDataset.state.aiDeniedSuggestions).toHaveLength(1);

    const clearedDecisions = await dispatch({ type: 'CLEAR_MAPPING_CACHE' });
    expect(clearedDecisions.ok).toBe(true);
    expect(clearedDecisions.state.aiDeniedSuggestions).toEqual([]);
  });
});

describe('attendance run messaging handshake', () => {
  it('allows only one of two concurrent start requests to reserve the run', async () => {
    sendMessage.mockImplementation(async (_tabId: number, message: Record<string, unknown>) => (
      message.type === 'SCAN_PORTAL' ? portalScanResponse() : { ok: true }
    ));

    const request = {
      type: 'START_RUN',
      mappings: { 'source-1': 'portal-1' },
      includedSourceChildIds: ['source-1'],
      overwriteAcknowledged: true,
    };
    const responses = await Promise.all([dispatch(request), dispatch(request)]);

    expect(responses.filter((response) => response.ok)).toHaveLength(1);
    expect(responses.filter((response) => !response.ok)).toEqual([
      expect.objectContaining({ error: expect.stringMatching(/already active|checkpointed run/i) }),
    ]);
    expect(sendMessage.mock.calls.filter(([, message]) => message.type === 'CONTENT_RUN')).toHaveLength(1);
    expect(stored[STORAGE_KEY]).toMatchObject({ status: 'running' });
  });

  it('starts only after the live portal scan and content engine acknowledge the request', async () => {
    sendMessage
      .mockResolvedValueOnce(portalScanResponse())
      .mockResolvedValueOnce({ ok: true });

    const response = await dispatch({
      type: 'START_RUN',
      mappings: { 'source-1': 'portal-1' },
      includedSourceChildIds: ['source-1'],
      overwriteAcknowledged: true,
    });

    expect(response.ok).toBe(true);
    expect(sendMessage).toHaveBeenNthCalledWith(1, 41, { type: 'SCAN_PORTAL' });
    expect(sendMessage).toHaveBeenNthCalledWith(2, 41, { type: 'CONTENT_RUN' });
    expect(response.state).toMatchObject({
      status: 'running',
      runMappings: { 'source-1': 'portal-1' },
      includedSourceChildIds: ['source-1'],
      checkpoint: {
        engineVersion: 6,
        stage: 'daily',
        dayStage: 'cleanup',
        dateIndex: 0,
        cleanupIndex: 0,
        recordIndex: 0,
        phase: 'select_date',
      },
    });
  });

  it('does not leave a silent running state when the content engine cannot attach', async () => {
    sendMessage
      .mockResolvedValueOnce(portalScanResponse())
      .mockRejectedValueOnce(new Error('Receiving end does not exist'))
      .mockRejectedValueOnce(new Error('Receiving end still does not exist'));

    const response = await dispatch({
      type: 'START_RUN',
      mappings: { 'source-1': 'portal-1' },
      includedSourceChildIds: ['source-1'],
      overwriteAcknowledged: true,
    });

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/could not attach/i);
    expect(executeScript).toHaveBeenCalledWith({ target: { tabId: 41 }, files: ['content.js'] });
    expect(stored[STORAGE_KEY]).toMatchObject({
      status: 'error',
      error: expect.stringMatching(/could not attach/i),
    });
    expect((stored[STORAGE_KEY] as Record<string, any>).logs.at(-1)).toMatchObject({
      level: 'error',
      message: 'Attendance run could not start on the connected tab',
    });
  });

  it('preserves the checkpoint and reports an error when resume cannot reach the tab', async () => {
    stored[STORAGE_KEY] = {
      ...startableState(),
      status: 'paused',
      checkpoint: {
        stage: 'daily',
        dayStage: 'entry',
        dateIndex: 4,
        cleanupIndex: 0,
        recordIndex: 7,
        sessionIndex: 1,
        phase: 'save_end',
        attempt: 2,
      },
    };
    sendMessage
      .mockRejectedValueOnce(new Error('tab closed'))
      .mockRejectedValueOnce(new Error('tab still closed'));

    const response = await dispatch({ type: 'RESUME_RUN' });

    expect(response.ok).toBe(false);
    expect(stored[STORAGE_KEY]).toMatchObject({
      status: 'error',
      checkpoint: {
        stage: 'daily',
        dayStage: 'entry',
        dateIndex: 4,
        recordIndex: 7,
        sessionIndex: 1,
        phase: 'save_end',
        attempt: 0,
      },
    });
  });

  it('merges a content progress patch without losing its durable checkpoint', async () => {
    stored[STORAGE_KEY] = {
      ...startableState(),
      status: 'running',
      checkpoint: {
        stage: 'daily',
        dayStage: 'cleanup',
        dateIndex: 2,
        cleanupIndex: 5,
        recordIndex: 0,
        sessionIndex: 0,
        phase: 'cleanup_existing',
        attempt: 1,
      },
      progress: { cleanupRecordsCompleted: 12, recordsCompleted: 0 },
    };

    const response = await dispatch(
      { type: 'ENGINE_PATCH', patch: { progress: { cleanupRecordsCompleted: 13 } } },
      { tab: { id: 41 } },
    );

    expect(response.ok).toBe(true);
    expect(response.state).toMatchObject({
      checkpoint: {
        stage: 'daily',
        dayStage: 'cleanup',
        dateIndex: 2,
        cleanupIndex: 5,
        phase: 'cleanup_existing',
        attempt: 1,
      },
      progress: { cleanupRecordsCompleted: 13, recordsCompleted: 0 },
    });
  });

  it('rejects checkpoint patches from a different tab', async () => {
    stored[STORAGE_KEY] = { ...startableState(), status: 'running' };

    const response = await dispatch(
      { type: 'ENGINE_PATCH', patch: { status: 'completed' } },
      { tab: { id: 99 } },
    );

    expect(response.ok).toBe(false);
    expect(response.error).toMatch(/different browser tab/i);
    expect(stored[STORAGE_KEY]).toMatchObject({ status: 'running' });
  });

  it('allows duplicate source children to map to one portal child for date-wise consolidation', async () => {
    const state = startableState();
    state.dataset.children.push({ id: 'source-2', name: 'Jitu Regassa duplicate' });
    state.dataset.records.push({
      date: '2026-07-13',
      sourceChildId: 'source-2',
      sourceChildName: 'Jitu Regassa duplicate',
      sessions: [{ start: '16:30', end: '17:00' }],
    });
    Object.assign(state.mappings, { 'source-2': 'portal-1' });
    stored[STORAGE_KEY] = state;
    sendMessage
      .mockResolvedValueOnce(portalScanResponse())
      .mockResolvedValueOnce({ ok: true });

    const response = await dispatch({
      type: 'START_RUN',
      mappings: { 'source-1': 'portal-1', 'source-2': 'portal-1' },
      includedSourceChildIds: ['source-1', 'source-2'],
      overwriteAcknowledged: true,
    });

    expect(response.ok).toBe(true);
    expect(sendMessage).toHaveBeenCalledTimes(2);
    expect(sendMessage).toHaveBeenNthCalledWith(1, 41, { type: 'SCAN_PORTAL' });
    expect(sendMessage).toHaveBeenNthCalledWith(2, 41, { type: 'CONTENT_RUN' });
    expect(stored[STORAGE_KEY]).toMatchObject({
      status: 'running',
      runMappings: { 'source-1': 'portal-1', 'source-2': 'portal-1' },
    });
  });
});
