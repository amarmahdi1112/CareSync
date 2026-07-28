import type { RoomWorkspace } from '../rooms/roomsApi';
import { fetchRoomWorkspace } from '../rooms/roomsApi';
import {
  fetchMedicationPlan,
  fetchMedicationRoomDay,
  type MedicationPlan,
  type MedicationRoomDay,
} from './medicationApi';

export interface MedicationRealtimeRequest {
  organizationId: string;
  facilityId: string;
  roomId: string;
  date: string;
  focusedPlanId: string | null;
}

export interface MedicationRealtimeSnapshot {
  workspace: RoomWorkspace;
  facilityId: string;
  roomId: string;
  key: string;
  day: MedicationRoomDay | null;
  focusedPlan: MedicationPlan | null;
}

interface MedicationRealtimeDependencies {
  workspace: (organizationId: string) => Promise<RoomWorkspace>;
  roomDay: (
    roomId: string,
    date: string,
    organizationId: string,
    facilityId: string,
  ) => Promise<MedicationRoomDay>;
  plan: (planId: string, organizationId: string) => Promise<MedicationPlan>;
}

const dependencies: MedicationRealtimeDependencies = {
  workspace: (organizationId) => fetchRoomWorkspace(organizationId),
  roomDay: (roomId, date, organizationId, facilityId) =>
    fetchMedicationRoomDay(roomId, date, organizationId, facilityId),
  plan: (planId, organizationId) => fetchMedicationPlan(planId, organizationId),
};

/**
 * Rebuild every canonical record rendered by the mounted medication surface.
 * An exact notification target remains part of that surface after its query
 * parameter is cleared, so it must succeed in the same cursor checkpoint as
 * the room-day projection.
 */
export async function fetchMedicationRealtimeSnapshot(
  request: MedicationRealtimeRequest,
  load: MedicationRealtimeDependencies = dependencies,
): Promise<MedicationRealtimeSnapshot> {
  const workspace = await load.workspace(request.organizationId);
  const facilities = workspace.facilities.filter(
    (facility) => facility.status === 'active'
      && workspace.rooms.some(
        (room) => room.is_active && room.facility_id === facility.id,
      ),
  );
  const facilityId = facilities.some((facility) => facility.id === request.facilityId)
    ? request.facilityId
    : facilities[0]?.id || '';
  const rooms = workspace.rooms.filter(
    (room) => room.is_active && room.facility_id === facilityId,
  );
  const roomId = rooms.some((room) => room.id === request.roomId)
    ? request.roomId
    : rooms[0]?.id || '';
  const key = facilityId && roomId
    ? `${request.organizationId}:${facilityId}:${roomId}:${request.date}`
    : '';
  const [day, focusedPlan] = await Promise.all([
    key
      ? load.roomDay(roomId, request.date, request.organizationId, facilityId)
      : Promise.resolve(null),
    request.focusedPlanId
      ? load.plan(request.focusedPlanId, request.organizationId)
      : Promise.resolve(null),
  ]);
  return { workspace, facilityId, roomId, key, day, focusedPlan };
}
