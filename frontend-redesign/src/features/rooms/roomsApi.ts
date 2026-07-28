import { SESSION_TOKEN_KEY, addOrganizationHeader, notifyAuthorizationDenied } from "../../api/client";
import {
  normalizeProgramType,
  type ProgramType,
} from "../../models/programTypes";
import { parseDeactivationImpact, type DeactivationImpact } from "../../models/deactivationImpact";
import {
  CommandOutcomeUnknownError,
  createExactChildcareCommand,
  exactChildcareCommandBody,
  type ExactChildcareCommand,
} from "../../api/childcareCommand";

const API_URL = (
  import.meta.env.VITE_API_URL || "http://127.0.0.1:3002/api/v1"
).replace(/\/$/, "");

export interface FacilityRecord {
  id: string;
  organization_id: string;
  name: string;
  license_number: string | null;
  licensed_capacity: number;
  city: string | null;
  province: string;
  timezone: string;
  status: string;
}

export interface ProgramRecord {
  id: string;
  organization_id: string;
  facility_id: string;
  name: string;
  program_type: ProgramType;
  capacity: number;
  minimum_age_months: number | null;
  maximum_age_months: number | null;
  is_active: boolean;
}

export interface RoomRecord {
  id: string;
  organization_id: string;
  facility_id: string;
  program_id: string | null;
  name: string;
  capacity: number;
  age_group: string | null;
  minimum_age_months: number | null;
  maximum_age_months: number | null;
  is_active: boolean;
  enrolled_children?: number;
}

export interface RoomWorkspace {
  facilities: FacilityRecord[];
  programs: ProgramRecord[];
  rooms: RoomRecord[];
}

export interface RoomRosterChild {
  child_id: string;
  enrollment_id: string;
  family_id: string;
  family_name: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  date_of_birth: string;
  age_group: string | null;
  child_is_active: boolean;
  profile_photo_url: string | null;
  facility_id: string;
  program_id: string | null;
  room_id: string | null;
  enrollment_status: string;
  enrollment_version: number;
  start_date: string;
  placement_effective_date: string | null;
  end_date: string | null;
}

export interface RoomRosterEntry {
  room_id: string;
  facility_id: string;
  program_id: string | null;
  name: string;
  occupancy: number;
  capacity: number;
  is_active: boolean;
  children: RoomRosterChild[];
  reserved_children: RoomRosterChild[];
}

export interface RoomRoster {
  facility_id: string;
  facility_date: string;
  rooms: RoomRosterEntry[];
  unassigned_children: RoomRosterChild[];
}

export interface RoomPlacementApproval {
  id: string;
  organization_id: string;
  facility_id: string;
  child_id: string;
  program_id: string | null;
  room_id: string | null;
  placement_effective_date: string | null;
  start_date: string;
  end_date: string | null;
  status: string;
  version: number;
  replayed: boolean;
  is_active: boolean;
  facility_name: string;
  program_name: string | null;
  program_type: string | null;
  room_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProgramMutation {
  facility_id: string;
  name: string;
  program_type: ProgramType;
  capacity: number;
  minimum_age_months: number | null;
  maximum_age_months: number | null;
  is_active: boolean;
}

export interface RoomMutation {
  facility_id: string;
  program_id: string;
  name: string;
  capacity: number;
  age_group: string | null;
  minimum_age_months: number | null;
  maximum_age_months: number | null;
  is_active: boolean;
}

export interface RoomUpdateMutation extends RoomMutation {
  deactivation_confirmation?: string;
  deactivation_reason?: string;
}

export interface RoomPlacementCandidate {
  room_id: string;
  room_name: string;
  room_age_group: string | null;
  minimum_age_months: number;
  maximum_age_months: number;
  capacity: number;
  occupancy: number;
  available_places: number;
  program_id: string;
  program_name: string;
  program_type: ProgramType;
}

export interface RoomPlacementReview {
  organization_id: string;
  facility_id: string;
  enrollment_id: string;
  enrollment_version: number;
  child_id: string;
  child_first_name: string;
  child_middle_name: string | null;
  child_last_name: string;
  date_of_birth: string;
  enrollment_start_date: string;
  effective_date: string;
  age_months: number;
  suggestion_state: "none" | "one" | "multiple";
  candidates: RoomPlacementCandidate[];
}

export interface RoomPlacementPlan {
  review: RoomPlacementReview;
  roomId: string;
  command: RoomPlacementApprovalCommand;
}

export type RoomPlacementApprovalCommand = ExactChildcareCommand<{
  room_id: string;
  effective_date: string;
}>;

export class RoomsApiError extends Error {
  constructor(
    message: string,
    public readonly status = 0,
  ) {
    super(message);
    this.name = "RoomsApiError";
  }
}

function detailMessage(payload: unknown, status: number): string {
  if (status === 401) return "Your session expired. Sign in again to continue.";
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : String(item),
        )
        .join("; ");
  }
  if (status === 403)
    return "Your role does not have permission to change rooms or programs.";
  if (status === 409)
    return "That change conflicts with the current room or enrollment state.";
  return `The rooms request failed (${status}).`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem(SESSION_TOKEN_KEY);
  if (!token)
    throw new RoomsApiError("A signed-in CareSync account is required.", 401);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  addOrganizationHeader(headers);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (response.status === 401)
      window.dispatchEvent(new Event("caresync-redesign:unauthorized"));
    if (response.status === 403) notifyAuthorizationDenied();
    throw new RoomsApiError(
      detailMessage(payload, response.status),
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new RoomsApiError(
      `The server returned an invalid ${label} response.`,
    );
  return value as Record<string, unknown>;
}
function string(value: unknown, label: string): string {
  if (typeof value !== "string" || !value)
    throw new RoomsApiError(`The server returned an invalid ${label}.`);
  return value;
}
function nullable(value: unknown, label: string): string | null {
  if (value == null) return null;
  if (typeof value !== "string")
    throw new RoomsApiError(`The server returned an invalid ${label}.`);
  return value;
}
function integer(value: unknown, label: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum)
    throw new RoomsApiError(`The server returned an invalid ${label}.`);
  return Number(value);
}
function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean")
    throw new RoomsApiError(`The server returned an invalid ${label}.`);
  return value;
}
function programType(value: unknown): ProgramType {
  const normalized = normalizeProgramType(value);
  if (!normalized)
    throw new RoomsApiError("The server returned an invalid program type.");
  return normalized;
}

export function parseFacility(value: unknown): FacilityRecord {
  const data = object(value, "facility");
  return {
    id: string(data.id, "facility id"),
    organization_id: string(data.organization_id, "facility organization"),
    name: string(data.name, "facility name"),
    license_number: nullable(data.license_number, "license number"),
    licensed_capacity: integer(data.licensed_capacity, "licensed capacity"),
    city: nullable(data.city, "facility city"),
    province: string(data.province, "facility province"),
    timezone: string(data.timezone, "facility timezone"),
    status: string(data.status, "facility status"),
  };
}
export function parseProgram(value: unknown): ProgramRecord {
  const data = object(value, "program");
  return {
    id: string(data.id, "program id"),
    organization_id: string(data.organization_id, "program organization"),
    facility_id: string(data.facility_id, "program facility"),
    name: string(data.name, "program name"),
    program_type: programType(data.program_type),
    capacity: integer(data.capacity, "program capacity"),
    minimum_age_months:
      data.minimum_age_months == null
        ? null
        : integer(data.minimum_age_months, "minimum age"),
    maximum_age_months:
      data.maximum_age_months == null
        ? null
        : integer(data.maximum_age_months, "maximum age"),
    is_active: boolean(data.is_active, "program status"),
  };
}
export function parseRoom(value: unknown): RoomRecord {
  const data = object(value, "room");
  const result: RoomRecord = {
    id: string(data.id, "room id"),
    organization_id: string(data.organization_id, "room organization"),
    facility_id: string(data.facility_id, "room facility"),
    program_id: nullable(data.program_id, "room program"),
    name: string(data.name, "room name"),
    capacity: integer(data.capacity, "room capacity", 1),
    age_group: nullable(data.age_group, "room age group"),
    minimum_age_months:
      data.minimum_age_months == null
        ? null
        : integer(data.minimum_age_months, "room minimum age"),
    maximum_age_months:
      data.maximum_age_months == null
        ? null
        : integer(data.maximum_age_months, "room maximum age"),
    is_active: boolean(data.is_active, "room status"),
  };
  if (data.enrolled_children !== undefined)
    result.enrolled_children = integer(
      data.enrolled_children,
      "enrolled child count",
    );
  return result;
}

export function parseRoomPlacementReview(value: unknown): RoomPlacementReview {
  const data = object(value, "room placement review");
  const state = string(data.suggestion_state, "room placement state");
  if (!["none", "one", "multiple"].includes(state))
    throw new RoomsApiError(
      "The server returned an invalid room placement state.",
    );
  const candidates = parseArray(
    data.candidates,
    "room placement candidates",
    (item): RoomPlacementCandidate => {
      const candidate = object(item, "room placement candidate");
      const parsed = {
        room_id: string(candidate.room_id, "placement room id"),
        room_name: string(candidate.room_name, "placement room name"),
        room_age_group: nullable(
          candidate.room_age_group,
          "placement age group",
        ),
        minimum_age_months: integer(
          candidate.minimum_age_months,
          "placement minimum age",
        ),
        maximum_age_months: integer(
          candidate.maximum_age_months,
          "placement maximum age",
        ),
        capacity: integer(candidate.capacity, "placement capacity", 1),
        occupancy: integer(candidate.occupancy, "placement occupancy"),
        available_places: integer(
          candidate.available_places,
          "placement available places",
        ),
        program_id: string(candidate.program_id, "placement program id"),
        program_name: string(candidate.program_name, "placement program name"),
        program_type: programType(candidate.program_type),
      };
      if (
        parsed.occupancy > parsed.capacity ||
        parsed.available_places !==
          Math.max(parsed.capacity - parsed.occupancy, 0) ||
        parsed.maximum_age_months < parsed.minimum_age_months
      ) {
        throw new RoomsApiError(
          "The server returned inconsistent room placement capacity or ages.",
        );
      }
      return parsed;
    },
  );
  const available = candidates.filter(
    (candidate) => candidate.available_places > 0,
  );
  const narrowestSpan = available.length
    ? Math.min(
        ...available.map(
          (candidate) =>
            candidate.maximum_age_months - candidate.minimum_age_months,
        ),
      )
    : null;
  const preferredCount =
    narrowestSpan === null
      ? 0
      : available.filter(
          (candidate) =>
            candidate.maximum_age_months - candidate.minimum_age_months ===
            narrowestSpan,
        ).length;
  const expectedState =
    preferredCount === 0 ? "none" : preferredCount === 1 ? "one" : "multiple";
  if (state !== expectedState)
    throw new RoomsApiError(
      "The room placement state did not match its candidates.",
    );
  return {
    organization_id: string(data.organization_id, "placement organization"),
    facility_id: string(data.facility_id, "placement facility"),
    enrollment_id: string(data.enrollment_id, "placement enrollment"),
    enrollment_version: integer(data.enrollment_version, "placement enrollment version", 1),
    child_id: string(data.child_id, "placement child"),
    child_first_name: string(data.child_first_name, "placement first name"),
    child_middle_name: nullable(
      data.child_middle_name,
      "placement middle name",
    ),
    child_last_name: string(data.child_last_name, "placement last name"),
    date_of_birth: string(data.date_of_birth, "placement date of birth"),
    enrollment_start_date: string(
      data.enrollment_start_date,
      "placement enrollment date",
    ),
    effective_date: string(data.effective_date, "placement effective date"),
    age_months: integer(data.age_months, "placement age"),
    suggestion_state: state as RoomPlacementReview["suggestion_state"],
    candidates,
  };
}

export function parseRoomPlacementApproval(
  value: unknown,
): RoomPlacementApproval {
  const data = object(value, "room placement approval");
  return {
    id: string(data.id, "approval enrollment"),
    organization_id: string(data.organization_id, "approval organization"),
    facility_id: string(data.facility_id, "approval facility"),
    child_id: string(data.child_id, "approval child"),
    program_id: nullable(data.program_id, "approval program"),
    room_id: nullable(data.room_id, "approval room"),
    placement_effective_date: nullable(data.placement_effective_date, "approval effective date"),
    start_date: string(data.start_date, "approval start date"),
    end_date: nullable(data.end_date, "approval end date"),
    status: string(data.status, "approval status"),
    version: integer(data.version, "approval version", 1),
    replayed: boolean(data.replayed, "approval replay status"),
    is_active: boolean(data.is_active, "approval active status"),
    facility_name: string(data.facility_name, "approval facility name"),
    program_name: nullable(data.program_name, "approval program name"),
    program_type: nullable(data.program_type, "approval program type"),
    room_name: nullable(data.room_name, "approval room name"),
    created_at: string(data.created_at, "approval created time"),
    updated_at: string(data.updated_at, "approval updated time"),
  };
}

export function parseRoomRosterChild(value: unknown): RoomRosterChild {
  const data = object(value, "room roster child");
  return {
    child_id: string(data.child_id, "roster child id"),
    enrollment_id: string(data.enrollment_id, "roster enrollment id"),
    family_id: string(data.family_id, "roster family id"),
    family_name: string(data.family_name, "roster family name"),
    first_name: string(data.first_name, "roster first name"),
    middle_name: nullable(data.middle_name, "roster middle name"),
    last_name: string(data.last_name, "roster last name"),
    date_of_birth: string(data.date_of_birth, "roster date of birth"),
    age_group: nullable(data.age_group, "roster age group"),
    child_is_active: boolean(data.child_is_active, "roster child status"),
    profile_photo_url: nullable(
      data.profile_photo_url,
      "roster child profile photo",
    ),
    facility_id: string(data.facility_id, "roster facility id"),
    program_id: nullable(data.program_id, "roster program id"),
    room_id: nullable(data.room_id, "roster room id"),
    enrollment_status: string(
      data.enrollment_status,
      "roster enrollment status",
    ),
    enrollment_version: integer(data.enrollment_version, "roster enrollment version", 1),
    start_date: string(data.start_date, "roster enrollment start date"),
    placement_effective_date: nullable(data.placement_effective_date, "roster placement effective date"),
    end_date: nullable(data.end_date, "roster enrollment end date"),
  };
}

export function parseRoomRoster(value: unknown): RoomRoster {
  const data = object(value, "room roster");
  const facilityDate = string(data.facility_date, "room roster facility date");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(facilityDate))
    throw new RoomsApiError("The server returned an invalid room roster facility date.");
  const rooms = parseArray(data.rooms, "room roster rooms", (item) => {
    const entry = object(item, "room roster entry");
    const children = parseArray(
      entry.children,
      "room roster children",
      parseRoomRosterChild,
    );
    const reservedChildren = parseArray(
      entry.reserved_children,
      "reserved room roster children",
      parseRoomRosterChild,
    );
    const occupancy = integer(entry.occupancy, "room roster occupancy");
    if (occupancy !== children.length)
      throw new RoomsApiError(
        "The room roster occupancy did not match its child list.",
      );
    return {
      room_id: string(entry.room_id, "room roster room id"),
      facility_id: string(entry.facility_id, "room roster facility id"),
      program_id: nullable(entry.program_id, "room roster program id"),
      name: string(entry.name, "room roster room name"),
      occupancy,
      capacity: integer(entry.capacity, "room roster capacity", 1),
      is_active: boolean(entry.is_active, "room roster room status"),
      children,
      reserved_children: reservedChildren,
    };
  });
  const result = {
    facility_id: string(data.facility_id, "room roster facility id"),
    facility_date: facilityDate,
    rooms,
    unassigned_children: parseArray(
      data.unassigned_children,
      "unassigned room roster children",
      parseRoomRosterChild,
    ),
  };
  const roomIds = new Set(result.rooms.map((entry) => entry.room_id));
  if (roomIds.size !== result.rooms.length)
    throw new RoomsApiError("The room roster returned a room more than once.");
  const children = [
    ...result.rooms.flatMap((entry) => entry.children),
    ...result.rooms.flatMap((entry) => entry.reserved_children),
    ...result.unassigned_children,
  ];
  if (
    new Set(children.map((child) => child.enrollment_id)).size !==
    children.length
  ) {
    throw new RoomsApiError(
      "The room roster returned an enrollment more than once.",
    );
  }
  return result;
}

function parseArray<T>(
  value: unknown,
  label: string,
  parser: (item: unknown) => T,
): T[] {
  if (!Array.isArray(value))
    throw new RoomsApiError(
      `The server returned an invalid ${label} response.`,
    );
  return value.map(parser);
}

function assertOrganization(
  record: { organization_id: string },
  organizationId: string,
  label: string,
): void {
  if (record.organization_id !== organizationId)
    throw new RoomsApiError(
      `${label} was returned outside the active organization boundary.`,
    );
}

export async function fetchRoomWorkspace(
  organizationId: string,
  signal?: AbortSignal,
): Promise<RoomWorkspace> {
  if (!organizationId)
    throw new RoomsApiError("A confirmed organization context is required.");
  const [facilityPayload, programPayload, roomPayload] = await Promise.all([
    request<unknown>("/facilities", { signal }),
    request<unknown>("/programs", { signal }),
    request<unknown>("/rooms", { signal }),
  ]);
  const workspace = {
    facilities: parseArray(facilityPayload, "facilities", parseFacility),
    programs: parseArray(programPayload, "programs", parseProgram),
    rooms: parseArray(roomPayload, "rooms", parseRoom),
  };
  workspace.facilities.forEach((item) =>
    assertOrganization(item, organizationId, "A facility"),
  );
  workspace.programs.forEach((item) => {
    assertOrganization(item, organizationId, "A program");
    if (
      !workspace.facilities.some((facility) => facility.id === item.facility_id)
    )
      throw new RoomsApiError(
        "A program points outside the loaded facility set.",
      );
  });
  workspace.rooms.forEach((item) => {
    assertOrganization(item, organizationId, "A room");
    if (
      !workspace.facilities.some((facility) => facility.id === item.facility_id)
    )
      throw new RoomsApiError("A room points outside the loaded facility set.");
    if (
      item.program_id &&
      !workspace.programs.some(
        (program) =>
          program.id === item.program_id &&
          program.facility_id === item.facility_id,
      )
    )
      throw new RoomsApiError(
        "A room points to a program outside its facility.",
      );
  });
  return workspace;
}

export async function fetchRoomRoster(
  facilityId: string,
  organizationId: string,
  workspaceRooms: RoomRecord[],
  signal?: AbortSignal,
): Promise<RoomRoster> {
  if (!facilityId || !organizationId)
    throw new RoomsApiError(
      "A confirmed facility and organization are required for its roster.",
    );
  const result = parseRoomRoster(
    await request<unknown>(
      `/room-rosters?facility_id=${encodeURIComponent(facilityId)}`,
      { signal },
    ),
  );
  if (result.facility_id !== facilityId)
    throw new RoomsApiError(
      "The roster response crossed the selected facility boundary.",
    );
  const expectedRooms = workspaceRooms.filter(
    (room) =>
      room.facility_id === facilityId &&
      room.organization_id === organizationId,
  );
  if (
    result.rooms.length !== expectedRooms.length ||
    result.rooms.some(
      (entry) => !expectedRooms.some((room) => room.id === entry.room_id),
    )
  ) {
    throw new RoomsApiError(
      "The roster response did not match the selected facility rooms.",
    );
  }
  result.rooms.forEach((entry) => {
    const room = expectedRooms.find((item) => item.id === entry.room_id)!;
    if (
      entry.facility_id !== facilityId ||
      entry.program_id !== room.program_id ||
      entry.name !== room.name ||
      entry.capacity !== room.capacity ||
      entry.is_active !== room.is_active
    ) {
      throw new RoomsApiError(
        "The roster room did not match the verified room workspace.",
      );
    }
    if (
      [...entry.children, ...entry.reserved_children].some(
        (child) =>
          child.facility_id !== facilityId || child.room_id !== entry.room_id,
      )
    ) {
      throw new RoomsApiError(
        "A roster child crossed the selected room boundary.",
      );
    }
  });
  if (
    result.unassigned_children.some(
      (child) =>
        child.facility_id !== facilityId ||
        child.room_id !== null ||
        child.program_id !== null,
    )
  ) {
    throw new RoomsApiError(
      "An unassigned roster child crossed the selected facility boundary.",
    );
  }
  return result;
}

export async function fetchRoomPlacementReviews(
  facilityId: string,
  organizationId: string,
  workspace: RoomWorkspace,
  signal?: AbortSignal,
): Promise<RoomPlacementReview[]> {
  if (!facilityId || !organizationId)
    throw new RoomsApiError(
      "A confirmed facility and organization are required for placement review.",
    );
  const reviews = parseArray(
    await request<unknown>(
      `/room-placement-reviews?facility_id=${encodeURIComponent(facilityId)}`,
      { signal },
    ),
    "room placement reviews",
    parseRoomPlacementReview,
  );
  const roomIds = new Set(
    workspace.rooms
      .filter(
        (room) =>
          room.facility_id === facilityId &&
          room.organization_id === organizationId,
      )
      .map((room) => room.id),
  );
  reviews.forEach((review) => {
    assertOrganization(review, organizationId, "A room placement review");
    if (
      review.facility_id !== facilityId ||
      review.candidates.some((candidate) => !roomIds.has(candidate.room_id))
    ) {
      throw new RoomsApiError(
        "A room placement review crossed the selected facility boundary.",
      );
    }
  });
  if (
    new Set(reviews.map((review) => review.enrollment_id)).size !==
    reviews.length
  )
    throw new RoomsApiError(
      "An enrollment appeared twice in room placement review.",
    );
  return reviews;
}

function placementCandidate(review: RoomPlacementReview, roomId: string): RoomPlacementCandidate {
  const candidate = review.candidates.find(
    (item) => item.room_id === roomId && item.available_places > 0,
  );
  if (!candidate)
    throw new RoomsApiError(
      "Select an available recommended room before approval.",
    );
  return candidate;
}

export function buildRoomPlacementPlan(
  review: RoomPlacementReview,
  roomId: string,
): RoomPlacementPlan {
  placementCandidate(review, roomId);
  return {
    review,
    roomId,
    command: createExactChildcareCommand({
      room_id: roomId,
      effective_date: review.effective_date,
    }, review.enrollment_version),
  };
}

function unknownPlacementOutcome(caught: unknown): never {
  if (caught instanceof CommandOutcomeUnknownError) throw caught;
  if (
    caught instanceof TypeError
    || caught instanceof SyntaxError
    || (caught instanceof Error && caught.name === "AbortError")
    || (caught instanceof RoomsApiError && (
      caught.status === 0
      || caught.status === 408
      || caught.status === 425
      || caught.status >= 500
    ))
  ) {
    throw new CommandOutcomeUnknownError(
      "CareSync could not confirm the room placement command. Check the saved result; CareSync will not resend it automatically.",
      caught,
    );
  }
  throw caught;
}

function assertPlacementApproval(
  approval: RoomPlacementApproval,
  plan: RoomPlacementPlan,
  organizationId: string,
): void {
  const candidate = placementCandidate(plan.review, plan.roomId);
  assertOrganization(approval, organizationId, "The room placement approval");
  if (
    approval.id !== plan.review.enrollment_id
    || approval.facility_id !== plan.review.facility_id
    || approval.child_id !== plan.review.child_id
    || approval.room_id !== plan.roomId
    || approval.program_id !== candidate.program_id
    || approval.placement_effective_date !== plan.review.effective_date
    || (!approval.replayed && approval.status !== "active")
    || (!approval.replayed && approval.version !== plan.review.enrollment_version + 1)
    || (approval.replayed && approval.version <= plan.review.enrollment_version)
  ) {
    throw new RoomsApiError(
      "The approved room placement did not match the reviewed recommendation.",
    );
  }
}

export async function approveRoomPlacement(
  plan: RoomPlacementPlan,
  organizationId: string,
  signal?: AbortSignal,
): Promise<RoomPlacementApproval> {
  if (
    plan.command.expectedVersion !== plan.review.enrollment_version
    || plan.command.intent.room_id !== plan.roomId
    || plan.command.intent.effective_date !== plan.review.effective_date
  ) throw new RoomsApiError("The exact placement command no longer matches its review.");
  placementCandidate(plan.review, plan.roomId);
  try {
    const approval = parseRoomPlacementApproval(
      await request<unknown>(
        `/enrollments/${encodeURIComponent(plan.review.enrollment_id)}/placement-approval`,
        {
          method: "POST",
          body: JSON.stringify(exactChildcareCommandBody(plan.command)),
          signal,
        },
      ),
    );
    assertPlacementApproval(approval, plan, organizationId);
    return approval;
  } catch (caught) {
    unknownPlacementOutcome(caught);
  }
}

export async function approveRoomPlacementsBatch(
  placements: RoomPlacementPlan[],
  organizationId: string,
  signal?: AbortSignal,
): Promise<RoomPlacementApproval[]> {
  if (!placements.length || placements.length > 250)
    throw new RoomsApiError("Choose between 1 and 250 reviewed room placements.");
  if (new Set(placements.map(({ review }) => review.enrollment_id)).size !== placements.length)
    throw new RoomsApiError("Each enrollment may appear only once in a room placement batch.");
  const expected = placements.map((plan) => {
    const candidate = placementCandidate(plan.review, plan.roomId);
    if (
      plan.command.expectedVersion !== plan.review.enrollment_version
      || plan.command.intent.room_id !== plan.roomId
      || plan.command.intent.effective_date !== plan.review.effective_date
    ) throw new RoomsApiError("An exact batch placement command no longer matches its review.");
    return { ...plan, candidate };
  });
  try {
    const response = object(
      await request<unknown>("/room-placement-approvals/batch", {
        method: "POST",
        body: JSON.stringify({
          placements: expected.map(({ review, command }) => ({
            enrollment_id: review.enrollment_id,
            ...exactChildcareCommandBody(command),
          })),
        }),
        signal,
      }),
      "room placement batch",
    );
    const approvals = parseArray(
      response.approvals,
      "room placement batch approvals",
      parseRoomPlacementApproval,
    );
    if (
      approvals.length !== expected.length
      || new Set(approvals.map((item) => item.id)).size !== approvals.length
    ) throw new RoomsApiError("The room placement batch response did not match the requested placements.");
    expected.forEach((plan, index) => {
      const approval = approvals[index];
      if (approval.id !== plan.review.enrollment_id) {
        throw new RoomsApiError("The room placement batch response order did not match the requested placements.");
      }
      assertPlacementApproval(approval, plan, organizationId);
    });
    return approvals;
  } catch (caught) {
    unknownPlacementOutcome(caught);
  }
}

export async function createProgram(
  payload: ProgramMutation,
  organizationId: string,
): Promise<ProgramRecord> {
  const value = parseProgram(
    await request<unknown>("/programs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  );
  assertOrganization(value, organizationId, "The program");
  if (value.facility_id !== payload.facility_id)
    throw new RoomsApiError(
      "The saved program facility did not match the request.",
    );
  return value;
}

export async function updateProgram(
  id: string,
  payload: ProgramMutation,
  organizationId: string,
): Promise<ProgramRecord> {
  const { facility_id: _facilityId, ...patch } = payload;
  const value = parseProgram(
    await request<unknown>(`/programs/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
  assertOrganization(value, organizationId, "The program");
  return value;
}

export async function createRoom(
  payload: RoomMutation,
  organizationId: string,
): Promise<RoomRecord> {
  const value = parseRoom(
    await request<unknown>("/rooms", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  );
  assertOrganization(value, organizationId, "The room");
  if (value.facility_id !== payload.facility_id)
    throw new RoomsApiError(
      "The saved room facility did not match the request.",
    );
  return value;
}

export async function updateRoom(
  id: string,
  payload: RoomUpdateMutation,
  organizationId: string,
): Promise<RoomRecord> {
  const { facility_id: _facilityId, ...patch } = payload;
  const value = parseRoom(
    await request<unknown>(`/rooms/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  );
  assertOrganization(value, organizationId, "The room");
  return value;
}

export async function fetchRoomDeactivationImpact(
  id: string,
  organizationId: string,
): Promise<DeactivationImpact> {
  return parseDeactivationImpact(
    await request<unknown>(`/rooms/${encodeURIComponent(id)}/deactivation-impact`),
    { organizationId, entityType: "room", entityId: id },
  );
}
