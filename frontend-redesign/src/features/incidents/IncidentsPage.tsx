import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  PlusIcon,
  ShieldExclamationIcon,
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
import { formatCareTime } from "../daily-care/careModel";
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
  createIncident,
  fetchIncident,
  fetchIncidentRoomContext,
  fetchIncidents,
  finalizeIncident,
  recordExternalReport,
  returnIncidentToDraft,
  submitIncidentForReview,
  updateIncident,
  type IncidentAssessment,
  type IncidentList,
  type IncidentRecord,
  type IncidentRoomContext,
  type IncidentStatus,
} from "./incidentApi";
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  clearNotificationTarget,
  isSafeNotificationTargetId,
} from '../notifications/notificationTarget';
import {
  ExternalReportDialog,
  IncidentDraftDialog,
  IncidentFinalizeDialog,
  IncidentHistoryDialog,
  IncidentSubmitReviewDialog,
  ReturnIncidentDialog,
  type ExternalReportDraft,
  type IncidentDraft,
} from "./IncidentDialogs";
import {
  canEditIncident,
  canRecordExternalReport,
  externalReportLabel,
  incidentAssessmentLabel,
  incidentCounts,
  incidentMatches,
  incidentSeverityLabel,
  incidentStatusLabel,
  incidentStatusTone,
  reportGuidance,
} from "./incidentModel";

const Summary = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: 0.75rem;
  line-height: 1.62;
`;

const IncidentCard = styled(OperationCard)<{ $focused?: boolean }>`
  ${({ $focused, theme }) => $focused ? `
    border-color: ${theme.color.cyan};
    box-shadow: 0 0 0 2px color-mix(in srgb, ${theme.color.cyan} 24%, transparent), ${theme.shadow.panel};
  ` : ''}
`;

type IncidentDialog =
  | { kind: "draft"; incident?: IncidentRecord }
  | { kind: "review"; incident: IncidentRecord }
  | { kind: "return"; incident: IncidentRecord }
  | { kind: "finalize"; incident: IncidentRecord }
  | { kind: "external"; incident: IncidentRecord }
  | { kind: "history"; incident: IncidentRecord }
  | null;

interface Resource {
  key: string;
  status: "idle" | "loading" | "refreshing" | "ready" | "error";
  context: IncidentRoomContext | null;
  list: IncidentList | null;
  error: string;
}

export default function IncidentsPage() {
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
  const [resource, setResource] = useState<Resource>({
    key: "",
    status: "idle",
    context: null,
    list: null,
    error: "",
  });
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<
    "all" | IncidentStatus | "external_pending"
  >("all");
  const [dialog, setDialog] = useState<IncidentDialog>(null);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState<{
    error: boolean;
    message: string;
  } | null>(null);
  const [focusedIncidentId, setFocusedIncidentId] = useState<string | null>(null);
  const targetLookup = useRef("");

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

  const requestedIncidentId = searchParams.get("incident");
  useEffect(() => {
    if (!requestedIncidentId) {
      targetLookup.current = "";
      return;
    }
    if (!organizationReady || workspaceStatus !== "ready" || !workspace) return;
    const lookupKey = `${organizationId}:${requestedIncidentId}`;
    if (targetLookup.current === lookupKey) return;
    targetLookup.current = lookupKey;
    const clearTarget = () =>
      setSearchParams(
        (current) => clearNotificationTarget(current, "incident"),
        { replace: true },
      );
    if (!isSafeNotificationTargetId(requestedIncidentId)) {
      setFocusedIncidentId(null);
      setNotice({
        error: true,
        message:
          "The notification contained an invalid incident target. The current incident workspace is shown instead.",
      });
      clearTarget();
      return;
    }
    const controller = new AbortController();
    void fetchIncident(requestedIncidentId, organizationId, controller.signal)
      .then((incident) => {
        if (controller.signal.aborted) return;
        const facilityAvailable = workspace.facilities.some(
          (item) => item.status === "active" && item.id === incident.facility_id,
        );
        const roomAvailable = workspace.rooms.some(
          (item) =>
            item.is_active &&
            item.id === incident.room_id &&
            item.facility_id === incident.facility_id,
        );
        if (!facilityAvailable || !roomAvailable) {
          setFocusedIncidentId(null);
          setNotice({
            error: false,
            message:
              "That incident is no longer available in your active facility and room scope. The current incident workspace is shown instead.",
          });
          return;
        }
        setFacilityId(incident.facility_id);
        setRoomId(incident.room_id);
        setDate(incident.service_date);
        setQuery("");
        setFilter("all");
        setFocusedIncidentId(incident.id);
        setDialog({ kind: "history", incident });
        setNotice({
          error: false,
          message: `Opened ${incident.child_name || "the room-wide incident"} from the notification.`,
        });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setFocusedIncidentId(null);
        setNotice({
          error: false,
          message:
            "That incident is stale, unavailable, or outside your current access. The current incident workspace is shown instead.",
        });
      })
      .finally(() => {
        if (!controller.signal.aborted) clearTarget();
      });
    return () => {
      controller.abort();
      if (targetLookup.current === lookupKey) targetLookup.current = "";
    };
  }, [
    organizationId,
    organizationReady,
    requestedIncidentId,
    setSearchParams,
    workspace,
    workspaceStatus,
  ]);
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

  const key =
    organizationId && facilityId && roomId && date
      ? `${organizationId}:${facilityId}:${roomId}:${date}`
      : "";
  useRealtimeRefresh({ scope: 'incidents', organizationId, enabled: organizationReady, entityTypes: featureIntegrationManifest.incidents.realtimeEntities, refresh: async () => {
    const nextWorkspace = await fetchRoomWorkspace(organizationId);
    const nextFacilities = nextWorkspace.facilities.filter((item) => item.status === 'active' && nextWorkspace.rooms.some((candidate) => candidate.is_active && candidate.facility_id === item.id));
    const nextFacilityId = nextFacilities.some((item) => item.id === facilityId) ? facilityId : nextFacilities[0]?.id || '';
    const nextRooms = nextWorkspace.rooms.filter((item) => item.is_active && item.facility_id === nextFacilityId);
    const nextRoomId = nextRooms.some((item) => item.id === roomId) ? roomId : nextRooms[0]?.id || '';
    const nextKey = nextFacilityId && nextRoomId ? `${organizationId}:${nextFacilityId}:${nextRoomId}:${date}` : '';
    const [context, list] = nextKey ? await Promise.all([fetchIncidentRoomContext(nextRoomId, date, organizationId, nextFacilityId), fetchIncidents({ facilityId: nextFacilityId, roomId: nextRoomId }, organizationId)]) : [null, null];
    setWorkspace(nextWorkspace); setWorkspaceStatus('ready'); setFacilityId(nextFacilityId); setRoomId(nextRoomId); setResource(context && list ? { key: nextKey, status: 'ready', context, list, error: '' } : { key: '', status: 'idle', context: null, list: null, error: '' });
  } });
  useEffect(() => {
    if (!key) {
      setResource({
        key: "",
        status: "idle",
        context: null,
        list: null,
        error: "",
      });
      return;
    }
    const controller = new AbortController();
    setResource((current) =>
      current.key === key && current.context && current.list
        ? { ...current, status: "refreshing", error: "" }
        : { key, status: "loading", context: null, list: null, error: "" },
    );
    Promise.all([
      fetchIncidentRoomContext(
        roomId,
        date,
        organizationId,
        facilityId,
        controller.signal,
      ),
      fetchIncidents({ facilityId, roomId }, organizationId, controller.signal),
    ])
      .then(([context, list]) => {
        if (!controller.signal.aborted)
          setResource({ key, status: "ready", context, list, error: "" });
      })
      .catch((caught) => {
        if (!controller.signal.aborted)
          setResource({
            key,
            status: "error",
            context: null,
            list: null,
            error:
              caught instanceof Error
                ? caught.message
                : "The incident workspace could not be loaded.",
          });
      });
    return () => controller.abort();
  }, [date, facilityId, key, organizationId, refreshVersion, roomId]);

  const context = resource.key === key ? resource.context : null;
  const allIncidents =
    resource.key === key ? resource.list?.incidents || [] : [];
  const dateIncidents = allIncidents.filter(
    (incident) => incident.service_date === date,
  );
  const counts = incidentCounts(dateIncidents);
  const shown = dateIncidents.filter(
    (incident) =>
      incidentMatches(incident, query) &&
      (filter === "all" || filter === "external_pending"
        ? filter === "all" || incident.external_report_status === "pending"
        : incident.status === filter),
  );
  const focusedIncidentVisible = Boolean(
    focusedIncidentId && shown.some((incident) => incident.id === focusedIncidentId),
  );
  useEffect(() => {
    if (
      !focusedIncidentId ||
      !focusedIncidentVisible ||
      dialog?.kind === "history"
    )
      return;
    const frame = requestAnimationFrame(() => {
      const card = document.querySelector<HTMLElement>(
        `[data-incident-id="${CSS.escape(focusedIncidentId)}"]`,
      );
      card?.scrollIntoView({ behavior: "smooth", block: "center" });
      card?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [dialog?.kind, focusedIncidentId, focusedIncidentVisible]);
  const canCreate = hasPermission(session.user, ACCESS.incidentCreate);
  const canUpdateAny = hasPermission(session.user, ACCESS.incidentUpdate);
  const canUpdateOwn = hasPermission(session.user, ACCESS.incidentUpdateOwn);
  const canReview = hasPermission(session.user, ACCESS.incidentReview);
  const canExternal = hasPermission(
    session.user,
    ACCESS.incidentExternalReport,
  );
  const mayUpdate = (incident: IncidentRecord) =>
    canEditIncident(incident) &&
    (canUpdateAny ||
      (canUpdateOwn && incident.created_by_user_id === session.user?.id));

  const refresh = (message: string) => {
    setDialog(null);
    setNotice({ error: false, message });
    setRefreshVersion((value) => value + 1);
  };
  const input = (draft: IncidentDraft) => ({
    occurred_at: draft.occurredAt,
    category: draft.category,
    severity: draft.severity,
    summary: draft.summary,
    immediate_actions: draft.immediateActions,
    medical_attention: draft.medicalAttention,
    parent_notification_status: draft.parentNotificationStatus,
    parent_notified_at: draft.parentNotifiedAt,
    parent_notification_notes: draft.parentNotificationNotes,
    authorities_contacted: draft.authoritiesContacted,
    staff_present: draft.staffPresent,
    client_operation_id: draft.clientOperationId,
  });
  const saveDraft = async (
    state: Extract<IncidentDialog, { kind: "draft" }>,
    draft: IncidentDraft,
  ) => {
    setBusy(`draft:${state.incident?.id || "new"}`);
    setNotice(null);
    try {
      if (state.incident)
        await updateIncident(state.incident, {
          ...input(draft),
          expected_version: state.incident.version,
          reason: draft.updateReason || "Incident draft updated",
        });
      else
        await createIncident(
          {
            facility_id: facilityId,
            room_id: roomId,
            attendance_day_id: draft.attendanceDayId,
            ...input(draft),
          },
          organizationId,
        );
      refresh(
        "The factual incident draft was saved internally. Nothing was submitted outside CareSync.",
      );
    } finally {
      setBusy("");
    }
  };
  const saveReview = async (incident: IncidentRecord, operationId: string) => {
    setBusy(`review:${incident.id}`);
    try {
      await submitIncidentForReview(incident, operationId);
      refresh(
        "The incident moved to internal review. No external report was sent.",
      );
    } finally {
      setBusy("");
    }
  };
  const saveReturn = async (
    incident: IncidentRecord,
    reason: string,
    operationId: string,
  ) => {
    setBusy(`return:${incident.id}`);
    try {
      await returnIncidentToDraft(incident, reason, operationId);
      refresh("The incident returned to draft with an audit reason.");
    } finally {
      setBusy("");
    }
  };
  const saveFinalize = async (
    incident: IncidentRecord,
    assessment: Exclude<IncidentAssessment, "unassessed">,
    reviewerNote: string,
    operationId: string,
  ) => {
    setBusy(`finalize:${incident.id}`);
    try {
      await finalizeIncident(incident, assessment, reviewerNote, operationId);
      refresh(
        "The human internal assessment was finalized. External action, if required, remains separate.",
      );
    } finally {
      setBusy("");
    }
  };
  const saveExternal = async (
    incident: IncidentRecord,
    draft: ExternalReportDraft,
  ) => {
    setBusy(`external:${incident.id}`);
    try {
      await recordExternalReport(incident, {
        reported_at: draft.reportedAt,
        confirmation_reference: draft.confirmationReference,
        submission_channel: draft.submissionChannel,
        submitted_by_name: draft.submittedByName,
        client_operation_id: draft.clientOperationId,
      });
      refresh(
        "The external confirmation was manually recorded. CareSync did not perform the submission.",
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
            Incident records stay unavailable until the signed-in account and
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
            <ShieldExclamationIcon width={14} /> Incident operations
          </Eyebrow>
          <h1>Facts, review, then action.</h1>
          <p>
            Capture an internal factual draft, route it through human review,
            and separately track evidence of any external action. CareSync never
            decides legal classification or submits to Alberta.
          </p>
        </div>
        <PrivateMark>
          <i /> Role-scoped · private, no-store
        </PrivateMark>
      </OperationHeader>
      <OperationNotice $error>
        <ShieldExclamationIcon />{" "}
        <span>
          Never delay immediate safety action, emergency services, parent
          contact, police, Child Intervention, or Child Care Connect as
          applicable.{" "}
          <a
            href="https://www.alberta.ca/childcare-report-an-incident-concern-or-complaint"
            target="_blank"
            rel="noreferrer"
          >
            Use current Alberta guidance
          </a>{" "}
          and confirm with Child Care Connect if unsure.
        </span>
      </OperationNotice>
      <ScopePanel $accent="amber">
        <OperationField>
          <span>Facility</span>
          <select
            aria-label="Incident facility"
            value={facilityId}
            onChange={(event) => setFacilityId(event.target.value)}
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
            aria-label="Incident room"
            value={roomId}
            onChange={(event) => setRoomId(event.target.value)}
          >
            {rooms.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </OperationField>
        <OperationField>
          <span>Incident date</span>
          <input
            aria-label="Incident date"
            type="date"
            max={today}
            disabled={!organizationWide}
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </OperationField>
        <IconButton
          type="button"
          aria-label="Refresh incident workspace"
          disabled={
            !key ||
            resource.status === "loading" ||
            resource.status === "refreshing"
          }
          onClick={() => setRefreshVersion((value) => value + 1)}
        >
          <ArrowPathIcon />
        </IconButton>
      </ScopePanel>
      {workspaceStatus === "loading" && (
        <OperationNotice role="status">
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
      {resource.status === "loading" && (
        <OperationNotice role="status">
          <ArrowPathIcon /> Loading internal incident work…
        </OperationNotice>
      )}
      {resource.status === "error" && (
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
      {context && (
        <>
          <MetricGrid>
            <MetricCard>
              <span>
                <IdentificationIcon /> Records
              </span>
              <strong>{counts.total}</strong>
            </MetricCard>
            <MetricCard>
              <span>
                <PencilSquareIcon /> Drafts
              </span>
              <strong>{counts.draft}</strong>
            </MetricCard>
            <MetricCard>
              <span>
                <ClockIcon /> Internal review
              </span>
              <strong>{counts.under_review}</strong>
            </MetricCard>
            <MetricCard>
              <span>
                <ExclamationTriangleIcon /> External action pending
              </span>
              <strong>{counts.externalPending}</strong>
            </MetricCard>
          </MetricGrid>
          <Toolbar>
            <SearchField>
              <MagnifyingGlassIcon />
              <input
                aria-label="Search incidents"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search children, room, type, or facts"
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
                $active={filter === "draft"}
                aria-pressed={filter === "draft"}
                onClick={() => setFilter("draft")}
              >
                Draft {counts.draft}
              </FilterButton>
              <FilterButton
                type="button"
                $active={filter === "under_review"}
                aria-pressed={filter === "under_review"}
                onClick={() => setFilter("under_review")}
              >
                Review {counts.under_review}
              </FilterButton>
              <FilterButton
                type="button"
                $active={filter === "finalized"}
                aria-pressed={filter === "finalized"}
                onClick={() => setFilter("finalized")}
              >
                Finalized {counts.finalized}
              </FilterButton>
              <FilterButton
                type="button"
                $active={filter === "external_pending"}
                aria-pressed={filter === "external_pending"}
                onClick={() => setFilter("external_pending")}
              >
                External pending {counts.externalPending}
              </FilterButton>
            </FilterRow>
          </Toolbar>
          <CardActions>
            {canCreate && (
              <ActionButton
                type="button"
                $variant="primary"
                onClick={() => setDialog({ kind: "draft" })}
              >
                <PlusIcon /> New internal draft
              </ActionButton>
            )}
          </CardActions>
          <div aria-live="polite">
            {resource.status === "refreshing" && (
              <OperationNotice role="status">
                <ArrowPathIcon /> Refreshing incident facts…
              </OperationNotice>
            )}
            {notice && (
              <OperationNotice $error={notice.error}>
                {notice.error ? (
                  <ExclamationTriangleIcon />
                ) : (
                  <CheckCircleIcon />
                )}{" "}
                {notice.message}
              </OperationNotice>
            )}
          </div>
          {shown.length ? (
            <CardGrid>
              {shown.map((incident) => {
                const guidance = reportGuidance(incident);
                return (
                  <IncidentCard
                    key={incident.id}
                    $accent={guidance.urgent ? "amber" : "cyan"}
                    $focused={focusedIncidentId === incident.id}
                    data-incident-id={incident.id}
                    tabIndex={focusedIncidentId === incident.id ? -1 : undefined}
                  >
                    <CardHeader>
                      <div>
                        <h2>
                          {incident.child_name || "Room-wide incident"} ·{" "}
                          {incident.category.replaceAll("_", " ")}
                        </h2>
                        <p>
                          {incident.room_name} ·{" "}
                          {formatCareTime(
                            incident.occurred_at,
                            incident.facility_timezone,
                          )}{" "}
                          {incident.facility_timezone} · created by{" "}
                          {incident.created_by_name}
                        </p>
                      </div>
                      <StatusChip $tone={incidentStatusTone(incident.status)}>
                        {incidentStatusLabel(incident.status)}
                      </StatusChip>
                    </CardHeader>
                    <OperationNotice
                      $error={guidance.urgent}
                      $warning={!guidance.urgent}
                    >
                      <ShieldExclamationIcon />{" "}
                      <span>
                        <strong>{guidance.heading}</strong>
                        <br />
                        {guidance.detail}
                      </span>
                    </OperationNotice>
                    <Summary>{incident.summary}</Summary>
                    <DetailGrid>
                      <div>
                        <dt>Working severity</dt>
                        <dd>{incidentSeverityLabel(incident.severity)}</dd>
                      </div>
                      <div>
                        <dt>Medical attention recorded</dt>
                        <dd>
                          {incident.medical_attention.replaceAll("_", " ")}
                        </dd>
                      </div>
                      <div>
                        <dt>Parent contact</dt>
                        <dd>
                          {incident.parent_notification_status.replaceAll(
                            "_",
                            " ",
                          )}
                          {incident.parent_notification_notes
                            ? ` · ${incident.parent_notification_notes}`
                            : ""}
                        </dd>
                      </div>
                      <div>
                        <dt>Internal assessment</dt>
                        <dd>
                          {incidentAssessmentLabel(
                            incident.reportability_assessment,
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>External status</dt>
                        <dd>
                          {externalReportLabel(incident.external_report_status)}
                        </dd>
                      </div>
                      <div>
                        <dt>CareSync submission</dt>
                        <dd>
                          Not performed · external evidence is manually tracked
                          only
                        </dd>
                      </div>
                    </DetailGrid>
                    <CardActions>
                      {mayUpdate(incident) && (
                        <ActionButton
                          type="button"
                          onClick={() => setDialog({ kind: "draft", incident })}
                        >
                          <PencilSquareIcon /> Edit draft
                        </ActionButton>
                      )}
                      {canReview && incident.status === "draft" && (
                        <ActionButton
                          type="button"
                          $variant="primary"
                          onClick={() =>
                            setDialog({ kind: "review", incident })
                          }
                        >
                          Begin internal review
                        </ActionButton>
                      )}
                      {canReview && incident.status === "under_review" && (
                        <>
                          <ActionButton
                            type="button"
                            onClick={() =>
                              setDialog({ kind: "return", incident })
                            }
                          >
                            Return to draft
                          </ActionButton>
                          <ActionButton
                            type="button"
                            $variant="primary"
                            onClick={() =>
                              setDialog({ kind: "finalize", incident })
                            }
                          >
                            Finalize human review
                          </ActionButton>
                        </>
                      )}
                      {canExternal && canRecordExternalReport(incident) && (
                        <ActionButton
                          type="button"
                          $variant="primary"
                          onClick={() =>
                            setDialog({ kind: "external", incident })
                          }
                        >
                          Record external confirmation
                        </ActionButton>
                      )}
                      <ActionButton
                        type="button"
                        onClick={() => setDialog({ kind: "history", incident })}
                      >
                        <ClockIcon /> History
                      </ActionButton>
                    </CardActions>
                  </IncidentCard>
                );
              })}
            </CardGrid>
          ) : (
            <EmptyState>
              <div>
                <IdentificationIcon />
                <h2>No incidents match this date and view.</h2>
                <p>
                  Start an internal factual draft when needed. Nothing is
                  submitted outside CareSync from this workspace.
                </p>
              </div>
            </EmptyState>
          )}
        </>
      )}
      {dialog?.kind === "draft" && context && (
        <IncidentDraftDialog
          key={`${dialog.incident?.id || "new"}:${dialog.incident?.version || 0}`}
          incident={dialog.incident}
          roomName={context.room_name}
          attendanceOptions={context.attendance_options.map((option) => ({
            attendanceDayId: option.attendance_day_id,
            childId: option.child_id,
            childName: `${option.child_name}${option.attendance_state === "checked_out" ? " · checked out" : ""}`,
          }))}
          timeZone={context.facility_timezone}
          busy={busy === `draft:${dialog.incident?.id || "new"}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(draft) => saveDraft(dialog, draft)}
        />
      )}
      {dialog?.kind === "review" && (
        <IncidentSubmitReviewDialog
          incident={dialog.incident}
          busy={busy === `review:${dialog.incident.id}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(id) => saveReview(dialog.incident, id)}
        />
      )}
      {dialog?.kind === "return" && (
        <ReturnIncidentDialog
          incident={dialog.incident}
          busy={busy === `return:${dialog.incident.id}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(reason, id) => saveReturn(dialog.incident, reason, id)}
        />
      )}
      {dialog?.kind === "finalize" && (
        <IncidentFinalizeDialog
          incident={dialog.incident}
          busy={busy === `finalize:${dialog.incident.id}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(assessment, note, id) =>
            saveFinalize(dialog.incident, assessment, note, id)
          }
        />
      )}
      {dialog?.kind === "external" && (
        <ExternalReportDialog
          incident={dialog.incident}
          timeZone={dialog.incident.facility_timezone}
          busy={busy === `external:${dialog.incident.id}`}
          onClose={() => !busy && setDialog(null)}
          onSave={(draft) => saveExternal(dialog.incident, draft)}
        />
      )}
      {dialog?.kind === "history" && (
        <IncidentHistoryDialog
          incident={dialog.incident}
          onClose={() => setDialog(null)}
        />
      )}
    </OperationPage>
  );
}
