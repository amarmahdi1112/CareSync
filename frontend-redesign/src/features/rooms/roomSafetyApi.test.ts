import { describe, expect, it } from "vitest";
import type { RoomRecord } from "./roomsApi";
import {
  LIVE_ROOM_SAFETY_STANDING_BOUNDARY,
  RoomSafetyContractError,
  parseLiveRoomSafetyBoard,
  parseLiveRoomSafetyCapability,
  parseLiveRoomSafetyCapabilityFromStaffSelf,
  parseRoomSafetyReleaseResponse,
  parseRoomSafetyReleaseStatus,
  parseRoomExceptionAcknowledgement,
  parseRoomExceptionActionTarget,
  parseRoomExceptionPage,
  roomExceptionTargetPath,
  roomExceptionAcknowledgementRequestSha256,
  roomSafetyFacilitySetSha256,
} from "./roomSafetyApi";

const ids = {
  organization: "11111111-1111-4111-8111-111111111111",
  actor: "22222222-2222-4222-8222-222222222222",
  facility: "33333333-3333-4333-8333-333333333333",
  facilityTwo: "88888888-8888-4888-8888-888888888888",
  room: "44444444-4444-4444-8444-444444444444",
  exception: "55555555-5555-4555-8555-555555555555",
  operation: "66666666-6666-4666-8666-666666666666",
  event: "77777777-7777-4777-8777-777777777777",
  releaseEvent: "99999999-9999-4999-8999-999999999999",
  releaseEventTwo: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  releaseOrganizationReceipt: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
};
const generatedAt = "2026-07-23T18:00:00Z";
const acknowledgementReason = "Coverage call is in progress";
// Golden value generated independently with the backend's
// canonical_json/request_sha256 implementation.
const hash = "07fbe03c5db624f46ab38180e4ad21c72c69232518ea175a0f3a3089f24510b2";

const room: RoomRecord = {
  id: ids.room,
  organization_id: ids.organization,
  facility_id: ids.facility,
  program_id: null,
  name: "Infant North",
  capacity: 10,
  age_group: "Infant",
  minimum_age_months: 0,
  maximum_age_months: 18,
  is_active: true,
};

function capability() {
  return {
    schema_version: "0041",
    capability: "live_room_presence_safety_board",
    runtime_available: true,
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
    operational_configured_target_only: true,
    regulatory_compliance_certified: false,
  };
}

function releaseStatus(complete = false) {
  return {
    schema_version: "0041",
    organization_id: ids.organization,
    foundation_available: true,
    complete,
    active_facility_count: 2,
    completed_facility_count: complete ? 2 : 0,
    missing_facility_ids: complete
      ? []
      : [ids.facility, ids.facilityTwo],
    facility_set_sha256: "a".repeat(64),
    organization_receipt_id: complete
      ? ids.releaseOrganizationReceipt
      : null,
    generated_at: generatedAt,
  };
}

function releaseResponse() {
  return {
    schema_version: "0041",
    organization_id: ids.organization,
    client_operation_id: ids.operation,
    replayed: false,
    complete: true,
    facility_set_sha256: "a".repeat(64),
    organization_receipt_id: ids.releaseOrganizationReceipt,
    facility_receipts: [
      {
        facility_id: ids.facility,
        audit_event_id: ids.releaseEvent,
        client_operation_id: ids.operation,
        projection_sha256: "b".repeat(64),
        reconciled_at: generatedAt,
      },
      {
        facility_id: ids.facilityTwo,
        audit_event_id: ids.releaseEventTwo,
        client_operation_id: ids.operation,
        projection_sha256: "c".repeat(64),
        reconciled_at: generatedAt,
      },
    ],
    generated_at: generatedAt,
  };
}

function board() {
  return {
    schema_version: "live-room-safety-v1",
    organization_id: ids.organization,
    facility_id: ids.facility,
    facility_timezone: "America/Edmonton",
    view_scope: "facility",
    as_of: generatedAt,
    generated_at: generatedAt,
    data_through_realtime_sequence: 41,
    operational_configured_target_only: true,
    regulatory_compliance_certified: false,
    standing_boundary: LIVE_ROOM_SAFETY_STANDING_BOUNDARY,
    facility: {
      confirmed_children: 2,
      present_children_without_active_room: 0,
      open_shift_staff: 1,
      located_staff: 1,
      unlocated_staff: 0,
      configured_target: {
        state: "target_met",
        required_staff: 1,
        window_start_local: "08:00",
        window_end_local: "18:00",
      },
      overall_state: "no_active_configured_target_signal",
      active_exception_count: 0,
      data_quality_reason_codes: [],
    },
    rooms: [
      {
        room_id: ids.room,
        room_name: room.name,
        confirmed_children: 2,
        configured_room_capacity: 10,
        capacity_state: "within_configured_capacity",
        confirmed_staff: 1,
        configured_target: {
          state: "target_met",
          required_staff: 1,
          window_start_local: "08:00",
          window_end_local: "18:00",
        },
        overall_state: "no_active_configured_target_signal",
        active_exception_ids: [],
        data_quality_reason_codes: [],
      },
    ],
  };
}

function exception(state: "open" | "acknowledged" | "resolved" = "open") {
  return {
    id: ids.exception,
    facility_id: ids.facility,
    scope_kind: "room",
    scope_id: ids.room,
    room_id: ids.room,
    condition_code: "confirmed_staff_below_configured_room_target",
    state,
    version: state === "open" ? 1 : 2,
    opened_at: generatedAt,
    materially_changed_at: null,
    acknowledged_at:
      state === "acknowledged" ? "2026-07-23T18:01:00Z" : null,
    acknowledged_by_user_id:
      state === "acknowledged" ? ids.actor : null,
    acknowledgement_reason:
      state === "acknowledged"
        ? "Coverage call is in progress"
        : null,
    resolved_at: state === "resolved" ? "2026-07-23T18:02:00Z" : null,
    observed_value: 1,
    configured_value: 2,
    source_integrity_reason_codes: [],
    action_target_path: `/api/v1/room-safety/exceptions/${ids.exception}/action-target`,
  };
}

describe("0041 live room safety contracts", () => {
  it("accepts only the exact advertised capability and treats an absent staff marker as unavailable", () => {
    expect(parseLiveRoomSafetyCapability(capability())).toEqual(capability());
    expect(
      parseLiveRoomSafetyCapabilityFromStaffSelf(
        { organization_id: ids.organization },
        ids.organization,
      ),
    ).toBeNull();
    expect(() =>
      parseLiveRoomSafetyCapability({
        ...capability(),
        manager_live_board_path: "/rooms",
      }),
    ).toThrow(RoomSafetyContractError);
    expect(() =>
      parseLiveRoomSafetyCapability({
        ...capability(),
        runtime_available: false,
      }),
    ).toThrow(RoomSafetyContractError);
  });

  it("binds the one-time release review to the organization, facility set, and protected operation", () => {
    expect(
      parseRoomSafetyReleaseStatus(
        releaseStatus(false),
        ids.organization,
      ),
    ).toMatchObject({
      complete: false,
      completed_facility_count: 0,
      missing_facility_ids: [ids.facility, ids.facilityTwo],
    });
    expect(
      parseRoomSafetyReleaseStatus(
        releaseStatus(true),
        ids.organization,
      ),
    ).toMatchObject({
      complete: true,
      completed_facility_count: 2,
      organization_receipt_id: ids.releaseOrganizationReceipt,
    });
    expect(
      parseRoomSafetyReleaseResponse(releaseResponse(), {
        organizationId: ids.organization,
        operationId: ids.operation,
        facilitySetSha256: "a".repeat(64),
        facilityIds: [ids.facility, ids.facilityTwo],
      }),
    ).toMatchObject({
      complete: true,
      facility_receipts: [
        { facility_id: ids.facility },
        { facility_id: ids.facilityTwo },
      ],
    });

    for (const invalidStatus of [
      {
        ...releaseStatus(false),
        completed_facility_count: 1,
      },
      {
        ...releaseStatus(false),
        missing_facility_ids: [ids.facility],
      },
      {
        ...releaseStatus(true),
        organization_receipt_id: null,
      },
      {
        ...releaseStatus(false),
        foundation_available: false,
      },
    ]) {
      expect(() =>
        parseRoomSafetyReleaseStatus(invalidStatus, ids.organization),
      ).toThrow(RoomSafetyContractError);
    }
    expect(() =>
      parseRoomSafetyReleaseResponse(
        {
          ...releaseResponse(),
          client_operation_id: ids.event,
        },
        {
          organizationId: ids.organization,
          operationId: ids.operation,
          facilitySetSha256: "a".repeat(64),
          facilityIds: [ids.facility, ids.facilityTwo],
        },
      ),
    ).toThrow(RoomSafetyContractError);
    expect(() =>
      parseRoomSafetyReleaseResponse(
        {
          ...releaseResponse(),
          facility_receipts: [
            releaseResponse().facility_receipts[0],
            releaseResponse().facility_receipts[0],
          ],
        },
        {
          organizationId: ids.organization,
          operationId: ids.operation,
          facilitySetSha256: "a".repeat(64),
          facilityIds: [ids.facility, ids.facilityTwo],
        },
      ),
    ).toThrow(RoomSafetyContractError);
    expect(() =>
      parseRoomSafetyReleaseResponse(
        {
          ...releaseResponse(),
          organization_receipt_id: ids.releaseEvent,
        },
        {
          organizationId: ids.organization,
          operationId: ids.operation,
          facilitySetSha256: "a".repeat(64),
          facilityIds: [ids.facility, ids.facilityTwo],
        },
      ),
    ).toThrow(RoomSafetyContractError);
  });

  it("recomputes the release facility-set digest with the backend canonical format", async () => {
    await expect(
      roomSafetyFacilitySetSha256([ids.facilityTwo, ids.facility]),
    ).resolves.toBe(
      "e3afe0467382d20bff448903e62888422b86b60ca27c966c4ee84d3aecefdd82",
    );
    await expect(
      roomSafetyFacilitySetSha256([ids.facility, ids.facility]),
    ).rejects.toThrow(RoomSafetyContractError);
  });

  it("reconciles room, facility, capacity, target, timezone, and operational-only boundaries", () => {
    expect(
      parseLiveRoomSafetyBoard(board(), {
        organizationId: ids.organization,
        facilityId: ids.facility,
        facilityTimezone: "America/Edmonton",
        rooms: [room],
      }).facility.located_staff,
    ).toBe(1);
    expect(
      parseLiveRoomSafetyBoard(
        { ...board(), facility_timezone: "UTC" },
        {
          organizationId: ids.organization,
          facilityId: ids.facility,
          facilityTimezone: "UTC",
          rooms: [room],
        },
      ).facility_timezone,
    ).toBe("UTC");

    for (const invalidBoard of [
      {
        ...board(),
        rooms: [{ ...board().rooms[0], capacity_state: "unknown" }],
      },
      {
        ...board(),
        rooms: [
          {
            ...board().rooms[0],
            configured_target: {
              state: "unknown",
              required_staff: null,
              window_start_local: null,
              window_end_local: null,
            },
          },
        ],
      },
      {
        ...board(),
        facility: { ...board().facility, active_exception_count: 1 },
      },
      {
        ...board(),
        facility: {
          ...board().facility,
          open_shift_staff: 2,
          unlocated_staff: 1,
        },
      },
      {
        ...board(),
        rooms: [
          {
            ...board().rooms[0],
            configured_target: {
              state: "target_met",
              required_staff: 1,
              window_start_local: "08:07",
              window_end_local: "18:00",
            },
          },
        ],
      },
      {
        ...board(),
        facility: { ...board().facility, confirmed_children: 3 },
      },
      { ...board(), standing_boundary: "Everything is compliant." },
    ]) {
      expect(() =>
        parseLiveRoomSafetyBoard(invalidBoard, {
          organizationId: ids.organization,
          facilityId: ids.facility,
          facilityTimezone: "America/Edmonton",
          rooms: [room],
        }),
      ).toThrow(RoomSafetyContractError);
    }
  });

  it("accepts the exact zero-to-500 configured-target range", () => {
    for (const requiredStaff of [0, 500]) {
      const candidate = board();
      candidate.facility = {
        ...candidate.facility,
        open_shift_staff: requiredStaff,
        located_staff: requiredStaff,
        configured_target: {
          ...candidate.facility.configured_target,
          required_staff: requiredStaff,
        },
      };
      candidate.rooms = candidate.rooms.map((item) => ({
        ...item,
        confirmed_staff: requiredStaff,
        configured_target: {
          ...item.configured_target,
          required_staff: requiredStaff,
        },
      }));

      const parsed = parseLiveRoomSafetyBoard(candidate, {
        organizationId: ids.organization,
        facilityId: ids.facility,
        facilityTimezone: "America/Edmonton",
        rooms: [room],
      });
      expect(parsed.facility.configured_target.required_staff).toBe(
        requiredStaff,
      );
      expect(parsed.rooms[0]?.configured_target.required_staff).toBe(
        requiredStaff,
      );
    }

    for (const requiredStaff of [-1, 501]) {
      const candidate = board();
      candidate.facility.configured_target.required_staff = requiredStaff;
      expect(() =>
        parseLiveRoomSafetyBoard(candidate, {
          organizationId: ids.organization,
          facilityId: ids.facility,
          facilityTimezone: "America/Edmonton",
          rooms: [room],
        }),
      ).toThrow(RoomSafetyContractError);
    }
  });

  it("requires exact facility and room child-count completeness", () => {
    const base = board();
    const facilityUnknown = {
      ...base.facility,
      overall_state: "unknown",
      data_quality_reason_codes: ["attendance_source_incoherent"],
    };
    const roomChildrenUnknown = base.rooms.map((item) => ({
      ...item,
      confirmed_children: null,
      capacity_state: "unknown",
      overall_state: "unknown",
      data_quality_reason_codes: ["attendance_source_incoherent"],
    }));
    const completeUnknownBoard = {
      ...base,
      facility: {
        ...facilityUnknown,
        confirmed_children: null,
        present_children_without_active_room: null,
      },
      rooms: roomChildrenUnknown,
    };
    expect(
      parseLiveRoomSafetyBoard(completeUnknownBoard, {
        organizationId: ids.organization,
        facilityId: ids.facility,
        facilityTimezone: "America/Edmonton",
        rooms: [room],
      }).facility.confirmed_children,
    ).toBeNull();

    for (const invalidBoard of [
      {
        ...base,
        facility: {
          ...facilityUnknown,
          confirmed_children: null,
        },
      },
      {
        ...base,
        facility: {
          ...facilityUnknown,
          confirmed_children: null,
          present_children_without_active_room: null,
        },
      },
      {
        ...base,
        facility: {
          ...facilityUnknown,
          present_children_without_active_room: null,
        },
      },
      {
        ...base,
        rooms: roomChildrenUnknown,
      },
      {
        ...completeUnknownBoard,
        rooms: completeUnknownBoard.rooms.map((item) => ({
          ...item,
          overall_state: "attention",
        })),
      },
    ]) {
      expect(() =>
        parseLiveRoomSafetyBoard(invalidBoard, {
          organizationId: ids.organization,
          facilityId: ids.facility,
          facilityTimezone: "America/Edmonton",
          rooms: [room],
        }),
      ).toThrow(RoomSafetyContractError);
    }
  });

  it("requires exact facility and room staff-count completeness", () => {
    const base = board();
    const retainedUnknownTarget = {
      state: "unknown",
      required_staff: 1,
      window_start_local: "08:00",
      window_end_local: "18:00",
    };
    const completeUnknownBoard = {
      ...base,
      facility: {
        ...base.facility,
        open_shift_staff: null,
        located_staff: null,
        unlocated_staff: null,
        configured_target: retainedUnknownTarget,
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      },
      rooms: base.rooms.map((item) => ({
        ...item,
        confirmed_staff: null,
        configured_target: retainedUnknownTarget,
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      })),
    };
    expect(
      parseLiveRoomSafetyBoard(completeUnknownBoard, {
        organizationId: ids.organization,
        facilityId: ids.facility,
        facilityTimezone: "America/Edmonton",
        rooms: [room],
      }).facility.located_staff,
    ).toBeNull();

    for (const invalidBoard of [
      {
        ...completeUnknownBoard,
        rooms: completeUnknownBoard.rooms.map((item) => ({
          ...item,
          confirmed_staff: 1,
          configured_target: {
            ...item.configured_target,
            state: "target_met",
          },
        })),
      },
      {
        ...base,
        rooms: base.rooms.map((item) => ({
          ...item,
          confirmed_staff: null,
          configured_target: retainedUnknownTarget,
          overall_state: "unknown",
          data_quality_reason_codes: [
            "room_presence_source_incoherent",
          ],
        })),
      },
    ]) {
      expect(() =>
        parseLiveRoomSafetyBoard(invalidBoard, {
          organizationId: ids.organization,
          facilityId: ids.facility,
          facilityTimezone: "America/Edmonton",
          rooms: [room],
        }),
      ).toThrow(RoomSafetyContractError);
    }
  });

  it("accepts only complete retained targets for incoherent unknown staff arithmetic", () => {
    const base = board();
    const retainedUnknownTarget = {
      state: "unknown",
      required_staff: 0,
      window_start_local: "08:00",
      window_end_local: "18:00",
    };
    const incoherentBoard = {
      ...base,
      facility: {
        ...base.facility,
        open_shift_staff: null,
        located_staff: null,
        unlocated_staff: null,
        configured_target: retainedUnknownTarget,
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      },
      rooms: base.rooms.map((item) => ({
        ...item,
        confirmed_staff: null,
        configured_target: retainedUnknownTarget,
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      })),
    };

    const parsed = parseLiveRoomSafetyBoard(incoherentBoard, {
      organizationId: ids.organization,
      facilityId: ids.facility,
      facilityTimezone: "America/Edmonton",
      rooms: [room],
    });
    expect(parsed.facility.configured_target).toEqual(
      retainedUnknownTarget,
    );
    expect(parsed.rooms[0]?.configured_target).toEqual(
      retainedUnknownTarget,
    );
    expect(() =>
      parseLiveRoomSafetyBoard(
        {
          ...incoherentBoard,
          facility: {
            ...incoherentBoard.facility,
            overall_state: "attention",
          },
        },
        {
          organizationId: ids.organization,
          facilityId: ids.facility,
          facilityTimezone: "America/Edmonton",
          rooms: [room],
        },
      ),
    ).toThrow(RoomSafetyContractError);

    const emptyUnknownTarget = {
      state: "unknown",
      required_staff: null,
      window_start_local: null,
      window_end_local: null,
    };
    const emptyParsed = parseLiveRoomSafetyBoard(
      {
        ...incoherentBoard,
        facility: {
          ...incoherentBoard.facility,
          configured_target: emptyUnknownTarget,
        },
        rooms: incoherentBoard.rooms.map((item) => ({
          ...item,
          configured_target: emptyUnknownTarget,
        })),
      },
      {
        organizationId: ids.organization,
        facilityId: ids.facility,
        facilityTimezone: "America/Edmonton",
        rooms: [room],
      },
    );
    expect(emptyParsed.facility.configured_target).toEqual(
      emptyUnknownTarget,
    );
    expect(emptyParsed.rooms[0]?.configured_target).toEqual(
      emptyUnknownTarget,
    );

    const invalidRoomVariants = [
      {
        confirmed_staff: null,
        configured_target: {
          ...retainedUnknownTarget,
          required_staff: null,
        },
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      },
      {
        confirmed_staff: null,
        configured_target: {
          ...retainedUnknownTarget,
          window_end_local: null,
        },
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      },
      {
        confirmed_staff: 1,
        configured_target: retainedUnknownTarget,
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      },
      {
        confirmed_staff: null,
        configured_target: retainedUnknownTarget,
        overall_state: "unknown",
        data_quality_reason_codes: [],
      },
      {
        confirmed_staff: null,
        configured_target: {
          ...retainedUnknownTarget,
          window_start_local: "18:00",
          window_end_local: "08:00",
        },
        overall_state: "unknown",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      },
      {
        confirmed_staff: null,
        configured_target: retainedUnknownTarget,
        overall_state: "no_active_configured_target_signal",
        data_quality_reason_codes: [
          "room_presence_source_incoherent",
        ],
      },
    ];
    for (const invalidRoom of invalidRoomVariants) {
      expect(() =>
        parseLiveRoomSafetyBoard(
          {
            ...incoherentBoard,
            rooms: [
              {
                ...incoherentBoard.rooms[0],
                ...invalidRoom,
              },
            ],
          },
          {
            organizationId: ids.organization,
            facilityId: ids.facility,
            facilityTimezone: "America/Edmonton",
            rooms: [room],
          },
        ),
      ).toThrow(RoomSafetyContractError);
    }
  });

  it("binds bounded exception pages and action targets to the loaded organization, facility, room, and episode", () => {
    const page = parseRoomExceptionPage(
      {
        schema_version: "room-operational-exceptions-v1",
        organization_id: ids.organization,
        facility_id: ids.facility,
        state_filter: "all",
        items: [exception()],
        next_cursor: "YWZ0ZXJfcm93",
        generated_at: generatedAt,
      },
      {
        organizationId: ids.organization,
        facilityId: ids.facility,
        stateFilter: "all",
        limit: 50,
      },
    );
    expect(page.items[0]?.id).toBe(ids.exception);
    expect(() =>
      parseRoomExceptionPage(
        {
          ...page,
          next_cursor: "bad+cursor=",
        },
        {
          organizationId: ids.organization,
          facilityId: ids.facility,
          stateFilter: "all",
          limit: 50,
        },
      ),
    ).toThrow(RoomSafetyContractError);
    expect(() =>
      parseRoomExceptionPage(
        {
          schema_version: "room-operational-exceptions-v1",
          organization_id: ids.organization,
          facility_id: ids.facility,
          state_filter: "all",
          items: [
            {
              ...exception(),
              observed_value: 3,
              configured_value: 2,
            },
          ],
          next_cursor: null,
          generated_at: generatedAt,
        },
        {
          organizationId: ids.organization,
          facilityId: ids.facility,
          stateFilter: "all",
          limit: 50,
        },
      ),
    ).toThrow(RoomSafetyContractError);

    const target = {
      schema_version: "room-operational-exception-action-target-v1",
      organization_id: ids.organization,
      facility_id: ids.facility,
      room_id: ids.room,
      exception_id: ids.exception,
      state: "open",
      version: 1,
      visible: true,
      action_path: "/rooms",
      generated_at: generatedAt,
    };
    expect(
      parseRoomExceptionActionTarget(target, {
        organizationId: ids.organization,
        exceptionId: ids.exception,
        facilityId: ids.facility,
        roomId: ids.room,
      }).facility_id,
    ).toBe(ids.facility);
    expect(() =>
      parseRoomExceptionActionTarget(target, {
        organizationId: ids.organization,
        exceptionId: ids.exception,
        facilityId: "88888888-8888-4888-8888-888888888888",
      }),
    ).toThrow(RoomSafetyContractError);
    const resolvedTarget = parseRoomExceptionActionTarget(
      { ...target, state: "resolved", version: 2 },
      {
        organizationId: ids.organization,
        exceptionId: ids.exception,
        facilityId: ids.facility,
        roomId: ids.room,
      },
    );
    expect(() => roomExceptionTargetPath(resolvedTarget)).toThrow(
      "This operational signal is no longer available.",
    );
  });

  it("accepts facility target episodes while preserving scope and below-target arithmetic", () => {
    const facilityTargetException = {
      ...exception(),
      scope_kind: "facility",
      scope_id: ids.facility,
      room_id: null,
    };
    const parsed = parseRoomExceptionPage(
      {
        schema_version: "room-operational-exceptions-v1",
        organization_id: ids.organization,
        facility_id: ids.facility,
        state_filter: "all",
        items: [facilityTargetException],
        next_cursor: null,
        generated_at: generatedAt,
      },
      {
        organizationId: ids.organization,
        facilityId: ids.facility,
        stateFilter: "all",
        limit: 50,
      },
    );
    expect(parsed.items[0]).toMatchObject({
      scope_kind: "facility",
      scope_id: ids.facility,
      room_id: null,
      condition_code:
        "confirmed_staff_below_configured_room_target",
      observed_value: 1,
      configured_value: 2,
    });

    for (const invalidException of [
      {
        ...facilityTargetException,
        condition_code:
          "confirmed_children_above_configured_room_capacity",
      },
      {
        ...facilityTargetException,
        observed_value: 2,
        configured_value: 2,
      },
      {
        ...facilityTargetException,
        observed_value: 0,
        configured_value: 0,
      },
    ]) {
      expect(() =>
        parseRoomExceptionPage(
          {
            schema_version: "room-operational-exceptions-v1",
            organization_id: ids.organization,
            facility_id: ids.facility,
            state_filter: "all",
            items: [invalidException],
            next_cursor: null,
            generated_at: generatedAt,
          },
          {
            organizationId: ids.organization,
            facilityId: ids.facility,
            stateFilter: "all",
            limit: 50,
          },
        ),
      ).toThrow(RoomSafetyContractError);
    }
  });

  it("matches the backend-independent canonical acknowledgement digest vector", async () => {
    await expect(
      roomExceptionAcknowledgementRequestSha256({
        organizationId: ids.organization,
        actorUserId: ids.actor,
        exceptionId: ids.exception,
        facilityId: ids.facility,
        roomId: ids.room,
        operationId: ids.operation,
        expectedVersion: 1,
        normalizedReason: acknowledgementReason,
      }),
    ).resolves.toBe(hash);
  });

  it("verifies the immutable acknowledgement receipt and current exception projection separately", async () => {
    const response = {
      organization_id: ids.organization,
      client_operation_id: ids.operation,
      request_sha256: hash,
      replayed: false,
      receipt: {
        organization_id: ids.organization,
        actor_user_id: ids.actor,
        event_id: ids.event,
        command_kind: "room_operational_exception_acknowledge",
        event_type: "acknowledged",
        client_operation_id: ids.operation,
        request_sha256: hash,
        exception_id: ids.exception,
        facility_id: ids.facility,
        room_id: ids.room,
        expected_version: 1,
        resulting_version: 2,
        occurred_at: "2026-07-23T18:01:00Z",
      },
      exception: exception("acknowledged"),
      generated_at: "2026-07-23T18:01:00Z",
    };
    await expect(
      parseRoomExceptionAcknowledgement(response, {
        organizationId: ids.organization,
        actorUserId: ids.actor,
        exceptionId: ids.exception,
        facilityId: ids.facility,
        roomId: ids.room,
        operationId: ids.operation,
        expectedVersion: 1,
        normalizedReason: acknowledgementReason,
      }),
    ).resolves.toMatchObject({ receipt: { resulting_version: 2 } });
    await expect(
      parseRoomExceptionAcknowledgement(
        {
          ...response,
          receipt: { ...response.receipt, room_id: null },
        },
        {
          organizationId: ids.organization,
          actorUserId: ids.actor,
          exceptionId: ids.exception,
          facilityId: ids.facility,
          roomId: ids.room,
          operationId: ids.operation,
          expectedVersion: 1,
          normalizedReason: acknowledgementReason,
        },
      ),
    ).rejects.toThrow(RoomSafetyContractError);
    await expect(
      parseRoomExceptionAcknowledgement(
        response,
        {
          organizationId: ids.organization,
          actorUserId: ids.actor,
          exceptionId: ids.exception,
          facilityId: ids.facility,
          roomId: ids.room,
          operationId: ids.operation,
          expectedVersion: 1,
          normalizedReason: "A different reviewed reason",
        },
      ),
    ).rejects.toThrow(RoomSafetyContractError);
    await expect(
      parseRoomExceptionAcknowledgement(
        {
          ...response,
          request_sha256: "a".repeat(64),
          receipt: {
            ...response.receipt,
            request_sha256: "a".repeat(64),
          },
        },
        {
          organizationId: ids.organization,
          actorUserId: ids.actor,
          exceptionId: ids.exception,
          facilityId: ids.facility,
          roomId: ids.room,
          operationId: ids.operation,
          expectedVersion: 1,
          normalizedReason: acknowledgementReason,
        },
      ),
    ).rejects.toThrow(RoomSafetyContractError);
  });
});
