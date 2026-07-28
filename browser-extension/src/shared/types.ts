export interface AttendanceSession {
  start: string;
  end: string;
}

export interface AttendanceRecord {
  date: string;
  sourceChildId: string;
  sourceChildName: string;
  sessions: AttendanceSession[];
  scheduleEntryId?: string;
}

export interface SourceChild {
  id: string;
  name: string;
}

export interface AttendanceDataset {
  id: string;
  fileName: string;
  importedAt: string;
  dates: string[];
  children: SourceChild[];
  records: AttendanceRecord[];
}

export interface PortalChild {
  id: string;
  name: string;
}

export interface ChildMappingMemory {
  sourceId: string;
  sourceName: string;
  portalId: string;
  portalName: string;
  pageGroupId: string;
  savedAt: string;
}

export interface PortalSnapshot {
  isPortal: boolean;
  url: string;
  title?: string;
  pageGroupId: string;
  roomName: string;
  pageDate: string;
  children: PortalChild[];
  scannedAt: string;
}

export type RunStatus = 'idle' | 'ready' | 'running' | 'paused' | 'completed' | 'stopped' | 'error';
export type RunPhase =
  | 'select_date'
  | 'cleanup_existing'
  | 'delete_existing'
  | 'save_start'
  | 'save_end'
  | 'record_complete';

export interface RunCheckpoint {
  engineVersion?: number;
  /** Legacy checkpoints used cleanup/entry; current runs use one date-at-a-time daily processing. */
  stage?: 'cleanup' | 'entry' | 'daily';
  dayStage?: 'cleanup' | 'entry';
  dateIndex: number;
  cleanupIndex?: number;
  cleanupChildIds?: string[];
  recordIndex: number;
  sessionIndex: number;
  phase: RunPhase;
  attempt: number;
}

export interface RunProgress {
  cleanupDatesCompleted?: number;
  cleanupRecordsCompleted?: number;
  cleanupFailures?: number;
  failedRecords?: number;
  datesCompleted: number;
  totalDates: number;
  recordsCompleted: number;
  totalRecords: number;
  sessionsCompleted: number;
  totalSessions: number;
}

export interface RunLogEntry {
  id: string;
  at: string;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
}

export interface PortalConnection {
  tabId: number;
  origin: string;
  url: string;
  scriptId: string;
  connectedAt: string;
  lastSeenAt?: string;
}

export interface CurrentAction {
  action: string;
  date?: string;
  childId?: string;
  childName?: string;
  session?: number;
  value?: string;
}

export interface ExtensionError {
  message: string;
  at: string;
  checkpoint?: RunCheckpoint;
}

export interface AiMatchSummary {
  model: string;
  threshold: number;
  acceptedCount: number;
  suggestionCount?: number;
  chunkCount?: number;
  remainingCount: number;
  matchedAt: string;
  requestMode?: 'all' | 'denied';
}

/**
 * Durable recovery information for an AI request that failed before a valid,
 * globally unique recommendation set was returned. Existing mappings and
 * denial history remain authoritative while this retry hint is present.
 */
export interface AiMatchRecovery {
  requestMode: 'all' | 'denied';
  error: string;
  failedAt: string;
  attempt: number;
}

export interface AiNameSuggestion {
  sourceChildId: string;
  portalChildId: string;
  sourceChildName?: string;
  portalChildName?: string;
  pageGroupId?: string;
  confidence: number;
  reason: string;
}

/** A rejected AI pair, kept locally so a rematch must choose a different child. */
export interface AiDeniedSuggestion {
  sourceChildId: string;
  sourceChildName: string;
  portalChildId: string;
  portalChildName: string;
  pageGroupId: string;
  confidence: number;
  reason: string;
  deniedAt: string;
}

export interface ExtensionState {
  version: 1;
  status: RunStatus | 'connected';
  connection?: PortalConnection;
  dataset: AttendanceDataset | null;
  portal: PortalSnapshot | null;
  /** CareSync source child ID -> visible portal child ID. Unmapped children are outside the current room. */
  mappings: Record<string, string>;
  /** Long-lived, validated mapping memory used across monthly ZIP imports. */
  mappingMemory?: Record<string, ChildMappingMemory>;
  aiMatch?: AiMatchSummary;
  aiSuggestions?: AiNameSuggestion[];
  aiMatchRecovery?: AiMatchRecovery;
  /** Long-lived, room-scoped history of operator-denied AI pairs. */
  aiDeniedSuggestions?: AiDeniedSuggestion[];
  checkpoint?: RunCheckpoint;
  progress?: RunProgress;
  current?: CurrentAction;
  settings?: { overwriteExisting: boolean; timeoutMs: number; retryLimit: number };
  error?: ExtensionError | string;
  logs: RunLogEntry[];
}

export type RuntimeMessage =
  | { type: 'GET_STATE' }
  | { type: 'CONNECT_PORTAL' }
  | { type: 'SCAN_PORTAL' }
  | { type: 'SET_DATASET'; dataset: AttendanceDataset }
  | { type: 'SET_MAPPING'; sourceId: string; portalId: string | null }
  | { type: 'SET_MAPPINGS'; mappings: Record<string, string> }
  | { type: 'AI_MATCH' }
  | { type: 'REMATCH_DENIED' }
  | { type: 'DISMISS_AI_SUGGESTION'; sourceId: string; portalId: string }
  | { type: 'CLEAR_ERROR_CACHE' }
  | { type: 'CLEAR_RUN_CACHE' }
  | { type: 'CLEAR_DATASET_CACHE' }
  | { type: 'CLEAR_MAPPING_CACHE' }
  | { type: 'CLEAR_ALL_CACHE' }
  | { type: 'START_RUN'; overwriteAcknowledged: boolean; settings?: { overwriteExisting?: boolean } }
  | { type: 'PAUSE_RUN' }
  | { type: 'RESUME_RUN' }
  | { type: 'STOP_RUN' }
  | { type: 'CONTENT_READY' }
  | { type: 'CONTENT_SCAN' }
  | { type: 'CONTENT_RUN' };

export interface RuntimeResponse {
  ok: boolean;
  state?: ExtensionState;
  portal?: PortalSnapshot;
  error?: string;
}

export const STORAGE_KEY = 'caresyncAttendanceState';
