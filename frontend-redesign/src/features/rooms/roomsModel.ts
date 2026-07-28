import {
  PROGRAM_TYPES,
  isProgramType,
  type ProgramType,
} from "../../models/programTypes";
import type {
  ProgramMutation,
  ProgramRecord,
  RoomMutation,
  RoomRecord,
} from "./roomsApi";

export function missingProgramTypes(
  programs: Array<Pick<ProgramRecord, "facility_id" | "program_type">>,
  facilityId: string,
): ProgramType[] {
  const configured = new Set(
    programs
      .filter((program) => program.facility_id === facilityId)
      .map((program) => program.program_type),
  );
  return PROGRAM_TYPES.filter((type) => !configured.has(type));
}

export function editableProgramTypes(
  programs: Array<Pick<ProgramRecord, "facility_id" | "program_type">>,
  facilityId: string,
  currentType?: ProgramType,
): ProgramType[] {
  const missing = missingProgramTypes(programs, facilityId);
  return currentType
    ? PROGRAM_TYPES.filter(
        (type) => type === currentType || missing.includes(type),
      )
    : missing;
}

export function validateProgram(input: ProgramMutation): string[] {
  const errors: string[] = [];
  if (!input.facility_id) errors.push("Choose a facility.");
  if (!input.name.trim()) errors.push("Enter a program name.");
  if (!isProgramType(input.program_type))
    errors.push("Choose Daycare or OSC as the licensed program type.");
  if (!Number.isInteger(input.capacity) || input.capacity < 0) {
    errors.push("Program capacity must be a non-negative whole number.");
  }
  if (input.minimum_age_months !== null && input.minimum_age_months < 0) {
    errors.push("Minimum age cannot be negative.");
  }
  if (input.maximum_age_months !== null && input.maximum_age_months < 0) {
    errors.push("Maximum age cannot be negative.");
  }
  if (
    input.minimum_age_months !== null &&
    input.maximum_age_months !== null &&
    input.maximum_age_months < input.minimum_age_months
  ) {
    errors.push("Maximum age must be greater than or equal to minimum age.");
  }
  return errors;
}

export function activeRoomCapacity(
  rooms: RoomRecord[],
  programId: string,
  excludeRoomId?: string,
): number {
  return rooms
    .filter(
      (room) =>
        room.is_active &&
        room.program_id === programId &&
        room.id !== excludeRoomId,
    )
    .reduce((total, room) => total + room.capacity, 0);
}

export function validateProgramInWorkspace(
  input: ProgramMutation,
  rooms: RoomRecord[],
  editingProgramId?: string,
): string[] {
  const errors = validateProgram(input);
  if (!editingProgramId) return errors;
  const assignedRooms = rooms.filter(
    (room) => room.is_active && room.program_id === editingProgramId,
  );
  const assignedCapacity = assignedRooms.reduce(
    (total, room) => total + room.capacity,
    0,
  );
  if (Number.isInteger(input.capacity) && input.capacity < assignedCapacity) {
    errors.push(
      `Program capacity cannot be lower than the ${assignedCapacity} places assigned across active rooms.`,
    );
  }
  if (!input.is_active && assignedRooms.length) {
    errors.push(
      `Move or deactivate the ${assignedRooms.length} active assigned room${assignedRooms.length === 1 ? "" : "s"} before deactivating this program.`,
    );
  }
  return errors;
}

export function normalizedRoomName(value: string): string {
  return value
    .normalize("NFKC")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase("en-CA");
}

export function validateRoom(input: RoomMutation): string[] {
  const errors: string[] = [];
  if (!input.facility_id) errors.push("Choose a facility.");
  if (!input.program_id) errors.push("Choose an active program.");
  if (!input.name.trim()) errors.push("Enter a room name.");
  if (!Number.isInteger(input.capacity) || input.capacity < 1) {
    errors.push("Room capacity must be a whole number greater than zero.");
  }
  if (input.minimum_age_months === null || input.maximum_age_months === null) {
    errors.push(
      "Enter the room minimum and maximum ages for automatic DOB placement.",
    );
  }
  if (
    input.minimum_age_months !== null &&
    (!Number.isInteger(input.minimum_age_months) ||
      input.minimum_age_months < 0)
  ) {
    errors.push("Minimum room age must be a non-negative whole number.");
  }
  if (
    input.maximum_age_months !== null &&
    (!Number.isInteger(input.maximum_age_months) ||
      input.maximum_age_months < 0)
  ) {
    errors.push("Maximum room age must be a non-negative whole number.");
  }
  if (
    input.minimum_age_months !== null &&
    input.maximum_age_months !== null &&
    input.maximum_age_months < input.minimum_age_months
  ) {
    errors.push(
      "Maximum room age must be greater than or equal to minimum age.",
    );
  }
  return errors;
}

export function validateRoomInWorkspace(
  input: RoomMutation,
  programs: ProgramRecord[],
  rooms: RoomRecord[],
  editingRoomId?: string,
): string[] {
  const errors = validateRoom(input);
  const targetProgram = programs.find(
    (program) =>
      program.id === input.program_id &&
      program.facility_id === input.facility_id &&
      program.is_active,
  );
  if (input.program_id && !targetProgram)
    errors.push("Choose an active program at this facility.");

  const requestedName = normalizedRoomName(input.name);
  if (
    requestedName &&
    rooms.some(
      (room) =>
        room.id !== editingRoomId &&
        room.facility_id === input.facility_id &&
        normalizedRoomName(room.name) === requestedName,
    )
  ) {
    errors.push("A room with this name already exists at the facility.");
  }

  if (
    input.is_active &&
    targetProgram &&
    Number.isInteger(input.capacity) &&
    input.capacity > 0
  ) {
    const existingCapacity = activeRoomCapacity(
      rooms,
      targetProgram.id,
      editingRoomId,
    );
    if (existingCapacity + input.capacity > targetProgram.capacity) {
      errors.push(
        `Active room capacity would be ${existingCapacity + input.capacity}, above ${targetProgram.name}’s ${targetProgram.capacity}-place capacity.`,
      );
    }
  }
  return errors;
}
