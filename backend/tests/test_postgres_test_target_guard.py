"""The opt-in PostgreSQL harness must never accept retained or remote state."""

from __future__ import annotations

import pytest

from tests.conftest import _guard_disposable_postgres_target


def test_disposable_postgres_guard_allows_an_explicit_loopback_scratch_port(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
    monkeypatch.setenv("BASIC_POSTGRES_TEST_PORT", "55433")
    _guard_disposable_postgres_target()


@pytest.mark.parametrize("port", ["5432", "5433", "5434", "0", "65536"])
def test_disposable_postgres_guard_rejects_retained_or_invalid_ports(
    monkeypatch,
    port: str,
) -> None:
    monkeypatch.setenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
    monkeypatch.setenv("BASIC_POSTGRES_TEST_PORT", port)
    with pytest.raises(RuntimeError):
        _guard_disposable_postgres_target()


def test_disposable_postgres_guard_rejects_remote_hosts(monkeypatch) -> None:
    monkeypatch.setenv("BASIC_POSTGRES_TEST_HOST", "database.example.test")
    monkeypatch.setenv("BASIC_POSTGRES_TEST_PORT", "55433")
    with pytest.raises(RuntimeError):
        _guard_disposable_postgres_target()


def test_disposable_postgres_guard_rejects_non_numeric_port(monkeypatch) -> None:
    monkeypatch.setenv("BASIC_POSTGRES_TEST_HOST", "localhost")
    monkeypatch.setenv("BASIC_POSTGRES_TEST_PORT", "not-a-port")
    with pytest.raises(RuntimeError):
        _guard_disposable_postgres_target()


def test_disposable_postgres_guard_allows_migration_tests_on_scratch_port(
    monkeypatch,
) -> None:
    monkeypatch.delenv("BASIC_POSTGRES_TEST_PORT", raising=False)
    monkeypatch.setenv("BASIC_POSTGRES_TEST_HOST", "::1")
    monkeypatch.setenv("BASIC_POSTGRES_MIGRATION_TEST_PORT", "55434")
    _guard_disposable_postgres_target()


@pytest.mark.parametrize("port", ["5432", "5433", "5434", "0", "65536"])
def test_disposable_postgres_guard_protects_migration_test_target(
    monkeypatch,
    port: str,
) -> None:
    monkeypatch.delenv("BASIC_POSTGRES_TEST_PORT", raising=False)
    monkeypatch.setenv("BASIC_POSTGRES_TEST_HOST", "127.0.0.1")
    monkeypatch.setenv("BASIC_POSTGRES_MIGRATION_TEST_PORT", port)
    with pytest.raises(RuntimeError):
        _guard_disposable_postgres_target()


def test_disposable_postgres_guard_rejects_non_numeric_migration_port(
    monkeypatch,
) -> None:
    monkeypatch.delenv("BASIC_POSTGRES_TEST_PORT", raising=False)
    monkeypatch.setenv("BASIC_POSTGRES_TEST_HOST", "localhost")
    monkeypatch.setenv("BASIC_POSTGRES_MIGRATION_TEST_PORT", "not-a-port")
    with pytest.raises(RuntimeError):
        _guard_disposable_postgres_target()
