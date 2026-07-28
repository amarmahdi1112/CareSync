import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { parseCareSyncZip } from "./shared/csv";
import {
  activeDeniedSuggestions,
  exactSourceMappings,
  normalizeName,
} from "./shared/matching";
import type { ExtensionState } from "./shared/types";

type Json = Record<string, unknown>;
type UiState = ExtensionState & Json;

type ChildOption = {
  id: string;
  name: string;
  recordCount?: number;
};

type LogItem = {
  at?: string;
  level?: string;
  message?: string;
};

type NameSuggestion = {
  sourceChildId: string;
  portalChildId: string;
  confidence: number;
  reason: string;
};

const STORAGE_KEY = "caresyncAttendanceState";

const EMPTY_STATE = {
  version: 1,
  status: "idle",
  mappings: {},
  logs: [],
} as unknown as UiState;

function asObject(value: unknown): Json {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Json) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function textValue(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function childFromRecord(value: unknown): ChildOption | null {
  const item = asObject(value);
  const id = textValue(item.id ?? item.childId ?? item.child_id ?? item.sourceChildId);
  const name = textValue(item.name ?? item.childName ?? item.child_name ?? item.sourceChildName).trim();
  return id && name ? { id, name } : null;
}

function attendanceRows(dataset: unknown): unknown[] {
  const source = asObject(dataset);
  const direct = asArray(source.records ?? source.entries ?? source.attendance);
  if (direct.length) return direct;

  const dayCollections = asArray(source.days ?? source.dates ?? source.dailyAttendance ?? source.files);
  const nested = dayCollections.flatMap((day) => {
    const object = asObject(day);
    return asArray(object.records ?? object.entries ?? object.attendance ?? object.rows);
  });
  if (nested.length) return nested;

  return Object.values(source).flatMap((value) => (Array.isArray(value) ? value : []));
}

function sourceChildren(dataset: unknown): ChildOption[] {
  const source = asObject(dataset);
  const declared = asArray(source.children ?? source.sourceChildren);
  const rows = declared.length ? declared : attendanceRows(dataset);
  const counts = new Map<string, number>();
  for (const row of attendanceRows(dataset)) {
    const child = childFromRecord(row);
    if (child) counts.set(child.id, (counts.get(child.id) ?? 0) + 1);
  }
  const byId = new Map<string, ChildOption>();

  for (const row of rows) {
    const child = childFromRecord(row);
    if (!child) continue;
    const existing = byId.get(child.id);
    byId.set(child.id, {
      ...child,
      recordCount: declared.length ? counts.get(child.id) ?? 0 : (existing?.recordCount ?? 0) + 1,
    });
  }
  return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function portalChildren(portal: unknown): ChildOption[] {
  const source = asObject(portal);
  const candidates = asArray(source.children ?? source.rows ?? source.portalChildren);
  return candidates
    .map(childFromRecord)
    .filter((child): child is ChildOption => Boolean(child))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function datasetDates(dataset: unknown): string[] {
  const source = asObject(dataset);
  const explicit = asArray(source.dates ?? source.days)
    .map((value) => {
      const row = asObject(value);
      return textValue(row.date ?? row.attendanceDate ?? row.attendance_date ?? value);
    })
    .filter(Boolean);
  if (explicit.length) return [...new Set(explicit)].sort();

  return [
    ...new Set(
      attendanceRows(dataset)
        .map((value) => {
          const row = asObject(value);
          return textValue(row.date ?? row.attendanceDate ?? row.attendance_date);
        })
        .filter(Boolean),
    ),
  ].sort();
}

function datasetRecordCount(dataset: unknown): number {
  const source = asObject(dataset);
  const summary = asObject(source.summary);
  const declared = Number(source.recordCount ?? source.totalRecords ?? summary.records ?? summary.recordCount);
  return Number.isFinite(declared) && declared > 0 ? declared : attendanceRows(dataset).length;
}

function roomName(portal: unknown): string {
  const source = asObject(portal);
  return textValue(source.roomName ?? source.room ?? source.groupName ?? source.name) || "Attendance room";
}

function stateMappings(state: UiState): Record<string, string> {
  const value = asObject(state.mappings);
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, candidate]) => [key, textValue(asObject(candidate).portalChildId ?? candidate)] as const)
      .filter(([, candidate]) => Boolean(candidate)),
  );
}

function stateLogs(state: UiState): LogItem[] {
  return asArray(state.logs).filter((item): item is LogItem => Boolean(item) && typeof item === "object");
}

function stateSuggestions(state: UiState): NameSuggestion[] {
  return asArray(state.aiSuggestions)
    .map((value) => {
      const suggestion = asObject(value);
      return {
        sourceChildId: textValue(suggestion.sourceChildId),
        portalChildId: textValue(suggestion.portalChildId),
        confidence: Number(suggestion.confidence),
        reason: textValue(suggestion.reason),
      };
    })
    .filter((suggestion) =>
      Boolean(
        suggestion.sourceChildId &&
        suggestion.portalChildId &&
        Number.isFinite(suggestion.confidence),
      ),
    );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function send(type: string, payload: Json = {}): Promise<Json> {
  const response = (await chrome.runtime.sendMessage({ type, ...payload })) as Json | undefined;
  if (!response) throw new Error("The extension service worker did not respond.");
  if (response.ok === false) throw new Error(textValue(response.error) || `${type} failed.`);
  return response;
}

async function sendWithFallback(primary: string, fallback: string, payload: Json = {}): Promise<Json> {
  try {
    return await send(primary, payload);
  } catch (error) {
    if (!/unknown extension message/i.test(errorMessage(error))) throw error;
    return send(fallback, payload);
  }
}

function Icon({ name, size = 15 }: { name: "check" | "link" | "upload" | "scan" | "play" | "pause" | "stop" | "shield" | "info" | "resume" | "sparkles" | "search"; size?: number }) {
  const paths: Record<typeof name, ReactNode> = {
    check: <path d="m5 12 4 4L19 6" />,
    link: <><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1" /><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1" /></>,
    upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 20h14" /></>,
    scan: <><path d="M4 7V4h3" /><path d="M17 4h3v3" /><path d="M20 17v3h-3" /><path d="M7 20H4v-3" /><path d="M8 12h8" /></>,
    play: <path d="m8 5 11 7-11 7Z" />,
    pause: <><path d="M9 5v14" /><path d="M15 5v14" /></>,
    resume: <><path d="m9 7 7 5-7 5Z" /><path d="M4 5v14" /></>,
    stop: <rect width="12" height="12" x="6" y="6" rx="2" />,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" /><path d="m9 12 2 2 4-4" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></>,
    sparkles: <><path d="m12 3 1.2 3.3L16.5 7.5l-3.3 1.2L12 12l-1.2-3.3-3.3-1.2 3.3-1.2Z" /><path d="m18 13 .8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8Z" /><path d="m6 14 .7 1.8 1.8.7-1.8.7L6 19l-.7-1.8-1.8-.7 1.8-.7Z" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function StepHeader({ number, title, caption, complete }: { number: number; title: string; caption: string; complete: boolean }) {
  return (
    <div className="card-header">
      <div className="card-title-group">
        <div className="step-number">{complete ? <Icon name="check" size={14} /> : String(number).padStart(2, "0")}</div>
        <div>
          <h2>{title}</h2>
          <p className="card-caption" title={caption}>{caption}</p>
        </div>
      </div>
      {complete && <div className="icon-check"><Icon name="check" size={13} /></div>}
    </div>
  );
}

export default function App() {
  const [state, setState] = useState<UiState>(EMPTY_STATE);
  const [busy, setBusy] = useState<string>("");
  const [uiError, setUiError] = useState<string>("");
  const [aiError, setAiError] = useState<string>("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [scopeAcknowledged, setScopeAcknowledged] = useState(false);
  const [matchSearch, setMatchSearch] = useState("");
  const [recommendationSearch, setRecommendationSearch] = useState("");
  const autoMapSignature = useRef("");

  const refreshState = useCallback(async () => {
    const response = await send("GET_STATE");
    setState((response.state ?? EMPTY_STATE) as UiState);
  }, []);

  useEffect(() => {
    void refreshState().catch((error) => setUiError(errorMessage(error)));
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === "local" && changes[STORAGE_KEY]?.newValue) {
        setState(changes[STORAGE_KEY].newValue as UiState);
      }
    };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, [refreshState]);

  const portalState = asObject(state.portal);
  const directConnection = asObject(state.connection);
  const connection = Object.keys(directConnection).length ? directConnection : portalState;
  const run = asObject(state.run);
  const dataset = state.dataset;
  const portal = state.portal;
  const source = useMemo(() => sourceChildren(dataset), [dataset]);
  const portalList = useMemo(() => portalChildren(portal), [portal]);
  const storedMappings = useMemo(() => stateMappings(state), [state]);
  const aiSuggestions = useMemo(() => stateSuggestions(state), [state]);
  const aiMatch = asObject(state.aiMatch);
  const aiMatchRecovery = asObject(state.aiMatchRecovery);
  const aiRecoveryError = textValue(aiMatchRecovery.error);
  const aiRecoveryMode = textValue(aiMatchRecovery.requestMode) === "denied" ? "denied" : "all";
  const displayedAiError = aiError || aiRecoveryError;
  const dates = useMemo(() => datasetDates(dataset), [dataset]);
  const portalPageGroupId = textValue(portalState.pageGroupId);
  const deniedSuggestions = useMemo(
    () => activeDeniedSuggestions(state.aiDeniedSuggestions, source, portalList, portalPageGroupId),
    [portalList, portalPageGroupId, source, state.aiDeniedSuggestions],
  );

  const exactMappings = useMemo(
    () => exactSourceMappings(source, portalList),
    [portalList, source],
  );

  const mappings = useMemo(() => ({ ...exactMappings, ...storedMappings }), [exactMappings, storedMappings]);
  const visiblePortalIds = useMemo(() => new Set(portalList.map((child) => child.id)), [portalList]);
  const portalNamesById = useMemo(
    () => new Map(portalList.map((child) => [child.id, child.name])),
    [portalList],
  );
  const sourceNamesById = useMemo(
    () => new Map(source.map((child) => [child.id, child.name])),
    [source],
  );
  const suggestionsBySource = useMemo(
    () => new Map(aiSuggestions.map((suggestion) => [suggestion.sourceChildId, suggestion])),
    [aiSuggestions],
  );
  const filteredSource = useMemo(() => {
    const query = normalizeName(matchSearch);
    return source.filter((child) => {
      const suggestion = suggestionsBySource.get(child.id);
      if (!query) return true;
      const selectedPortalName = portalNamesById.get(mappings[child.id]) ?? "";
      const suggestedPortalName = suggestion ? portalNamesById.get(suggestion.portalChildId) ?? "" : "";
      return (
        normalizeName(child.name).includes(query) ||
        normalizeName(selectedPortalName).includes(query) ||
        normalizeName(suggestedPortalName).includes(query)
      );
    });
  }, [mappings, matchSearch, portalNamesById, source, suggestionsBySource]);
  const filteredAiSuggestions = useMemo(() => {
    const query = normalizeName(recommendationSearch);
    if (!query) return aiSuggestions;
    return aiSuggestions.filter((suggestion) =>
      normalizeName(sourceNamesById.get(suggestion.sourceChildId) ?? "").includes(query) ||
      normalizeName(portalNamesById.get(suggestion.portalChildId) ?? "").includes(query) ||
      normalizeName(suggestion.reason).includes(query),
    );
  }, [aiSuggestions, portalNamesById, recommendationSearch, sourceNamesById]);
  const deniedSourceGroups = useMemo(() => {
    const groups = new Map<string, typeof deniedSuggestions>();
    for (const denied of deniedSuggestions) {
      if (visiblePortalIds.has(mappings[denied.sourceChildId])) continue;
      groups.set(denied.sourceChildId, [...(groups.get(denied.sourceChildId) ?? []), denied]);
    }
    return [...groups.entries()].map(([sourceChildId, deniedPairs]) => ({ sourceChildId, deniedPairs }));
  }, [deniedSuggestions, mappings, visiblePortalIds]);

  useEffect(() => {
    const additions = Object.fromEntries(Object.entries(exactMappings).filter(([key]) => !storedMappings[key]));
    if (!Object.keys(additions).length) return;
    const next = { ...storedMappings, ...additions };
    const signature = JSON.stringify(next);
    if (signature === autoMapSignature.current) return;
    autoMapSignature.current = signature;
    void send("SET_MAPPINGS", { mappings: next })
      .then((response) => response.state && setState(response.state as UiState))
      .catch((error) => setUiError(errorMessage(error)));
  }, [exactMappings, storedMappings]);

  const mappedCount = source.filter((child) => visiblePortalIds.has(mappings[child.id])).length;
  const unresolvedCount = Math.max(0, source.length - mappedCount);
  const pendingSuggestionCount = aiSuggestions.length;
  const deniedSourceCount = deniedSourceGroups.length;
  const selectedPortalIds = source.map((child) => mappings[child.id]).filter((id) => visiblePortalIds.has(id));
  const duplicateMappingCount = selectedPortalIds.length - new Set(selectedPortalIds).size;
  const mappedSourceIds = useMemo(
    () => new Set(source.filter((child) => visiblePortalIds.has(mappings[child.id])).map((child) => child.id)),
    [mappings, source, visiblePortalIds],
  );
  const roomRecordTotal = useMemo(
    () => attendanceRows(dataset).filter((row) => {
      const child = childFromRecord(row);
      return child ? mappedSourceIds.has(child.id) : false;
    }).length,
    [dataset, mappedSourceIds],
  );
  const connected = Boolean(connection.tabId || connection.origin || portalState.connected || portalState.isPortal);
  const scanned = portalList.length > 0;
  const imported = Boolean(dataset && source.length && dates.length);
  const roomReady = imported && scanned && mappedCount > 0 && pendingSuggestionCount === 0 && (unresolvedCount === 0 || scopeAcknowledged);
  const status = textValue(state.status ?? run.status).toLowerCase() || "idle";
  const isRunning = status === "running";
  const isPaused = status === "paused";
  const isRunLocked = isRunning || isPaused;
  const needsAttention = status === "error" || status === "failed";
  const isResumable = isPaused || needsAttention;
  const isTerminal = status === "completed" || status === "stopped";
  const progress = asObject(state.progress ?? run.progress);
  const checkpoint = asObject(state.checkpoint ?? run.checkpoint);
  const checkpointPhase = textValue(checkpoint.phase);
  const dayStage = textValue(checkpoint.dayStage) || (checkpointPhase === "cleanup_existing" ? "cleanup" : "entry");
  const completedRecords = Number(progress.recordsCompleted ?? progress.completedRecords ?? progress.completed ?? 0) || 0;
  const cleanupRecordsCompleted = Number(progress.cleanupRecordsCompleted ?? 0) || 0;
  const cleanupRecordTotal = Number(progress.totalCleanupRecords) || dates.length * portalList.length;
  const entryRecordTotal = Number(progress.totalRecords) || Number(roomRecordTotal ?? datasetRecordCount(dataset)) || 0;
  const totalRecords = status === "completed" ? entryRecordTotal : dayStage === "cleanup" ? cleanupRecordTotal : entryRecordTotal;
  const displayedRecords = status === "completed" ? completedRecords : dayStage === "cleanup" ? cleanupRecordsCompleted : completedRecords;
  const percent = status === "completed" ? 100 : totalRecords ? Math.min(100, Math.round((displayedRecords / totalRecords) * 100)) : 0;
  const current = asObject(state.current);
  const currentIndex = Number(
    dayStage === "cleanup"
      ? checkpoint.cleanupIndex ?? 0
      : checkpoint.recordIndex ?? checkpoint.childIndex ?? 0,
  );
  const currentDate = textValue(current.date ?? current.attendanceDate ?? checkpoint.date ?? dates[Number(checkpoint.dateIndex ?? 0)]);
  const currentChild = textValue(
    current.childName ?? current.name ?? (dayStage === "cleanup" ? portalList[currentIndex]?.name : source[currentIndex]?.name),
  );
  const currentAction = textValue(current.action ?? current.phase ?? run.currentAction ?? checkpoint.phase).replaceAll("_", " ");
  const dateIndex = Math.max(0, Number(checkpoint.dateIndex ?? 0));
  const currentDateNumber = dates.length ? Math.min(dates.length, dateIndex + 1) : 0;
  const dayStageLabel = dayStage === "cleanup" ? "Cleaning visible attendance" : "Entering and verifying schedules";
  const skippedRecords = Number(progress.skippedRecords ?? 0) || 0;
  const failedRecords = Number(progress.failedRecords ?? 0) || 0;
  const cleanupFailures = Number(progress.cleanupFailures ?? 0) || 0;
  const logs = stateLogs(state).slice(-40).reverse();
  const runtimeError = textValue(run.error) || textValue(state.error) || textValue(asObject(state.error).message);
  const issueFromRuntime = !uiError && Boolean(runtimeError);
  const checkpointIssue = issueFromRuntime && needsAttention;
  const issueHeading = checkpointIssue ? "Run paused at a safe checkpoint" : isRunning ? "Run is continuing" : "Panel action needs attention";
  const issueText = uiError || runtimeError;

  const runAction = useCallback(async (key: string, primary: string, fallback: string, payload: Json = {}) => {
    setBusy(key);
    setUiError("");
    try {
      const response = await sendWithFallback(primary, fallback, payload);
      if (response.state) setState(response.state as UiState);
      else await refreshState();
    } catch (error) {
      setUiError(errorMessage(error));
    } finally {
      setBusy("");
    }
  }, [refreshState]);

  const connect = async () => {
    setBusy("connect");
    setUiError("");
    try {
      const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
      const candidates = await chrome.tabs.query({ url: ["https://web.kinderlogix.com/*"] });
      const activeCandidate = candidates.find((candidate) => candidate.id === active?.id);
      const tab = activeCandidate || (candidates.length === 1 ? candidates[0] : undefined);
      if (!tab?.id) {
        throw new Error(
          candidates.length > 1
            ? "More than one KinderLogix tab is open. Make the intended attendance tab active, then connect again."
            : "No KinderLogix attendance tab is open in this browser. Open https://web.kinderlogix.com/content.php first.",
        );
      }
      const response = await sendWithFallback("CONNECT_PORTAL", "CONNECT_CURRENT_TAB", { tabId: tab.id });
      if (response.state) setState(response.state as UiState);
      else await refreshState();
    } catch (error) {
      setUiError(errorMessage(error));
    } finally {
      setBusy("");
    }
  };
  const scan = () => {
    setScopeAcknowledged(false);
    setAcknowledged(false);
    setRecommendationSearch("");
    setAiError("");
    return runAction("scan", "SCAN_PORTAL", "SCAN");
  };

  const importFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy("import");
    setUiError("");
    setAcknowledged(false);
    setScopeAcknowledged(false);
    setMatchSearch("");
    setRecommendationSearch("");
    setAiError("");
    try {
      const parsed = await parseCareSyncZip(await file.arrayBuffer(), file.name);
      const response = await send("SET_DATASET", { dataset: parsed, payload: parsed });
      if (response.state) setState(response.state as UiState);
      else await refreshState();
    } catch (error) {
      setUiError(`Could not import ${file.name}: ${errorMessage(error)}`);
    } finally {
      setBusy("");
    }
  };

  const setMapping = async (sourceId: string, portalId: string) => {
    const next = { ...mappings };
    if (portalId) next[sourceId] = portalId;
    else delete next[sourceId];
    setBusy(`mapping:${sourceId}`);
    setUiError("");
    setAcknowledged(false);
    setScopeAcknowledged(false);
    try {
      let response: Json;
      try {
        response = await send("SET_MAPPING", {
          sourceId,
          portalId,
          sourceChildId: portalId ? sourceId : null,
          portalChildId: portalId || mappings[sourceId],
          mapping: { sourceId, portalId },
        });
      } catch (error) {
        if (!/unknown extension message/i.test(errorMessage(error))) throw error;
        response = await send("SET_MAPPINGS", { mappings: next });
      }
      if (response.state) setState(response.state as UiState);
      else await refreshState();
    } catch (error) {
      setUiError(errorMessage(error));
    } finally {
      setBusy("");
    }
  };

  const aiMatchNames = async (deniedOnly = false) => {
    setBusy(deniedOnly ? "ai-rematch" : "ai-match");
    setUiError("");
    setAiError("");
    setAcknowledged(false);
    setScopeAcknowledged(false);
    try {
      const response = await send(deniedOnly ? "REMATCH_DENIED" : "AI_MATCH");
      if (response.state) {
        const nextState = response.state as UiState;
        setState(nextState);
        setRecommendationSearch("");
      } else {
        await refreshState();
      }
    } catch (error) {
      const message = errorMessage(error);
      setAiError(message);
      // The service worker durably records recoverable backend failures. Pull
      // that state immediately so the retry survives closing/reopening the
      // side panel without duplicating the error in the global run banner.
      await refreshState().catch(() => undefined);
    } finally {
      setBusy("");
    }
  };

  const dismissSuggestion = async (sourceId: string, portalId: string) => {
    setBusy(`suggestion:${sourceId}`);
    setUiError("");
    try {
      const response = await send("DISMISS_AI_SUGGESTION", { sourceId, portalId });
      if (response.state) setState(response.state as UiState);
      else await refreshState();
    } catch (error) {
      setUiError(errorMessage(error));
    } finally {
      setBusy("");
    }
  };

  const start = async () => {
    if (!roomReady || !acknowledged) return;
    const includedSourceChildIds = [...mappedSourceIds];
    await runAction("start", "START_RUN", "START", {
      mappings,
      settings: { overwriteExisting: true, includedSourceChildIds },
      includedSourceChildIds,
      overwriteConfirmed: true,
      overwriteAcknowledged: true,
    });
  };

  const clearCache = async (key: string, type: string, confirmation?: string) => {
    if (confirmation && !window.confirm(confirmation)) return;
    setBusy(key);
    setUiError("");
    try {
      const response = await send(type);
      setState((response.state ?? EMPTY_STATE) as UiState);
      setAcknowledged(false);
      setScopeAcknowledged(false);
      if (type === "CLEAR_DATASET_CACHE" || type === "CLEAR_MAPPING_CACHE" || type === "CLEAR_ALL_CACHE") {
        setMatchSearch("");
        setRecommendationSearch("");
      }
    } catch (error) {
      setUiError(errorMessage(error));
    } finally {
      setBusy("");
    }
  };

  const workflowStep = !connected ? 0 : !imported ? 1 : !scanned ? 2 : pendingSuggestionCount > 0 ? 3 : !roomReady ? 2 : 4;
  const statusLabel = isRunning ? "Running" : isPaused ? "Paused safely" : needsAttention ? "Checkpoint needs attention" : status === "completed" ? "Run complete" : connected ? "Portal connected" : "Not connected";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Icon name="shield" size={19} /></div>
          <div>
            <p className="brand-name">CareSync</p>
            <p className="brand-subtitle">Attendance Operator</p>
          </div>
        </div>
        <div className={`status-pill ${isRunning ? "running" : isPaused || needsAttention ? "paused" : connected ? "connected" : ""}`}>{statusLabel}</div>
      </header>

      <section className="hero">
        <p className="eyebrow">Reliable room entry</p>
        <h1>Move attendance with confidence.</h1>
        <p>Import CareSync’s daily records, review every child match, then let the operator enter and verify each IN and OUT.</p>
      </section>

      <div className="steps" aria-label="Workflow progress">
        {[0, 1, 2, 3, 4].map((step) => <div key={step} className={`step-bar ${workflowStep > step ? "complete" : workflowStep === step ? "active" : ""}`} />)}
      </div>

      <div className="card-stack">
        <section className={`card ${connected ? "is-complete" : "is-active"}`}>
          <StepHeader number={1} title="Portal room" caption={connected ? textValue(connection.origin) || "Current attendance tab" : "Open the infant attendance page first"} complete={connected} />
          <div className="card-body">
            {connected ? (
              <div className="card-row">
                <div className="detail-tile">
                  <p className="detail-label">Detected room</p>
                  <p className="detail-value">{scanned ? `${roomName(portal)} · ${portalList.length} children` : "Ready to scan"}</p>
                </div>
                <button className="button compact" disabled={Boolean(busy) || isRunLocked} onClick={scan}>
                  {busy === "scan" ? <span className="spinner" /> : <Icon name="scan" />} {scanned ? "Scan again" : "Scan room"}
                </button>
              </div>
            ) : (
              <button className="button primary wide" disabled={Boolean(busy)} onClick={connect}>
                {busy === "connect" ? <span className="spinner" /> : <Icon name="link" />} Connect this tab
              </button>
            )}
          </div>
        </section>

        <section className={`card ${imported ? "is-complete" : connected ? "is-active" : ""}`}>
          <StepHeader number={2} title="CareSync schedule" caption={imported ? `${dates[0]} to ${dates.at(-1)}` : "Use the Daily CSV ZIP from CareSync Export"} complete={imported} />
          <div className="card-body">
            <label className="dropzone">
              <input className="file-input" type="file" accept=".zip,application/zip" disabled={Boolean(busy) || isRunLocked} onChange={(event) => void importFile(event.target.files?.[0])} />
              <span className="drop-icon">{busy === "import" ? <span className="spinner" /> : <Icon name="upload" size={17} />}</span>
              <span>
                <span className="drop-title">{imported ? "Replace imported ZIP" : "Choose CareSync ZIP"}</span>
                <span className="drop-help">Parsed locally. Dates and attendance times never go to the AI matcher.</span>
              </span>
            </label>
            {imported && (
              <div className="summary-grid">
                <div className="metric"><strong>{dates.length}</strong><span>Days</span></div>
                <div className="metric"><strong>{source.length}</strong><span>Children</span></div>
                <div className="metric"><strong>{datasetRecordCount(dataset)}</strong><span>Entries</span></div>
              </div>
            )}
          </div>
        </section>

        <section className={`card ${roomReady ? "is-complete" : imported && scanned ? "is-active" : ""}`}>
          <StepHeader number={3} title="Room matching" caption={source.length ? `${mappedCount} mapped to this room · ${unresolvedCount} outside / unresolved` : "Import and scan to compare both lists"} complete={roomReady} />
          <div className="card-body">
            {!imported || !scanned ? (
              <div className="empty-state">{!imported ? "Import a CareSync ZIP" : "Scan the current portal room"} to review child matches.</div>
            ) : (
              <>
                <div className="mapping-toolbar">
                  <span className="mapping-count"><strong>{mappedCount}</strong> mapped to room · <strong>{unresolvedCount}</strong> outside / unresolved</span>
                  <span className={`match-tag ${roomReady ? "exact" : "unresolved"}`}>{roomReady ? "Room ready" : duplicateMappingCount > 0 ? "Duplicate match" : pendingSuggestionCount > 0 ? `Approve in section 04` : "Manual matching needed"}</span>
                </div>
                {unresolvedCount > 0 && (
                  <div className="review-guidance">
                    <Icon name="info" size={13} />
                    <span>{pendingSuggestionCount > 0 ? `There are ${pendingSuggestionCount} AI recommendations waiting in the separate approval section directly below this card.` : "Choose names manually here, or generate recommendations in the separate AI approval section below."}</span>
                  </div>
                )}
                <div className="mapping-search-row">
                  <label className="mapping-search">
                    <Icon name="search" size={14} />
                    <input
                      type="search"
                      value={matchSearch}
                      placeholder="Search CareSync or portal child…"
                      aria-label="Search child name matches"
                      onChange={(event) => setMatchSearch(event.target.value)}
                    />
                    <span>{filteredSource.length} / {source.length}</span>
                  </label>
                </div>
                <div className="mapping-list">
                  {filteredSource.map((child) => {
                    const storedSelection = mappings[child.id] ?? "";
                    const selected = visiblePortalIds.has(storedSelection) ? storedSelection : "";
                    const isExact = exactMappings[child.id] === selected;
                    return (
                      <div className="mapping-item" key={child.id}>
                        <div className="mapping-names">
                          <div className="mapping-source">
                            <strong title={child.name}>{child.name}</strong>
                            <span>{child.recordCount || "—"} daily records</span>
                          </div>
                          <span className={`match-tag ${selected ? (isExact ? "exact" : "") : "unresolved"}`}>{selected ? (isExact ? "Exact" : "Confirmed") : "Unresolved"}</span>
                        </div>
                        <div className="select-wrap">
                          <select aria-label={`Portal child for ${child.name}`} value={selected} disabled={Boolean(busy) || isRunLocked} onChange={(event) => void setMapping(child.id, event.target.value)}>
                            <option value="">Select portal child…</option>
                            {portalList.map((portalChild) => <option key={portalChild.id} value={portalChild.id}>{portalChild.name}</option>)}
                          </select>
                        </div>
                      </div>
                    );
                  })}
                  {filteredSource.length === 0 && (
                    <div className="empty-state">No child names match “{matchSearch.trim()}”.</div>
                  )}
                </div>
                  <div className="notice"><Icon name="info" size={13} /><span>Confirmed matches are remembered for future monthly ZIPs and revalidated by child ID, name, and room. Every DeepSeek recommendation requires your approval, regardless of confidence.</span></div>
                {duplicateMappingCount > 0 && <div className="notice warning"><Icon name="info" size={13} /><span>One portal child is matched to multiple CareSync records. Their attendance is safely consolidated by date before portal entry.</span></div>}
                {unresolvedCount > 0 && pendingSuggestionCount === 0 && (
                  <label className="acknowledgement scope-confirmation">
                    <input type="checkbox" checked={scopeAcknowledged} disabled={Boolean(busy) || isRunLocked} onChange={(event) => setScopeAcknowledged(event.target.checked)} />
                    <span>I confirm the {unresolvedCount} outside / unresolved CareSync {unresolvedCount === 1 ? "child is" : "children are"} not part of this visible portal room. Only the {mappedCount} mapped {mappedCount === 1 ? "child" : "children"} will run here.</span>
                  </label>
                )}
              </>
            )}
          </div>
        </section>

        <section className={`card ai-approval-card ${pendingSuggestionCount > 0 || deniedSourceCount > 0 ? "is-active" : aiMatch.matchedAt ? "is-complete" : ""}`}>
          <StepHeader
            number={4}
            title="AI recommendation approval"
            caption={!imported || !scanned ? "Import the ZIP and scan the room first" : pendingSuggestionCount > 0 ? `${pendingSuggestionCount} DeepSeek recommendation${pendingSuggestionCount === 1 ? "" : "s"} waiting for your decision` : deniedSourceCount > 0 ? `${deniedSourceCount} denied ${deniedSourceCount === 1 ? "child is" : "children are"} ready for a different rematch` : aiMatch.matchedAt ? "No AI recommendations are waiting" : "Generate suggestions, then approve or deny every match here"}
            complete={Boolean(aiMatch.matchedAt) && pendingSuggestionCount === 0 && deniedSourceCount === 0}
          />
          <div className="card-body">
            {!imported || !scanned ? (
              <div className="empty-state">The AI approval list becomes available after the CareSync ZIP is imported and the KinderLogix room is scanned.</div>
            ) : unresolvedCount === 0 ? (
              <div className="empty-state">Every CareSync child is already matched to this portal room. No AI approval is needed.</div>
            ) : (
              <>
                <button className="button ai-match wide" disabled={Boolean(busy) || isRunLocked || pendingSuggestionCount > 0} onClick={() => void aiMatchNames(false)}>
                  {busy === "ai-match" ? <span className="spinner" /> : <Icon name="sparkles" />} {pendingSuggestionCount > 0 ? "Approve or deny the current recommendations first" : "Generate AI recommendations with DeepSeek"}
                </button>
                {displayedAiError && (
                  <div className="notice error ai-inline-error error-with-action" role="status" aria-live="polite">
                    <Icon name="info" size={13} />
                    <span className="ai-error-copy">
                      <strong>DeepSeek did not finish</strong>
                      <small>{displayedAiError}</small>
                      {aiRecoveryError && <small>Your approved mappings, denied pairs, and current room data were preserved. Retry requests the complete globally unique set again.</small>}
                    </span>
                    {aiRecoveryError && (
                      <button
                        className="button compact ai-retry"
                        disabled={Boolean(busy) || isRunLocked || pendingSuggestionCount > 0}
                        onClick={() => void aiMatchNames(aiRecoveryMode === "denied")}
                      >
                        {busy === (aiRecoveryMode === "denied" ? "ai-rematch" : "ai-match") ? <span className="spinner" /> : <Icon name="sparkles" size={13} />}
                        Retry
                      </button>
                    )}
                  </div>
                )}
                {aiMatch.matchedAt && (
                  <div className="ai-result">
                    <Icon name="sparkles" size={13} />
                    <span><strong>{pendingSuggestionCount}</strong> awaiting your decision · {unresolvedCount} currently unresolved · {textValue(aiMatch.chunkCount ?? 1)} AI {Number(aiMatch.chunkCount ?? 1) === 1 ? "chunk" : "chunks"}</span>
                  </div>
                )}
                {pendingSuggestionCount > 0 ? (
                  <section className="recommendation-review" aria-label="AI name recommendations awaiting approval">
                    <header>
                      <div>
                        <strong>AI recommendations—approve or deny</strong>
                        <span>CareSync child → KinderLogix portal child</span>
                      </div>
                      <span className="recommendation-count">{pendingSuggestionCount} left</span>
                    </header>
                    <label className="mapping-search recommendation-search">
                      <Icon name="search" size={14} />
                      <input
                        type="search"
                        value={recommendationSearch}
                        placeholder="Search either child name…"
                        aria-label="Search AI name recommendations"
                        onChange={(event) => setRecommendationSearch(event.target.value)}
                      />
                      <span>{filteredAiSuggestions.length} / {pendingSuggestionCount}</span>
                    </label>
                    <div className="recommendation-list">
                      {filteredAiSuggestions.map((suggestion) => {
                        const sourceName = sourceNamesById.get(suggestion.sourceChildId) ?? "Unknown CareSync child";
                        const portalName = portalNamesById.get(suggestion.portalChildId) ?? "Unknown portal child";
                        const suggestionConflict = selectedPortalIds.some((portalId) => portalId === suggestion.portalChildId);
                        return (
                          <article className="recommendation-item" key={suggestion.sourceChildId}>
                            <div className="recommendation-pair">
                              <strong title={sourceName}>{sourceName}</strong>
                              <span aria-hidden="true">→</span>
                              <strong title={portalName}>{portalName}</strong>
                            </div>
                            <div className="recommendation-explanation">
                              <span>{Math.round(suggestion.confidence * 100)}% confidence</span>
                              <p title={suggestion.reason}>{suggestion.reason || "Possible name variation"}</p>
                            </div>
                            <div className="suggestion-actions">
                              <button className="suggestion-verify" disabled={Boolean(busy) || isRunLocked || suggestionConflict} onClick={() => void setMapping(suggestion.sourceChildId, suggestion.portalChildId)}>{suggestionConflict ? "Already used" : "Approve this match"}</button>
                              <button className="suggestion-reject" disabled={Boolean(busy) || isRunLocked} onClick={() => void dismissSuggestion(suggestion.sourceChildId, suggestion.portalChildId)}>Deny</button>
                            </div>
                          </article>
                        );
                      })}
                      {filteredAiSuggestions.length === 0 && <div className="empty-state">No recommendations match “{recommendationSearch.trim()}”.</div>}
                    </div>
                  </section>
                ) : (
                  <div className="empty-state ai-empty-state">{deniedSourceCount > 0 ? "The denied queue is safely stored below. Choose Rematch denied children when you want DeepSeek to find different candidates." : aiMatch.matchedAt ? "DeepSeek has no pending recommendations. Generate again after rescanning if the portal room changed; otherwise use the manual name dropdowns in section 03." : "Select Generate AI recommendations. Every returned match will appear in this separate section for your approval—nothing will be applied automatically."}</div>
                )}
                {deniedSourceCount > 0 && (
                  <section className="denied-review" aria-label="Denied AI name recommendations">
                    <header>
                      <div>
                        <strong>Denied recommendations—saved</strong>
                        <span>DeepSeek cannot repeat these exact CareSync → KinderLogix pairs.</span>
                      </div>
                      <span className="denied-count">{deniedSourceCount} {deniedSourceCount === 1 ? "child" : "children"}</span>
                    </header>
                    <div className="denied-list">
                      {deniedSourceGroups.map(({ sourceChildId, deniedPairs }) => (
                        <article className="denied-item" key={sourceChildId}>
                          <div>
                            <strong title={sourceNamesById.get(sourceChildId) ?? deniedPairs[0]?.sourceChildName}>{sourceNamesById.get(sourceChildId) ?? deniedPairs[0]?.sourceChildName}</strong>
                            <span>{deniedPairs.length} rejected {deniedPairs.length === 1 ? "candidate" : "candidates"}</span>
                          </div>
                          <p title={deniedPairs.map((pair) => pair.portalChildName).join(", ")}>{deniedPairs.map((pair) => pair.portalChildName).join(" · ")}</p>
                        </article>
                      ))}
                    </div>
                    <button className="button rematch-denied wide" disabled={Boolean(busy) || isRunLocked || pendingSuggestionCount > 0} onClick={() => void aiMatchNames(true)}>
                      {busy === "ai-rematch" ? <span className="spinner" /> : <Icon name="sparkles" />} {pendingSuggestionCount > 0 ? "Finish the current review before rematching" : `Rematch ${deniedSourceCount} denied ${deniedSourceCount === 1 ? "child" : "children"}`}
                    </button>
                    <div className="denied-help">Only denied, still-unresolved children are sent again. Approved mappings stay exactly as they are.</div>
                  </section>
                )}
              </>
            )}
          </div>
        </section>

        <section className={`card ${isRunning || isPaused || needsAttention || isTerminal ? "is-active" : roomReady ? "is-active" : ""}`}>
          <StepHeader
            number={5}
            title="Attendance run"
            caption={isRunning || isPaused || needsAttention ? `Date ${currentDateNumber || "—"} of ${dates.length || "—"} · ${dayStageLabel}` : "Each date: clean room, enter and verify, then continue"}
            complete={status === "completed"}
          />
          <div className="card-body">
            {isRunning || isPaused || needsAttention || isTerminal ? (
              <>
                <div className="pipeline-status">
                  <span className={`pipeline-stage ${status === "completed" ? "complete" : dayStage}`}>{status === "completed" ? "Complete" : dayStage === "cleanup" ? "Cleanup" : "Entry + verify"}</span>
                  <div>
                    <strong>{status === "completed" ? "All dates complete" : `Date ${currentDateNumber || "—"} of ${dates.length || "—"}`}</strong>
                    <span>{status === "completed" ? "Every completed record passed portal confirmation." : dayStage === "cleanup" ? "Removing all visible sessions for this date before entry begins." : "Writing and verifying this date before moving to the next date."}</span>
                  </div>
                </div>
                <div className="progress-wrap">
                  <div className="progress-meta"><strong>{status === "completed" ? "Run complete" : dayStage === "cleanup" ? `${percent}% cleanup progress` : `${percent}% entry progress`}</strong><span>{displayedRecords} / {totalRecords}</span></div>
                  <div className="progress-track"><div className="progress-fill" style={{ width: `${percent}%` }} /></div>
                </div>
                <div className={`current-action ${isRunning ? "running" : ""}`}>
                  <span className="activity-dot" />
                  <div>
                    <strong>{currentChild || (status === "completed" ? "All entries verified" : needsAttention ? "Checkpoint preserved for recovery" : "Saved checkpoint ready")}</strong>
                    <span>{[currentDate, currentAction].filter(Boolean).join(" · ") || (needsAttention ? "Correct the reported issue, then resume the checkpoint." : status)}</span>
                  </div>
                </div>
                {isTerminal && (
                  <label className="acknowledgement">
                    <input type="checkbox" checked={acknowledged} disabled={!roomReady || Boolean(busy)} onChange={(event) => setAcknowledged(event.target.checked)} />
                    <span>I authorize a new date-by-date run: clean the visible room for each date, enter and verify that date, then continue.</span>
                  </label>
                )}
                <div className="run-grid">
                  {isRunning ? <button className="button" disabled={Boolean(busy)} onClick={() => void runAction("pause", "PAUSE_RUN", "PAUSE")}><Icon name="pause" /> Pause safely</button> : isResumable ? <button className="button primary" disabled={Boolean(busy)} onClick={() => void runAction("resume", "RESUME_RUN", "RESUME")}><Icon name="resume" /> {needsAttention ? "Resume checkpoint" : "Resume"}</button> : <button className="button primary" disabled={!roomReady || !acknowledged || Boolean(busy)} onClick={() => void start()}><Icon name="play" /> Run again</button>}
                  <button className="button danger" disabled={Boolean(busy) || status === "completed" || status === "stopped"} onClick={() => void runAction("stop", "STOP_RUN", "STOP")}><Icon name="stop" /> Stop run</button>
                </div>
                <div className="notice continuation-notice"><Icon name="info" size={13} /><span>Recoverable date-child issues are logged and skipped; the batch continues with the remaining records. A safety or portal-state failure preserves this checkpoint and shows <strong>Resume checkpoint</strong> after you correct it.</span></div>
                {skippedRecords > 0 && <div className="notice warning"><Icon name="info" size={13} /><span>{skippedRecords} unavailable date-child {skippedRecords === 1 ? "record has" : "records have"} been skipped. The run continued and the details remain in the activity log.</span></div>}
                {(failedRecords > 0 || cleanupFailures > 0) && <div className="notice error"><Icon name="info" size={13} /><span>The batch continued past {failedRecords} entry {failedRecords === 1 ? "failure" : "failures"} and {cleanupFailures} cleanup {cleanupFailures === 1 ? "failure" : "failures"}. Review the activity log and retry those records before treating the month as complete.</span></div>}
                {logs.length > 0 && <div className="log" aria-label="Run activity log">{logs.map((item, index) => <div className="log-entry" key={`${item.at}-${index}`}><span className="log-time">{item.at ? new Date(item.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"}</span><span>{item.message || item.level || "Activity saved"}</span></div>)}</div>}
              </>
            ) : (
              <>
                <label className="acknowledgement">
                  <input type="checkbox" checked={acknowledged} disabled={!roomReady || Boolean(busy)} onChange={(event) => setAcknowledged(event.target.checked)} />
                  <span>I authorize the date-by-date pipeline: delete every visible session on a date, enter and verify its approved schedules, then continue to the next ZIP date.</span>
                </label>
                <button className="button primary wide" disabled={!roomReady || !acknowledged || Boolean(busy)} onClick={() => void start()}>
                  {busy === "start" ? <span className="spinner" /> : <Icon name="play" />} Start attendance run
                </button>
                <div className="notice"><Icon name="info" size={13} /><span>KinderLogix stores attendance on a five-minute grid. Non-grid ZIP times are deterministically rounded to the nearest five minutes and recorded in the activity log.</span></div>
                <div className="notice warning"><Icon name="shield" size={13} /><span>For each ZIP date, the operator removes every visible session in this room, confirms cleanup, enters and verifies the mapped IN/OUT schedules, and only then advances to the next date.</span></div>
              </>
            )}
          </div>
        </section>

        {issueText && (
          <div className={`notice ${checkpointIssue ? "error" : "warning"} error-with-action`}>
            <Icon name="info" size={14} />
            <span className="issue-copy"><strong>{issueHeading}</strong><small>{issueText}</small>{checkpointIssue && <small>Correct the issue in the portal, then resume from the saved date and action.</small>}</span>
            <button
              className="notice-action"
              disabled={Boolean(busy) || (issueFromRuntime && isRunLocked)}
              onClick={() => checkpointIssue ? void runAction("resume", "RESUME_RUN", "RESUME") : issueFromRuntime ? void clearCache("clear-error", "CLEAR_ERROR_CACHE") : setUiError("")}
            >
              {checkpointIssue ? "Resume checkpoint" : issueFromRuntime ? "Clear saved notice" : "Dismiss"}
            </button>
          </div>
        )}

        <details className="maintenance-card">
          <summary>Local data &amp; recovery</summary>
          <div className="maintenance-body">
            <p>Clear only the saved state that is causing trouble. Name memory and imported attendance stay intact unless you choose those controls.</p>
            <div className="maintenance-grid">
              <button className="button compact" disabled={Boolean(busy) || isRunLocked || !runtimeError} onClick={() => void clearCache("clear-error", "CLEAR_ERROR_CACHE")}>Clear saved error</button>
              <button className="button compact" disabled={Boolean(busy) || isRunLocked} onClick={() => void clearCache("clear-run", "CLEAR_RUN_CACHE", "Clear the saved checkpoint, progress, and activity log? Imported ZIP and name mappings will remain.")}>Clear run history</button>
              <button className="button compact" disabled={Boolean(busy) || isRunLocked || !dataset} onClick={() => void clearCache("clear-zip", "CLEAR_DATASET_CACHE", "Remove the imported ZIP and run history? Remembered child names will remain for the next import.")}>Remove imported ZIP</button>
              <button className="button compact" disabled={Boolean(busy) || isRunLocked} onClick={() => void clearCache("clear-mappings", "CLEAR_MAPPING_CACHE", "Forget every saved child-name mapping and denied AI pair? You will need to match the room again.")}>Forget name decisions</button>
              <button className="button compact danger maintenance-reset" disabled={Boolean(busy) || isRunLocked} onClick={() => void clearCache("clear-all", "CLEAR_ALL_CACHE", "Reset all CareSync extension data, including the imported ZIP, mappings, portal connection, checkpoints, logs, and settings?")}>Reset all local data</button>
            </div>
            {isRunLocked && <div className="notice warning"><Icon name="shield" size={13} /><span>Pause is not enough for cache clearing. Stop the active run first so its recovery checkpoint cannot be removed accidentally.</span></div>}
          </div>
        </details>
      </div>

      <p className="footer-note"><Icon name="shield" size={11} /> State is saved locally after every confirmed step</p>
    </main>
  );
}
