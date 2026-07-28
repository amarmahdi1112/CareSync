"""DeepSeek JSON-mode client for constrained child-name reconciliation."""

import json
import math
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from app.schemas.ai_matching import (
    NameCandidate,
    NameMatchResponse,
    NameMatchResult,
)

DEEPSEEK_CHAT_URL = "https://api.deepseek.com/chat/completions"
_TRUNCATION_TERMINAL_RETRIES = 1
_PROVIDER_CALL_TIMEOUT_SECONDS = 60.0
DEFAULT_NAME_MATCH_MAX_PROVIDER_CALLS = 300
DEFAULT_NAME_MATCH_DEADLINE_SECONDS = 180.0


class DeepSeekConfigurationError(RuntimeError):
    """Raised when the local DeepSeek integration is not configured."""


class DeepSeekServiceError(RuntimeError):
    """Raised for invalid, unavailable, or unsafe model responses."""


class DeepSeekResponseTruncatedError(DeepSeekServiceError):
    """Raised when DeepSeek stops because its completion reached the output limit."""


class _ProviderRequestBudget:
    """Bound every provider call made by one public name-matching request."""

    def __init__(self, *, max_calls: int, deadline_seconds: float) -> None:
        if max_calls < 1:
            raise ValueError("max_provider_calls must be at least 1")
        if not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be a positive finite number")
        self.max_calls = max_calls
        self.deadline_seconds = deadline_seconds
        self.deadline_at = monotonic() + deadline_seconds
        self.calls = 0

    def _deadline_error(self) -> DeepSeekServiceError:
        return DeepSeekServiceError(
            "DeepSeek name matching exceeded its whole-request deadline of "
            f"{self.deadline_seconds:g} seconds"
        )

    def ensure_before_deadline(self) -> None:
        if monotonic() >= self.deadline_at:
            raise self._deadline_error()

    def begin_provider_call(self) -> float:
        self.ensure_before_deadline()
        if self.calls >= self.max_calls:
            raise DeepSeekServiceError(
                "DeepSeek name matching reached its whole-request provider-call ceiling of "
                f"{self.max_calls}"
            )
        remaining = self.deadline_at - monotonic()
        if remaining <= 0:
            raise self._deadline_error()
        self.calls += 1
        return min(_PROVIDER_CALL_TIMEOUT_SECONDS, remaining)


def _response_text(result: dict) -> str:
    choices = result.get("choices") or []
    if not choices:
        return ""
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length":
        raise DeepSeekResponseTruncatedError("DeepSeek name-matching response was truncated")
    if finish_reason != "stop":
        reason = str(finish_reason or "missing")[:100]
        raise DeepSeekServiceError(
            f"DeepSeek name-matching completion ended unexpectedly: {reason}"
        )
    return str(choice.get("message", {}).get("content") or "").strip()


def _validated_matches(
    raw: dict,
    source_children: list[NameCandidate],
    portal_children: list[NameCandidate],
    threshold: float,
    excluded_pairs: set[tuple[str, str]] | None = None,
) -> tuple[list[NameMatchResult], int, int]:
    values = raw.get("matches")
    if not isinstance(values, list):
        raise DeepSeekServiceError("DeepSeek returned an invalid name-matching structure")
    source_ids = {child.id for child in source_children}
    portal_ids = {child.id for child in portal_children}
    excluded = excluded_pairs or set()
    candidates: list[NameMatchResult] = []
    discarded_count = 0
    for value in values:
        if not isinstance(value, dict):
            discarded_count += 1
            continue
        source_id = str(value.get("source_id") or value.get("sourceChildId") or "").strip()
        portal_id = str(value.get("portal_id") or value.get("portalChildId") or "").strip()
        try:
            confidence = float(value.get("confidence"))
        except (TypeError, ValueError):
            discarded_count += 1
            continue
        reason = str(value.get("reason") or "Name variation identified").strip()[:60]
        if source_id not in source_ids or portal_id not in portal_ids:
            discarded_count += 1
            continue
        # A denied pair is an expected omission, not an invalid model row. Do
        # not count it as a service failure, but never allow it into candidates.
        if (source_id, portal_id) in excluded:
            continue
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            discarded_count += 1
            continue
        candidates.append(
            NameMatchResult(
                sourceChildId=source_id,
                portalChildId=portal_id,
                confidence=round(confidence, 4),
                reason=reason,
                accepted=confidence >= threshold,
            )
        )
    matches = _globally_unique_matches(candidates)
    return matches, len(candidates) - len(matches), discarded_count


def match_child_names(
    *,
    api_key: str,
    model: str,
    threshold: float,
    source_children: list[NameCandidate],
    portal_children: list[NameCandidate],
    excluded_pairs: set[tuple[str, str]] | None = None,
    provider_budget: _ProviderRequestBudget | None = None,
) -> NameMatchResponse:
    """Match only plausible same-person name variants and validate every returned ID."""

    if not api_key:
        raise DeepSeekConfigurationError("DeepSeek API key is not configured")
    system_prompt = (
        "You reconcile child names between two daycare systems.\n"
        "Return exactly one compact JSON object using this schema/example and no additional keys:\n"
        '{"matches":[{"source_id":"SOURCE_ID","portal_id":"PORTAL_ID",'
        '"confidence":0.95,"reason":"spelling variant"}]}\n'
        'Return {"matches":[]} when no relationship is meaningful. Every reason must be at most '
        "8 words and 60 characters.\n"
        "For each portal child, return the best plausible source candidate when there is any "
        "meaningful name relationship: capitalization, spacing, punctuation, token order, "
        "transliteration, spelling, or an added/omitted middle or family name. Use a lower "
        "confidence for uncertain recommendations instead of hiding them; the operator will "
        "verify those manually. Omit only pairs with no meaningful name relationship. Never "
        "reuse a source or portal ID: every recommendation must be one-to-one. Use only IDs "
        "present in the input. Never return a source/portal pair listed in excluded_pairs; those "
        "pairs were explicitly rejected by the operator. Confidence must represent same-person "
        "certainty from 0 to 1. Output JSON and nothing else."
    )
    excluded = excluded_pairs or set()
    prompt_payload = {
        "task": "Return JSON matching source children to portal children",
        "source_children": [child.model_dump() for child in source_children],
        "portal_children": [child.model_dump() for child in portal_children],
    }
    if excluded:
        prompt_payload["excluded_pairs"] = [
            {"source_id": source_id, "portal_id": portal_id}
            for source_id, portal_id in sorted(excluded)
        ]
    user_prompt = json.dumps(
        prompt_payload,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    outbound = UrlRequest(
        DEEPSEEK_CHAT_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    request_timeout = (
        provider_budget.begin_provider_call()
        if provider_budget is not None
        else _PROVIDER_CALL_TIMEOUT_SECONDS
    )
    try:
        with urlopen(outbound, timeout=request_timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if provider_budget is not None:
            provider_budget.ensure_before_deadline()
    except HTTPError as error:
        if provider_budget is not None:
            provider_budget.ensure_before_deadline()
        detail = "DeepSeek rejected the name-matching request"
        try:
            error_payload = json.loads(error.read().decode("utf-8"))
            detail = str(error_payload.get("error", {}).get("message") or detail)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        raise DeepSeekServiceError(detail) from None
    except (URLError, TimeoutError) as error:
        if provider_budget is not None:
            provider_budget.ensure_before_deadline()
        reason = error.reason if isinstance(error, URLError) else "timeout"
        raise DeepSeekServiceError(f"DeepSeek request failed: {reason}") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        if provider_budget is not None:
            provider_budget.ensure_before_deadline()
        raise DeepSeekServiceError("DeepSeek returned an unreadable response") from error

    content = _response_text(result)
    if not content:
        raise DeepSeekServiceError("DeepSeek returned an empty name-matching response")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise DeepSeekServiceError("DeepSeek returned invalid JSON") from error
    matches, collision_count, discarded_count = _validated_matches(
        parsed,
        source_children,
        portal_children,
        threshold,
        excluded,
    )
    accepted_sources = {match.source_child_id for match in matches if match.accepted}
    accepted_portals = {match.portal_child_id for match in matches if match.accepted}
    return NameMatchResponse(
        model=model,
        threshold=threshold,
        collisionCount=collision_count,
        discardedCount=discarded_count,
        matches=matches,
        acceptedCount=len(accepted_sources),
        unresolvedSourceChildIds=[
            child.id for child in source_children if child.id not in accepted_sources
        ],
        unresolvedPortalChildIds=[
            child.id for child in portal_children if child.id not in accepted_portals
        ],
    )


def _chunks(values: list[NameCandidate], size: int) -> list[list[NameCandidate]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _globally_unique_matches(
    matches: list[NameMatchResult],
    *,
    excluded_source_ids: set[str] | None = None,
    excluded_portal_ids: set[str] | None = None,
) -> list[NameMatchResult]:
    used_sources = set(excluded_source_ids or ())
    used_portals = set(excluded_portal_ids or ())
    selected: list[NameMatchResult] = []
    for match in sorted(matches, key=lambda candidate: candidate.confidence, reverse=True):
        if match.source_child_id in used_sources or match.portal_child_id in used_portals:
            continue
        selected.append(match)
        used_sources.add(match.source_child_id)
        used_portals.add(match.portal_child_id)
    return selected


def _truncation_recovery_limits(portal_batch_size: int) -> tuple[int, int]:
    """Return a complete binary-split depth and a strict request ceiling.

    A batch of ``n`` can always reach singleton leaves in ``ceil(log2(n))``
    levels. Its full binary split tree uses at most ``2n - 1`` requests. One
    retry for every singleton adds at most ``n`` more requests, making the
    absolute per-batch ceiling ``3n - 1`` (149 for the configured maximum of
    50 portal children).
    """

    if portal_batch_size < 1:
        raise ValueError("portal batch must contain at least one child")
    max_split_depth = (portal_batch_size - 1).bit_length()
    max_attempts = (3 * portal_batch_size) - 1
    return max_split_depth, max_attempts


def _match_portal_chunk_with_truncation_recovery(
    *,
    api_key: str,
    model: str,
    threshold: float,
    source_children: list[NameCandidate],
    portal_children: list[NameCandidate],
    excluded_pairs: set[tuple[str, str]],
    provider_budget: _ProviderRequestBudget,
) -> tuple[list[NameMatchResponse], int]:
    """Split a truncated portal batch and retry it within strict request bounds.

    DeepSeek can return ``finish_reason=length`` even when JSON mode is enabled. A
    partial JSON document is unsafe to consume, so the failed completion is
    discarded and the portal side of the prompt is divided deterministically.
    The source pool remains complete so a valid cross-system match is not hidden.
    """

    attempts = 0
    original_size = len(portal_children)
    max_split_depth, max_attempts = _truncation_recovery_limits(original_size)

    def exhausted() -> DeepSeekServiceError:
        child_label = "portal child" if original_size == 1 else "portal children"
        return DeepSeekServiceError(
            "DeepSeek name-matching response remained truncated after "
            f"{attempts} bounded recovery attempts for a batch of "
            f"{original_size} {child_label}"
        )

    def attempt(
        portal_batch: list[NameCandidate],
        *,
        split_depth: int,
        terminal_retries: int,
    ) -> list[NameMatchResponse]:
        nonlocal attempts
        if attempts >= max_attempts:
            raise exhausted()

        attempts += 1
        source_ids = {child.id for child in source_children}
        portal_ids = {child.id for child in portal_batch}
        scoped_exclusions = {
            pair for pair in excluded_pairs if pair[0] in source_ids and pair[1] in portal_ids
        }
        try:
            response = match_child_names(
                api_key=api_key,
                model=model,
                threshold=threshold,
                source_children=source_children,
                portal_children=portal_batch,
                excluded_pairs=scoped_exclusions,
                provider_budget=provider_budget,
            )
        except DeepSeekResponseTruncatedError:
            if len(portal_batch) > 1 and split_depth < max_split_depth:
                midpoint = len(portal_batch) // 2
                left = attempt(
                    portal_batch[:midpoint],
                    split_depth=split_depth + 1,
                    terminal_retries=_TRUNCATION_TERMINAL_RETRIES,
                )
                right = attempt(
                    portal_batch[midpoint:],
                    split_depth=split_depth + 1,
                    terminal_retries=_TRUNCATION_TERMINAL_RETRIES,
                )
                return left + right
            if terminal_retries > 0:
                return attempt(
                    portal_batch,
                    split_depth=split_depth,
                    terminal_retries=terminal_retries - 1,
                )
            raise exhausted() from None
        return [response]

    return (
        attempt(
            portal_children,
            split_depth=0,
            terminal_retries=_TRUNCATION_TERMINAL_RETRIES,
        ),
        attempts,
    )


def match_child_names_chunked(
    *,
    api_key: str,
    model: str,
    threshold: float,
    chunk_size: int,
    source_children: list[NameCandidate],
    portal_children: list[NameCandidate],
    excluded_pairs: set[tuple[str, str]] | None = None,
    max_provider_calls: int = DEFAULT_NAME_MATCH_MAX_PROVIDER_CALLS,
    deadline_seconds: float = DEFAULT_NAME_MATCH_DEADLINE_SECONDS,
) -> NameMatchResponse:
    """Collect bounded completions, then globally reconcile their one-to-one recommendations."""

    requests = 0
    excluded = excluded_pairs or set()
    provider_budget = _ProviderRequestBudget(
        max_calls=max_provider_calls,
        deadline_seconds=deadline_seconds,
    )
    first_pass_candidates: list[NameMatchResult] = []
    collision_count = 0
    discarded_count = 0
    for portal_chunk in _chunks(portal_children, chunk_size):
        responses, chunk_requests = _match_portal_chunk_with_truncation_recovery(
            api_key=api_key,
            model=model,
            threshold=threshold,
            source_children=source_children,
            portal_children=portal_chunk,
            excluded_pairs=excluded,
            provider_budget=provider_budget,
        )
        requests += chunk_requests
        for response in responses:
            first_pass_candidates.extend(
                match
                for match in response.matches
                if (match.source_child_id, match.portal_child_id) not in excluded
            )
            collision_count += response.collision_count
            discarded_count += response.discarded_count

    selected = _globally_unique_matches(first_pass_candidates)
    used_source_ids = {match.source_child_id for match in selected}
    used_portal_ids = {match.portal_child_id for match in selected}

    # Cross-chunk collisions can cause a portal recommendation to lose to a
    # higher-confidence recommendation for the same source. Give only those
    # remaining portals a second chance against the still-unused sources.
    collision_count += len(first_pass_candidates) - len(selected)
    if collision_count > 0 or discarded_count > 0:
        remaining_sources = [child for child in source_children if child.id not in used_source_ids]
        remaining_portals = [child for child in portal_children if child.id not in used_portal_ids]
        second_pass_candidates: list[NameMatchResult] = []
        if remaining_sources and remaining_portals:
            for portal_chunk in _chunks(remaining_portals, chunk_size):
                responses, chunk_requests = _match_portal_chunk_with_truncation_recovery(
                    api_key=api_key,
                    model=model,
                    threshold=threshold,
                    source_children=remaining_sources,
                    portal_children=portal_chunk,
                    excluded_pairs=excluded,
                    provider_budget=provider_budget,
                )
                requests += chunk_requests
                for response in responses:
                    second_pass_candidates.extend(
                        match
                        for match in response.matches
                        if (match.source_child_id, match.portal_child_id) not in excluded
                    )
                    collision_count += response.collision_count
                    discarded_count += response.discarded_count
            second_pass_selected = _globally_unique_matches(
                second_pass_candidates,
                excluded_source_ids=used_source_ids,
                excluded_portal_ids=used_portal_ids,
            )
            collision_count += len(second_pass_candidates) - len(second_pass_selected)
            selected.extend(second_pass_selected)

    # Defense in depth for substituted clients and future refactors: excluded
    # pairs are forbidden even if an inner matcher bypasses prompt validation.
    selected = [
        match
        for match in selected
        if (match.source_child_id, match.portal_child_id) not in excluded
    ]

    if not selected and discarded_count > 0:
        raise DeepSeekServiceError(
            "DeepSeek returned no usable name recommendations after a bounded retry"
        )

    source_order = {child.id: index for index, child in enumerate(source_children)}
    selected.sort(key=lambda match: source_order[match.source_child_id])
    accepted_sources = {match.source_child_id for match in selected if match.accepted}
    accepted_portals = {match.portal_child_id for match in selected if match.accepted}
    provider_budget.ensure_before_deadline()
    return NameMatchResponse(
        model=model,
        threshold=threshold,
        chunkCount=max(1, requests),
        collisionCount=collision_count,
        discardedCount=discarded_count,
        matches=selected,
        acceptedCount=len(accepted_sources),
        unresolvedSourceChildIds=[
            child.id for child in source_children if child.id not in accepted_sources
        ],
        unresolvedPortalChildIds=[
            child.id for child in portal_children if child.id not in accepted_portals
        ],
    )
