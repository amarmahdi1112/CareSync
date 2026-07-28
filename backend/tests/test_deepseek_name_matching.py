import json

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import ai as ai_api
from app.core.config import Settings
from app.main import create_app
from app.schemas.ai_matching import (
    NameCandidate,
    NameMatchRequest,
    NameMatchResponse,
    NameMatchResult,
)
from app.services import deepseek


class FakeDeepSeekResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeDeepSeekResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_name_matching_requires_a_deepseek_key(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/ai/name-matches",
            json={
                "sourceChildren": [{"id": "source-1", "name": "Amina Noor"}],
                "portalChildren": [{"id": "portal-1", "name": "Amina N."}],
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "DeepSeek API key is not configured"


def test_name_matching_api_passes_configured_whole_request_limits(
    tmp_path,
    monkeypatch,
) -> None:
    captured: dict = {}

    def fake_match_child_names_chunked(**kwargs) -> NameMatchResponse:
        captured.update(kwargs)
        return NameMatchResponse(
            model=kwargs["model"],
            threshold=kwargs["threshold"],
            matches=[],
            acceptedCount=0,
            unresolvedSourceChildIds=["source-1"],
            unresolvedPortalChildIds=["portal-1"],
        )

    monkeypatch.setattr(ai_api, "match_child_names_chunked", fake_match_child_names_chunked)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        deepseek_name_match_max_provider_calls=37,
        deepseek_name_match_deadline_seconds=42,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/ai/name-matches",
            json={
                "sourceChildren": [{"id": "source-1", "name": "Amina Noor"}],
                "portalChildren": [{"id": "portal-1", "name": "Amina N."}],
            },
        )

    assert response.status_code == 200
    assert captured["max_provider_calls"] == 37
    assert captured["deadline_seconds"] == 42


def test_name_matching_accepts_only_results_above_threshold(tmp_path, monkeypatch) -> None:
    content = {
        "matches": [
            {
                "source_id": "source-1",
                "portal_id": "portal-1",
                "confidence": 0.97,
                "reason": "Punctuation variation",
            },
            {
                "source_id": "source-2",
                "portal_id": "portal-2",
                "confidence": 0.89,
                "reason": "Possible spelling variation",
            },
        ]
    }
    monkeypatch.setattr(
        deepseek,
        "urlopen",
        lambda *_args, **_kwargs: FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(content)},
                    }
                ]
            }
        ),
    )
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        deepseek_api_key="test-key",
        deepseek_name_match_threshold=0.92,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/ai/name-matches",
            json={
                "sourceChildren": [
                    {"id": "source-1", "name": "Amina Noor"},
                    {"id": "source-2", "name": "Yusuf Ali"},
                ],
                "portalChildren": [
                    {"id": "portal-1", "name": "Amina N."},
                    {"id": "portal-2", "name": "Yousuf Ali"},
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["acceptedCount"] == 1
    assert payload["matches"][0]["accepted"] is True
    assert payload["matches"][1]["accepted"] is False
    assert payload["unresolvedSourceChildIds"] == ["source-2"]


def test_name_matching_rejects_an_unexpected_finish_reason(monkeypatch) -> None:
    monkeypatch.setattr(
        deepseek,
        "urlopen",
        lambda *_args, **_kwargs: FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "content_filter",
                        "message": {"content": '{"matches":[]}'},
                    }
                ]
            }
        ),
    )

    with pytest.raises(
        deepseek.DeepSeekServiceError,
        match="completion ended unexpectedly: content_filter",
    ):
        deepseek.match_child_names(
            api_key="test-key",
            model="test-model",
            threshold=0.92,
            source_children=[NameCandidate(id="s1", name="Source One")],
            portal_children=[NameCandidate(id="p1", name="Portal One")],
        )


def test_chrome_extension_origin_is_allowed_by_cors(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
    )
    origin = f"chrome-extension://{'a' * 32}"
    with TestClient(create_app(settings)) as client:
        response = client.options(
            "/api/v1/ai/name-matches",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_non_unique_model_rows_keep_the_highest_confidence_pair() -> None:
    matches, collision_count, discarded_count = deepseek._validated_matches(
        {
            "matches": [
                {
                    "source_id": "s1",
                    "portal_id": "p1",
                    "confidence": 0.71,
                    "reason": "weaker candidate",
                },
                {
                    "source_id": "s1",
                    "portal_id": "p2",
                    "confidence": 0.94,
                    "reason": "stronger candidate",
                },
            ]
        },
        [NameCandidate(id="s1", name="Source One")],
        [
            NameCandidate(id="p1", name="Portal One"),
            NameCandidate(id="p2", name="Portal Two"),
        ],
        0.92,
    )

    assert collision_count == 1
    assert discarded_count == 0
    assert [(match.source_child_id, match.portal_child_id) for match in matches] == [("s1", "p2")]


def test_invalid_model_rows_are_discarded_without_losing_valid_recommendations() -> None:
    matches, collision_count, discarded_count = deepseek._validated_matches(
        {
            "matches": [
                {
                    "sourceChildId": "s1",
                    "portalChildId": "p1",
                    "confidence": 0.87,
                    "reason": "valid camel-case row",
                },
                {"source_id": "missing", "portal_id": "p2", "confidence": 0.8},
                {"source_id": "s2", "portal_id": "p2", "confidence": "bad"},
                "not an object",
            ]
        },
        [
            NameCandidate(id="s1", name="Source One"),
            NameCandidate(id="s2", name="Source Two"),
        ],
        [
            NameCandidate(id="p1", name="Portal One"),
            NameCandidate(id="p2", name="Portal Two"),
        ],
        0.92,
    )

    assert collision_count == 0
    assert discarded_count == 3
    assert [(match.source_child_id, match.portal_child_id) for match in matches] == [("s1", "p1")]


def test_chunked_matching_retries_collisions_reported_inside_one_completion(
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], list[str]]] = []

    def fake_match_child_names(**kwargs) -> NameMatchResponse:
        source_ids = [child.id for child in kwargs["source_children"]]
        portal_ids = [child.id for child in kwargs["portal_children"]]
        calls.append((source_ids, portal_ids))
        if len(portal_ids) == 2:
            source_id, portal_id, collisions = "s1", "p1", 1
        else:
            source_id, portal_id, collisions = "s2", "p2", 0
        match = NameMatchResult(
            sourceChildId=source_id,
            portalChildId=portal_id,
            confidence=0.9,
            reason="test recommendation",
            accepted=False,
        )
        return NameMatchResponse(
            model=kwargs["model"],
            threshold=kwargs["threshold"],
            collisionCount=collisions,
            matches=[match],
            acceptedCount=0,
            unresolvedSourceChildIds=[],
            unresolvedPortalChildIds=[],
        )

    monkeypatch.setattr(deepseek, "match_child_names", fake_match_child_names)
    response = deepseek.match_child_names_chunked(
        api_key="test-key",
        model="test-model",
        threshold=0.92,
        chunk_size=20,
        source_children=[
            NameCandidate(id="s1", name="Source One"),
            NameCandidate(id="s2", name="Source Two"),
        ],
        portal_children=[
            NameCandidate(id="p1", name="Portal One"),
            NameCandidate(id="p2", name="Portal Two"),
        ],
    )

    assert calls == [(["s1", "s2"], ["p1", "p2"]), (["s2"], ["p2"])]
    assert {(match.source_child_id, match.portal_child_id) for match in response.matches} == {
        ("s1", "p1"),
        ("s2", "p2"),
    }


def test_chunked_matching_fails_clearly_when_bounded_retry_has_no_usable_rows(
    monkeypatch,
) -> None:
    calls = 0

    def fake_match_child_names(**kwargs) -> NameMatchResponse:
        nonlocal calls
        calls += 1
        return NameMatchResponse(
            model=kwargs["model"],
            threshold=kwargs["threshold"],
            discardedCount=1,
            matches=[],
            acceptedCount=0,
            unresolvedSourceChildIds=[child.id for child in kwargs["source_children"]],
            unresolvedPortalChildIds=[child.id for child in kwargs["portal_children"]],
        )

    monkeypatch.setattr(deepseek, "match_child_names", fake_match_child_names)

    with pytest.raises(
        deepseek.DeepSeekServiceError,
        match="no usable name recommendations after a bounded retry",
    ):
        deepseek.match_child_names_chunked(
            api_key="test-key",
            model="test-model",
            threshold=0.92,
            chunk_size=20,
            source_children=[NameCandidate(id="s1", name="Source One")],
            portal_children=[NameCandidate(id="p1", name="Portal One")],
        )

    assert calls == 2


def test_chunked_matching_recovers_from_truncation_with_smaller_batches(
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], list[dict[str, str]]]] = []

    def fake_urlopen(request, **_kwargs):
        request_payload = json.loads(request.data.decode("utf-8"))
        prompt = json.loads(request_payload["messages"][1]["content"])
        portal_ids = [child["id"] for child in prompt["portal_children"]]
        calls.append((portal_ids, prompt.get("excluded_pairs", [])))
        if len(portal_ids) > 2:
            return FakeDeepSeekResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": '{"matches":['},
                        }
                    ]
                }
            )
        matches = [
            {
                "source_id": portal_id.replace("p", "s", 1),
                "portal_id": portal_id,
                "confidence": 0.97,
                "reason": "same numbered test child",
            }
            for portal_id in portal_ids
        ]
        return FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps({"matches": matches})},
                    }
                ]
            }
        )

    monkeypatch.setattr(deepseek, "urlopen", fake_urlopen)
    response = deepseek.match_child_names_chunked(
        api_key="test-key",
        model="test-model",
        threshold=0.92,
        chunk_size=4,
        source_children=[
            NameCandidate(id=f"s{index}", name=f"Source {index}") for index in range(1, 5)
        ],
        portal_children=[
            NameCandidate(id=f"p{index}", name=f"Portal {index}") for index in range(1, 5)
        ],
        excluded_pairs={("s1", "p1")},
    )

    assert calls == [
        (["p1", "p2", "p3", "p4"], [{"source_id": "s1", "portal_id": "p1"}]),
        (["p1", "p2"], [{"source_id": "s1", "portal_id": "p1"}]),
        (["p3", "p4"], []),
    ]
    assert response.chunk_count == 3
    assert [(match.source_child_id, match.portal_child_id) for match in response.matches] == [
        ("s2", "p2"),
        ("s3", "p3"),
        ("s4", "p4"),
    ]
    assert response.unresolved_source_child_ids == ["s1"]
    assert response.unresolved_portal_child_ids == ["p1"]


def test_chunked_matching_can_split_a_configured_fifty_child_batch_to_singletons(
    monkeypatch,
) -> None:
    call_sizes: list[int] = []

    def fake_urlopen(request, **_kwargs):
        request_payload = json.loads(request.data.decode("utf-8"))
        prompt = json.loads(request_payload["messages"][1]["content"])
        portal_children = prompt["portal_children"]
        call_sizes.append(len(portal_children))
        if len(portal_children) > 1:
            return FakeDeepSeekResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": '{"matches":['},
                        }
                    ]
                }
            )
        portal_id = portal_children[0]["id"]
        match = {
            "source_id": portal_id.replace("p", "s", 1),
            "portal_id": portal_id,
            "confidence": 0.97,
            "reason": "same numbered child",
        }
        return FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps({"matches": [match]})},
                    }
                ]
            }
        )

    monkeypatch.setattr(deepseek, "urlopen", fake_urlopen)
    response = deepseek.match_child_names_chunked(
        api_key="test-key",
        model="test-model",
        threshold=0.92,
        chunk_size=50,
        source_children=[
            NameCandidate(id=f"s{index}", name=f"Source {index}") for index in range(1, 51)
        ],
        portal_children=[
            NameCandidate(id=f"p{index}", name=f"Portal {index}") for index in range(1, 51)
        ],
    )

    assert response.chunk_count == 99
    assert len(response.matches) == 50
    assert response.accepted_count == 50
    assert call_sizes[0] == 50
    assert max(size for size in call_sizes if size > 1) == 50
    assert call_sizes.count(1) == 50
    assert deepseek._truncation_recovery_limits(50) == (6, 149)


def test_chunked_matching_stops_after_bounded_persistent_singleton_truncation(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_urlopen(request, **_kwargs):
        request_payload = json.loads(request.data.decode("utf-8"))
        prompt = json.loads(request_payload["messages"][1]["content"])
        calls.append([child["id"] for child in prompt["portal_children"]])
        return FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"matches":['},
                    }
                ]
            }
        )

    monkeypatch.setattr(deepseek, "urlopen", fake_urlopen)

    with pytest.raises(
        deepseek.DeepSeekServiceError,
        match="remained truncated after 2 bounded recovery attempts for a batch of 1 portal child",
    ):
        deepseek.match_child_names_chunked(
            api_key="test-key",
            model="test-model",
            threshold=0.92,
            chunk_size=50,
            source_children=[NameCandidate(id="s1", name="Source One")],
            portal_children=[NameCandidate(id="p1", name="Portal One")],
        )

    assert calls == [["p1"], ["p1"]]
    assert len(calls) == deepseek._truncation_recovery_limits(1)[1]


def test_chunked_matching_enforces_a_whole_request_provider_call_ceiling(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_urlopen(request, **_kwargs):
        request_payload = json.loads(request.data.decode("utf-8"))
        prompt = json.loads(request_payload["messages"][1]["content"])
        portal_ids = [child["id"] for child in prompt["portal_children"]]
        calls.append(portal_ids)
        portal_id = portal_ids[0]
        return FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "matches": [
                                        {
                                            "source_id": portal_id.replace("p", "s", 1),
                                            "portal_id": portal_id,
                                            "confidence": 0.97,
                                            "reason": "same numbered child",
                                        }
                                    ]
                                }
                            )
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(deepseek, "urlopen", fake_urlopen)

    with pytest.raises(
        deepseek.DeepSeekServiceError,
        match="whole-request provider-call ceiling of 2",
    ):
        deepseek.match_child_names_chunked(
            api_key="test-key",
            model="test-model",
            threshold=0.92,
            chunk_size=1,
            max_provider_calls=2,
            deadline_seconds=180,
            source_children=[
                NameCandidate(id=f"s{index}", name=f"Source {index}")
                for index in range(1, 4)
            ],
            portal_children=[
                NameCandidate(id=f"p{index}", name=f"Portal {index}")
                for index in range(1, 4)
            ],
        )

    assert calls == [["p1"], ["p2"]]


def test_chunked_matching_threads_remaining_whole_request_deadline_to_urlopen(
    monkeypatch,
) -> None:
    clock = {"now": 100.0}
    observed_timeouts: list[float] = []

    monkeypatch.setattr(deepseek, "monotonic", lambda: clock["now"])

    def fake_urlopen(_request, **kwargs):
        observed_timeouts.append(kwargs["timeout"])
        clock["now"] += 3.0
        return FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"matches":[]}'},
                    }
                ]
            }
        )

    monkeypatch.setattr(deepseek, "urlopen", fake_urlopen)

    with pytest.raises(
        deepseek.DeepSeekServiceError,
        match="whole-request deadline of 3 seconds",
    ):
        deepseek.match_child_names_chunked(
            api_key="test-key",
            model="test-model",
            threshold=0.92,
            chunk_size=1,
            max_provider_calls=10,
            deadline_seconds=3,
            source_children=[NameCandidate(id="s1", name="Source One")],
            portal_children=[NameCandidate(id="p1", name="Portal One")],
        )

    assert observed_timeouts == [pytest.approx(3.0)]


def test_chunked_matching_reconciles_collisions_and_retries_remaining_children(
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], list[str]]] = []

    def fake_match_child_names(**kwargs) -> NameMatchResponse:
        source_ids = [child.id for child in kwargs["source_children"]]
        portal_ids = [child.id for child in kwargs["portal_children"]]
        calls.append((source_ids, portal_ids))
        portal_id = portal_ids[0]
        if portal_id == "p1":
            source_id, confidence = "s1", 0.96
        elif portal_id == "p2" and "s1" in source_ids:
            source_id, confidence = "s1", 0.88
        elif portal_id == "p2":
            source_id, confidence = "s2", 0.84
        else:
            source_id, confidence = "s3", 0.8
        match = NameMatchResult(
            sourceChildId=source_id,
            portalChildId=portal_id,
            confidence=confidence,
            reason="test recommendation",
            accepted=confidence >= kwargs["threshold"],
        )
        return NameMatchResponse(
            model=kwargs["model"],
            threshold=kwargs["threshold"],
            matches=[match],
            acceptedCount=int(match.accepted),
            unresolvedSourceChildIds=[],
            unresolvedPortalChildIds=[],
        )

    monkeypatch.setattr(deepseek, "match_child_names", fake_match_child_names)
    response = deepseek.match_child_names_chunked(
        api_key="test-key",
        model="test-model",
        threshold=0.92,
        chunk_size=1,
        source_children=[
            NameCandidate(id="s1", name="Source One"),
            NameCandidate(id="s2", name="Source Two"),
            NameCandidate(id="s3", name="Source Three"),
        ],
        portal_children=[
            NameCandidate(id="p1", name="Portal One"),
            NameCandidate(id="p2", name="Portal Two"),
            NameCandidate(id="p3", name="Portal Three"),
        ],
    )

    assert response.chunk_count == 4
    assert {(match.source_child_id, match.portal_child_id) for match in response.matches} == {
        ("s1", "p1"),
        ("s2", "p2"),
        ("s3", "p3"),
    }
    assert calls[-1] == (["s2"], ["p2"])


@pytest.mark.parametrize(
    ("excluded_pairs", "message"),
    [
        (
            [
                {"sourceChildId": "s1", "portalChildId": "p1"},
                {"sourceChildId": "s1", "portalChildId": "p1"},
            ],
            "unique source/portal pairs",
        ),
        (
            [{"sourceChildId": "missing", "portalChildId": "p1"}],
            "IDs present in sourceChildren and portalChildren",
        ),
    ],
)
def test_name_match_request_rejects_invalid_excluded_pairs(
    excluded_pairs: list[dict[str, str]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        NameMatchRequest.model_validate(
            {
                "sourceChildren": [{"id": "s1", "name": "Source One"}],
                "portalChildren": [{"id": "p1", "name": "Portal One"}],
                "excludedPairs": excluded_pairs,
            }
        )


def test_api_forwards_exclusions_to_prompt_and_never_returns_them(
    tmp_path,
    monkeypatch,
) -> None:
    captured_request: dict = {}
    content = {
        "matches": [
            {
                "source_id": "s1",
                "portal_id": "p1",
                "confidence": 0.99,
                "reason": "Previously rejected pair",
            },
            {
                "source_id": "s1",
                "portal_id": "p2",
                "confidence": 0.95,
                "reason": "Allowed alternative",
            },
        ]
    }

    def fake_urlopen(request, **_kwargs):
        captured_request.update(json.loads(request.data.decode("utf-8")))
        return FakeDeepSeekResponse(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(content)},
                    }
                ]
            }
        )

    monkeypatch.setattr(deepseek, "urlopen", fake_urlopen)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        deepseek_api_key="test-key",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/ai/name-matches",
            json={
                "sourceChildren": [{"id": "s1", "name": "Source One"}],
                "portalChildren": [
                    {"id": "p1", "name": "Portal Rejected"},
                    {"id": "p2", "name": "Portal Alternative"},
                ],
                "excludedPairs": [{"sourceChildId": "s1", "portalChildId": "p1"}],
            },
        )

    assert response.status_code == 200, response.text
    assert [
        (match["sourceChildId"], match["portalChildId"]) for match in response.json()["matches"]
    ] == [("s1", "p2")]
    messages = captured_request["messages"]
    system_prompt = messages[0]["content"]
    assert "Never return a source/portal pair listed in excluded_pairs" in system_prompt
    assert (
        '{"matches":[{"source_id":"SOURCE_ID","portal_id":"PORTAL_ID",'
        '"confidence":0.95,"reason":"spelling variant"}]}'
    ) in system_prompt
    assert "Every reason must be at most 8 words and 60 characters" in system_prompt
    prompt = json.loads(messages[1]["content"])
    assert prompt["excluded_pairs"] == [{"source_id": "s1", "portal_id": "p1"}]


def test_chunked_matching_scopes_exclusions_and_enforces_them_after_inner_match(
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], set[tuple[str, str]]]] = []

    def fake_match_child_names(**kwargs) -> NameMatchResponse:
        portal_ids = [child.id for child in kwargs["portal_children"]]
        calls.append((portal_ids, kwargs["excluded_pairs"]))
        portal_id = portal_ids[0]
        match = NameMatchResult(
            sourceChildId="s1",
            portalChildId=portal_id,
            confidence=0.99,
            reason="inner matcher bypass fixture",
            accepted=True,
        )
        return NameMatchResponse(
            model=kwargs["model"],
            threshold=kwargs["threshold"],
            matches=[match],
            acceptedCount=1,
            unresolvedSourceChildIds=[],
            unresolvedPortalChildIds=[],
        )

    monkeypatch.setattr(deepseek, "match_child_names", fake_match_child_names)
    response = deepseek.match_child_names_chunked(
        api_key="test-key",
        model="test-model",
        threshold=0.92,
        chunk_size=1,
        source_children=[
            NameCandidate(id="s1", name="Source One"),
            NameCandidate(id="s2", name="Source Two"),
        ],
        portal_children=[
            NameCandidate(id="p1", name="Portal One"),
            NameCandidate(id="p2", name="Portal Two"),
        ],
        excluded_pairs={("s1", "p1"), ("s2", "p2")},
    )

    assert calls == [
        (["p1"], {("s1", "p1")}),
        (["p2"], {("s2", "p2")}),
    ]
    assert [(match.source_child_id, match.portal_child_id) for match in response.matches] == [
        ("s1", "p2")
    ]
