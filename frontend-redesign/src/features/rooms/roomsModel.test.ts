import { describe, expect, it } from "vitest";
import {
  activeRoomCapacity,
  editableProgramTypes,
  missingProgramTypes,
  normalizedRoomName,
  validateProgram,
  validateProgramInWorkspace,
  validateRoom,
  validateRoomInWorkspace,
} from "./roomsModel";
import type { ProgramMutation, ProgramRecord, RoomRecord } from "./roomsApi";

const daycare: ProgramRecord = {
  id: "program-1",
  organization_id: "org-1",
  facility_id: "facility-1",
  name: "Daycare",
  program_type: "daycare",
  capacity: 20,
  minimum_age_months: null,
  maximum_age_months: null,
  is_active: true,
};

function room(
  id: string,
  name: string,
  capacity: number,
  overrides: Partial<RoomRecord> = {},
): RoomRecord {
  return {
    id,
    organization_id: "org-1",
    facility_id: "facility-1",
    program_id: "program-1",
    name,
    capacity,
    age_group: null,
    minimum_age_months: 0,
    maximum_age_months: 143,
    is_active: true,
    ...overrides,
  };
}

describe("rooms model", () => {
  it("requires a program for every room mutation", () => {
    const valid = {
      facility_id: "facility-1",
      program_id: "program-1",
      name: "Infant North",
      capacity: 12,
      age_group: "Infant",
      minimum_age_months: 0,
      maximum_age_months: 18,
      is_active: true,
    };
    expect(validateRoom(valid)).toEqual([]);
    expect(validateRoom({ ...valid, program_id: "" })).toContain(
      "Choose an active program.",
    );
  });

  it("requires a complete inclusive room age range for DOB matching", () => {
    const base = {
      facility_id: "facility-1",
      program_id: "program-1",
      name: "Infant",
      capacity: 5,
      age_group: "Infant",
      is_active: true,
    };
    expect(
      validateRoom({ ...base, minimum_age_months: 0, maximum_age_months: 18 }),
    ).toEqual([]);
    expect(
      validateRoom({
        ...base,
        minimum_age_months: 0,
        maximum_age_months: null,
      }),
    ).toContain(
      "Enter the room minimum and maximum ages for automatic DOB placement.",
    );
    expect(
      validateRoom({
        ...base,
        minimum_age_months: null,
        maximum_age_months: null,
      }),
    ).toContain(
      "Enter the room minimum and maximum ages for automatic DOB placement.",
    );
    expect(
      validateRoom({ ...base, minimum_age_months: 19, maximum_age_months: 18 }),
    ).toContain(
      "Maximum room age must be greater than or equal to minimum age.",
    );
  });

  it("normalizes room names and rejects case/whitespace-equivalent duplicates", () => {
    expect(normalizedRoomName("  Infant\u00a0  North ")).toBe("infant north");
    const errors = validateRoomInWorkspace(
      {
        facility_id: "facility-1",
        program_id: "program-1",
        name: " INFANT   NORTH ",
        capacity: 5,
        age_group: null,
        minimum_age_months: 0,
        maximum_age_months: 18,
        is_active: true,
      },
      [daycare],
      [room("room-1", "Infant North", 8)],
    );
    expect(errors).toContain(
      "A room with this name already exists at the facility.",
    );
  });

  it("checks active aggregate capacity and excludes the room being edited", () => {
    const rooms = [
      room("room-edit", "Infant", 12),
      room("room-other", "Toddler", 5),
    ];
    expect(activeRoomCapacity(rooms, "program-1", "room-edit")).toBe(5);
    expect(
      validateRoomInWorkspace(
        {
          facility_id: "facility-1",
          program_id: "program-1",
          name: "Infant",
          capacity: 15,
          age_group: null,
          minimum_age_months: 0,
          maximum_age_months: 18,
          is_active: true,
        },
        [daycare],
        rooms,
        "room-edit",
      ),
    ).toEqual([]);
    expect(
      validateRoomInWorkspace(
        {
          facility_id: "facility-1",
          program_id: "program-1",
          name: "Infant",
          capacity: 16,
          age_group: null,
          minimum_age_months: 0,
          maximum_age_months: 18,
          is_active: true,
        },
        [daycare],
        rooms,
        "room-edit",
      ).join(" "),
    ).toContain("above Daycare’s 20-place capacity");
  });

  it("requires the selected room program to be active and in the same facility", () => {
    const errors = validateRoomInWorkspace(
      {
        facility_id: "facility-1",
        program_id: "program-1",
        name: "Infant",
        capacity: 5,
        age_group: null,
        minimum_age_months: 0,
        maximum_age_months: 18,
        is_active: true,
      },
      [{ ...daycare, is_active: false }],
      [],
    );
    expect(errors).toContain("Choose an active program at this facility.");
  });

  it("rejects an inverted program age window", () => {
    expect(
      validateProgram({
        facility_id: "facility-1",
        name: "Preschool",
        program_type: "daycare",
        capacity: 24,
        minimum_age_months: 60,
        maximum_age_months: 36,
        is_active: true,
      }),
    ).toContain("Maximum age must be greater than or equal to minimum age.");
  });

  it("prevents capacity reduction and deactivation while active rooms are assigned", () => {
    const mutation: ProgramMutation = {
      facility_id: "facility-1",
      name: "Daycare",
      program_type: "daycare",
      capacity: 16,
      minimum_age_months: null,
      maximum_age_months: null,
      is_active: false,
    };
    const errors = validateProgramInWorkspace(
      mutation,
      [room("room-1", "Infant", 12), room("room-2", "Toddler", 5)],
      "program-1",
    );
    expect(errors.join(" ")).toContain("cannot be lower than the 17 places");
    expect(errors.join(" ")).toContain("before deactivating this program");
  });

  it("offers only program types missing from the selected facility", () => {
    const programs = [
      { facility_id: "facility-1", program_type: "daycare" as const },
      {
        facility_id: "facility-2",
        program_type: "out_of_school_care" as const,
      },
    ];
    expect(missingProgramTypes(programs, "facility-1")).toEqual([
      "out_of_school_care",
    ]);
    expect(
      missingProgramTypes(
        [
          ...programs,
          {
            facility_id: "facility-1",
            program_type: "out_of_school_care" as const,
          },
        ],
        "facility-1",
      ),
    ).toEqual([]);
  });

  it("keeps the current type editable without offering a duplicate type", () => {
    const programs = [
      { facility_id: "facility-1", program_type: "daycare" as const },
      {
        facility_id: "facility-1",
        program_type: "out_of_school_care" as const,
      },
    ];
    expect(editableProgramTypes(programs, "facility-1", "daycare")).toEqual([
      "daycare",
    ]);
  });
});
