import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowPathIcon,
  BeakerIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  PlusIcon,
  ShieldCheckIcon,
  UserGroupIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import { useSearchParams } from "react-router-dom";
import { ACCESS, hasPermission } from "../../auth/accessModel";
import { useSession } from "../../auth/SessionContext";
import {
  ActionButton,
  Eyebrow,
  IconButton,
  StatusChip,
} from "../../components/ui/Primitives";
import { serviceDateValue } from "../../hooks/useCommandData";
import ChildAvatar from "../children/ChildAvatar";
import { childNameParts, formatCareTime } from "../daily-care/careModel";
import { fetchRoomWorkspace, type RoomWorkspace } from "../rooms/roomsApi";
import {
  CardActions,
  CardGrid,
  CardHeader,
  DetailGrid,
  EmptyState,
  FilterButton,
  FilterRow,
  MetricCard,
  MetricGrid,
  OperationCard,
  OperationField,
  OperationHeader,
  OperationNotice,
  OperationPage,
  PrivateMark,
  ScopePanel,
  SearchField,
  Toolbar,
} from "../safety-operations/OperationStyles";
import {
  activateMedicationPlan,
  createMedicationPlan,
  fetchMedicationRoomDay,
  fetchMedicationPlan,
  recordMedicationAdministration,
  recordMedicationAuthorization,
  updateMedicationPlan,
  type MedicationDayChild,
  type MedicationAdministration,
  type MedicationPlan,
  type MedicationRoomDay,
} from "./medicationApi";
import {
  clearNotificationTarget,
  isSafeNotificationTargetId,
} from "../notifications/notificationTarget";
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  MedicationActivationDialog,
  MedicationAdministrationDialog,
  MedicationAuthorizationDialog,
  MedicationHistoryDialog,
  MedicationPlanDialog,
  type MedicationAdministrationDraft,
  type MedicationAuthorizationDraft,
  type MedicationPlanDraft,
} from "./MedicationDialogs";
import {
  activeAdministrations,
  authorizationEvidenceLabel,
  canRecordMedication,
  childMedicationMatches,
  medicationDayCounts,
  medicationDueItems,
  medicationOutcomeLabel,
  medicationOutcomeTone,
  medicationPlanGate,
  medicationPlanGateLabel,
  medicationPlanGateTone,
} from "./medicationModel";
import { fetchMedicationRealtimeSnapshot } from "./medicationRealtime";

const Identity = styled.div`
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
  h2 {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
`;

const PlanStack = styled.div`
  display: grid;
  gap: 10px;
`;
const PlanPanel = styled.section`
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px 5px 13px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
`;
const PlanHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  h3 {
    margin: 0;
    font-size: 0.78rem;
    font-weight: 650;
  }
  p {
    margin: 4px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.66rem;
    line-height: 1.5;
  }
  @media (max-width: 520px) {
    flex-direction: column;
  }
`;
const DueList = styled.ol`
  display: grid;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
`;
const DueRow = styled.li`
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  min-height: 54px;
  padding: 8px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 11px 5px 11px 5px;
  background: ${({ theme }) => theme.color.surface};
  > svg {
    width: 17px;
    margin: auto;
    color: ${({ theme }) => theme.color.cyan};
  }
  strong {
    display: block;
    font-size: 0.71rem;
    font-weight: 620;
  }
  p {
    margin: 3px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.64rem;
    line-height: 1.45;
  }
  @media (max-width: 520px) {
    grid-template-columns: 32px minmax(0, 1fr);
    > button {
      grid-column: 1 / -1;
      width: 100%;
    }
  }
`;
const History = styled.div`
  display: grid;
  gap: 7px;
  h3 {
    margin: 0;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.7rem;
    font-weight: 650;
  }
`;
const FocusedPlanPanel = styled(PlanPanel)`
  border-color: ${({ theme }) => theme.color.cyan};
  box-shadow: 0 0 0 2px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 20%, transparent), ${({ theme }) => theme.shadow.panel};
  outline: none;
`;

type MedicationDialog =
  | { kind: "plan"; child: MedicationDayChild; plan?: MedicationPlan }
  | { kind: "authorization"; child: MedicationDayChild; plan: MedicationPlan }
  | { kind: "activate"; child: MedicationDayChild; plan: MedicationPlan }
  | {
      kind: "administration";
      child: MedicationDayChild;
      plan: MedicationPlan;
      dueTime: string | null;
    }
  | { kind: "history"; subject: MedicationPlan | MedicationAdministration }
  | null;

interface DayResource {
  key: string;
  status: "idle" | "loading" | "refreshing" | "ready" | "error";
  data: MedicationRoomDay | null;
  error: string;
}

function formatServiceDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("en-CA", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day, 12)));
}

export default function MedicationPage() {
  const session = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const organizationReady =
    session.status === "authenticated" &&
    Boolean(session.organization?.id) &&
    session.organization?.id === session.user?.organization_id &&
    !session.organizationUnavailable;
  const organizationId = organizationReady ? session.organization!.id : "";
  const organizationWide =
    session.user?.role.key === "owner" ||
    session.user?.role.key === "administrator";
  const [workspace, setWorkspace] = useState<RoomWorkspace | null>(null);
  const [workspaceStatus, setWorkspaceStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [workspaceError, setWorkspaceError] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [date, setDate] = useState(() =>
    serviceDateValue(
      new Date(),
      session.organization?.timezone || "America/Edmonton",
    ),
  );
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [resource, setResource] = useState<DayResource>({
    key: "",
    status: "idle",
    data: null,
    error: "",
  });
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "due" | "blocked">("all");
  const [dialog, setDialog] = useState<MedicationDialog>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState<{
    error: boolean;
    message: string;
  } | null>(null);
  const [focusedPlan, setFocusedPlan] = useState<MedicationPlan | null>(null);
  const [focusedPlanLoading, setFocusedPlanLoading] = useState(false);
  const focusedPlanRef = useRef<MedicationPlan | null>(null);
  focusedPlanRef.current = focusedPlan;
  const planTargetLookup = useRef("");
  const requestedPlanId = searchParams.get("plan");

  useEffect(() => {
    if (!requestedPlanId) {
      planTargetLookup.current = "";
      return;
    }
    if (!organizationReady || !organizationId) return;
    const lookupKey = `${organizationId}:${requestedPlanId}`;
    if (planTargetLookup.current === lookupKey) return;
    planTargetLookup.current = lookupKey;
    const clearTarget = () =>
      setSearchParams(
        (current) => clearNotificationTarget(current, "plan"),
        { replace: true },
      );
    if (
      searchParams.getAll("plan").length !== 1 ||
      !isSafeNotificationTargetId(requestedPlanId)
    ) {
      setFocusedPlan(null);
      setNotice({
        error: true,
        message: "The notification contained an invalid medication-plan target. No plan was opened.",
      });
      clearTarget();
      return;
    }
    const controller = new AbortController();
    setFocusedPlanLoading(true);
    void fetchMedicationPlan(requestedPlanId, organizationId, controller.signal)
      .then((plan) => {
        if (controller.signal.aborted) return;
        setFocusedPlan(plan);
        setNotice({
          error: false,
          message: `Opened ${plan.child_name}’s ${plan.medication_name} plan from a fresh authorized server read. Room and date filters were not inferred from the notification.`,
        });
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setFocusedPlan(null);
        setNotice({
          error: true,
          message:
            caught instanceof Error
              ? `The requested medication plan could not be safely opened. ${caught.message}`
              : "The requested medication plan could not be safely opened.",
        });
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        setFocusedPlanLoading(false);
        clearTarget();
      });
    return () => {
      controller.abort();
      if (planTargetLookup.current === lookupKey) planTargetLookup.current = "";
    };
  }, [organizationId, organizationReady, requestedPlanId, searchParams, setSearchParams]);

  useEffect(() => {
    if (!focusedPlan) return;
    const frame = requestAnimationFrame(() => {
      const panel = document.querySelector<HTMLElement>(
        `[data-medication-plan-id="${CSS.escape(focusedPlan.id)}"]`,
      );
      panel?.scrollIntoView({ behavior: "smooth", block: "center" });
      panel?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusedPlan]);

  const loadWorkspace = useCallback(
    (signal?: AbortSignal) => {
      if (!organizationId) return Promise.resolve();
      setWorkspaceStatus("loading");
      setWorkspaceError("");
      return fetchRoomWorkspace(organizationId, signal)
        .then((next) => {
          if (!signal?.aborted) {
            setWorkspace(next);
            setWorkspaceStatus("ready");
          }
        })
        .catch((caught) => {
          if (!signal?.aborted) {
            setWorkspace(null);
            setWorkspaceStatus("error");
            setWorkspaceError(
              caught instanceof Error
                ? caught.message
                : "Assigned rooms could not be loaded.",
            );
          }
        });
    },
    [organizationId],
  );

  useEffect(() => {
    const controller = new AbortController();
    if (organizationReady) void loadWorkspace(controller.signal);
    else {
      setWorkspace(null);
      setWorkspaceStatus("idle");
    }
    return () => controller.abort();
  }, [loadWorkspace, organizationReady]);
  const facilities = useMemo(
    () =>
      (workspace?.facilities || []).filter(
        (facility) =>
          facility.status === "active" &&
          workspace?.rooms.some(
            (room) => room.is_active && room.facility_id === facility.id,
          ),
      ),
    [workspace],
  );
  useEffect(
    () =>
      setFacilityId((current) =>
        facilities.some((facility) => facility.id === current)
          ? current
          : facilities[0]?.id || "",
      ),
    [facilities],
  );
  const rooms = useMemo(
    () =>
      (workspace?.rooms || []).filter(
        (room) => room.is_active && room.facility_id === facilityId,
      ),
    [facilityId, workspace],
  );
  useEffect(
    () =>
      setRoomId((current) =>
        rooms.some((room) => room.id === current)
          ? current
          : rooms[0]?.id || "",
      ),
    [rooms],
  );
  const facility = facilities.find((item) => item.id === facilityId);
  const room = rooms.find((item) => item.id === roomId);
  const today = serviceDateValue(
    new Date(),
    facility?.timezone || session.organization?.timezone || "America/Edmonton",
  );
  useEffect(() => {
    if (facility)
      setDate((current) =>
        !organizationWide || current > today ? today : current,
      );
  }, [facility, organizationWide, today]);

  const dayKey =
    organizationId && facilityId && roomId && date
      ? `${organizationId}:${facilityId}:${roomId}:${date}`
      : "";
  useRealtimeRefresh({ scope: 'medications', organizationId, enabled: organizationReady, entityTypes: featureIntegrationManifest.medications.realtimeEntities, refresh: async () => {
    const focusedPlanId = focusedPlanRef.current?.id || null;
    let snapshot;
    try {
      snapshot = await fetchMedicationRealtimeSnapshot({
        organizationId, facilityId, roomId, date, focusedPlanId,
      });
    } catch (caught) {
      if (focusedPlanId && focusedPlanRef.current?.id === focusedPlanId) {
        setFocusedPlan(null);
        setNotice({
          error: true,
          message: caught instanceof Error
            ? `The exact medication plan could not be refreshed safely. ${caught.message}`
            : 'The exact medication plan could not be refreshed safely.',
        });
      }
      throw caught;
    }
    setWorkspace(snapshot.workspace); setWorkspaceStatus('ready'); setFacilityId(snapshot.facilityId); setRoomId(snapshot.roomId);
    setResource(snapshot.day ? { key: snapshot.key, status: 'ready', data: snapshot.day, error: '' } : { key: '', status: 'idle', data: null, error: '' });
    if (focusedPlanId && focusedPlanRef.current?.id === focusedPlanId && snapshot.focusedPlan) {
      setFocusedPlan(snapshot.focusedPlan);
    }
  } });
  useEffect(() => {
    if (!dayKey) {
      setResource({ key: "", status: "idle", data: null, error: "" });
      return;
    }
    const controller = new AbortController();
    setResource((current) =>
      current.key === dayKey && current.data
        ? { ...current, status: "refreshing", error: "" }
        : { key: dayKey, status: "loading", data: null, error: "" },
    );
    fetchMedicationRoomDay(
      roomId,
      date,
      organizationId,
      facilityId,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted)
          setResource({ key: dayKey, status: "ready", data, error: "" });
      })
      .catch((caught) => {
        if (!controller.signal.aborted)
          setResource({
            key: dayKey,
            status: "error",
            data: null,
            error:
              caught instanceof Error
                ? caught.message
                : "The medication workspace could not be loaded.",
          });
      });
    return () => controller.abort();
  }, [date, dayKey, facilityId, organizationId, refreshVersion, roomId]);

  const day = resource.key === dayKey ? resource.data : null;
  const status = resource.key === dayKey ? resource.status : "loading";
  const counts = medicationDayCounts(day?.children || [], date);
  const canManage = hasPermission(session.user, ACCESS.medicationManage);
  const canRecord = hasPermission(session.user, ACCESS.medicationRecord);
  const focusedPlanFacility = workspace?.facilities.find(
    (item) => item.id === focusedPlan?.facility_id,
  );
  const focusedPlanToday = serviceDateValue(
    new Date(),
    focusedPlanFacility?.timezone ||
      session.organization?.timezone ||
      "America/Edmonton",
  );
  const filteredChildren = useMemo(
    () =>
      (day?.children || []).filter((child) => {
        if (!childMedicationMatches(child, query)) return false;
        if (filter === "due")
          return medicationDueItems(child, date).some(
            (item) => item.kind === "scheduled" && !item.administration,
          );
        if (filter === "blocked")
          return child.plans.some((plan) =>
            medicationPlanGate(plan, date).startsWith("authorization_"),
          );
        return true;
      }),
    [date, day, filter, query],
  );

  const refresh = (message: string) => {
    setDialog(null);
    setNotice({ error: false, message });
    setRefreshVersion((value) => value + 1);
  };
  const savePlan = async (
    state: Extract<MedicationDialog, { kind: "plan" }>,
    draft: MedicationPlanDraft,
  ) => {
    setBusy(`plan:${state.child.child_id}`);
    setNotice(null);
    const input = {
      medication_name: draft.medicationName,
      dosage: draft.dosage,
      route: draft.route,
      label_directions: draft.labelDirections,
      scheduled_times: draft.scheduledTimes,
      as_needed: draft.asNeeded,
      start_date: draft.startDate,
      end_date: draft.endDate,
      medication_kind: draft.medicationKind,
      storage_method: draft.storageMethod,
      storage_instructions: draft.storageInstructions,
      emergency_plan_reference: draft.emergencyPlanReference,
      client_operation_id: draft.clientOperationId,
    };
    try {
      if (state.plan)
        await updateMedicationPlan(
          state.plan.id,
          {
            ...input,
            facility_id: facilityId,
            child_id: state.child.child_id,
            expected_version: state.plan.version,
            reason: draft.reason || "Medication plan updated",
          },
          organizationId,
          facilityId,
          state.child.child_id,
        );
      else
        await createMedicationPlan(
          { ...input, facility_id: facilityId, child_id: state.child.child_id },
          organizationId,
        );
      refresh(
        `${state.child.child_name}’s medication plan was saved as an internal draft.`,
      );
    } finally {
      setBusy("");
    }
  };
  const saveAuthorization = async (
    state: Extract<MedicationDialog, { kind: "authorization" }>,
    draft: MedicationAuthorizationDraft,
  ) => {
    setBusy(`authorization:${state.plan.id}`);
    setNotice(null);
    try {
      await recordMedicationAuthorization(state.plan, {
        guardian_id: draft.guardianId,
        signed_authorization_reference: draft.reference,
        authorization_signed_at: draft.signedAt,
        valid_until: draft.validUntil,
        expected_version: state.plan.version,
        client_operation_id: draft.clientOperationId,
      });
      refresh(
        "Reviewed signed consent evidence was recorded separately from profile markers.",
      );
    } finally {
      setBusy("");
    }
  };
  const saveActivation = async (
    state: Extract<MedicationDialog, { kind: "activate" }>,
    operationId: string,
  ) => {
    setBusy(`activate:${state.plan.id}`);
    setNotice(null);
    try {
      await activateMedicationPlan(state.plan, operationId);
      refresh(
        "The medication plan is active after signed-evidence and physical-label verification.",
      );
    } finally {
      setBusy("");
    }
  };
  const saveAdministration = async (
    state: Extract<MedicationDialog, { kind: "administration" }>,
    draft: MedicationAdministrationDraft,
  ) => {
    if (!state.child.attendance_day_id)
      throw new Error("A verified attendance day is required.");
    setBusy(`administration:${state.plan.id}:${state.dueTime || "prn"}`);
    setNotice(null);
    try {
      await recordMedicationAdministration(
        {
          medication_plan_id: state.plan.id,
          attendance_day_id: state.child.attendance_day_id,
          outcome: draft.outcome,
          scheduled_for: draft.scheduledFor,
          occurred_at: draft.occurredAt,
          amount: draft.amount,
          reason: draft.reason,
          note: draft.note,
          client_operation_id: draft.clientOperationId,
        },
        {
          organizationId,
          facilityId,
          roomId,
          childId: state.child.child_id,
          attendanceDayId: state.child.attendance_day_id,
          serviceDate: date,
        },
      );
      refresh(
        `${state.child.child_name}’s observed medication outcome was recorded with the plan snapshot.`,
      );
    } finally {
      setBusy("");
    }
  };

  if (!organizationReady)
    return (
      <EmptyState>
        <div>
          <ExclamationTriangleIcon />
          <h2>Confirmed organization required.</h2>
          <p>
            Medication records stay unavailable until the signed-in account and
            organization context agree.
          </p>
        </div>
      </EmptyState>
    );

  return (
    <OperationPage>
      <OperationHeader>
        <div>
          <Eyebrow>
            <BeakerIcon width={14} /> Medication operations
          </Eyebrow>
          <h1>Evidence before action.</h1>
          <p>
            Keep written consent, the original label, the child’s actual
            attendance, and every observed outcome connected without turning
            profile notes into authorization or offering medical advice.
          </p>
        </div>
        <PrivateMark>
          <i /> Role-scoped · private, no-store
        </PrivateMark>
      </OperationHeader>
      <OperationNotice $warning>
        <ShieldCheckIcon /> Medication is only recorded under a current active
        plan with reviewed signed-consent evidence and verified original-label
        facts. CareSync never recommends a drug, dosage, route, or decision to
        administer.
      </OperationNotice>
      {focusedPlanLoading && (
        <OperationNotice role="status" aria-live="polite">
          <ArrowPathIcon /> Resolving the exact medication plan from the canonical server record…
        </OperationNotice>
      )}
      {focusedPlan && (
        <FocusedPlanPanel
          data-medication-plan-id={focusedPlan.id}
          tabIndex={-1}
          aria-label={`Focused medication plan for ${focusedPlan.child_name}`}
        >
          <PlanHeader>
            <div>
              <h3>{focusedPlan.child_name} · {focusedPlan.medication_name}</h3>
              <p>
                {focusedPlan.dosage} · {focusedPlan.route} · {focusedPlanFacility?.name || "Authorized facility"}. This exact plan was re-read independently of the room-day workspace below.
              </p>
            </div>
            <StatusChip $tone={medicationPlanGateTone(medicationPlanGate(focusedPlan, focusedPlanToday))}>
              {medicationPlanGateLabel(medicationPlanGate(focusedPlan, focusedPlanToday))}
            </StatusChip>
          </PlanHeader>
          <CardActions>
            <ActionButton
              type="button"
              onClick={() => setDialog({ kind: "history", subject: focusedPlan })}
            >
              <ClockIcon /> Plan history
            </ActionButton>
            <ActionButton type="button" onClick={() => setFocusedPlan(null)}>
              Clear exact focus
            </ActionButton>
          </CardActions>
        </FocusedPlanPanel>
      )}
      <ScopePanel $accent="cyan">
        <OperationField>
          <span>Facility</span>
          <select
            aria-label="Medication facility"
            value={facilityId}
            onChange={(event) => {
              setFacilityId(event.target.value);
              setNotice(null);
            }}
          >
            {facilities.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </OperationField>
        <OperationField>
          <span>Assigned room</span>
          <select
            aria-label="Medication room"
            value={roomId}
            onChange={(event) => {
              setRoomId(event.target.value);
              setNotice(null);
            }}
          >
            {rooms.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </OperationField>
        <OperationField>
          <span>Service date</span>
          <input
            aria-label="Medication service date"
            type="date"
            max={today}
            disabled={!organizationWide}
            value={date}
            onChange={(event) => {
              setDate(event.target.value);
              setNotice(null);
            }}
          />
        </OperationField>
        <IconButton
          type="button"
          aria-label="Refresh medication workspace"
          onClick={() => setRefreshVersion((value) => value + 1)}
          disabled={!dayKey || status === "loading" || status === "refreshing"}
        >
          <ArrowPathIcon />
        </IconButton>
      </ScopePanel>
      {workspaceStatus === "loading" && (
        <OperationNotice role="status" aria-live="polite">
          <ArrowPathIcon /> Loading assigned facilities and rooms…
        </OperationNotice>
      )}
      {workspaceStatus === "error" && (
        <OperationNotice $error role="alert">
          <ExclamationTriangleIcon />{" "}
          <span>
            {workspaceError}{" "}
            <button type="button" onClick={() => void loadWorkspace()}>
              Try again
            </button>
          </span>
        </OperationNotice>
      )}
      {status === "loading" && dayKey && (
        <OperationNotice role="status" aria-live="polite">
          <ArrowPathIcon /> Loading medication work for{" "}
          {formatServiceDate(date)}…
        </OperationNotice>
      )}
      {status === "error" && (
        <OperationNotice $error role="alert">
          <ExclamationTriangleIcon />{" "}
          <span>
            {resource.error}{" "}
            <button
              type="button"
              onClick={() => setRefreshVersion((value) => value + 1)}
            >
              Try again
            </button>
          </span>
        </OperationNotice>
      )}
      {day && (
        <>
          <MetricGrid aria-label="Medication day summary">
            <MetricCard>
              <span>
                <UserGroupIcon /> Room children
              </span>
              <strong>{counts.children}</strong>
            </MetricCard>
            <MetricCard>
              <span>
                <ShieldCheckIcon /> Ready plans
              </span>
              <strong>{counts.activePlans}</strong>
            </MetricCard>
            <MetricCard>
              <span>
                <ClockIcon /> Scheduled today
              </span>
              <strong>{counts.due}</strong>
            </MetricCard>
            <MetricCard>
              <span>
                <CheckCircleIcon /> Recorded outcomes
              </span>
              <strong>{counts.recorded}</strong>
            </MetricCard>
          </MetricGrid>
          <Toolbar>
            <SearchField>
              <MagnifyingGlassIcon />
              <input
                aria-label="Search medication children and plans"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search children or medication plans"
              />
            </SearchField>
            <FilterRow>
              <FilterButton
                type="button"
                $active={filter === "all"}
                aria-pressed={filter === "all"}
                onClick={() => setFilter("all")}
              >
                All
              </FilterButton>
              <FilterButton
                type="button"
                $active={filter === "due"}
                aria-pressed={filter === "due"}
                onClick={() => setFilter("due")}
              >
                Unrecorded schedule
              </FilterButton>
              <FilterButton
                type="button"
                $active={filter === "blocked"}
                aria-pressed={filter === "blocked"}
                onClick={() => setFilter("blocked")}
              >
                Consent attention {counts.blocked}
              </FilterButton>
            </FilterRow>
          </Toolbar>
          <div aria-live="polite">
            {status === "refreshing" && (
              <OperationNotice role="status">
                <ArrowPathIcon /> Refreshing medication facts without
                interrupting your work…
              </OperationNotice>
            )}
            {notice && (
              <OperationNotice
                $error={notice.error}
                role={notice.error ? "alert" : "status"}
              >
                {notice.error ? (
                  <ExclamationTriangleIcon />
                ) : (
                  <CheckCircleIcon />
                )}{" "}
                {notice.message}
              </OperationNotice>
            )}
          </div>
          {filteredChildren.length ? (
            <CardGrid>
              {filteredChildren.map((child) => {
                const name = childNameParts(child.child_name);
                const dueItems = medicationDueItems(child, date);
                const administrations = activeAdministrations(
                  child.administrations,
                );
                return (
                  <OperationCard
                    key={child.child_id}
                    $accent={
                      child.plans.some((plan) =>
                        medicationPlanGate(plan, date).startsWith(
                          "authorization_",
                        ),
                      )
                        ? "amber"
                        : "cyan"
                    }
                  >
                    <CardHeader>
                      <Identity>
                        <ChildAvatar
                          firstName={name.firstName}
                          lastName={name.lastName}
                          photoUrl={child.profile_photo_url}
                          size={46}
                        />
                        <div>
                          <h2>{child.child_name}</h2>
                          <p>
                            {child.attendance_state === "on_site"
                              ? "On site"
                              : child.attendance_state === "checked_out"
                                ? "Checked out"
                                : child.attendance_state === "no_show"
                                  ? "No-show"
                                  : "Attendance not recorded"}{" "}
                            · {child.plans.length} plan
                            {child.plans.length === 1 ? "" : "s"}
                          </p>
                        </div>
                      </Identity>
                      {canManage && (
                        <ActionButton
                          type="button"
                          onClick={() => setDialog({ kind: "plan", child })}
                        >
                          <PlusIcon /> New plan
                        </ActionButton>
                      )}
                    </CardHeader>
                    {child.plans.length ? (
                      <PlanStack>
                        {child.plans.map((plan) => {
                          const gate = medicationPlanGate(plan, date);
                          const planDue = dueItems.filter(
                            (item) => item.plan.id === plan.id,
                          );
                          return (
                            <PlanPanel key={plan.id}>
                              <PlanHeader>
                                <div>
                                  <h3>
                                    {plan.medication_name} · {plan.dosage}
                                  </h3>
                                  <p>
                                    {plan.route.replaceAll("_", " ")} ·{" "}
                                    {plan.as_needed
                                      ? "as-needed enabled"
                                      : "scheduled only"}{" "}
                                    · {authorizationEvidenceLabel(plan, date)}
                                  </p>
                                </div>
                                <StatusChip
                                  $tone={medicationPlanGateTone(gate)}
                                >
                                  {medicationPlanGateLabel(gate)}
                                </StatusChip>
                              </PlanHeader>
                              <DetailGrid>
                                <div>
                                  <dt>Original label directions</dt>
                                  <dd>{plan.label_directions}</dd>
                                </div>
                                <div>
                                  <dt>Storage fact</dt>
                                  <dd>
                                    {plan.medication_kind === "emergency"
                                      ? "Emergency access per agreed plan"
                                      : "Locked and inaccessible"}{" "}
                                    · {plan.storage_instructions}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Plan dates</dt>
                                  <dd>
                                    {plan.start_date}–
                                    {plan.end_date || "open end"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Signed evidence</dt>
                                  <dd>
                                    {authorizationEvidenceLabel(plan, date)}
                                    {plan.authorization_status === "verified"
                                      ? ` · ${plan.authorization_guardian_name} · ${plan.signed_authorization_reference}`
                                      : ""}
                                  </dd>
                                </div>
                              </DetailGrid>
                              {planDue.length > 0 && (
                                <DueList>
                                  {planDue.map((item) => (
                                    <DueRow key={item.key}>
                                      <ClockIcon />
                                      <div>
                                        <strong>
                                          {item.dueTime
                                            ? `Scheduled ${item.dueTime}`
                                            : "As-needed recording"}
                                        </strong>
                                        <p>
                                          {item.administration
                                            ? `${medicationOutcomeLabel(item.administration.outcome)} at ${formatCareTime(item.administration.occurred_at, day.facility_timezone)} by ${item.administration.staff_name_snapshot} (${item.administration.staff_initials_snapshot})`
                                            : item.kind === "scheduled"
                                              ? "No observed outcome recorded for this schedule slot"
                                              : "Use only after a real as-needed event under the active plan"}
                                        </p>
                                      </div>
                                      {!item.administration &&
                                        canRecord &&
                                        canRecordMedication(
                                          child,
                                          plan,
                                          date,
                                        ) && (
                                          <ActionButton
                                            type="button"
                                            $variant="primary"
                                            onClick={() =>
                                              setDialog({
                                                kind: "administration",
                                                child,
                                                plan,
                                                dueTime: item.dueTime,
                                              })
                                            }
                                          >
                                            Record outcome
                                          </ActionButton>
                                        )}
                                      {item.administration && (
                                        <StatusChip
                                          $tone={medicationOutcomeTone(
                                            item.administration.outcome,
                                          )}
                                        >
                                          {medicationOutcomeLabel(
                                            item.administration.outcome,
                                          )}
                                        </StatusChip>
                                      )}
                                    </DueRow>
                                  ))}
                                </DueList>
                              )}
                              <CardActions>
                                {canManage && plan.status !== "archived" && (
                                  <ActionButton
                                    type="button"
                                    onClick={() =>
                                      setDialog({ kind: "plan", child, plan })
                                    }
                                  >
                                    <PencilSquareIcon /> Edit plan
                                  </ActionButton>
                                )}
                                {canManage &&
                                  plan.status === "draft" &&
                                  plan.authorization_status !== "verified" && (
                                    <ActionButton
                                      type="button"
                                      onClick={() =>
                                        setDialog({
                                          kind: "authorization",
                                          child,
                                          plan,
                                        })
                                      }
                                    >
                                      <ShieldCheckIcon /> Record signed evidence
                                    </ActionButton>
                                  )}
                                {canManage &&
                                  plan.status === "draft" &&
                                  plan.authorization_status === "verified" &&
                                  plan.authorization_is_current && (
                                    <ActionButton
                                      type="button"
                                      $variant="primary"
                                      onClick={() =>
                                        setDialog({
                                          kind: "activate",
                                          child,
                                          plan,
                                        })
                                      }
                                    >
                                      <CheckCircleIcon /> Verify and activate
                                    </ActionButton>
                                  )}
                                <ActionButton
                                  type="button"
                                  onClick={() =>
                                    setDialog({
                                      kind: "history",
                                      subject: plan,
                                    })
                                  }
                                >
                                  <ClockIcon /> Plan history
                                </ActionButton>
                              </CardActions>
                            </PlanPanel>
                          );
                        })}
                      </PlanStack>
                    ) : (
                      <OperationNotice>
                        <BeakerIcon /> No medication plan is recorded for this
                        child.
                      </OperationNotice>
                    )}
                    {administrations.length > 0 && (
                      <History>
                        <h3>Observed outcomes · immutable plan snapshots</h3>
                        {administrations.slice(0, 5).map((record) => (
                          <DueRow key={record.id}>
                            <BeakerIcon />
                            <div>
                              <strong>
                                {record.plan_snapshot.medication_name} ·{" "}
                                {medicationOutcomeLabel(record.outcome)}
                              </strong>
                              <p>
                                {formatCareTime(
                                  record.occurred_at,
                                  day.facility_timezone,
                                )}{" "}
                                · {record.amount || record.reason} ·{" "}
                                {record.staff_name_snapshot} (
                                {record.staff_initials_snapshot})
                              </p>
                            </div>
                            <ActionButton
                              type="button"
                              onClick={() =>
                                setDialog({ kind: "history", subject: record })
                              }
                            >
                              History
                            </ActionButton>
                          </DueRow>
                        ))}
                      </History>
                    )}
                  </OperationCard>
                );
              })}
            </CardGrid>
          ) : (
            <EmptyState>
              <div>
                <MagnifyingGlassIcon />
                <h2>No medication work matches this view.</h2>
                <p>
                  Change the search or filter. CareSync never invents a plan,
                  child, consent record, or administration outcome.
                </p>
              </div>
            </EmptyState>
          )}
        </>
      )}
      {dialog?.kind === "plan" && (
        <MedicationPlanDialog
          key={`${dialog.child.child_id}:${dialog.plan?.id || "new"}:${dialog.plan?.version || 0}`}
          childName={dialog.child.child_name}
          serviceDate={date}
          plan={dialog.plan}
          busy={busy === `plan:${dialog.child.child_id}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(draft) => savePlan(dialog, draft)}
        />
      )}
      {dialog?.kind === "authorization" && day && (
        <MedicationAuthorizationDialog
          key={`${dialog.plan.id}:${dialog.plan.version}`}
          plan={dialog.plan}
          childName={dialog.child.child_name}
          guardians={dialog.child.eligible_guardians}
          timeZone={day.facility_timezone}
          busy={busy === `authorization:${dialog.plan.id}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(draft) => saveAuthorization(dialog, draft)}
        />
      )}
      {dialog?.kind === "activate" && (
        <MedicationActivationDialog
          key={`${dialog.plan.id}:${dialog.plan.version}`}
          plan={dialog.plan}
          childName={dialog.child.child_name}
          busy={busy === `activate:${dialog.plan.id}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(operationId) => saveActivation(dialog, operationId)}
        />
      )}
      {dialog?.kind === "administration" && day && (
        <MedicationAdministrationDialog
          key={`${dialog.plan.id}:${dialog.dueTime || "prn"}`}
          plan={dialog.plan}
          childName={dialog.child.child_name}
          dueTime={dialog.dueTime}
          timeZone={day.facility_timezone}
          busy={
            busy ===
            `administration:${dialog.plan.id}:${dialog.dueTime || "prn"}`
          }
          onClose={() => !busy && setDialog(null)}
          onSave={(draft) => saveAdministration(dialog, draft)}
        />
      )}
      {dialog?.kind === "history" && (
        <MedicationHistoryDialog
          subject={dialog.subject}
          timeZone={
            workspace?.facilities.find(
              (item) => item.id === dialog.subject.facility_id,
            )?.timezone || day?.facility_timezone || session.organization?.timezone || "America/Edmonton"
          }
          onClose={() => setDialog(null)}
        />
      )}
    </OperationPage>
  );
}
