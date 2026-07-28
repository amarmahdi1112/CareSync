import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ArrowPathIcon,
  BuildingOffice2Icon,
  CheckCircleIcon,
  Cog6ToothIcon,
  ExclamationTriangleIcon,
  PencilSquareIcon,
  PlusIcon,
  RectangleGroupIcon,
  SignalIcon,
  SparklesIcon,
  Squares2X2Icon,
  UserGroupIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import { useSearchParams } from "react-router-dom";
import { useSession } from "../../auth/SessionContext";
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import { ACCESS, hasPermission } from "../../auth/accessModel";
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  IconButton,
  StatusChip,
} from "../../components/ui/Primitives";
import {
  ROOM_AGE_GROUP_OPTIONS,
  includesDomainValue,
} from "../../models/domainOptions";
import {
  PROGRAM_TYPE_LABELS,
  formatProgramType,
} from "../../models/programTypes";
import {
  createProgram,
  createRoom,
  fetchRoomDeactivationImpact,
  fetchRoomRoster,
  fetchRoomWorkspace,
  updateProgram,
  updateRoom,
  type ProgramMutation,
  type ProgramRecord,
  type RoomMutation,
  type RoomRecord,
  type RoomRoster,
  type RoomWorkspace,
} from "./roomsApi";
import {
  fetchLiveRoomSafetyCapability,
  type LiveRoomSafetyCapability,
  type RoomExceptionActionTarget,
} from "./roomSafetyApi";
import type { DeactivationImpact } from "../../models/deactivationImpact";
import {
  activeRoomCapacity,
  editableProgramTypes,
  missingProgramTypes,
  validateProgramInWorkspace,
  validateRoomInWorkspace,
} from "./roomsModel";
import RoomRosterPanel, { type RosterLoadState } from "./RoomRosterPanel";
import RoomPlacementReviewDialog from "./RoomPlacementReviewDialog";
import RoomSafetyActivationCard from "./RoomSafetyActivationCard";
import RoomSafetyLiveWorkspace from "./RoomSafetyLiveWorkspace";

const Page = styled.div`
  display: grid;
  gap: 24px;
`;

const Header = styled.header`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 22px;
  h1 {
    margin: 10px 0 7px;
    font-family: "CareSync Display", sans-serif;
    font-size: clamp(1.85rem, 3.4vw, 2.85rem);
    font-weight: 520;
    letter-spacing: -0.045em;
  }
  p {
    max-width: 690px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.78rem;
    line-height: 1.75;
  }
  @media (max-width: 760px) {
    align-items: flex-start;
    flex-direction: column;
  }
`;

const HeaderActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
`;
const ModeSwitch = styled.div`
  display: inline-flex;
  gap: 5px;
  padding: 4px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 11px 5px 11px 5px;
  background: ${({ theme }) => theme.color.control};
  button {
    display: inline-flex;
    min-height: 38px;
    align-items: center;
    gap: 7px;
    padding: 0 11px;
    border: 1px solid transparent;
    border-radius: 8px 4px 8px 4px;
    color: ${({ theme }) => theme.color.textMuted};
    background: transparent;
    cursor: pointer;
    font: inherit;
    font-size: 0.72rem;
  }
  button[aria-pressed="true"] {
    border-color: ${({ theme }) => theme.color.cyan};
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.surfaceHover};
  }
  svg {
    width: 16px;
  }
`;
const Toolbar = styled(GlassPanel)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  select {
    min-width: min(310px, 70vw);
    min-height: 44px;
    padding: 0 13px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 11px;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: 0.76rem;
  }
  @media (max-width: 620px) {
    align-items: stretch;
    flex-direction: column;
    select {
      width: 100%;
      min-width: 0;
    }
  }
`;

const Metrics = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 700px) {
    grid-template-columns: 1fr;
  }
`;
const Metric = styled(GlassPanel)`
  padding: 18px;
  span {
    display: flex;
    align-items: center;
    gap: 8px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  svg {
    width: 18px;
    color: ${({ theme }) => theme.color.cyan};
  }
  strong {
    display: block;
    margin-top: 12px;
    font-family: "CareSync Display", sans-serif;
    font-size: 2rem;
    font-weight: 590;
  }
  small {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
  }
`;

const Workspace = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.55fr);
  gap: 16px;
  @media (max-width: 920px) {
    grid-template-columns: 1fr;
  }
`;
const Section = styled(GlassPanel)`
  padding: 20px;
`;
const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.35rem;
    font-weight: 560;
    letter-spacing: -0.04em;
  }
  p {
    margin: 4px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
  }
`;
const RoomGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  @media (max-width: 650px) {
    grid-template-columns: 1fr;
  }
`;
const RoomCard = styled.div<{ $selected?: boolean }>`
  position: relative;
  display: grid;
  overflow: hidden;
  border: 1px solid
    ${({ $selected, theme }) => ($selected ? theme.color.cyan : theme.color.border)};
  border-radius: 15px 7px 15px 7px;
  background: ${({ $selected, theme }) =>
    $selected
      ? `color-mix(in srgb, ${theme.color.surfaceStrong} 92%, ${theme.color.cyan})`
      : theme.color.surfaceStrong};
  box-shadow: ${({ $selected, theme }) => ($selected ? theme.shadow.cyan : "none")};
  transition:
    transform ${({ theme }) => theme.motion.fast}
      ${({ theme }) => theme.motion.ease},
    border-color ${({ theme }) => theme.motion.fast} ease,
    background ${({ theme }) => theme.motion.fast} ease;
  &:hover {
    transform: translateY(-1px);
    border-color: ${({ theme }) => theme.color.cyan};
    background: ${({ theme }) => theme.color.surfaceHover};
  }
  &:focus-within {
    border-color: ${({ theme }) => theme.color.cyan};
  }
  h3 {
    margin: 0;
    font-size: 0.92rem;
  }
  p {
    margin: 4px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
  }
`;
const RoomOpenButton = styled.button`
  display: grid;
  gap: 14px;
  width: 100%;
  padding: 17px 56px 17px 17px;
  border: 0;
  border-radius: inherit;
  color: inherit;
  background: transparent;
  cursor: pointer;
  text-align: left;
  &:focus-visible {
    outline: 0;
    box-shadow: inset 0 0 0 2px ${({ theme }) => theme.color.cyan};
  }
`;
const RoomTop = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
`;
const TinyButton = styled(IconButton)`
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  width: 44px;
  height: 44px;
  &:focus-visible {
    outline: 0;
    box-shadow: inset 0 0 0 2px ${({ theme }) => theme.color.cyan};
  }
  svg {
    width: 16px;
  }
`;
const RoomStats = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.72rem;
  }
  svg {
    width: 15px;
    color: ${({ theme }) => theme.color.cyan};
  }
`;
const CapacityTrack = styled.div`
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: ${({ theme }) => theme.color.surfaceHover};
  span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: ${({ theme }) => theme.color.cyan};
    box-shadow: ${({ theme }) => theme.shadow.cyan};
  }
`;
const ProgramList = styled.div`
  display: grid;
  gap: 9px;
`;
const ProgramRow = styled.button`
  display: grid;
  grid-template-columns: 36px 1fr auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 44px;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.surfaceStrong};
  cursor: pointer;
  text-align: left;
  > svg {
    width: 19px;
    margin: auto;
    color: ${({ theme }) => theme.color.plasmaBright};
  }
  strong {
    display: block;
    font-size: 0.76rem;
    font-weight: 600;
  }
  small {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
  }
  transition:
    border-color ${({ theme }) => theme.motion.fast} ease,
    background ${({ theme }) => theme.motion.fast} ease,
    transform ${({ theme }) => theme.motion.fast}
      ${({ theme }) => theme.motion.ease};
  &:hover {
    transform: translateY(-1px);
    border-color: ${({ theme }) => theme.color.cyan};
    background: ${({ theme }) => theme.color.surfaceHover};
  }
  &:disabled {
    cursor: not-allowed;
    opacity: 0.58;
    transform: none;
  }
`;
const Empty = styled.div`
  display: grid;
  min-height: 210px;
  place-items: center;
  padding: 28px;
  border: 1px dashed ${({ theme }) => theme.color.border};
  border-radius: 14px;
  text-align: center;
  svg {
    width: 40px;
    margin: 0 auto 11px;
    color: ${({ theme }) => theme.color.textMuted};
  }
  h3 {
    margin: 0 0 5px;
  }
  p {
    max-width: 430px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
    line-height: 1.6;
  }
`;
const Gate = styled(GlassPanel)`
  display: grid;
  min-height: 330px;
  place-items: center;
  padding: 30px;
  text-align: center;
  svg {
    width: 45px;
    margin: 0 auto 12px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 0 0 7px;
  }
  p {
    max-width: 520px;
    margin: 0 auto 16px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
  }
`;

const Overlay = styled.div`
  position: fixed;
  inset: 0;
  z-index: 800;
  display: grid;
  place-items: center;
  padding: 18px;
  overflow-y: auto;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});
`;
const Dialog = styled(GlassPanel)`
  width: min(700px, 100%);
  max-height: calc(100vh - 36px);
  padding: 22px;
  overflow-y: auto;
`;
const DialogHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 15px;
  margin-bottom: 20px;
  h2 {
    margin: 5px 0 4px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.65rem;
    font-weight: 560;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
  }
`;
const Form = styled.form`
  display: grid;
  gap: 16px;
`;
const Fields = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 13px;
  @media (max-width: 580px) {
    grid-template-columns: 1fr;
  }
`;
const Field = styled.label<{ $wide?: boolean }>`
  display: grid;
  grid-column: ${({ $wide }) => ($wide ? "1 / -1" : "auto")};
  gap: 6px;
  span {
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.72rem;
    font-weight: 600;
  }
  input,
  select {
    width: 100%;
    min-height: 44px;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 10px;
    outline: none;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: 0.74rem;
  }
  input:focus,
  select:focus {
    border-color: ${({ theme }) => theme.color.cyan};
    box-shadow: 0 0 0 3px
      color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent);
  }
`;
const Toggle = styled.label`
  display: flex;
  grid-column: 1 / -1;
  align-items: center;
  gap: 9px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: 0.75rem;
  input {
    accent-color: ${({ theme }) => theme.color.plasma};
  }
`;
const FormNotice = styled.div<{ $error?: boolean }>`
  padding: 11px 13px;
  border: 1px solid
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.mint)};
  border-radius: 10px 4px 10px 4px;
  color: ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.mint)};
  background: ${({ $error, theme }) => ($error ? `color-mix(in srgb, ${theme.color.surfaceStrong} 92%, ${theme.color.coral})` : `color-mix(in srgb, ${theme.color.surfaceStrong} 92%, ${theme.color.mint})`)};
  font-size: 0.75rem;
  line-height: 1.5;
`;
const FormActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 9px;
`;

type Editor =
  | { kind: "room"; value: RoomRecord | null }
  | { kind: "program"; value: ProgramRecord | null };

const blankRoom = (facilityId = "", programId = ""): RoomMutation => ({
  facility_id: facilityId,
  program_id: programId,
  name: "",
  capacity: 1,
  age_group: null,
  minimum_age_months: null,
  maximum_age_months: null,
  is_active: true,
});
const blankProgram = (
  facilityId = "",
  programType: ProgramMutation["program_type"] = "daycare",
): ProgramMutation => ({
  facility_id: facilityId,
  name: "",
  program_type: programType,
  capacity: 0,
  minimum_age_months: null,
  maximum_age_months: null,
  is_active: true,
});

function RoomEditor({
  editor,
  workspace,
  organizationId,
  defaultFacility,
  onClose,
  onSaved,
}: {
  editor: Editor;
  workspace: RoomWorkspace;
  organizationId: string;
  defaultFacility: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const savingRef = useRef(false);
  const [room, setRoom] = useState<RoomMutation>(() =>
    editor.kind === "room" && editor.value
      ? {
          facility_id: editor.value.facility_id,
          program_id: editor.value.program_id || "",
          name: editor.value.name,
          capacity: editor.value.capacity,
          age_group: editor.value.age_group,
          minimum_age_months: editor.value.minimum_age_months,
          maximum_age_months: editor.value.maximum_age_months,
          is_active: editor.value.is_active,
        }
      : blankRoom(
          defaultFacility,
          workspace.programs.find(
            (item) => item.facility_id === defaultFacility && item.is_active,
          )?.id || "",
        ),
  );
  const [program, setProgram] = useState<ProgramMutation>(() =>
    editor.kind === "program" && editor.value
      ? {
          facility_id: editor.value.facility_id,
          name: editor.value.name,
          program_type: editor.value.program_type,
          capacity: editor.value.capacity,
          minimum_age_months: editor.value.minimum_age_months,
          maximum_age_months: editor.value.maximum_age_months,
          is_active: editor.value.is_active,
        }
      : blankProgram(
          defaultFacility,
          missingProgramTypes(workspace.programs, defaultFacility)[0] ||
            "daycare",
        ),
  );
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [roomImpact, setRoomImpact] = useState<DeactivationImpact | null>(null);
  const [roomConfirmation, setRoomConfirmation] = useState("");
  const [roomDeactivationReason, setRoomDeactivationReason] = useState("");

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !savingRef.current) onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [
        ...dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", keyboard);
    requestAnimationFrame(() =>
      dialogRef.current?.querySelector<HTMLElement>("input, select")?.focus(),
    );
    return () => {
      window.removeEventListener("keydown", keyboard);
      document.body.style.overflow = previousOverflow;
      previous?.focus();
    };
  }, [onClose]);

  const facilityId =
    editor.kind === "room" ? room.facility_id : program.facility_id;
  const availablePrograms = workspace.programs.filter(
    (item) => item.facility_id === facilityId && item.is_active,
  );
  const programTypeChoices =
    editor.kind === "program"
      ? editableProgramTypes(
          workspace.programs,
          facilityId,
          editor.value?.program_type,
        )
      : [];
  const assignedActiveRooms =
    editor.kind === "program" && editor.value
      ? workspace.rooms.filter(
          (item) => item.is_active && item.program_id === editor.value!.id,
        )
      : [];
  const assignedActiveCapacity =
    editor.kind === "program" && editor.value
      ? activeRoomCapacity(workspace.rooms, editor.value.id)
      : 0;
  const programDeactivateLocked =
    editor.kind === "program" &&
    program.is_active &&
    assignedActiveRooms.length > 0;
  const hasCustomRoomAgeGroup = Boolean(
    room.age_group &&
    !includesDomainValue(ROOM_AGE_GROUP_OPTIONS, room.age_group),
  );

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (editor.kind === "program" && !programTypeChoices.length) {
      setNotice(
        "This facility already has both licensed program types. Edit an existing program instead.",
      );
      return;
    }
    const errors =
      editor.kind === "room"
        ? validateRoomInWorkspace(
            room,
            workspace.programs,
            workspace.rooms,
            editor.value?.id,
          )
        : validateProgramInWorkspace(
            program,
            workspace.rooms,
            editor.value?.id,
          );
    if (errors.length) {
      setNotice(errors.join(" "));
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setNotice(null);
    try {
      if (editor.kind === "room") {
        if (editor.value) {
          const isDeactivation = editor.value.is_active && !room.is_active;
          if (isDeactivation && !roomImpact) {
            const impact = await fetchRoomDeactivationImpact(editor.value.id, organizationId);
            setRoomImpact(impact);
            setNotice(impact.can_deactivate ? "Review the impact and confirm this room deactivation." : "This room cannot be deactivated until every blocker is resolved.");
            return;
          }
          if (isDeactivation && roomImpact) {
            if (!roomImpact.can_deactivate) throw new Error("Resolve every deactivation blocker before trying again.");
            if (roomConfirmation !== roomImpact.confirmation_text) throw new Error(`Type “${roomImpact.confirmation_text}” exactly to confirm.`);
            if (roomDeactivationReason.trim().length < 3) throw new Error("Enter a deactivation reason of at least 3 characters.");
          }
          await updateRoom(editor.value.id, {
            ...room,
            ...(isDeactivation && roomImpact ? {
              deactivation_confirmation: roomConfirmation,
              deactivation_reason: roomDeactivationReason.trim(),
            } : {}),
          }, organizationId);
        }
        else await createRoom(room, organizationId);
      } else if (editor.value)
        await updateProgram(editor.value.id, program, organizationId);
      else await createProgram(program, organizationId);
      onSaved();
    } catch (caught) {
      setNotice(
        caught instanceof Error
          ? caught.message
          : "The change could not be saved.",
      );
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !saving && onClose()
      }
    >
      <Dialog
        ref={dialogRef}
        $accent={editor.kind === "room" ? "cyan" : "plasma"}
        role="dialog"
        aria-modal="true"
        aria-labelledby="room-editor-title"
        aria-describedby="room-editor-description"
      >
        <DialogHeader>
          <div>
            <Eyebrow>
              {editor.kind === "room" ? (
                <RectangleGroupIcon width={14} />
              ) : (
                <Squares2X2Icon width={14} />
              )}{" "}
              {editor.kind === "room" ? "Care room" : "Care program"}
            </Eyebrow>
            <h2 id="room-editor-title">
              {editor.value ? "Edit" : "Create"} {editor.kind}.
            </h2>
            <p id="room-editor-description">
              Capacity and age lanes become part of the dependable enrollment
              foundation.
            </p>
          </div>
          <IconButton
            type="button"
            onClick={onClose}
            disabled={saving}
            aria-label="Close editor"
          >
            <XMarkIcon />
          </IconButton>
        </DialogHeader>
        <Form onSubmit={save}>
          <Fields>
            <Field $wide>
              <span>Facility</span>
              <select
                required
                disabled={Boolean(editor.value)}
                value={facilityId}
                onChange={(event) => {
                  const nextFacilityId = event.target.value;
                  if (editor.kind === "room")
                    setRoom((value) => ({
                      ...value,
                      facility_id: nextFacilityId,
                      program_id:
                        workspace.programs.find(
                          (item) =>
                            item.facility_id === nextFacilityId &&
                            item.is_active,
                        )?.id || "",
                    }));
                  else
                    setProgram((value) => ({
                      ...value,
                      facility_id: nextFacilityId,
                      program_type:
                        missingProgramTypes(
                          workspace.programs,
                          nextFacilityId,
                        )[0] || value.program_type,
                    }));
                }}
              >
                {workspace.facilities.map((item) => {
                  const noProgramTypeAvailable =
                    editor.kind === "program" &&
                    !editor.value &&
                    missingProgramTypes(workspace.programs, item.id).length ===
                      0;
                  const noActiveProgram =
                    editor.kind === "room" &&
                    !editor.value &&
                    !workspace.programs.some(
                      (programItem) =>
                        programItem.facility_id === item.id &&
                        programItem.is_active,
                    );
                  return (
                    <option
                      key={item.id}
                      value={item.id}
                      disabled={noProgramTypeAvailable || noActiveProgram}
                    >
                      {item.name}
                      {noProgramTypeAvailable
                        ? " · Daycare and OSC already configured"
                        : noActiveProgram
                          ? " · active program required"
                          : ""}
                    </option>
                  );
                })}
              </select>
            </Field>
            <Field $wide>
              <span>
                {editor.kind === "room" ? "Room name" : "Program name"}
              </span>
              <input
                required
                value={editor.kind === "room" ? room.name : program.name}
                onChange={(event) =>
                  editor.kind === "room"
                    ? setRoom((value) => ({
                        ...value,
                        name: event.target.value,
                      }))
                    : setProgram((value) => ({
                        ...value,
                        name: event.target.value,
                      }))
                }
                placeholder={
                  editor.kind === "room" ? "Infant North" : "Daycare Program"
                }
              />
            </Field>
            {editor.kind === "room" ? (
              <>
                <Field>
                  <span>Capacity</span>
                  <input
                    required
                    type="number"
                    min="1"
                    step="1"
                    value={room.capacity}
                    onChange={(event) =>
                      setRoom((value) => ({
                        ...value,
                        capacity: Number(event.target.value),
                      }))
                    }
                  />
                </Field>
                <Field>
                  <span>Age group</span>
                  <select
                    value={room.age_group || ""}
                    onChange={(event) =>
                      setRoom((value) => ({
                        ...value,
                        age_group: event.target.value || null,
                      }))
                    }
                  >
                    <option value="">Select age group</option>
                    {ROOM_AGE_GROUP_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                    {hasCustomRoomAgeGroup && (
                      <option value={room.age_group!}>
                        Saved custom · {room.age_group}
                      </option>
                    )}
                  </select>
                </Field>
                <Field>
                  <span>Minimum age (months, inclusive)</span>
                  <input
                    required
                    type="number"
                    min="0"
                    step="1"
                    value={room.minimum_age_months ?? ""}
                    onChange={(event) =>
                      setRoom((value) => ({
                        ...value,
                        minimum_age_months:
                          event.target.value === ""
                            ? null
                            : Number(event.target.value),
                      }))
                    }
                  />
                </Field>
                <Field>
                  <span>Maximum age (months, inclusive)</span>
                  <input
                    required
                    type="number"
                    min="0"
                    step="1"
                    value={room.maximum_age_months ?? ""}
                    onChange={(event) =>
                      setRoom((value) => ({
                        ...value,
                        maximum_age_months:
                          event.target.value === ""
                            ? null
                            : Number(event.target.value),
                      }))
                    }
                  />
                </Field>
                <Field $wide>
                  <span>Program</span>
                  <select
                    required
                    value={room.program_id}
                    onChange={(event) =>
                      setRoom((value) => ({
                        ...value,
                        program_id: event.target.value,
                      }))
                    }
                  >
                    <option value="">Select program</option>
                    {availablePrograms.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </>
            ) : (
              <>
                <Field>
                  <span>Licensed program type</span>
                  <select
                    required
                    value={program.program_type}
                    onChange={(event) =>
                      setProgram((value) => ({
                        ...value,
                        program_type: event.target
                          .value as ProgramMutation["program_type"],
                      }))
                    }
                  >
                    {programTypeChoices.map((type) => (
                      <option key={type} value={type}>
                        {PROGRAM_TYPE_LABELS[type]}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field>
                  <span>Capacity</span>
                  <input
                    required
                    type="number"
                    min={assignedActiveCapacity}
                    step="1"
                    value={program.capacity}
                    onChange={(event) =>
                      setProgram((value) => ({
                        ...value,
                        capacity: Number(event.target.value),
                      }))
                    }
                  />
                </Field>
                <Field>
                  <span>Minimum age (months)</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={program.minimum_age_months ?? ""}
                    onChange={(event) =>
                      setProgram((value) => ({
                        ...value,
                        minimum_age_months: event.target.value
                          ? Number(event.target.value)
                          : null,
                      }))
                    }
                  />
                </Field>
                <Field>
                  <span>Maximum age (months)</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={program.maximum_age_months ?? ""}
                    onChange={(event) =>
                      setProgram((value) => ({
                        ...value,
                        maximum_age_months: event.target.value
                          ? Number(event.target.value)
                          : null,
                      }))
                    }
                  />
                </Field>
              </>
            )}
            {editor.kind === "room" ? (
              <Toggle>
                <input
                  type="checkbox"
                  checked={room.is_active}
                  onChange={(event) =>
                    { setRoom((value) => ({
                        ...value,
                        is_active: event.target.checked,
                      })); setRoomImpact(null); setRoomConfirmation(""); setRoomDeactivationReason(""); }
                  }
                />{" "}
                Active and available for new enrollment
              </Toggle>
            ) : (
              <Toggle
                title={
                  programDeactivateLocked
                    ? "Active assigned rooms must be moved or deactivated first."
                    : undefined
                }
              >
                <input
                  type="checkbox"
                  checked={program.is_active}
                  disabled={programDeactivateLocked}
                  onChange={(event) =>
                    setProgram((value) => ({
                      ...value,
                      is_active: event.target.checked,
                    }))
                  }
                />{" "}
                Active and available for room assignment
              </Toggle>
            )}
          </Fields>
          {editor.kind === "program" && assignedActiveRooms.length > 0 && (
            <FormNotice role="status">
              {assignedActiveRooms.length} active room
              {assignedActiveRooms.length === 1 ? "" : "s"} use this program (
              {assignedActiveCapacity} places total). Capacity cannot go below{" "}
              {assignedActiveCapacity}, and the program cannot be deactivated
              until those rooms move or become inactive.
            </FormNotice>
          )}
          {editor.kind === "program" && !programTypeChoices.length && (
            <FormNotice $error role="alert">
              This facility already has both licensed program types. Edit an
              existing program instead.
            </FormNotice>
          )}
          {editor.kind === "room" && roomImpact && editor.value?.is_active && !room.is_active && <>
            <FormNotice $error={!roomImpact.can_deactivate} role={roomImpact.can_deactivate ? "status" : "alert"}>
              {roomImpact.active_programs} active programs · {roomImpact.active_rooms} active rooms · {roomImpact.open_enrollments} open enrollments · {roomImpact.open_attendance_intervals} open attendance intervals · {roomImpact.active_staff_assignments} active staff assignments · {roomImpact.open_staff_shifts} open staff shifts
              {roomImpact.blockers.map((item) => <div key={item}>Blocker: {item}</div>)}
              {roomImpact.warnings.map((item) => <div key={item}>Warning: {item}</div>)}
            </FormNotice>
            <Fields>
              <Field $wide><span>Type {roomImpact.confirmation_text} exactly</span><input disabled={!roomImpact.can_deactivate} value={roomConfirmation} onChange={(event) => setRoomConfirmation(event.target.value)} autoComplete="off" /></Field>
              <Field $wide><span>Reason for deactivation</span><input disabled={!roomImpact.can_deactivate} value={roomDeactivationReason} onChange={(event) => setRoomDeactivationReason(event.target.value)} placeholder="Required for the audit record" /></Field>
            </Fields>
          </>}
          {notice && (
            <FormNotice $error role="alert">
              {notice}
            </FormNotice>
          )}
          <FormActions>
            <ActionButton type="button" onClick={onClose} disabled={saving}>
              Cancel
            </ActionButton>
            <ActionButton
              type="submit"
              $variant="primary"
              disabled={
                saving ||
                (editor.kind === "program" && !programTypeChoices.length) ||
                Boolean(editor.kind === "room" && roomImpact && !roomImpact.can_deactivate)
              }
            >
              {saving
                ? "Saving…"
                : editor.value
                  ? "Save changes"
                  : `Create ${editor.kind}`}
            </ActionButton>
          </FormActions>
        </Form>
      </Dialog>
    </Overlay>
  );
}

export type PlacementDeepLinkResolution =
  | { state: 'wait' }
  | { state: 'valid'; facilityId: string; enrollmentId: string }
  | { state: 'invalid'; message: string };

export function resolvePlacementDeepLink(
  requestedFacilityId: string,
  requestedEnrollmentId: string,
  workspace: RoomWorkspace,
  roster: RoomRoster | null,
): PlacementDeepLinkResolution {
  if (!requestedFacilityId || !requestedEnrollmentId) {
    return { state: 'invalid', message: 'The placement-review link was incomplete and was safely ignored.' };
  }
  if (!workspace.facilities.some((facility) => facility.id === requestedFacilityId)) {
    return { state: 'invalid', message: 'That placement-review facility is stale or outside the loaded organization.' };
  }
  if (!roster || roster.facility_id !== requestedFacilityId) return { state: 'wait' };
  const enrollment = roster.unassigned_children.find((child) => child.enrollment_id === requestedEnrollmentId);
  if (!enrollment || enrollment.facility_id !== requestedFacilityId) {
    return { state: 'invalid', message: 'That enrollment is no longer in this facility’s unassigned placement queue.' };
  }
  return { state: 'valid', facilityId: requestedFacilityId, enrollmentId: requestedEnrollmentId };
}

export default function RoomsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedWorkspaceView = searchParams.get("view");
  const requestedFacilityParameter = searchParams.get("facility_id") || "";
  const session = useSession();
  const organizationReady =
    session.status === "authenticated" &&
    Boolean(session.user?.organization_id) &&
    session.user?.organization_id === session.organization?.id &&
    !session.organizationUnavailable;
  const organizationId = organizationReady ? session.organization!.id : "";
  const isOwner = hasPermission(session.user, ACCESS.facilityManage);
  const canViewLiveOperations = [
    ACCESS.facilityRead,
    ACCESS.careRosterRead,
    ACCESS.staffManageEducators,
  ].every((permission) => hasPermission(session.user, permission));
  const canActivateLiveOperations =
    canViewLiveOperations &&
    hasPermission(session.user, ACCESS.facilityManage) &&
    ["owner", "administrator"].includes(session.user?.role?.key || "");
  const [workspace, setWorkspace] = useState<RoomWorkspace | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [error, setError] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [placementReviewOpen, setPlacementReviewOpen] = useState(false);
  const [version, setVersion] = useState(0);
  const [roster, setRoster] = useState<RoomRoster | null>(null);
  const [rosterState, setRosterState] = useState<RosterLoadState>("idle");
  const [rosterError, setRosterError] = useState("");
  const [rosterVersion, setRosterVersion] = useState(0);
  const [selectedRoomId, setSelectedRoomId] = useState("");
  const [placementEnrollmentId, setPlacementEnrollmentId] = useState("");
  const [deepLinkNotice, setDeepLinkNotice] = useState("");
  const [liveCapability, setLiveCapability] =
    useState<LiveRoomSafetyCapability | null>(null);
  const [liveCapabilityPhase, setLiveCapabilityPhase] = useState<
    "idle" | "checking" | "enabled" | "disabled"
  >("idle");
  const handledDeepLink = useRef("");

  useEffect(() => {
    if (!organizationReady || !organizationId || !canViewLiveOperations) {
      setLiveCapability(null);
      setLiveCapabilityPhase("disabled");
      return;
    }
    const controller = new AbortController();
    setLiveCapability(null);
    setLiveCapabilityPhase("checking");
    void fetchLiveRoomSafetyCapability(organizationId, controller.signal)
      .then((capability) => {
        if (controller.signal.aborted) return;
        setLiveCapability(capability);
        setLiveCapabilityPhase(capability ? "enabled" : "disabled");
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setLiveCapability(null);
        setLiveCapabilityPhase("disabled");
        if (requestedWorkspaceView === "live")
          setDeepLinkNotice(
            caught instanceof Error
              ? `Live operations is unavailable: ${caught.message}`
              : "Live operations is unavailable because its capability could not be verified.",
          );
      });
    return () => controller.abort();
  }, [
    canViewLiveOperations,
    organizationId,
    organizationReady,
  ]);

  const refreshRooms = useCallback(async () => {
    if (!organizationId) return;
    const nextWorkspace = await fetchRoomWorkspace(organizationId);
    const nextFacilityId = facilityId && nextWorkspace.facilities.some((item) => item.id === facilityId) ? facilityId : nextWorkspace.facilities[0]?.id || '';
    const nextRoster = nextFacilityId ? await fetchRoomRoster(nextFacilityId, organizationId, nextWorkspace.rooms) : null;
    setWorkspace(nextWorkspace); setFacilityId(nextFacilityId); setStatus('ready'); setError('');
    setRoster(nextRoster); setRosterState(nextRoster ? 'ready' : 'idle'); setRosterError('');
  }, [facilityId, organizationId]);
  useRealtimeRefresh({ scope: 'rooms', organizationId, enabled: organizationReady, entityTypes: featureIntegrationManifest.rooms.realtimeEntities, refresh: refreshRooms });

  useEffect(() => {
    if (!organizationReady || !organizationId) {
      setStatus("idle");
      setWorkspace(null);
      return;
    }
    const controller = new AbortController();
    setStatus("loading");
    setError("");
    fetchRoomWorkspace(organizationId, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setWorkspace(value);
        setFacilityId((current) => {
          const requestedFacilityId = requestedFacilityParameter;
          if (
            requestedFacilityId &&
            value.facilities.some((item) => item.id === requestedFacilityId)
          )
            return requestedFacilityId;
          return current &&
            value.facilities.some((item) => item.id === current)
            ? current
            : value.facilities[0]?.id || "";
        });
        setStatus("ready");
      })
      .catch((caught) => {
        if (!controller.signal.aborted) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Rooms could not be loaded.",
          );
          setStatus("error");
        }
      });
    return () => controller.abort();
  }, [
    organizationId,
    organizationReady,
    requestedFacilityParameter,
    version,
  ]);

  useEffect(() => {
    if (!organizationId || !facilityId || !workspace || status !== "ready") {
      setRoster(null);
      setRosterState("idle");
      return;
    }
    const controller = new AbortController();
    setRosterState("loading");
    setRosterError("");
    fetchRoomRoster(
      facilityId,
      organizationId,
      workspace.rooms,
      controller.signal,
    )
      .then((value) => {
        if (controller.signal.aborted) return;
        setRoster(value);
        setRosterState("ready");
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setRoster(null);
        setRosterError(
          caught instanceof Error
            ? caught.message
            : "The room roster could not be loaded.",
        );
        setRosterState("error");
      });
    return () => controller.abort();
  }, [facilityId, organizationId, rosterVersion, status, workspace]);

  useEffect(() => {
    if (!workspace || status !== 'ready') return;
    const requestedFacilityId = searchParams.get('facility_id') || '';
    const requestedEnrollmentId = searchParams.get('placement_enrollment_id') || '';
    if (!requestedEnrollmentId) return;
    const key = `${requestedFacilityId}\u0000${requestedEnrollmentId}`;
    if (handledDeepLink.current === key) return;
    const resolution = resolvePlacementDeepLink(
      requestedFacilityId,
      requestedEnrollmentId,
      workspace,
      roster,
    );
    if (resolution.state === 'wait') {
      if (facilityId !== requestedFacilityId) setFacilityId(requestedFacilityId);
      return;
    }

    handledDeepLink.current = key;
    const cleaned = new URLSearchParams(searchParams);
    cleaned.delete('facility_id');
    cleaned.delete('placement_enrollment_id');
    setSearchParams(cleaned, { replace: true });
    if (resolution.state === 'invalid') {
      setDeepLinkNotice(resolution.message);
      setPlacementEnrollmentId('');
      setPlacementReviewOpen(false);
      return;
    }
    if (!isOwner) {
      setDeepLinkNotice('Your current role can view rooms but cannot approve enrollment placement.');
      return;
    }
    setFacilityId(resolution.facilityId);
    setPlacementEnrollmentId(resolution.enrollmentId);
    setPlacementReviewOpen(true);
    setDeepLinkNotice('Opened the exact unassigned enrollment from record readiness.');
  }, [facilityId, isOwner, roster, searchParams, setSearchParams, status, workspace]);

  const rooms = useMemo(
    () =>
      (workspace?.rooms || []).filter(
        (item) => !facilityId || item.facility_id === facilityId,
      ),
    [workspace, facilityId],
  );
  const programs = useMemo(
    () =>
      (workspace?.programs || []).filter(
        (item) => !facilityId || item.facility_id === facilityId,
      ),
    [workspace, facilityId],
  );
  const remainingProgramTypes = missingProgramTypes(
    workspace?.programs || [],
    facilityId,
  );
  const programTypesComplete =
    Boolean(facilityId) && remainingProgramTypes.length === 0;
  const activePrograms = programs.filter((item) => item.is_active);
  const roomCreationBlocked =
    Boolean(facilityId) && activePrograms.length === 0;
  const capacity = rooms
    .filter((item) => item.is_active)
    .reduce((sum, item) => sum + item.capacity, 0);
  const selectedRoom =
    workspace?.rooms.find(
      (item) => item.id === selectedRoomId && item.facility_id === facilityId,
    ) || null;
  const activeFacility =
    workspace?.facilities.find((item) => item.id === facilityId) || null;
  const liveMode =
    requestedWorkspaceView === "live" &&
    liveCapabilityPhase === "enabled" &&
    Boolean(liveCapability);
  const requestedLiveExceptionId = liveMode
    ? searchParams.get("exception") || undefined
    : undefined;
  const requestedLiveRoomId = liveMode
    ? searchParams.get("room_id") || undefined
    : undefined;

  const setWorkspaceMode = (mode: "configuration" | "live") => {
    const next = new URLSearchParams(searchParams);
    if (mode === "live" && liveCapability) {
      next.set("view", "live");
      if (facilityId) next.set("facility_id", facilityId);
    } else {
      next.delete("view");
      next.delete("exception");
      next.delete("room_id");
      next.delete("facility_id");
    }
    setSearchParams(next, { replace: true });
  };

  const applyLiveActionTarget = useCallback(
    (target: RoomExceptionActionTarget) => {
      if (
        !workspace?.facilities.some(
          (facility) => facility.id === target.facility_id,
        )
      ) {
        setDeepLinkNotice(
          "That live-operations target is outside the loaded facility directory.",
        );
        return;
      }
      setFacilityId(target.facility_id);
      const next = new URLSearchParams(searchParams);
      next.set("view", "live");
      next.set("facility_id", target.facility_id);
      next.set("exception", target.exception_id);
      if (target.room_id) next.set("room_id", target.room_id);
      else next.delete("room_id");
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams, workspace?.facilities],
  );

  const saved = () => {
    setEditor(null);
    setVersion((value) => value + 1);
  };

  return (
    <Page>
      <Header>
        <div>
          <Eyebrow>
            <BuildingOffice2Icon width={14} /> Care environment
          </Eyebrow>
          <h1>Rooms & programs.</h1>
          <p>
            Define the physical care lanes that connect licensing capacity,
            child enrollment, and dependable daily attendance.
          </p>
        </div>
        {!liveMode && <HeaderActions>
          <ActionButton
            onClick={() => { setPlacementEnrollmentId(''); setPlacementReviewOpen(true); }}
            disabled={!workspace?.facilities.length || !isOwner || !facilityId}
          >
            <SparklesIcon /> Review placements
          </ActionButton>
          <ActionButton
            title={
              programTypesComplete
                ? "This facility already has both Daycare and OSC programs."
                : remainingProgramTypes.length === 1
                  ? `Add ${PROGRAM_TYPE_LABELS[remainingProgramTypes[0]]}`
                  : "Add a licensed program"
            }
            onClick={() => setEditor({ kind: "program", value: null })}
            disabled={
              !workspace?.facilities.length || !isOwner || programTypesComplete
            }
          >
            {programTypesComplete ? <CheckCircleIcon /> : <PlusIcon />}{" "}
            {programTypesComplete
              ? "Daycare & OSC added"
              : remainingProgramTypes.length === 1
                ? `Add ${PROGRAM_TYPE_LABELS[remainingProgramTypes[0]]}`
                : "Add program"}
          </ActionButton>
          <ActionButton
            $variant="primary"
            title={
              roomCreationBlocked
                ? "Create or activate a program before adding a room."
                : "Add room"
            }
            onClick={() => setEditor({ kind: "room", value: null })}
            disabled={
              !workspace?.facilities.length || !isOwner || roomCreationBlocked
            }
          >
            {roomCreationBlocked ? <ExclamationTriangleIcon /> : <PlusIcon />}{" "}
            {roomCreationBlocked ? "Activate a program first" : "Add room"}
          </ActionButton>
        </HeaderActions>}
      </Header>
      {deepLinkNotice && <FormNotice role="status">{deepLinkNotice}</FormNotice>}
      {status === "idle" && (
        <Gate $accent="amber">
          <div>
            <ExclamationTriangleIcon />
            <h2>Rooms are safely locked.</h2>
            <p>
              CareSync must verify the signed-in organization before loading or
              changing care spaces.
            </p>
          </div>
        </Gate>
      )}
      {status === "loading" && (
        <Gate $accent="cyan" aria-busy="true">
          <div>
            <ArrowPathIcon />
            <h2>Loading the care environment.</h2>
            <p>
              CareSync is verifying facilities, programs, and rooms inside your
              organization.
            </p>
          </div>
        </Gate>
      )}
      {status === "error" && (
        <Gate $accent="amber">
          <div>
            <ExclamationTriangleIcon />
            <h2>Rooms stayed unchanged.</h2>
            <p>{error}</p>
            <ActionButton onClick={() => setVersion((value) => value + 1)}>
              <ArrowPathIcon /> Try again
            </ActionButton>
          </div>
        </Gate>
      )}
      {status === "ready" && workspace && (
        <>
          {session.user && liveCapabilityPhase !== "enabled" && (
            <RoomSafetyActivationCard
              organizationId={organizationId}
              actorUserId={session.user.id}
              canActivate={canActivateLiveOperations}
              onActivated={(capability, activatedFacilityCount) => {
                setLiveCapability(capability);
                setLiveCapabilityPhase("enabled");
                setDeepLinkNotice(
                  `Live room operations activated across ${activatedFacilityCount} ${
                    activatedFacilityCount === 1 ? "facility" : "facilities"
                  }.`,
                );
                setWorkspaceMode("live");
              }}
            />
          )}
          <Toolbar $accent="plasma">
            <div>
              <Eyebrow>
                <BuildingOffice2Icon width={14} /> Active facility
              </Eyebrow>
            </div>
            {liveCapabilityPhase === "enabled" && liveCapability && (
              <ModeSwitch aria-label="Rooms workspace mode">
                <button
                  type="button"
                  aria-pressed={!liveMode}
                  onClick={() => setWorkspaceMode("configuration")}
                >
                  <Cog6ToothIcon /> Configuration
                </button>
                <button
                  type="button"
                  aria-pressed={liveMode}
                  onClick={() => setWorkspaceMode("live")}
                >
                  <SignalIcon /> Live operations
                </button>
              </ModeSwitch>
            )}
            <select
              aria-label="Choose facility"
              value={facilityId}
              onChange={(event) => {
                const nextFacilityId = event.target.value;
                setFacilityId(nextFacilityId);
                setSelectedRoomId("");
                if (liveMode) {
                  const next = new URLSearchParams(searchParams);
                  next.set("view", "live");
                  next.set("facility_id", nextFacilityId);
                  next.delete("exception");
                  next.delete("room_id");
                  setSearchParams(next, { replace: true });
                }
              }}
            >
              {workspace.facilities.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                  {item.city ? ` · ${item.city}` : ""}
                </option>
              ))}
            </select>
          </Toolbar>
          {!liveMode && <>
          <Metrics>
            <Metric $accent="plasma">
              <span>
                <RectangleGroupIcon /> Rooms
              </span>
              <strong>{rooms.filter((item) => item.is_active).length}</strong>
              <small>active care rooms</small>
            </Metric>
            <Metric $accent="cyan">
              <span>
                <UserGroupIcon /> Configured room places
              </span>
              <strong>{capacity}</strong>
              <small>Across active Daycare and OSC programs</small>
            </Metric>
            <Metric $accent="amber">
              <span>
                <Squares2X2Icon /> Programs
              </span>
              <strong>
                {programs.filter((item) => item.is_active).length}
              </strong>
              <small>active care programs</small>
            </Metric>
          </Metrics>
          <Workspace>
            <Section $accent="cyan">
              <SectionHeader>
                <div>
                  <h2>Care rooms</h2>
                  <p>
                    Select a room to view its verified roster and manage child
                    placement.
                  </p>
                </div>
                <StatusChip
                  $tone={rosterState === "error" ? "warning" : "info"}
                >
                  {rosterState === "ready"
                    ? `${roster?.unassigned_children.length || 0} unassigned`
                    : rosterState === "error"
                      ? "Roster needs retry"
                      : `${rooms.length} configured`}
                </StatusChip>
              </SectionHeader>
              {rooms.length ? (
                <RoomGrid>
                  {rooms.map((roomItem) => {
                    const programItem = workspace.programs.find(
                      (item) => item.id === roomItem.program_id,
                    );
                    const rosterEntry = roster?.rooms.find(
                      (entry) => entry.room_id === roomItem.id,
                    );
                    const occupancy =
                      rosterEntry?.occupancy ?? roomItem.enrolled_children;
                    const capacityPercent =
                      occupancy === undefined
                        ? 0
                        : Math.min(
                            100,
                            Math.round((occupancy / roomItem.capacity) * 100),
                          );
                    return (
                      <RoomCard
                        key={roomItem.id}
                        $selected={selectedRoomId === roomItem.id}
                      >
                        <RoomOpenButton
                          type="button"
                          onClick={() => setSelectedRoomId(roomItem.id)}
                          aria-haspopup="dialog"
                          aria-label={`Open ${roomItem.name} roster`}
                        >
                          <RoomTop>
                            <div>
                              <h3>{roomItem.name}</h3>
                              <p>
                                {programItem
                                  ? `${programItem.name} · ${formatProgramType(programItem.program_type)}`
                                  : "Program needs review"}
                                {roomItem.age_group
                                  ? ` · ${roomItem.age_group}`
                                  : ""}
                              </p>
                            </div>
                          </RoomTop>
                          <RoomStats>
                            <span>
                              <UserGroupIcon />{" "}
                              {occupancy === undefined ? "—" : occupancy}/
                              {roomItem.capacity} enrolled
                            </span>
                            <span>
                              <CheckCircleIcon />{" "}
                              {roomItem.is_active ? "Active" : "Inactive"}
                            </span>
                          </RoomStats>
                          <CapacityTrack aria-hidden="true">
                            <span style={{ width: `${capacityPercent}%` }} />
                          </CapacityTrack>
                        </RoomOpenButton>
                        <TinyButton
                          type="button"
                          disabled={!isOwner}
                          onClick={() =>
                            setEditor({ kind: "room", value: roomItem })
                          }
                          aria-label={`Edit ${roomItem.name}`}
                        >
                          <PencilSquareIcon />
                        </TinyButton>
                      </RoomCard>
                    );
                  })}
                </RoomGrid>
              ) : (
                <Empty>
                  <div>
                    <RectangleGroupIcon />
                    <h3>No rooms at this facility.</h3>
                    <p>
                      Create the first room before enrolling children or
                      recording attendance.
                    </p>
                  </div>
                </Empty>
              )}
            </Section>
            <Section $accent="plasma">
              <SectionHeader>
                <div>
                  <h2>Programs</h2>
                  <p>Licensed Daycare and OSC services.</p>
                </div>
              </SectionHeader>
              {programs.length ? (
                <ProgramList>
                  {programs.map((programItem) => (
                    <ProgramRow
                      type="button"
                      key={programItem.id}
                      disabled={!isOwner}
                      onClick={() =>
                        setEditor({ kind: "program", value: programItem })
                      }
                    >
                      <Squares2X2Icon />
                      <div>
                        <strong>{programItem.name}</strong>
                        <small>
                          {formatProgramType(programItem.program_type)} ·{" "}
                          {programItem.capacity} places
                        </small>
                      </div>
                      <PencilSquareIcon width={16} />
                    </ProgramRow>
                  ))}
                </ProgramList>
              ) : (
                <Empty>
                  <div>
                    <Squares2X2Icon />
                    <h3>No programs yet.</h3>
                    <p>
                      Add the licensed Daycare or OSC service this facility
                      operates, then assign rooms to it.
                    </p>
                  </div>
                </Empty>
              )}
            </Section>
          </Workspace>
          </>}
          {liveMode &&
            liveCapability &&
            activeFacility &&
            session.user && (
              <RoomSafetyLiveWorkspace
                organizationId={organizationId}
                actorUserId={session.user.id}
                facilityId={activeFacility.id}
                facilityTimezone={activeFacility.timezone}
                rooms={workspace.rooms}
                capability={liveCapability}
                requestedExceptionId={requestedLiveExceptionId}
                requestedRoomId={requestedLiveRoomId}
                onOpenRoster={(roomId) => setSelectedRoomId(roomId)}
                onActionTarget={applyLiveActionTarget}
              />
            )}
        </>
      )}
      {editor && workspace && organizationId && (
        <RoomEditor
          editor={editor}
          workspace={workspace}
          organizationId={organizationId}
          defaultFacility={facilityId || workspace.facilities[0]?.id || ""}
          onClose={() => setEditor(null)}
          onSaved={saved}
        />
      )}
      {selectedRoom && workspace && organizationId && (
        <RoomRosterPanel
          room={selectedRoom}
          workspace={workspace}
          roster={roster}
          rosterState={rosterState}
          rosterError={rosterError}
          organizationId={organizationId}
          canManage={isOwner}
          onClose={() => setSelectedRoomId("")}
          onRefresh={() => setRosterVersion((value) => value + 1)}
        />
      )}
      {placementReviewOpen && workspace && organizationId && facilityId && (
        <RoomPlacementReviewDialog
          facilityId={facilityId}
          organizationId={organizationId}
          workspace={workspace}
          initialEnrollmentId={placementEnrollmentId || undefined}
          onClose={() => { setPlacementReviewOpen(false); setPlacementEnrollmentId(''); }}
          onChanged={() => {
            setVersion((value) => value + 1);
            setRosterVersion((value) => value + 1);
          }}
        />
      )}
    </Page>
  );
}
