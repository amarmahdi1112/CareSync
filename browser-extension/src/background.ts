/*
 * CareSync Attendance - MV3 service worker
 *
 * The service worker is the single writer for durable run state.  Keeping all
 * checkpoints here prevents a portal AJAX refresh (or a full page reload after
 * delete) from making the content script restart from the beginning.
 */

import {
  activeDeniedSuggestions,
  clearDeniedSources,
  rememberDeniedSuggestion,
  rememberMappings,
  restoreRememberedMappings,
  sanitizeActiveMappings,
} from "./shared/matching";
import type { AiNameSuggestion, ChildMappingMemory } from "./shared/types";

const STORAGE_KEY = "caresyncAttendanceState";
const CONTENT_SCRIPT_FILE = "content.js";
const NAME_MATCH_URL = "http://127.0.0.1:3002/api/v1/ai/name-matches";
const AI_NAME_MATCH_TIMEOUT_MS = 5 * 60_000;

type JsonObject = Record<string, any>;

interface Connection {
  tabId: number;
  origin: string;
  url: string;
  scriptId: string;
  connectedAt: string;
  lastSeenAt?: string;
}

interface DurableState extends JsonObject {
  version: 1;
  status: string;
  connection?: Connection;
  logs: Array<JsonObject>;
}

const DEFAULT_STATE: DurableState = {
  version: 1,
  status: "idle",
  dataset: null,
  portal: null,
  logs: [],
  mappings: {},
  mappingMemory: {},
  aiDeniedSuggestions: [],
  settings: {
    overwriteExisting: false,
    timeoutMs: 20_000,
    retryLimit: 2,
  },
  run: {
    status: "idle",
    checkpoint: { dateIndex: 0, childIndex: 0, sessionIndex: 0, phase: "idle" },
    progress: {
      completedDates: 0,
      totalDates: 0,
      completedRecords: 0,
      totalRecords: 0,
      completedSessions: 0,
      totalSessions: 0,
    },
    updatedAt: new Date(0).toISOString(),
    overwriteConfirmed: false,
  },
};

let stateWrite: Promise<DurableState> = Promise.resolve(DEFAULT_STATE);

type AiMatchRequestMode = "all" | "denied";

class RecoverableAiMatchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RecoverableAiMatchError";
  }
}

let aiMatchInFlight: {
  mode: AiMatchRequestMode;
  promise: Promise<DurableState>;
} | null = null;

function now(): string {
  return new Date().toISOString();
}

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function storageSafe<T>(value: T): T {
  if (Array.isArray(value)) return value.map((item) => storageSafe(item)) as T;
  if (!isObject(value)) return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, item]) => item !== undefined)
      .map(([key, item]) => [key, storageSafe(item)]),
  ) as T;
}

function mergeState(current: DurableState, patch: JsonObject): DurableState {
  const next: DurableState = { ...current, ...patch } as DurableState;
  if (isObject(current.checkpoint) && isObject(patch.checkpoint)) {
    next.checkpoint = { ...current.checkpoint, ...patch.checkpoint };
  }
  if (isObject(current.progress) && isObject(patch.progress)) {
    next.progress = { ...current.progress, ...patch.progress };
  }
  if (isObject(current.settings) && isObject(patch.settings)) {
    next.settings = { ...current.settings, ...patch.settings };
  }
  if (isObject(current.connection) && isObject(patch.connection)) {
    next.connection = { ...current.connection, ...patch.connection };
  }
  if (isObject(current.portal) && isObject(patch.portal)) {
    next.portal = { ...current.portal, ...patch.portal };
  }
  if (Array.isArray(patch.logs)) {
    next.logs = patch.logs.slice(-300);
  } else {
    next.logs = Array.isArray(current.logs) ? current.logs.slice(-300) : [];
  }
  const checkpoint = next.checkpoint || next.run?.checkpoint;
  const progress = next.progress || next.run?.progress;
  const sharedPhase: Record<string, string> = {
    select_date: "navigating_date",
    delete_existing: "deleting_existing",
    save_start: "entering_start",
    save_end: "entering_end",
    record_complete: "advancing_child",
  };
  if (checkpoint) {
    next.checkpoint = {
      ...checkpoint,
      recordIndex: Number(checkpoint.recordIndex ?? checkpoint.childIndex ?? 0),
      childIndex: Number(checkpoint.childIndex ?? checkpoint.recordIndex ?? 0),
    };
  }
  if (progress) {
    next.progress = {
      ...progress,
      datesCompleted: Number(progress.datesCompleted ?? progress.completedDates ?? 0),
      completedDates: Number(progress.completedDates ?? progress.datesCompleted ?? 0),
      recordsCompleted: Number(progress.recordsCompleted ?? progress.completedRecords ?? 0),
      completedRecords: Number(progress.completedRecords ?? progress.recordsCompleted ?? 0),
      sessionsCompleted: Number(progress.sessionsCompleted ?? progress.completedSessions ?? 0),
      completedSessions: Number(progress.completedSessions ?? progress.sessionsCompleted ?? 0),
    };
  }
  const run = { ...(next.run || {}) };
  run.status = next.status === "connected" ? (next.dataset ? "ready" : "idle") : next.status || run.status || "idle";
  if (next.checkpoint) {
    run.checkpoint = {
      ...next.checkpoint,
      phase: sharedPhase[next.checkpoint.phase] || next.checkpoint.phase || "idle",
    };
  }
  if (next.progress) run.progress = { ...next.progress };
  run.currentAction = next.current?.action ?? run.currentAction;
  run.error = typeof next.error === "string" ? next.error : next.error?.message;
  run.startedAt = next.startedAt ?? run.startedAt;
  run.updatedAt = now();
  run.overwriteConfirmed = Boolean(next.overwriteConfirmed ?? run.overwriteConfirmed);
  next.run = run;
  return next;
}

async function readState(): Promise<DurableState> {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  return mergeState(DEFAULT_STATE, (stored[STORAGE_KEY] as JsonObject) || {});
}

function updateStateFromCurrent(
  createPatch: (current: DurableState) => JsonObject | null | Promise<JsonObject | null>,
): Promise<DurableState> {
  // Serialize read/modify/write operations. Popup actions and content-script
  // checkpoints may arrive at nearly the same time.
  stateWrite = stateWrite
    .catch(() => DEFAULT_STATE)
    .then(async () => {
      const current = await readState();
      const patch = await createPatch(current);
      if (patch === null) return current;
      const next = storageSafe(mergeState(current, patch));
      await chrome.storage.local.set({ [STORAGE_KEY]: next });
      return next;
    });
  return stateWrite;
}

function updateState(patch: JsonObject): Promise<DurableState> {
  return updateStateFromCurrent(() => patch);
}

async function appendLog(level: string, message: string, details?: unknown): Promise<DurableState> {
  stateWrite = stateWrite
    .catch(() => DEFAULT_STATE)
    .then(async () => {
      const current = await readState();
      const next = storageSafe(mergeState(current, {
        logs: [
          ...(Array.isArray(current.logs) ? current.logs : []),
          {
            id: crypto.randomUUID(),
            at: now(),
            level: level === "warn" ? "warning" : level,
            message,
            ...(details === undefined ? {} : { details }),
          },
        ].slice(-300),
      }));
      await chrome.storage.local.set({ [STORAGE_KEY]: next });
      return next;
    });
  return stateWrite;
}

function scriptIdForOrigin(origin: string): string {
  let hash = 2166136261;
  for (let index = 0; index < origin.length; index += 1) {
    hash ^= origin.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `caresync-attendance-${(hash >>> 0).toString(16)}`;
}

function originPattern(url: URL): string {
  return `${url.protocol}//${url.host}/*`;
}

function isKinderLogixTab(tab: chrome.tabs.Tab | undefined, expectedOrigin?: string): tab is chrome.tabs.Tab {
  if (!tab?.id || !tab.url) return false;
  try {
    const url = new URL(tab.url);
    return (
      url.protocol === "https:" &&
      url.hostname === "web.kinderlogix.com" &&
      (!expectedOrigin || url.origin === expectedOrigin)
    );
  } catch {
    return false;
  }
}

async function liveConnectedTab(connection: Connection | undefined): Promise<chrome.tabs.Tab | null> {
  if (!connection?.tabId) return null;
  try {
    const tab = await chrome.tabs.get(connection.tabId);
    return isKinderLogixTab(tab, connection.origin) ? tab : null;
  } catch {
    return null;
  }
}

function staleConnectionPatch(current: DurableState): JsonObject {
  const recoverableCheckpoint = Boolean(current.checkpoint) &&
    (current.status === "running" || current.status === "paused" || current.status === "error");
  const status = recoverableCheckpoint
    ? "paused"
    : current.status === "completed" || current.status === "stopped"
      ? current.status
      : "idle";
  const error = recoverableCheckpoint
    ? "The saved attendance tab closed. Open the intended KinderLogix room, connect this tab, then resume the preserved checkpoint."
    : undefined;
  return {
    status,
    connection: undefined,
    portal: null,
    mappings: {},
    aiMatch: undefined,
    aiSuggestions: undefined,
    aiMatchRecovery: undefined,
    overwriteConfirmed: false,
    error,
  };
}

async function clearStaleConnection(expectedTabId?: number): Promise<DurableState> {
  return updateStateFromCurrent((current) => {
    if (current.connection?.tabId !== expectedTabId) return null;
    return staleConnectionPatch(current);
  });
}

async function attendanceTab(preferredTabId?: number): Promise<chrome.tabs.Tab> {
  if (preferredTabId) {
    try {
      const preferred = await chrome.tabs.get(preferredTabId);
      if (isKinderLogixTab(preferred)) return preferred;
    } catch {
      // A browser restart invalidates saved tab IDs. Fall through to discovery.
    }
  }
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  const candidates = await chrome.tabs.query({ url: ["https://web.kinderlogix.com/*"] });
  const activeCandidate = candidates.find((candidate) => candidate.id === active?.id);
  if (activeCandidate?.id && activeCandidate.url) return activeCandidate;
  if (candidates.length === 1 && candidates[0].id && candidates[0].url) return candidates[0];
  throw new Error(
    candidates.length > 1
      ? "More than one KinderLogix tab is open. Make the intended attendance tab active, then connect again."
      : "No KinderLogix attendance tab is open in this browser. Open https://web.kinderlogix.com/content.php first.",
  );
}

async function ensureRegistered(originUrl: URL): Promise<string> {
  const id = scriptIdForOrigin(originUrl.origin);
  const existing = await chrome.scripting.getRegisteredContentScripts({ ids: [id] });
  if (existing.length) await chrome.scripting.unregisterContentScripts({ ids: [id] });
  await chrome.scripting.registerContentScripts([
    {
      id,
      matches: [originPattern(originUrl)],
      js: [CONTENT_SCRIPT_FILE],
      runAt: "document_idle",
      persistAcrossSessions: true,
    },
  ]);
  return id;
}

async function requestPortalScan(tabId: number): Promise<JsonObject> {
  let tab: chrome.tabs.Tab;
  try {
    tab = await chrome.tabs.get(tabId);
  } catch {
    throw new Error("The saved attendance tab is closed. Connect the currently open KinderLogix tab and scan again.");
  }
  if (!isKinderLogixTab(tab)) {
    throw new Error("The connected tab is no longer showing KinderLogix. Open the intended attendance room and reconnect.");
  }
  try {
    return (await chrome.tabs.sendMessage(tabId, { type: "SCAN_PORTAL" })) as JsonObject;
  } catch (firstError) {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: [CONTENT_SCRIPT_FILE] });
      return (await chrome.tabs.sendMessage(tabId, { type: "SCAN_PORTAL" })) as JsonObject;
    } catch (injectionError) {
      throw new Error(
        `The attendance detector could not attach to this tab. Reload the extension and portal page, then reconnect. ${
          injectionError instanceof Error ? injectionError.message : String(injectionError || firstError)
        }`,
      );
    }
  }
}

async function connectCurrentTab(preferredTabId?: number): Promise<JsonObject> {
  const tab = await attendanceTab(preferredTabId);
  const existingState = await readState();
  const checkpointedRun = existingState.status === "running" || existingState.status === "paused";
  let replacingDeadRunTab = false;
  if (
    checkpointedRun &&
    existingState.connection?.tabId &&
    existingState.connection.tabId !== tab.id
  ) {
    const previousTab = await liveConnectedTab(existingState.connection);
    if (previousTab) {
      throw new Error("Pause or stop the saved attendance run before connecting a different tab.");
    }
    replacingDeadRunTab = true;
  }
  const url = new URL(tab.url!);
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new Error("The active tab is not an HTTP(S) attendance page.");
  }

  const scriptId = await ensureRegistered(url);
  const connection: Connection = {
    tabId: tab.id!,
    origin: url.origin,
    url: tab.url!,
    scriptId,
    connectedAt: now(),
  };
  const connectionChanged = existingState.connection?.tabId !== tab.id;
  const state = await updateState({
    status:
      replacingDeadRunTab
        ? "paused"
        : checkpointedRun
        ? existingState.status
        : "connected",
    connection,
    error: replacingDeadRunTab
      ? "The previous attendance tab closed. The checkpoint is preserved; review this room, then resume."
      : undefined,
    ...(connectionChanged
      ? {
          portal: null,
          mappings: {},
          aiMatch: undefined,
          aiSuggestions: undefined,
          aiMatchRecovery: undefined,
          overwriteConfirmed: false,
        }
      : {}),
  });

  let portal: unknown;
  try {
    portal = await requestPortalScan(tab.id!);
  } catch (error) {
    await appendLog("warning", "Attendance detector did not attach during Connect", String(error));
  }
  const portalValue = (portal as JsonObject)?.portal ?? portal;
  const decoratedPortal = portalValue
    ? { ...(portalValue as JsonObject), connected: true, tabId: tab.id!, origin: url.origin }
    : portalValue;
  const validPortal = decoratedPortal?.isPortal && childCandidates(decoratedPortal.children).length
    ? decoratedPortal
    : undefined;
  const next = validPortal
    ? await updateStateFromCurrent((current) => {
        const runActive = current.status === "running" || current.status === "paused";
        const mappingMemory = memoryWithMappings(current);
        const mappings = current.dataset && !runActive
          ? mappingsFromMemory(mappingMemory, current.dataset, validPortal)
          : current.mappings;
        const aiDeniedSuggestions = denialsAfterRestoredMappings(current, mappings, validPortal);
        const portalChanged = portalRosterSignature(current.portal) !== portalRosterSignature(validPortal);
        const aiPatch = portalChanged
          ? { aiMatch: undefined, aiSuggestions: undefined, aiMatchRecovery: undefined }
          : reconciledAiPatch({ ...current, aiDeniedSuggestions }, mappings, validPortal);
        return { portal: validPortal, mappings, mappingMemory, aiDeniedSuggestions, ...aiPatch };
      })
    : await readState();
  return { ok: true, state: next, portal: validPortal };
}

function senderTabId(sender: chrome.runtime.MessageSender): number | undefined {
  return sender.tab?.id;
}

function assertSenderScope(state: DurableState, sender: chrome.runtime.MessageSender): void {
  const tabId = senderTabId(sender);
  if (tabId !== undefined && state.connection?.tabId !== undefined && state.connection.tabId !== tabId) {
    throw new Error("This run belongs to a different browser tab.");
  }
}

function assertRunNotActive(state: DurableState, action: string): void {
  if (state.status === "running" || state.status === "paused") {
    throw new Error(`${action} is locked while a checkpointed run is active. Stop the run first.`);
  }
}

function readyStatus(state: DurableState, hasDataset = Boolean(state.dataset)): string {
  if (!state.connection) return "idle";
  return hasDataset ? "ready" : "connected";
}

function clearedRunPatch(state: DurableState, hasDataset = Boolean(state.dataset)): JsonObject {
  return {
    status: readyStatus(state, hasDataset),
    run: {},
    runId: undefined,
    runMappings: undefined,
    runDatasetId: undefined,
    runPageGroupId: undefined,
    includedSourceChildIds: undefined,
    startedAt: undefined,
    completedAt: undefined,
    pausedAt: undefined,
    resumedAt: undefined,
    stoppedAt: undefined,
    current: undefined,
    error: undefined,
    overwriteConfirmed: false,
    checkpoint: {
      dateIndex: 0,
      recordIndex: 0,
      childIndex: 0,
      sessionIndex: 0,
      phase: "select_date",
      attempt: 0,
    },
    progress: {
      cleanupDatesCompleted: 0,
      cleanupRecordsCompleted: 0,
      cleanupFailures: 0,
      datesCompleted: 0,
      completedDates: 0,
      recordsCompleted: 0,
      completedRecords: 0,
      sessionsCompleted: 0,
      completedSessions: 0,
      skippedRecords: 0,
      failedRecords: 0,
    },
    settings: { overwriteExisting: false },
  };
}

async function sendToConnectedTab(message: JsonObject, requireAcknowledgement = false): Promise<JsonObject | undefined> {
  const state = await readState();
  const connection = state.connection;
  if (!connection?.tabId) {
    if (requireAcknowledgement) throw new Error("The attendance tab is no longer connected. Connect it again, then retry.");
    return undefined;
  }
  const liveTab = await liveConnectedTab(connection);
  if (!liveTab?.id) {
    await clearStaleConnection(connection.tabId);
    if (requireAcknowledgement) {
      throw new Error("The attendance tab closed. Connect the intended KinderLogix room, then retry from the preserved checkpoint.");
    }
    return undefined;
  }
  const tabId = liveTab.id;
  try {
    const response = (await chrome.tabs.sendMessage(tabId, message)) as JsonObject | undefined;
    if (requireAcknowledgement && response?.ok !== true) {
      throw new Error(String(response?.error || "The attendance page did not acknowledge the run."));
    }
    return response;
  } catch (firstError) {
    if (!requireAcknowledgement) return undefined;
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: [CONTENT_SCRIPT_FILE] });
      const response = (await chrome.tabs.sendMessage(tabId, message)) as JsonObject | undefined;
      if (response?.ok !== true) throw new Error(String(response?.error || "The attendance page did not acknowledge the run."));
      return response;
    } catch (retryError) {
      throw new Error(
        `The attendance engine could not attach to the connected tab. Reload the KinderLogix page, reconnect, and retry. ${
          retryError instanceof Error ? retryError.message : String(retryError || firstError)
        }`,
      );
    }
  }
}

function childCandidates(value: unknown): Array<{ id: string; name: string }> {
  if (!Array.isArray(value)) return [];
  return value
    .map((candidate) => ({
      id: String(candidate?.id ?? candidate?.sourceChildId ?? "").trim(),
      name: String(candidate?.name ?? candidate?.sourceChildName ?? "").trim(),
    }))
    .filter((candidate) => candidate.id && candidate.name);
}

function memoryWithMappings(
  current: DurableState,
  mappings: Record<string, string> = current.mappings || {},
): Record<string, ChildMappingMemory> {
  return rememberMappings(
    current.mappingMemory || {},
    mappings,
    childCandidates(current.dataset?.children),
    childCandidates(current.portal?.children),
    String(current.portal?.pageGroupId || ""),
    now(),
  );
}

function mappingsFromMemory(
  memory: Record<string, ChildMappingMemory>,
  dataset: JsonObject | null | undefined,
  portal: JsonObject | null | undefined,
): Record<string, string> {
  return restoreRememberedMappings(
    memory,
    childCandidates(dataset?.children),
    childCandidates(portal?.children),
    String(portal?.pageGroupId || ""),
  );
}

function sanitizedMappings(
  current: DurableState,
  mappings: Record<string, string>,
): Record<string, string> {
  return sanitizeActiveMappings(
    mappings,
    childCandidates(current.dataset?.children),
    childCandidates(current.portal?.children),
  );
}

function denialsAfterRestoredMappings(
  current: DurableState,
  mappings: Record<string, string>,
  portal: JsonObject | null | undefined = current.portal,
) {
  return clearDeniedSources(
    current.aiDeniedSuggestions,
    Object.keys(mappings),
    String(portal?.pageGroupId || ""),
  );
}

function portalRosterSignature(portal: JsonObject | null | undefined): string {
  const children = childCandidates(portal?.children)
    .map((child) => `${child.id}:${child.name}`)
    .sort();
  return `${String(portal?.pageGroupId || "")}|${children.join("|")}`;
}

function childMappingSignature(mappings: Record<string, string> | null | undefined): string {
  return Object.entries(mappings || {})
    .map(([sourceId, portalId]) => `${sourceId}:${portalId}`)
    .sort()
    .join("|");
}

function aiPairKey(sourceId: string, portalId: string): string {
  return `${sourceId}\u0000${portalId}`;
}

function reconciledAiPatch(
  current: DurableState,
  mappings: Record<string, string> = current.mappings || {},
  portal: JsonObject | null | undefined = current.portal,
  rawSuggestions: unknown = current.aiSuggestions,
): JsonObject {
  const sourceChildren = childCandidates(current.dataset?.children);
  const portalChildren = childCandidates(portal?.children);
  const sourceIds = new Set(sourceChildren.map((child) => child.id));
  const portalIds = new Set(portalChildren.map((child) => child.id));
  const mappedPortalIds = new Set(Object.values(mappings).map(String).filter((id) => portalIds.has(id)));
  const deniedPairs = new Set(
    activeDeniedSuggestions(
      current.aiDeniedSuggestions,
      sourceChildren,
      portalChildren,
      String(portal?.pageGroupId || ""),
    ).map((denied) => aiPairKey(denied.sourceChildId, denied.portalChildId)),
  );
  const seenSources = new Set<string>();
  const seenPortals = new Set<string>();
  const aiSuggestions = (Array.isArray(rawSuggestions) ? rawSuggestions : []).filter((raw: JsonObject) => {
    const sourceId = String(raw?.sourceChildId || "");
    const portalId = String(raw?.portalChildId || "");
    const confidence = Number(raw?.confidence);
    if (
      !sourceIds.has(sourceId) ||
      !portalIds.has(portalId) ||
      mappings[sourceId] ||
      mappedPortalIds.has(portalId) ||
      seenSources.has(sourceId) ||
      seenPortals.has(portalId) ||
      deniedPairs.has(aiPairKey(sourceId, portalId)) ||
      !Number.isFinite(confidence) ||
      confidence < 0 ||
      confidence > 1
    ) return false;
    seenSources.add(sourceId);
    seenPortals.add(portalId);
    return true;
  });
  const remainingCount = sourceChildren.filter(
    (child) => !portalIds.has(String(mappings[child.id] || "")),
  ).length;
  return {
    aiSuggestions,
    aiMatch: isObject(current.aiMatch)
      ? { ...current.aiMatch, suggestionCount: aiSuggestions.length, remainingCount }
      : undefined,
  };
}

async function runAiNameMatch(current: DurableState, deniedOnly = false): Promise<DurableState> {
  assertRunNotActive(current, "AI name matching");
  if (!current.dataset) throw new Error("Import a CareSync attendance ZIP first.");
  if (!current.portal) throw new Error("Scan the KinderLogix room first.");

  const currentAiPatch = reconciledAiPatch(current);
  if (Array.isArray(currentAiPatch.aiSuggestions) && currentAiPatch.aiSuggestions.length > 0) {
    throw new Error("Approve or deny the current AI recommendations before requesting another match.");
  }

  const sourceChildren = childCandidates(current.dataset.children);
  const portalChildren = childCandidates(current.portal.children);
  const portalIds = new Set(portalChildren.map((child) => child.id));
  const usedPortalIds = new Set(
    Object.values(current.mappings || {})
      .map(String)
      .filter((id) => portalIds.has(id)),
  );
  const allUnresolvedSources = sourceChildren.filter(
    (child) => !portalIds.has(String(current.mappings?.[child.id] ?? "")),
  );
  const activeDenials = activeDeniedSuggestions(
    current.aiDeniedSuggestions,
    sourceChildren,
    portalChildren,
    String(current.portal?.pageGroupId || ""),
  );
  const deniedSourceIds = new Set(activeDenials.map((denied) => denied.sourceChildId));
  const unresolvedSources = deniedOnly
    ? allUnresolvedSources.filter((child) => deniedSourceIds.has(child.id))
    : allUnresolvedSources;
  const availablePortals = portalChildren.filter((child) => !usedPortalIds.has(child.id));
  if (!allUnresolvedSources.length) throw new Error("Every imported child is already matched.");
  if (!unresolvedSources.length && deniedOnly) {
    throw new Error("There are no unresolved denied children to rematch in this room.");
  }
  if (!availablePortals.length) throw new Error("No unmatched children remain in this portal room.");

  const candidateSourceIds = new Set(unresolvedSources.map((child) => child.id));
  const candidatePortalIds = new Set(availablePortals.map((child) => child.id));
  const excludedPairs = activeDenials
    .filter(
      (denied) => candidateSourceIds.has(denied.sourceChildId) && candidatePortalIds.has(denied.portalChildId),
    )
    .map((denied) => ({
      sourceChildId: denied.sourceChildId,
      portalChildId: denied.portalChildId,
    }));
  const excludedPairKeys = new Set(
    excludedPairs.map((denied) => aiPairKey(denied.sourceChildId, denied.portalChildId)),
  );

  const controller = new AbortController();
  const timeoutError = new RecoverableAiMatchError(
    "DeepSeek name matching timed out after 5 minutes. No names were changed; retry is available.",
  );
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      controller.abort();
      reject(timeoutError);
    }, AI_NAME_MATCH_TIMEOUT_MS);
  });
  const request = (async (): Promise<JsonObject> => {
    let response: Response;
    try {
      response = await fetch(NAME_MATCH_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceChildren: unresolvedSources, portalChildren: availablePortals, excludedPairs }),
        signal: controller.signal,
      });
    } catch {
      if (controller.signal.aborted) throw timeoutError;
      throw new RecoverableAiMatchError(
        "CareSync Basic is not reachable. Start it on 127.0.0.1:3002, then try AI matching again.",
      );
    }

    let payload: JsonObject = {};
    let bodyWasReadable = true;
    try {
      payload = (await response.json()) as JsonObject;
    } catch {
      bodyWasReadable = false;
    }
    if (!response.ok) {
      const detail = String(payload.detail || `DeepSeek name matching failed (${response.status}).`);
      if (response.status === 408 || response.status === 429 || response.status >= 500) {
        throw new RecoverableAiMatchError(detail);
      }
      throw new Error(detail);
    }
    if (!bodyWasReadable || !isObject(payload)) {
      throw new RecoverableAiMatchError(
        "DeepSeek returned an unreadable recommendation response. No names were changed.",
      );
    }
    return payload;
  })();
  let payload: JsonObject;
  try {
    payload = await Promise.race([request, timeout]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
  const responseThreshold = Number(payload.threshold);
  const responseChunkCount = Number(payload.chunkCount ?? 1);
  if (
    !Array.isArray(payload.matches) ||
    !Number.isFinite(responseThreshold) ||
    responseThreshold < 0 ||
    responseThreshold > 1 ||
    !Number.isInteger(responseChunkCount) ||
    responseChunkCount < 1
  ) {
    throw new RecoverableAiMatchError("DeepSeek returned an invalid recommendation response. No names were changed.");
  }

  const sourceIds = new Set(unresolvedSources.map((child) => child.id));
  const availablePortalIds = new Set(availablePortals.map((child) => child.id));
  const seenSources = new Set<string>();
  const seenPortals = new Set<string>();
  const suggestions: JsonObject[] = [];
  const threshold = responseThreshold;
  let returnedNonExcludedPair = false;
  for (const raw of Array.isArray(payload.matches) ? payload.matches : []) {
    const match = raw as JsonObject;
    const sourceId = String(match.sourceChildId || "");
    const portalId = String(match.portalChildId || "");
    const confidence = Number(match.confidence);
    if (excludedPairKeys.has(aiPairKey(sourceId, portalId))) continue;
    returnedNonExcludedPair = true;
    if (
      !Number.isFinite(confidence) ||
      confidence < 0 ||
      confidence > 1 ||
      !sourceIds.has(sourceId) ||
      !availablePortalIds.has(portalId) ||
      seenSources.has(sourceId) ||
      seenPortals.has(portalId) ||
      usedPortalIds.has(portalId)
    ) {
      continue;
    }
    seenSources.add(sourceId);
    seenPortals.add(portalId);
    suggestions.push({
      sourceChildId: sourceId,
      portalChildId: portalId,
      sourceChildName: unresolvedSources.find((child) => child.id === sourceId)?.name || "",
      portalChildName: availablePortals.find((child) => child.id === portalId)?.name || "",
      pageGroupId: String(current.portal?.pageGroupId || ""),
      confidence,
      reason: String(match.reason || "Possible name variation").slice(0, 300),
    });
  }
  if (payload.matches.length > 0 && suggestions.length === 0 && returnedNonExcludedPair) {
    throw new RecoverableAiMatchError(
      "DeepSeek recommendations did not match the current ZIP and portal room. Scan the room again and retry.",
    );
  }
  let savedSuggestionCount = 0;
  let savedRemainingCount = allUnresolvedSources.length;
  await updateStateFromCurrent((latest) => {
    assertRunNotActive(latest, "Saving AI name recommendations");
    if (
      String(latest.dataset?.id || "") !== String(current.dataset?.id || "") ||
      portalRosterSignature(latest.portal) !== portalRosterSignature(current.portal)
    ) {
      throw new Error("The imported ZIP or visible portal room changed while DeepSeek was matching. Generate recommendations again.");
    }
    const newerPending = reconciledAiPatch(latest).aiSuggestions;
    if (Array.isArray(newerPending) && newerPending.length > 0) {
      throw new Error("A newer AI recommendation set is already waiting for review.");
    }
    const aiPatch = reconciledAiPatch(
      {
        ...latest,
        aiMatch: {
          model: String(payload.model || "DeepSeek"),
          threshold,
          acceptedCount: 0,
          suggestionCount: suggestions.length,
          chunkCount: responseChunkCount,
          remainingCount: allUnresolvedSources.length,
          matchedAt: now(),
          requestMode: deniedOnly ? "denied" : "all",
        },
      },
      latest.mappings || {},
      latest.portal,
      suggestions,
    );
    savedSuggestionCount = Array.isArray(aiPatch.aiSuggestions) ? aiPatch.aiSuggestions.length : 0;
    savedRemainingCount = Number(aiPatch.aiMatch?.remainingCount ?? allUnresolvedSources.length);
    return { ...aiPatch, aiMatchRecovery: undefined, error: undefined };
  });
  const state = await appendLog("info", `DeepSeek returned ${savedSuggestionCount} ${deniedOnly ? "rematched" : "new"} recommendations for operator approval`, {
    remainingCount: savedRemainingCount,
    requestedChildren: unresolvedSources.length,
    excludedPairs: excludedPairs.length,
    threshold,
    model: payload.model,
    chunkCount: responseChunkCount,
  });
  return state;
}

function isRecoverableAiMatchFailure(error: unknown): boolean {
  return error instanceof RecoverableAiMatchError;
}

async function rememberAiMatchFailure(
  requestState: DurableState,
  deniedOnly: boolean,
  error: unknown,
): Promise<void> {
  const message = error instanceof Error ? error.message : String(error);
  const mode: AiMatchRequestMode = deniedOnly ? "denied" : "all";
  if (!isRecoverableAiMatchFailure(error)) {
    // A previous transient failure may have left a Retry action visible. Do
    // not keep advertising it when the same request now fails for a definite
    // operator/configuration 4xx condition.
    await updateStateFromCurrent((latest) => {
      if (
        String(latest.dataset?.id || "") !== String(requestState.dataset?.id || "") ||
        portalRosterSignature(latest.portal) !== portalRosterSignature(requestState.portal) ||
        latest.aiMatchRecovery?.requestMode !== mode
      ) {
        return null;
      }
      return { aiMatchRecovery: undefined };
    });
    return;
  }

  let saved = false;
  await updateStateFromCurrent((latest) => {
    // A retry is only valid for the exact ZIP and portal roster that produced
    // the failure. If either changed while the request was running, retain the
    // new state and do not advertise a stale retry.
    if (
      String(latest.dataset?.id || "") !== String(requestState.dataset?.id || "") ||
      portalRosterSignature(latest.portal) !== portalRosterSignature(requestState.portal)
    ) {
      return null;
    }
    const pending = reconciledAiPatch(latest).aiSuggestions;
    if (Array.isArray(pending) && pending.length > 0) return null;

    const previousRecovery = isObject(latest.aiMatchRecovery) ? latest.aiMatchRecovery : {};
    const previousAttempt = previousRecovery.requestMode === mode
      ? Number(previousRecovery.attempt || 0)
      : 0;
    saved = true;
    return {
      aiMatchRecovery: {
        requestMode: mode,
        error: message.slice(0, 1_000),
        failedAt: now(),
        attempt: previousAttempt + 1,
      },
    };
  });
  if (saved) {
    await appendLog("warning", "DeepSeek matching stopped before a complete recommendation set was returned; retry is available", {
      requestMode: deniedOnly ? "denied" : "all",
      message,
    });
  }
}

function runAiNameMatchSingleFlight(deniedOnly = false): Promise<DurableState> {
  const mode: AiMatchRequestMode = deniedOnly ? "denied" : "all";
  if (aiMatchInFlight) {
    if (aiMatchInFlight.mode === mode) return aiMatchInFlight.promise;
    return Promise.reject(
      new Error("DeepSeek name matching is already in progress. Wait for that request to finish before starting a different rematch."),
    );
  }

  const execution = (async () => {
    const current = await readState();
    try {
      return await runAiNameMatch(current, deniedOnly);
    } catch (error) {
      await rememberAiMatchFailure(current, deniedOnly, error);
      throw error;
    }
  })();
  const promise = execution.finally(() => {
    if (aiMatchInFlight?.promise === promise) aiMatchInFlight = null;
  });
  aiMatchInFlight = { mode, promise };
  return promise;
}

async function handleMessage(message: JsonObject, sender: chrome.runtime.MessageSender): Promise<JsonObject> {
  const rawType = String(message?.type || "").toUpperCase();
  const aliases: Record<string, string> = {
    CONNECT_PORTAL: "CONNECT",
    START_RUN: "START",
    PAUSE_RUN: "PAUSE",
    RESUME_RUN: "RESUME",
    STOP_RUN: "STOP",
  };
  const type = aliases[rawType] || rawType;

  if (type === "CONNECT" || type === "CONNECT_CURRENT_TAB") return connectCurrentTab(Number(message.tabId) || undefined);

  if (type === "GET_STATE" || type === "GET_RUN_STATE") {
    const state = await updateStateFromCurrent(async (current) => {
      if (current.connection && !(await liveConnectedTab(current.connection))) {
        return staleConnectionPatch(current);
      }
      if (!current.connection && current.portal) {
        return staleConnectionPatch(current);
      }
      if (sender.tab) assertSenderScope(current, sender);
      const aiPatch = reconciledAiPatch(current);
      const changed =
        JSON.stringify(current.aiSuggestions || []) !== JSON.stringify(aiPatch.aiSuggestions || []) ||
        JSON.stringify(current.aiMatch || null) !== JSON.stringify(aiPatch.aiMatch || null);
      return changed ? aiPatch : null;
    });
    return { ok: true, state };
  }

  if (type === "CONTENT_READY") {
    const tabId = senderTabId(sender)!;
    const incomingPortal = isObject(message.portal) && message.portal.isPortal && childCandidates(message.portal.children).length
      ? message.portal
      : undefined;
    const next = await updateStateFromCurrent(async (current) => {
      if (!current.connection) return null;
      if (!(await liveConnectedTab(current.connection))) return staleConnectionPatch(current);
      assertSenderScope(current, sender);
      const connection = current.connection
        ? { ...current.connection, tabId, lastSeenAt: now(), url: sender.tab?.url || current.connection.url }
        : undefined;
      const portal = incomingPortal ?? current.portal;
      const runActive = current.status === "running" || current.status === "paused";
      const mappingMemory = memoryWithMappings(current);
      const mappings =
        portal && current.dataset && !runActive
          ? mappingsFromMemory(mappingMemory, current.dataset, portal)
          : current.mappings;
      const aiDeniedSuggestions = denialsAfterRestoredMappings(current, mappings, portal);
      const portalChanged = Boolean(incomingPortal) && portalRosterSignature(current.portal) !== portalRosterSignature(incomingPortal);
      const aiPatch = portalChanged
        ? { aiMatch: undefined, aiSuggestions: undefined, aiMatchRecovery: undefined }
        : reconciledAiPatch({ ...current, aiDeniedSuggestions }, mappings, portal);
      return { connection, portal, mappings, mappingMemory, aiDeniedSuggestions, ...aiPatch };
    });
    return { ok: true, state: next };
  }

  if (type === "SCAN" || type === "SCAN_PORTAL") {
    if (sender.tab) return { ok: true, delegated: false };
    const state = await readState();
    let tab: chrome.tabs.Tab;
    try {
      tab = await attendanceTab(state.connection?.tabId);
    } catch (error) {
      if (state.connection && !(await liveConnectedTab(state.connection))) {
        await clearStaleConnection(state.connection.tabId);
      }
      throw error;
    }
    const tabId = tab.id;
    if (!tabId) throw new Error("No connected attendance tab.");
    if (state.connection?.tabId !== tabId) {
      const checkpointedRun = Boolean(state.checkpoint) &&
        (state.status === "running" || state.status === "paused" || state.status === "error");
      if (checkpointedRun) {
        await clearStaleConnection(state.connection?.tabId);
        throw new Error("The saved attendance tab closed. Connect this KinderLogix tab, review the room, then resume the checkpoint.");
      }
      return connectCurrentTab(tabId);
    }
    let response: JsonObject;
    try {
      response = await requestPortalScan(tabId);
    } catch (error) {
      if (!(await liveConnectedTab(state.connection))) {
        await clearStaleConnection(tabId);
      }
      throw error;
    }
    const portalValue = response?.portal ?? response;
    if (!portalValue?.isPortal) {
      const diagnostics = Array.isArray(portalValue?.diagnostics)
        ? portalValue.diagnostics
            .map((entry: JsonObject) => `${entry.document}: date=${entry.pagedate ? "yes" : "no"}, room=${entry.pagegroupid ? "yes" : "no"}, table=${entry.table ? "yes" : "no"}, rows=${entry.childRows || 0}`)
            .join("; ")
        : "";
      throw new Error(`${portalValue?.error || "The attendance room was not detected."}${diagnostics ? ` (${diagnostics})` : ""}`);
    }
    let portal: JsonObject = {};
    const next = await updateStateFromCurrent((current) => {
      portal = {
        ...(portalValue as JsonObject),
        connected: true,
        tabId,
        origin: current.connection?.origin || "",
      };
      const mappingMemory = memoryWithMappings(current);
      const mappings = current.dataset ? mappingsFromMemory(mappingMemory, current.dataset, portal) : current.mappings;
      const aiDeniedSuggestions = denialsAfterRestoredMappings(current, mappings, portal);
      return {
        portal,
        mappings,
        mappingMemory,
        aiDeniedSuggestions,
        aiMatch: undefined,
        aiSuggestions: undefined,
        aiMatchRecovery: undefined,
        error: undefined,
        status: current.status === "running" || current.status === "paused" ? current.status : "connected",
      };
    });
    return { ok: true, portal, state: next };
  }

  if (type === "SET_DATASET") {
    const dataset = message.dataset ?? message.payload;
    const state = await updateStateFromCurrent((current) => {
      assertRunNotActive(current, "Replacing the imported dataset");
      const mappingMemory = memoryWithMappings(current);
      const mappings = mappingsFromMemory(mappingMemory, dataset, current.portal);
      const aiDeniedSuggestions = denialsAfterRestoredMappings(current, mappings);
      return {
        dataset,
        mappings,
        mappingMemory,
        aiDeniedSuggestions,
        aiMatch: undefined,
        aiSuggestions: undefined,
        aiMatchRecovery: undefined,
        status: current.connection ? "ready" : "idle",
        checkpoint: { dateIndex: 0, recordIndex: 0, childIndex: 0, sessionIndex: 0, phase: "select_date", attempt: 0 },
        progress: {
          datesCompleted: 0,
          completedDates: 0,
          recordsCompleted: 0,
          completedRecords: 0,
          sessionsCompleted: 0,
          completedSessions: 0,
        },
        error: undefined,
        overwriteConfirmed: false,
        settings: { overwriteExisting: false },
      };
    });
    return { ok: true, state };
  }

  if (type === "SET_MAPPINGS") {
    const requestedMappings = (message.mappings ?? message.payload ?? {}) as Record<string, string>;
    const state = await updateStateFromCurrent((current) => {
      assertRunNotActive(current, "Changing child mappings");
      const mappings = sanitizedMappings(current, requestedMappings);
      const mappingMemory = memoryWithMappings(current, mappings);
      const aiDeniedSuggestions = denialsAfterRestoredMappings(current, mappings);
      const aiPatch = reconciledAiPatch({ ...current, aiDeniedSuggestions }, mappings);
      return { mappings, mappingMemory, aiDeniedSuggestions, ...aiPatch, aiMatchRecovery: undefined };
    });
    return { ok: true, state };
  }

  if (type === "AI_MATCH") {
    const state = await runAiNameMatchSingleFlight();
    return { ok: true, state };
  }

  if (type === "REMATCH_DENIED") {
    const state = await runAiNameMatchSingleFlight(true);
    return { ok: true, state };
  }

  if (type === "DISMISS_AI_SUGGESTION") {
    const sourceId = String(message.sourceId || "");
    const portalId = String(message.portalId || "");
    await updateStateFromCurrent((current) => {
      assertRunNotActive(current, "Reviewing AI name suggestions");
      const validPendingSuggestions = reconciledAiPatch(current).aiSuggestions;
      const pendingSuggestion = (Array.isArray(validPendingSuggestions) ? validPendingSuggestions : []).find(
        (suggestion: JsonObject) =>
          String(suggestion.sourceChildId) === sourceId && String(suggestion.portalChildId) === portalId,
      ) as AiNameSuggestion | undefined;
      if (!pendingSuggestion) {
        throw new Error("That AI recommendation is no longer pending. Refresh the extension and review the current list.");
      }
      const aiDeniedSuggestions = rememberDeniedSuggestion(
        current.aiDeniedSuggestions,
        pendingSuggestion,
        childCandidates(current.dataset?.children),
        childCandidates(current.portal?.children),
        String(current.portal?.pageGroupId || ""),
        now(),
      );
      const remainingSuggestions = (Array.isArray(current.aiSuggestions) ? current.aiSuggestions : []).filter(
        (suggestion: JsonObject) =>
          String(suggestion.sourceChildId) !== sourceId || String(suggestion.portalChildId) !== portalId,
      );
      return {
        aiDeniedSuggestions,
        ...reconciledAiPatch(
          { ...current, aiDeniedSuggestions },
          current.mappings || {},
          current.portal,
          remainingSuggestions,
        ),
      };
    });
    const state = await appendLog("info", "AI name recommendation denied and saved for a different rematch", {
      sourceId,
      portalId,
    });
    return { ok: true, state };
  }

  if (type === "SET_MAPPING") {
    const requestedSourceId = String(message.sourceId ?? message.sourceChildId ?? message.mapping?.sourceId ?? "");
    const portalId = String(message.portalId ?? message.portalChildId ?? message.mapping?.portalId ?? "");
    const state = await updateStateFromCurrent((current) => {
      assertRunNotActive(current, "Changing child mappings");
      const mappings = { ...(current.mappings || {}) } as JsonObject;
      let sourceId = requestedSourceId;
      if (!sourceId && message.sourceChildId === null && portalId) {
        sourceId = Object.keys(mappings).find((key) => String(mappings[key]) === portalId) || "";
      }
      if (!sourceId) throw new Error("SET_MAPPING requires a source child or an existing portal mapping to remove.");
      let mappingMemory = memoryWithMappings(current);
      if (message.sourceChildId === null || !portalId) {
        delete mappings[sourceId];
        delete mappingMemory[sourceId];
      } else {
        const sourceIds = new Set(childCandidates(current.dataset?.children).map((child) => child.id));
        const portalIds = new Set(childCandidates(current.portal?.children).map((child) => child.id));
        if (!sourceIds.has(sourceId) || !portalIds.has(portalId)) {
          throw new Error("That child mapping is not part of the imported ZIP and visible portal room.");
        }
        mappings[sourceId] = portalId;
        const displacedSourceIds: string[] = [];
        Object.keys(mappings).forEach((otherSourceId) => {
          if (otherSourceId !== sourceId && mappings[otherSourceId] === portalId) {
            delete mappings[otherSourceId];
            displacedSourceIds.push(otherSourceId);
          }
        });
        mappingMemory = memoryWithMappings({ ...current, mappings }, mappings as Record<string, string>);
        displacedSourceIds.forEach((displacedSourceId) => delete mappingMemory[displacedSourceId]);
      }
      const validPendingSuggestions = reconciledAiPatch(current).aiSuggestions;
      const approvedPendingSuggestion = portalId
        ? (Array.isArray(validPendingSuggestions) ? validPendingSuggestions : []).some(
            (suggestion: JsonObject) =>
              String(suggestion.sourceChildId) === sourceId && String(suggestion.portalChildId) === portalId,
          )
        : false;
      const aiDeniedSuggestions = portalId
        ? clearDeniedSources(
            current.aiDeniedSuggestions,
            [sourceId],
            String(current.portal?.pageGroupId || ""),
          )
        : current.aiDeniedSuggestions;
      const aiPatch = reconciledAiPatch({ ...current, aiDeniedSuggestions }, mappings);
      if (approvedPendingSuggestion && isObject(aiPatch.aiMatch)) {
        aiPatch.aiMatch = {
          ...aiPatch.aiMatch,
          acceptedCount: Number(current.aiMatch?.acceptedCount || 0) + 1,
        };
      }
      return { mappings, mappingMemory, aiDeniedSuggestions, ...aiPatch, aiMatchRecovery: undefined };
    });
    return { ok: true, state };
  }

  if (type === "SET_SETTINGS") {
    const state = await updateState({ settings: message.settings ?? message.payload ?? {} });
    return { ok: true, state };
  }

  if (type === "CLEAR_ERROR_CACHE") {
    const current = await readState();
    assertRunNotActive(current, "Clearing the saved error");
    const state = await updateState({
      status: readyStatus(current),
      error: undefined,
      aiMatchRecovery: undefined,
      current: undefined,
      run: { ...(current.run || {}), status: readyStatus(current), error: undefined, currentAction: undefined },
    });
    return { ok: true, state };
  }

  if (type === "CLEAR_RUN_CACHE") {
    const current = await readState();
    assertRunNotActive(current, "Clearing run recovery data");
    const state = await updateState({ ...clearedRunPatch(current), logs: [] });
    return { ok: true, state };
  }

  if (type === "CLEAR_DATASET_CACHE") {
    const current = await readState();
    assertRunNotActive(current, "Clearing the imported ZIP");
    const state = await updateState({
      ...clearedRunPatch(current, false),
      dataset: null,
      mappings: {},
      aiMatch: undefined,
      aiSuggestions: undefined,
      aiMatchRecovery: undefined,
      logs: [],
    });
    return { ok: true, state };
  }

  if (type === "CLEAR_MAPPING_CACHE") {
    const current = await readState();
    assertRunNotActive(current, "Clearing remembered child mappings");
    const state = await updateState({
      ...clearedRunPatch(current),
      mappings: {},
      mappingMemory: {},
      aiDeniedSuggestions: [],
      aiMatch: undefined,
      aiSuggestions: undefined,
      aiMatchRecovery: undefined,
    });
    return { ok: true, state };
  }

  if (type === "CLEAR_ALL_CACHE") {
    const current = await readState();
    assertRunNotActive(current, "Clearing all local extension data");
    const reset = storageSafe(structuredClone(DEFAULT_STATE));
    await chrome.storage.local.set({ [STORAGE_KEY]: reset });
    stateWrite = Promise.resolve(reset);
    return { ok: true, state: reset };
  }

  if (type === "START") {
    let current = await readState();
    assertRunNotActive(current, "Starting an attendance run");
    if (isObject(message.settings)) {
      const { overwriteExisting: _ignored, ...safeSettings } = message.settings;
      if (Object.keys(safeSettings).length) current = await updateState({ settings: safeSettings });
    }
    if (!current.connection?.tabId) throw new Error("Connect the attendance tab first.");
    if (!current.dataset) throw new Error("Import a CareSync attendance ZIP first.");
    if (message.overwriteAcknowledged !== true) {
      throw new Error("Review the child mappings and confirm overwrite authorization first.");
    }
    const connectedTab = await liveConnectedTab(current.connection);
    if (!connectedTab) {
      await clearStaleConnection(current.connection.tabId);
      throw new Error("The saved attendance tab is closed or no longer shows KinderLogix. Connect the intended room and review it before starting.");
    }
    const scanResponse = await requestPortalScan(current.connection.tabId);
    const livePortalValue = scanResponse?.portal ?? scanResponse;
    if (!livePortalValue?.isPortal || !childCandidates(livePortalValue.children).length) {
      throw new Error("The connected tab is not showing a loaded KinderLogix attendance room. Reload the page, select the room and date, then reconnect.");
    }
    if (
      current.portal?.pageGroupId &&
      String(current.portal.pageGroupId) !== String(livePortalValue.pageGroupId || "")
    ) {
      throw new Error("The visible KinderLogix room changed after name matching. Scan and review this room again before starting.");
    }
    const livePortal = {
      ...(livePortalValue as JsonObject),
      connected: true,
      tabId: current.connection.tabId,
      origin: current.connection.origin,
    };
    current = await updateState({ portal: livePortal });

    const reviewedMappings = isObject(message.mappings)
      ? (message.mappings as Record<string, string>)
      : (current.mappings || {});
    const activeMappings = sanitizedMappings(current, reviewedMappings);
    const reviewedMappingCount = Object.values(reviewedMappings).filter(Boolean).length;
    if (Object.keys(activeMappings).length !== reviewedMappingCount) {
      throw new Error("One or more reviewed child mappings are no longer valid for the visible room. Scan and review the mappings again.");
    }
    const mappingMemory = memoryWithMappings({ ...current, mappings: activeMappings }, activeMappings);
    current = await updateState({ mappings: activeMappings, mappingMemory });

    const records = Array.isArray(current.dataset?.records) ? current.dataset.records : [];
    const visiblePortalIds = new Set(
      (Array.isArray(current.portal?.children) ? current.portal.children : []).map((child: JsonObject) => String(child.id)),
    );
    const datasetSourceIds = new Set(records.map((record: JsonObject) => String(record.sourceChildId ?? record.child_id ?? record.childId ?? "")));
    const requestedSourceIds = new Set(
      (Array.isArray(message.includedSourceChildIds) ? message.includedSourceChildIds : Object.keys(activeMappings))
        .map(String)
        .filter(Boolean),
    );
    if (!requestedSourceIds.size) throw new Error("Map at least one imported child to a visible child in this portal room.");
    for (const sourceId of requestedSourceIds) {
      if (!datasetSourceIds.has(sourceId) || !activeMappings[sourceId] || !visiblePortalIds.has(String(activeMappings[sourceId]))) {
        throw new Error("The reviewed run contains a missing or out-of-room child mapping. Scan and review the mappings again.");
      }
    }
    const runMappings = Object.fromEntries(
      [...requestedSourceIds].map((sourceId) => [sourceId, activeMappings[sourceId]]),
    );
    const mapped = records.filter((record: JsonObject) =>
      requestedSourceIds.has(String(record.sourceChildId ?? record.child_id ?? record.childId ?? "")),
    );
    if (!mapped.length) throw new Error("The reviewed children have no complete attendance records in the imported ZIP.");
    current = await updateState({ settings: { overwriteExisting: true } });
    const runId = crypto.randomUUID();
    const state = await updateStateFromCurrent((latest) => {
      // Reserve the run atomically. Two panel clicks, restored side panels, or
      // duplicate runtime messages must never reset an already-running
      // checkpoint and wake a second destructive loop.
      assertRunNotActive(latest, "Starting an attendance run");
      if (
        latest.connection?.tabId !== current.connection?.tabId ||
        String(latest.dataset?.id || "") !== String(current.dataset?.id || "") ||
        portalRosterSignature(latest.portal) !== portalRosterSignature(current.portal) ||
        childMappingSignature(latest.mappings) !== childMappingSignature(activeMappings)
      ) {
        throw new Error("The attendance room, imported ZIP, or child mappings changed while the run was starting. Review them and start again.");
      }
      return {
        status: "running",
        runId,
        startedAt: now(),
        completedAt: undefined,
        error: undefined,
        overwriteConfirmed: true,
        runMappings,
        runDatasetId: current.dataset?.id,
        runPageGroupId: String(current.portal?.pageGroupId || ""),
        includedSourceChildIds: [...requestedSourceIds],
        checkpoint: {
          engineVersion: 6,
          stage: "daily",
          dayStage: "cleanup",
          dateIndex: 0,
          cleanupIndex: 0,
          recordIndex: 0,
          sessionIndex: 0,
          phase: "select_date",
          attempt: 0,
        },
        progress: {
          cleanupDatesCompleted: 0,
          cleanupRecordsCompleted: 0,
          cleanupFailures: 0,
          datesCompleted: 0,
          recordsCompleted: 0,
          sessionsCompleted: 0,
          skippedRecords: 0,
          failedRecords: 0,
        },
      };
    });
    await appendLog("info", "Attendance run started with date-by-date cleanup, entry, and verification", { runId });
    try {
      await sendToConnectedTab({ type: "CONTENT_RUN" }, true);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await updateState({ status: "error", error: message, lastActionAt: now() });
      await appendLog("error", "Attendance run could not start on the connected tab", { runId, message });
      throw error;
    }
    return { ok: true, state };
  }

  if (type === "PAUSE") {
    await updateState({ status: "paused", pausedAt: now() });
    await appendLog("info", "Attendance run paused");
    await sendToConnectedTab({ type: "ENGINE_PAUSE" });
    const state = await readState();
    return { ok: true, state };
  }

  if (type === "RESUME") {
    const current = await readState();
    if (!current.checkpoint) throw new Error("There is no saved checkpoint to resume.");
    const connectedTab = await liveConnectedTab(current.connection);
    if (!connectedTab) {
      await clearStaleConnection(current.connection?.tabId);
      throw new Error("The saved attendance tab is closed. Connect the intended KinderLogix room before resuming the preserved checkpoint.");
    }
    const checkpoint = { ...current.checkpoint, attempt: 0 };
    const state = await updateState({ status: "running", resumedAt: now(), error: undefined, checkpoint });
    await appendLog("info", "Attendance run resumed", checkpoint);
    try {
      await sendToConnectedTab({ type: "CONTENT_RUN" }, true);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await updateState({ status: "error", error: message, lastActionAt: now() });
      await appendLog("error", "Attendance run could not resume on the connected tab", { message });
      throw error;
    }
    return { ok: true, state };
  }

  if (type === "STOP") {
    await updateState({ status: "stopped", stoppedAt: now() });
    await appendLog("info", "Attendance run stopped by operator");
    await sendToConnectedTab({ type: "ENGINE_STOP" });
    const state = await readState();
    return { ok: true, state };
  }

  if (type === "ENGINE_PATCH") {
    const current = await readState();
    assertSenderScope(current, sender);
    // Content scripts cannot replace the dataset, mappings, connection, or run
    // identity. They may only advance runtime/checkpoint fields.
    const allowed = [
      "status",
      "checkpoint",
      "progress",
      "portal",
      "error",
      "completedAt",
      "lastActionAt",
      "current",
    ];
    const patch: JsonObject = {};
    for (const key of allowed) if (Object.prototype.hasOwnProperty.call(message.patch || {}, key)) patch[key] = message.patch[key];
    const state = await updateState(patch);
    return { ok: true, state };
  }

  if (type === "ENGINE_LOG") {
    const current = await readState();
    assertSenderScope(current, sender);
    const state = await appendLog(message.level || "info", String(message.message || ""), message.details);
    return { ok: true, state };
  }

  throw new Error(`Unknown extension message: ${message?.type || "(missing type)"}`);
}

chrome.runtime.onInstalled.addListener(() => {
  void readState().then((state) => chrome.storage.local.set({ [STORAGE_KEY]: state }));
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

// Service workers may restart without firing onInstalled. Re-apply the action
// behavior so clicking the toolbar icon always opens the React side panel.
void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

chrome.runtime.onMessage.addListener((message: JsonObject, sender, sendResponse) => {
  void handleMessage(message || {}, sender)
    .then((response) => sendResponse(response))
    .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) }));
  return true;
});
