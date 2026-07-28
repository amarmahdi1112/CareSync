import { createElement } from "react";
import {
  act,
  create,
  type ReactTestInstance,
  type ReactTestRenderer,
} from "react-test-renderer";
import { ThemeProvider } from "styled-components";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { workspaceTheme } from "../../styles/theme";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;

const organizationOne = "11111111-1111-4111-8111-111111111111";
const organizationTwo = "22222222-2222-4222-8222-222222222222";
const actorOne = "33333333-3333-4333-8333-333333333333";
const actorTwo = "44444444-4444-4444-8444-444444444444";
const facilityOne = "55555555-5555-4555-8555-555555555555";
const facilityTwo = "66666666-6666-4666-8666-666666666666";
const operationId = "77777777-7777-4777-8777-777777777777";
const receiptId = "88888888-8888-4888-8888-888888888888";
const auditEventId = "99999999-9999-4999-8999-999999999999";
const generatedAt = "2026-07-23T18:00:00Z";
const checkpointSchema = "caresync-room-safety-activation-v1";

const harness = vi.hoisted(() => ({
  activate: vi.fn(),
  fetchCapability: vi.fn(),
  fetchStatus: vi.fn(),
}));

vi.mock("./roomSafetyApi", async (importOriginal) => {
  const original = await importOriginal<typeof import("./roomSafetyApi")>();
  return {
    ...original,
    activateRoomSafetyRelease: harness.activate,
    fetchLiveRoomSafetyCapability: harness.fetchCapability,
    fetchRoomSafetyReleaseStatus: harness.fetchStatus,
  };
});

import RoomSafetyActivationCard from "./RoomSafetyActivationCard";

function capability() {
  return {
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
}

function releaseStatus(
  organizationId = organizationOne,
  complete = false,
  facilityId = facilityOne,
) {
  return {
    schema_version: "0041" as const,
    organization_id: organizationId,
    foundation_available: true as const,
    complete,
    active_facility_count: 1,
    completed_facility_count: complete ? 1 : 0,
    missing_facility_ids: complete ? [] : [facilityId],
    facility_set_sha256: (facilityId === facilityOne ? "a" : "b").repeat(64),
    organization_receipt_id: complete ? receiptId : null,
    generated_at: generatedAt,
  };
}

function releaseResponse() {
  return {
    schema_version: "0041" as const,
    organization_id: organizationOne,
    client_operation_id: operationId,
    replayed: true,
    complete: true as const,
    facility_set_sha256: "a".repeat(64),
    organization_receipt_id: receiptId,
    facility_receipts: [
      {
        facility_id: facilityOne,
        audit_event_id: auditEventId,
        client_operation_id: operationId,
        projection_sha256: "c".repeat(64),
        reconciled_at: generatedAt,
      },
    ],
    generated_at: generatedAt,
  };
}

function checkpointKey(
  organizationId = organizationOne,
  actorUserId = actorOne,
): string {
  return `${checkpointSchema}:${organizationId}:${actorUserId}`;
}

function checkpoint(
  organizationId = organizationOne,
  actorUserId = actorOne,
): string {
  return JSON.stringify({
    schema: checkpointSchema,
    organizationId,
    actorUserId,
    operationId,
  });
}

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

function nodeText(node: ReactTestInstance): string {
  return node.children
    .map((child) => (typeof child === "string" ? child : nodeText(child)))
    .join("");
}

function activationButton(renderer: ReactTestRenderer): ReactTestInstance {
  return renderer.root.find(
    (node) =>
      node.type === "button" &&
      nodeText(node).includes("Activate live room operations"),
  );
}

function confirmationInput(renderer: ReactTestRenderer): ReactTestInstance {
  return renderer.root.find(
    (node) => node.type === "input" && node.props.type === "checkbox",
  );
}

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function renderCard(input: {
  organizationId?: string;
  actorUserId?: string;
  onActivated?: ReturnType<typeof vi.fn>;
} = {}): Promise<{
  renderer: ReactTestRenderer;
  onActivated: ReturnType<typeof vi.fn>;
}> {
  const onActivated = input.onActivated ?? vi.fn();
  let renderer!: ReactTestRenderer;
  await act(async () => {
    renderer = create(
      createElement(
        ThemeProvider,
        { theme: workspaceTheme },
        createElement(RoomSafetyActivationCard, {
          organizationId: input.organizationId ?? organizationOne,
          actorUserId: input.actorUserId ?? actorOne,
          canActivate: true,
          onActivated,
        }),
      ),
    );
  });
  await settle();
  return { renderer, onActivated };
}

async function confirmAndActivate(renderer: ReactTestRenderer): Promise<void> {
  await act(async () => {
    confirmationInput(renderer).props.onChange({
      target: { checked: true },
    });
  });
  await act(async () => {
    await activationButton(renderer).props.onClick();
  });
  await settle();
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("localStorage", new MemoryStorage());
  harness.fetchStatus.mockResolvedValue(releaseStatus());
  harness.fetchCapability.mockResolvedValue(capability());
  harness.activate.mockResolvedValue(releaseResponse());
});

describe("RoomSafetyActivationCard protected recovery", () => {
  it("recovers a response-loss checkpoint with the same operation and converges on canonical completion", async () => {
    localStorage.setItem(checkpointKey(), checkpoint());
    harness.fetchStatus
      .mockResolvedValueOnce(releaseStatus())
      .mockResolvedValueOnce(releaseStatus(organizationOne, true));
    harness.activate.mockRejectedValueOnce(new Error("Connection lost"));

    const { renderer, onActivated } = await renderCard();
    await confirmAndActivate(renderer);

    expect(harness.activate).toHaveBeenCalledWith(
      expect.objectContaining({
        organizationId: organizationOne,
        operationId,
        expectedStatus: releaseStatus(),
        signal: expect.any(AbortSignal),
      }),
    );
    expect(harness.fetchStatus).toHaveBeenNthCalledWith(
      2,
      organizationOne,
      expect.any(AbortSignal),
    );
    expect(onActivated).toHaveBeenCalledWith(capability(), 1);
    expect(localStorage.getItem(checkpointKey())).toBeNull();
    expect(renderer.toJSON()).toBeNull();
  });

  it("survives denied browser storage and performs no activation write", async () => {
    const deniedStorage = {
      get length(): number {
        throw new DOMException("Denied", "SecurityError");
      },
      clear: () => {
        throw new DOMException("Denied", "SecurityError");
      },
      getItem: () => {
        throw new DOMException("Denied", "SecurityError");
      },
      key: () => {
        throw new DOMException("Denied", "SecurityError");
      },
      removeItem: () => {
        throw new DOMException("Denied", "SecurityError");
      },
      setItem: () => {
        throw new DOMException("Denied", "SecurityError");
      },
    } satisfies Storage;
    vi.stubGlobal("localStorage", deniedStorage);

    const { renderer, onActivated } = await renderCard();
    await confirmAndActivate(renderer);

    expect(harness.activate).not.toHaveBeenCalled();
    expect(onActivated).not.toHaveBeenCalled();
    expect(nodeText(renderer.root)).toContain(
      "CareSync cannot protect this one-time activation in browser storage.",
    );
    expect(activationButton(renderer).props.disabled).toBe(false);
  });

  it("aborts and ignores an old organization completion while preserving its checkpoint", async () => {
    localStorage.setItem(checkpointKey(), checkpoint());
    let resolveActivation!: (value: ReturnType<typeof releaseResponse>) => void;
    const pendingActivation = new Promise<ReturnType<typeof releaseResponse>>(
      (resolve) => {
        resolveActivation = resolve;
      },
    );
    harness.activate.mockReturnValueOnce(pendingActivation);
    harness.fetchStatus.mockImplementation(
      async (organizationId: string) =>
        organizationId === organizationOne
          ? releaseStatus()
          : releaseStatus(organizationTwo, false, facilityTwo),
    );
    const onActivated = vi.fn();
    const { renderer } = await renderCard({ onActivated });

    await act(async () => {
      confirmationInput(renderer).props.onChange({
        target: { checked: true },
      });
    });
    let oldActivation!: Promise<void>;
    await act(async () => {
      oldActivation = activationButton(renderer).props.onClick();
      await Promise.resolve();
    });
    expect(harness.activate).toHaveBeenCalledTimes(1);

    await act(async () => {
      renderer.update(
        createElement(
          ThemeProvider,
          { theme: workspaceTheme },
          createElement(RoomSafetyActivationCard, {
            organizationId: organizationTwo,
            actorUserId: actorTwo,
            canActivate: true,
            onActivated,
          }),
        ),
      );
    });
    await settle();
    await act(async () => {
      resolveActivation(releaseResponse());
      await oldActivation;
    });
    await settle();

    expect(onActivated).not.toHaveBeenCalled();
    expect(harness.fetchCapability).not.toHaveBeenCalled();
    expect(localStorage.getItem(checkpointKey())).toBe(checkpoint());
    expect(nodeText(renderer.root)).toContain("1 active facility");
    expect(confirmationInput(renderer).props.checked).toBe(false);
  });
});
