import { describe, expect, it } from "vitest";
import roomsPageSource from "./RoomsPage.tsx?raw";
import liveSource from "./RoomSafetyLiveWorkspace.tsx?raw";
import compactSource from "./RoomSafetyCompactSummary.tsx?raw";
import activationSource from "./RoomSafetyActivationCard.tsx?raw";
import apiSource from "./roomSafetyApi.ts?raw";
import operationSource from "./roomSafetyOperation.ts?raw";
import coverageSource from "../../realtime/realtimeCoverage.ts?raw";
import notificationSource from "../notifications/NotificationInbox.tsx?raw";

describe("0041 administrator live room operations integration", () => {
  it("mounts Live operations inside the existing Rooms workspace only after exact capability discovery", () => {
    expect(roomsPageSource).toContain(
      'const requestedWorkspaceView = searchParams.get("view")',
    );
    expect(roomsPageSource).toContain(
      'requestedWorkspaceView === "live"',
    );
    expect(roomsPageSource).toContain("<RoomSafetyLiveWorkspace");
    expect(roomsPageSource).toContain("liveCapabilityPhase === \"enabled\"");
    expect(roomsPageSource).toContain("ACCESS.facilityRead");
    expect(roomsPageSource).toContain("ACCESS.careRosterRead");
    expect(roomsPageSource).toContain("ACCESS.staffManageEducators");
    expect(roomsPageSource).not.toContain('navigate("/room-safety")');
  });

  it("keeps 0041 unavailable until an authorized, resumable release review completes", () => {
    expect(roomsPageSource).toContain("<RoomSafetyActivationCard");
    expect(roomsPageSource).toContain("canActivateLiveOperations");
    expect(apiSource).toContain(
      '"/room-safety/release-reconciliation/status"',
    );
    expect(activationSource).toContain("pendingOperationId");
    expect(activationSource).toContain("writeCheckpoint(checkpoint)");
    expect(activationSource).toContain("fetchLiveRoomSafetyCapability");
    expect(activationSource).not.toContain("setInterval");
  });

  it("keeps configured room capacity and configured operational staffing target as separate facts", () => {
    expect(liveSource).toContain("Configured room capacity");
    expect(liveSource).toContain("Configured operational staffing target");
    expect(liveSource).toContain(
      "LIVE_ROOM_SAFETY_STANDING_BOUNDARY",
    );
    expect(liveSource).toContain("Confirmed room-present staff");
    expect(liveSource).not.toContain("licensed ratio");
    expect(liveSource).not.toContain("regulatory compliance met");
  });

  it("loses positive status when stale, disconnected, unknown, or contract-invalid", () => {
    expect(liveSource).toContain('now - generatedAt >= 60_000');
    expect(liveSource).toContain('realtimeState !== "connected"');
    expect(liveSource).toContain("No live status is shown because");
    expect(apiSource).toContain('invalid("positive room state")');
    expect(apiSource).toContain('invalid("positive facility state")');
    expect(apiSource).toContain(
      'invalid("facility child reconciliation")',
    );
    expect(compactSource).toContain('realtimeState !== "connected"');
    expect(compactSource).toContain("setBoard(null)");
    expect(compactSource).toContain(
      "No counts or positive status are shown",
    );
  });

  it("protects one exact acknowledgement and never exposes manual resolution, dismissal, or waiver", () => {
    expect(liveSource).toContain(
      "executeProtectedRoomExceptionAcknowledgement",
    );
    expect(operationSource).toContain(
      "input.storage.setItem(key, JSON.stringify(pending))",
    );
    expect(operationSource).toContain(
      "RoomSafetyOperationOutcomeUnknownError",
    );
    expect(liveSource).toContain("Acknowledgement is not resolution");
    expect(liveSource).toContain(
      "reconcileCanonicallyConfirmedAcknowledgements",
    );
    expect(liveSource).toContain("Start a new reviewed action");
    expect(liveSource).toContain("was intentionally not stored");
    expect(liveSource).not.toContain("Resolve signal");
    expect(liveSource).not.toContain("Dismiss signal");
    expect(liveSource).not.toContain("Waive");
  });

  it("refreshes canonical room truth before the realtime cursor can advance", () => {
    for (const entity of [
      "attendance_day",
      "staff_shift",
      "staff_coverage_target",
      "staff_room_presence",
      "room_operational_exception",
    ])
      expect(liveSource).toContain(`"${entity}"`);
    expect(coverageSource).toContain(
      "the mounted Live operations mode additionally rebuilds its canonical board and exception page before the realtime cursor advances",
    );
  });

  it("resolves a notification entity through the authenticated action-target endpoint before navigation", () => {
    expect(notificationSource).toContain(
      "fetchRoomExceptionActionTarget",
    );
    expect(notificationSource).toContain("roomExceptionTargetPath");
    expect(apiSource).toContain(
      "/action-target",
    );
    expect(apiSource).toContain('action_path: "/rooms"');
    expect(apiSource).toContain('target.state === "resolved"');
    expect(apiSource).toContain(
      "This operational signal is no longer available.",
    );
    const resolution = notificationSource.indexOf(
      "path = roomExceptionTargetPath(actionTarget)",
    );
    const markRead = notificationSource.indexOf(
      "notificationsApi.read(item.id)",
    );
    const navigate = notificationSource.indexOf("navigate(path)");
    expect(resolution).toBeGreaterThan(-1);
    expect(resolution).toBeLessThan(markRead);
    expect(resolution).toBeLessThan(navigate);
  });
});
