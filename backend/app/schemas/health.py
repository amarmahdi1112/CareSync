"""Health endpoint response contracts."""

from typing import Literal

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    connected: bool
    integrity: str
    database_name: str
    database_filename: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    database: DatabaseHealth
    staff_screening_evidence_upload: Literal["ready", "unavailable"]
