import { ApiError, apiRequest } from "../../api/client";
import type { RoomRecord } from "./roomsApi";

export const LIVE_ROOM_SAFETY_SCHEMA = "live-room-safety-v1" as const;
export const ROOM_EXCEPTION_SCHEMA = "room-operational-exceptions-v1" as const;
export const ROOM_EXCEPTION_TARGET_SCHEMA =
  "room-operational-exception-action-target-v1" as const;
export const LIVE_ROOM_SAFETY_STANDING_BOUNDARY =
  "Operational configured-target evidence only. CareSync does not calculate or certify regulatory ratios, qualifications, group-size rules, licensing compliance or adequate supervision." as const;

export type LiveRoomOverallState =
  | "attention"
  | "unknown"
  | "no_active_configured_target_signal"
  | "not_evaluated";
export type RoomCapacityState =
  | "within_configured_capacity"
  | "above_configured_capacity"
  | "unknown";
export type RoomTargetState =
  | "target_met"
  | "confirmed_staff_below_target"
  | "outside_configured_window"
  | "not_configured"
  | "unknown";
export type RoomExceptionState =
  | "open"
  | "acknowledged"
  | "resolved";
export type RoomExceptionFilter = RoomExceptionState | "all";
export type RoomExceptionCondition =
  | "confirmed_children_above_configured_room_capacity"
  | "confirmed_staff_below_configured_room_target"
  | "open_shift_staff_without_current_room"
  | "present_child_without_active_room"
  | "source_integrity_unknown";

export interface LiveRoomSafetyCapability {
  schema_version: "0041";
  capability: "live_room_presence_safety_board";
  runtime_available: true;
  self_presence_read_path: "/api/v1/staff/self/room-presence";
  self_live_board_path: "/api/v1/staff/self/room-safety/live";
  start_path: "/api/v1/staff/self/room-presence/start";
  move_path: "/api/v1/staff/self/room-presence/move";
  end_path: "/api/v1/staff/self/room-presence/end";
  manager_live_board_path: "/api/v1/room-safety/live";
  manager_exceptions_path: "/api/v1/room-safety/exceptions";
  manager_action_target_path_template: "/api/v1/room-safety/exceptions/{exception_id}/action-target";
  manager_acknowledge_path_template: "/api/v1/room-safety/exceptions/{exception_id}/acknowledge";
  online_only: true;
  operational_configured_target_only: true;
  regulatory_compliance_certified: false;
}

export interface RoomSafetyReleaseStatus {
  schema_version: "0041";
  organization_id: string;
  foundation_available: true;
  complete: boolean;
  active_facility_count: number;
  completed_facility_count: number;
  missing_facility_ids: string[];
  facility_set_sha256: string;
  organization_receipt_id: string | null;
  generated_at: string;
}

export interface RoomSafetyReleaseFacilityReceipt {
  facility_id: string;
  audit_event_id: string;
  client_operation_id: string;
  projection_sha256: string;
  reconciled_at: string;
}

export interface RoomSafetyReleaseResponse {
  schema_version: "0041";
  organization_id: string;
  client_operation_id: string;
  replayed: boolean;
  complete: true;
  facility_set_sha256: string;
  organization_receipt_id: string;
  facility_receipts: RoomSafetyReleaseFacilityReceipt[];
  generated_at: string;
}

export interface LiveRoomConfiguredTarget {
  state: RoomTargetState;
  required_staff: number | null;
  window_start_local: string | null;
  window_end_local: string | null;
}

export interface LiveRoomRow {
  room_id: string;
  room_name: string;
  confirmed_children: number | null;
  configured_room_capacity: number | null;
  capacity_state: RoomCapacityState;
  confirmed_staff: number | null;
  configured_target: LiveRoomConfiguredTarget;
  overall_state: LiveRoomOverallState;
  active_exception_ids: string[];
  data_quality_reason_codes: string[];
}

export interface LiveRoomFacilitySummary {
  confirmed_children: number | null;
  present_children_without_active_room: number | null;
  open_shift_staff: number | null;
  located_staff: number | null;
  unlocated_staff: number | null;
  configured_target: LiveRoomConfiguredTarget;
  overall_state: LiveRoomOverallState;
  active_exception_count: number;
  data_quality_reason_codes: string[];
}

export interface LiveRoomSafetyBoard {
  schema_version: typeof LIVE_ROOM_SAFETY_SCHEMA;
  organization_id: string;
  facility_id: string;
  facility_timezone: string;
  as_of: string;
  view_scope: "facility";
  generated_at: string;
  data_through_realtime_sequence: number | null;
  operational_configured_target_only: true;
  regulatory_compliance_certified: false;
  standing_boundary: typeof LIVE_ROOM_SAFETY_STANDING_BOUNDARY;
  facility: LiveRoomFacilitySummary;
  rooms: LiveRoomRow[];
}

export interface RoomOperationalException {
  id: string;
  facility_id: string;
  scope_kind: "facility" | "room";
  scope_id: string;
  room_id: string | null;
  condition_code: RoomExceptionCondition;
  state: RoomExceptionState;
  version: number;
  opened_at: string;
  materially_changed_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by_user_id: string | null;
  acknowledgement_reason: string | null;
  resolved_at: string | null;
  observed_value: number | null;
  configured_value: number | null;
  source_integrity_reason_codes: string[];
  action_target_path: string;
}

export interface RoomExceptionPage {
  schema_version: typeof ROOM_EXCEPTION_SCHEMA;
  organization_id: string;
  facility_id: string;
  state_filter: RoomExceptionFilter;
  items: RoomOperationalException[];
  next_cursor: string | null;
  generated_at: string;
}

export interface RoomExceptionActionTarget {
  schema_version: typeof ROOM_EXCEPTION_TARGET_SCHEMA;
  organization_id: string;
  facility_id: string;
  room_id: string | null;
  exception_id: string;
  state: RoomExceptionState;
  version: number;
  visible: true;
  action_path: "/rooms";
  generated_at: string;
}

export interface RoomExceptionAcknowledgementRequest {
  client_operation_id: string;
  expected_version: number;
  reason: string;
}

export interface RoomExceptionAcknowledgementReceipt {
  organization_id: string;
  actor_user_id: string;
  event_id: string;
  command_kind: "room_operational_exception_acknowledge";
  event_type: "acknowledged";
  client_operation_id: string;
  request_sha256: string;
  exception_id: string;
  facility_id: string;
  room_id: string | null;
  expected_version: number;
  resulting_version: number;
  occurred_at: string;
}

export interface RoomExceptionAcknowledgementResponse {
  organization_id: string;
  client_operation_id: string;
  request_sha256: string;
  replayed: boolean;
  receipt: RoomExceptionAcknowledgementReceipt;
  exception: RoomOperationalException;
  generated_at: string;
}

export class RoomSafetyContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RoomSafetyContractError";
  }
}

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const SAFE_CODE = /^[a-z][a-z0-9_]{0,79}$/;
const RFC3339_WITH_ZONE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

const CAPABILITY_KEYS = [
  "schema_version",
  "capability",
  "runtime_available",
  "self_presence_read_path",
  "self_live_board_path",
  "start_path",
  "move_path",
  "end_path",
  "manager_live_board_path",
  "manager_exceptions_path",
  "manager_action_target_path_template",
  "manager_acknowledge_path_template",
  "online_only",
  "operational_configured_target_only",
  "regulatory_compliance_certified",
] as const;
const RELEASE_STATUS_KEYS = [
  "schema_version",
  "organization_id",
  "foundation_available",
  "complete",
  "active_facility_count",
  "completed_facility_count",
  "missing_facility_ids",
  "facility_set_sha256",
  "organization_receipt_id",
  "generated_at",
] as const;
const RELEASE_RESPONSE_KEYS = [
  "schema_version",
  "organization_id",
  "client_operation_id",
  "replayed",
  "complete",
  "facility_set_sha256",
  "organization_receipt_id",
  "facility_receipts",
  "generated_at",
] as const;
const RELEASE_FACILITY_RECEIPT_KEYS = [
  "facility_id",
  "audit_event_id",
  "client_operation_id",
  "projection_sha256",
  "reconciled_at",
] as const;
const BOARD_KEYS = [
  "schema_version",
  "organization_id",
  "facility_id",
  "facility_timezone",
  "as_of",
  "view_scope",
  "generated_at",
  "data_through_realtime_sequence",
  "operational_configured_target_only",
  "regulatory_compliance_certified",
  "standing_boundary",
  "facility",
  "rooms",
] as const;
const FACILITY_KEYS = [
  "confirmed_children",
  "present_children_without_active_room",
  "open_shift_staff",
  "located_staff",
  "unlocated_staff",
  "configured_target",
  "overall_state",
  "active_exception_count",
  "data_quality_reason_codes",
] as const;
const ROOM_KEYS = [
  "room_id",
  "room_name",
  "confirmed_children",
  "configured_room_capacity",
  "capacity_state",
  "confirmed_staff",
  "configured_target",
  "overall_state",
  "active_exception_ids",
  "data_quality_reason_codes",
] as const;
const TARGET_KEYS = [
  "state",
  "required_staff",
  "window_start_local",
  "window_end_local",
] as const;
const EXCEPTION_PAGE_KEYS = [
  "schema_version",
  "organization_id",
  "facility_id",
  "state_filter",
  "items",
  "next_cursor",
  "generated_at",
] as const;
const EXCEPTION_KEYS = [
  "id",
  "facility_id",
  "scope_kind",
  "scope_id",
  "room_id",
  "condition_code",
  "state",
  "version",
  "opened_at",
  "materially_changed_at",
  "acknowledged_at",
  "acknowledged_by_user_id",
  "acknowledgement_reason",
  "resolved_at",
  "observed_value",
  "configured_value",
  "source_integrity_reason_codes",
  "action_target_path",
] as const;
const ACTION_TARGET_KEYS = [
  "schema_version",
  "organization_id",
  "facility_id",
  "room_id",
  "exception_id",
  "state",
  "version",
  "visible",
  "action_path",
  "generated_at",
] as const;
const ACKNOWLEDGEMENT_KEYS = [
  "organization_id",
  "client_operation_id",
  "request_sha256",
  "replayed",
  "receipt",
  "exception",
  "generated_at",
] as const;
const RECEIPT_KEYS = [
  "organization_id",
  "actor_user_id",
  "event_id",
  "command_kind",
  "event_type",
  "client_operation_id",
  "request_sha256",
  "exception_id",
  "facility_id",
  "room_id",
  "expected_version",
  "resulting_version",
  "occurred_at",
] as const;

function invalid(label: string): never {
  throw new RoomSafetyContractError(
    `CareSync rejected an invalid live room ${label} response.`,
  );
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    invalid(label);
  return value as Record<string, unknown>;
}

function exactObject<const T extends readonly string[]>(
  value: unknown,
  keys: T,
  label: string,
): Record<T[number], unknown> {
  const row = object(value, label);
  const actual = Object.keys(row).sort();
  const expected = [...keys].sort();
  if (
    actual.length !== expected.length ||
    actual.some((key, index) => key !== expected[index])
  )
    invalid(`${label} shape`);
  return row as Record<T[number], unknown>;
}

function text(
  value: unknown,
  label: string,
  maximum = 500,
): string {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value !== value.trim() ||
    value.length > maximum ||
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)
  )
    invalid(label);
  return value;
}

function nullableText(
  value: unknown,
  label: string,
  maximum = 500,
): string | null {
  return value == null ? null : text(value, label, maximum);
}

function id(value: unknown, label: string): string {
  const result = text(value, label, 36);
  if (!UUID.test(result)) invalid(label);
  return result.toLowerCase();
}

function nullableId(value: unknown, label: string): string | null {
  return value == null ? null : id(value, label);
}

function timestamp(value: unknown, label: string): string {
  const result = text(value, label, 40);
  if (!RFC3339_WITH_ZONE.test(result) || !Number.isFinite(Date.parse(result)))
    invalid(label);
  return result;
}

function timezone(value: unknown, label: string): string {
  const result = text(value, label, 100);
  if (
    result !== "UTC" &&
    !/^[A-Za-z][A-Za-z0-9_+-]*(?:\/[A-Za-z0-9_+-]+)+$/.test(result)
  )
    invalid(label);
  try {
    Intl.DateTimeFormat(undefined, { timeZone: result }).format();
  } catch {
    invalid(label);
  }
  return result;
}

function nullableTimestamp(value: unknown, label: string): string | null {
  return value == null ? null : timestamp(value, label);
}

function integer(
  value: unknown,
  label: string,
  minimum = 0,
  maximum = 1_000_000,
): number {
  if (
    !Number.isSafeInteger(value) ||
    Number(value) < minimum ||
    Number(value) > maximum
  )
    invalid(label);
  return Number(value);
}

function nullableInteger(
  value: unknown,
  label: string,
  minimum = 0,
  maximum = 1_000_000,
): number | null {
  return value == null ? null : integer(value, label, minimum, maximum);
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") invalid(label);
  return value;
}

function oneOf<const T extends readonly string[]>(
  value: unknown,
  values: T,
  label: string,
): T[number] {
  if (typeof value !== "string" || !values.includes(value)) invalid(label);
  return value as T[number];
}

function uniqueIds(value: unknown, label: string, maximum = 100): string[] {
  if (!Array.isArray(value) || value.length > maximum) invalid(label);
  const values = value.map((item) => id(item, label));
  if (new Set(values).size !== values.length) invalid(`${label} duplicates`);
  return values;
}

function reasonCodes(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.length > 50) invalid(label);
  const values = value.map((item) => {
    const code = text(item, label, 80);
    if (!SAFE_CODE.test(code)) invalid(label);
    return code;
  });
  if (new Set(values).size !== values.length) invalid(`${label} duplicates`);
  return values;
}

function parseOverallState(value: unknown, label: string): LiveRoomOverallState {
  return oneOf(
    value,
    [
      "attention",
      "unknown",
      "no_active_configured_target_signal",
      "not_evaluated",
    ] as const,
    label,
  );
}

export function parseLiveRoomSafetyCapability(
  value: unknown,
): LiveRoomSafetyCapability {
  const row = exactObject(value, CAPABILITY_KEYS, "capability");
  if (row.runtime_available !== true)
    invalid("capability availability");
  if (row.operational_configured_target_only !== true)
    invalid("capability operational boundary");
  if (row.regulatory_compliance_certified !== false)
    invalid("capability regulatory boundary");

  const expected = {
    schema_version: "0041",
    capability: "live_room_presence_safety_board",
    self_presence_read_path: "/api/v1/staff/self/room-presence",
    self_live_board_path: "/api/v1/staff/self/room-safety/live",
    start_path: "/api/v1/staff/self/room-presence/start",
    move_path: "/api/v1/staff/self/room-presence/move",
    end_path: "/api/v1/staff/self/room-presence/end",
    manager_live_board_path: "/api/v1/room-safety/live",
    manager_exceptions_path: "/api/v1/room-safety/exceptions",
    manager_action_target_path_template:
      "/api/v1/room-safety/exceptions/{exception_id}/action-target",
    manager_acknowledge_path_template:
      "/api/v1/room-safety/exceptions/{exception_id}/acknowledge",
    online_only: true,
  } as const;
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (row[key as keyof typeof row] !== expectedValue)
      invalid(`capability ${key}`);
  }
  return {
    ...expected,
    runtime_available: true,
    operational_configured_target_only: true,
    regulatory_compliance_certified: false,
  };
}

export function parseRoomSafetyReleaseStatus(
  value: unknown,
  organizationId: string,
): RoomSafetyReleaseStatus {
  const row = exactObject(value, RELEASE_STATUS_KEYS, "release status");
  const expectedOrganizationId = id(
    organizationId,
    "expected release organization",
  );
  const parsedOrganizationId = id(
    row.organization_id,
    "release organization",
  );
  if (
    row.schema_version !== "0041" ||
    row.foundation_available !== true ||
    parsedOrganizationId !== expectedOrganizationId
  )
    invalid("release status boundary");
  const complete = boolean(row.complete, "release completion");
  const activeFacilityCount = integer(
    row.active_facility_count,
    "active release facility count",
    0,
    10_000,
  );
  const completedFacilityCount = integer(
    row.completed_facility_count,
    "completed release facility count",
    0,
    activeFacilityCount,
  );
  const missingFacilityIds = uniqueIds(
    row.missing_facility_ids,
    "missing release facilities",
    10_000,
  );
  const facilitySetSha256 = text(
    row.facility_set_sha256,
    "release facility-set digest",
    64,
  );
  if (!SHA256.test(facilitySetSha256))
    invalid("release facility-set digest");
  const organizationReceiptId = nullableId(
    row.organization_receipt_id,
    "release organization receipt",
  );
  if (
    (complete &&
      (completedFacilityCount !== activeFacilityCount ||
        missingFacilityIds.length !== 0 ||
        organizationReceiptId === null)) ||
    (!complete &&
      (completedFacilityCount !== 0 ||
        missingFacilityIds.length !== activeFacilityCount ||
        organizationReceiptId !== null))
  )
    invalid("release status arithmetic");
  return {
    schema_version: "0041",
    organization_id: parsedOrganizationId,
    foundation_available: true,
    complete,
    active_facility_count: activeFacilityCount,
    completed_facility_count: completedFacilityCount,
    missing_facility_ids: missingFacilityIds,
    facility_set_sha256: facilitySetSha256,
    organization_receipt_id: organizationReceiptId,
    generated_at: timestamp(row.generated_at, "release status generation time"),
  };
}

export function parseRoomSafetyReleaseResponse(
  value: unknown,
  expected: {
    organizationId: string;
    operationId: string;
    facilitySetSha256: string;
    facilityIds: string[];
  },
): RoomSafetyReleaseResponse {
  const row = exactObject(value, RELEASE_RESPONSE_KEYS, "release response");
  const organizationId = id(
    row.organization_id,
    "release response organization",
  );
  const operationId = id(
    row.client_operation_id,
    "release response operation",
  );
  const expectedOrganizationId = id(
    expected.organizationId,
    "expected release response organization",
  );
  const expectedOperationId = id(
    expected.operationId,
    "expected release response operation",
  );
  const expectedFacilityIds = expected.facilityIds
    .map((value) => id(value, "expected release facility"))
    .sort();
  if (new Set(expectedFacilityIds).size !== expectedFacilityIds.length)
    invalid("expected release facility duplicates");
  const facilitySetSha256 = text(
    row.facility_set_sha256,
    "release response facility-set digest",
    64,
  );
  if (
    row.schema_version !== "0041" ||
    row.complete !== true ||
    organizationId !== expectedOrganizationId ||
    operationId !== expectedOperationId ||
    facilitySetSha256 !== expected.facilitySetSha256 ||
    !SHA256.test(facilitySetSha256)
  )
    invalid("release response binding");
  if (
    !Array.isArray(row.facility_receipts) ||
    row.facility_receipts.length !== expectedFacilityIds.length
  )
    invalid("release facility receipts");
  const facilityReceipts = row.facility_receipts.map((value) => {
    const receipt = exactObject(
      value,
      RELEASE_FACILITY_RECEIPT_KEYS,
      "release facility receipt",
    );
    const receiptOperationId = id(
      receipt.client_operation_id,
      "release facility receipt operation",
    );
    const projectionSha256 = text(
      receipt.projection_sha256,
      "release projection digest",
      64,
    );
    if (
      receiptOperationId !== expectedOperationId ||
      !SHA256.test(projectionSha256)
    )
      invalid("release facility receipt binding");
    return {
      facility_id: id(receipt.facility_id, "release receipt facility"),
      audit_event_id: id(
        receipt.audit_event_id,
        "release facility audit receipt",
      ),
      client_operation_id: receiptOperationId,
      projection_sha256: projectionSha256,
      reconciled_at: timestamp(
        receipt.reconciled_at,
        "release facility reconciliation time",
      ),
    };
  });
  const returnedFacilityIds = facilityReceipts
    .map((receipt) => receipt.facility_id)
    .sort();
  const facilityAuditReceiptIds = facilityReceipts.map(
    (receipt) => receipt.audit_event_id,
  );
  if (
    returnedFacilityIds.some(
      (facilityId, index) => facilityId !== expectedFacilityIds[index],
    ) ||
    new Set(facilityAuditReceiptIds).size !==
      facilityAuditReceiptIds.length
  )
    invalid("release facility receipt scope");
  const organizationReceiptId = id(
    row.organization_receipt_id,
    "release organization receipt",
  );
  if (facilityAuditReceiptIds.includes(organizationReceiptId))
    invalid("release receipt identity collision");
  const generatedAt = timestamp(
    row.generated_at,
    "release response generation time",
  );
  if (
    facilityReceipts.some(
      (receipt) =>
        Date.parse(receipt.reconciled_at) > Date.parse(generatedAt),
    )
  )
    invalid("release response chronology");
  return {
    schema_version: "0041",
    organization_id: organizationId,
    client_operation_id: operationId,
    replayed: boolean(row.replayed, "release replay marker"),
    complete: true,
    facility_set_sha256: facilitySetSha256,
    organization_receipt_id: organizationReceiptId,
    facility_receipts: facilityReceipts,
    generated_at: generatedAt,
  };
}

export function parseLiveRoomSafetyCapabilityFromStaffSelf(
  value: unknown,
  organizationId: string,
): LiveRoomSafetyCapability | null {
  const row = object(value, "staff self capability envelope");
  if (
    id(row.organization_id, "capability organization") !==
    id(organizationId, "expected capability organization")
  )
    invalid("capability organization boundary");
  if (!Object.prototype.hasOwnProperty.call(
    row,
    "live_room_presence_safety_board",
  ))
    return null;
  return parseLiveRoomSafetyCapability(
    row.live_room_presence_safety_board,
  );
}

function parseTarget(
  value: unknown,
  confirmedStaff: number | null,
  sourceReasonCodes: readonly string[],
): LiveRoomConfiguredTarget {
  const row = exactObject(value, TARGET_KEYS, "configured target");
  const state = oneOf(
    row.state,
    [
      "target_met",
      "confirmed_staff_below_target",
      "outside_configured_window",
      "not_configured",
      "unknown",
    ] as const,
    "configured target state",
  );
  const requiredStaff = nullableInteger(
    row.required_staff,
    "configured target staff",
    0,
    500,
  );
  const windowStart = nullableText(
    row.window_start_local,
    "configured target window start",
    64,
  );
  const windowEnd = nullableText(
    row.window_end_local,
    "configured target window end",
    64,
  );
  if ((windowStart === null) !== (windowEnd === null))
    invalid("configured target window pair");
  const isAlignedLocalTime = (candidate: string | null) =>
    candidate === null ||
    /^(?:[01]\d|2[0-3]):(?:00|15|30|45)$/.test(candidate);
  if (!isAlignedLocalTime(windowStart) || !isAlignedLocalTime(windowEnd))
    invalid("configured target window alignment");
  if (
    windowStart !== null &&
    windowEnd !== null &&
    windowStart >= windowEnd
  )
    invalid("configured target window order");
  if (state === "target_met" || state === "confirmed_staff_below_target") {
    if (
      requiredStaff === null ||
      confirmedStaff === null ||
      windowStart === null
    )
      invalid("active configured target arithmetic");
    if (
      (state === "target_met" && confirmedStaff < requiredStaff) ||
      (state === "confirmed_staff_below_target" &&
        confirmedStaff >= requiredStaff)
    )
      invalid("configured target comparison");
  }
  const targetValuesAreAbsent =
    requiredStaff === null && windowStart === null && windowEnd === null;
  if (state === "unknown") {
    const retainedActiveTarget =
      requiredStaff !== null &&
      windowStart !== null &&
      windowEnd !== null &&
      confirmedStaff === null &&
      sourceReasonCodes.includes("room_presence_source_incoherent");
    if (!targetValuesAreAbsent && !retainedActiveTarget)
      invalid("unknown configured target evidence");
  } else if (
    (state === "outside_configured_window" ||
      state === "not_configured") &&
    !targetValuesAreAbsent
  ) {
    invalid("inactive configured target value");
  }
  return {
    state,
    required_staff: requiredStaff,
    window_start_local: windowStart,
    window_end_local: windowEnd,
  };
}

function parseRoom(
  value: unknown,
  expected: RoomRecord,
): LiveRoomRow {
  const row = exactObject(value, ROOM_KEYS, "room row");
  const roomId = id(row.room_id, "room id");
  if (
    roomId !== expected.id.toLowerCase() ||
    text(row.room_name, "room name", 200) !== expected.name
  )
    invalid("room workspace boundary");
  const confirmedChildren = nullableInteger(
    row.confirmed_children,
    "confirmed child count",
  );
  const configuredCapacity = nullableInteger(
    row.configured_room_capacity,
    "configured room capacity",
    1,
  );
  if (
    configuredCapacity !== null &&
    configuredCapacity !== expected.capacity
  )
    invalid("configured room capacity source");
  const capacityState = oneOf(
    row.capacity_state,
    [
      "within_configured_capacity",
      "above_configured_capacity",
      "unknown",
    ] as const,
    "configured room capacity state",
  );
  if (confirmedChildren === null || configuredCapacity === null) {
    if (capacityState !== "unknown")
      invalid("unknown configured room capacity");
  } else {
    const expectedCapacityState =
      confirmedChildren <= configuredCapacity
        ? "within_configured_capacity"
        : "above_configured_capacity";
    if (capacityState !== expectedCapacityState)
      invalid("configured room capacity arithmetic");
  }
  const confirmedStaff = nullableInteger(
    row.confirmed_staff,
    "confirmed room staff",
  );
  const reasonCodeValues = reasonCodes(
    row.data_quality_reason_codes,
    "room data-quality reason codes",
  );
  const overallState = parseOverallState(row.overall_state, "room overall state");
  const activeExceptionIds = uniqueIds(
    row.active_exception_ids,
    "active room exception ids",
  );
  const configuredTarget = parseTarget(
    row.configured_target,
    confirmedStaff,
    reasonCodeValues,
  );
  const expectedOverallState: LiveRoomOverallState =
    capacityState === "above_configured_capacity" ||
    configuredTarget.state === "confirmed_staff_below_target"
      ? "attention"
      : capacityState === "unknown" ||
          configuredTarget.state === "unknown" ||
          reasonCodeValues.length > 0
        ? "unknown"
        : configuredTarget.state === "not_configured" ||
            configuredTarget.state === "outside_configured_window"
          ? "not_evaluated"
          : "no_active_configured_target_signal";
  if (overallState !== expectedOverallState)
    invalid("room overall-state arithmetic");
  if (
    overallState === "no_active_configured_target_signal" &&
    (reasonCodeValues.length > 0 ||
      confirmedChildren === null ||
      configuredCapacity === null ||
      confirmedStaff === null ||
      capacityState === "above_configured_capacity" ||
      activeExceptionIds.length > 0 ||
      configuredTarget.state === "confirmed_staff_below_target" ||
      configuredTarget.state === "unknown")
  )
    invalid("positive room state");
  return {
    room_id: roomId,
    room_name: expected.name,
    confirmed_children: confirmedChildren,
    configured_room_capacity: configuredCapacity,
    capacity_state: capacityState,
    confirmed_staff: confirmedStaff,
    configured_target: configuredTarget,
    overall_state: overallState,
    active_exception_ids: activeExceptionIds,
    data_quality_reason_codes: reasonCodeValues,
  };
}

function parseFacility(value: unknown): LiveRoomFacilitySummary {
  const row = exactObject(value, FACILITY_KEYS, "facility summary");
  const openShiftStaff = nullableInteger(
    row.open_shift_staff,
    "open actual-shift staff",
  );
  const locatedStaff = nullableInteger(row.located_staff, "located staff");
  const unlocatedStaff = nullableInteger(row.unlocated_staff, "unlocated staff");
  if (
    [openShiftStaff, locatedStaff, unlocatedStaff].some((item) => item === null)
  ) {
    if (
      [openShiftStaff, locatedStaff, unlocatedStaff].some(
        (item) => item !== null,
      )
    )
      invalid("facility staff reconciliation");
  } else if (openShiftStaff !== locatedStaff! + unlocatedStaff!) {
    invalid("facility staff arithmetic");
  }
  const reasonCodeValues = reasonCodes(
    row.data_quality_reason_codes,
    "facility data-quality reason codes",
  );
  const overallState = parseOverallState(
    row.overall_state,
    "facility overall state",
  );
  const confirmedChildren = nullableInteger(
    row.confirmed_children,
    "facility confirmed children",
  );
  const presentChildrenWithoutActiveRoom = nullableInteger(
    row.present_children_without_active_room,
    "present children without an active room",
  );
  const configuredTarget = parseTarget(
    row.configured_target,
    openShiftStaff,
    reasonCodeValues,
  );
  const activeExceptionCount = integer(
    row.active_exception_count,
    "active facility exception count",
    0,
    10_000,
  );
  if (
    overallState === "no_active_configured_target_signal" &&
    (reasonCodeValues.length > 0 ||
      confirmedChildren === null ||
      openShiftStaff === null ||
      presentChildrenWithoutActiveRoom === null ||
      presentChildrenWithoutActiveRoom > 0 ||
      unlocatedStaff === null ||
      unlocatedStaff > 0 ||
      activeExceptionCount > 0 ||
      configuredTarget.state === "confirmed_staff_below_target" ||
      configuredTarget.state === "unknown")
  )
    invalid("positive facility state");
  return {
    confirmed_children: confirmedChildren,
    present_children_without_active_room: presentChildrenWithoutActiveRoom,
    open_shift_staff: openShiftStaff,
    located_staff: locatedStaff,
    unlocated_staff: unlocatedStaff,
    configured_target: configuredTarget,
    overall_state: overallState,
    active_exception_count: activeExceptionCount,
    data_quality_reason_codes: reasonCodeValues,
  };
}

export function parseLiveRoomSafetyBoard(
  value: unknown,
  expected: {
    organizationId: string;
    facilityId: string;
    facilityTimezone: string;
    rooms: RoomRecord[];
  },
): LiveRoomSafetyBoard {
  const row = exactObject(value, BOARD_KEYS, "board");
  if (row.schema_version !== LIVE_ROOM_SAFETY_SCHEMA)
    invalid("board schema");
  const organizationId = id(row.organization_id, "board organization");
  const facilityId = id(row.facility_id, "board facility");
  if (
    organizationId !== expected.organizationId.toLowerCase() ||
    facilityId !== expected.facilityId.toLowerCase() ||
    row.view_scope !== "facility"
  )
    invalid("board scope");
  if (row.operational_configured_target_only !== true)
    invalid("board operational boundary");
  if (row.regulatory_compliance_certified !== false)
    invalid("board regulatory boundary");
  if (row.standing_boundary !== LIVE_ROOM_SAFETY_STANDING_BOUNDARY)
    invalid("board standing boundary");
  const facilityTimezone = timezone(
    row.facility_timezone,
    "board facility timezone",
  );
  if (facilityTimezone !== expected.facilityTimezone)
    invalid("board facility timezone boundary");
  const asOf = timestamp(row.as_of, "board projection instant");
  const generatedAt = timestamp(row.generated_at, "board generation time");
  if (Date.parse(asOf) > Date.parse(generatedAt))
    invalid("board projection chronology");
  if (!Array.isArray(row.rooms) || row.rooms.length > 500)
    invalid("board rooms");
  const activeRooms = expected.rooms.filter(
    (room) =>
      room.organization_id.toLowerCase() === organizationId &&
      room.facility_id.toLowerCase() === facilityId &&
      room.is_active,
  );
  if (row.rooms.length !== activeRooms.length)
    invalid("board active-room completeness");
  const expectedById = new Map(
    activeRooms.map((room) => [room.id.toLowerCase(), room]),
  );
  const parsedRooms = row.rooms.map((item) => {
    const raw = object(item, "room row");
    const roomId = id(raw.room_id, "room id");
    const expectedRoom = expectedById.get(roomId);
    if (!expectedRoom) invalid("room facility boundary");
    return parseRoom(item, expectedRoom!);
  });
  if (new Set(parsedRooms.map((room) => room.room_id)).size !== parsedRooms.length)
    invalid("duplicate room");
  const facility = parseFacility(row.facility);
  const facilityChildrenKnown =
    facility.confirmed_children !== null &&
    facility.present_children_without_active_room !== null;
  const facilityChildrenAbsent =
    facility.confirmed_children === null &&
    facility.present_children_without_active_room === null;
  const roomChildrenKnown = parsedRooms.every(
    (room) => room.confirmed_children !== null,
  );
  const roomChildrenAbsent = parsedRooms.every(
    (room) => room.confirmed_children === null,
  );
  if (
    (!facilityChildrenKnown && !facilityChildrenAbsent) ||
    (facilityChildrenKnown && !roomChildrenKnown) ||
    (facilityChildrenAbsent && !roomChildrenAbsent)
  )
    invalid("facility child completeness");
  if (
    facilityChildrenKnown &&
    facility.confirmed_children !==
      parsedRooms.reduce(
        (total, room) => total + (room.confirmed_children ?? 0),
        0,
      ) +
        facility.present_children_without_active_room!
  )
    invalid("facility child reconciliation");
  const facilityStaffKnown =
    facility.open_shift_staff !== null &&
    facility.located_staff !== null &&
    facility.unlocated_staff !== null;
  const facilityStaffAbsent =
    facility.open_shift_staff === null &&
    facility.located_staff === null &&
    facility.unlocated_staff === null;
  const roomStaffKnown = parsedRooms.every(
    (room) => room.confirmed_staff !== null,
  );
  const roomStaffAbsent = parsedRooms.every(
    (room) => room.confirmed_staff === null,
  );
  if (
    (!facilityStaffKnown && !facilityStaffAbsent) ||
    (facilityStaffKnown && !roomStaffKnown) ||
    (facilityStaffAbsent && !roomStaffAbsent)
  )
    invalid("facility staff completeness");
  if (
    facilityStaffKnown &&
    facility.located_staff !==
      parsedRooms.reduce(
        (total, room) => total + (room.confirmed_staff ?? 0),
        0,
      )
  )
    invalid("facility located-staff reconciliation");
  const visibleFacilityAttention =
    (facility.unlocated_staff ?? 0) > 0 ||
    (facility.present_children_without_active_room ?? 0) > 0 ||
    facility.configured_target.state ===
      "confirmed_staff_below_target" ||
    parsedRooms.some((room) => room.overall_state === "attention");
  const visibleFacilityUnknown =
    facility.confirmed_children === null ||
    facility.present_children_without_active_room === null ||
    facility.open_shift_staff === null ||
    facility.located_staff === null ||
    facility.unlocated_staff === null ||
    facility.configured_target.state === "unknown" ||
    facility.data_quality_reason_codes.length > 0 ||
    parsedRooms.some((room) => room.overall_state === "unknown");
  const neutralFacilityState: LiveRoomOverallState =
    (facility.configured_target.state === "not_configured" ||
      facility.configured_target.state ===
        "outside_configured_window") &&
    parsedRooms.every((room) => room.overall_state === "not_evaluated")
      ? "not_evaluated"
      : "no_active_configured_target_signal";
  const expectedFacilityState: LiveRoomOverallState =
    visibleFacilityAttention
      ? "attention"
      : visibleFacilityUnknown
        ? "unknown"
        : neutralFacilityState;
  if (facility.overall_state !== expectedFacilityState)
    invalid("facility overall-state arithmetic");
  return {
    schema_version: LIVE_ROOM_SAFETY_SCHEMA,
    organization_id: organizationId,
    facility_id: facilityId,
    facility_timezone: facilityTimezone,
    as_of: asOf,
    view_scope: "facility",
    generated_at: generatedAt,
    data_through_realtime_sequence: nullableInteger(
      row.data_through_realtime_sequence,
      "board realtime sequence",
      0,
      Number.MAX_SAFE_INTEGER,
    ),
    operational_configured_target_only: true,
    regulatory_compliance_certified: false,
    standing_boundary: LIVE_ROOM_SAFETY_STANDING_BOUNDARY,
    facility,
    rooms: parsedRooms,
  };
}

function parseExceptionState(value: unknown, label: string): RoomExceptionState {
  return oneOf(
    value,
    ["open", "acknowledged", "resolved"] as const,
    label,
  );
}

function parseCondition(value: unknown): RoomExceptionCondition {
  return oneOf(
    value,
    [
      "confirmed_children_above_configured_room_capacity",
      "confirmed_staff_below_configured_room_target",
      "open_shift_staff_without_current_room",
      "present_child_without_active_room",
      "source_integrity_unknown",
    ] as const,
    "exception condition",
  );
}

export function parseRoomOperationalException(
  value: unknown,
  expectedFacilityId: string,
): RoomOperationalException {
  const row = exactObject(value, EXCEPTION_KEYS, "exception");
  const exceptionId = id(row.id, "exception id");
  const facilityId = id(row.facility_id, "exception facility");
  if (facilityId !== expectedFacilityId.toLowerCase())
    invalid("exception facility boundary");
  const scopeKind = oneOf(
    row.scope_kind,
    ["facility", "room"] as const,
    "exception scope",
  );
  const scopeId = id(row.scope_id, "exception scope id");
  const roomId = nullableId(row.room_id, "exception room");
  if (
    (scopeKind === "facility" &&
      (scopeId !== facilityId || roomId !== null)) ||
    (scopeKind === "room" &&
      (roomId === null || scopeId !== roomId))
  )
    invalid("exception scope binding");
  const state = parseExceptionState(row.state, "exception state");
  const acknowledgedAt = nullableTimestamp(
    row.acknowledged_at,
    "exception acknowledgement time",
  );
  const acknowledgedBy = nullableId(
    row.acknowledged_by_user_id,
    "exception acknowledging actor",
  );
  const acknowledgementReason = nullableText(
    row.acknowledgement_reason,
    "exception acknowledgement reason",
  );
  const acknowledgementValues = [
    acknowledgedAt,
    acknowledgedBy,
    acknowledgementReason,
  ];
  if (
    acknowledgementValues.some((item) => item === null) &&
    acknowledgementValues.some((item) => item !== null)
  )
    invalid("exception acknowledgement evidence");
  if (state === "open" && acknowledgementValues.some((item) => item !== null))
    invalid("open exception acknowledgement");
  if (
    state === "acknowledged" &&
    acknowledgementValues.some((item) => item === null)
  )
    invalid("acknowledged exception evidence");
  const resolvedAt = nullableTimestamp(
    row.resolved_at,
    "exception resolution time",
  );
  if (
    (state === "resolved" && resolvedAt === null) ||
    (state !== "resolved" && resolvedAt !== null)
  )
    invalid("exception resolution state");
  const actionTargetPath = text(
    row.action_target_path,
    "exception action-target path",
    250,
  );
  if (
    actionTargetPath !==
    `/api/v1/room-safety/exceptions/${exceptionId}/action-target`
  )
    invalid("exception action-target binding");
  const condition = parseCondition(row.condition_code);
  const sourceReasons = reasonCodes(
    row.source_integrity_reason_codes,
    "exception source-integrity reasons",
  );
  const roomOnlyCondition =
    condition === "confirmed_children_above_configured_room_capacity";
  const configuredThresholdCondition =
    roomOnlyCondition ||
    condition === "confirmed_staff_below_configured_room_target";
  const facilityOnlyCondition =
    condition === "open_shift_staff_without_current_room" ||
    condition === "present_child_without_active_room";
  if (
    (roomOnlyCondition && scopeKind !== "room") ||
    (facilityOnlyCondition && scopeKind !== "facility")
  )
    invalid("exception condition scope");
  const observedValue = nullableInteger(
    row.observed_value,
    "exception observed value",
  );
  const configuredValue = nullableInteger(
    row.configured_value,
    "exception configured value",
  );
  if (condition === "source_integrity_unknown") {
    if (
      sourceReasons.length === 0 ||
      observedValue !== null ||
      configuredValue !== null
    )
      invalid("source-integrity exception evidence");
  } else {
    if (
      sourceReasons.length > 0 ||
      observedValue === null ||
      configuredValue === null ||
      (configuredThresholdCondition && configuredValue <= 0)
    )
      invalid("configured exception evidence");
    if (
      condition === "confirmed_children_above_configured_room_capacity" &&
      observedValue <= configuredValue
    )
      invalid("configured capacity exception arithmetic");
    if (
      condition === "confirmed_staff_below_configured_room_target" &&
      observedValue >= configuredValue
    )
      invalid("configured target exception arithmetic");
    if (
      facilityOnlyCondition &&
      (observedValue <= 0 || configuredValue !== 0)
    )
      invalid("facility exception arithmetic");
  }
  const openedAt = timestamp(row.opened_at, "exception opening time");
  const materiallyChangedAt = nullableTimestamp(
    row.materially_changed_at,
    "exception change time",
  );
  if (
    (materiallyChangedAt &&
      Date.parse(materiallyChangedAt) <= Date.parse(openedAt)) ||
    (acknowledgedAt && Date.parse(acknowledgedAt) < Date.parse(openedAt)) ||
    (resolvedAt && Date.parse(resolvedAt) < Date.parse(openedAt)) ||
    (acknowledgedAt &&
      resolvedAt &&
      Date.parse(acknowledgedAt) > Date.parse(resolvedAt))
  )
    invalid("exception chronology");
  return {
    id: exceptionId,
    facility_id: facilityId,
    scope_kind: scopeKind,
    scope_id: scopeId,
    room_id: roomId,
    condition_code: condition,
    state,
    version: integer(row.version, "exception version", 1),
    opened_at: openedAt,
    materially_changed_at: materiallyChangedAt,
    acknowledged_at: acknowledgedAt,
    acknowledged_by_user_id: acknowledgedBy,
    acknowledgement_reason: acknowledgementReason,
    resolved_at: resolvedAt,
    observed_value: observedValue,
    configured_value: configuredValue,
    source_integrity_reason_codes: sourceReasons,
    action_target_path: actionTargetPath,
  };
}

export function parseRoomExceptionPage(
  value: unknown,
  expected: {
    organizationId: string;
    facilityId: string;
    stateFilter: RoomExceptionFilter;
    limit: number;
  },
): RoomExceptionPage {
  const row = exactObject(value, EXCEPTION_PAGE_KEYS, "exception page");
  if (row.schema_version !== ROOM_EXCEPTION_SCHEMA)
    invalid("exception page schema");
  const organizationId = id(
    row.organization_id,
    "exception page organization",
  );
  const facilityId = id(row.facility_id, "exception page facility");
  const stateFilter = oneOf(
    row.state_filter,
    ["open", "acknowledged", "resolved", "all"] as const,
    "exception state filter",
  );
  if (
    organizationId !== expected.organizationId.toLowerCase() ||
    facilityId !== expected.facilityId.toLowerCase() ||
    stateFilter !== expected.stateFilter
  )
    invalid("exception page scope");
  if (!Array.isArray(row.items) || row.items.length > expected.limit)
    invalid("exception page size");
  const items = row.items.map((item) =>
    parseRoomOperationalException(item, facilityId),
  );
  if (new Set(items.map((item) => item.id)).size !== items.length)
    invalid("duplicate exception");
  if (
    stateFilter !== "all" &&
    items.some((item) => item.state !== stateFilter)
  )
    invalid("exception filter result");
  const nextCursor = nullableText(
    row.next_cursor,
    "exception continuation",
    500,
  );
  if (nextCursor !== null && !/^[A-Za-z0-9_-]+$/.test(nextCursor))
    invalid("exception continuation encoding");
  return {
    schema_version: ROOM_EXCEPTION_SCHEMA,
    organization_id: organizationId,
    facility_id: facilityId,
    state_filter: stateFilter,
    items,
    next_cursor: nextCursor,
    generated_at: timestamp(row.generated_at, "exception page generation time"),
  };
}

export function parseRoomExceptionActionTarget(
  value: unknown,
  expected: {
    organizationId: string;
    exceptionId: string;
    facilityId?: string;
    roomId?: string | null;
  },
): RoomExceptionActionTarget {
  const row = exactObject(value, ACTION_TARGET_KEYS, "exception action target");
  if (row.schema_version !== ROOM_EXCEPTION_TARGET_SCHEMA)
    invalid("exception action-target schema");
  const organizationId = id(
    row.organization_id,
    "action-target organization",
  );
  const exceptionId = id(row.exception_id, "action-target exception");
  const facilityId = id(row.facility_id, "action-target facility");
  const roomId = nullableId(row.room_id, "action-target room");
  if (
    organizationId !== expected.organizationId.toLowerCase() ||
    exceptionId !== expected.exceptionId.toLowerCase() ||
    (expected.facilityId !== undefined &&
      facilityId !== expected.facilityId.toLowerCase()) ||
    (expected.roomId !== undefined &&
      roomId !== (expected.roomId?.toLowerCase() ?? null)) ||
    row.visible !== true ||
    row.action_path !== "/rooms"
  )
    invalid("exception action-target boundary");
  return {
    schema_version: ROOM_EXCEPTION_TARGET_SCHEMA,
    organization_id: organizationId,
    facility_id: facilityId,
    room_id: roomId,
    exception_id: exceptionId,
    state: parseExceptionState(row.state, "action-target state"),
    version: integer(row.version, "action-target version", 1),
    visible: true,
    action_path: "/rooms",
    generated_at: timestamp(
      row.generated_at,
      "action-target generation time",
    ),
  };
}

export function normalizeRoomExceptionAcknowledgementReason(
  value: string,
): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  if (
    normalized.length < 5 ||
    normalized.length > 500 ||
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(normalized)
  )
    throw new RoomSafetyContractError(
      "Acknowledgement reason must contain 5 to 500 readable characters.",
    );
  return normalized;
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object")
    return JSON.stringify(value);
  if (Array.isArray(value))
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  return `{${Object.entries(value as Record<string, unknown>)
    .filter(([, child]) => child !== undefined)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, child]) => `${JSON.stringify(key)}:${canonicalJson(child)}`)
    .join(",")}}`;
}

async function canonicalSha256(value: unknown): Promise<string> {
  if (!globalThis.crypto?.subtle)
    throw new RoomSafetyContractError(
      "Secure command receipt verification is unavailable.",
    );
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonicalJson(value)),
  );
  return [...new Uint8Array(digest)]
    .map((part) => part.toString(16).padStart(2, "0"))
    .join("");
}

export async function roomSafetyFacilitySetSha256(
  facilityIds: string[],
): Promise<string> {
  const normalized = facilityIds
    .map((value) => id(value, "release facility digest"))
    .sort();
  if (new Set(normalized).size !== normalized.length)
    throw new RoomSafetyContractError(
      "The release facility review contains a duplicate facility.",
    );
  return canonicalSha256({ facility_ids: normalized });
}

export async function roomExceptionAcknowledgementRequestSha256(input: {
  organizationId: string;
  actorUserId: string;
  exceptionId: string;
  facilityId: string;
  roomId: string | null;
  operationId: string;
  expectedVersion: number;
  normalizedReason: string;
}): Promise<string> {
  const organizationId = id(
    input.organizationId,
    "acknowledgement expected organization",
  );
  const actorUserId = id(
    input.actorUserId,
    "acknowledgement expected actor",
  );
  const exceptionId = id(
    input.exceptionId,
    "acknowledgement expected exception",
  );
  const facilityId = id(
    input.facilityId,
    "acknowledgement expected facility",
  );
  const roomId = nullableId(
    input.roomId,
    "acknowledgement expected room",
  );
  const operationId = id(
    input.operationId,
    "acknowledgement expected operation",
  );
  const expectedVersion = integer(
    input.expectedVersion,
    "acknowledgement expected version",
    1,
  );
  const reason = normalizeRoomExceptionAcknowledgementReason(
    input.normalizedReason,
  );
  return canonicalSha256({
    actor_user_id: actorUserId,
    client_operation_id: operationId,
    command_kind: "room_operational_exception_acknowledge",
    exception_id: exceptionId,
    expected_version: expectedVersion,
    facility_id: facilityId,
    organization_id: organizationId,
    reason,
    room_id: roomId,
  });
}

export async function parseRoomExceptionAcknowledgement(
  value: unknown,
  expected: {
    organizationId: string;
    actorUserId: string;
    exceptionId: string;
    facilityId: string;
    roomId: string | null;
    operationId: string;
    expectedVersion: number;
    normalizedReason: string;
  },
): Promise<RoomExceptionAcknowledgementResponse> {
  const row = exactObject(value, ACKNOWLEDGEMENT_KEYS, "acknowledgement");
  const organizationId = id(
    row.organization_id,
    "acknowledgement organization",
  );
  const operationId = id(
    row.client_operation_id,
    "acknowledgement operation",
  );
  if (
    organizationId !== expected.organizationId.toLowerCase() ||
    operationId !== expected.operationId.toLowerCase()
  )
    invalid("acknowledgement identity");
  const receiptRow = exactObject(
    row.receipt,
    RECEIPT_KEYS,
    "acknowledgement receipt",
  );
  const receipt: RoomExceptionAcknowledgementReceipt = {
    organization_id: id(
      receiptRow.organization_id,
      "acknowledgement receipt organization",
    ),
    actor_user_id: id(receiptRow.actor_user_id, "acknowledgement actor"),
    event_id: id(receiptRow.event_id, "acknowledgement event"),
    command_kind: oneOf(
      receiptRow.command_kind,
      ["room_operational_exception_acknowledge"] as const,
      "acknowledgement command",
    ),
    event_type: oneOf(
      receiptRow.event_type,
      ["acknowledged"] as const,
      "acknowledgement event type",
    ),
    client_operation_id: id(
      receiptRow.client_operation_id,
      "acknowledgement receipt operation",
    ),
    request_sha256: text(
      receiptRow.request_sha256,
      "acknowledgement receipt request digest",
      64,
    ),
    exception_id: id(
      receiptRow.exception_id,
      "acknowledgement receipt exception",
    ),
    facility_id: id(
      receiptRow.facility_id,
      "acknowledgement receipt facility",
    ),
    room_id: nullableId(
      receiptRow.room_id,
      "acknowledgement receipt room",
    ),
    expected_version: integer(
      receiptRow.expected_version,
      "acknowledgement receipt expected version",
      1,
    ),
    resulting_version: integer(
      receiptRow.resulting_version,
      "acknowledgement receipt resulting version",
      2,
    ),
    occurred_at: timestamp(
      receiptRow.occurred_at,
      "acknowledgement receipt time",
    ),
  };
  if (!SHA256.test(receipt.request_sha256))
    invalid("acknowledgement receipt request digest");
  if (
    receipt.organization_id !== expected.organizationId.toLowerCase() ||
    receipt.actor_user_id !== expected.actorUserId.toLowerCase() ||
    receipt.client_operation_id !== expected.operationId.toLowerCase() ||
    receipt.exception_id !== expected.exceptionId.toLowerCase() ||
    receipt.facility_id !== expected.facilityId.toLowerCase() ||
    receipt.room_id !== (expected.roomId?.toLowerCase() ?? null) ||
    receipt.expected_version !== expected.expectedVersion ||
    receipt.resulting_version !== expected.expectedVersion + 1
  )
    invalid("acknowledgement receipt binding");
  const exception = parseRoomOperationalException(
    row.exception,
    expected.facilityId,
  );
  if (
    exception.id !== expected.exceptionId.toLowerCase() ||
    exception.room_id !== (expected.roomId?.toLowerCase() ?? null) ||
    exception.version < receipt.resulting_version ||
    !["acknowledged", "resolved"].includes(exception.state)
  )
    invalid("acknowledgement current exception");
  const requestHash = text(
    row.request_sha256,
    "acknowledgement request digest",
    64,
  );
  if (!SHA256.test(requestHash)) invalid("acknowledgement request digest");
  const canonicalRequestHash =
    await roomExceptionAcknowledgementRequestSha256(expected);
  if (
    requestHash !== receipt.request_sha256 ||
    requestHash !== canonicalRequestHash
  )
    invalid("acknowledgement request digest binding");
  const generatedAt = timestamp(
    row.generated_at,
    "acknowledgement generation time",
  );
  if (
    Date.parse(receipt.occurred_at) > Date.parse(generatedAt) ||
    (exception.acknowledged_at &&
      Date.parse(exception.acknowledged_at) > Date.parse(generatedAt)) ||
    (exception.resolved_at &&
      Date.parse(exception.resolved_at) > Date.parse(generatedAt))
  )
    invalid("acknowledgement chronology");
  return {
    organization_id: organizationId,
    client_operation_id: operationId,
    request_sha256: requestHash,
    replayed: boolean(row.replayed, "acknowledgement replay marker"),
    receipt,
    exception,
    generated_at: generatedAt,
  };
}

export async function fetchLiveRoomSafetyCapability(
  _organizationId: string,
  signal?: AbortSignal,
): Promise<LiveRoomSafetyCapability | null> {
  try {
    const response = await apiRequest<unknown>("/room-safety/capability", {
      signal,
      suppressAuthorizationRecheck: true,
    });
    return parseLiveRoomSafetyCapability(response);
  } catch (caught) {
    if (
      caught instanceof ApiError &&
      [403, 404, 503].includes(caught.status)
    )
      return null;
    throw caught;
  }
}

export async function fetchRoomSafetyReleaseStatus(
  organizationId: string,
  signal?: AbortSignal,
): Promise<RoomSafetyReleaseStatus | null> {
  try {
    const response = await apiRequest<unknown>(
      "/room-safety/release-reconciliation/status",
      {
        signal,
        suppressAuthorizationRecheck: true,
      },
    );
    return parseRoomSafetyReleaseStatus(response, organizationId);
  } catch (caught) {
    if (
      caught instanceof ApiError &&
      [403, 404, 503].includes(caught.status)
    )
      return null;
    throw caught;
  }
}

export async function activateRoomSafetyRelease(input: {
  organizationId: string;
  operationId: string;
  expectedStatus: RoomSafetyReleaseStatus;
  signal?: AbortSignal;
}): Promise<RoomSafetyReleaseResponse> {
  if (
    input.expectedStatus.organization_id !==
      id(input.organizationId, "activation organization") ||
    input.expectedStatus.complete ||
    input.expectedStatus.missing_facility_ids.length !==
      input.expectedStatus.active_facility_count
  )
    throw new RoomSafetyContractError(
      "Refresh the live room activation review before continuing.",
    );
  const reviewedFacilitySetSha256 = await roomSafetyFacilitySetSha256(
    input.expectedStatus.missing_facility_ids,
  );
  if (
    reviewedFacilitySetSha256 !==
    input.expectedStatus.facility_set_sha256
  )
    throw new RoomSafetyContractError(
      "CareSync rejected an invalid live room release facility review.",
    );
  const operationId = id(
    input.operationId,
    "release activation operation",
  );
  const response = await apiRequest<unknown>(
    "/room-safety/release-reconciliation",
    {
      method: "POST",
      body: JSON.stringify({
        client_operation_id: operationId,
        expected_active_facility_count:
          input.expectedStatus.active_facility_count,
        expected_facility_set_sha256:
          input.expectedStatus.facility_set_sha256,
        expected_facility_ids:
          input.expectedStatus.missing_facility_ids,
      }),
      signal: input.signal,
    },
  );
  return parseRoomSafetyReleaseResponse(response, {
    organizationId: input.organizationId,
    operationId,
    facilitySetSha256: input.expectedStatus.facility_set_sha256,
    facilityIds: input.expectedStatus.missing_facility_ids,
  });
}

export async function fetchLiveRoomSafetyBoard(input: {
  organizationId: string;
  facilityId: string;
  facilityTimezone: string;
  rooms: RoomRecord[];
  signal?: AbortSignal;
}): Promise<LiveRoomSafetyBoard> {
  const response = await apiRequest<unknown>(
    `/room-safety/live?facility_id=${encodeURIComponent(input.facilityId)}`,
    { signal: input.signal },
  );
  return parseLiveRoomSafetyBoard(response, {
    organizationId: input.organizationId,
    facilityId: input.facilityId,
    facilityTimezone: input.facilityTimezone,
    rooms: input.rooms,
  });
}

export async function fetchRoomOperationalExceptions(input: {
  organizationId: string;
  facilityId: string;
  stateFilter?: RoomExceptionFilter;
  cursor?: string | null;
  limit?: number;
  signal?: AbortSignal;
}): Promise<RoomExceptionPage> {
  const stateFilter = input.stateFilter ?? "open";
  const limit = input.limit ?? 50;
  if (!Number.isInteger(limit) || limit < 1 || limit > 100)
    throw new RoomSafetyContractError(
      "Choose between 1 and 100 operational exceptions.",
    );
  if (
    input.cursor &&
    (input.cursor.length > 500 || !/^[A-Za-z0-9_-]+$/.test(input.cursor))
  )
    throw new RoomSafetyContractError(
      "The operational exception continuation is invalid.",
    );
  const query = new URLSearchParams({
    facility_id: input.facilityId,
    state: stateFilter,
    limit: String(limit),
  });
  if (input.cursor) query.set("cursor", input.cursor);
  const response = await apiRequest<unknown>(
    `/room-safety/exceptions?${query}`,
    { signal: input.signal },
  );
  return parseRoomExceptionPage(response, {
    organizationId: input.organizationId,
    facilityId: input.facilityId,
    stateFilter,
    limit,
  });
}

export async function fetchRoomExceptionActionTarget(input: {
  organizationId: string;
  exceptionId: string;
  expectedFacilityId?: string;
  expectedRoomId?: string | null;
  signal?: AbortSignal;
}): Promise<RoomExceptionActionTarget> {
  if (!UUID.test(input.exceptionId))
    throw new RoomSafetyContractError(
      "The operational exception target is invalid.",
    );
  const response = await apiRequest<unknown>(
    `/room-safety/exceptions/${encodeURIComponent(input.exceptionId)}/action-target`,
    {
      signal: input.signal,
      suppressAuthorizationRecheck: true,
    },
  );
  const target = parseRoomExceptionActionTarget(response, {
    organizationId: input.organizationId,
    exceptionId: input.exceptionId,
    facilityId: input.expectedFacilityId,
    roomId: input.expectedRoomId,
  });
  if (target.state === "resolved")
    throw new RoomSafetyContractError(
      "This operational signal is no longer available.",
    );
  return target;
}

export async function acknowledgeRoomOperationalException(input: {
  organizationId: string;
  actorUserId: string;
  exception: RoomOperationalException;
  request: RoomExceptionAcknowledgementRequest;
  signal?: AbortSignal;
}): Promise<RoomExceptionAcknowledgementResponse> {
  const reason = normalizeRoomExceptionAcknowledgementReason(
    input.request.reason,
  );
  if (
    !UUID.test(input.request.client_operation_id) ||
    !Number.isSafeInteger(input.request.expected_version) ||
    input.request.expected_version < 1 ||
    input.request.expected_version !== input.exception.version
  )
    throw new RoomSafetyContractError(
      "The acknowledgement no longer matches the reviewed exception.",
    );
  const response = await apiRequest<unknown>(
    `/room-safety/exceptions/${encodeURIComponent(input.exception.id)}/acknowledge`,
    {
      method: "POST",
      body: JSON.stringify({
        client_operation_id: input.request.client_operation_id,
        expected_version: input.request.expected_version,
        reason,
      }),
      signal: input.signal,
    },
  );
  return parseRoomExceptionAcknowledgement(response, {
    organizationId: input.organizationId,
    actorUserId: input.actorUserId,
    exceptionId: input.exception.id,
    facilityId: input.exception.facility_id,
    roomId: input.exception.room_id,
    operationId: input.request.client_operation_id,
    expectedVersion: input.request.expected_version,
    normalizedReason: reason,
  });
}

export function roomExceptionTargetPath(
  target: RoomExceptionActionTarget,
): string {
  if (target.state === "resolved")
    throw new RoomSafetyContractError(
      "This operational signal is no longer available.",
    );
  const query = new URLSearchParams({
    view: "live",
    facility_id: target.facility_id,
    exception: target.exception_id,
  });
  if (target.room_id) query.set("room_id", target.room_id);
  return `/rooms?${query}`;
}

export function roomSafetyApiErrorCode(caught: unknown): string | null {
  if (!(caught instanceof ApiError)) return null;
  const details = caught.details;
  if (!details || typeof details !== "object" || Array.isArray(details))
    return null;
  const detail = (details as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object" || Array.isArray(detail))
    return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}
