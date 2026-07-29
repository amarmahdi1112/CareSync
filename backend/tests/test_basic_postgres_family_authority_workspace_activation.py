"""Opt-in PostgreSQL proofs for the A2-activated family-authority workspace.

The A1 command surface remains available before activation, but the current
workspace projection intentionally fails closed until the exact A2 boundary.
These proofs therefore run only on an explicitly selected disposable
PostgreSQL database at ``0029A2_authority_activation``.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import create_app
from tests.test_basic_postgres_family_authority_api import (
    RUNTIME_ROLE,
    PostgresHarness,
    _assert_workspace_and_exact_replays_share_the_family_command_boundary,
    _assert_workspace_projection_writes_nothing_and_authority_is_role_and_tenant_private,
    _settings,
    _url,
)

TEST_PORT = os.getenv("BASIC_POSTGRES_TEST_PORT")
CURRENT_REVISION = "0029A2_authority_activation"

pytestmark = pytest.mark.skipif(
    not TEST_PORT,
    reason="BASIC_POSTGRES_TEST_PORT must identify a disposable PostgreSQL cluster",
)


@pytest.fixture
def activated_postgres_harness() -> PostgresHarness:
    admin = create_engine(_url("postgres"))
    with admin.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == CURRENT_REVISION
        )

    application = create_app(_settings())
    with TestClient(application, raise_server_exceptions=False) as client:
        with application.state.database.engine.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == (
                RUNTIME_ROLE
            )
        yield PostgresHarness(admin=admin, application=application, client=client)
    admin.dispose()


def test_workspace_projection_writes_nothing_and_authority_is_role_and_tenant_private(
    activated_postgres_harness: PostgresHarness,
) -> None:
    _assert_workspace_projection_writes_nothing_and_authority_is_role_and_tenant_private(
        activated_postgres_harness
    )


def test_workspace_and_exact_replays_share_the_family_command_boundary(
    activated_postgres_harness: PostgresHarness,
) -> None:
    _assert_workspace_and_exact_replays_share_the_family_command_boundary(
        activated_postgres_harness
    )
