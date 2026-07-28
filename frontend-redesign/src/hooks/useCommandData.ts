import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, type FamilyStats } from '../api/client';
import { useSession } from '../auth/SessionContext';
import { fetchAttendanceRoster, type AttendanceRosterRow } from '../features/attendance/attendanceApi';
import { attendanceCounts } from '../features/attendance/attendanceModel';
import { fetchRoomWorkspace, type RoomWorkspace } from '../features/rooms/roomsApi';
import { fetchChildRecordReadiness, type ChildRecordReadinessResponse } from '../features/dashboard/readinessApi';
import { useRealtimeRefresh } from '../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../realtime/featureIntegrationManifest';

export type ResourceStatus = 'idle' | 'loading' | 'live' | 'empty' | 'error';

export interface ResourceState<T> {
  status: ResourceStatus;
  data: T | null;
  message?: string;
}

export interface TodayAttendanceSummary {
  serviceDate: string;
  refreshedAt: string;
  facilityCount: number;
  facilityFailures: number;
  enrolled: number;
  pending: number;
  onSite: number;
  completed: number;
  absent: number;
}

export interface AttendanceRefreshResult {
  summary: TodayAttendanceSummary;
  message?: string;
}

interface CommandSnapshot {
  key: string;
  families: ResourceState<FamilyStats>;
  workspace: ResourceState<RoomWorkspace>;
  attendance: ResourceState<TodayAttendanceSummary>;
  readiness: ResourceState<ChildRecordReadinessResponse>;
}

export interface CommandData extends CommandSnapshot {
  organizationReady: boolean;
  serviceDate: string;
  timeZone: string;
}

const idle = <T,>(): ResourceState<T> => ({ status: 'idle', data: null });
const loading = <T,>(): ResourceState<T> => ({ status: 'loading', data: null });
const failed = <T,>(caught: unknown): ResourceState<T> => ({
  status: 'error',
  data: null,
  message: caught instanceof Error ? caught.message : 'The resource is unavailable.',
});

export function serviceDateValue(now = new Date(), timeZone?: string): string {
  if (timeZone) {
    try {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(now);
      const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
      if (value.year && value.month && value.day) return `${value.year}-${value.month}-${value.day}`;
    } catch {
      // Fall through to the browser-local calendar only if the saved timezone is invalid.
    }
  }
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Loads each facility independently so one unavailable roster cannot erase the
 * canonical totals returned by the other facilities or block a realtime cursor.
 */
export async function loadAttendanceSummary(
  serviceDate: string,
  facilityIds: readonly string[],
  loadRoster: (facilityId: string) => Promise<AttendanceRosterRow[]>,
  refreshedAt = () => new Date().toISOString(),
): Promise<AttendanceRefreshResult> {
  const results = await Promise.allSettled(facilityIds.map((facilityId) => loadRoster(facilityId)));
  const successfulRosters = results.flatMap((result) => result.status === 'fulfilled' ? [result.value] : []);
  const failedRosters = results.filter((result) => result.status === 'rejected');

  if (facilityIds.length > 0 && successfulRosters.length === 0) {
    const firstFailure = failedRosters[0];
    throw firstFailure?.status === 'rejected'
      ? firstFailure.reason
      : new Error('Attendance rosters are unavailable.');
  }

  const summary: TodayAttendanceSummary = {
    serviceDate,
    refreshedAt: refreshedAt(),
    facilityCount: facilityIds.length,
    facilityFailures: failedRosters.length,
    enrolled: 0,
    pending: 0,
    onSite: 0,
    completed: 0,
    absent: 0,
  };
  successfulRosters.forEach((rows) => {
    const counts = attendanceCounts(rows);
    summary.enrolled += counts.enrolled;
    summary.pending += counts.pending;
    summary.onSite += counts.onSite;
    summary.completed += counts.completed;
    summary.absent += counts.absent;
  });

  return {
    summary,
    message: failedRosters.length
      ? `${successfulRosters.length} of ${facilityIds.length} facility rosters are current; ${failedRosters.length} unavailable.`
      : undefined,
  };
}

function useCommandClock(timeZone: string): { serviceDate: string; refreshVersion: number } {
  const [clock, setClock] = useState(() => ({ serviceDate: serviceDateValue(new Date(), timeZone), refreshVersion: 0 }));
  const lastRefreshAt = useRef(0);

  useEffect(() => {
    setClock((current) => {
      const serviceDate = serviceDateValue(new Date(), timeZone);
      return serviceDate === current.serviceDate ? current : { serviceDate, refreshVersion: current.refreshVersion + 1 };
    });

    const refresh = () => {
      const now = Date.now();
      if (now - lastRefreshAt.current < 10_000) return;
      lastRefreshAt.current = now;
      setClock((current) => ({
        serviceDate: serviceDateValue(new Date(now), timeZone),
        refreshVersion: current.refreshVersion + 1,
      }));
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState !== 'hidden') refresh();
    };
    const interval = window.setInterval(refresh, 120_000);

    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [timeZone]);

  return clock;
}

function createSnapshot(key: string, operational: boolean, includeFamilyStats: boolean): CommandSnapshot {
  return {
    key,
    families: operational && includeFamilyStats ? loading() : { status: 'empty', data: null, message: includeFamilyStats ? undefined : 'Not requested for this role.' },
    workspace: operational ? loading() : idle(),
    attendance: operational ? loading() : idle(),
    readiness: operational && includeFamilyStats ? loading() : { status: 'empty', data: null, message: includeFamilyStats ? undefined : 'Not requested for this role.' },
  };
}

export function useCommandData({ includeFamilyStats = true }: { includeFamilyStats?: boolean } = {}): CommandData {
  const session = useSession();
  const timeZone = session.organization?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Edmonton';
  const { serviceDate, refreshVersion } = useCommandClock(timeZone);
  const organizationReady = session.status === 'authenticated'
    && Boolean(session.user?.organization_id)
    && Boolean(session.organization?.id)
    && session.user?.organization_id === session.organization?.id
    && !session.organizationUnavailable;
  const organizationId = organizationReady ? session.organization!.id : '';
  const identityKey = organizationReady
    ? `${session.user!.id}:${organizationId}`
    : `session:${session.status}:${session.user?.id || 'none'}:${session.organization?.id || 'none'}`;
  const snapshotKey = `${identityKey}:${serviceDate}:families-${includeFamilyStats ? 'yes' : 'no'}`;
  const [snapshot, setSnapshot] = useState<CommandSnapshot>(() => createSnapshot(snapshotKey, organizationReady, includeFamilyStats));

  const refreshCanonical = useCallback(async () => {
    if (!organizationReady || !organizationId) return;
    const [families, workspace, readiness] = await Promise.all([
      includeFamilyStats ? api.familyStats() : Promise.resolve(null),
      fetchRoomWorkspace(organizationId),
      includeFamilyStats ? fetchChildRecordReadiness(organizationId, { limit: 8 }) : Promise.resolve(null),
    ]);
    const activeFacilityIds = workspace.facilities
      .filter((facility) => facility.status === 'active')
      .map((facility) => facility.id);
    const attendanceResult = await loadAttendanceSummary(
      serviceDate,
      activeFacilityIds,
      (facilityId) => fetchAttendanceRoster(serviceDate, facilityId, organizationId),
    );
    setSnapshot((current) => current.key === snapshotKey ? {
      key: snapshotKey,
      families: includeFamilyStats ? { status: 'live', data: families } as ResourceState<FamilyStats> : { status: 'empty', data: null, message: 'Not requested for this role.' },
      workspace: { status: workspace.facilities.length ? 'live' : 'empty', data: workspace },
      attendance: { status: 'live', data: attendanceResult.summary, message: attendanceResult.message },
      readiness: includeFamilyStats ? { status: readiness?.total ? 'live' : 'empty', data: readiness } as ResourceState<ChildRecordReadinessResponse> : { status: 'empty', data: null, message: 'Not requested for this role.' },
    } : current);
  }, [includeFamilyStats, organizationId, organizationReady, serviceDate, snapshotKey]);
  useRealtimeRefresh({ scope: 'dashboard', organizationId, enabled: organizationReady, entityTypes: featureIntegrationManifest.dashboard.realtimeEntities, refresh: refreshCanonical });

  useEffect(() => {
    const controller = new AbortController();
    const requestKey = snapshotKey;
    setSnapshot((current) => current.key === requestKey ? current : createSnapshot(requestKey, organizationReady, includeFamilyStats));

    if (!organizationReady || !organizationId) return () => controller.abort();

    const update = (transform: (current: CommandSnapshot) => CommandSnapshot) => {
      if (controller.signal.aborted) return;
      setSnapshot((current) => current.key === requestKey ? transform(current) : current);
    };

    if (includeFamilyStats) {
      api.familyStats(controller.signal)
        .then((families) => update((current) => ({ ...current, families: { status: 'live', data: families } })))
        .catch((caught) => {
          if (!controller.signal.aborted) update((current) => ({ ...current, families: failed(caught) }));
        });
      fetchChildRecordReadiness(organizationId, { limit: 8 }, controller.signal)
        .then((readiness) => update((current) => ({
          ...current,
          readiness: { status: readiness.total ? 'live' : 'empty', data: readiness },
        })))
        .catch((caught) => {
          if (!controller.signal.aborted) update((current) => ({ ...current, readiness: failed(caught) }));
        });
    }

    fetchRoomWorkspace(organizationId, controller.signal)
      .then(async (workspace) => {
        update((current) => ({
          ...current,
          workspace: { status: workspace.facilities.length ? 'live' : 'empty', data: workspace },
        }));
        const activeFacilityIds = workspace.facilities
          .filter((facility) => facility.status === 'active')
          .map((facility) => facility.id);
        const attendanceResult = await loadAttendanceSummary(
          serviceDate,
          activeFacilityIds,
          (facilityId) => fetchAttendanceRoster(serviceDate, facilityId, organizationId, controller.signal),
        );
        if (controller.signal.aborted) return;
        update((current) => ({
          ...current,
          attendance: {
            status: 'live',
            data: attendanceResult.summary,
            message: attendanceResult.message,
          },
        }));
      })
      .catch((caught) => {
        if (!controller.signal.aborted) {
          update((current) => ({
            ...current,
            workspace: current.workspace.status === 'loading' ? failed(caught) : current.workspace,
            attendance: failed(caught),
          }));
        }
      });

    return () => controller.abort();
  }, [includeFamilyStats, organizationId, organizationReady, refreshVersion, serviceDate, snapshotKey]);

  const current = snapshot.key === snapshotKey ? snapshot : createSnapshot(snapshotKey, organizationReady, includeFamilyStats);
  return useMemo(() => ({ ...current, organizationReady, serviceDate, timeZone }), [current, organizationReady, serviceDate, timeZone]);
}
