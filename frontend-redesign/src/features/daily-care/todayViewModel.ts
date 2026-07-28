import type { ApiUser } from '../../api/client';
import { ACCESS, hasPermission, type AccessPermission } from '../../auth/accessModel';
import type { RoomDailyClosePreview } from './dailyCloseApi';

export type TodayView = 'daybook' | 'daily_close';

export const DAILY_CLOSE_PERMISSIONS = [
  ACCESS.careRead,
  ACCESS.childSafetyRead,
  ACCESS.medicationRead,
  ACCESS.incidentRead,
] as const satisfies readonly AccessPermission[];

export function canOpenDailyClosePreview(user: ApiUser | null | undefined): boolean {
  return DAILY_CLOSE_PERMISSIONS.every((permission) => hasPermission(user, permission));
}

export function nextTodayView(
  current: TodayView,
  key: string,
  dailyCloseAvailable: boolean,
): TodayView {
  const views: readonly TodayView[] = dailyCloseAvailable
    ? ['daybook', 'daily_close']
    : ['daybook'];
  if (key === 'Home') return views[0];
  if (key === 'End') return views[views.length - 1];
  const direction = key === 'ArrowRight' || key === 'ArrowDown'
    ? 1
    : key === 'ArrowLeft' || key === 'ArrowUp'
      ? -1
      : 0;
  if (!direction) return current;
  const currentIndex = Math.max(0, views.indexOf(current));
  return views[(currentIndex + direction + views.length) % views.length];
}

export function dailyCloseBoundaryKey(
  organizationId: string,
  facilityId: string,
  roomId: string,
  serviceDate: string,
): string {
  return `${organizationId}:${facilityId}:${roomId}:${serviceDate}`;
}

export interface DailyCloseRequestTicket {
  readonly boundaryKey: string;
  readonly sequence: number;
}

export interface DailyCloseResourceState {
  key: string;
  status: 'idle' | 'loading' | 'refreshing' | 'ready' | 'error';
  data: RoomDailyClosePreview | null;
  error: string;
}

export function settleQuietDailyCloseFailure(
  current: DailyCloseResourceState,
  boundaryKey: string,
  error: string,
): DailyCloseResourceState {
  if (current.key === boundaryKey && current.data) {
    return { ...current, status: 'ready', error: '' };
  }
  return { key: boundaryKey, status: 'error', data: null, error };
}

export interface DailyCloseRequestGate {
  begin: (boundaryKey: string) => DailyCloseRequestTicket;
  isCurrent: (ticket: DailyCloseRequestTicket, boundaryKey: string) => boolean;
  invalidate: () => void;
}

export function createDailyCloseRequestGate(): DailyCloseRequestGate {
  let sequence = 0;
  return {
    begin(boundaryKey) {
      sequence += 1;
      return { boundaryKey, sequence };
    },
    isCurrent(ticket, boundaryKey) {
      return ticket.sequence === sequence && ticket.boundaryKey === boundaryKey;
    },
    invalidate() {
      sequence += 1;
    },
  };
}
