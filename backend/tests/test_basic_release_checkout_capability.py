"""Capability/closure proofs for the authenticated verified-release boundary."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.basic import release_checkout_capability as capability


@pytest.fixture
def postgres(monkeypatch):
    monkeypatch.setattr(capability, "_is_postgresql", lambda _session: True)


def test_capability_is_not_advertised_before_the_complete_runtime(
    monkeypatch,
    postgres,
) -> None:
    called = False

    def projection(_session, *, facility_id):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(capability, "_postgres_activation_enabled", projection)
    common = {
        "session": object(),
        "organization_id": uuid4(),
        "facility_id": uuid4(),
        "permissions": ["attendance:record", "release:read", "release:checkout"],
    }

    assert capability.verified_release_capability(
        **common,
        foundation_present=False,
        runtime_enabled=False,
    ) == capability.VerifiedReleaseCapability(False, False, True, True, None)
    assert capability.verified_release_capability(
        **common,
        foundation_present=True,
        runtime_enabled=False,
    ) == capability.VerifiedReleaseCapability(False, False, True, False, None)
    assert called is False


def test_capability_requires_user_permissions_and_facility_activation(
    monkeypatch,
    postgres,
) -> None:
    activation = True
    calls = []

    def projection(_session, *, facility_id):
        calls.append(facility_id)
        return activation

    monkeypatch.setattr(capability, "_postgres_activation_enabled", projection)
    organization_id = uuid4()
    facility_id = uuid4()
    common = {
        "session": object(),
        "organization_id": organization_id,
        "facility_id": facility_id,
        "foundation_present": True,
        "runtime_enabled": True,
    }

    unavailable = capability.verified_release_capability(
        **common,
        permissions=["attendance:record", "release:checkout"],
    )
    assert unavailable == capability.VerifiedReleaseCapability(
        True,
        True,
        False,
        False,
        "normal_verified_release_v1",
    )
    assert calls == [facility_id]

    activation = False
    inactive = capability.verified_release_capability(
        **common,
        permissions=["attendance:record", "release:read", "release:checkout"],
    )
    assert inactive == capability.VerifiedReleaseCapability(True, False, True, True, None)

    activation = True
    active = capability.verified_release_capability(
        **common,
        permissions=["attendance:record", "release:read", "release:checkout"],
    )
    assert active == capability.VerifiedReleaseCapability(
        True,
        True,
        True,
        False,
        "normal_verified_release_v1",
    )
    assert calls == [facility_id, facility_id, facility_id]


def test_portable_activation_closes_legacy_without_advertising_d(
    monkeypatch,
) -> None:
    monkeypatch.setattr(capability, "_is_postgresql", lambda _session: False)
    monkeypatch.setattr(
        capability,
        "_portable_activation_enabled",
        lambda _session, *, organization_id, facility_id: True,
    )
    value = capability.verified_release_capability(
        object(),
        organization_id=uuid4(),
        facility_id=uuid4(),
        permissions=["attendance:record", "release:read", "release:checkout"],
        foundation_present=True,
        runtime_enabled=False,
    )
    assert value == capability.VerifiedReleaseCapability(
        False,
        True,
        True,
        False,
        "normal_verified_release_v1",
    )


def test_postgres_legacy_closure_fails_closed_until_d_can_answer(
    monkeypatch,
    postgres,
) -> None:
    facility_id = uuid4()
    common = {
        "session": object(),
        "organization_id": uuid4(),
        "facility_id": facility_id,
    }

    assert capability.facility_requires_verified_release_checkout(
        **common,
        foundation_present=False,
        runtime_enabled=False,
    ) is False
    assert capability.facility_requires_verified_release_checkout(
        **common,
        foundation_present=True,
        runtime_enabled=False,
    ) is True

    monkeypatch.setattr(
        capability,
        "_postgres_activation_enabled",
        lambda _session, *, facility_id: False,
    )
    assert capability.facility_requires_verified_release_checkout(
        **common,
        foundation_present=True,
        runtime_enabled=True,
    ) is False
    monkeypatch.setattr(
        capability,
        "_postgres_activation_enabled",
        lambda _session, *, facility_id: True,
    )
    assert capability.facility_requires_verified_release_checkout(
        **common,
        foundation_present=True,
        runtime_enabled=True,
    ) is True


def test_projection_failure_never_degrades_to_legacy_checkout(
    monkeypatch,
    postgres,
) -> None:
    def unavailable(_session, *, facility_id):
        raise capability.ReleaseCheckoutRepositoryError(
            code="family_authority_release_checkout_unavailable",
            status_code=503,
        )

    monkeypatch.setattr(
        capability,
        "postgres_release_checkout_activation_enabled",
        unavailable,
    )
    with pytest.raises(HTTPException) as captured:
        capability.facility_requires_verified_release_checkout(
            object(),
            organization_id=uuid4(),
            facility_id=uuid4(),
            foundation_present=True,
            runtime_enabled=True,
        )
    assert captured.value.status_code == 503
    assert captured.value.detail == {
        "code": "family_authority_release_checkout_unavailable"
    }
