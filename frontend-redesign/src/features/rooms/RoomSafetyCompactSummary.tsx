import {
  ExclamationTriangleIcon,
  SignalIcon,
} from "@heroicons/react/24/outline";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import styled from "styled-components";
import { ACCESS, hasPermission } from "../../auth/accessModel";
import { useSession } from "../../auth/SessionContext";
import {
  useRealtimeRefresh,
  useRealtimeState,
} from "../../realtime/RealtimeContext";
import { GlassPanel, StatusChip } from "../../components/ui/Primitives";
import {
  fetchLiveRoomSafetyBoard,
  fetchLiveRoomSafetyCapability,
  type LiveRoomSafetyBoard,
  type LiveRoomSafetyCapability,
} from "./roomSafetyApi";
import type { RoomRecord } from "./roomsApi";

const Card = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 15px 16px;
  h2 {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0;
    font-size: 0.86rem;
    font-weight: 620;
  }
  h2 svg {
    width: 18px;
    color: ${({ theme }) => theme.color.cyan};
  }
  p {
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
    line-height: 1.5;
  }
  a {
    display: inline-flex;
    min-height: 40px;
    align-items: center;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 9px 4px 9px 4px;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font-size: 0.72rem;
    text-decoration: none;
  }
  @media (max-width: 680px) {
    grid-template-columns: 1fr;
  }
`;
const Summary = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px 14px;
  margin-top: 8px;
  span {
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.7rem;
  }
`;

const LIVE_ENTITIES = [
  "attendance_day",
  "staff_shift",
  "staff_coverage_target",
  "staff_room_presence",
  "room_operational_exception",
  "organization_membership",
  "facility",
  "room",
] as const;

export default function RoomSafetyCompactSummary({
  organizationId,
  facilityId,
  facilityTimezone,
  rooms,
}: {
  organizationId: string;
  facilityId: string;
  facilityTimezone: string;
  rooms: RoomRecord[];
}) {
  const session = useSession();
  const realtimeState = useRealtimeState();
  const canView = [
    ACCESS.facilityRead,
    ACCESS.careRosterRead,
    ACCESS.staffManageEducators,
  ].every((permission) => hasPermission(session.user, permission));
  const [capability, setCapability] =
    useState<LiveRoomSafetyCapability | null>(null);
  const [board, setBoard] = useState<LiveRoomSafetyBoard | null>(null);
  const [checked, setChecked] = useState(false);
  const [boardUnavailable, setBoardUnavailable] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const loadBoard = useCallback(async () => {
    if (!capability || !canView || !organizationId || !facilityId) return;
    try {
      const nextBoard = await fetchLiveRoomSafetyBoard({
        organizationId,
        facilityId,
        facilityTimezone,
        rooms,
      });
      setBoard(nextBoard);
      setBoardUnavailable(false);
      setNow(Date.now());
    } catch (caught) {
      setBoard(null);
      setBoardUnavailable(true);
      throw caught;
    }
  }, [
    canView,
    capability,
    facilityId,
    facilityTimezone,
    organizationId,
    rooms,
  ]);

  useEffect(() => {
    if (!canView || !organizationId || !facilityId) {
      setCapability(null);
      setBoard(null);
      setBoardUnavailable(false);
      setChecked(true);
      return;
    }
    const controller = new AbortController();
    setChecked(false);
    void fetchLiveRoomSafetyCapability(organizationId, controller.signal)
      .then(async (nextCapability) => {
        if (controller.signal.aborted) return;
        setCapability(nextCapability);
        if (!nextCapability) {
          setBoard(null);
          setChecked(true);
          return;
        }
        try {
          const nextBoard = await fetchLiveRoomSafetyBoard({
            organizationId,
            facilityId,
            facilityTimezone,
            rooms,
            signal: controller.signal,
          });
          if (!controller.signal.aborted) {
            setBoard(nextBoard);
            setBoardUnavailable(false);
            setNow(Date.now());
            setChecked(true);
          }
        } catch {
          if (!controller.signal.aborted) {
            setBoard(null);
            setBoardUnavailable(true);
            setChecked(true);
          }
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setCapability(null);
          setBoard(null);
          setBoardUnavailable(false);
          setChecked(true);
        }
      });
    return () => controller.abort();
  }, [canView, facilityId, facilityTimezone, organizationId, rooms]);

  useRealtimeRefresh({
    scope: "compact-live-room-operations",
    organizationId,
    enabled: Boolean(capability && board),
    entityTypes: LIVE_ENTITIES,
    refresh: loadBoard,
  });

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(timer);
  }, []);

  if (!checked || !capability) return null;
  if (!board || boardUnavailable) {
    return (
      <Card $accent="amber" role="status">
        <div>
          <h2>
            <ExclamationTriangleIcon /> Live room operations unavailable
          </h2>
          <p>
            No counts or positive status are shown because the canonical live
            projection could not be verified.
          </p>
        </div>
        <Link
          to={`/rooms?view=live&facility_id=${encodeURIComponent(facilityId)}`}
        >
          Review in Rooms
        </Link>
      </Card>
    );
  }
  const stale =
    realtimeState !== "connected" ||
    now - Date.parse(board.generated_at) >= 60_000;
  const attention = board.facility.overall_state === "attention";
  const unknown =
    stale || board.facility.overall_state === "unknown";
  return (
    <Card $accent={unknown || attention ? "amber" : "cyan"}>
      <div>
        <h2>
          {unknown ? <ExclamationTriangleIcon /> : <SignalIcon />}
          Live room operations
        </h2>
        <Summary>
          <span>
            {board.facility.confirmed_children ?? "—"} confirmed children
          </span>
          <span>{board.facility.located_staff ?? "—"} located staff</span>
          <span>{board.facility.unlocated_staff ?? "—"} unlocated staff</span>
          <span>{board.facility.active_exception_count} active signals</span>
          <StatusChip
            $tone={
              unknown
                ? "neutral"
                : attention
                  ? "warning"
                  : "success"
            }
          >
            {unknown
              ? "Stale or unknown"
              : attention
                ? "Review needed"
                : "Current projection"}
          </StatusChip>
        </Summary>
        <p>
          Operational configured-target evidence only. No regulatory or
          supervision certification.
        </p>
      </div>
      <Link
        to={`/rooms?view=live&facility_id=${encodeURIComponent(facilityId)}`}
      >
        Open live operations
      </Link>
    </Card>
  );
}
