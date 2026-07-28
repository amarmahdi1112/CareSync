import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { addDays, format, parseISO } from "date-fns";
import {
  ArrowPathIcon,
  ArrowsRightLeftIcon,
  BriefcaseIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  PaperAirplaneIcon,
  PencilSquareIcon,
  PlusIcon,
  UserGroupIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  IconButton,
  StatusChip,
} from "../../../components/ui/Primitives";
import { useRealtimeRefresh } from "../../../realtime/RealtimeContext";
import {
  facilityDateTimeInputValue,
  facilityDateTimeToIso,
} from "../../daily-care/careModel";
import type { StaffWorkspace } from "../../staff/types";
import type { StaffSchedule } from "../types";
import type { StaffRotaActionTarget } from "../staffRotaNotificationFocus";
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
import { exchangeApi, exchangeErrorMessage } from "./exchangeApi";
import {
  engagementStatusLabel,
  filterCandidates,
  managerOfferPath,
  managerOfferWindowOpen,
  openShiftStatusLabel,
  sortOpenShifts,
  sortSwaps,
  swapStatusLabel,
  validateManagerOfferExpiry,
  validateOpenShiftInput,
} from "./exchangeModel";
import type {
  OpenShiftCandidate,
  OpenShiftEngagement,
  OpenShiftInput,
  OpenShiftPosting,
  ShiftSwapRequest,
  SubstituteCandidate,
} from "./exchangeTypes";

const Shell = styled(GlassPanel)`
  display: grid;
  gap: 13px;
  padding: 15px;
  overflow: visible;
`;
const Header = styled.div`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  h2 {
    margin: 7px 0 4px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.08rem;
    font-weight: 580;
    letter-spacing: -0.025em;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.71rem;
    line-height: 1.5;
  }
  @media (max-width: 680px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const HeaderActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  select {
    min-height: 42px;
    padding: 0 34px 0 10px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 9px 12px 9px 12px;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: 0.72rem;
  }
`;
const Notice = styled.div<{ $error?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 11px;
  border: 1px solid
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.borderStrong)};
  border-radius: 8px 11px 8px 11px;
  color: ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.textSoft)};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: 0.7rem;
  line-height: 1.5;
  svg {
    width: 17px;
    flex: 0 0 auto;
  }
`;
const Tabs = styled.div`
  display: flex;
  gap: 5px;
  padding: 5px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 10px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  overflow-x: auto;
`;
const Tab = styled.button<{ $active?: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 38px;
  padding: 0 11px;
  border: 1px solid
    ${({ $active, theme }) => ($active ? theme.color.cyan : "transparent")};
  border-radius: 8px;
  color: ${({ $active, theme }) => ($active ? theme.color.text : theme.color.textMuted)};
  background: ${({ $active, theme }) => ($active ? theme.color.control : "transparent")};
  font: inherit;
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  svg {
    width: 15px;
  }
`;
const Summary = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  @media (max-width: 740px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
`;
const Metric = styled.div`
  padding: 10px 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 8px 11px 8px 11px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  span {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.61rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
  }
  strong {
    display: block;
    margin-top: 5px;
    font-size: 1.15rem;
    font-weight: 600;
  }
`;
const Section = styled.section`
  display: grid;
  gap: 10px;
`;
const SectionHead = styled.div`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 10px;
  h3 {
    margin: 0;
    font-size: 0.86rem;
    font-weight: 600;
  }
  p {
    margin: 3px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.67rem;
  }
  @media (max-width: 580px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const Cards = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  @media (max-width: 820px) {
    grid-template-columns: 1fr;
  }
`;
const Card = styled.article<{ $focused?: boolean }>`
  display: grid;
  gap: 8px;
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
    font-size: 0.78rem;
    font-weight: 600;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.68rem;
    line-height: 1.5;
  }
  small {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.63rem;
    line-height: 1.45;
  }
`;
const CardTop = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 9px;
`;
const CardActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  button {
    min-height: 34px;
    padding: 0 9px;
    font-size: 0.67rem;
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
  font-size: 0.7rem;
`;
const Search = styled.label`
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 42px;
  padding: 0 10px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 9px 12px 9px 12px;
  background: ${({ theme }) => theme.color.control};
  svg {
    width: 16px;
    color: ${({ theme }) => theme.color.textMuted};
  }
  input {
    min-width: 0;
    flex: 1;
    border: 0;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: transparent;
    font: inherit;
    font-size: 0.7rem;
  }
`;
const ReviewToolbar = styled.div`
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 160px;
  gap: 8px;
  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;
const Select = styled.select`
  min-height: 42px;
  padding: 0 32px 0 10px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 9px 12px 9px 12px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.control};
  font: inherit;
  font-size: 0.7rem;
`;
const CandidateList = styled.div`
  display: grid;
  gap: 7px;
  max-height: 48vh;
  overflow-y: auto;
  padding-right: 3px;
`;
const Candidate = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 9px;
  padding: 10px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 8px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  strong,
  small {
    display: block;
  }
  strong {
    font-size: 0.74rem;
  }
  small {
    margin-top: 3px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.63rem;
    line-height: 1.4;
  }
  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;
const ReasonList = styled.ul`
  margin: 5px 0 0;
  padding-left: 16px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.64rem;
  line-height: 1.5;
`;
const Timeline = styled.div`
  display: grid;
  gap: 7px;
`;
const TimelineRow = styled.div<{ $focused?: boolean }>`
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  padding: 9px;
  border-left: 2px solid
    ${({ $focused, theme }) =>
      $focused ? theme.color.cyan : theme.color.borderStrong};
  background: ${({ theme }) => theme.color.surfaceStrong};
  box-shadow: ${({ $focused, theme }) =>
    $focused
      ? `0 0 0 2px color-mix(in srgb, ${theme.color.cyan} 20%, transparent)`
      : "none"};
  outline: none;
  strong,
  small {
    display: block;
  }
  strong {
    font-size: 0.7rem;
  }
  small {
    margin-top: 3px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.62rem;
  }
`;
const Compare = styled.div`
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 9px;
  align-items: center;
  padding: 10px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 8px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  div strong,
  div small {
    display: block;
  }
  div strong {
    font-size: 0.7rem;
  }
  div small {
    margin-top: 4px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.63rem;
  }
  svg {
    width: 18px;
    color: ${({ theme }) => theme.color.cyan};
  }
  @media (max-width: 520px) {
    grid-template-columns: 1fr;
    svg {
      transform: rotate(90deg);
    }
  }
`;

type ExchangeTab = "coverage" | "substitutes" | "swaps";
const TAB_ORDER: ExchangeTab[] = ["coverage", "substitutes", "swaps"];
type OpenEditor = {
  post: OpenShiftPosting | null;
  operationId: string;
  retryLocked: boolean;
  facilityId: string;
  roomId: string;
  sourceScheduleId: string | null;
  date: string;
  start: string;
  end: string;
  note: string;
};
type PostingAction = {
  post: OpenShiftPosting;
  kind: "post" | "cancel";
  operationId: string;
  retryLocked: boolean;
  reason: string;
};
type ReviewState = {
  post: OpenShiftPosting;
  phase: "loading" | "ready" | "error";
  candidates: OpenShiftCandidate[];
  engagements: OpenShiftEngagement[];
  query: string;
  eligibility: string;
};
type OfferState = {
  post: OpenShiftPosting;
  candidate: OpenShiftCandidate;
  sourceInterestId: string | null;
  operationId: string;
  retryLocked: boolean;
  note: string;
  expiresLocal: string;
};
type WithdrawState = {
  engagement: OpenShiftEngagement;
  operationId: string;
  retryLocked: boolean;
  note: string;
};
type SwapDecision = {
  swap: ShiftSwapRequest;
  kind: "approve" | "reject";
  operationId: string;
  retryLocked: boolean;
  reason: string;
};

const dateTimeLabel = (value: string, timezone: string) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
const offerExpiryLocal = (
  post: OpenShiftPosting,
  serverTimestamp: string,
): string | null => {
  const serverNow = Date.parse(serverTimestamp);
  if (!managerOfferWindowOpen(serverTimestamp, post.scheduled_start_at))
    return null;
  const soon = serverNow + 24 * 60 * 60_000;
  const earliest = serverNow + 5 * 60_000;
  const beforeShift = Date.parse(post.scheduled_start_at) - 60 * 60_000;
  const latest = Date.parse(post.scheduled_start_at) - 60_000;
  if (latest <= earliest) return null;
  const expiry = Math.max(earliest, Math.min(soon, beforeShift));
  return facilityDateTimeInputValue(
    new Date(expiry).toISOString(),
    post.facility_timezone,
  );
};

export function ShiftExchangePanel({
  organizationId,
  workspace,
  weekStart,
  days,
  preferredFacilityId = "",
  notificationTarget = null,
  requestedSource = null,
  onRequestedSourceHandled,
  onSchedulesChanged,
}: {
  organizationId: string;
  workspace: StaffWorkspace;
  weekStart: string;
  days: string[];
  preferredFacilityId?: string;
  notificationTarget?: StaffRotaActionTarget | null;
  requestedSource?: StaffSchedule | null;
  onRequestedSourceHandled?: () => void;
  onSchedulesChanged: () => Promise<void> | void;
}) {
  const facilities = useMemo(
    () => workspace.facilities.filter((item) => item.status === "active"),
    [workspace.facilities],
  );
  const [facilityId, setFacilityId] = useState(
    () => preferredFacilityId || facilities[0]?.id || "",
  );
  const [tab, setTab] = useState<ExchangeTab>("coverage");
  const [posts, setPosts] = useState<OpenShiftPosting[]>([]);
  const [substitutes, setSubstitutes] = useState<SubstituteCandidate[]>([]);
  const [swaps, setSwaps] = useState<ShiftSwapRequest[]>([]);
  const [serverNow, setServerNow] = useState<string | null>(null);
  const [loadedScope, setLoadedScope] = useState<{
    facilityId: string;
    startAt: string;
    endAt: string;
  } | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [editor, setEditor] = useState<OpenEditor | null>(null);
  const [postingAction, setPostingAction] = useState<PostingAction | null>(
    null,
  );
  const [review, setReview] = useState<ReviewState | null>(null);
  const [offer, setOffer] = useState<OfferState | null>(null);
  const [withdraw, setWithdraw] = useState<WithdrawState | null>(null);
  const [swapDecision, setSwapDecision] = useState<SwapDecision | null>(null);
  const focusedTargetHandled = useRef("");
  const focusedEngagementReviewStarted = useRef("");
  const exchangeTarget =
    notificationTarget &&
    [
      "staff_open_shift",
      "staff_open_shift_engagement",
      "staff_substitute_profile",
      "staff_shift_swap",
    ].includes(notificationTarget.entityType)
      ? notificationTarget
      : null;

  useEffect(() => {
    setFacilityId((current) => {
      if (
        preferredFacilityId &&
        facilities.some((item) => item.id === preferredFacilityId)
      )
        return preferredFacilityId;
      return facilities.some((item) => item.id === current)
        ? current
        : facilities[0]?.id || "";
    });
  }, [facilities, preferredFacilityId]);

  useEffect(() => {
    if (!exchangeTarget) {
      focusedTargetHandled.current = "";
      focusedEngagementReviewStarted.current = "";
      return;
    }
    setFacilityId(exchangeTarget.facilityId);
    setTab(
      exchangeTarget.entityType === "staff_substitute_profile"
        ? "substitutes"
        : exchangeTarget.entityType === "staff_shift_swap"
          ? "swaps"
          : "coverage",
    );
    focusedTargetHandled.current = "";
    focusedEngagementReviewStarted.current = "";
    if (exchangeTarget.entityType !== "staff_open_shift_engagement") {
      setReview(null);
    }
  }, [
    exchangeTarget?.entityId,
    exchangeTarget?.entityType,
    exchangeTarget?.facilityId,
  ]);

  const facility = facilities.find((item) => item.id === facilityId);
  const rooms = useMemo(
    () =>
      workspace.rooms.filter(
        (item) => item.facility_id === facilityId && item.is_active,
      ),
    [facilityId, workspace.rooms],
  );
  const range = useMemo(() => {
    if (!facility) return null;
    const end = format(
      addDays(parseISO(days[6] || weekStart), 1),
      "yyyy-MM-dd",
    );
    return {
      startAt: facilityDateTimeToIso(`${weekStart}T00:00`, facility.timezone),
      endAt: facilityDateTimeToIso(`${end}T00:00`, facility.timezone),
    };
  }, [days, facility, weekStart]);
  const exchangeTargetInRange = Boolean(
    exchangeTarget &&
      (!exchangeTarget.startsAt ||
        (range &&
          Date.parse(exchangeTarget.startsAt) >= Date.parse(range.startAt) &&
          Date.parse(exchangeTarget.startsAt) < Date.parse(range.endAt))),
  );

  const load = useCallback(
    async (signal?: AbortSignal, quiet = false) => {
      if (!organizationId || !facilityId || !range) return;
      if (!quiet) {
        setPhase("loading");
        setLoadedScope(null);
      }
      setError("");
      try {
        const [openResult, substituteResult, swapResult] = await Promise.all([
          exchangeApi.listOpenShifts(
            organizationId,
            { facilityId, ...range },
            signal,
          ),
          exchangeApi.substitutes(facilityId, signal),
          exchangeApi.listSwaps(
            organizationId,
            { facilityId, ...range },
            signal,
          ),
        ]);
        if (signal?.aborted) return;
        const knownRooms = new Set(
          workspace.rooms
            .filter((item) => item.facility_id === facilityId)
            .map((item) => item.id),
        );
        const userByMembership = new Map(
          workspace.members.map((item) => [item.membership_id, item.user_id]),
        );
        if (
          openResult.items.some(
            (item) => item.room_id && !knownRooms.has(item.room_id),
          ) ||
          swapResult.items.some(
            (item) =>
              item.requester_schedule.room_id &&
              !knownRooms.has(item.requester_schedule.room_id),
          ) ||
          substituteResult.items.some(
            (item) =>
              userByMembership.get(item.membership_id) !== item.staff_user_id,
          ) ||
          swapResult.items.some(
            (item) =>
              userByMembership.get(item.requester_membership_id) !==
                item.requester_staff_user_id ||
              userByMembership.get(item.counterparty_membership_id) !==
                item.counterparty_staff_user_id,
          )
        )
          throw new Error(
            "Staff exchange data crossed the verified staff or room boundary.",
          );
        setPosts(sortOpenShifts(openResult.items));
        setSubstitutes(substituteResult.items);
        setSwaps(sortSwaps(swapResult.items));
        setServerNow(openResult.generated_at);
        setLoadedScope({ facilityId, startAt: range.startAt, endAt: range.endAt });
        setPhase("ready");
      } catch (caught) {
        if (!signal?.aborted) {
          setError(exchangeErrorMessage(caught));
          setPhase("error");
        }
        throw caught;
      }
    },
    [facilityId, organizationId, range, workspace.members, workspace.rooms],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [load]);
  useRealtimeRefresh({
    scope: "staff-exchange-manager",
    organizationId,
    enabled: Boolean(facilityId),
    eventPrefixes: [
      "staff_open_shift.",
      "staff_open_shift_engagement.",
      "staff_substitute_profile.",
      "staff_shift_swap.",
      "staff_schedule.",
    ],
    entityTypes: [
      "staff_open_shift",
      "staff_open_shift_engagement",
      "staff_substitute_profile",
      "staff_shift_swap",
      "staff_schedule",
    ],
    refresh: async () => load(undefined, true),
  });

  const loadReview = useCallback(
    async (post: OpenShiftPosting) => {
      setReview((current) =>
        current?.post.id === post.id
          ? { ...current, phase: "loading" }
          : {
              post,
              phase: "loading",
              candidates: [],
              engagements: [],
              query: "",
              eligibility: "all",
            },
      );
      try {
        const [candidates, engagements] = await Promise.all([
          post.status === "open"
            ? exchangeApi.candidates(post)
            : Promise.resolve({
                items: [],
                total: 0,
                generated_at: new Date().toISOString(),
              }),
          exchangeApi.engagements(organizationId, post),
        ]);
        const userByMembership = new Map(
          workspace.members.map((item) => [item.membership_id, item.user_id]),
        );
        if (
          candidates.items.some(
            (item) =>
              userByMembership.get(item.membership_id) !== item.staff_user_id,
          ) ||
          engagements.items.some(
            (item) =>
              userByMembership.get(item.membership_id) !== item.staff_user_id,
          )
        )
          throw new Error(
            "Candidate review crossed the verified staff workspace.",
          );
        setServerNow(
          [candidates.generated_at, engagements.generated_at].sort().at(-1)!,
        );
        setReview((current) =>
          current?.post.id === post.id
            ? {
                ...current,
                phase: "ready",
                candidates: candidates.items,
                engagements: engagements.items,
              }
            : current,
        );
      } catch (caught) {
        setReview((current) =>
          current?.post.id === post.id
            ? { ...current, phase: "error" }
            : current,
        );
        setError(exchangeErrorMessage(caught));
      }
    },
    [organizationId, workspace.members],
  );

  useEffect(() => {
    if (
      !exchangeTarget ||
      exchangeTarget.entityType !== "staff_open_shift_engagement" ||
      phase !== "ready" ||
      facilityId !== exchangeTarget.facilityId ||
      loadedScope?.facilityId !== exchangeTarget.facilityId ||
      loadedScope.startAt !== range?.startAt ||
      loadedScope.endAt !== range?.endAt ||
      tab !== "coverage" ||
      !exchangeTargetInRange
    )
      return;
    const targetKey = `${exchangeTarget.entityType}:${exchangeTarget.entityId}`;
    if (focusedEngagementReviewStarted.current === targetKey) return;
    focusedEngagementReviewStarted.current = targetKey;
    const parent = posts.find(
      (post) => post.id === exchangeTarget.parentEntityId,
    );
    if (!parent) {
      focusedTargetHandled.current = targetKey;
      setNotice(
        "The verified engagement's parent opportunity is no longer present in this canonical week. No different record was selected.",
      );
      return;
    }
    void loadReview(parent);
  }, [
    exchangeTarget,
    exchangeTargetInRange,
    facilityId,
    loadReview,
    loadedScope,
    phase,
    posts,
    range,
    tab,
  ]);

  useEffect(() => {
    if (
      !exchangeTarget ||
      phase !== "ready" ||
      facilityId !== exchangeTarget.facilityId ||
      loadedScope?.facilityId !== exchangeTarget.facilityId ||
      loadedScope.startAt !== range?.startAt ||
      loadedScope.endAt !== range?.endAt ||
      !exchangeTargetInRange
    )
      return;
    const owningTab: ExchangeTab =
      exchangeTarget.entityType === "staff_substitute_profile"
        ? "substitutes"
        : exchangeTarget.entityType === "staff_shift_swap"
          ? "swaps"
          : "coverage";
    if (tab !== owningTab) return;
    const targetKey = `${exchangeTarget.entityType}:${exchangeTarget.entityId}`;
    if (focusedTargetHandled.current === targetKey) return;

    let visible = false;
    if (exchangeTarget.entityType === "staff_open_shift") {
      visible = posts.some((post) => post.id === exchangeTarget.entityId);
    } else if (exchangeTarget.entityType === "staff_substitute_profile") {
      visible = substitutes.some(
        (candidate) => candidate.membership_id === exchangeTarget.membershipId,
      );
    } else if (exchangeTarget.entityType === "staff_shift_swap") {
      visible = swaps.some((swap) => swap.id === exchangeTarget.entityId);
    } else if (exchangeTarget.entityType === "staff_open_shift_engagement") {
      if (
        review?.post.id !== exchangeTarget.parentEntityId ||
        review.phase === "loading"
      )
        return;
      if (review.phase !== "ready") {
        focusedTargetHandled.current = targetKey;
        setNotice(
          "The verified engagement could not be loaded from its canonical opportunity. No different record was selected.",
        );
        return;
      }
      visible = review.engagements.some(
        (engagement) => engagement.id === exchangeTarget.entityId,
      );
    }

    focusedTargetHandled.current = targetKey;
    if (!visible) {
      setNotice(
        "The verified exchange record is no longer present in this current canonical view. No different row was selected.",
      );
      return;
    }
    const frame = requestAnimationFrame(() => {
      const row = document.querySelector<HTMLElement>(
        `[data-exchange-target="${CSS.escape(targetKey)}"]`,
      );
      row?.scrollIntoView({ behavior: "smooth", block: "center" });
      row?.focus({ preventScroll: true });
      setNotice(
        "The exact exchange record is focused from the latest canonical server read.",
      );
    });
    return () => cancelAnimationFrame(frame);
  }, [
    exchangeTarget,
    exchangeTargetInRange,
    facilityId,
    loadedScope,
    phase,
    posts,
    range,
    review,
    substitutes,
    swaps,
    tab,
  ]);

  useEffect(() => {
    if (!requestedSource || editor) return;
    setFacilityId(requestedSource.facility_id);
    setTab("coverage");
    const start = facilityDateTimeInputValue(
      requestedSource.scheduled_start_at,
      requestedSource.facility_timezone,
    );
    const end = facilityDateTimeInputValue(
      requestedSource.scheduled_end_at,
      requestedSource.facility_timezone,
    );
    setEditor({
      post: null,
      operationId: createOperationId(),
      retryLocked: false,
      facilityId: requestedSource.facility_id,
      roomId: requestedSource.room_id || "",
      sourceScheduleId: requestedSource.id,
      date: start.slice(0, 10),
      start: start.slice(11, 16),
      end: end.slice(11, 16),
      note: `Coverage for ${requestedSource.staff_display_name}`,
    });
    onRequestedSourceHandled?.();
  }, [editor, onRequestedSourceHandled, requestedSource]);

  const complete = async (message: string, schedulesChanged = false) => {
    await load(undefined, true).catch(() => undefined);
    if (schedulesChanged)
      await Promise.resolve(onSchedulesChanged()).catch(() => undefined);
    setNotice(message);
  };
  const recover = async <
    T extends { operationId: string; retryLocked: boolean },
  >(
    caught: unknown,
    setter: React.Dispatch<React.SetStateAction<T | null>>,
  ) => {
    const disposition = mutationFailureDisposition(caught);
    if (disposition === "refresh_then_reset")
      await load(undefined, true).catch(() => undefined);
    setter((current) =>
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

  const openNew = () =>
    setEditor({
      post: null,
      operationId: createOperationId(),
      retryLocked: false,
      facilityId,
      roomId: "",
      sourceScheduleId: null,
      date: days[0] || weekStart,
      start: "08:00",
      end: "16:00",
      note: "",
    });
  const openEdit = (post: OpenShiftPosting) => {
    const start = facilityDateTimeInputValue(
      post.scheduled_start_at,
      post.facility_timezone,
    );
    const end = facilityDateTimeInputValue(
      post.scheduled_end_at,
      post.facility_timezone,
    );
    setEditor({
      post,
      operationId: createOperationId(),
      retryLocked: false,
      facilityId: post.facility_id,
      roomId: post.room_id || "",
      sourceScheduleId: post.source_schedule_id,
      date: start.slice(0, 10),
      start: start.slice(11, 16),
      end: end.slice(11, 16),
      note: post.public_note || "",
    });
  };
  const saveOpenShift = async (event: FormEvent) => {
    event.preventDefault();
    if (!editor) return;
    const editFacility = facilities.find(
      (item) => item.id === editor.facilityId,
    );
    if (!editFacility) {
      setError("Choose an active facility.");
      return;
    }
    let input: OpenShiftInput;
    try {
      input = {
        facility_id: editor.facilityId,
        room_id: editor.roomId || null,
        source_schedule_id: editor.sourceScheduleId,
        scheduled_start_at: facilityDateTimeToIso(
          `${editor.date}T${editor.start}`,
          editFacility.timezone,
        ),
        scheduled_end_at: facilityDateTimeToIso(
          `${editor.date}T${editor.end}`,
          editFacility.timezone,
        ),
        public_note: editor.note.trim() || null,
      };
    } catch (caught) {
      setError(exchangeErrorMessage(caught));
      return;
    }
    const errors = validateOpenShiftInput(input);
    if (errors.length) {
      setError(errors[0]!);
      return;
    }
    setBusy("save-open");
    setError("");
    try {
      if (editor.post)
        await exchangeApi.updateOpenShift(
          organizationId,
          editor.post,
          input,
          editor.operationId,
        );
      else
        await exchangeApi.createOpenShift(
          organizationId,
          input,
          editor.operationId,
        );
      await complete(
        editor.post ? "Open-shift draft updated." : "Open-shift draft created.",
      );
      setEditor(null);
    } catch (caught) {
      await recover(caught, setEditor);
      setError(exchangeErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const runPostingAction = async (event: FormEvent) => {
    event.preventDefault();
    if (!postingAction) return;
    if (
      postingAction.kind === "cancel" &&
      postingAction.reason.trim().length < 5
    ) {
      setError("Explain the cancellation in at least five characters.");
      return;
    }
    setBusy("posting-action");
    setError("");
    try {
      if (postingAction.kind === "post")
        await exchangeApi.postOpenShift(
          organizationId,
          postingAction.post,
          postingAction.operationId,
        );
      else
        await exchangeApi.cancelOpenShift(
          organizationId,
          postingAction.post,
          postingAction.operationId,
          postingAction.reason.trim(),
        );
      await complete(
        postingAction.kind === "post"
          ? "Coverage opportunity posted to eligible staff."
          : "Open shift cancelled.",
      );
      setPostingAction(null);
    } catch (caught) {
      await recover(caught, setPostingAction);
      setError(exchangeErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const openOffer = (candidate: OpenShiftCandidate) => {
    if (!review) return;
    const path = managerOfferPath(candidate, review.engagements);
    if (!path.allowed) {
      setError(path.reason || "This offer is not available.");
      return;
    }
    const defaultExpiry = serverNow
      ? offerExpiryLocal(review.post, serverNow)
      : null;
    if (!defaultExpiry) {
      setError(
        "It is too late to issue an offer before this shift starts. Refresh the board or arrange coverage outside this workflow.",
      );
      return;
    }
    setOffer({
      post: review.post,
      candidate,
      sourceInterestId: path.sourceInterestId,
      operationId: createOperationId(),
      retryLocked: false,
      note: "",
      expiresLocal: defaultExpiry,
    });
  };
  const sendOffer = async (event: FormEvent) => {
    event.preventDefault();
    if (!offer) return;
    let expiresAt: string;
    try {
      expiresAt = facilityDateTimeToIso(
        offer.expiresLocal,
        offer.post.facility_timezone,
      );
    } catch (caught) {
      setError(exchangeErrorMessage(caught));
      return;
    }
    if (!offer.retryLocked) {
      const expiryError = validateManagerOfferExpiry(
        expiresAt,
        serverNow || "",
        offer.post.scheduled_start_at,
      );
      if (expiryError) {
        setError(expiryError);
        return;
      }
    }
    setBusy("offer");
    setError("");
    try {
      await exchangeApi.createOffer(
        organizationId,
        offer.post,
        offer.operationId,
        {
          staff_user_id: offer.candidate.staff_user_id,
          source_interest_id: offer.sourceInterestId,
          note: offer.note.trim() || null,
          expires_at: expiresAt,
        },
      );
      await loadReview(offer.post);
      setNotice(
        `Offer sent to ${offer.candidate.staff_display_name}. No assignment exists until they accept.`,
      );
      setOffer(null);
    } catch (caught) {
      await recover(caught, setOffer);
      setError(exchangeErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const withdrawOffer = async (event: FormEvent) => {
    event.preventDefault();
    if (!withdraw || !review) return;
    setBusy("withdraw");
    setError("");
    try {
      await exchangeApi.withdrawEngagement(
        organizationId,
        withdraw.engagement,
        withdraw.operationId,
        withdraw.note.trim() || null,
      );
      await loadReview(review.post);
      setNotice("Offer withdrawn. The staff member was not assigned.");
      setWithdraw(null);
    } catch (caught) {
      await recover(caught, setWithdraw);
      setError(exchangeErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const decideSwap = async (event: FormEvent) => {
    event.preventDefault();
    if (!swapDecision) return;
    if (
      swapDecision.kind === "reject" &&
      swapDecision.reason.trim().length < 5
    ) {
      setError("Explain the rejection in at least five characters.");
      return;
    }
    setBusy("swap");
    setError("");
    try {
      if (swapDecision.kind === "approve")
        await exchangeApi.approveSwap(
          organizationId,
          swapDecision.swap,
          swapDecision.operationId,
        );
      else
        await exchangeApi.rejectSwap(
          organizationId,
          swapDecision.swap,
          swapDecision.operationId,
          swapDecision.reason.trim(),
        );
      await complete(
        swapDecision.kind === "approve"
          ? "Swap approved atomically; replacement schedules are now canonical."
          : "Swap rejected with the manager reason.",
        swapDecision.kind === "approve",
      );
      setSwapDecision(null);
    } catch (caught) {
      await recover(caught, setSwapDecision);
      setError(exchangeErrorMessage(caught));
    } finally {
      setBusy("");
    }
  };

  const tabKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const current = TAB_ORDER.indexOf(tab);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? TAB_ORDER.length - 1
          : (current +
              (event.key === "ArrowRight" ? 1 : -1) +
              TAB_ORDER.length) %
            TAB_ORDER.length;
    setTab(TAB_ORDER[next]!);
    requestAnimationFrame(() =>
      document.getElementById(`exchange-tab-${TAB_ORDER[next]}`)?.focus(),
    );
  };
  const pendingManager = swaps.filter(
    (item) => item.status === "pending_manager",
  ).length;
  const visibleCandidates = review
    ? filterCandidates(review.candidates, review.query, review.eligibility)
    : [];
  const reviewDefaultExpiry =
    review && serverNow ? offerExpiryLocal(review.post, serverNow) : null;

  if (!facilities.length)
    return (
      <Shell $accent="cyan">
        <Header>
          <div>
            <Eyebrow>
              <ArrowsRightLeftIcon width={14} /> Staff exchange
            </Eyebrow>
            <h2>Coverage needs an active facility.</h2>
            <p>
              Create or reactivate a facility before posting staff
              opportunities.
            </p>
          </div>
        </Header>
        <Empty>No active facility is available for staff exchange.</Empty>
      </Shell>
    );

  return (
    <Shell $accent="cyan">
      <Header>
        <div>
          <Eyebrow>
            <ArrowsRightLeftIcon width={14} /> Staff exchange
          </Eyebrow>
          <h2>Coverage without silent assignment.</h2>
          <p>
            Post opportunities, review eligibility evidence, target expiring
            offers, and decide accepted peer swaps from canonical server state.
          </p>
        </div>
        <HeaderActions>
          <select
            aria-label="Staff exchange facility"
            value={facilityId}
            onChange={(event) => setFacilityId(event.target.value)}
          >
            {facilities.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <IconButton
            type="button"
            onClick={() => void load().catch(() => undefined)}
            disabled={phase === "loading"}
            aria-label="Refresh staff exchange"
          >
            <ArrowPathIcon />
          </IconButton>
        </HeaderActions>
      </Header>
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
      <Summary>
        <Metric>
          <span>Open opportunities</span>
          <strong>
            {posts.filter((item) => item.status === "open").length}
          </strong>
        </Metric>
        <Metric>
          <span>Draft posts</span>
          <strong>
            {posts.filter((item) => item.status === "draft").length}
          </strong>
        </Metric>
        <Metric>
          <span>Opted-in substitutes</span>
          <strong>{substitutes.length}</strong>
        </Metric>
        <Metric>
          <span>Manager swap review</span>
          <strong>{pendingManager}</strong>
        </Metric>
      </Summary>
      <Tabs
        role="tablist"
        aria-label="Staff exchange views"
        onKeyDown={tabKeyDown}
      >
        {(
          [
            ["coverage", BriefcaseIcon, "Open coverage"],
            ["substitutes", UserGroupIcon, "Substitute pool"],
            ["swaps", ArrowsRightLeftIcon, "Peer swaps"],
          ] as const
        ).map(([key, Icon, label]) => (
          <Tab
            key={key}
            id={`exchange-tab-${key}`}
            role="tab"
            aria-selected={tab === key}
            aria-controls={`exchange-panel-${key}`}
            tabIndex={tab === key ? 0 : -1}
            $active={tab === key}
            onClick={() => setTab(key)}
          >
            <Icon /> {label}
          </Tab>
        ))}
      </Tabs>
      {phase === "loading" && (
        <Notice role="status">
          <ArrowPathIcon /> Loading verified coverage opportunities and exchange
          decisions…
        </Notice>
      )}
      {tab === "coverage" && (
        <Section
          id="exchange-panel-coverage"
          role="tabpanel"
          aria-labelledby="exchange-tab-coverage"
        >
          <SectionHead>
            <div>
              <h3>Open-shift board</h3>
              <p>
                A posting is not an assignment. Staff interest only opens a
                review path.
              </p>
            </div>
            <ActionButton
              type="button"
              $variant="primary"
              onClick={openNew}
              disabled={!facilityId}
            >
              <PlusIcon /> New opportunity
            </ActionButton>
          </SectionHead>
          {posts.length ? (
            <Cards>
              {posts.map((post) => {
                const focused =
                  exchangeTarget?.entityType === "staff_open_shift" &&
                  exchangeTarget.entityId === post.id;
                return (
                <Card
                  key={post.id}
                  $focused={focused}
                  data-exchange-target={`staff_open_shift:${post.id}`}
                  tabIndex={focused ? -1 : undefined}
                >
                  <CardTop>
                    <div>
                      <h4>
                        {dateTimeLabel(
                          post.scheduled_start_at,
                          post.facility_timezone,
                        )}
                      </h4>
                      <p>
                        {post.room_name || "Facility-wide"} ·{" "}
                        {post.is_replacement
                          ? "Replacement coverage"
                          : "Additional coverage"}
                      </p>
                    </div>
                    <StatusChip
                      $tone={
                        post.status === "open"
                          ? "success"
                          : post.status === "draft"
                            ? "info"
                            : "neutral"
                      }
                    >
                      {openShiftStatusLabel(post.status)}
                    </StatusChip>
                  </CardTop>
                  {post.public_note && <p>{post.public_note}</p>}
                  <CardActions>
                    {post.can_edit && (
                      <ActionButton
                        type="button"
                        onClick={() => openEdit(post)}
                      >
                        <PencilSquareIcon /> Edit
                      </ActionButton>
                    )}
                    {post.can_post && (
                      <ActionButton
                        type="button"
                        $variant="primary"
                        onClick={() =>
                          setPostingAction({
                            post,
                            kind: "post",
                            operationId: createOperationId(),
                            retryLocked: false,
                            reason: "",
                          })
                        }
                      >
                        <PaperAirplaneIcon /> Post
                      </ActionButton>
                    )}
                    {post.status !== "draft" && (
                      <ActionButton
                        type="button"
                        onClick={() => void loadReview(post)}
                      >
                        <UserGroupIcon />{" "}
                        {post.status === "open"
                          ? "Review candidates"
                          : "View outcome"}
                      </ActionButton>
                    )}
                    {post.can_cancel && (
                      <ActionButton
                        type="button"
                        $variant="danger"
                        onClick={() =>
                          setPostingAction({
                            post,
                            kind: "cancel",
                            operationId: createOperationId(),
                            retryLocked: false,
                            reason: "",
                          })
                        }
                      >
                        <XMarkIcon /> Cancel
                      </ActionButton>
                    )}
                  </CardActions>
                </Card>
                );
              })}
            </Cards>
          ) : (
            <Empty>No open-shift records for this facility and week.</Empty>
          )}
        </Section>
      )}
      {tab === "substitutes" && (
        <Section
          id="exchange-panel-substitutes"
          role="tabpanel"
          aria-labelledby="exchange-tab-substitutes"
        >
          <SectionHead>
            <div>
              <h3>Opted-in substitute pool</h3>
              <p>
                Only safe discovery fields are shown. Availability and leave
                details stay private.
              </p>
            </div>
          </SectionHead>
          {substitutes.length ? (
            <Cards>
              {substitutes.map((candidate) => {
                const focused =
                  exchangeTarget?.entityType === "staff_substitute_profile" &&
                  exchangeTarget.membershipId === candidate.membership_id;
                return (
                <Card
                  key={candidate.membership_id}
                  $focused={focused}
                  data-exchange-target={
                    focused
                      ? `staff_substitute_profile:${exchangeTarget.entityId}`
                      : undefined
                  }
                  tabIndex={focused ? -1 : undefined}
                >
                  <CardTop>
                    <div>
                      <h4>{candidate.staff_display_name}</h4>
                      <p>{candidate.facility_name}</p>
                    </div>
                    <StatusChip
                      $tone={
                        candidate.eligibility === "eligible"
                          ? "success"
                          : candidate.eligibility === "warning"
                            ? "warning"
                            : "neutral"
                      }
                    >
                      {candidate.eligibility}
                    </StatusChip>
                  </CardTop>
                  {candidate.eligibility_reasons.length ? (
                    <ReasonList>
                      {candidate.eligibility_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ReasonList>
                  ) : (
                    <small>
                      Eligible for proactive offers. A posting and explicit
                      acceptance are still required.
                    </small>
                  )}
                </Card>
                );
              })}
            </Cards>
          ) : (
            <Empty>
              No staff have opted into substitute discovery for this facility.
            </Empty>
          )}
        </Section>
      )}
      {tab === "swaps" && (
        <Section
          id="exchange-panel-swaps"
          role="tabpanel"
          aria-labelledby="exchange-tab-swaps"
        >
          <SectionHead>
            <div>
              <h3>Peer exchange decisions</h3>
              <p>
                Coworker acceptance never edits the rota. Manager approval
                performs one atomic replacement.
              </p>
            </div>
          </SectionHead>
          {swaps.length ? (
            <Cards>
              {swaps.map((swap) => {
                const focused =
                  exchangeTarget?.entityType === "staff_shift_swap" &&
                  exchangeTarget.entityId === swap.id;
                return (
                <Card
                  key={swap.id}
                  $focused={focused}
                  data-exchange-target={`staff_shift_swap:${swap.id}`}
                  tabIndex={focused ? -1 : undefined}
                >
                  <CardTop>
                    <div>
                      <h4>
                        {swap.requester_display_name} ·{" "}
                        {swap.kind === "trade"
                          ? `trade with ${swap.counterparty_display_name}`
                          : `cover by ${swap.counterparty_display_name}`}
                      </h4>
                      <p>
                        {dateTimeLabel(
                          swap.requester_schedule.scheduled_start_at,
                          swap.facility_timezone,
                        )}
                      </p>
                    </div>
                    <StatusChip
                      $tone={
                        swap.status === "pending_manager"
                          ? "warning"
                          : swap.status === "approved"
                            ? "success"
                            : "neutral"
                      }
                    >
                      {swapStatusLabel(swap.status)}
                    </StatusChip>
                  </CardTop>
                  {swap.note && <p>{swap.note}</p>}
                  <CardActions>
                    {swap.can_approve && (
                      <ActionButton
                        type="button"
                        $variant="primary"
                        onClick={() =>
                          setSwapDecision({
                            swap,
                            kind: "approve",
                            operationId: createOperationId(),
                            retryLocked: false,
                            reason: "",
                          })
                        }
                      >
                        <CheckCircleIcon /> Review approval
                      </ActionButton>
                    )}
                    {swap.can_reject && (
                      <ActionButton
                        type="button"
                        $variant="danger"
                        onClick={() =>
                          setSwapDecision({
                            swap,
                            kind: "reject",
                            operationId: createOperationId(),
                            retryLocked: false,
                            reason: "",
                          })
                        }
                      >
                        <XMarkIcon /> Review rejection
                      </ActionButton>
                    )}
                  </CardActions>
                </Card>
                );
              })}
            </Cards>
          ) : (
            <Empty>No peer exchange requests in this week.</Empty>
          )}
        </Section>
      )}

      {editor && (
        <WorkforceDialog
          labelId="open-shift-editor-title"
          busy={Boolean(busy)}
          retryLocked={editor.retryLocked}
          onClose={() => setEditor(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <BriefcaseIcon width={14} /> Coverage draft
              </Eyebrow>
              <h2 id="open-shift-editor-title">
                {editor.post
                  ? "Edit opportunity"
                  : editor.sourceScheduleId
                    ? "Find replacement coverage"
                    : "Create an open shift"}
              </h2>
              <p>
                Times use{" "}
                {
                  facilities.find((item) => item.id === editor.facilityId)
                    ?.timezone
                }
                . Save privately, then post when ready.
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setEditor(null)}
              disabled={Boolean(busy) || editor.retryLocked}
              aria-label="Close open-shift editor"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={saveOpenShift}>
            {editor.retryLocked && (
              <Notice>
                <ArrowPathIcon /> Response uncertain. Retry exact save before
                changing these values.
              </Notice>
            )}
            <WorkforceDialogGrid>
              <WorkforceDialogField>
                <span>Facility</span>
                <select
                  required
                  disabled={
                    editor.retryLocked ||
                    Boolean(editor.post) ||
                    Boolean(editor.sourceScheduleId)
                  }
                  value={editor.facilityId}
                  onChange={(event) =>
                    setEditor({
                      ...editor,
                      facilityId: event.target.value,
                      roomId: "",
                    })
                  }
                >
                  {facilities.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>Room</span>
                <select
                  disabled={
                    editor.retryLocked || Boolean(editor.sourceScheduleId)
                  }
                  value={editor.roomId}
                  onChange={(event) =>
                    setEditor({ ...editor, roomId: event.target.value })
                  }
                >
                  <option value="">Facility-wide</option>
                  {workspace.rooms
                    .filter(
                      (item) =>
                        item.facility_id === editor.facilityId &&
                        item.is_active,
                    )
                    .map((room) => (
                      <option key={room.id} value={room.id}>
                        {room.name}
                      </option>
                    ))}
                </select>
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>Date</span>
                <input
                  type="date"
                  required
                  disabled={
                    editor.retryLocked || Boolean(editor.sourceScheduleId)
                  }
                  value={editor.date}
                  onChange={(event) =>
                    setEditor({ ...editor, date: event.target.value })
                  }
                />
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>Timezone</span>
                <input
                  readOnly
                  value={
                    facilities.find((item) => item.id === editor.facilityId)
                      ?.timezone || ""
                  }
                />
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>Starts</span>
                <input
                  type="time"
                  required
                  disabled={
                    editor.retryLocked || Boolean(editor.sourceScheduleId)
                  }
                  value={editor.start}
                  onChange={(event) =>
                    setEditor({ ...editor, start: event.target.value })
                  }
                />
              </WorkforceDialogField>
              <WorkforceDialogField>
                <span>Ends</span>
                <input
                  type="time"
                  required
                  disabled={
                    editor.retryLocked || Boolean(editor.sourceScheduleId)
                  }
                  value={editor.end}
                  onChange={(event) =>
                    setEditor({ ...editor, end: event.target.value })
                  }
                />
              </WorkforceDialogField>
              <WorkforceDialogField $wide>
                <span>Staff-visible note</span>
                <textarea
                  maxLength={1000}
                  disabled={editor.retryLocked}
                  value={editor.note}
                  onChange={(event) =>
                    setEditor({ ...editor, note: event.target.value })
                  }
                  placeholder="What should eligible staff know about this coverage?"
                />
              </WorkforceDialogField>
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
                {busy === "save-open"
                  ? "Saving…"
                  : editor.retryLocked
                    ? "Retry exact save"
                    : "Save draft"}
              </ActionButton>
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}
      {postingAction && (
        <WorkforceDialog
          labelId="posting-action-title"
          busy={Boolean(busy)}
          retryLocked={postingAction.retryLocked}
          onClose={() => setPostingAction(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <ExclamationTriangleIcon width={14} />{" "}
                {postingAction.kind === "post"
                  ? "Publish opportunity"
                  : "Cancel opportunity"}
              </Eyebrow>
              <h2 id="posting-action-title">
                {postingAction.kind === "post"
                  ? "Post this shift to eligible staff?"
                  : "Cancel this open shift?"}
              </h2>
              <p>
                {dateTimeLabel(
                  postingAction.post.scheduled_start_at,
                  postingAction.post.facility_timezone,
                )}{" "}
                · {postingAction.post.room_name || "Facility-wide"}
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setPostingAction(null)}
              disabled={Boolean(busy) || postingAction.retryLocked}
              aria-label="Close action"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={runPostingAction}>
            {postingAction.retryLocked && (
              <Notice>
                <ArrowPathIcon /> Response uncertain. Retry the exact command.
              </Notice>
            )}
            {postingAction.kind === "cancel" && (
              <WorkforceDialogField>
                <span>Required reason</span>
                <textarea
                  required
                  minLength={5}
                  disabled={postingAction.retryLocked}
                  value={postingAction.reason}
                  onChange={(event) =>
                    setPostingAction({
                      ...postingAction,
                      reason: event.target.value,
                    })
                  }
                />
              </WorkforceDialogField>
            )}
            <WorkforceDialogActions>
              <ActionButton
                type="button"
                onClick={() => setPostingAction(null)}
                disabled={Boolean(busy) || postingAction.retryLocked}
              >
                Back
              </ActionButton>
              <ActionButton
                type="submit"
                $variant={
                  postingAction.kind === "cancel" ? "danger" : "primary"
                }
                disabled={Boolean(busy)}
              >
                {busy === "posting-action"
                  ? "Saving…"
                  : postingAction.retryLocked
                    ? "Retry exact action"
                    : postingAction.kind === "post"
                      ? "Post opportunity"
                      : "Cancel shift"}
              </ActionButton>
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}
      {review && !offer && !withdraw && (
        <WorkforceDialog
          labelId="candidate-review-title"
          busy={Boolean(busy)}
          onClose={() => setReview(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <UserGroupIcon width={14} /> Candidate review
              </Eyebrow>
              <h2 id="candidate-review-title">Coverage participation</h2>
              <p>
                {dateTimeLabel(
                  review.post.scheduled_start_at,
                  review.post.facility_timezone,
                )}{" "}
                · interest never creates an assignment.
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setReview(null)}
              disabled={Boolean(busy)}
              aria-label="Close candidate review"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          {review.phase === "loading" && (
            <Notice>
              <ArrowPathIcon /> Loading candidates and engagement history…
            </Notice>
          )}
          {review.phase === "error" && (
            <Notice $error>
              <ExclamationTriangleIcon /> Candidate review could not be
              verified.
            </Notice>
          )}
          {review.phase === "ready" && (
            <div style={{ display: "grid", gap: 12 }}>
              {!reviewDefaultExpiry && (
                <Notice $error>
                  <ClockIcon /> It is too late to issue an expiring offer before
                  this shift starts. Candidate history remains available for
                  review.
                </Notice>
              )}
              <ReviewToolbar>
                <Search>
                  <MagnifyingGlassIcon />
                  <input
                    aria-label="Search eligible staff"
                    value={review.query}
                    onChange={(event) =>
                      setReview({ ...review, query: event.target.value })
                    }
                    placeholder="Search staff"
                  />
                </Search>
                <Select
                  aria-label="Filter candidate eligibility"
                  value={review.eligibility}
                  onChange={(event) =>
                    setReview({ ...review, eligibility: event.target.value })
                  }
                >
                  <option value="all">All eligibility</option>
                  <option value="eligible">Eligible</option>
                  <option value="warning">Review warning</option>
                  <option value="ineligible">Ineligible</option>
                </Select>
              </ReviewToolbar>
              <CandidateList>
                {visibleCandidates.length ? (
                  visibleCandidates.map((candidate) => {
                    const staffEngagements = review.engagements.filter(
                      (item) => item.staff_user_id === candidate.staff_user_id,
                    );
                    const activeOffer = staffEngagements.find(
                      (item) =>
                        item.kind === "offer" && item.status === "pending",
                    );
                    const offerPath = managerOfferPath(
                      candidate,
                      review.engagements,
                    );
                    return (
                      <Candidate key={candidate.membership_id}>
                        <div>
                          <strong>{candidate.staff_display_name}</strong>
                          <small>
                            {candidate.substitute_opted_in
                              ? "Substitute opt-in on"
                              : "Not in substitute discovery"}{" "}
                            · {candidate.eligibility}
                          </small>
                          {!offerPath.allowed && offerPath.reason && (
                            <small>{offerPath.reason}</small>
                          )}
                          {candidate.eligibility_reasons.length > 0 && (
                            <ReasonList>
                              {candidate.eligibility_reasons.map((reason) => (
                                <li key={reason}>{reason}</li>
                              ))}
                            </ReasonList>
                          )}
                          {staffEngagements.map((item) => (
                            <small key={item.id}>
                              {engagementStatusLabel(item)}
                              {item.expires_at
                                ? ` · expires ${dateTimeLabel(item.expires_at, review.post.facility_timezone)}`
                                : ""}
                            </small>
                          ))}
                        </div>
                        <CardActions>
                          {activeOffer?.can_withdraw && (
                            <ActionButton
                              type="button"
                              $variant="danger"
                              onClick={() =>
                                setWithdraw({
                                  engagement: activeOffer,
                                  operationId: createOperationId(),
                                  retryLocked: false,
                                  note: "",
                                })
                              }
                            >
                              Withdraw
                            </ActionButton>
                          )}
                          <ActionButton
                            type="button"
                            $variant="primary"
                            disabled={
                              !offerPath.allowed || !reviewDefaultExpiry
                            }
                            onClick={() => openOffer(candidate)}
                          >
                            <PaperAirplaneIcon />{" "}
                            {offerPath.sourceInterestId
                              ? "Offer from interest"
                              : "Direct offer"}
                          </ActionButton>
                        </CardActions>
                      </Candidate>
                    );
                  })
                ) : (
                  <Empty>No candidates match this review.</Empty>
                )}
              </CandidateList>
              {review.engagements.length > 0 && (
                <Timeline>
                  {review.engagements.map((item) => {
                    const focused =
                      exchangeTarget?.entityType ===
                        "staff_open_shift_engagement" &&
                      exchangeTarget.entityId === item.id;
                    return (
                    <TimelineRow
                      key={item.id}
                      $focused={focused}
                      data-exchange-target={`staff_open_shift_engagement:${item.id}`}
                      tabIndex={focused ? -1 : undefined}
                    >
                      <div>
                        <strong>
                          {item.staff_display_name} ·{" "}
                          {engagementStatusLabel(item)}
                        </strong>
                        <small>
                          {item.note || item.response_note || "No note"} ·{" "}
                          {dateTimeLabel(
                            item.updated_at,
                            review.post.facility_timezone,
                          )}
                        </small>
                      </div>
                      {item.resulting_schedule_id && (
                        <StatusChip $tone="success">Assigned</StatusChip>
                      )}
                    </TimelineRow>
                    );
                  })}
                </Timeline>
              )}
            </div>
          )}
        </WorkforceDialog>
      )}
      {offer && (
        <WorkforceDialog
          labelId="offer-title"
          busy={Boolean(busy)}
          retryLocked={offer.retryLocked}
          onClose={() => setOffer(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <PaperAirplaneIcon width={14} /> Targeted offer
              </Eyebrow>
              <h2 id="offer-title">
                Offer this shift to {offer.candidate.staff_display_name}?
              </h2>
              <p>
                The offer expires explicitly and does not assign work until
                accepted.
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setOffer(null)}
              disabled={Boolean(busy) || offer.retryLocked}
              aria-label="Close offer"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={sendOffer}>
            {offer.retryLocked && (
              <Notice>
                <ArrowPathIcon /> Response uncertain. Retry this exact offer.
              </Notice>
            )}
            <WorkforceDialogGrid>
              <WorkforceDialogField $wide>
                <span>Expiry in {offer.post.facility_timezone}</span>
                <input
                  type="datetime-local"
                  required
                  disabled={offer.retryLocked}
                  min={
                    serverNow
                      ? facilityDateTimeInputValue(
                          new Date(
                            Date.parse(serverNow) + 5 * 60_000,
                          ).toISOString(),
                          offer.post.facility_timezone,
                        )
                      : undefined
                  }
                  max={facilityDateTimeInputValue(
                    new Date(
                      Date.parse(offer.post.scheduled_start_at) - 60_000,
                    ).toISOString(),
                    offer.post.facility_timezone,
                  )}
                  value={offer.expiresLocal}
                  onChange={(event) =>
                    setOffer({ ...offer, expiresLocal: event.target.value })
                  }
                />
                <small>
                  Expiry is required, must be in the future, and must be before
                  the shift starts. Expired offers cannot be accepted or
                  declined.
                </small>
              </WorkforceDialogField>
              <WorkforceDialogField $wide>
                <span>Offer note</span>
                <textarea
                  maxLength={1000}
                  disabled={offer.retryLocked}
                  value={offer.note}
                  onChange={(event) =>
                    setOffer({ ...offer, note: event.target.value })
                  }
                  placeholder="Optional context for this staff member"
                />
              </WorkforceDialogField>
            </WorkforceDialogGrid>
            <WorkforceDialogActions>
              <ActionButton
                type="button"
                onClick={() => setOffer(null)}
                disabled={Boolean(busy) || offer.retryLocked}
              >
                Back
              </ActionButton>
              <ActionButton
                type="submit"
                $variant="primary"
                disabled={Boolean(busy)}
              >
                {busy === "offer"
                  ? "Sending…"
                  : offer.retryLocked
                    ? "Retry exact offer"
                    : "Send offer"}
              </ActionButton>
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}
      {withdraw && (
        <WorkforceDialog
          labelId="withdraw-title"
          busy={Boolean(busy)}
          retryLocked={withdraw.retryLocked}
          onClose={() => setWithdraw(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <XMarkIcon width={14} /> Withdraw offer
              </Eyebrow>
              <h2 id="withdraw-title">Withdraw this pending offer?</h2>
              <p>No schedule will be created by this action.</p>
            </div>
            <IconButton
              type="button"
              onClick={() => setWithdraw(null)}
              disabled={Boolean(busy) || withdraw.retryLocked}
              aria-label="Close withdrawal"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={withdrawOffer}>
            {withdraw.retryLocked && (
              <Notice>
                <ArrowPathIcon /> Response uncertain. Retry the exact
                withdrawal.
              </Notice>
            )}
            <WorkforceDialogField>
              <span>Optional note</span>
              <textarea
                maxLength={1000}
                disabled={withdraw.retryLocked}
                value={withdraw.note}
                onChange={(event) =>
                  setWithdraw({ ...withdraw, note: event.target.value })
                }
              />
            </WorkforceDialogField>
            <WorkforceDialogActions>
              <ActionButton
                type="button"
                onClick={() => setWithdraw(null)}
                disabled={Boolean(busy) || withdraw.retryLocked}
              >
                Back
              </ActionButton>
              <ActionButton
                type="submit"
                $variant="danger"
                disabled={Boolean(busy)}
              >
                {busy === "withdraw"
                  ? "Withdrawing…"
                  : withdraw.retryLocked
                    ? "Retry exact withdrawal"
                    : "Withdraw offer"}
              </ActionButton>
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}
      {swapDecision && (
        <WorkforceDialog
          labelId="swap-decision-title"
          busy={Boolean(busy)}
          retryLocked={swapDecision.retryLocked}
          onClose={() => setSwapDecision(null)}
        >
          <WorkforceDialogHeader>
            <div>
              <Eyebrow>
                <ArrowsRightLeftIcon width={14} /> Atomic swap review
              </Eyebrow>
              <h2 id="swap-decision-title">
                {swapDecision.kind === "approve"
                  ? "Approve these replacement assignments?"
                  : "Reject this peer exchange?"}
              </h2>
              <p>
                The original shifts remain unchanged unless the entire approval
                commits.
              </p>
            </div>
            <IconButton
              type="button"
              onClick={() => setSwapDecision(null)}
              disabled={Boolean(busy) || swapDecision.retryLocked}
              aria-label="Close swap review"
            >
              <XMarkIcon />
            </IconButton>
          </WorkforceDialogHeader>
          <WorkforceDialogForm onSubmit={decideSwap}>
            {swapDecision.retryLocked && (
              <Notice>
                <ArrowPathIcon /> Response uncertain. Retry this exact decision.
              </Notice>
            )}
            <Compare>
              <div>
                <strong>
                  {swapDecision.swap.requester_schedule.staff_display_name}
                </strong>
                <small>
                  {dateTimeLabel(
                    swapDecision.swap.requester_schedule.scheduled_start_at,
                    swapDecision.swap.facility_timezone,
                  )}
                </small>
              </div>
              <ArrowsRightLeftIcon />
              <div>
                <strong>{swapDecision.swap.counterparty_display_name}</strong>
                <small>
                  {swapDecision.swap.counterparty_schedule
                    ? dateTimeLabel(
                        swapDecision.swap.counterparty_schedule
                          .scheduled_start_at,
                        swapDecision.swap.facility_timezone,
                      )
                    : "Covers requester shift"}
                </small>
              </div>
            </Compare>
            {swapDecision.swap.counterparty_response_note && (
              <Notice>
                <CheckCircleIcon /> Coworker response:{" "}
                {swapDecision.swap.counterparty_response_note}
              </Notice>
            )}
            {swapDecision.kind === "reject" && (
              <WorkforceDialogField>
                <span>Required manager reason</span>
                <textarea
                  required
                  minLength={5}
                  disabled={swapDecision.retryLocked}
                  value={swapDecision.reason}
                  onChange={(event) =>
                    setSwapDecision({
                      ...swapDecision,
                      reason: event.target.value,
                    })
                  }
                />
              </WorkforceDialogField>
            )}
            <WorkforceDialogActions>
              <ActionButton
                type="button"
                onClick={() => setSwapDecision(null)}
                disabled={Boolean(busy) || swapDecision.retryLocked}
              >
                Back
              </ActionButton>
              <ActionButton
                type="submit"
                $variant={
                  swapDecision.kind === "approve" ? "primary" : "danger"
                }
                disabled={Boolean(busy)}
              >
                {busy === "swap"
                  ? "Saving…"
                  : swapDecision.retryLocked
                    ? "Retry exact decision"
                    : swapDecision.kind === "approve"
                      ? "Approve atomically"
                      : "Reject swap"}
              </ActionButton>
            </WorkforceDialogActions>
          </WorkforceDialogForm>
        </WorkforceDialog>
      )}
    </Shell>
  );
}
