"""Captured-source runtime configuration continuity contract."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from scripts import basic_runtime_config as runtime_config

EXTERNAL_JWT = "external-jwt-material-that-is-longer-than-thirty-two-bytes"
INHERITED_JWT = "inherited-jwt-material-that-is-longer-than-thirty-two-bytes"


def _private_env(tmp_path: Path, content: str) -> Path:
    source = tmp_path / ".env"
    source.write_text(content, encoding="utf-8")
    source.chmod(0o600)
    return source


def _without_settings(environment: dict[str, str] | None = None) -> dict[str, str]:
    values = dict(os.environ if environment is None else environment)
    setting_names = {name.casefold() for name in Settings.model_fields}
    return {
        key: value
        for key, value in values.items()
        if key.casefold() not in setting_names
    }


def test_every_settings_field_is_explicitly_classified() -> None:
    assert not (
        runtime_config.RELEASE_CONTROLLED_FIELDS
        & runtime_config.CONTINUITY_FIELDS
    )
    assert frozenset(Settings.model_fields) == (
        runtime_config.RELEASE_CONTROLLED_FIELDS
        | runtime_config.CONTINUITY_FIELDS
    )


def test_protected_env_reader_accepts_private_file_and_rejects_substitution(
    tmp_path: Path,
) -> None:
    source = _private_env(tmp_path, f"JWT_SECRET={EXTERNAL_JWT}\n")

    assert runtime_config.read_protected_env(source) == (
        f"JWT_SECRET={EXTERNAL_JWT}\n"
    )

    source.chmod(0o640)
    with pytest.raises(
        runtime_config.RuntimeConfigError,
        match="owner-private single-link regular file",
    ):
        runtime_config.read_protected_env(source)

    source.unlink()
    outside = _private_env(tmp_path, f"JWT_SECRET={INHERITED_JWT}\n")
    link = tmp_path / "linked.env"
    link.symlink_to(outside)
    with pytest.raises(runtime_config.RuntimeConfigError):
        runtime_config.read_protected_env(link)


def test_protected_env_reader_rejects_metadata_change_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _private_env(tmp_path, f"JWT_SECRET={EXTERNAL_JWT}\n")
    real_fstat = os.fstat
    call_count = 0

    def changed_fstat(file_descriptor: int) -> os.stat_result | SimpleNamespace:
        nonlocal call_count
        result = real_fstat(file_descriptor)
        call_count += 1
        if call_count != 2:
            return result
        return SimpleNamespace(
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_mode=result.st_mode,
            st_uid=result.st_uid,
            st_gid=result.st_gid,
            st_nlink=result.st_nlink,
            st_size=result.st_size,
            st_mtime_ns=result.st_mtime_ns,
            st_ctime_ns=result.st_ctime_ns + 1,
        )

    monkeypatch.setattr(runtime_config.os, "fstat", changed_fstat)

    with pytest.raises(runtime_config.RuntimeConfigError, match="changed while"):
        runtime_config.read_protected_env(source)


def test_environment_wins_and_release_controlled_settings_are_removed(
    tmp_path: Path,
) -> None:
    external_root = tmp_path / "installed-backend"
    external_root.mkdir()
    inherited = _without_settings(
        {
            "PATH": os.environ["PATH"],
            "JWT_SECRET": INHERITED_JWT,
            "DATABASE_HOST": "must-not-cross-the-release-boundary",
            "DATABASE_PASSWORD": "must-not-cross-the-release-boundary",
            "BILLING_MODE": "sandbox",
            "CARESYNC_BASIC_API_HOST": "127.0.0.1",
        }
    )
    inherited.update(
        {
            "JWT_SECRET": INHERITED_JWT,
            "DATABASE_HOST": "must-not-cross-the-release-boundary",
            "DATABASE_PASSWORD": "must-not-cross-the-release-boundary",
            "BILLING_MODE": "sandbox",
        }
    )
    external = {
        "JWT_SECRET": EXTERNAL_JWT,
        "GEMINI_API_KEY": "synthetic-gemini-key",
        "DEEPSEEK_API_KEY": "synthetic-provider-key",
        "DEEPSEEK_MODEL": "synthetic-model",
        "ALLOWED_ORIGINS": "http://localhost:5174",
        "FAMILY_EVIDENCE_SCANNER_PATH": "bin/scanner",
        "DATABASE_PORT": "9999",
        "UNRECOGNIZED_SHELL_CONTROL": "$(false)",
    }

    child = runtime_config.build_runtime_environment(
        inherited=inherited,
        external=external,
        external_backend_root=external_root,
    )

    assert child["JWT_SECRET"] == INHERITED_JWT
    assert child["GEMINI_API_KEY"] == "synthetic-gemini-key"
    assert child["DEEPSEEK_API_KEY"] == "synthetic-provider-key"
    assert child["DEEPSEEK_MODEL"] == "synthetic-model"
    assert child["FAMILY_EVIDENCE_SCANNER_PATH"] == str(
        external_root / "bin" / "scanner"
    )
    assert child["CARESYNC_BASIC_API_HOST"] == "127.0.0.1"
    assert child["CARESYNC_BASIC_RUNTIME_CONFIG_LOADED"] == (
        runtime_config.RUNTIME_CONFIG_MARKER
    )
    assert "DATABASE_HOST" not in child
    assert "DATABASE_PASSWORD" not in child
    assert "DATABASE_PORT" not in child
    assert "BILLING_MODE" not in child
    assert "UNRECOGNIZED_SHELL_CONTROL" not in child


@pytest.mark.parametrize(
    "inherited,external",
    [
        ({}, {}),
        ({"JWT_SECRET": "change-me"}, {"JWT_SECRET": EXTERNAL_JWT}),
        ({"JWT_SECRET": "too-short"}, {}),
    ],
)
def test_missing_or_unsafe_jwt_fails_closed(
    inherited: dict[str, str],
    external: dict[str, str],
    tmp_path: Path,
) -> None:
    with pytest.raises(runtime_config.RuntimeConfigError, match="JWT"):
        runtime_config.build_runtime_environment(
            inherited=_without_settings(inherited) | inherited,
            external=external,
            external_backend_root=tmp_path,
        )


def test_enabled_push_requires_complete_provider_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(runtime_config.RuntimeConfigError, match="push delivery"):
        runtime_config.build_runtime_environment(
            inherited=_without_settings(),
            external={
                "JWT_SECRET": EXTERNAL_JWT,
                "PUSH_DELIVERY_ENABLED": "true",
                "PUSH_PROVIDER": "expo",
                "EXPO_PUSH_ACCESS_TOKEN": "",
            },
            external_backend_root=tmp_path,
        )


def test_dotenv_is_data_not_shell_and_unknown_keys_are_not_forwarded(
    tmp_path: Path,
) -> None:
    shell_effect = tmp_path / "shell-effect"
    text = (
        f"JWT_SECRET={EXTERNAL_JWT}\n"
        f"UNRECOGNIZED=$(/usr/bin/touch {shell_effect})\n"
    )

    parsed = runtime_config.parse_external_env(text)
    child = runtime_config.build_runtime_environment(
        inherited=_without_settings(),
        external=parsed,
        external_backend_root=tmp_path,
    )

    assert not shell_effect.exists()
    assert "UNRECOGNIZED" not in child
    assert child["JWT_SECRET"] == EXTERNAL_JWT


def test_dotenv_parser_failure_never_exposes_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_parse(_stream: object) -> object:
        raise ValueError(EXTERNAL_JWT)

    monkeypatch.setattr(runtime_config, "parse_stream", fail_parse)

    with pytest.raises(runtime_config.RuntimeConfigError) as error:
        runtime_config.parse_external_env(f"JWT_SECRET={EXTERNAL_JWT}\n")

    assert EXTERNAL_JWT not in str(error.value)


def test_exec_bridge_never_emits_configuration_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _private_env(
        tmp_path,
        "\n".join(
            (
                f"JWT_SECRET={EXTERNAL_JWT}",
                "DEEPSEEK_API_KEY=provider-value-that-must-not-be-printed",
                "",
            )
        ),
    )
    inherited = _without_settings()
    monkeypatch.setattr(os, "environ", inherited)
    captured_environment: dict[str, str] = {}

    def refuse_exec(
        _file: str,
        _argv: list[str],
        environment: dict[str, str],
    ) -> None:
        captured_environment.update(environment)
        raise OSError

    monkeypatch.setattr(os, "execvpe", refuse_exec)

    result = runtime_config.main(
        ["exec", "--source-env", str(source), "--", "/usr/bin/true"]
    )

    output = capsys.readouterr()
    assert result == 78
    assert EXTERNAL_JWT not in output.out + output.err
    assert "provider-value-that-must-not-be-printed" not in output.out + output.err
    assert captured_environment["JWT_SECRET"] == EXTERNAL_JWT


def test_launcher_loads_external_config_before_state_lock_without_sourcing_it() -> None:
    project_root = Path(__file__).resolve().parents[2]
    launcher = (project_root / "scripts" / "start-basic.sh").read_text(
        encoding="utf-8"
    )
    bridge_position = launcher.index("basic_runtime_config.py")
    lock_position = launcher.index("basic_reexec_with_state_change_lock")

    assert bridge_position < lock_position
    assert 'external_env="$installed_root/backend/.env"' in launcher
    assert "caresync-basic-runtime-config-v1" in launcher
    assert "source \"$external_env\"" not in launcher
    assert ". \"$external_env\"" not in launcher
