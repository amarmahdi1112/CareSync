import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { addDays, format, parseISO } from "date-fns";
import {
  ArrowPathIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  EyeIcon,
  PencilSquareIcon,
  PlusIcon,
  SquaresPlusIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import {
  ActionButton,
  Eyebrow,
  IconButton,
  StatusChip,
} from "../../../components/ui/Primitives";
import { useRealtimeRefresh } from "../../../realtime/RealtimeContext";
import type { StaffWorkspace } from "../../staff/types";
import {
  WorkforceDialog,
  WorkforceDialogActions,
  WorkforceDialogField,
  WorkforceDialogForm,
  WorkforceDialogGrid,
  WorkforceDialogHeader,
} from "../components/WorkforceDialog";
import {
  createOperationId,
  mutationFailureDisposition,
} from "../mutationPolicy";
import {
  rotationApi,
  rotationErrorCode,
  rotationErrorMessage,
} from "./rotationApi";
import {
  occurrenceCounts,
  rotationDraftInput,
  rotationSummary,
  validateRotationInput,
} from "./rotationModel";
import type {
  RotationPattern,
  RotationPatternInput,
  RotationPreview,
  RotationSlotInput,
} from "./rotationTypes";

const Section = styled.section`
  display: grid;
  gap: 12px;
`;
const SectionHead = styled.div`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  h3 {
    margin: 0;
    font-size: 0.88rem;
    font-weight: 600;
  }
  p {
    margin: 4px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.69rem;
    line-height: 1.45;
  }
  @media (max-width: 600px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const Notice = styled.div<{ $error?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 11px 12px;
  border: 1px solid
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.borderStrong)};
  border-radius: 8px 12px 8px 12px;
  color: ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.textSoft)};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: 0.72rem;
  line-height: 1.5;
  svg {
    width: 17px;
    flex: 0 0 auto;
  }
`;
const Cards = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  @media (max-width: 820px) {
    grid-template-columns: 1fr;
  }
`;
const Card = styled.article<{ $focused?: boolean }>`
  display: grid;
  gap: 9px;
  padding: 12px;
  border: 1px solid
    ${({ $focused, theme }) => ($focused ? theme.color.cyan : theme.color.border)};
  border-radius: 9px 13px 9px 13px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  box-shadow: ${({ $focused, theme }) =>
    $focused
      ? `0 0 0 2px color-mix(in srgb, ${theme.color.cyan} 20%, transparent)`
      : "none"};
  outline: none;
  h4 {
    margin: 0;
    font-size: 0.79rem;
    font-weight: 600;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.68rem;
    line-height: 1.45;
  }
`;
const CardTop = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
`;
const CardActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  button {
    min-height: 34px;
    padding: 0 9px;
    font-size: 0.68rem;
  }
  button svg {
    width: 14px;
  }
`;
const Empty = styled.div`
  padding: 28px 16px;
  border: 1px dashed ${({ theme }) => theme.color.borderStrong};
  border-radius: 9px;
  text-align: center;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.72rem;
`;
const SlotRows = styled.div`
  display: grid;
  gap: 8px;
  grid-column: 1/-1;
`;
const SlotRow = styled.div`
  display: grid;
  grid-template-columns: 0.7fr 1fr 1.25fr 1.15fr 0.8fr 0.8fr auto;
  gap: 7px;
  align-items: end;
  padding: 9px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 9px;
  @media (max-width: 760px) {
    grid-template-columns: 1fr 1fr;
    .staff,
    .room {
      grid-column: 1/-1;
    }
  }
`;
const PreviewGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;
const PreviewMetric = styled.div`
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 8px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  span {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.64rem;
  }
  strong {
    display: block;
    margin-top: 4px;
    font-size: 1.2rem;
  }
`;
const Issues = styled.div`
  display: grid;
  gap: 6px;
`;
const Issue = styled.div`
  padding: 9px 10px;
  border: 1px solid ${({ theme }) => theme.color.coral};
  border-radius: 8px;
  color: ${({ theme }) => theme.color.coral};
  font-size: 0.68rem;
  line-height: 1.45;
`;

type EditorState = {
  pattern: RotationPattern | null;
  copiedFrom: RotationPattern | null;
  operationId: string;
  retryLocked: boolean;
  input: RotationPatternInput;
};
type LifecycleState = {
  pattern: RotationPattern;
  kind: "activate" | "retire";
  operationId: string;
  retryLocked: boolean;
  reason: string;
};
type PreviewState = {
  pattern: RotationPattern;
  startDate: string;
  endDate: string;
  preview: RotationPreview | null;
  operationId: string;
  retryLocked: boolean;
};

const newSlot = (): RotationSlotInput => ({
  slot_id: createOperationId(),
  cycle_week: 0,
  weekday: 0,
  staff_user_id: "",
  room_id: null,
  start_local: "08:00",
  end_local: "16:00",
  notes: null,
});

export function RotationPlanningPanel({
  organizationId,
  workspace,
  facilityId,
  weekStart,
  enabled,
  focusedPatternId = null,
  onDraftsGenerated,
}: {
  organizationId: string;
  workspace: StaffWorkspace;
  facilityId: string;
  weekStart: string;
  enabled: boolean;
  focusedPatternId?: string | null;
  onDraftsGenerated: () => Promise<void> | void;
}) {
  const [patterns, setPatterns] = useState<RotationPattern[]>([]);
  const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [loadedFacilityId, setLoadedFacilityId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [lifecycle, setLifecycle] = useState<LifecycleState | null>(null);
  const [previewState, setPreviewState] = useState<PreviewState | null>(null);
  const focusedPatternHandled = useRef("");

  const members = useMemo(
    () =>
      workspace.members.filter(
        (item) =>
          item.membership_status === "active" &&
          item.assigned_facility_ids.includes(facilityId),
      ),
    [facilityId, workspace.members],
  );
  const rooms = useMemo(
    () =>
      workspace.rooms.filter(
        (item) => item.facility_id === facilityId && item.is_active,
      ),
    [facilityId, workspace.rooms],
  );
  const facility = workspace.facilities.find((item) => item.id === facilityId);

  const load = useCallback(
    async (signal?: AbortSignal, quiet = false) => {
      if (!enabled || !organizationId || !facilityId) return;
      if (!quiet) {
        setPhase("loading");
        setLoadedFacilityId("");
      }
      setError("");
      try {
        const result = await rotationApi.list(
          organizationId,
          facilityId,
          true,
          signal,
        );
        if (signal?.aborted) return;
        const knownUsers = new Set(
          workspace.members.map((item) => item.user_id),
        );
        const membershipByUser = new Map(
          workspace.members.map((item) => [item.user_id, item.membership_id]),
        );
        const knownRooms = new Set(
          workspace.rooms
            .filter((item) => item.facility_id === facilityId)
            .map((item) => item.id),
        );
        if (
          result.items.some((pattern) =>
            pattern.slots.some(
              (slot) =>
                !knownUsers.has(slot.staff_user_id) ||
                membershipByUser.get(slot.staff_user_id) !==
                  slot.membership_id ||
                (slot.room_id && !knownRooms.has(slot.room_id)),
            ),
          )
        )
          throw new Error(
            "A rotation crossed the verified staff or room workspace.",
          );
        setPatterns(result.items);
        setLoadedFacilityId(facilityId);
        setPhase("ready");
      } catch (caught) {
        if (!signal?.aborted) {
          setError(rotationErrorMessage(caught));
          setPhase("error");
        }
        throw caught;
      }
    },
    [enabled, facilityId, organizationId, workspace.members, workspace.rooms],
  );

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void load(controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [enabled, load]);
  useRealtimeRefresh({
    scope: "staff-rotations",
    organizationId,
    enabled: enabled && Boolean(facilityId),
    eventPrefixes: [
      "staff_rotation.",
      "staff_schedule.",
      "staff_availability.",
      "staff_time_off.",
    ],
    entityTypes: [
      "staff_rotation_pattern",
      "staff_schedule",
      "staff_availability",
      "staff_time_off",
      "organization_membership",
      "room",
      "facility",
    ],
    refresh: async () => load(undefined, true),
  });

  useEffect(() => {
    if (!focusedPatternId) {
      focusedPatternHandled.current = "";
      return;
    }
    if (
      phase !== "ready" ||
      loadedFacilityId !== facilityId ||
      focusedPatternHandled.current === focusedPatternId
    )
      return;
    focusedPatternHandled.current = focusedPatternId;
    if (!patterns.some((pattern) => pattern.id === focusedPatternId)) {
      setNotice(
        "The verified rotation is no longer present in this current canonical list. No different rotation was selected.",
      );
      return;
    }
    const frame = requestAnimationFrame(() => {
      const card = document.querySelector<HTMLElement>(
        `[data-rotation-id="${CSS.escape(focusedPatternId)}"]`,
      );
      card?.scrollIntoView({ behavior: "smooth", block: "center" });
      card?.focus({ preventScroll: true });
      setNotice("The exact rotation is focused from the latest canonical list.");
    });
    return () => cancelAnimationFrame(frame);
  }, [facilityId, focusedPatternId, loadedFacilityId, patterns, phase]);

  const complete = async (message: string) => {
    try {
      await load(undefined, true);
      setNotice(message);
    } catch {
      setNotice(`${message} Refresh to load the latest canonical state.`);
    }
  };
  const openEditor = (pattern: RotationPattern | null, asNextVersion = false) =>
    setEditor({
      pattern: asNextVersion ? null : pattern,
      copiedFrom: asNextVersion ? pattern : null,
      operationId: createOperationId(),
      retryLocked: false,
      input: pattern
        ? rotationDraftInput(pattern)
        : {
            facility_id: facilityId,
            name: "",
            anchor_date: weekStart,
            cycle_weeks: 1,
            slots: [newSlot()],
          },
    });

  const recoverEditor = async (caught: unknown) => {
    const disposition = mutationFailureDisposition(caught);
    if (disposition === "refresh_then_reset")
      await load(undefined, true).catch(() => undefined);
    setEditor((current) =>
      current
        ? {
            ...current,
            retryLocked: disposition === "retain_exact",
            operationId:
              disposition === "retain_exact"
                ? current.operationId
                : createOperationId(),
          }
        : current,
    );
  };
  const recoverLifecycle = async (caught: unknown) => {
    const disposition = mutationFailureDisposition(caught);
    if (disposition === "refresh_then_reset")
      await load(undefined, true).catch(() => undefined);
    setLifecycle((current) =>
      current
        ? {
            ...current,
            retryLocked: disposition === "retain_exact",
            operationId:
              disposition === "retain_exact"
                ? current.operationId
                : createOperationId(),
          }
        : current,
    );
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!editor) return;
    const input = {
      ...editor.input,
      name: editor.input.name.trim(),
      slots: editor.input.slots.map((slot) => ({
        ...slot,
        notes: slot.notes?.trim() || null,
      })),
    };
    const errors = validateRotationInput(input);
    if (errors.length) {
      setError(errors[0]!);
      return;
    }
    setBusy("save");
    setError("");
    try {
      if (editor.pattern)
        await rotationApi.update(
          organizationId,
          editor.pattern,
          input,
          editor.operationId,
        );
      else await rotationApi.create(organizationId, input, editor.operationId);
      await complete(
        editor.pattern ? "Rotation draft updated." : "Rotation draft created.",
      );
      setEditor(null);
    } catch (caught) {
      await recoverEditor(caught);
      setError(rotationErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const changeLifecycle = async (event: FormEvent) => {
    event.preventDefault();
    if (!lifecycle) return;
    if (lifecycle.kind === "retire" && lifecycle.reason.trim().length < 5) {
      setError("Explain the retirement in at least five characters.");
      return;
    }
    setBusy("lifecycle");
    setError("");
    try {
      if (lifecycle.kind === "activate")
        await rotationApi.activate(
          organizationId,
          lifecycle.pattern,
          lifecycle.operationId,
        );
      else
        await rotationApi.retire(
          organizationId,
          lifecycle.pattern,
          lifecycle.operationId,
          lifecycle.reason.trim(),
        );
      await complete(
        lifecycle.kind === "activate"
          ? "Rotation activated. Preview it before generating drafts."
          : "Rotation retired. Existing drafts remain unchanged.",
      );
      setLifecycle(null);
    } catch (caught) {
      await recoverLifecycle(caught);
      setError(rotationErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const runPreview = async (event: FormEvent) => {
    event.preventDefault();
    if (!previewState || previewState.retryLocked) return;
    setBusy("preview");
    setError("");
    try {
      const value = await rotationApi.preview(previewState.pattern, {
        startDate: previewState.startDate,
        endDate: previewState.endDate,
      });
      setPreviewState({
        ...previewState,
        preview: value,
        operationId: createOperationId(),
      });
    } catch (caught) {
      setError(rotationErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const generate = async () => {
    if (
      !previewState?.preview?.can_generate ||
      !previewState.preview.occurrences.length
    )
      return;
    setBusy("generate");
    setError("");
    try {
      const receipt = await rotationApi.generate(
        previewState.pattern,
        previewState.preview,
        previewState.operationId,
      );
      try {
        await onDraftsGenerated();
      } catch {
        /* Canonical manual refresh remains available. */
      }
      await complete(
        `${receipt.total} rotation draft${receipt.total === 1 ? "" : "s"} generated atomically.`,
      );
      setPreviewState(null);
    } catch (caught) {
      const disposition = mutationFailureDisposition(caught);
      if (disposition === "refresh_then_reset") {
        await load(undefined, true).catch(() => undefined);
        setPreviewState((current) =>
          current
            ? {
                ...current,
                preview: null,
                retryLocked: false,
                operationId: createOperationId(),
              }
            : current,
        );
      } else
        setPreviewState((current) =>
          current
            ? {
                ...current,
                retryLocked: disposition === "retain_exact",
                operationId:
                  disposition === "retain_exact"
                    ? current.operationId
                    : createOperationId(),
              }
            : current,
        );
      setError(
        rotationErrorCode(caught) === "preview_stale"
          ? "The preview is stale. Run a fresh preview before generating any drafts."
          : rotationErrorMessage(caught),
      );
    } finally {
      setBusy("");
    }
  };

  if (!enabled) return null;
  return (
    <Section
      role="tabpanel"
      id="workforce-panel-rotations"
      aria-labelledby="workforce-tab-rotations"
      aria-busy={phase === "loading"}
    >
      <SectionHead>
        <div>
          <h3>Recurring staffed rotations</h3>
          <p>
            Patterns are planning sources. Preview validates every occurrence;
            generation creates ordinary unpublished drafts only.
          </p>
        </div>
        <ActionButton
          type="button"
          $variant="primary"
          onClick={() => openEditor(null)}
          disabled={!facilityId}
        >
          <PlusIcon /> New rotation
        </ActionButton>
      </SectionHead>
      {error && (
        <Notice $error role="alert">
          <ExclamationTriangleIcon /> {error}
        </Notice>
      )}
      {notice && (
        <Notice role="status">
          <CheckCircleIcon /> {notice}
        </Notice>
      )}
      {phase === "loading" && (
        <Notice role="status">
          <ArrowPathIcon /> Loading recurring rotations…
        </Notice>
      )}
      {phase === "error" && !patterns.length && (
        <Empty>Rotations are unavailable. Nothing was changed.</Empty>
      )}
      {phase === "ready" &&
        (patterns.length ? (
          <Cards>
            {patterns.map((pattern) => {
              const focused = focusedPatternId === pattern.id;
              return (
              <Card
                key={pattern.id}
                $focused={focused}
                data-rotation-id={pattern.id}
                tabIndex={focused ? -1 : undefined}
              >
                <CardTop>
                  <div>
                    <h4>
                      {pattern.name} · v{pattern.version}
                    </h4>
                    <p>
                      {rotationSummary(pattern)} · anchored{" "}
                      {pattern.anchor_date} · {pattern.facility_timezone}
                    </p>
                  </div>
                  <StatusChip
                    $tone={
                      pattern.status === "active"
                        ? "success"
                        : pattern.status === "draft"
                          ? "info"
                          : "neutral"
                    }
                  >
                    {pattern.status}
                  </StatusChip>
                </CardTop>
                <p>
                  {pattern.status === "draft"
                    ? "Editable planning source. Activate before preview."
                    : pattern.status === "active"
                      ? "Immutable active source. Preview a bounded date range before generation."
                      : `Historical source; existing generated drafts remain ordinary rota records.${pattern.retirement_reason ? ` Retired: ${pattern.retirement_reason}` : ""}`}
                </p>
                <CardActions>
                  {pattern.can_edit && (
                    <ActionButton
                      type="button"
                      onClick={() => openEditor(pattern)}
                    >
                      <PencilSquareIcon /> Edit
                    </ActionButton>
                  )}
                  {pattern.status !== "draft" && (
                    <ActionButton
                      type="button"
                      onClick={() => openEditor(pattern, true)}
                    >
                      <PlusIcon /> Create next version
                    </ActionButton>
                  )}
                  {pattern.can_activate && (
                    <ActionButton
                      type="button"
                      $variant="primary"
                      onClick={() =>
                        setLifecycle({
                          pattern,
                          kind: "activate",
                          operationId: createOperationId(),
                          retryLocked: false,
                          reason: "",
                        })
                      }
                    >
                      <CheckCircleIcon /> Activate
                    </ActionButton>
                  )}
                  {pattern.can_preview && (
                    <ActionButton
                      type="button"
                      $variant="primary"
                      onClick={() =>
                        setPreviewState({
                          pattern,
                          startDate: weekStart,
                          endDate: format(
                            addDays(parseISO(weekStart), 27),
                            "yyyy-MM-dd",
                          ),
                          preview: null,
                          operationId: createOperationId(),
                          retryLocked: false,
                        })
                      }
                    >
                      <EyeIcon /> Preview
                    </ActionButton>
                  )}
                  {pattern.can_retire && (
                    <ActionButton
                      type="button"
                      $variant="danger"
                      onClick={() =>
                        setLifecycle({
                          pattern,
                          kind: "retire",
                          operationId: createOperationId(),
                          retryLocked: false,
                          reason: "",
                        })
                      }
                    >
                      Retire
                    </ActionButton>
                  )}
                </CardActions>
              </Card>
              );
            })}
          </Cards>
        ) : (
          <Empty>
            No recurring rotation patterns for{" "}
            {facility?.name || "this facility"}.
          </Empty>
        ))}

      {editor && (
        <WorkforceDialog
          labelId="rotation-editor-title"
          busy={Boolean(busy)}
          retryLocked={editor.retryLocked}
          onClose={() => setEditor(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <CalendarDaysIcon width={14} /> Rotation draft
              </Eyebrow>
              <h2 id="rotation-editor-title">
                {editor.pattern
                  ? "Edit recurring rotation"
                  : editor.copiedFrom
                    ? `Create the next version after v${editor.copiedFrom.version}`
                    : "Create recurring rotation"}
              </h2>
              <p>
                {editor.copiedFrom
                  ? `This is a new editable draft copied from immutable v${editor.copiedFrom.version}; saving never patches the historical snapshot. `
                  : ""}
                Week numbers and wall-clock times use {facility?.timezone}.
                Activation makes this snapshot immutable.
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setEditor(null)}
              disabled={Boolean(busy) || editor.retryLocked}
              aria-label="Close rotation editor"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={save}>
            {editor.retryLocked && (
              <Notice>
                <ArrowPathIcon /> The outcome is uncertain. Fields are frozen so
                Retry exact save reuses the same command.
              </Notice>
            )}
            <WorkforceDialogGrid>
              <WorkforceDialogField $wide>
                <span>Name</span>
                <input
                  required
                  maxLength={150}
                  disabled={editor.retryLocked}
                  value={editor.input.name}
                  onChange={(event) =>
                    setEditor({
                      ...editor,
                      input: { ...editor.input, name: event.target.value },
                    })
                  }
                />
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>Anchor Monday</span>
                <input
                  required
                  type="date"
                  disabled={editor.retryLocked}
                  value={editor.input.anchor_date}
                  onChange={(event) =>
                    setEditor({
                      ...editor,
                      input: {
                        ...editor.input,
                        anchor_date: event.target.value,
                      },
                    })
                  }
                />
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>Cycle length</span>
                <select
                  disabled={editor.retryLocked}
                  value={editor.input.cycle_weeks}
                  onChange={(event) =>
                    setEditor({
                      ...editor,
                      input: {
                        ...editor.input,
                        cycle_weeks: Number(event.target.value),
                        slots: editor.input.slots.map((slot) => ({
                          ...slot,
                          cycle_week: Math.min(
                            slot.cycle_week,
                            Number(event.target.value) - 1,
                          ),
                        })),
                      },
                    })
                  }
                >
                  {Array.from({ length: 8 }, (_, index) => (
                    <option key={index + 1} value={index + 1}>
                      {index + 1} week{index ? "s" : ""}
                    </option>
                  ))}
                </select>
              </WorkforceDialogField>
              <SlotRows>
                {editor.input.slots.map((slot, index) => (
                  <SlotRow key={slot.slot_id}>
                    <WorkforceDialogField>
                      <span>Week</span>
                      <select
                        disabled={editor.retryLocked}
                        value={slot.cycle_week}
                        onChange={(event) =>
                          setEditor({
                            ...editor,
                            input: {
                              ...editor.input,
                              slots: editor.input.slots.map(
                                (item, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...item,
                                        cycle_week: Number(event.target.value),
                                      }
                                    : item,
                              ),
                            },
                          })
                        }
                      >
                        {Array.from(
                          { length: editor.input.cycle_weeks },
                          (_, week) => (
                            <option key={week} value={week}>
                              Week {week + 1}
                            </option>
                          ),
                        )}
                      </select>
                    </WorkforceDialogField>
                    <WorkforceDialogField>
                      <span>Day</span>
                      <select
                        disabled={editor.retryLocked}
                        value={slot.weekday}
                        onChange={(event) =>
                          setEditor({
                            ...editor,
                            input: {
                              ...editor.input,
                              slots: editor.input.slots.map(
                                (item, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...item,
                                        weekday: Number(event.target.value),
                                      }
                                    : item,
                              ),
                            },
                          })
                        }
                      >
                        {[
                          "Monday",
                          "Tuesday",
                          "Wednesday",
                          "Thursday",
                          "Friday",
                          "Saturday",
                          "Sunday",
                        ].map((day, dayIndex) => (
                          <option key={day} value={dayIndex}>
                            {day}
                          </option>
                        ))}
                      </select>
                    </WorkforceDialogField>
                    <WorkforceDialogField className="staff">
                      <span>Staff</span>
                      <select
                        required
                        disabled={editor.retryLocked}
                        value={slot.staff_user_id}
                        onChange={(event) =>
                          setEditor({
                            ...editor,
                            input: {
                              ...editor.input,
                              slots: editor.input.slots.map(
                                (item, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...item,
                                        staff_user_id: event.target.value,
                                      }
                                    : item,
                              ),
                            },
                          })
                        }
                      >
                        <option value="">Select staff</option>
                        {members.map((member) => (
                          <option key={member.user_id} value={member.user_id}>
                            {member.first_name} {member.last_name}
                          </option>
                        ))}
                      </select>
                    </WorkforceDialogField>
                    <WorkforceDialogField className="room">
                      <span>Room</span>
                      <select
                        disabled={editor.retryLocked}
                        value={slot.room_id || ""}
                        onChange={(event) =>
                          setEditor({
                            ...editor,
                            input: {
                              ...editor.input,
                              slots: editor.input.slots.map(
                                (item, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...item,
                                        room_id: event.target.value || null,
                                      }
                                    : item,
                              ),
                            },
                          })
                        }
                      >
                        <option value="">Facility-wide</option>
                        {rooms.map((room) => (
                          <option key={room.id} value={room.id}>
                            {room.name}
                          </option>
                        ))}
                      </select>
                    </WorkforceDialogField>
                    <WorkforceDialogField>
                      <span>Starts</span>
                      <input
                        required
                        type="time"
                        disabled={editor.retryLocked}
                        value={slot.start_local}
                        onChange={(event) =>
                          setEditor({
                            ...editor,
                            input: {
                              ...editor.input,
                              slots: editor.input.slots.map(
                                (item, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...item,
                                        start_local: event.target.value,
                                      }
                                    : item,
                              ),
                            },
                          })
                        }
                      />
                    </WorkforceDialogField>
                    <WorkforceDialogField>
                      <span>Ends</span>
                      <input
                        required
                        type="time"
                        disabled={editor.retryLocked}
                        value={slot.end_local}
                        onChange={(event) =>
                          setEditor({
                            ...editor,
                            input: {
                              ...editor.input,
                              slots: editor.input.slots.map(
                                (item, itemIndex) =>
                                  itemIndex === index
                                    ? { ...item, end_local: event.target.value }
                                    : item,
                              ),
                            },
                          })
                        }
                      />
                    </WorkforceDialogField>
                    <IconButton
                      type="button"
                      disabled={
                        editor.retryLocked || editor.input.slots.length === 1
                      }
                      onClick={() =>
                        setEditor({
                          ...editor,
                          input: {
                            ...editor.input,
                            slots: editor.input.slots.filter(
                              (_, itemIndex) => itemIndex !== index,
                            ),
                          },
                        })
                      }
                      aria-label={`Remove rotation slot ${index + 1}`}
                    >
                      <TrashIcon />
                    </IconButton>
                  </SlotRow>
                ))}
              </SlotRows>
              <ActionButton
                type="button"
                disabled={
                  editor.retryLocked || editor.input.slots.length >= 500
                }
                onClick={() =>
                  setEditor({
                    ...editor,
                    input: {
                      ...editor.input,
                      slots: [...editor.input.slots, newSlot()],
                    },
                  })
                }
              >
                <PlusIcon /> Add slot
              </ActionButton>
            </WorkforceDialogGrid>
            <WorkforceDialogActions>
              <ActionButton
                type="button"
                onClick={() => setEditor(null)}
                disabled={Boolean(busy) || editor.retryLocked}
              >
                Cancel
              </ActionButton>
              <ActionButton
                type="submit"
                $variant="primary"
                disabled={Boolean(busy)}
              >
                {busy === "save"
                  ? "Saving…"
                  : editor.retryLocked
                    ? "Retry exact save"
                    : editor.copiedFrom
                      ? "Create new draft version"
                      : "Save draft"}
              </ActionButton>
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}

      {lifecycle && (
        <WorkforceDialog
          labelId="rotation-lifecycle-title"
          busy={Boolean(busy)}
          retryLocked={lifecycle.retryLocked}
          onClose={() => setLifecycle(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <CheckCircleIcon width={14} /> Rotation lifecycle
              </Eyebrow>
              <h2 id="rotation-lifecycle-title">
                {lifecycle.kind === "activate"
                  ? `Activate ${lifecycle.pattern.name}?`
                  : `Retire ${lifecycle.pattern.name}?`}
              </h2>
              <p>
                {lifecycle.kind === "activate"
                  ? "Activation validates the complete snapshot and prevents later editing."
                  : "Retirement prevents future generation but never removes existing drafts or provenance."}
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setLifecycle(null)}
              disabled={Boolean(busy) || lifecycle.retryLocked}
              aria-label="Close rotation action"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={changeLifecycle}>
            {lifecycle.retryLocked && (
              <Notice>
                <ArrowPathIcon /> The response is uncertain. Retry this exact
                lifecycle action.
              </Notice>
            )}
            {lifecycle.kind === "retire" && (
              <WorkforceDialogField>
                <span>Required reason</span>
                <textarea
                  required
                  minLength={5}
                  maxLength={500}
                  disabled={lifecycle.retryLocked}
                  value={lifecycle.reason}
                  onChange={(event) =>
                    setLifecycle({ ...lifecycle, reason: event.target.value })
                  }
                />
              </WorkforceDialogField>
            )}
            <WorkforceDialogActions>
              <ActionButton
                type="button"
                onClick={() => setLifecycle(null)}
                disabled={Boolean(busy) || lifecycle.retryLocked}
              >
                Back
              </ActionButton>
              <ActionButton
                type="submit"
                $variant={lifecycle.kind === "retire" ? "danger" : "primary"}
                disabled={Boolean(busy)}
              >
                {busy === "lifecycle"
                  ? "Recording…"
                  : lifecycle.retryLocked
                    ? "Retry exact action"
                    : lifecycle.kind === "activate"
                      ? "Activate rotation"
                      : "Retire rotation"}
              </ActionButton>
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}

      {previewState && (
        <WorkforceDialog
          labelId="rotation-preview-title"
          busy={Boolean(busy)}
          retryLocked={previewState.retryLocked}
          onClose={() => setPreviewState(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <EyeIcon width={14} /> Rotation preview
              </Eyebrow>
              <h2 id="rotation-preview-title">
                Preview {previewState.pattern.name}
              </h2>
              <p>
                The server rechecks assignment scope, overlaps, approved leave
                and facility-local DST. Generation is all-or-none.
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setPreviewState(null)}
              disabled={Boolean(busy) || previewState.retryLocked}
              aria-label="Close rotation preview"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={runPreview}>
            {previewState.retryLocked && (
              <Notice>
                <ArrowPathIcon /> Generation outcome is uncertain. Retry the
                exact generation with this frozen preview digest.
              </Notice>
            )}
            <WorkforceDialogGrid>
              <WorkforceDialogField>
                <span>Start date</span>
                <input
                  type="date"
                  required
                  disabled={previewState.retryLocked}
                  value={previewState.startDate}
                  onChange={(event) =>
                    setPreviewState({
                      ...previewState,
                      startDate: event.target.value,
                      preview: null,
                      operationId: createOperationId(),
                    })
                  }
                />
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>End date</span>
                <input
                  type="date"
                  required
                  disabled={previewState.retryLocked}
                  value={previewState.endDate}
                  onChange={(event) =>
                    setPreviewState({
                      ...previewState,
                      endDate: event.target.value,
                      preview: null,
                      operationId: createOperationId(),
                    })
                  }
                />
              </WorkforceDialogField>
            </WorkforceDialogGrid>
            {previewState.preview &&
              (() => {
                const counts = occurrenceCounts(previewState.preview);
                return (
                  <>
                    <PreviewGrid>
                      <PreviewMetric>
                        <span>Ready occurrences</span>
                        <strong>{counts.ready}</strong>
                      </PreviewMetric>
                      <PreviewMetric>
                        <span>Conflicting occurrences</span>
                        <strong>{counts.conflicts}</strong>
                      </PreviewMetric>
                      <PreviewMetric>
                        <span>Validation issues</span>
                        <strong>{counts.issues}</strong>
                      </PreviewMetric>
                    </PreviewGrid>
                    {previewState.preview.issues.length > 0 && (
                      <Issues>
                        {previewState.preview.issues.map((issue, index) => (
                          <Issue
                            key={`${issue.code}:${issue.occurrence_key || index}`}
                          >
                            <strong>{issue.code.replaceAll("_", " ")}</strong>
                            <br />
                            {issue.message}
                          </Issue>
                        ))}
                      </Issues>
                    )}
                  </>
                );
              })()}
            <WorkforceDialogActions>
              <ActionButton
                type="button"
                onClick={() => setPreviewState(null)}
                disabled={Boolean(busy) || previewState.retryLocked}
              >
                Close
              </ActionButton>
              {!previewState.retryLocked && (
                <ActionButton type="submit" disabled={Boolean(busy)}>
                  <EyeIcon /> {busy === "preview" ? "Checking…" : "Run preview"}
                </ActionButton>
              )}
              {previewState.preview?.can_generate &&
                previewState.preview.occurrences.length > 0 && (
                  <ActionButton
                    type="button"
                    $variant="primary"
                    onClick={() => void generate()}
                    disabled={Boolean(busy)}
                  >
                    <SquaresPlusIcon />{" "}
                    {busy === "generate"
                      ? "Generating…"
                      : previewState.retryLocked
                        ? "Retry exact generation"
                        : `Generate ${previewState.preview.total} drafts`}
                  </ActionButton>
                )}
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}
    </Section>
  );
}
