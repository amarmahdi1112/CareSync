import {
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  RectangleGroupIcon,
  ShieldExclamationIcon,
  UserGroupIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link } from "react-router-dom";
import styled from "styled-components";
import {
  useRealtimeRefresh,
  useRealtimeState,
} from "../../realtime/RealtimeContext";
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  IconButton,
  StatusChip,
} from "../../components/ui/Primitives";
import {
  acknowledgeRoomOperationalException,
  fetchLiveRoomSafetyBoard,
  fetchRoomExceptionActionTarget,
  fetchRoomOperationalExceptions,
  type LiveRoomOverallState,
  type LiveRoomSafetyBoard,
  type LiveRoomSafetyCapability,
  type RoomExceptionActionTarget,
  type RoomExceptionFilter,
  type RoomOperationalException,
  LIVE_ROOM_SAFETY_STANDING_BOUNDARY,
} from "./roomSafetyApi";
import {
  clearPendingRoomExceptionAcknowledgement,
  executeProtectedRoomExceptionAcknowledgement,
  listPendingRoomExceptionAcknowledgements,
  readPendingRoomExceptionAcknowledgement,
  readVolatileRoomExceptionAcknowledgementReason,
  RoomSafetyOperationOutcomeUnknownError,
  RoomSafetyOperationPendingError,
} from "./roomSafetyOperation";
import type { RoomRecord } from "./roomsApi";

const Shell = styled.section`
  display: grid;
  gap: 16px;
`;
const ControlBar = styled(GlassPanel)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  > div:first-child {
    min-width: 0;
  }
  h2 {
    margin: 6px 0 3px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.35rem;
    font-weight: 560;
    letter-spacing: -0.035em;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.74rem;
    line-height: 1.55;
  }
  @media (max-width: 720px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const ControlActions = styled.div`
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  @media (max-width: 720px) {
    justify-content: flex-start;
  }
`;
const Boundary = styled.div<{ $warning?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid
    ${({ $warning, theme }) =>
      $warning ? theme.color.amber : theme.color.borderStrong};
  border-radius: 12px 5px 12px 5px;
  color: ${({ $warning, theme }) =>
    $warning ? theme.color.amber : theme.color.textSoft};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: 0.73rem;
  line-height: 1.55;
  svg {
    width: 19px;
    flex: 0 0 auto;
  }
`;
const MetricGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  @media (max-width: 1060px) {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  @media (max-width: 640px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
`;
const Metric = styled(GlassPanel)`
  padding: 15px;
  span {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.67rem;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    margin-top: 9px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.65rem;
    font-weight: 560;
  }
  small {
    display: block;
    margin-top: 3px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.68rem;
    line-height: 1.4;
  }
`;
const RoomGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 1060px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  @media (max-width: 660px) {
    grid-template-columns: 1fr;
  }
`;
const RoomCard = styled(GlassPanel)<{ $attention: boolean; $unknown: boolean }>`
  display: grid;
  gap: 13px;
  padding: 17px;
  border-color: ${({ $attention, $unknown, theme }) =>
    $attention
      ? theme.color.amber
      : $unknown
        ? theme.color.borderStrong
        : theme.color.border};
  h3 {
    margin: 0;
    font-size: 0.94rem;
    font-weight: 620;
  }
`;
const CardTop = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
`;
const FactGrid = styled.dl`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
  margin: 0;
  div {
    padding: 10px;
    border: 1px solid ${({ theme }) => theme.color.border};
    border-radius: 9px;
    background: ${({ theme }) => theme.color.surfaceStrong};
  }
  dt {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
    line-height: 1.35;
  }
  dd {
    margin: 5px 0 0;
    font-size: 1rem;
    font-weight: 620;
  }
`;
const CardActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  a,
  button {
    min-height: 40px;
    padding: 0 11px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 9px 4px 9px 4px;
    color: ${({ theme }) => theme.color.textSoft};
    background: ${({ theme }) => theme.color.control};
    cursor: pointer;
    font: inherit;
    font-size: 0.72rem;
    text-decoration: none;
  }
`;
const ExceptionSection = styled(GlassPanel)`
  display: grid;
  gap: 14px;
  padding: 18px;
`;
const SectionTop = styled.div`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.2rem;
    font-weight: 560;
  }
  p {
    margin: 4px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
  }
  select {
    min-height: 42px;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 9px;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: 0.73rem;
  }
  @media (max-width: 600px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const ExceptionList = styled.div`
  display: grid;
  gap: 9px;
`;
const ExceptionButton = styled.button<{ $selected: boolean }>`
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  width: 100%;
  padding: 13px;
  border: 1px solid
    ${({ $selected, theme }) =>
      $selected ? theme.color.cyan : theme.color.border};
  border-radius: 11px 5px 11px 5px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ $selected, theme }) =>
    $selected ? theme.color.surfaceHover : theme.color.surfaceStrong};
  cursor: pointer;
  text-align: left;
  strong {
    display: block;
    font-size: 0.79rem;
  }
  small {
    display: block;
    margin-top: 4px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.69rem;
    line-height: 1.45;
  }
`;
const Detail = styled.section`
  display: grid;
  gap: 13px;
  padding: 16px;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 12px 5px 12px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  h3 {
    margin: 0;
    font-size: 1rem;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.74rem;
    line-height: 1.6;
  }
`;
const DetailFacts = styled.dl`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  div {
    padding: 10px;
    border: 1px solid ${({ theme }) => theme.color.border};
    border-radius: 8px;
  }
  dt {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
  }
  dd {
    margin: 5px 0 0;
    font-size: 0.76rem;
  }
  @media (max-width: 680px) {
    grid-template-columns: 1fr;
  }
`;
const Empty = styled.div`
  padding: 28px 18px;
  border: 1px dashed ${({ theme }) => theme.color.border};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.75rem;
  text-align: center;
`;
const DialogOverlay = styled.div`
  position: fixed;
  inset: 0;
  z-index: 900;
  display: grid;
  place-items: center;
  padding: max(18px, env(safe-area-inset-top)) 18px
    max(18px, env(safe-area-inset-bottom));
  overflow-y: auto;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});
`;
const Dialog = styled(GlassPanel)`
  width: min(620px, 100%);
  max-height: calc(100dvh - 36px);
  padding: 20px;
  overflow-y: auto;
`;
const DialogHead = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  h2 {
    margin: 5px 0 3px;
    font-size: 1.2rem;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
  }
`;
const AcknowledgeForm = styled.form`
  display: grid;
  gap: 13px;
  margin-top: 16px;
  label {
    display: grid;
    gap: 6px;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.72rem;
  }
  textarea {
    min-height: 118px;
    padding: 11px;
    resize: vertical;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 10px;
    outline: none;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: 0.75rem;
    line-height: 1.5;
  }
  textarea:focus {
    border-color: ${({ theme }) => theme.color.cyan};
  }
  footer {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
  }
`;
const InlineError = styled.div`
  padding: 11px 12px;
  border: 1px solid ${({ theme }) => theme.color.amber};
  border-radius: 9px;
  color: ${({ theme }) => theme.color.amber};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: 0.72rem;
  line-height: 1.5;
`;

const ROOM_SAFETY_REALTIME_ENTITIES = [
  "attendance_day",
  "staff_shift",
  "staff_schedule",
  "staff_coverage_target",
  "organization_membership",
  "facility",
  "room",
  "staff_room_presence",
  "room_operational_exception",
] as const;

const conditionCopy = {
  confirmed_children_above_configured_room_capacity: {
    title: "Confirmed children above configured room capacity",
    owner: "Review attendance facts here and room configuration in Rooms.",
    correction: "rooms",
  },
  confirmed_staff_below_configured_room_target: {
    title: "Confirmed room staff below configured operational target",
    owner: "Review current room presence here and configured targets in Staff rota.",
    correction: "staff-rota",
  },
  open_shift_staff_without_current_room: {
    title: "On-duty staff not currently located in a room",
    owner: "Review the actual shift and ask the staff member to choose their current room.",
    correction: "staff",
  },
  present_child_without_active_room: {
    title: "Confirmed child presence has no active room",
    owner: "Review the attendance record and active room assignment.",
    correction: "attendance",
  },
  source_integrity_unknown: {
    title: "Live room source facts need review",
    owner: "Refresh canonical records and review the listed source reason codes.",
    correction: "rooms",
  },
} as const;

function exceptionConditionCopy(exception: RoomOperationalException) {
  if (
    exception.condition_code ===
      "confirmed_staff_below_configured_room_target" &&
    exception.scope_kind === "facility"
  )
    return {
      title:
        "Confirmed facility staff below configured operational target",
      owner:
        "This compares open actual-shift staff with the facility-wide configured operational target, not room allocation. Review configured targets in Staff rota.",
      correction: "staff-rota",
    } as const;
  return conditionCopy[exception.condition_code];
}

function stateLabel(state: LiveRoomOverallState, stale: boolean): string {
  if (stale) return "Stale — refresh required";
  if (state === "attention") return "Current signal needs review";
  if (state === "unknown") return "Current result is unknown";
  if (state === "not_evaluated") return "No configured target is active";
  return "No current configured-target signal";
}

function stateTone(
  state: LiveRoomOverallState,
  stale: boolean,
): "success" | "warning" | "info" | "neutral" {
  if (stale || state === "unknown") return "neutral";
  if (state === "attention") return "warning";
  if (state === "not_evaluated") return "info";
  return "success";
}

function formatCount(value: number | null): string {
  return value === null ? "—" : String(value);
}

function formatReason(code: string): string {
  return code.replaceAll("_", " ");
}

function correctionPath(exception: RoomOperationalException): string {
  const correction = exceptionConditionCopy(exception).correction;
  if (correction === "staff-rota") return "/staff-rota";
  if (correction === "staff") return "/staff";
  if (correction === "attendance") return "/attendance";
  return "/rooms";
}

function reconcileCanonicallyConfirmedAcknowledgements(
  scope: { organizationId: string; actorUserId: string },
  items: RoomOperationalException[],
): number {
  const currentById = new Map(items.map((item) => [item.id, item]));
  let cleared = 0;
  for (const pending of listPendingRoomExceptionAcknowledgements(scope)) {
    const current = currentById.get(pending.exception_id);
    if (
      !current ||
      !current.acknowledged_at ||
      current.acknowledged_by_user_id !==
        pending.actor_user_id ||
      current.version <= pending.expected_version ||
      Date.parse(current.acknowledged_at) <
        Date.parse(pending.created_at)
    )
      continue;
    clearPendingRoomExceptionAcknowledgement(
      scope,
      pending.exception_id,
      pending.client_operation_id,
    );
    cleared += 1;
  }
  return cleared;
}

function AcknowledgementDialog({
  exception,
  scope,
  stale,
  onClose,
  onConfirmed,
}: {
  exception: RoomOperationalException;
  scope: { organizationId: string; actorUserId: string };
  stale: boolean;
  onClose: () => void;
  onConfirmed: () => Promise<void>;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [pending, setPending] = useState(() =>
    readPendingRoomExceptionAcknowledgement(scope, exception.id),
  );
  const recoveredProtectedReason = pending
    ? readVolatileRoomExceptionAcknowledgementReason(scope, pending)
    : null;
  const [reason, setReason] = useState(() =>
    pending
      ? recoveredProtectedReason ?? ""
      : exception.acknowledgement_reason ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retryProtected, setRetryProtected] = useState(
    Boolean(pending),
  );
  const [confirmNewReview, setConfirmNewReview] = useState(false);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [
        ...dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", keyboard);
    requestAnimationFrame(() => dialogRef.current?.querySelector("textarea")?.focus());
    return () => {
      window.removeEventListener("keydown", keyboard);
      document.body.style.overflow = previousOverflow;
      previous?.focus();
    };
  }, [busy, onClose]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (stale) {
      setError("Refresh the canonical live board before acknowledging this signal.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await executeProtectedRoomExceptionAcknowledgement({
        scope,
        exception,
        reason,
        send: (operationId, expectedVersion, normalizedReason) =>
          acknowledgeRoomOperationalException({
            organizationId: scope.organizationId,
            actorUserId: scope.actorUserId,
            exception,
            request: {
              client_operation_id: operationId,
              expected_version: expectedVersion,
              reason: normalizedReason,
            },
          }),
      });
      await onConfirmed();
      onClose();
    } catch (caught) {
      const protectedRetry =
        caught instanceof RoomSafetyOperationOutcomeUnknownError ||
        caught instanceof RoomSafetyOperationPendingError;
      if (
        caught instanceof RoomSafetyOperationOutcomeUnknownError ||
        caught instanceof RoomSafetyOperationPendingError
      )
        setPending(caught.pending);
      setRetryProtected(protectedRetry);
      setError(
        caught instanceof Error
          ? caught.message
          : "The acknowledgement could not be confirmed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const startNewReviewedAction = () => {
    if (!pending || recoveredProtectedReason || stale || busy) return;
    if (!confirmNewReview) {
      setConfirmNewReview(true);
      setError("");
      return;
    }
    clearPendingRoomExceptionAcknowledgement(
      scope,
      exception.id,
      pending.client_operation_id,
    );
    setPending(null);
    setRetryProtected(false);
    setConfirmNewReview(false);
    setReason("");
    setError("");
  };

  return (
    <DialogOverlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <Dialog
        ref={dialogRef}
        $accent="amber"
        role="dialog"
        aria-modal="true"
        aria-labelledby="room-ack-title"
        aria-describedby="room-ack-description"
      >
        <DialogHead>
          <div>
            <Eyebrow>
              <ShieldExclamationIcon width={14} /> Human review evidence
            </Eyebrow>
            <h2 id="room-ack-title">Acknowledge this operational signal</h2>
            <p id="room-ack-description">
              Acknowledgement records that a manager is reviewing the signal.
              It does not resolve, approve, waive, or certify the underlying
              condition.
            </p>
          </div>
          <IconButton
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close acknowledgement"
          >
            <XMarkIcon />
          </IconButton>
        </DialogHead>
        <AcknowledgeForm onSubmit={submit}>
          <Boundary $warning>
            <InformationCircleIcon />
            <span>
              Version {exception.version} is protected. If the source facts
              change first, the server rejects this review instead of
              overwriting another operator.
            </span>
          </Boundary>
          <label>
            Review note
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={busy}
              minLength={5}
              maxLength={500}
              required
              placeholder="Coverage call is in progress; manager is monitoring the room"
            />
          </label>
          {retryProtected && (
            <Boundary $warning role="status">
              <ClockIcon />
              <span>
                {recoveredProtectedReason
                  ? "The exact operation and its in-memory reason are protected. Retry without changing the reason; CareSync will not create a second decision."
                  : "The redacted operation proof is protected, but its prior free-text reason is no longer available in memory. Refresh canonical truth before trying to reconstruct the exact reason; CareSync will not send a changed decision."}
              </span>
            </Boundary>
          )}
          {pending && !recoveredProtectedReason && (
            <Boundary $warning role="alert">
              <ExclamationTriangleIcon />
              <span>
                A prior response was interrupted and its private review note
                was intentionally not stored. This action stays locked. After
                canonical refresh confirms this episode is still open, you may
                explicitly release the redacted draft and begin a new reviewed
                action; CareSync will never guess or reconstruct the old note.
              </span>
            </Boundary>
          )}
          {error && <InlineError role="alert">{error}</InlineError>}
          <footer>
            <ActionButton type="button" onClick={onClose} disabled={busy}>
              Cancel
            </ActionButton>
            {pending && !recoveredProtectedReason && (
              <ActionButton
                type="button"
                onClick={startNewReviewedAction}
                disabled={busy || stale || exception.state !== "open"}
              >
                {confirmNewReview
                  ? "Confirm new reviewed action"
                  : "Start a new reviewed action"}
              </ActionButton>
            )}
            <ActionButton
              type="submit"
              $variant="primary"
              disabled={
                busy ||
                stale ||
                reason.trim().length < 5 ||
                Boolean(pending && !recoveredProtectedReason)
              }
            >
              {busy
                ? "Confirming exact receipt…"
                : retryProtected
                  ? "Retry exact acknowledgement"
                  : "Record acknowledgement"}
            </ActionButton>
          </footer>
        </AcknowledgeForm>
      </Dialog>
    </DialogOverlay>
  );
}

export default function RoomSafetyLiveWorkspace({
  organizationId,
  actorUserId,
  facilityId,
  facilityTimezone,
  rooms,
  capability,
  requestedExceptionId,
  requestedRoomId,
  onOpenRoster,
  onActionTarget,
}: {
  organizationId: string;
  actorUserId: string;
  facilityId: string;
  facilityTimezone: string;
  rooms: RoomRecord[];
  capability: LiveRoomSafetyCapability;
  requestedExceptionId?: string;
  requestedRoomId?: string;
  onOpenRoster: (roomId: string) => void;
  onActionTarget: (target: RoomExceptionActionTarget) => void;
}) {
  const realtimeState = useRealtimeState();
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [board, setBoard] = useState<LiveRoomSafetyBoard | null>(null);
  const [exceptions, setExceptions] = useState<RoomOperationalException[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [filter, setFilter] = useState<RoomExceptionFilter>("all");
  const [selectedId, setSelectedId] = useState(requestedExceptionId ?? "");
  const [acknowledging, setAcknowledging] =
    useState<RoomOperationalException | null>(null);
  const [error, setError] = useState("");
  const [targetNotice, setTargetNotice] = useState("");
  const [recoveryNotice, setRecoveryNotice] = useState("");
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    if (!capability.runtime_available || !organizationId || !facilityId) return;
    const [nextBoard, nextExceptions] = await Promise.all([
      fetchLiveRoomSafetyBoard({
        organizationId,
        facilityId,
        facilityTimezone,
        rooms,
      }),
      fetchRoomOperationalExceptions({
        organizationId,
        facilityId,
        stateFilter: "all",
        limit: 100,
      }),
    ]);
    let nextRecoveryNotice = "";
    try {
      const confirmed = reconcileCanonicallyConfirmedAcknowledgements(
        { organizationId, actorUserId },
        nextExceptions.items,
      );
      if (confirmed > 0)
        nextRecoveryNotice =
          "Canonical acknowledgement evidence confirmed a previously interrupted review action. Its protected local draft was cleared.";
    } catch {
      nextRecoveryNotice =
        "A protected local acknowledgement draft could not be verified. CareSync left it locked and did not send or replace any action.";
    }
    setBoard(nextBoard);
    setExceptions(nextExceptions.items);
    setNextCursor(nextExceptions.next_cursor);
    setRecoveryNotice(nextRecoveryNotice);
    setPhase("ready");
    setError("");
    setNow(Date.now());
  }, [
    capability.runtime_available,
    actorUserId,
    facilityId,
    facilityTimezone,
    organizationId,
    rooms,
  ]);

  useEffect(() => {
    let active = true;
    setPhase("loading");
    setBoard(null);
    setExceptions([]);
    setSelectedId(requestedExceptionId ?? "");
    void load().catch((caught) => {
      if (!active) return;
      setBoard(null);
      setExceptions([]);
      setError(
        caught instanceof Error
          ? caught.message
          : "The live room board could not be verified.",
      );
      setPhase("error");
    });
    return () => {
      active = false;
    };
  }, [load, requestedExceptionId]);

  useRealtimeRefresh({
    scope: "rooms-live-operations",
    organizationId,
    enabled: Boolean(organizationId && facilityId),
    entityTypes: ROOM_SAFETY_REALTIME_ENTITIES,
    refresh: async () => {
      try {
        await load();
      } catch (caught) {
        setBoard(null);
        setExceptions([]);
        setError(
          caught instanceof Error
            ? caught.message
            : "The canonical live room refresh could not be verified.",
        );
        setPhase("error");
        throw caught;
      }
    },
  });

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!requestedExceptionId) return;
    let active = true;
    setTargetNotice("");
    void fetchRoomExceptionActionTarget({
      organizationId,
      exceptionId: requestedExceptionId,
      expectedFacilityId: facilityId,
      expectedRoomId: requestedRoomId,
    })
      .then((target) => {
        if (!active) return;
        onActionTarget(target);
        setSelectedId(target.exception_id);
        if (target.state === "resolved")
          setTargetNotice(
            "That operational episode is resolved. Its retained review evidence is shown when available.",
          );
        else if (requestedRoomId && target.room_id !== requestedRoomId)
          setTargetNotice(
            "The supplied room focus was stale. CareSync used the server-confirmed action target.",
          );
      })
      .catch((caught) => {
        if (!active) return;
        setSelectedId("");
        setTargetNotice(
          caught instanceof Error
            ? caught.message
            : "That operational episode is no longer available.",
        );
      });
    return () => {
      active = false;
    };
  }, [
    onActionTarget,
    facilityId,
    organizationId,
    requestedExceptionId,
    requestedRoomId,
  ]);

  const generatedAt = board ? Date.parse(board.generated_at) : Number.NaN;
  const stale =
    phase !== "ready" ||
    !Number.isFinite(generatedAt) ||
    now - generatedAt >= 60_000 ||
    realtimeState !== "connected";
  const visibleExceptions = useMemo(
    () =>
      exceptions.filter((item) =>
        filter === "all" ? true : item.state === filter,
      ),
    [exceptions, filter],
  );
  const selected =
    exceptions.find((item) => item.id === selectedId) ?? null;

  const loadMore = async () => {
    if (!nextCursor) return;
    try {
      const page = await fetchRoomOperationalExceptions({
        organizationId,
        facilityId,
        stateFilter: "all",
        cursor: nextCursor,
        limit: 100,
      });
      setExceptions((current) => {
        const ids = new Set(current.map((item) => item.id));
        if (page.items.some((item) => ids.has(item.id)))
          throw new Error(
            "The operational exception continuation repeated a prior episode.",
          );
        return [...current, ...page.items];
      });
      setNextCursor(page.next_cursor);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "More operational episodes could not be verified.",
      );
    }
  };

  if (phase === "loading") {
    return (
      <Boundary role="status">
        <ArrowPathIcon />
        <span>
          CareSync is rebuilding the live room projection from confirmed
          attendance, actual shifts, current room presence, configured room
          capacity, and configured operational targets.
        </span>
      </Boundary>
    );
  }
  if (phase === "error" || !board) {
    return (
      <Shell>
        <Boundary $warning role="alert">
          <ExclamationTriangleIcon />
          <span>
            No live status is shown because the canonical projection could not
            be verified. {error}
          </span>
        </Boundary>
        <div>
          <ActionButton
            type="button"
            onClick={() => {
              setPhase("loading");
              void load().catch((caught) => {
                setError(
                  caught instanceof Error
                    ? caught.message
                    : "The live room board could not be verified.",
                );
                setPhase("error");
              });
            }}
          >
            <ArrowPathIcon /> Retry canonical refresh
          </ActionButton>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <ControlBar $accent="cyan">
        <div>
          <Eyebrow>
            <RectangleGroupIcon width={14} /> Live operations
          </Eyebrow>
          <h2>Confirmed room presence</h2>
          <p>
            Last canonical projection{" "}
            {new Date(board.generated_at).toLocaleString()}.
          </p>
        </div>
        <ControlActions>
          <StatusChip
            $tone={stateTone(board.facility.overall_state, stale)}
            role="status"
            aria-live="polite"
          >
            {stateLabel(board.facility.overall_state, stale)}
          </StatusChip>
          <ActionButton
            type="button"
            onClick={() =>
              void load().catch((caught) => {
                setError(
                  caught instanceof Error
                    ? caught.message
                    : "The live room board could not be refreshed.",
                );
                setPhase("error");
              })
            }
          >
            <ArrowPathIcon /> Refresh
          </ActionButton>
        </ControlActions>
      </ControlBar>
      <Boundary $warning={stale}>
        {stale ? <ExclamationTriangleIcon /> : <InformationCircleIcon />}
        <span>
          {stale
            ? "Live facts are stale because the projection is older than 60 seconds or realtime confirmation is unavailable. Counts remain historical evidence only until refresh and reconnection succeed. "
            : ""}
          {LIVE_ROOM_SAFETY_STANDING_BOUNDARY}
        </span>
      </Boundary>
      {error && <InlineError role="alert">{error}</InlineError>}
      {targetNotice && <Boundary role="status"><InformationCircleIcon /><span>{targetNotice}</span></Boundary>}
      {recoveryNotice && (
        <Boundary role="status">
          <InformationCircleIcon />
          <span>{recoveryNotice}</span>
        </Boundary>
      )}
      <MetricGrid aria-label="Facility live room facts">
        <Metric $accent="cyan">
          <span>Confirmed on-site children</span>
          <strong>{formatCount(board.facility.confirmed_children)}</strong>
          <small>
            Open attendance intervals ·{" "}
            {formatCount(board.facility.present_children_without_active_room)}{" "}
            without an active room
          </small>
        </Metric>
        <Metric $accent="plasma">
          <span>Open actual-shift staff</span>
          <strong>{formatCount(board.facility.open_shift_staff)}</strong>
          <small>Facility clock evidence</small>
        </Metric>
        <Metric $accent="cyan">
          <span>Located room staff</span>
          <strong>{formatCount(board.facility.located_staff)}</strong>
          <small>Current room-presence sessions</small>
        </Metric>
        <Metric $accent="amber">
          <span>Unlocated on-duty staff</span>
          <strong>{formatCount(board.facility.unlocated_staff)}</strong>
          <small>Open shift without a current room</small>
        </Metric>
        <Metric $accent="amber">
          <span>Facility operational target</span>
          <strong>
            {formatCount(board.facility.configured_target.required_staff)}
          </strong>
          <small>
            {formatReason(board.facility.configured_target.state)}
          </small>
        </Metric>
        <Metric $accent="amber">
          <span>Active signals</span>
          <strong>{board.facility.active_exception_count}</strong>
          <small>Open or acknowledged episodes</small>
        </Metric>
      </MetricGrid>
      {board.facility.data_quality_reason_codes.length > 0 && (
        <Boundary $warning role="alert">
          <ExclamationTriangleIcon />
          <span>
            Facility arithmetic is unknown:{" "}
            {board.facility.data_quality_reason_codes
              .map(formatReason)
              .join(", ")}
            .
          </span>
        </Boundary>
      )}
      <RoomGrid aria-label="Live room cards">
        {board.rooms.map((room) => {
          const roomStaleOrUnknown =
            stale ||
            room.overall_state === "unknown" ||
            room.data_quality_reason_codes.length > 0;
          const target = room.configured_target;
          return (
            <RoomCard
              key={room.room_id}
              $accent={
                room.overall_state === "attention" ? "amber" : "cyan"
              }
              $attention={room.overall_state === "attention" && !stale}
              $unknown={roomStaleOrUnknown}
            >
              <CardTop>
                <div>
                  <h3>{room.room_name}</h3>
                </div>
                <StatusChip
                  $tone={stateTone(room.overall_state, roomStaleOrUnknown)}
                >
                  {stateLabel(room.overall_state, roomStaleOrUnknown)}
                </StatusChip>
              </CardTop>
              <FactGrid>
                <div>
                  <dt>Confirmed on-site children</dt>
                  <dd>{formatCount(room.confirmed_children)}</dd>
                </div>
                <div>
                  <dt>Configured room capacity</dt>
                  <dd>{formatCount(room.configured_room_capacity)}</dd>
                </div>
                <div>
                  <dt>Confirmed room-present staff</dt>
                  <dd>{formatCount(room.confirmed_staff)}</dd>
                </div>
                <div>
                  <dt>Configured operational staffing target</dt>
                  <dd>{formatCount(target.required_staff)}</dd>
                </div>
              </FactGrid>
              <Boundary $warning={roomStaleOrUnknown}>
                {roomStaleOrUnknown ? (
                  <ExclamationTriangleIcon />
                ) : (
                  <CheckCircleIcon />
                )}
                <span>
                  Capacity: {formatReason(room.capacity_state)}. Staffing target:
                  {" "}
                  {formatReason(target.state)}.
                  {room.data_quality_reason_codes.length
                    ? ` Unknown source facts: ${room.data_quality_reason_codes
                        .map(formatReason)
                        .join(", ")}.`
                    : ""}
                </span>
              </Boundary>
              <CardActions>
                <button
                  type="button"
                  onClick={() => onOpenRoster(room.room_id)}
                >
                  Open current roster
                </button>
                {room.active_exception_ids[0] && (
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedId(room.active_exception_ids[0])
                    }
                  >
                    Review current signal
                  </button>
                )}
              </CardActions>
            </RoomCard>
          );
        })}
      </RoomGrid>
      <ExceptionSection $accent="amber">
        <SectionTop>
          <div>
            <h2>Operational signal episodes</h2>
            <p>
              Acknowledgement records review only. Source facts resolve an
              episode.
            </p>
          </div>
          <select
            aria-label="Filter operational signals"
            value={filter}
            onChange={(event) =>
              setFilter(event.target.value as RoomExceptionFilter)
            }
          >
            <option value="all">All loaded episodes</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
        </SectionTop>
        {visibleExceptions.length ? (
          <ExceptionList>
            {visibleExceptions.map((item) => (
              <ExceptionButton
                key={item.id}
                type="button"
                $selected={item.id === selectedId}
                onClick={() => setSelectedId(item.id)}
              >
                <div>
                  <strong>{exceptionConditionCopy(item).title}</strong>
                  <small>
                    {item.scope_kind === "room" ? "Room" : "Facility"} signal ·
                    opened {new Date(item.opened_at).toLocaleString()} · version{" "}
                    {item.version}
                  </small>
                </div>
                <StatusChip
                  $tone={
                    item.state === "open"
                      ? "warning"
                      : item.state === "acknowledged"
                        ? "info"
                        : "neutral"
                  }
                >
                  {item.state}
                </StatusChip>
              </ExceptionButton>
            ))}
          </ExceptionList>
        ) : (
          <Empty>No loaded episodes match this filter.</Empty>
        )}
        {nextCursor && (
          <div>
            <ActionButton type="button" onClick={() => void loadMore()}>
              Load older episodes
            </ActionButton>
          </div>
        )}
        {selected && (
          <Detail aria-label="Operational signal detail">
            <div>
              <Eyebrow>
                <ShieldExclamationIcon width={14} /> Server-derived episode
              </Eyebrow>
              <h3>{exceptionConditionCopy(selected).title}</h3>
            </div>
            <p>{exceptionConditionCopy(selected).owner}</p>
            <DetailFacts>
              <div>
                <dt>Observed server value</dt>
                <dd>{formatCount(selected.observed_value)}</dd>
              </div>
              <div>
                <dt>Configured comparison value</dt>
                <dd>{formatCount(selected.configured_value)}</dd>
              </div>
              <div>
                <dt>Current state and version</dt>
                <dd>
                  {selected.state} · v{selected.version}
                </dd>
              </div>
            </DetailFacts>
            {selected.source_integrity_reason_codes.length > 0 && (
              <Boundary $warning>
                <ExclamationTriangleIcon />
                <span>
                  Unknown source facts:{" "}
                  {selected.source_integrity_reason_codes
                    .map(formatReason)
                    .join(", ")}
                  .
                </span>
              </Boundary>
            )}
            {selected.acknowledgement_reason && (
              <Boundary>
                <InformationCircleIcon />
                <span>
                  Review recorded{" "}
                  {selected.acknowledged_at
                    ? new Date(selected.acknowledged_at).toLocaleString()
                    : ""}
                  : {selected.acknowledgement_reason}
                </span>
              </Boundary>
            )}
            <Boundary>
              <InformationCircleIcon />
              <span>
                Acknowledgement is not resolution. Only a changed canonical
                attendance, shift, room presence, room, or configured-target
                fact can clear this episode.
              </span>
            </Boundary>
            <CardActions>
              <Link to={correctionPath(selected)}>
                Open likely source workspace
              </Link>
              {selected.room_id && (
                <button
                  type="button"
                  onClick={() => onOpenRoster(selected.room_id!)}
                >
                  Open room roster
                </button>
              )}
              {selected.state === "open" && (
                <button
                  type="button"
                  disabled={stale}
                  onClick={() => setAcknowledging(selected)}
                >
                  Acknowledge review
                </button>
              )}
            </CardActions>
          </Detail>
        )}
      </ExceptionSection>
      {acknowledging && (
        <AcknowledgementDialog
          exception={acknowledging}
          scope={{ organizationId, actorUserId }}
          stale={stale}
          onClose={() => setAcknowledging(null)}
          onConfirmed={load}
        />
      )}
    </Shell>
  );
}
