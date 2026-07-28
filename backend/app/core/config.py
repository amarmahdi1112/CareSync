"""Typed runtime settings with legacy database-name preservation."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL

BACKEND_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SQLITE_NAME = "caresync.db"
LEGACY_POSTGRES_NAME = "caresync"


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "CareSync Private"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = 3001
    api_prefix: str = "/api/v1"
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )
    extension_origin_regex: str = r"^chrome-extension://[a-p]{32}$"

    database_type: Literal["sqlite", "postgres"] = "sqlite"
    database_path: Path = BACKEND_ROOT / "storage" / LEGACY_SQLITE_NAME
    database_name: str = LEGACY_POSTGRES_NAME
    database_host: str = "localhost"
    database_port: int = 5432
    database_user: str = "postgres"
    database_password: SecretStr = SecretStr("")
    transport_evidence_ingest_user: Literal["caresync_transport_evidence_ingest"] = (
        "caresync_transport_evidence_ingest"
    )
    transport_evidence_ingest_password: SecretStr = SecretStr("")
    database_ssl: bool = False
    database_read_only: bool = True
    enable_advanced_routes: bool = False
    billing_mode: Literal["disabled", "shadow", "sandbox", "manual"] = "disabled"
    billing_sandbox_target_attestation: Literal["", "DISPOSABLE_CARESYNC_BILLING_SANDBOX"] = ""
    billing_sandbox_organization_ids: Annotated[list[UUID], NoDecode] = Field(default_factory=list)
    billing_manual_target_attestation: Literal["", "PRIVATE_LOCAL_MANUAL_BILLING"] = ""
    billing_manual_organization_ids: Annotated[list[UUID], NoDecode] = Field(default_factory=list)
    child_profile_photo_max_bytes: int = Field(
        default=6 * 1024 * 1024,
        ge=64 * 1024,
        le=20 * 1024 * 1024,
    )
    child_profile_photo_max_pixels: int = Field(
        default=25_000_000,
        ge=1_000_000,
        le=100_000_000,
    )
    child_profile_photo_max_edge: int = Field(default=1024, ge=256, le=4096)
    family_evidence_vault_path: Path | None = None
    family_evidence_max_bytes: int = Field(
        default=20 * 1024 * 1024,
        ge=64 * 1024,
        le=50 * 1024 * 1024,
    )
    family_evidence_max_image_pixels: int = Field(
        default=40_000_000,
        ge=1_000_000,
        le=100_000_000,
    )
    family_evidence_max_pdf_pages: int = Field(default=100, ge=1, le=500)
    family_evidence_parser_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    family_evidence_scanner_path: Path | None = None
    family_evidence_scanner_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    family_evidence_scanner_max_definition_age_hours: int = Field(default=168, ge=1, le=720)
    staff_screening_vault_path: Path | None = None
    staff_screening_vault_encryption_key: SecretStr = SecretStr("")
    staff_screening_vault_key_id: str = Field(
        default="local-v1",
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$",
    )
    staff_screening_document_max_bytes: int = Field(
        default=20 * 1024 * 1024,
        ge=64 * 1024,
        le=50 * 1024 * 1024,
    )
    # V2 is retained only as a deprecated emergency rollback option.
    scheduler_engine_version: Literal["v2", "v3"] = "v3"
    jwt_secret: SecretStr = SecretStr("change-me")
    jwt_expires_in: str = "7d"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash"
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_name_match_threshold: float = Field(default=0.92, ge=0.8, le=1.0)
    deepseek_name_match_chunk_size: int = Field(default=20, ge=5, le=50)
    deepseek_name_match_max_provider_calls: int = Field(default=300, ge=1, le=2_000)
    deepseek_name_match_deadline_seconds: float = Field(default=180.0, ge=10.0, le=900.0)
    push_delivery_enabled: bool = False
    push_provider: Literal["disabled", "expo"] = "disabled"
    expo_push_access_token: SecretStr = SecretStr("")
    push_provider_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            origins = (
                json.loads(stripped)
                if stripped.startswith("[")
                else [origin.strip() for origin in stripped.split(",") if origin.strip()]
            )
        else:
            origins = list(value) if value else []
        expanded = list(origins)
        for origin in origins:
            if "localhost" in origin:
                loopback = origin.replace("localhost", "127.0.0.1")
                if loopback not in expanded:
                    expanded.append(loopback)
        return expanded

    @field_validator(
        "billing_sandbox_organization_ids",
        "billing_manual_organization_ids",
        mode="before",
    )
    @classmethod
    def parse_billing_organization_ids(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return (
                json.loads(stripped)
                if stripped.startswith("[")
                else [item.strip() for item in stripped.split(",") if item.strip()]
            )
        return list(value) if value else []

    @field_validator("database_path")
    @classmethod
    def preserve_sqlite_filename(cls, value: Path) -> Path:
        if value.name != LEGACY_SQLITE_NAME:
            raise ValueError(f"SQLite database filename must remain {LEGACY_SQLITE_NAME!r}")
        return value

    @field_validator("database_name")
    @classmethod
    def preserve_postgres_name(cls, value: str) -> str:
        if value != LEGACY_POSTGRES_NAME:
            raise ValueError(f"PostgreSQL database name must remain {LEGACY_POSTGRES_NAME!r}")
        return value

    @property
    def sqlite_path(self) -> Path:
        path = self.database_path
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        return path

    @property
    def database_url(self) -> str | URL:
        if self.database_type == "sqlite":
            path = self.sqlite_path
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{path}"

        return URL.create(
            "postgresql+psycopg",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

    @property
    def transport_evidence_ingest_database_url(self) -> URL | None:
        """Return the isolated 0032 evidence identity URL when explicitly configured."""

        if self.database_type != "postgres":
            return None
        password = self.transport_evidence_ingest_password.get_secret_value()
        if not password or password == self.database_password.get_secret_value():
            return None
        return URL.create(
            "postgresql+psycopg",
            username=self.transport_evidence_ingest_user,
            password=password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

    @property
    def billing_sandbox_target_is_disposable(self) -> bool:
        """Authorize 0033 writes only on an explicit disposable PostgreSQL target."""

        if (
            self.environment != "test"
            or self.database_type != "postgres"
            or self.database_read_only
            or self.billing_sandbox_target_attestation != "DISPOSABLE_CARESYNC_BILLING_SANDBOX"
        ):
            return False
        return (
            self.database_host.casefold() in {"localhost", "127.0.0.1", "::1"}
            and self.database_port >= 1024
            and self.database_port not in {5432, 5433, 5434}
        )

    @property
    def billing_manual_target_is_private_local(self) -> bool:
        """Authorize manual records only on an explicitly attested local PostgreSQL server."""

        return bool(
            self.environment == "development"
            and self.database_type == "postgres"
            and not self.database_read_only
            and self.database_host.casefold() in {"localhost", "127.0.0.1", "::1"}
            and self.database_port >= 1024
            and self.billing_manual_target_attestation == "PRIVATE_LOCAL_MANUAL_BILLING"
        )

    def billing_organization_is_allowlisted(self, organization_id: UUID) -> bool:
        """Require an explicit mode-specific tenant allowlist."""

        if self.billing_mode == "manual":
            return organization_id in set(self.billing_manual_organization_ids)
        return organization_id in set(self.billing_sandbox_organization_ids)

    @property
    def resolved_family_evidence_vault_path(self) -> Path:
        """Return the lexical private root without following symbolic links.

        The vault layer opens every component with ``O_NOFOLLOW``.  Calling
        ``Path.resolve`` here would erase the very symlink evidence that layer
        must reject and would let a symlink be retargeted after configuration.
        """

        configured = self.family_evidence_vault_path
        path = configured or (
            Path.home()
            / "Library"
            / "Application Support"
            / "CareSync Basic"
            / "private-family-authority-vault"
        )
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        path = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
        backend_root = Path(os.path.abspath(os.fspath(BACKEND_ROOT)))
        if path == backend_root or backend_root in path.parents:
            raise ValueError("Family evidence vault must remain outside the backend source tree")
        public_uploads = Path(os.path.abspath(os.fspath(self.sqlite_path.parent / "uploads")))
        if path == public_uploads or public_uploads in path.parents:
            raise ValueError("Family evidence vault must remain outside the web uploads directory")
        return path

    @property
    def resolved_staff_screening_vault_path(self) -> Path:
        """Return the private HR-vault root without resolving symlink components."""

        configured = self.staff_screening_vault_path
        path = configured or (
            Path.home()
            / "Library"
            / "Application Support"
            / "CareSync Basic"
            / "private-staff-screening-vault"
        )
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        path = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
        backend_root = Path(os.path.abspath(os.fspath(BACKEND_ROOT)))
        if path == backend_root or backend_root in path.parents:
            raise ValueError("Staff screening vault must remain outside the backend source tree")
        public_uploads = Path(os.path.abspath(os.fspath(self.sqlite_path.parent / "uploads")))
        if path == public_uploads or public_uploads in path.parents:
            raise ValueError("Staff screening vault must remain outside the web uploads directory")
        family_vault = self.resolved_family_evidence_vault_path
        if path == family_vault or path in family_vault.parents or family_vault in path.parents:
            raise ValueError("Staff screening and family evidence vaults must not overlap")
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
