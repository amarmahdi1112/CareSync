import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import { commandBoundToJournalOperation } from "../../api/childcareCommand";
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  IconButton,
  StatusChip,
} from "../../components/ui/Primitives";
import { formatProgramType } from "../../models/programTypes";
import {
  approveRoomPlacement,
  buildRoomPlacementPlan,
  fetchRoomPlacementReviews,
  type RoomPlacementPlan,
  type RoomPlacementReview,
  type RoomWorkspace,
} from "./roomsApi";
import {
  ChildcareCommandRecoveredCommitError,
  childcareCommandWasNotPrepared,
  childcareFinalAbsenceAcknowledged,
  childcareMutationControlDisabled,
  useChildcareCommandRecovery,
} from "../../childcare-commands/ChildcareCommandRecoveryContext";
import { PlacementCommandSequenceError, runPlacementCommandSequence } from "./placementCommandSequence";

interface Props {
  facilityId: string;
  organizationId: string;
  workspace: RoomWorkspace;
  initialEnrollmentId?: string;
  onClose: () => void;
  onChanged: () => void;
}

const Overlay = styled.div`
  position: fixed;
  inset: 0;
  z-index: 980;
  display: grid;
  place-items: center;
  padding: 22px;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});
  @media (max-width: 700px) {
    padding: 0;
  }
`;
const Dialog = styled(GlassPanel)`
  display: grid;
  width: min(980px, calc(100vw - 44px));
  max-height: calc(100dvh - 44px);
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border-radius: 24px 8px 24px 8px;
  background:
    ${({ theme }) => theme.effect.panelHighlight},
    ${({ theme }) => theme.color.surface};
  @media (max-width: 700px) {
    width: 100vw;
    max-height: 100dvh;
    border-radius: 0;
  }
`;
const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px 18px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  h2 {
    margin: 8px 0 5px;
    font-family: "CareSync Display", sans-serif;
    font-size: clamp(1.5rem, 3vw, 2.15rem);
    font-weight: 540;
    letter-spacing: -0.045em;
  }
  p {
    max-width: 680px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
    line-height: 1.6;
  }
`;
const Body = styled.div`
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 20px 24px 30px;
  overflow-y: auto;
  @media (max-width: 600px) {
    padding-inline: 14px;
  }
`;
const State = styled.div`
  display: grid;
  min-height: 220px;
  place-items: center;
  padding: 26px;
  border: 1px dashed ${({ theme }) => theme.color.border};
  border-radius: 16px;
  text-align: center;
  svg {
    width: 40px;
    margin-bottom: 10px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h3 {
    margin: 0 0 6px;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
  }
`;
const Card = styled.section`
  display: grid;
  gap: 14px;
  padding: 17px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 17px 7px 17px 7px;
  background: ${({ theme }) => theme.color.surfaceStrong};
`;
const CardHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  h3 {
    margin: 0 0 5px;
    font-size: 0.9rem;
    font-weight: 610;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
    line-height: 1.5;
  }
`;
const Options = styled.fieldset`
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  border: 0;
  legend {
    margin-bottom: 8px;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.72rem;
    font-weight: 600;
  }
`;
const Option = styled.label<{ $disabled?: boolean }>`
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  min-height: 48px;
  padding: 10px 12px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 12px;
  opacity: ${({ $disabled }) => ($disabled ? 0.55 : 1)};
  cursor: ${({ $disabled }) => ($disabled ? "not-allowed" : "pointer")};
  background: ${({ theme }) => theme.color.control};
  input {
    accent-color: ${({ theme }) => theme.color.cyan};
  }
  strong {
    display: block;
    font-size: 0.75rem;
  }
  small {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.69rem;
    line-height: 1.4;
  }
`;
const Footer = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
`;
const BatchBar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 14px 6px 14px 6px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  div {
    display: grid;
    gap: 4px;
  }
  strong {
    font-size: 0.8rem;
  }
  span {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.7rem;
    line-height: 1.45;
  }
  @media (max-width: 620px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const Notice = styled.div<{ $error?: boolean }>`
  padding: 10px 12px;
  border: 1px solid
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.amber)};
  border-radius: 10px 4px 10px 4px;
  color: ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.amber)};
  font-size: 0.72rem;
  line-height: 1.5;
`;

function childName(review: RoomPlacementReview): string {
  return [
    review.child_first_name,
    review.child_middle_name,
    review.child_last_name,
  ]
    .filter(Boolean)
    .join(" ");
}

function ageLabel(months: number): string {
  const years = Math.floor(months / 12);
  const remainder = months % 12;
  return years
    ? `${years}y${remainder ? ` ${remainder}m` : ""}`
    : `${months} month${months === 1 ? "" : "s"}`;
}

function preferredCandidates(
  review: RoomPlacementReview,
  remaining?: Map<string, number>,
) {
  const available = review.candidates.filter((candidate) =>
    remaining
      ? (remaining.get(candidate.room_id) || 0) > 0
      : candidate.available_places > 0,
  );
  if (!available.length) return [];
  const narrowestSpan = Math.min(
    ...available.map(
      (candidate) =>
        candidate.maximum_age_months - candidate.minimum_age_months,
    ),
  );
  return available.filter(
    (candidate) =>
      candidate.maximum_age_months - candidate.minimum_age_months ===
      narrowestSpan,
  );
}

function planClearPlacements(reviews: RoomPlacementReview[]) {
  const remaining = new Map<string, number>();
  reviews
    .flatMap((review) => review.candidates)
    .forEach((candidate) => {
      if (!remaining.has(candidate.room_id))
        remaining.set(candidate.room_id, candidate.available_places);
    });
  const plan: Array<{ review: RoomPlacementReview; roomId: string }> = [];
  reviews.forEach((review) => {
    const preferred = preferredCandidates(review, remaining);
    if (preferred.length !== 1) return;
    const candidate = preferred[0];
    plan.push({ review, roomId: candidate.room_id });
    remaining.set(
      candidate.room_id,
      (remaining.get(candidate.room_id) || 0) - 1,
    );
  });
  return plan;
}

export default function RoomPlacementReviewDialog({
  facilityId,
  organizationId,
  workspace,
  initialEnrollmentId,
  onClose,
  onChanged,
}: Props) {
  const commandRecovery = useChildcareCommandRecovery();
  const dialogRef = useRef<HTMLDivElement>(null);
  const savingRef = useRef(false);
  // Keep the verified room boundary stable for this review session. Realtime
  // workspace replacements must not reset selections while approvals are in flight.
  const workspaceSnapshot = useRef(workspace).current;
  const [reviews, setReviews] = useState<RoomPlacementReview[] | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState("");
  const [bulkProgress, setBulkProgress] = useState<{ completed: number; total: number } | null>(null);
  const [notice, setNotice] = useState("");
  const [pendingRecoveryOperationId, setPendingRecoveryOperationId] = useState<string | null>(null);

  useEffect(() => {
    setNotice("");
  }, [facilityId, initialEnrollmentId, organizationId]);

  useEffect(() => {
    const controller = new AbortController();
    setReviews(null);
    setError("");
    fetchRoomPlacementReviews(
      facilityId,
      organizationId,
      workspaceSnapshot,
      controller.signal,
    )
      .then((items) => {
        setReviews(items);
        setSelected(
          Object.fromEntries(
            items
              .map((item) => {
                const preferred = preferredCandidates(item);
                return [
                  item.enrollment_id,
                  preferred.length === 1 ? preferred[0].room_id : "",
                ] as const;
              })
              .filter((entry) => Boolean(entry[1])),
          ),
        );
        if (initialEnrollmentId) {
          const index = items.findIndex((item) => item.enrollment_id === initialEnrollmentId);
          if (index >= 0) requestAnimationFrame(() => {
            const cards = dialogRef.current?.querySelectorAll<HTMLElement>('[data-placement-card="true"]');
            cards?.[index]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
            cards?.[index]?.focus({ preventScroll: true });
          });
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted)
          setError(
            caught instanceof Error
              ? caught.message
              : "Room placement review could not be loaded.",
          );
      });
    return () => controller.abort();
  }, [facilityId, initialEnrollmentId, organizationId, refresh, workspaceSnapshot]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !savingRef.current) onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [
        ...dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex="-1"])',
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
    requestAnimationFrame(() =>
      dialogRef.current?.querySelector<HTMLElement>("button, input")?.focus(),
    );
    return () => {
      window.removeEventListener("keydown", keyboard);
      document.body.style.overflow = previousOverflow;
      previous?.focus();
    };
  }, [onClose]);

  const facility = useMemo(
    () => workspaceSnapshot.facilities.find((item) => item.id === facilityId),
    [facilityId, workspaceSnapshot.facilities],
  );
  const clearPlan = useMemo(
    () => planClearPlacements(reviews || []),
    [reviews],
  );
  const placementMutationLocked = childcareMutationControlDisabled(
    commandRecovery.laneBlocked,
    Boolean(savingId),
    Boolean(pendingRecoveryOperationId),
  );
  const approve = async (review: RoomPlacementReview) => {
    const roomId = selected[review.enrollment_id];
    if (!roomId || placementMutationLocked) return;
    const plan = buildRoomPlacementPlan(review, roomId);
    await executeSingle(plan);
  };
  const executeSingle = async (plan: RoomPlacementPlan) => {
    savingRef.current = true;
    setSavingId(plan.review.enrollment_id);
    setNotice("");
    setPendingRecoveryOperationId(plan.command.clientOperationId);
    try {
      const approval = await commandRecovery.execute({
        clientOperationId: plan.command.clientOperationId,
        commandType: 'enrollment.placement.approve',
        targetType: 'enrollment',
        expectedTargetId: plan.review.enrollment_id,
        expectedActionOwnerId: plan.review.child_id,
      }, (operationId) => approveRoomPlacement({
        ...plan,
        command: commandBoundToJournalOperation(plan.command, operationId),
      }, organizationId));
      setPendingRecoveryOperationId(null);
      setNotice(approval.replayed
        ? `${childName(plan.review)}’s exact placement command was confirmed. The enrollment changed after that approval, so the current canonical state is now shown.`
        : `${childName(plan.review)}’s placement was approved. Remaining recommendations were recalculated.`);
      onChanged();
      setRefresh((value) => value + 1);
    } catch (caught) {
      if (childcareCommandWasNotPrepared(caught, plan.command.clientOperationId)) {
        setPendingRecoveryOperationId(null);
      }
      if (caught instanceof ChildcareCommandRecoveredCommitError) {
        setPendingRecoveryOperationId(null);
        setNotice(`${childName(plan.review)}’s interrupted placement was confirmed saved.`);
        onChanged();
        setRefresh((value) => value + 1);
      } else {
        setNotice(
          caught instanceof Error
            ? caught.message
            : "The room placement could not be approved.",
        );
      }
    } finally {
      savingRef.current = false;
      setSavingId("");
    }
  };
  const approveClear = async () => {
    if (!clearPlan.length || placementMutationLocked) return;
    const exactPlan = clearPlan.map(({ review, roomId }) => buildRoomPlacementPlan(review, roomId));
    await executeBatch(exactPlan);
  };
  const executeBatch = async (exactPlan: RoomPlacementPlan[]) => {
    savingRef.current = true;
    setSavingId("bulk");
    setBulkProgress({ completed: 0, total: exactPlan.length });
    setNotice("");
    try {
      const approvals = await runPlacementCommandSequence(exactPlan, async (plan) => {
        setPendingRecoveryOperationId(plan.command.clientOperationId);
        const approval = await commandRecovery.execute({
          clientOperationId: plan.command.clientOperationId,
          commandType: 'enrollment.placement.approve',
          targetType: 'enrollment',
          expectedTargetId: plan.review.enrollment_id,
          expectedActionOwnerId: plan.review.child_id,
        }, (operationId) => approveRoomPlacement({
          ...plan,
          command: commandBoundToJournalOperation(plan.command, operationId),
        }, organizationId));
        setPendingRecoveryOperationId(null);
        return approval;
      }, (completed, total) => setBulkProgress({ completed, total }));
      const replayedCount = approvals.filter((approval) => approval.replayed).length;
      setNotice(replayedCount
        ? `${approvals.length} placement command${approvals.length === 1 ? " was" : "s were"} confirmed; ${replayedCount} now show later canonical enrollment state.`
        : `${approvals.length} reviewed DOB placement${approvals.length === 1 ? "" : "s"} approved in order.`);
      onChanged();
      setRefresh((value) => value + 1);
    } catch (caught) {
      const sequenceError = caught instanceof PlacementCommandSequenceError ? caught : null;
      const cause = sequenceError?.cause ?? caught;
      const priorCompleted = sequenceError?.completedResults.length ?? 0;
      const recoveredCurrent = cause instanceof ChildcareCommandRecoveredCommitError;
      const confirmedCount = priorCompleted + (recoveredCurrent ? 1 : 0);
      const currentPlan = sequenceError ? exactPlan[sequenceError.failedIndex] : null;
      if (currentPlan && childcareCommandWasNotPrepared(cause, currentPlan.command.clientOperationId)) {
        setPendingRecoveryOperationId(null);
      }
      if (confirmedCount > 0) {
        onChanged();
        setRefresh((value) => value + 1);
      }
      if (recoveredCurrent) {
        setPendingRecoveryOperationId(null);
        setNotice(`${confirmedCount} placement${confirmedCount === 1 ? ' was' : 's were'} confirmed saved. The remaining batch was not sent; the canonical queue is refreshing.`);
      } else {
        setNotice(
          `${priorCompleted > 0 ? `${priorCompleted} placement${priorCompleted === 1 ? ' was' : 's were'} saved before the sequence stopped. ` : ''}${cause instanceof Error
            ? cause.message
            : "The remaining placements were not sent."}${priorCompleted > 0 ? ' The canonical queue is refreshing.' : ' Refresh and review the current queue.'}`,
        );
      }
    } finally {
      savingRef.current = false;
      setSavingId("");
      setBulkProgress(null);
    }
  };

  useEffect(() => {
    if (savingId || !pendingRecoveryOperationId || commandRecovery.lastResolved?.clientOperationId !== pendingRecoveryOperationId) return;
    setPendingRecoveryOperationId(null);
    setNotice('The previously unresolved placement was confirmed saved. Refreshing the reviewed queue.');
    onChanged();
    setRefresh((value) => value + 1);
  }, [commandRecovery.lastResolved, onChanged, pendingRecoveryOperationId, savingId]);

  useEffect(() => {
    if (!childcareFinalAbsenceAcknowledged(
      pendingRecoveryOperationId,
      commandRecovery.lastFinalAbsenceAcknowledgedOperationId,
    )) return;
    setPendingRecoveryOperationId(null);
    setNotice('The server proved this placement was not saved. The canonical queue is refreshing; review it before approving a new operation.');
    onChanged();
    setRefresh((value) => value + 1);
  }, [commandRecovery.lastFinalAbsenceAcknowledgedOperationId, onChanged, pendingRecoveryOperationId]);

  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !savingId && onClose()
      }
    >
      <Dialog
        ref={dialogRef}
        $accent="cyan"
        role="dialog"
        aria-modal="true"
        aria-labelledby="placement-review-title"
        aria-describedby="placement-review-description"
      >
        <Header>
          <div>
            <Eyebrow>
              <SparklesIcon width={14} /> Approval-first placement
            </Eyebrow>
            <h2 id="placement-review-title">Review room recommendations.</h2>
            <p id="placement-review-description">
              CareSync compares each child’s full calendar age on the shown
              effective date with your configured room age ranges and current
              capacity. It never assigns a room until you approve one.
            </p>
          </div>
          <IconButton
            type="button"
            onClick={onClose}
            disabled={Boolean(savingId)}
            aria-label="Close room placement review"
          >
            <XMarkIcon />
          </IconButton>
        </Header>
        <Body aria-live="polite">
          {pendingRecoveryOperationId && <Notice role="alert">This placement is held for receipt reconciliation. CareSync will not resend it; use the saved-result control above the page.</Notice>}
          {!reviews && !error && (
            <State aria-busy="true">
              <div>
                <ArrowPathIcon />
                <h3>Calculating compatible rooms</h3>
                <p>
                  Checking DOB, program, configured ages, and capacity for{" "}
                  {facility?.name || "this facility"}.
                </p>
              </div>
            </State>
          )}
          {error && (
            <State>
              <div>
                <ExclamationTriangleIcon />
                <h3>Review needs a refresh</h3>
                <p>{error}</p>
                <ActionButton
                  type="button"
                  onClick={() => setRefresh((value) => value + 1)}
                >
                  Try again
                </ActionButton>
              </div>
            </State>
          )}
          {reviews?.length === 0 && (
            <State>
              <div>
                <CheckCircleIcon />
                <h3>Placement queue is clear</h3>
                <p>
                  Every active enrollment at this facility has a room
                  assignment.
                </p>
              </div>
            </State>
          )}
          {reviews && reviews.length > 0 && (
            <BatchBar>
              <div>
                <strong>
                  {clearPlan.length} clear DOB placement
                  {clearPlan.length === 1 ? "" : "s"} ready
                </strong>
                <span>
                  The narrowest compatible room interval wins; capacity overflow
                  moves to the next compatible interval. Equal best matches
                  remain manual.
                </span>
              </div>
              <ActionButton
                type="button"
                $variant="primary"
                disabled={!clearPlan.length || placementMutationLocked}
                onClick={() => void approveClear()}
              >
                {savingId === "bulk"
                  ? `Approving ${bulkProgress?.total || clearPlan.length} placements…`
                  : "Approve all clear placements"}
              </ActionButton>
            </BatchBar>
          )}
          {reviews?.map((review) => {
            const preferred = preferredCandidates(review);
            return (
              <Card key={review.enrollment_id} data-placement-card="true" tabIndex={-1}>
                <CardHeader>
                  <div>
                    <h3>{childName(review)}</h3>
                    <p>
                      DOB {review.date_of_birth} · {ageLabel(review.age_months)}{" "}
                      on {review.effective_date} · enrollment began{" "}
                      {review.enrollment_start_date}
                    </p>
                  </div>
                  <StatusChip
                    $tone={
                      review.suggestion_state === "none"
                        ? "warning"
                        : review.suggestion_state === "one"
                          ? "success"
                          : "info"
                    }
                  >
                    {review.suggestion_state === "none"
                      ? "No available match"
                      : review.suggestion_state === "one"
                        ? "Auto match ready"
                        : `${preferred.length} equal best matches`}
                  </StatusChip>
                </CardHeader>
                {review.candidates.length ? (
                  <Options>
                    <legend>
                      {review.suggestion_state === "multiple"
                        ? "Choose one compatible room"
                        : "Compatible rooms"}
                    </legend>
                    {review.candidates.map((candidate) => (
                      <Option
                        key={candidate.room_id}
                        $disabled={candidate.available_places === 0}
                      >
                        <input
                          type="radio"
                          name={`placement-${review.enrollment_id}`}
                          value={candidate.room_id}
                          checked={
                            selected[review.enrollment_id] === candidate.room_id
                          }
                          disabled={
                            candidate.available_places === 0 ||
                            placementMutationLocked
                          }
                          onChange={() =>
                            setSelected((value) => ({
                              ...value,
                              [review.enrollment_id]: candidate.room_id,
                            }))
                          }
                        />
                        <span>
                          <strong>
                            {candidate.room_name} · {candidate.program_name}
                          </strong>
                          <small>
                            {formatProgramType(candidate.program_type)} · ages{" "}
                            {candidate.minimum_age_months}–
                            {candidate.maximum_age_months} months inclusive
                          </small>
                        </span>
                        <small>
                          {candidate.available_places > 0
                            ? `${candidate.available_places} place${candidate.available_places === 1 ? "" : "s"} left`
                            : "Full"}
                        </small>
                      </Option>
                    ))}
                  </Options>
                ) : (
                  <Notice>
                    Configure both minimum and maximum ages on at least one
                    active room that fits this child. OSC recommendations also
                    require an active OSC program.
                  </Notice>
                )}
                <Footer>
                  <span>
                    {review.suggestion_state === "multiple"
                      ? "Your choice is required because equally specific rooms are eligible."
                      : review.suggestion_state === "one"
                        ? "The most specific compatible age interval is preselected; approval is still required."
                        : "No assignment will be made."}
                  </span>
                  <ActionButton
                    type="button"
                    $variant="primary"
                    disabled={
                      !selected[review.enrollment_id] || placementMutationLocked
                    }
                    onClick={() => approve(review)}
                  >
                    {savingId === review.enrollment_id
                      ? "Approving…"
                      : "Approve selected room"}
                  </ActionButton>
                </Footer>
              </Card>
            );
          })}
          {notice && <Notice role="status">{notice}</Notice>}
        </Body>
      </Dialog>
    </Overlay>
  );
}
