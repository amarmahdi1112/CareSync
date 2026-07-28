/*
 * CareSync Attendance - portal automation content script
 *
 * This script deliberately drives the portal's existing DOM event handlers.
 * It never calls private portal AJAX endpoints. Every server mutation is
 * followed by a DOM confirmation before the durable checkpoint advances.
 */

(() => {
  const GUARD = "__caresyncAttendanceEngineLoadedV6";
  const globalWindow = window as unknown as Window & Record<string, unknown>;
  if (globalWindow[GUARD]) return;
  globalWindow[GUARD] = true;

  type JsonObject = Record<string, any>;

  interface SessionValue {
    start: string;
    end: string;
    sourceStart?: string;
    sourceEnd?: string;
  }

  interface PreparedRecord {
    source: JsonObject;
    sourceId: string;
    name: string;
    normalizedName: string;
    sessions: SessionValue[];
  }

  interface PreparedDay {
    date: string;
    records: PreparedRecord[];
  }

  interface PortalChild {
    id: string;
    name: string;
    normalizedName: string;
    hasExisting: boolean;
    sessions: Array<{ timeId: string; start: string; end: string; subtotal: string }>;
  }

  class PausedError extends Error {}
  class StoppedError extends Error {}
  class HardSafetyError extends Error {}
  class PortalNotReadyError extends Error {}

  let enginePromise: Promise<void> | null = null;
  let chip: HTMLDivElement | null = null;
  let cachedPortalDocument: Document | null = null;
  let scheduledWake: number | null = null;

  const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
  const timestamp = () => new Date().toISOString();

  function text(value: unknown): string {
    return value == null ? "" : String(value).trim();
  }

  function normalizeName(value: unknown): string {
    return text(value)
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[’‘`]/g, "'")
      .toLocaleLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .replace(/\s+/g, " ");
  }

  function normalizeIsoDate(value: unknown): string {
    const raw = text(value);
    const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) throw new Error(`Invalid attendance date: ${raw || "(blank)"}`);
    return `${match[1]}-${match[2]}-${match[3]}`;
  }

  function minutesFromTime(value: unknown): number | null {
    const raw = text(value).toLowerCase();
    if (!raw) return null;
    const twelve = raw.match(/^(\d{1,2}):(\d{2})\s*([ap])\.?m\.?$/);
    if (twelve) {
      let hour = Number(twelve[1]) % 12;
      if (twelve[3] === "p") hour += 12;
      const minute = Number(twelve[2]);
      return hour <= 23 && minute <= 59 ? hour * 60 + minute : null;
    }
    const twentyFour = raw.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
    if (!twentyFour) return null;
    const hour = Number(twentyFour[1]);
    const minute = Number(twentyFour[2]);
    return hour <= 23 && minute <= 59 ? hour * 60 + minute : null;
  }

  function portalTime(value: unknown): string {
    const minutes = minutesFromTime(value);
    if (minutes == null) throw new Error(`Invalid attendance time: ${text(value) || "(blank)"}`);
    const roundedMinutes = Math.round(minutes / 5) * 5;
    if (roundedMinutes >= 24 * 60) {
      throw new Error(`Attendance time ${text(value)} cannot be represented on the portal's five-minute grid.`);
    }
    const hour24 = Math.floor(roundedMinutes / 60);
    const minute = roundedMinutes % 60;
    const suffix = hour24 >= 12 ? "pm" : "am";
    const hour12 = hour24 % 12 || 12;
    return `${hour12}:${String(minute).padStart(2, "0")} ${suffix}`;
  }

  function timesEqual(left: unknown, right: unknown): boolean {
    const a = minutesFromTime(left);
    const b = minutesFromTime(right);
    return a != null && b != null && a === b;
  }

  function formatPortalDate(isoDate: string): string {
    const [year, month, day] = normalizeIsoDate(isoDate).split("-").map(Number);
    const date = new Date(year, month - 1, day, 12, 0, 0);
    return new Intl.DateTimeFormat("en-US", {
      weekday: "long",
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
  }

  function sourceName(row: JsonObject): string {
    return text(row.child_name ?? row.childName ?? row.sourceChildName ?? row.name ?? row.full_name ?? row.fullName);
  }

  function sourceId(row: JsonObject): string {
    return text(row.child_id ?? row.childId ?? row.sourceChildId ?? row.id ?? sourceName(row));
  }

  function rowDate(row: JsonObject, fallback?: unknown): string {
    return normalizeIsoDate(row.attendance_date ?? row.attendanceDate ?? row.date ?? fallback);
  }

  function rowSessions(row: JsonObject): SessionValue[] {
    const rawSessions = Array.isArray(row.sessions) ? row.sessions : null;
    const pairs: SessionValue[] = rawSessions
      ? rawSessions.map((session: JsonObject) => ({
          start: text(session.start ?? session.startTime ?? session.in),
          end: text(session.end ?? session.endTime ?? session.out),
        }))
      : [1, 2].map((number) => ({
          start: text(row[`session_${number}_start`] ?? row[`session${number}Start`]),
          end: text(row[`session_${number}_end`] ?? row[`session${number}End`]),
        }));

    const sessions = pairs.filter((session: SessionValue) => session.start || session.end);
    for (const session of sessions) {
      if (!session.start || !session.end) throw new Error(`Incomplete IN/OUT pair for ${sourceName(row) || sourceId(row)}.`);
      session.sourceStart = session.start;
      session.sourceEnd = session.end;
      session.start = portalTime(session.start);
      session.end = portalTime(session.end);
      const start = minutesFromTime(session.start)!;
      const end = minutesFromTime(session.end)!;
      if (end <= start) throw new Error(`OUT must be after IN for ${sourceName(row) || sourceId(row)}.`);
    }
    if (sessions.length > 2) throw new Error(`The portal automation supports at most two sessions per child per day.`);
    return sessions;
  }

  function rawRows(dataset: any): Array<{ row: JsonObject; date?: unknown }> {
    if (Array.isArray(dataset)) return dataset.map((row) => ({ row }));
    if (!dataset || typeof dataset !== "object") return [];
    const direct = dataset.records ?? dataset.rows ?? dataset.entries;
    if (Array.isArray(direct)) return direct.map((row: JsonObject) => ({ row }));

    const days = dataset.days ?? dataset.dates;
    if (Array.isArray(days)) {
      return days.flatMap((day: JsonObject) => {
        const rows = day.records ?? day.rows ?? day.entries ?? day.children ?? [];
        return Array.isArray(rows) ? rows.map((row: JsonObject) => ({ row, date: day.date ?? day.attendance_date })) : [];
      });
    }

    const daily = dataset.dailyRecords ?? dataset.daily_records ?? dataset.byDate;
    if (daily && typeof daily === "object") {
      return Object.entries(daily).flatMap(([date, rows]) =>
        Array.isArray(rows) ? rows.map((row: JsonObject) => ({ row, date })) : [],
      );
    }
    return [];
  }

  function prepareDataset(dataset: unknown): PreparedDay[] {
    const grouped = new Map<string, PreparedRecord[]>();
    for (const item of rawRows(dataset)) {
      const name = sourceName(item.row);
      if (!name) throw new Error("Every attendance record must have child_name.");
      const sessions = rowSessions(item.row);
      if (!sessions.length) continue;
      const date = rowDate(item.row, item.date);
      const record: PreparedRecord = {
        source: item.row,
        sourceId: sourceId(item.row),
        name,
        normalizedName: normalizeName(name),
        sessions,
      };
      grouped.set(date, [...(grouped.get(date) || []), record]);
    }
    const days = [...grouped.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, records]) => ({ date, records }));
    if (!days.length) throw new Error("The imported dataset has no complete attendance sessions.");
    return days;
  }

  function accessibleDocuments(root: Document = document, seen = new Set<Document>()): Document[] {
    if (seen.has(root)) return [];
    seen.add(root);
    const documents = [root];
    for (const frame of root.querySelectorAll<HTMLIFrameElement | HTMLFrameElement>("iframe, frame")) {
      try {
        if (frame.contentDocument) documents.push(...accessibleDocuments(frame.contentDocument, seen));
      } catch {
        // Cross-origin frames are intentionally ignored. The extension never
        // reaches outside the portal origin explicitly granted by the operator.
      }
    }
    return documents;
  }

  function hasAttendanceMarkers(candidate: Document): boolean {
    const hasRows = Boolean(
      candidate.querySelector("#childattendancetable") ||
        candidate.querySelector('input[name="attendchildid"]') ||
        candidate.querySelector('[id^="detailrow"] .attendancetime'),
    );
    return Boolean(candidate.querySelector("#pagedate") && candidate.querySelector("#pagegroupid") && hasRows);
  }

  function portalDocument(): Document | null {
    if (cachedPortalDocument?.isConnected && hasAttendanceMarkers(cachedPortalDocument)) return cachedPortalDocument;
    cachedPortalDocument = accessibleDocuments().find(hasAttendanceMarkers) || null;
    return cachedPortalDocument;
  }

  function isPortalPage(): boolean {
    return portalDocument() !== null;
  }

  async function waitForPortalPage(timeoutMs = 10_000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (isPortalPage()) return true;
      await sleep(200);
    }
    return isPortalPage();
  }

  function looksLikeLoginPage(): boolean {
    return accessibleDocuments().some((candidate) =>
      Boolean(
        candidate.querySelector('input[type="password"]') ||
          candidate.querySelector('form[action*="login" i]') ||
          candidate.querySelector('[id*="login" i] input[name*="password" i]'),
      ),
    );
  }

  function assertVerifiedContext(isoDate: string, expectedGroupId: string): void {
    const attendanceDocument = portalDocument();
    if (!attendanceDocument) {
      if (!looksLikeLoginPage() && location.pathname.toLowerCase().includes("content.php")) {
        throw new PortalNotReadyError("The attendance room is temporarily reloading.");
      }
      throw new HardSafetyError("The authenticated attendance page is no longer available. Return to the room before resuming.");
    }
    const activeGroupId = text(attendanceDocument.querySelector<HTMLInputElement>("#pagegroupid")?.value);
    if (expectedGroupId && activeGroupId !== expectedGroupId) {
      throw new HardSafetyError(
        `The portal room changed from ${expectedGroupId} to ${activeGroupId || "unknown"}. Return to the mapped room before resuming.`,
      );
    }
    const expectedDate = formatPortalDate(isoDate);
    const activeDate = text(attendanceDocument.querySelector<HTMLInputElement>("#pagedate")?.value);
    if (activeDate !== expectedDate) {
      throw new HardSafetyError(`Portal date verification failed: found ${activeDate || "unknown"}; expected ${expectedDate}.`);
    }
  }

  function retryLimit(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.min(3, Math.floor(parsed))) : 2;
  }

  function isControlOrSafetyError(error: unknown): boolean {
    return (
      error instanceof PausedError ||
      error instanceof StoppedError ||
      error instanceof HardSafetyError ||
      error instanceof PortalNotReadyError
    );
  }

  function childTbody(childId: string): HTMLElement | null {
    return portalDocument()?.querySelector<HTMLElement>(`#detailrow${CSS.escape(childId)}`) || null;
  }

  function portalChildren(): PortalChild[] {
    const hiddenIds = [...(portalDocument()?.querySelectorAll<HTMLInputElement>('input[name="attendchildid"]') || [])];
    return hiddenIds.map((hidden) => {
      const id = hidden.value;
      const tbody = childTbody(id) || hidden.closest("tbody");
      const name = text(tbody?.querySelector("tr a")?.textContent);
      const sessions = tbody
        ? [...tbody.querySelectorAll<HTMLInputElement>('.attendancetime[data-input="starttime"]')]
            .map((start) => {
              const timeId = text(start.dataset.timeid);
              const row = start.closest("tr");
              const end = row?.querySelector<HTMLInputElement>('.attendancetime[data-input="endtime"]');
              const subtotal = row?.querySelector<HTMLInputElement>(".subtotal");
              return {
                timeId,
                start: text(start.value),
                end: text(end?.value),
                subtotal: text(subtotal?.value),
              };
            })
            .filter((session) => session.timeId !== "0" || session.start || session.end)
        : [];
      return { id, name, normalizedName: normalizeName(name), hasExisting: sessions.length > 0, sessions };
    });
  }

  function scanPortal(): JsonObject {
    const attendanceDocument = portalDocument();
    if (!attendanceDocument) {
      const diagnostics = accessibleDocuments().map((candidate, index) => ({
        document: index === 0 ? "top" : `frame-${index}`,
        pagedate: Boolean(candidate.querySelector("#pagedate")),
        pagegroupid: Boolean(candidate.querySelector("#pagegroupid")),
        table: Boolean(candidate.querySelector("#childattendancetable")),
        childRows: candidate.querySelectorAll('input[name="attendchildid"]').length,
      }));
      return {
        isPortal: false,
        error: "The attendance date, room, and child rows were not found together. Open a room, select a date, wait for its child list, then Scan again.",
        url: location.href,
        diagnostics,
      };
    }
    const groupId = text(attendanceDocument.querySelector<HTMLInputElement>("#pagegroupid")?.value);
    const roomLabels = [...attendanceDocument.querySelectorAll<HTMLAnchorElement>('a[onclick*="changeGroupPrompt"]')]
      .map((element) => text(element.textContent))
      .filter(Boolean);
    const pageDate = text(attendanceDocument.querySelector<HTMLInputElement>("#pagedate")?.value);
    return {
      isPortal: true,
      connected: true,
      url: location.href,
      origin: location.origin,
      title: attendanceDocument.title || document.title,
      pageDate,
      currentDate: pageDate,
      pageGroupId: groupId,
      roomName: roomLabels[0] || `Room ${groupId}`,
      children: portalChildren(),
      scannedAt: timestamp(),
    };
  }

  async function runtimeMessage(message: JsonObject): Promise<JsonObject> {
    const response = await chrome.runtime.sendMessage(message);
    if (!response?.ok) throw new Error(response?.error || `Extension request failed: ${message.type}`);
    return response;
  }

  async function state(): Promise<JsonObject> {
    return (await runtimeMessage({ type: "GET_RUN_STATE" })).state;
  }

  async function patch(patchValue: JsonObject): Promise<JsonObject> {
    return (await runtimeMessage({ type: "ENGINE_PATCH", patch: patchValue })).state;
  }

  async function log(level: string, message: string, details?: unknown): Promise<void> {
    await runtimeMessage({ type: "ENGINE_LOG", level, message, details });
  }

  async function ensureRunning(): Promise<JsonObject> {
    const current = await state();
    if (current.status === "paused") throw new PausedError("Run paused");
    if (current.status === "stopped" || current.status === "completed") throw new StoppedError(current.status);
    if (current.status !== "running") throw new Error(`Run is not active (status: ${current.status || "unknown"}).`);
    return current;
  }

  async function waitFor<T>(
    description: string,
    predicate: () => T | null | undefined | false,
    timeoutMs: number,
    intervalMs = 150,
  ): Promise<T> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await ensureRunning();
      const result = predicate();
      if (result) return result;
      await sleep(intervalMs);
    }
    throw new Error(`Timed out waiting for ${description}. No further records were changed.`);
  }

  async function waitForDomStable(timeoutMs: number, previousTable?: Element | null): Promise<void> {
    let lastMutation = Date.now();
    let listChanged = previousTable ? portalDocument()?.querySelector("#childattendancetable") !== previousTable : true;
    const attendanceDocument = portalDocument() || document;
    const Observer = attendanceDocument.defaultView?.MutationObserver || MutationObserver;
    const observer = new Observer((records) => {
      const currentTable = portalDocument()?.querySelector("#childattendancetable");
      const tableReplaced = Boolean(previousTable && currentTable !== previousTable);
      const tableMutated = records.some((record) =>
        Boolean(
          previousTable &&
            (record.target === previousTable ||
              previousTable.contains(record.target) ||
              [...record.addedNodes].some(
                (node) => node.nodeType === 1 && ((node as Element).id === "childattendancetable" || Boolean((node as Element).querySelector?.("#childattendancetable"))),
              )),
        ),
      );
      if (tableReplaced || tableMutated || !previousTable) {
        lastMutation = Date.now();
        listChanged = true;
      }
    });
    observer.observe(attendanceDocument.documentElement, { childList: true, subtree: true, attributes: true });
    try {
      await waitFor(
        "the attendance list to finish loading",
        () => listChanged && isPortalPage() && portalChildren().length > 0 && Date.now() - lastMutation >= 550,
        timeoutMs,
      );
    } finally {
      observer.disconnect();
    }
  }

  function setNativeInputValue(input: HTMLInputElement, value: string): void {
    const InputConstructor = input.ownerDocument.defaultView?.HTMLInputElement || HTMLInputElement;
    const descriptor = Object.getOwnPropertyDescriptor(InputConstructor.prototype, "value");
    descriptor?.set?.call(input, value);
  }

  function dispatchPortalEvent(input: HTMLInputElement, name: string): void {
    const EventConstructor = input.ownerDocument.defaultView?.Event || Event;
    input.dispatchEvent(new EventConstructor(name, { bubbles: true }));
  }

  function dispatchTime(input: HTMLInputElement, value: string): void {
    input.focus();
    setNativeInputValue(input, value);
    dispatchPortalEvent(input, "input");
    // The portal binds its AJAX persistence handler with jQuery .on('changeTime').
    // A native custom Event reaches that handler without reaching into page globals.
    dispatchPortalEvent(input, "changeTime");
    input.blur();
  }

  async function selectDate(isoDate: string, timeoutMs: number): Promise<void> {
    const input = portalDocument()?.querySelector<HTMLInputElement>("#pagedate");
    if (!input) throw new Error("Portal date control #pagedate is missing.");
    const desired = formatPortalDate(isoDate);
    if (text(input.value) === desired && portalChildren().length) return;

    await patch({ lastActionAt: timestamp(), current: { action: "select_date", date: isoDate } });
    const previousTable = portalDocument()?.querySelector("#childattendancetable") || null;
    setNativeInputValue(input, desired);
    dispatchPortalEvent(input, "input");
    dispatchPortalEvent(input, "change");
    await waitForDomStable(timeoutMs, previousTable);
    const actual = text(portalDocument()?.querySelector<HTMLInputElement>("#pagedate")?.value);
    if (actual !== desired) throw new Error(`Portal stayed on ${actual || "an unknown date"}; expected ${desired}.`);
    await log("info", `Loaded ${desired}`);
  }

  async function refreshCurrentAttendanceList(timeoutMs: number): Promise<void> {
    const input = portalDocument()?.querySelector<HTMLInputElement>("#pagedate");
    if (!input) throw new Error("Portal date control #pagedate is missing.");
    const expectedDate = text(input.value);
    const previousTable = portalDocument()?.querySelector("#childattendancetable") || null;
    dispatchPortalEvent(input, "change");
    await waitForDomStable(timeoutMs, previousTable);
    const actualDate = text(portalDocument()?.querySelector<HTMLInputElement>("#pagedate")?.value);
    if (actualDate !== expectedDate) {
      throw new HardSafetyError(`Portal date changed during refresh: found ${actualDate || "unknown"}; expected ${expectedDate}.`);
    }
  }

  async function selectDateWithRetries(
    isoDate: string,
    expectedGroupId: string,
    timeoutMs: number,
    retries: number,
  ): Promise<void> {
    let lastError: unknown;
    const savedAttempt = Math.max(0, Number((await state()).checkpoint?.attempt) || 0);
    if (savedAttempt > retries) lastError = new Error("The saved date-load retry budget is exhausted.");
    for (let attempt = savedAttempt; attempt <= retries; attempt += 1) {
      await ensureRunning();
      try {
        await patch({ checkpoint: { attempt: attempt + 1 } });
        await selectDate(isoDate, timeoutMs);
        assertVerifiedContext(isoDate, expectedGroupId);
        return;
      } catch (error) {
        if (isControlOrSafetyError(error)) throw error;
        lastError = error;
        if (attempt < retries) {
          await log("warn", `Date load retry ${attempt + 1}/${retries} for ${isoDate}.`, {
            error: error instanceof Error ? error.message : String(error),
          });
          await sleep(500);
        }
      }
    }
    const detail = lastError instanceof Error ? lastError.message : String(lastError);
    throw new HardSafetyError(`Could not verify portal date ${formatPortalDate(isoDate)} after ${retries + 1} attempts: ${detail}`);
  }

  async function runChildAction<T>(
    label: string,
    isoDate: string,
    expectedGroupId: string,
    timeoutMs: number,
    retries: number,
    action: () => Promise<T>,
  ): Promise<T> {
    let lastError: unknown;
    const savedAttempt = Math.max(0, Number((await state()).checkpoint?.attempt) || 0);
    if (savedAttempt > retries) lastError = new Error(`${label} exhausted its saved retry budget.`);
    for (let attempt = savedAttempt; attempt <= retries; attempt += 1) {
      await ensureRunning();
      assertVerifiedContext(isoDate, expectedGroupId);
      try {
        await patch({ checkpoint: { attempt: attempt + 1 } });
        return await action();
      } catch (error) {
        if (isControlOrSafetyError(error)) throw error;
        // A failed portal mutation is record-local only while the room and date
        // are still provably the intended target.
        assertVerifiedContext(isoDate, expectedGroupId);
        lastError = error;
        if (attempt < retries) {
          await log("warn", `${label} retry ${attempt + 1}/${retries}.`, {
            date: isoDate,
            error: error instanceof Error ? error.message : String(error),
          });
          await refreshCurrentAttendanceList(timeoutMs);
          assertVerifiedContext(isoDate, expectedGroupId);
          // Give any late AJAX response a chance to render. Each action then
          // reconciles the server-rendered DOM before issuing another write.
          await sleep(650);
        }
      }
    }
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }

  function mappingsLookup(mappings: unknown, record: PreparedRecord): string {
    if (Array.isArray(mappings)) {
      const entry = mappings.find((mapping: JsonObject) => {
        const key = text(mapping.sourceId ?? mapping.childId ?? mapping.sourceName ?? mapping.childName);
        return key === record.sourceId || normalizeName(key) === record.normalizedName;
      });
      return text(entry?.portalChildId ?? entry?.portalId ?? entry?.targetId ?? entry?.value);
    }
    if (mappings && typeof mappings === "object") {
      const object = mappings as JsonObject;
      const value = object[record.sourceId] ?? object[record.name] ?? object[record.normalizedName];
      return typeof value === "object"
        ? text(value?.portalChildId ?? value?.portalId ?? value?.targetId ?? value?.id)
        : text(value);
    }
    return "";
  }

  function resolveChild(record: PreparedRecord, mappings: unknown): PortalChild | null {
    const children = portalChildren();
    const explicitId = mappingsLookup(mappings, record);
    if (!explicitId) throw new Error(`${record.name} is not explicitly mapped to this portal room.`);
    return children.find((candidate) => candidate.id === explicitId) || null;
  }

  function scopeDatasetToRoom(days: PreparedDay[], mappings: unknown): { days: PreparedDay[]; skipped: number } {
    let skipped = 0;
    const scoped = days
      .map((day) => {
        const records = day.records.filter((record) => {
          const portalId = mappingsLookup(mappings, record);
          if (!portalId) {
            skipped += 1;
            return false;
          }
          return true;
        });
        return { ...day, records };
      });
    if (!scoped.some((day) => day.records.length > 0)) {
      throw new Error("No imported children are explicitly mapped to this portal room. Map at least one child before starting.");
    }
    return { days: scoped, skipped };
  }

  function consolidateMappedRecords(
    days: PreparedDay[],
    mappings: unknown,
  ): { days: PreparedDay[]; consolidatedRecords: number } {
    let consolidatedRecords = 0;
    const consolidatedDays = days.map((day) => {
      const byPortalChild = new Map<string, PreparedRecord>();
      for (const record of day.records) {
        const portalChildId = mappingsLookup(mappings, record);
        const existing = byPortalChild.get(portalChildId);
        if (!existing) {
          byPortalChild.set(portalChildId, { ...record, sessions: record.sessions.map((session) => ({ ...session })) });
          continue;
        }

        consolidatedRecords += 1;
        const uniqueSessions = new Map<string, SessionValue>();
        for (const session of [...existing.sessions, ...record.sessions]) {
          const key = `${minutesFromTime(session.start)}-${minutesFromTime(session.end)}`;
          if (!uniqueSessions.has(key)) uniqueSessions.set(key, { ...session });
        }
        const sessions = [...uniqueSessions.values()].sort(
          (left, right) => (minutesFromTime(left.start) || 0) - (minutesFromTime(right.start) || 0),
        );
        if (sessions.length > 2) {
          throw new Error(
            `${day.date} has more than two distinct sessions mapped to ${existing.name}. Fix the source rows before starting; no portal data was changed.`,
          );
        }
        for (let index = 1; index < sessions.length; index += 1) {
          if ((minutesFromTime(sessions[index].start) || 0) < (minutesFromTime(sessions[index - 1].end) || 0)) {
            throw new Error(
              `${day.date} has overlapping duplicate sessions mapped to ${existing.name}. Fix the source rows before starting; no portal data was changed.`,
            );
          }
        }
        existing.sessions = sessions;
      }
      return { ...day, records: [...byPortalChild.values()] };
    });
    return { days: consolidatedDays, consolidatedRecords };
  }

  function persistedSessions(childId: string): PortalChild["sessions"] {
    return portalChildren().find((child) => child.id === childId)?.sessions || [];
  }

  function childRowLoadedWithoutTimeId(childId: string, removedTimeId: string): boolean {
    const tbody = childTbody(childId);
    if (!tbody) return false;
    const startInputs = [...tbody.querySelectorAll<HTMLInputElement>('.attendancetime[data-input="starttime"]')];
    return startInputs.length > 0 && !startInputs.some((input) => text(input.dataset.timeid) === removedTimeId);
  }

  async function confirmDeletion(childId: string, childName: string, timeId: string, timeoutMs: number): Promise<void> {
    try {
      await waitFor(
        `deletion confirmation for ${childName}`,
        () => childRowLoadedWithoutTimeId(childId, timeId),
        timeoutMs,
      );
      return;
    } catch (initialError) {
      if (isControlOrSafetyError(initialError)) throw initialError;
      await log("warn", `Deletion confirmation was slow for ${childName}; refreshing the current date once before deciding.`, { timeId });
      try {
        await refreshCurrentAttendanceList(timeoutMs);
      } catch {
        throw initialError;
      }
      const refreshedChild = portalChildren().find((candidate) => candidate.id === childId);
      if (refreshedChild && !refreshedChild.sessions.some((session) => session.timeId === timeId)) return;
      throw initialError;
    }
  }

  function sessionsExactlyMatch(actual: PortalChild["sessions"], expected: SessionValue[]): boolean {
    return (
      actual.length === expected.length &&
      actual.every((session, index) =>
        session.timeId !== "0" &&
        timesEqual(session.start, expected[index].start) &&
        timesEqual(session.end, expected[index].end) &&
        Boolean(session.subtotal),
      )
    );
  }

  function sessionWithStart(childId: string, desiredStart: string): PortalChild["sessions"][number] | undefined {
    return persistedSessions(childId).find((session) => session.timeId !== "0" && timesEqual(session.start, desiredStart));
  }

  async function deleteAllExisting(child: PortalChild, childName: string, timeoutMs: number): Promise<void> {
    const existing = persistedSessions(child.id);
    if (!existing.length) return;

    const tbody = childTbody(child.id);
    const deleteButton = tbody?.querySelector<HTMLElement>('[onclick*="deleteDailyDetailAttendance"], span.delete');
    if (!deleteButton) throw new Error(`${childName} has existing attendance but its Delete control was not found.`);
    const timeId = text(
      deleteButton.closest("tr")?.querySelector<HTMLInputElement>('.attendancetime[data-input="starttime"]')?.dataset.timeid,
    );
    if (!timeId || timeId === "0") throw new Error(`${childName} has an unsafe or missing attendance record ID; cleanup stopped.`);
    await patch({
      lastActionAt: timestamp(),
      current: { action: "cleanup_delete", childId: child.id, childName, timeId },
    });
    await log("warn", `Cleanup: deleting existing attendance for ${childName}`, { timeId });
    deleteButton.click();
    await confirmDeletion(child.id, childName, timeId, timeoutMs);
    await deleteAllExisting(child, childName, timeoutMs);
  }

  function blankSessionInput(childId: string): HTMLInputElement | null {
    const tbody = childTbody(childId);
    if (!tbody) return null;
    return (
      [...tbody.querySelectorAll<HTMLInputElement>('.attendancetime[data-input="starttime"]')].find(
        (input) => text(input.dataset.timeid) === "0" && !text(input.value),
      ) || null
    );
  }

  async function ensureBlankSessionRow(childId: string, sessionIndex: number, timeoutMs: number): Promise<HTMLInputElement> {
    const existing = blankSessionInput(childId);
    if (existing) return existing;
    if (sessionIndex === 0 && persistedSessions(childId).length === 0) {
      throw new Error(`The blank attendance row for portal child ${childId} is missing.`);
    }
    const add = childTbody(childId)?.querySelector<HTMLElement>(".mbsc-ic-fa-plus-circle");
    if (!add) throw new Error(`The Add Session control for portal child ${childId} is missing.`);
    add.click();
    return waitFor(`a new session row for portal child ${childId}`, () => blankSessionInput(childId), timeoutMs);
  }

  async function saveStart(child: PortalChild, record: PreparedRecord, sessionIndex: number, timeoutMs: number): Promise<void> {
    const desired = record.sessions[sessionIndex];
    const already = sessionWithStart(child.id, desired.start);
    if (already) return;
    const input = await ensureBlankSessionRow(child.id, sessionIndex, timeoutMs);
    await patch({
      lastActionAt: timestamp(),
      current: { action: "save_in", childId: child.id, childName: record.name, session: sessionIndex + 1, value: desired.start },
    });
    dispatchTime(input, desired.start);
    await waitFor(
      `server confirmation of IN ${desired.start} for ${record.name}`,
      () => sessionWithStart(child.id, desired.start),
      timeoutMs,
    );
    await log("info", `Saved IN for ${record.name}`, { session: sessionIndex + 1, time: desired.start });
  }

  async function saveEnd(child: PortalChild, record: PreparedRecord, sessionIndex: number, timeoutMs: number): Promise<void> {
    const desired = record.sessions[sessionIndex];
    let persisted = sessionWithStart(child.id, desired.start);
    if (!persisted) throw new Error(`The saved IN record for ${record.name} disappeared before OUT could be saved.`);
    if (timesEqual(persisted.end, desired.end) && persisted.subtotal) return;

    const tbody = childTbody(child.id);
    const startInput = [...(tbody?.querySelectorAll<HTMLInputElement>('.attendancetime[data-input="starttime"]') || [])].find(
      (input) => text(input.dataset.timeid) === persisted!.timeId,
    );
    const row = startInput?.closest("tr");
    const endInput = row?.querySelector<HTMLInputElement>('.attendancetime[data-input="endtime"]');
    if (!endInput) throw new Error(`The OUT field for ${record.name} session ${sessionIndex + 1} is missing.`);

    await patch({
      lastActionAt: timestamp(),
      current: { action: "save_out", childId: child.id, childName: record.name, session: sessionIndex + 1, value: desired.end },
    });
    dispatchTime(endInput, desired.end);
    persisted = await waitFor(
      `server confirmation of OUT ${desired.end} for ${record.name}`,
      () => {
        const current = sessionWithStart(child.id, desired.start);
        return current && timesEqual(current.end, desired.end) && current.subtotal ? current : null;
      },
      timeoutMs,
    );

    // Button state is secondary because the historical page uses the same
    // classes for blank past rows. Record it for audit, but subtotal + time ID +
    // matching values are the authoritative server-rendered confirmation.
    const inButton = portalDocument()?.querySelector<HTMLElement>(`#inbutton${CSS.escape(child.id)}`);
    const outButton = portalDocument()?.querySelector<HTMLElement>(`#outbutton${CSS.escape(child.id)}`);
    await log("info", `Saved OUT for ${record.name}`, {
      session: sessionIndex + 1,
      time: desired.end,
      subtotal: persisted.subtotal,
      buttonState: { in: inButton?.className || "", out: outButton?.className || "" },
    });
  }

  function totalCounts(days: PreparedDay[], cleanupChildrenPerDate: number): JsonObject {
    return {
      totalDates: days.length,
      totalRecords: days.reduce((total, day) => total + day.records.length, 0),
      totalCleanupRecords: days.length * cleanupChildrenPerDate,
      totalSessions: days.reduce(
        (total, day) => total + day.records.reduce((dayTotal, record) => dayTotal + record.sessions.length, 0),
        0,
      ),
    };
  }

  async function advanceRecord(
    currentState: JsonObject,
    days: PreparedDay[],
    record: PreparedRecord,
    skipped = false,
    failed = false,
  ): Promise<void> {
    const checkpoint = currentState.checkpoint || {};
    const progress = currentState.progress || {};
    const day = days[Number(checkpoint.dateIndex) || 0];
    const nextRecord = (Number(checkpoint.recordIndex) || 0) + 1;
    if (nextRecord < day.records.length) {
      await patch({
        checkpoint: { ...checkpoint, recordIndex: nextRecord, sessionIndex: 0, phase: "delete_existing", attempt: 0 },
        progress: {
          ...progress,
          recordsCompleted: (Number(progress.recordsCompleted) || 0) + 1,
          sessionsCompleted: (Number(progress.sessionsCompleted) || 0) + (skipped || failed ? 0 : record.sessions.length),
          skippedRecords: (Number(progress.skippedRecords) || 0) + Number(skipped),
          failedRecords: (Number(progress.failedRecords) || 0) + Number(failed),
        },
      });
      return;
    }

    const nextDate = (Number(checkpoint.dateIndex) || 0) + 1;
    await patch({
      checkpoint: { ...checkpoint, dayStage: "cleanup", dateIndex: nextDate, cleanupIndex: 0, recordIndex: 0, sessionIndex: 0, phase: "select_date", attempt: 0 },
      progress: {
        ...progress,
        datesCompleted: (Number(progress.datesCompleted) || 0) + 1,
        recordsCompleted: (Number(progress.recordsCompleted) || 0) + 1,
        sessionsCompleted: (Number(progress.sessionsCompleted) || 0) + (skipped || failed ? 0 : record.sessions.length),
        skippedRecords: (Number(progress.skippedRecords) || 0) + Number(skipped),
        failedRecords: (Number(progress.failedRecords) || 0) + Number(failed),
      },
    });
  }

  async function completeDailyCleanup(currentState: JsonObject, countCurrentChild: boolean): Promise<void> {
    const checkpoint = currentState.checkpoint || {};
    const progress = currentState.progress || {};
    await patch({
      checkpoint: {
        ...checkpoint,
        dayStage: "entry",
        cleanupIndex: 0,
        recordIndex: 0,
        sessionIndex: 0,
        phase: "delete_existing",
        attempt: 0,
      },
      current: { action: "daily_cleanup_complete" },
      progress: {
        ...progress,
        cleanupDatesCompleted: (Number(progress.cleanupDatesCompleted) || 0) + 1,
        cleanupRecordsCompleted: (Number(progress.cleanupRecordsCompleted) || 0) + Number(countCurrentChild),
      },
    });
  }

  async function advanceDailyCleanup(currentState: JsonObject, visibleChildCount: number, failed = false): Promise<void> {
    const checkpoint = currentState.checkpoint || {};
    const progress = currentState.progress || {};
    const nextCleanupIndex = (Number(checkpoint.cleanupIndex) || 0) + 1;
    if (nextCleanupIndex < visibleChildCount) {
      await patch({
        checkpoint: { ...checkpoint, cleanupIndex: nextCleanupIndex, phase: "cleanup_existing", attempt: 0 },
        progress: {
          ...progress,
          cleanupRecordsCompleted: (Number(progress.cleanupRecordsCompleted) || 0) + 1,
          cleanupFailures: (Number(progress.cleanupFailures) || 0) + Number(failed),
        },
      });
      return;
    }
    if (failed) {
      await patch({ progress: { ...progress, cleanupFailures: (Number(progress.cleanupFailures) || 0) + 1 } });
      const refreshed = await state();
      await completeDailyCleanup(refreshed, true);
      return;
    }
    await completeDailyCleanup(currentState, true);
  }

  function showChip(status: string, detail = ""): void {
    if (!chip) {
      chip = document.createElement("div");
      chip.id = "caresync-attendance-status";
      Object.assign(chip.style, {
        position: "fixed",
        zIndex: "2147483647",
        top: "14px",
        right: "14px",
        maxWidth: "340px",
        padding: "10px 13px",
        borderRadius: "12px",
        boxShadow: "0 10px 30px rgba(15,23,42,.25)",
        color: "white",
        font: "600 12px/1.4 system-ui,-apple-system,sans-serif",
        pointerEvents: "none",
      });
      document.documentElement.appendChild(chip);
    }
    const colors: Record<string, string> = {
      running: "#0f766e",
      paused: "#b45309",
      completed: "#166534",
      error: "#b91c1c",
      stopped: "#475569",
      connected: "#334155",
    };
    chip.style.background = colors[status] || "#334155";
    chip.textContent = `CareSync · ${status}${detail ? ` — ${detail}` : ""}`;
  }

  async function runEngine(): Promise<void> {
    const initial = await ensureRunning();
    if (!(await waitForPortalPage(15_000))) {
      if (looksLikeLoginPage()) {
        throw new HardSafetyError("The KinderLogix session is signed out. Sign in and return to the attendance room before resuming.");
      }
      if (!location.pathname.toLowerCase().includes("content.php")) {
        throw new HardSafetyError("The connected tab is no longer on the KinderLogix attendance page.");
      }
      throw new PortalNotReadyError("The attendance room is still loading.");
    }
    if (initial.runDatasetId && initial.dataset?.id && initial.runDatasetId !== initial.dataset.id) {
      throw new Error("The imported dataset changed after this checkpoint was created. Start a new run instead of resuming.");
    }
    const runMappings = initial.runMappings || initial.mappings;
    const expectedGroupId = text(initial.runPageGroupId);
    if (!expectedGroupId) throw new HardSafetyError("The run has no verified room ID. Start a new run from the intended room.");
    const prepared = prepareDataset(initial.dataset);
    const scoped = scopeDatasetToRoom(prepared, runMappings);
    const consolidated = consolidateMappedRecords(scoped.days, runMappings);
    const days = consolidated.days;
    const totals = totalCounts(days, portalChildren().length);
    const scopeAlreadyLogged = Array.isArray(initial.logs)
      ? initial.logs.some((entry: JsonObject) => entry.details?.runId === initial.runId && entry.details?.kind === "room_scope")
      : false;
    const roundedValues = prepared.reduce(
      (total, day) =>
        total +
        day.records.reduce(
          (recordTotal, record) =>
            recordTotal +
            record.sessions.reduce(
              (sessionTotal, session) =>
                sessionTotal +
                Number(!timesEqual(session.sourceStart, session.start)) +
                Number(!timesEqual(session.sourceEnd, session.end)),
              0,
            ),
          0,
        ),
      0,
    );
    const roundingAlreadyLogged = Array.isArray(initial.logs)
      ? initial.logs.some((entry: JsonObject) => entry.details?.runId === initial.runId && entry.details?.kind === "time_rounding")
      : false;
    if (roundedValues > 0 && !roundingAlreadyLogged) {
      await log(
        "warn",
        `Rounded ${roundedValues} IN/OUT value${roundedValues === 1 ? "" : "s"} to the portal's five-minute grid.`,
        { runId: initial.runId, kind: "time_rounding", roundedValues },
      );
    }
    if (scoped.skipped > 0 && !scopeAlreadyLogged) {
      await log(
        "info",
        `Skipped ${scoped.skipped} out-of-room attendance record${scoped.skipped === 1 ? "" : "s"}.`,
        { runId: initial.runId, kind: "room_scope", skipped: scoped.skipped },
      );
    }
    const consolidationAlreadyLogged = Array.isArray(initial.logs)
      ? initial.logs.some((entry: JsonObject) => entry.details?.runId === initial.runId && entry.details?.kind === "record_consolidation")
      : false;
    if (consolidated.consolidatedRecords > 0 && !consolidationAlreadyLogged) {
      await log(
        "warn",
        `Consolidated ${consolidated.consolidatedRecords} duplicate mapped date-child record${consolidated.consolidatedRecords === 1 ? "" : "s"} before portal entry.`,
        { runId: initial.runId, kind: "record_consolidation", count: consolidated.consolidatedRecords },
      );
    }
    await patch({ portal: scanPortal(), progress: { ...(initial.progress || {}), ...totals } });

    while (true) {
      const currentState = await ensureRunning();
      const checkpoint = currentState.checkpoint || {};
      if (Number(checkpoint.engineVersion) !== 6) {
        await patch({
          checkpoint: {
            engineVersion: 6,
            stage: "daily",
            dayStage: "cleanup",
            dateIndex: 0,
            cleanupIndex: 0,
            cleanupChildIds: [],
            recordIndex: 0,
            sessionIndex: 0,
            phase: "select_date",
            attempt: 0,
          },
          progress: {
            ...totals,
            cleanupDatesCompleted: 0,
            cleanupRecordsCompleted: 0,
            cleanupFailures: 0,
            datesCompleted: 0,
            recordsCompleted: 0,
            sessionsCompleted: 0,
            skippedRecords: 0,
            failedRecords: 0,
          },
          current: { action: "engine_v6_upgrade_restart" },
        });
        await log(
          "warn",
          "Upgraded the saved run to the non-destructive V6 engine and restarted it from the first date so every record is rebuilt safely.",
          { runId: initial.runId, kind: "engine_v6_upgrade_restart" },
        );
        continue;
      }
      const stage = text(checkpoint.stage) || "entry";
      if (stage !== "daily") {
        const migratingCleanup = stage === "cleanup";
        await patch({
          checkpoint: {
            ...checkpoint,
            stage: "daily",
            dayStage: migratingCleanup ? "cleanup" : "entry",
            dateIndex: migratingCleanup ? 0 : Number(checkpoint.dateIndex) || 0,
            cleanupIndex: 0,
            recordIndex: migratingCleanup ? 0 : Number(checkpoint.recordIndex) || 0,
            phase: migratingCleanup ? "select_date" : text(checkpoint.phase) || "select_date",
          },
          current: { action: "checkpoint_migrated_to_daily_pipeline" },
        });
        await log("info", "Migrated the saved run to the date-by-date cleanup and entry pipeline.");
        continue;
      }
      const dayStage = text(checkpoint.dayStage) || (text(checkpoint.phase) === "cleanup_existing" ? "cleanup" : "entry");
      const dateIndex = Number(checkpoint.dateIndex) || 0;
      if (dateIndex >= days.length) {
        const skippedRecords = Number(currentState.progress?.skippedRecords) || 0;
        const failedRecords = Number(currentState.progress?.failedRecords) || 0;
        const cleanupFailures = Number(currentState.progress?.cleanupFailures) || 0;
        const issues = skippedRecords + failedRecords + cleanupFailures;
        await patch({ status: "completed", completedAt: timestamp(), current: undefined });
        await log(
          issues > 0 ? "warn" : "info",
          issues > 0
            ? `Attendance run completed with issues: ${skippedRecords} unavailable, ${failedRecords} entry failure${failedRecords === 1 ? "" : "s"}, and ${cleanupFailures} cleanup failure${cleanupFailures === 1 ? "" : "s"}.`
            : "Attendance run completed",
          { ...totals, skippedRecords, failedRecords, cleanupFailures },
        );
        showChip("completed", issues > 0 ? `${issues} recorded issue${issues === 1 ? "" : "s"}; review log` : `${totals.totalRecords} children verified`);
        return;
      }

      const day = days[dateIndex];
      const recordIndex = Number(checkpoint.recordIndex) || 0;
      const timeoutMs = Math.max(5_000, Math.min(60_000, Number(currentState.settings?.timeoutMs) || 20_000));
      const retries = retryLimit(currentState.settings?.retryLimit);
      const phase = text(checkpoint.phase) || "select_date";

      const activeGroupId = text(portalDocument()?.querySelector<HTMLInputElement>("#pagegroupid")?.value);
      if (activeGroupId !== expectedGroupId) {
        throw new HardSafetyError(`The portal room changed from ${expectedGroupId} to ${activeGroupId || "unknown"}. Return to the mapped room before resuming.`);
      }

      if (phase === "select_date") {
        await selectDateWithRetries(day.date, expectedGroupId, timeoutMs, retries);
        const loadedChildren = portalChildren();
        const cleanupChildIds = loadedChildren.map((candidate) => candidate.id);
        await patch({
          checkpoint: {
            ...checkpoint,
            phase: dayStage === "cleanup" ? "cleanup_existing" : "delete_existing",
            ...(dayStage === "cleanup" ? { cleanupChildIds } : {}),
            attempt: 0,
          },
          portal: scanPortal(),
          ...(dayStage === "cleanup"
            ? {
                progress: {
                  ...(currentState.progress || {}),
                  totalCleanupRecords: Math.max(
                    Number(currentState.progress?.totalCleanupRecords) || 0,
                    days.length * loadedChildren.length,
                  ),
                },
              }
            : {}),
        });
        continue;
      }

      if (text(portalDocument()?.querySelector<HTMLInputElement>("#pagedate")?.value) !== formatPortalDate(day.date)) {
        await selectDateWithRetries(day.date, expectedGroupId, timeoutMs, retries);
      }
      assertVerifiedContext(day.date, expectedGroupId);

      if (dayStage === "cleanup") {
        const visibleChildren = portalChildren();
        const cleanupChildIds = Array.isArray(checkpoint.cleanupChildIds)
          ? checkpoint.cleanupChildIds.map(text).filter(Boolean)
          : visibleChildren.map((candidate) => candidate.id);
        const cleanupIndex = Number(checkpoint.cleanupIndex) || 0;
        if (cleanupIndex >= cleanupChildIds.length) {
          await completeDailyCleanup(currentState, false);
          continue;
        }
        const cleanupChild = visibleChildren.find((candidate) => candidate.id === cleanupChildIds[cleanupIndex]);
        if (!cleanupChild) {
          await log("warn", `Cleanup child ${cleanupChildIds[cleanupIndex]} is no longer visible on ${day.date}; continuing.`, {
            date: day.date,
            portalChildId: cleanupChildIds[cleanupIndex],
            kind: "cleanup_child_not_visible",
          });
          await advanceDailyCleanup(currentState, cleanupChildIds.length, true);
          continue;
        }
        showChip("running", `cleanup all · ${day.date} · ${cleanupChild.name}`);
        try {
          await runChildAction(
            `Cleanup for ${cleanupChild.name}`,
            day.date,
            expectedGroupId,
            timeoutMs,
            retries,
            () => deleteAllExisting(cleanupChild, cleanupChild.name, timeoutMs),
          );
          await advanceDailyCleanup(currentState, cleanupChildIds.length);
        } catch (error) {
          if (isControlOrSafetyError(error)) throw error;
          const message = error instanceof Error ? error.message : String(error);
          await log("error", `Cleanup failed for ${cleanupChild.name} on ${day.date}; continuing to the next child.`, {
            date: day.date,
            portalChildId: cleanupChild.id,
            error: message,
            kind: "cleanup_child_failed",
          });
          await advanceDailyCleanup(currentState, cleanupChildIds.length, true);
        }
        continue;
      }

      if (recordIndex >= day.records.length) {
        await patch({
          checkpoint: {
            ...checkpoint,
            dayStage: "cleanup",
            dateIndex: dateIndex + 1,
            cleanupIndex: 0,
            cleanupChildIds: [],
            recordIndex: 0,
            sessionIndex: 0,
            phase: "select_date",
            attempt: 0,
          },
        });
        continue;
      }

      const record = day.records[recordIndex];
      showChip("running", `entry · ${day.date} · ${record.name} · ${phase.replaceAll("_", " ")}`);
      let child: PortalChild | null;
      try {
        child = resolveChild(record, runMappings);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        await log("error", `Could not resolve ${record.name} on ${day.date}; continuing.`, {
          date: day.date,
          sourceChildId: record.sourceId,
          error: message,
          kind: "child_resolution_failed",
        });
        await advanceRecord(currentState, days, record, false, true);
        continue;
      }
      if (!child) {
        const portalChildId = mappingsLookup(runMappings, record);
        await log("warn", `Skipped ${record.name} on ${day.date}: mapped portal child ${portalChildId} is not visible on this date. Continuing the run.`, {
          date: day.date,
          sourceChildId: record.sourceId,
          portalChildId,
          kind: "child_not_visible_on_date",
        });
        showChip("running", `skipped ${record.name} on ${day.date}; continuing`);
        await advanceRecord(currentState, days, record, true);
        continue;
      }

      const sessionIndex = Number(checkpoint.sessionIndex) || 0;
      const preserveFailureAndAdvance = async (error: unknown): Promise<void> => {
        if (isControlOrSafetyError(error)) throw error;
        const message = error instanceof Error ? error.message : String(error);
        await log("error", `Attendance could not be verified for ${record.name} on ${day.date}; existing portal data was preserved.`, {
          date: day.date,
          sourceChildId: record.sourceId,
          portalChildId: child!.id,
          phase,
          error: message,
          kind: "entry_record_failed_preserved",
        });
        const latest = await state();
        await advanceRecord(latest, days, record, false, true);
      };

      // Page-wide cleanup is the only destructive stage. Once entry begins,
      // existing data belongs either to this run or to a state requiring human
      // review, so it is never deleted automatically.
      if (phase === "delete_existing") {
        const existing = persistedSessions(child.id);
        if (existing.length && sessionsExactlyMatch(existing, record.sessions)) {
          await log("info", `Verified already-entered attendance for ${record.name}; no deletion was performed.`, {
            date: day.date,
            portalChildId: child.id,
            kind: "entry_already_complete",
          });
          await advanceRecord(currentState, days, record);
          continue;
        }
        if (existing.length) {
          await preserveFailureAndAdvance(
            new Error(`Unexpected existing or partial attendance remained after cleanup for ${record.name}.`),
          );
          continue;
        }
        await patch({ checkpoint: { ...checkpoint, sessionIndex: 0, phase: "save_start", attempt: 0 } });
        continue;
      }

      if (sessionIndex >= record.sessions.length && phase !== "record_complete") {
        await patch({ checkpoint: { ...checkpoint, phase: "record_complete", attempt: 0 } });
        continue;
      }

      if (phase === "save_start") {
        try {
          await runChildAction(`Save IN for ${record.name}`, day.date, expectedGroupId, timeoutMs, retries, () =>
            saveStart(child!, record, sessionIndex, timeoutMs),
          );
        } catch (error) {
          await preserveFailureAndAdvance(error);
          continue;
        }
        await patch({ checkpoint: { ...checkpoint, phase: "save_end", attempt: 0 } });
        continue;
      }

      if (phase === "save_end") {
        try {
          await runChildAction(`Save OUT for ${record.name}`, day.date, expectedGroupId, timeoutMs, retries, () =>
            saveEnd(child!, record, sessionIndex, timeoutMs),
          );
        } catch (error) {
          await preserveFailureAndAdvance(error);
          continue;
        }
        await patch({
          checkpoint: {
            ...checkpoint,
            sessionIndex: sessionIndex + 1,
            phase: sessionIndex + 1 < record.sessions.length ? "save_start" : "record_complete",
            attempt: 0,
          },
        });
        continue;
      }

      if (phase === "record_complete") {
        try {
          await runChildAction(`Final verification for ${record.name}`, day.date, expectedGroupId, timeoutMs, retries, async () => {
            const actual = persistedSessions(child!.id);
            if (!sessionsExactlyMatch(actual, record.sessions)) {
              throw new Error(`Final verification failed for ${record.name}.`);
            }
          });
        } catch (error) {
          await preserveFailureAndAdvance(error);
          continue;
        }
        // Keep checkpoint persistence outside the verification catch: if the
        // extension state write fails after successful verification, the row
        // remains intact and Resume simply verifies it again.
        await advanceRecord(currentState, days, record);
        continue;
      }

      await log("warn", `Reset unknown checkpoint phase ${phase} for ${record.name}.`, { date: day.date, phase });
      await patch({ checkpoint: { ...checkpoint, sessionIndex: 0, phase: "delete_existing", attempt: 0 } });
    }
  }

  function wakeEngine(): void {
    if (enginePromise) return;
    if (scheduledWake !== null) {
      window.clearTimeout(scheduledWake);
      scheduledWake = null;
    }
    let retryWhenPortalReady = false;
    enginePromise = runEngine()
      .catch(async (error) => {
        if (error instanceof PausedError) {
          showChip("paused", "checkpoint saved");
          return;
        }
        if (error instanceof StoppedError) {
          showChip(error.message, "checkpoint preserved");
          return;
        }
        if (error instanceof PortalNotReadyError) {
          retryWhenPortalReady = true;
          showChip("running", "waiting for attendance room to finish loading");
          return;
        }
        const message = error instanceof Error ? error.message : String(error);
        try {
          const current = await state();
          await patch({ status: "error", error: message, lastActionAt: timestamp() });
          await log("error", message, current.checkpoint);
        } catch {
          // The extension may be reloading; the last pre-action checkpoint is
          // already durable and will remain available for Resume.
        }
        showChip("error", message);
      })
      .finally(() => {
        enginePromise = null;
        if (retryWhenPortalReady && scheduledWake === null) {
          scheduledWake = window.setTimeout(() => {
            scheduledWake = null;
            wakeEngine();
          }, 2_000);
        }
      });
  }

  chrome.runtime.onMessage.addListener((message: JsonObject, _sender, sendResponse) => {
    const type = String(message?.type || "").toUpperCase();
    if (type === "SCAN_PORTAL" || type === "SCAN") {
      void waitForPortalPage()
        .then(() => sendResponse({ ok: true, portal: scanPortal() }))
        .catch((error) => sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : String(error),
          portal: scanPortal(),
        }));
      return true;
    }
    if (type === "ENGINE_WAKE" || type === "CONTENT_RUN" || type === "RESUME") {
      wakeEngine();
      sendResponse({ ok: true });
      return false;
    }
    if (type === "ENGINE_PAUSE") {
      showChip("paused", "checkpoint saved");
      sendResponse({ ok: true });
      return false;
    }
    if (type === "ENGINE_STOP") {
      showChip("stopped", "checkpoint preserved");
      sendResponse({ ok: true });
      return false;
    }
    return false;
  });

  void runtimeMessage({ type: "CONTENT_READY", portal: scanPortal() })
    .then((response) => {
      const current = response.state;
      showChip(current.status || "connected", current.status === "running" ? "resuming checkpoint" : "ready");
      if (current.status === "running") wakeEngine();
    })
    .catch(() => {
      // Registered scripts can run on same-origin non-attendance pages. Stay
      // inert there and never mutate anything unless this exact tab owns a run.
      if (isPortalPage()) showChip("connected", "open extension to connect");
    });
})();
