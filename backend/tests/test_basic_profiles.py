"""Routed family/child profile contracts and protected photo acceptance tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.api.basic import childcare as childcare_api
from app.basic.models import BasicBase, Child, ChildProfilePhoto, Facility, Room
from app.core.config import Settings
from app.main import create_app

PASSWORD = "correct-password-123"


def _client(
    tmp_path,
    *,
    maximum_photo_bytes: int = 6 * 1024 * 1024,
    maximum_photo_pixels: int = 25_000_000,
):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="profile-test-secret-with-at-least-32-bytes",
        child_profile_photo_max_bytes=maximum_photo_bytes,
        child_profile_photo_max_pixels=maximum_photo_pixels,
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client: TestClient, email: str, organization_name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Profile",
            "last_name": "Owner",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _create_family(client: TestClient, headers: dict[str, str], prefix: str) -> dict:
    response = client.post(
        "/api/v1/families",
        headers=headers,
        json={
            "client_operation_id": str(uuid4()),
            "name": f"{prefix} Family",
            "file_number": f"{prefix.upper()}-001",
            "additional_notes": "Family profile note",
            "consents": {
                "photo_consent": True,
                "field_trip_consent": True,
                "emergency_medical_consent": True,
            },
            "primary_guardian": {
                "first_name": "Primary",
                "last_name": prefix,
                "relationship": "Parent",
                "email": f"primary-{prefix.lower()}@example.com",
                "cell_phone": "780-555-0101",
            },
            "secondary_guardian": {
                "first_name": "Secondary",
                "last_name": prefix,
                "relationship": "Parent",
                "email": f"secondary-{prefix.lower()}@example.com",
                "cell_phone": "780-555-0102",
            },
            "emergency_contacts": [
                {
                    "first_name": "Emergency",
                    "last_name": prefix,
                    "relationship": "Aunt",
                    "cell_phone": "780-555-0103",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_facility_tree(client: TestClient, headers: dict[str, str], prefix: str):
    facility_response = client.post(
        "/api/v1/facilities",
        headers=headers,
        json={
            "name": f"{prefix} Centre",
            "status": "active",
            "licensed_capacity": 40,
        },
    )
    assert facility_response.status_code == 201, facility_response.text
    facility = facility_response.json()
    program_response = client.post(
        "/api/v1/programs",
        headers=headers,
        json={
            "facility_id": facility["id"],
            "name": f"{prefix} Daycare",
            "program_type": "daycare",
            "capacity": 40,
            "minimum_age_months": 0,
            "maximum_age_months": 143,
        },
    )
    assert program_response.status_code == 201, program_response.text
    program = program_response.json()
    rooms = []
    for suffix in ("North", "South"):
        room_response = client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "facility_id": facility["id"],
                "program_id": program["id"],
                "name": f"{prefix} {suffix}",
                "capacity": 20,
                "minimum_age_months": 0,
                "maximum_age_months": 143,
            },
        )
        assert room_response.status_code == 201, room_response.text
        rooms.append(room_response.json())
    return facility, program, rooms


def _create_child(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    first_name: str,
    *,
    placement: tuple[dict, dict, dict] | None = None,
    enrollment_start_date: str = "2026-01-01",
) -> dict:
    payload: dict[str, object] = {
        "client_operation_id": str(uuid4()),
        "family_id": family_id,
        "first_name": first_name,
        "middle_name": "M",
        "last_name": "Profile",
        "date_of_birth": "2023-01-01",
        "allergies": "Peanuts",
        "medical_conditions": "Asthma",
        "medications": "Inhaler",
        "immunization_up_to_date": True,
        "doctor_name": "Dr. Care",
        "doctor_phone": "780-555-0199",
    }
    response = client.post("/api/v1/children", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    child = response.json()
    if placement is not None:
        facility, _, room = placement
        enrollment_response = client.post(
            f"/api/v1/children/{child['id']}/enrollments",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "facility_id": facility["id"],
                "start_date": enrollment_start_date,
            },
        )
        assert enrollment_response.status_code == 201, enrollment_response.text
        enrollment = enrollment_response.json()
        approval_response = client.post(
            f"/api/v1/enrollments/{enrollment['id']}/placement-approval",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": enrollment["version"],
                "room_id": room["id"],
                "effective_date": max(date.today().isoformat(), enrollment_start_date),
            },
        )
        assert approval_response.status_code == 200, approval_response.text
        refreshed = client.get(f"/api/v1/children/{child['id']}", headers=headers)
        assert refreshed.status_code == 200, refreshed.text
        child = refreshed.json()
    return child


def _image_bytes(
    *,
    size: tuple[int, int] = (1800, 1200),
    transparent: bool = False,
    image_format: str = "PNG",
) -> bytes:
    mode = "RGBA" if transparent else "RGB"
    color = (32, 180, 220, 180) if transparent else (32, 180, 220)
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def _upload(
    client: TestClient,
    headers: dict[str, str],
    child_id: str,
    content: bytes,
    *,
    filename: str = "portrait.png",
    media_type: str = "image/png",
):
    return client.put(
        f"/api/v1/children/{child_id}/photo",
        headers=headers,
        files={"file": (filename, content, media_type)},
    )


def _secret_from_activation_url(value: str) -> str:
    parsed = urlparse(value)
    assert parsed.path.endswith("/activate-staff")
    values = parse_qs(parsed.fragment).get("token", [])
    assert len(values) == 1
    return values[0]


def test_family_and_child_profiles_include_connected_context_and_named_placement(
    tmp_path,
) -> None:
    client, _ = _client(tmp_path)
    with client:
        auth = _register(client, "profile-detail@example.com", "Profile Child Care")
        headers = _headers(auth)
        family = _create_family(client, headers, "Connected")
        facility, program, rooms = _create_facility_tree(client, headers, "Connected")
        child = _create_child(
            client,
            headers,
            family["id"],
            "Casey",
            placement=(facility, program, rooms[0]),
        )

        response = client.get(f"/api/v1/children/{child['id']}", headers=headers)
        assert response.status_code == 200, response.text
        profile = response.json()
        assert profile["family"] == {
            "id": family["id"],
            "organization_id": auth["user"]["organization_id"],
            "name": "Connected Family",
            "file_number": "CONNECTED-001",
            "status": "active",
            "version": family["version"],
            "replayed": False,
            "additional_notes": "Family profile note",
            "photo_consent": True,
            "field_trip_consent": True,
            "emergency_medical_consent": True,
            "guardians": family["guardians"],
            "emergency_contacts": family["emergency_contacts"],
        }
        current = profile["current_enrollment"]
        assert current["facility_name"] == "Connected Centre"
        assert current["program_name"] == "Connected Daycare"
        assert current["program_type"] == "daycare"
        assert current["room_name"] == "Connected North"
        assert profile["enrollments"] == [current]
        assert profile["profile_photo_url"] is None
        assert profile["profile_photo_updated_at"] is None

        family_profile = client.get(f"/api/v1/families/{family['id']}", headers=headers).json()
        nested = family_profile["children"][0]
        assert nested["id"] == child["id"]
        assert nested["enrollments"][0]["room_name"] == "Connected North"


def test_future_enrollment_is_history_not_current_profile_placement(tmp_path) -> None:
    client, _ = _client(tmp_path)
    with client:
        auth = _register(client, "future-profile@example.com", "Future Profile Care")
        headers = _headers(auth)
        family = _create_family(client, headers, "Future")
        facility, program, rooms = _create_facility_tree(client, headers, "Future")
        future_start = (date.today() + timedelta(days=30)).isoformat()
        child = _create_child(
            client,
            headers,
            family["id"],
            "Jordan",
            placement=(facility, program, rooms[0]),
            enrollment_start_date=future_start,
        )

        response = client.get(f"/api/v1/children/{child['id']}", headers=headers)
        assert response.status_code == 200, response.text
        profile = response.json()
        assert profile["current_enrollment"] is None
        assert len(profile["enrollments"]) == 1
        assert profile["enrollments"][0]["start_date"] == future_start
        assert profile["enrollments"][0]["status"] == "active"
        assert profile["enrollments"][0]["is_active"] is False


def test_profile_photo_is_normalized_private_no_store_replaceable_and_deletable(
    tmp_path,
) -> None:
    client, application = _client(tmp_path)
    with client:
        auth = _register(client, "photo-crud@example.com", "Photo Child Care")
        headers = _headers(auth)
        family = _create_family(client, headers, "Photo")
        child = _create_child(client, headers, family["id"], "Morgan")
        original = _image_bytes()

        uploaded = _upload(
            client,
            headers,
            child["id"],
            original,
            filename="../../Morgan portrait.png",
        )
        assert uploaded.status_code == 200, uploaded.text
        metadata = uploaded.json()
        assert metadata["url"] == f"/api/v1/children/{child['id']}/photo"
        assert metadata["content_type"] == "image/jpeg"
        assert max(metadata["width"], metadata["height"]) == 1024
        assert metadata["size_bytes"] < len(original)
        assert metadata["original_filename"] == "Morgan portrait.png"
        assert len(metadata["sha256"]) == 64

        private = client.get(metadata["url"], headers=headers)
        assert private.status_code == 200
        assert private.headers["content-type"] == "image/jpeg"
        assert private.headers["cache-control"] == "private, no-store"
        assert private.headers["pragma"] == "no-cache"
        assert private.headers["x-content-type-options"] == "nosniff"
        assert private.headers["etag"] == f'"{metadata["sha256"]}"'
        with Image.open(BytesIO(private.content)) as normalized:
            assert normalized.format == "JPEG"
            assert max(normalized.size) == 1024
            assert not normalized.getexif()
        assert private.content != original

        not_modified = client.get(
            metadata["url"],
            headers={**headers, "If-None-Match": private.headers["etag"]},
        )
        assert not_modified.status_code == 304
        assert not_modified.content == b""
        assert client.get(metadata["url"]).status_code == 401

        child_profile = client.get(f"/api/v1/children/{child['id']}", headers=headers).json()
        assert child_profile["profile_photo_url"] == metadata["url"]
        assert child_profile["profile_photo_updated_at"] is not None
        for technical_field in (
            "profile_photo_content_type",
            "profile_photo_size_bytes",
            "profile_photo_width",
            "profile_photo_height",
            "profile_photo_sha256",
            "profile_photo_original_filename",
        ):
            assert technical_field not in child_profile

        transparent = _upload(
            client,
            headers,
            child["id"],
            _image_bytes(size=(600, 800), transparent=True),
        )
        assert transparent.status_code == 200, transparent.text
        assert transparent.json()["content_type"] == "image/webp"
        assert transparent.json()["sha256"] != metadata["sha256"]
        assert (
            client.get(transparent.json()["url"], headers=headers).headers["content-type"]
            == "image/webp"
        )

        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildProfilePhoto)) == 1
            stored = session.scalar(select(ChildProfilePhoto))
            assert stored is not None
            assert stored.image_bytes != original

        deleted = client.delete(metadata["url"], headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert client.get(metadata["url"], headers=headers).status_code == 404
        after_delete = client.get(f"/api/v1/children/{child['id']}", headers=headers).json()
        assert after_delete["profile_photo_url"] is None
        assert after_delete["profile_photo_updated_at"] is None


def test_profile_photo_rejects_invalid_oversize_and_animated_inputs(tmp_path) -> None:
    client, application = _client(
        tmp_path,
        maximum_photo_bytes=64 * 1024,
        maximum_photo_pixels=1_000_000,
    )
    with client:
        auth = _register(client, "photo-invalid@example.com", "Invalid Photo Care")
        headers = _headers(auth)
        family = _create_family(client, headers, "Invalid")
        child = _create_child(client, headers, family["id"], "Avery")

        invalid = _upload(
            client,
            headers,
            child["id"],
            b"this is not an image",
            filename="not-image.png",
        )
        assert invalid.status_code == 422

        oversize = _upload(
            client,
            headers,
            child["id"],
            b"x" * (64 * 1024 + 1),
            filename="oversize.png",
        )
        assert oversize.status_code == 413

        excessive_pixels = _upload(
            client,
            headers,
            child["id"],
            _image_bytes(size=(1100, 1000)),
            filename="too-many-pixels.png",
        )
        assert excessive_pixels.status_code == 413

        frames = [Image.new("RGB", (32, 32), color) for color in ("red", "blue")]
        animation = BytesIO()
        frames[0].save(
            animation,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )
        animated = _upload(
            client,
            headers,
            child["id"],
            animation.getvalue(),
            filename="animated.webp",
            media_type="image/webp",
        )
        assert animated.status_code == 422
        assert animated.json()["detail"] == "Animated profile photos are not supported"

        with application.state.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(ChildProfilePhoto)) == 0


def test_photo_tenant_boundary_and_educator_room_scope_fail_closed(
    tmp_path,
    monkeypatch,
) -> None:
    client, application = _client(tmp_path)
    with client:
        owner = _register(client, "scope-owner@example.com", "Scoped Photo Care")
        owner_headers = _headers(owner)
        family = _create_family(client, owner_headers, "Scope")
        facility, program, rooms = _create_facility_tree(client, owner_headers, "Scope")
        facility_today = date.today() + timedelta(days=1)
        north_child = _create_child(
            client,
            owner_headers,
            family["id"],
            "North",
            placement=(facility, program, rooms[0]),
            enrollment_start_date=facility_today.isoformat(),
        )
        south_child = _create_child(
            client,
            owner_headers,
            family["id"],
            "South",
            placement=(facility, program, rooms[1]),
            enrollment_start_date=facility_today.isoformat(),
        )
        for child in (north_child, south_child):
            uploaded = _upload(
                client,
                owner_headers,
                child["id"],
                _image_bytes(size=(80, 80)),
            )
            assert uploaded.status_code == 200, uploaded.text

        other = _register(client, "other-owner@example.com", "Other Photo Care")
        other_headers = _headers(other)
        foreign = client.get(
            f"/api/v1/children/{north_child['id']}/photo",
            headers=other_headers,
        )
        missing = client.get(
            f"/api/v1/children/{uuid4()}/photo",
            headers=other_headers,
        )
        assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())
        assert foreign.status_code == 404

        workspace = client.get("/api/v1/staff/workspace", headers=owner_headers).json()
        educator_role = next(role for role in workspace["roles"] if role["key"] == "educator")
        invited = client.post(
            "/api/v1/staff/invitations",
            headers=owner_headers,
            json={
                "email": "photo-educator@example.com",
                "first_name": "Photo",
                "last_name": "Educator",
                "role_id": educator_role["id"],
                "assigned_facility_ids": [facility["id"]],
                "assigned_room_ids": [rooms[0]["id"]],
            },
        )
        assert invited.status_code == 201, invited.text
        token = _secret_from_activation_url(invited.json()["activation_url"])
        accepted = client.post(
            "/api/v1/auth/staff-activation/accept",
            json={"token": token, "password": PASSWORD},
        )
        assert accepted.status_code == 200, accepted.text
        educator_headers = _headers(accepted.json())

        frozen_instant = datetime.combine(
            facility_today,
            time(0, 30),
            ZoneInfo("America/Edmonton"),
        ).astimezone(UTC)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen_instant.astimezone(tz) if tz is not None else frozen_instant

        monkeypatch.setattr(childcare_api, "datetime", FrozenDateTime)

        assigned = client.get(
            f"/api/v1/children/{north_child['id']}/photo",
            headers=educator_headers,
        )
        outside_scope = client.get(
            f"/api/v1/children/{south_child['id']}/photo",
            headers=educator_headers,
        )
        random_child = client.get(
            f"/api/v1/children/{uuid4()}/photo",
            headers=educator_headers,
        )
        assert assigned.status_code == 200
        assert assigned.headers["cache-control"] == "private, no-store"
        assert outside_scope.status_code == 404
        assert outside_scope.json() == random_child.json()
        assert (
            _upload(
                client,
                educator_headers,
                north_child["id"],
                _image_bytes(size=(40, 40)),
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/api/v1/children/{north_child['id']}/photo",
                headers=educator_headers,
            ).status_code
            == 403
        )

        def set_state(model, object_id: str, attribute: str, value: object) -> None:
            with application.state.database.session_factory() as session:
                item = session.get(model, UUID(object_id))
                assert item is not None
                setattr(item, attribute, value)
                session.commit()

        set_state(Child, north_child["id"], "is_active", False)
        assert (
            client.get(
                f"/api/v1/children/{north_child['id']}/photo",
                headers=educator_headers,
            ).status_code
            == 404
        )
        set_state(Child, north_child["id"], "is_active", True)

        set_state(Room, rooms[0]["id"], "is_active", False)
        assert (
            client.get(
                f"/api/v1/children/{north_child['id']}/photo",
                headers=educator_headers,
            ).status_code
            == 404
        )
        set_state(Room, rooms[0]["id"], "is_active", True)

        set_state(Facility, facility["id"], "status", "inactive")
        assert (
            client.get(
                f"/api/v1/children/{north_child['id']}/photo",
                headers=educator_headers,
            ).status_code
            == 404
        )
