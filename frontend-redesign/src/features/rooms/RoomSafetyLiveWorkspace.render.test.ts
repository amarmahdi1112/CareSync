import { createElement } from "react";
import {
  act,
  create,
  type ReactTestInstance,
  type ReactTestRenderer,
} from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "styled-components";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { workspaceTheme } from "../../styles/theme";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;

const ids = {
  organization: "11111111-1111-4111-8111-111111111111",
  actor: "22222222-2222-4222-8222-222222222222",
  facility: "33333333-3333-4333-8333-333333333333",
  room: "44444444-4444-4444-8444-444444444444",
  exception: "55555555-5555-4555-8555-555555555555",
};
const generatedAt = "2026-07-23T18:00:00Z";

const harness = vi.hoisted(() => ({
  fetchBoard: vi.fn(),
  fetchExceptions: vi.fn(),
}));

vi.mock("../../realtime/RealtimeContext", () => ({
  useRealtimeState: () => "connected",
  useRealtimeRefresh: () => undefined,
}));

vi.mock("./roomSafetyApi", async (importOriginal) => {
  const original = await importOriginal<typeof import("./roomSafetyApi")>();
  return {
    ...original,
    fetchLiveRoomSafetyBoard: harness.fetchBoard,
    fetchRoomOperationalExceptions: harness.fetchExceptions,
  };
});

vi.mock("./roomSafetyOperation", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("./roomSafetyOperation")>();
  return {
    ...original,
    listPendingRoomExceptionAcknowledgements: () => [],
  };
});

import RoomSafetyLiveWorkspace from "./RoomSafetyLiveWorkspace";
import type { RoomOperationalException } from "./roomSafetyApi";

function nodeText(node: ReactTestInstance): string {
  return node.children
    .map((child) => (typeof child === "string" ? child : nodeText(child)))
    .join("");
}

function board() {
  return {
    schema_version: "live-room-safety-v1" as const,
    organization_id: ids.organization,
    facility_id: ids.facility,
    facility_timezone: "America/Edmonton",
    as_of: generatedAt,
    view_scope: "facility" as const,
    generated_at: generatedAt,
    data_through_realtime_sequence: 41,
    operational_configured_target_only: true as const,
    regulatory_compliance_certified: false as const,
    standing_boundary:
      "Operational configured-target evidence only. CareSync does not calculate or certify regulatory ratios, qualifications, group-size rules, licensing compliance or adequate supervision." as const,
    facility: {
      confirmed_children: 0,
      present_children_without_active_room: 0,
      open_shift_staff: 1,
      located_staff: 0,
      unlocated_staff: 1,
      configured_target: {
        state: "confirmed_staff_below_target" as const,
        required_staff: 2,
        window_start_local: "08:00",
        window_end_local: "18:00",
      },
      overall_state: "attention" as const,
      active_exception_count: 1,
      data_quality_reason_codes: [],
    },
    rooms: [],
  };
}

function targetException(
  scope: "facility" | "room",
): RoomOperationalException {
  return {
    id: ids.exception,
    facility_id: ids.facility,
    scope_kind: scope,
    scope_id: scope === "facility" ? ids.facility : ids.room,
    room_id: scope === "facility" ? null : ids.room,
    condition_code:
      "confirmed_staff_below_configured_room_target",
    state: "open",
    version: 1,
    opened_at: generatedAt,
    materially_changed_at: null,
    acknowledged_at: null,
    acknowledged_by_user_id: null,
    acknowledgement_reason: null,
    resolved_at: null,
    observed_value: 1,
    configured_value: 2,
    source_integrity_reason_codes: [],
    action_target_path: `/api/v1/room-safety/exceptions/${ids.exception}/action-target`,
  };
}

const capability = {
  schema_version: "0041" as const,
  capability: "live_room_presence_safety_board" as const,
  runtime_available: true as const,
  self_presence_read_path: "/api/v1/staff/self/room-presence" as const,
  self_live_board_path: "/api/v1/staff/self/room-safety/live" as const,
  start_path: "/api/v1/staff/self/room-presence/start" as const,
  move_path: "/api/v1/staff/self/room-presence/move" as const,
  end_path: "/api/v1/staff/self/room-presence/end" as const,
  manager_live_board_path: "/api/v1/room-safety/live" as const,
  manager_exceptions_path: "/api/v1/room-safety/exceptions" as const,
  manager_action_target_path_template:
    "/api/v1/room-safety/exceptions/{exception_id}/action-target" as const,
  manager_acknowledge_path_template:
    "/api/v1/room-safety/exceptions/{exception_id}/acknowledge" as const,
  online_only: true as const,
  operational_configured_target_only: true as const,
  regulatory_compliance_certified: false as const,
};

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function renderException(
  exception: RoomOperationalException,
): Promise<ReactTestRenderer> {
  harness.fetchBoard.mockResolvedValue(board());
  harness.fetchExceptions.mockResolvedValue({
    schema_version: "room-operational-exceptions-v1",
    organization_id: ids.organization,
    facility_id: ids.facility,
    state_filter: "all",
    items: [exception],
    next_cursor: null,
    generated_at: generatedAt,
  });
  let renderer!: ReactTestRenderer;
  await act(async () => {
    renderer = create(
      createElement(
        MemoryRouter,
        null,
        createElement(
          ThemeProvider,
          { theme: workspaceTheme },
          createElement(RoomSafetyLiveWorkspace, {
            organizationId: ids.organization,
            actorUserId: ids.actor,
            facilityId: ids.facility,
            facilityTimezone: "America/Edmonton",
            rooms: [],
            capability,
            onOpenRoster: vi.fn(),
            onActionTarget: vi.fn(),
          }),
        ),
      ),
    );
  });
  await settle();
  const episode = renderer.root.find(
    (node) =>
      node.type === "button" &&
      nodeText(node).includes("configured operational target"),
  );
  await act(async () => {
    episode.props.onClick();
  });
  return renderer;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  vi.setSystemTime(new Date(generatedAt));
  vi.stubGlobal("window", {
    setInterval: globalThis.setInterval,
    clearInterval: globalThis.clearInterval,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("RoomSafetyLiveWorkspace target exception copy", () => {
  it("explains a facility target against open actual-shift staff, not room allocation", async () => {
    const renderer = await renderException(targetException("facility"));
    const text = nodeText(renderer.root);

    expect(text).toContain(
      "Confirmed facility staff below configured operational target",
    );
    expect(text).toContain(
      "This compares open actual-shift staff with the facility-wide configured operational target, not room allocation.",
    );
    expect(text).not.toContain(
      "Confirmed room staff below configured operational target",
    );
    await act(async () => {
      renderer.unmount();
    });
  });

  it("retains room-presence copy for a room target", async () => {
    const renderer = await renderException(targetException("room"));
    const text = nodeText(renderer.root);

    expect(text).toContain(
      "Confirmed room staff below configured operational target",
    );
    expect(text).toContain(
      "Review current room presence here and configured targets in Staff rota.",
    );
    expect(text).not.toContain(
      "Confirmed facility staff below configured operational target",
    );
    await act(async () => {
      renderer.unmount();
    });
  });
});
