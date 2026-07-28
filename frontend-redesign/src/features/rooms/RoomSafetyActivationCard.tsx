import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import { ActionButton, Eyebrow, GlassPanel } from "../../components/ui/Primitives";
import {
  RoomSafetyContractError,
  activateRoomSafetyRelease,
  fetchLiveRoomSafetyCapability,
  fetchRoomSafetyReleaseStatus,
  type LiveRoomSafetyCapability,
  type RoomSafetyReleaseResponse,
  type RoomSafetyReleaseStatus,
} from "./roomSafetyApi";

const Card = styled(GlassPanel)`
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 22px;
  padding: 20px;
  overflow: hidden;
  border-color: color-mix(
    in srgb,
    ${({ theme }) => theme.color.cyan} 42%,
    ${({ theme }) => theme.color.border}
  );
  &::before {
    position: absolute;
    inset: 0 auto 0 0;
    width: 3px;
    content: "";
    background: linear-gradient(
      ${({ theme }) => theme.color.cyan},
      ${({ theme }) => theme.color.plasma}
    );
    box-shadow: 0 0 24px ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 8px 0 6px;
    font-family: "CareSync Display", sans-serif;
    font-size: clamp(1.05rem, 2vw, 1.35rem);
    font-weight: 540;
    letter-spacing: -0.025em;
  }
  p {
    max-width: 760px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.73rem;
    line-height: 1.65;
  }
  @media (max-width: 720px) {
    grid-template-columns: 1fr;
  }
`;

const Facts = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 13px;
  span {
    padding: 6px 9px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 9px 4px 9px 4px;
    color: ${({ theme }) => theme.color.textSoft};
    background: ${({ theme }) => theme.color.control};
    font-size: 0.68rem;
  }
`;

const Actions = styled.div`
  display: grid;
  justify-items: end;
  gap: 8px;
  min-width: min(250px, 100%);
  small {
    max-width: 260px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
    line-height: 1.45;
    text-align: right;
  }
  @media (max-width: 720px) {
    justify-items: stretch;
    small {
      max-width: none;
      text-align: left;
    }
  }
`;

const Confirmation = styled.label`
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: 0.7rem;
  line-height: 1.45;
  cursor: pointer;
  input {
    flex: 0 0 auto;
    margin-top: 2px;
    accent-color: ${({ theme }) => theme.color.cyan};
  }
`;

const Notice = styled.div<{ $error?: boolean }>`
  grid-column: 1 / -1;
  padding: 10px 12px;
  border: 1px solid
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.mint)};
  border-radius: 9px 4px 9px 4px;
  color: ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.mint)};
  background: color-mix(
    in srgb,
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.mint)} 8%,
    transparent
  );
  font-size: 0.7rem;
  line-height: 1.5;
`;

const CHECKPOINT_SCHEMA = "caresync-room-safety-activation-v1";
const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface ActivationCheckpoint {
  schema: typeof CHECKPOINT_SCHEMA;
  organizationId: string;
  actorUserId: string;
  operationId: string;
}

function checkpointKey(organizationId: string, actorUserId: string): string {
  return `${CHECKPOINT_SCHEMA}:${organizationId.toLowerCase()}:${actorUserId.toLowerCase()}`;
}

function removeCheckpointKey(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Storage denial is handled by the caller's visible recovery state.
  }
}

function readCheckpoint(
  organizationId: string,
  actorUserId: string,
): ActivationCheckpoint | null {
  const key = checkpointKey(organizationId, actorUserId);
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value) ||
      Object.keys(value).sort().join(",") !==
        "actorUserId,operationId,organizationId,schema" ||
      (value as ActivationCheckpoint).schema !== CHECKPOINT_SCHEMA ||
      (value as ActivationCheckpoint).organizationId !==
        organizationId.toLowerCase() ||
      (value as ActivationCheckpoint).actorUserId !==
        actorUserId.toLowerCase() ||
      !UUID.test((value as ActivationCheckpoint).operationId)
    ) {
      removeCheckpointKey(key);
      return null;
    }
    return value as ActivationCheckpoint;
  } catch {
    removeCheckpointKey(key);
    return null;
  }
}

function writeCheckpoint(value: ActivationCheckpoint): boolean {
  try {
    localStorage.setItem(
      checkpointKey(value.organizationId, value.actorUserId),
      JSON.stringify(value),
    );
    return true;
  } catch {
    return false;
  }
}

function clearCheckpoint(organizationId: string, actorUserId: string): void {
  removeCheckpointKey(checkpointKey(organizationId, actorUserId));
}

export default function RoomSafetyActivationCard({
  organizationId,
  actorUserId,
  canActivate,
  onActivated,
}: {
  organizationId: string;
  actorUserId: string;
  canActivate: boolean;
  onActivated: (
    capability: LiveRoomSafetyCapability,
    activatedFacilityCount: number,
  ) => void;
}) {
  const [status, setStatus] = useState<RoomSafetyReleaseStatus | null>(null);
  const [phase, setPhase] = useState<
    "checking" | "ready" | "activating" | "unavailable" | "error"
  >("checking");
  const [message, setMessage] = useState("");
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [pendingOperationId, setPendingOperationId] = useState<string | null>(
    () => readCheckpoint(organizationId, actorUserId)?.operationId ?? null,
  );
  const activationController = useRef<AbortController | null>(null);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!canActivate) {
        setStatus(null);
        setPhase("unavailable");
        return null;
      }
      setPhase("checking");
      setMessage("");
      try {
        const next = await fetchRoomSafetyReleaseStatus(
          organizationId,
          signal,
        );
        if (signal?.aborted) return null;
        setStatus(next);
        if (!next) {
          setPhase("unavailable");
          return null;
        }
        if (next.complete) {
          clearCheckpoint(organizationId, actorUserId);
          setPendingOperationId(null);
          setPhase("unavailable");
          return next;
        }
        setPhase("ready");
        return next;
      } catch (caught) {
        if (signal?.aborted) return null;
        setStatus(null);
        setPhase("error");
        setMessage(
          caught instanceof Error
            ? caught.message
            : "CareSync could not verify the live room activation review.",
        );
        return null;
      }
    },
    [actorUserId, canActivate, organizationId],
  );

  useEffect(() => {
    activationController.current?.abort();
    setReviewConfirmed(false);
    setPendingOperationId(
      readCheckpoint(organizationId, actorUserId)?.operationId ?? null,
    );
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => {
      controller.abort();
      activationController.current?.abort();
    };
  }, [refresh]);

  const activate = async () => {
    if (!status || status.complete || phase === "activating") return;
    const operationId = pendingOperationId ?? crypto.randomUUID();
    const checkpoint: ActivationCheckpoint = {
      schema: CHECKPOINT_SCHEMA,
      organizationId: organizationId.toLowerCase(),
      actorUserId: actorUserId.toLowerCase(),
      operationId,
    };
    if (!writeCheckpoint(checkpoint)) {
      setMessage(
        "CareSync cannot protect this one-time activation in browser storage. Allow site storage, then retry.",
      );
      setPhase("ready");
      return;
    }
    setPendingOperationId(operationId);
    activationController.current?.abort();
    const controller = new AbortController();
    activationController.current = controller;
    setPhase("activating");
    setMessage("");
    try {
      let nextReceipt: RoomSafetyReleaseResponse;
      try {
        nextReceipt = await activateRoomSafetyRelease({
          organizationId,
          operationId,
          expectedStatus: status,
          signal: controller.signal,
        });
      } catch (caught) {
        if (controller.signal.aborted) return;
        const currentStatus = await fetchRoomSafetyReleaseStatus(
          organizationId,
          controller.signal,
        );
        if (currentStatus?.complete) {
          const capability = await fetchLiveRoomSafetyCapability(
            organizationId,
            controller.signal,
          );
          if (!capability)
            throw new RoomSafetyContractError(
              "Activation completed, but the live room capability is not yet available. Retry verification.",
            );
          clearCheckpoint(organizationId, actorUserId);
          setPendingOperationId(null);
          setStatus(currentStatus);
          setPhase("unavailable");
          onActivated(capability, currentStatus.active_facility_count);
          return;
        }
        if (
          currentStatus &&
          currentStatus.facility_set_sha256 !== status.facility_set_sha256
        ) {
          clearCheckpoint(organizationId, actorUserId);
          setPendingOperationId(null);
          setStatus(currentStatus);
          setReviewConfirmed(false);
          setPhase("ready");
          setMessage(
            "The active facility set changed. Review the updated activation scope, then continue with a new protected operation.",
          );
          return;
        }
        throw caught;
      }
      if (controller.signal.aborted) return;
      const verifiedStatus = await fetchRoomSafetyReleaseStatus(
        organizationId,
        controller.signal,
      );
      if (
        !verifiedStatus?.complete ||
        verifiedStatus.facility_set_sha256 !==
          nextReceipt.facility_set_sha256
      )
        throw new RoomSafetyContractError(
          "CareSync could not verify the completed activation receipt.",
        );
      const capability = await fetchLiveRoomSafetyCapability(
        organizationId,
        controller.signal,
      );
      if (!capability)
        throw new RoomSafetyContractError(
          "Activation completed, but the live room capability is not yet available. Retry verification.",
        );
      clearCheckpoint(organizationId, actorUserId);
      setPendingOperationId(null);
      setStatus(verifiedStatus);
      setPhase("unavailable");
      onActivated(capability, verifiedStatus.active_facility_count);
    } catch (caught) {
      if (controller.signal.aborted) return;
      setPhase("ready");
      setMessage(
        caught instanceof Error
          ? caught.message
          : "The activation outcome is not confirmed. Retry uses the same protected operation.",
      );
    }
  };

  if (!canActivate || phase === "unavailable") return null;
  if (phase === "checking" && !status) return null;
  if (phase === "error" && !status)
    return (
      <Card>
        <div>
          <Eyebrow>
            <ShieldCheckIcon width={14} /> Live operations activation
          </Eyebrow>
          <h2>Activation review could not be verified.</h2>
          <p>{message}</p>
        </div>
        <Actions>
          <ActionButton type="button" onClick={() => void refresh()}>
            <ArrowPathIcon /> Retry verification
          </ActionButton>
        </Actions>
      </Card>
    );
  if (!status) return null;

  return (
    <Card aria-live="polite" aria-busy={phase === "activating"}>
      <div>
        <Eyebrow>
          <ShieldCheckIcon width={14} /> One-time operational review
        </Eyebrow>
        <h2>Activate live room operations.</h2>
        <p>
          CareSync will inspect current attendance, open staff shifts, room
          assignments, configured capacity, and your operational staffing
          targets. It creates current review signals only; it does not invent
          historical room presence or send activation notifications.
        </p>
        <Facts>
          <span>
            {status.active_facility_count} active{" "}
            {status.active_facility_count === 1 ? "facility" : "facilities"}
          </span>
          <span>No historical presence backfill</span>
          <span>Configured-target evidence only</span>
        </Facts>
        <Confirmation>
          <input
            type="checkbox"
            checked={reviewConfirmed}
            onChange={(event) => setReviewConfirmed(event.target.checked)}
            disabled={phase === "activating"}
          />
          <span>
            I reviewed this one-time activation scope and understand that
            CareSync will derive current operational signals without inventing
            historical room presence.
          </span>
        </Confirmation>
      </div>
      <Actions>
        <ActionButton
          type="button"
          $variant="primary"
          onClick={() => void activate()}
          disabled={phase === "activating" || !reviewConfirmed}
          aria-busy={phase === "activating"}
        >
          {phase === "activating" ? (
            <>
              <ArrowPathIcon /> Activating…
            </>
          ) : (
            <>
              <CheckCircleIcon /> Activate live room operations
            </>
          )}
        </ActionButton>
        <small>
          If the connection drops, retry continues the same protected
          activation instead of starting over.
        </small>
      </Actions>
      {message && <Notice $error>{message}</Notice>}
    </Card>
  );
}
