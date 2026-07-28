from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.basic import name_matching as name_matching_api
from app.core.config import Settings
from app.main import create_app
from app.schemas.ai_matching import NameMatchResponse, NameMatchResult


def _settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        enable_advanced_routes=False,
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        **overrides,
    )


def _payload() -> dict:
    return {
        "sourceChildren": [{"id": "source-1", "name": "Amina Noor"}],
        "portalChildren": [{"id": "portal-1", "name": "Amina N."}],
        "excludedPairs": [],
    }


def test_basic_exposes_only_the_narrow_name_matching_ai_route(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        schema = client.get("/openapi.json").json()
    ai_paths = sorted(
        path for path in schema["paths"] if path.startswith("/api/v1/ai")
    )

    assert ai_paths == ["/api/v1/ai/name-matches"]


def test_basic_name_matching_requires_server_side_provider_configuration(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post("/api/v1/ai/name-matches", json=_payload())

    assert response.status_code == 409
    assert response.json()["detail"] == "DeepSeek API key is not configured"


def test_basic_name_matching_forwards_only_bounded_contract_fields(
    tmp_path,
    monkeypatch,
) -> None:
    captured: dict = {}

    def fake_match_child_names_chunked(**kwargs) -> NameMatchResponse:
        captured.update(kwargs)
        return NameMatchResponse(
            model=kwargs["model"],
            threshold=kwargs["threshold"],
            chunkCount=1,
            matches=[
                NameMatchResult(
                    sourceChildId="source-1",
                    portalChildId="portal-1",
                    confidence=0.91,
                    reason="abbreviated family name",
                    accepted=False,
                )
            ],
            acceptedCount=0,
            unresolvedSourceChildIds=["source-1"],
            unresolvedPortalChildIds=["portal-1"],
        )

    monkeypatch.setattr(
        name_matching_api,
        "match_child_names_chunked",
        fake_match_child_names_chunked,
    )
    settings = _settings(
        tmp_path,
        deepseek_api_key="test-only-key",
        deepseek_name_match_chunk_size=17,
        deepseek_name_match_max_provider_calls=41,
        deepseek_name_match_deadline_seconds=73,
    )
    payload = {
        **_payload(),
        "excludedPairs": [
            {"sourceChildId": "source-1", "portalChildId": "portal-1"}
        ],
    }

    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/ai/name-matches", json=payload)

    assert response.status_code == 200
    assert captured["chunk_size"] == 17
    assert captured["max_provider_calls"] == 41
    assert captured["deadline_seconds"] == 73
    assert captured["excluded_pairs"] == {("source-1", "portal-1")}
    assert [child.model_dump() for child in captured["source_children"]] == [
        {"id": "source-1", "name": "Amina Noor"}
    ]
    assert [child.model_dump() for child in captured["portal_children"]] == [
        {"id": "portal-1", "name": "Amina N."}
    ]
    assert "test-only-key" not in response.text
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    ("client_host", "origin", "expected_detail"),
    [
        (
            "192.0.2.10",
            f"chrome-extension://{'a' * 32}",
            "only from this computer",
        ),
        (
            "127.0.0.1",
            "http://127.0.0.1:5174",
            "only to the CareSync browser extension",
        ),
        (
            "127.0.0.1",
            "chrome-extension://not-an-extension-id",
            "only to the CareSync browser extension",
        ),
    ],
)
def test_basic_name_matching_rejects_wrong_peer_or_origin(
    tmp_path,
    client_host: str,
    origin: str,
    expected_detail: str,
) -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        enable_advanced_routes=False,
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        deepseek_api_key="test-only-key",
    )
    with TestClient(
        create_app(settings),
        client=(client_host, 50_000),
    ) as client:
        response = client.post(
            "/api/v1/ai/name-matches",
            json=_payload(),
            headers={"Origin": origin},
        )

    assert response.status_code == 403
    assert expected_detail in response.json()["detail"]


def test_basic_name_matching_allows_loopback_extension_origin_without_calling_provider(
    tmp_path,
    monkeypatch,
) -> None:
    called = False

    def fake_match_child_names_chunked(**kwargs) -> NameMatchResponse:
        nonlocal called
        called = True
        return NameMatchResponse(
            model=kwargs["model"],
            threshold=kwargs["threshold"],
            matches=[],
            acceptedCount=0,
            unresolvedSourceChildIds=["source-1"],
            unresolvedPortalChildIds=["portal-1"],
        )

    monkeypatch.setattr(
        name_matching_api,
        "match_child_names_chunked",
        fake_match_child_names_chunked,
    )
    settings = Settings(
        _env_file=None,
        environment="development",
        enable_advanced_routes=False,
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        deepseek_api_key="test-only-key",
    )
    origin = f"chrome-extension://{'a' * 32}"
    with TestClient(
        create_app(settings),
        client=("127.0.0.1", 50_000),
    ) as client:
        preflight = client.options(
            "/api/v1/ai/name-matches",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        response = client.post(
            "/api/v1/ai/name-matches",
            json=_payload(),
            headers={"Origin": origin},
        )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert response.status_code == 200
    assert called is True


def test_basic_name_matching_keeps_schema_payload_limits(tmp_path) -> None:
    oversized_sources = [
        {"id": f"source-{index}", "name": "Child"}
        for index in range(501)
    ]
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post(
            "/api/v1/ai/name-matches",
            json={
                "sourceChildren": oversized_sources,
                "portalChildren": [{"id": "portal-1", "name": "Child"}],
            },
        )

    assert response.status_code == 422


def test_basic_name_matching_rejects_attendance_data_in_privacy_minimized_payload(
    tmp_path,
    monkeypatch,
) -> None:
    provider_called = False

    def unexpected_provider_call(**_kwargs):
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider must not receive a rejected payload")

    monkeypatch.setattr(
        name_matching_api,
        "match_child_names_chunked",
        unexpected_provider_call,
    )
    with TestClient(
        create_app(_settings(tmp_path, deepseek_api_key="test-only-key"))
    ) as client:
        response = client.post(
            "/api/v1/ai/name-matches",
            json={
                **_payload(),
                "attendanceDates": ["2026-07-01"],
                "sourceChildren": [
                    {
                        "id": "source-1",
                        "name": "Amina Noor",
                        "sessionStart": "08:00",
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert provider_called is False
