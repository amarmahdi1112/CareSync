"""Canonical licensed-program categories for the CareSync Basic domain."""

from __future__ import annotations

from typing import Final, Literal

DAYCARE_PROGRAM_TYPE: Final = "daycare"
OUT_OF_SCHOOL_CARE_PROGRAM_TYPE: Final = "out_of_school_care"

ProgramType = Literal["daycare", "out_of_school_care"]
PROGRAM_TYPES: Final[frozenset[str]] = frozenset(
    {DAYCARE_PROGRAM_TYPE, OUT_OF_SCHOOL_CARE_PROGRAM_TYPE}
)
