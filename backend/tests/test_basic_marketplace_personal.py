from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.basic.models import BasicBase
from app.core.config import Settings
from app.main import create_app

PASSWORD = "secure-password-123"


def _client(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="personal-profile-test-secret-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application)


def _register(client, email):
    response = client.post(
        "/api/v1/marketplace/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Private",
            "last_name": "Candidate",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _png():
    value = BytesIO()
    Image.new("RGB", (1200, 800), "purple").save(value, "PNG")
    return value.getvalue()


def test_profile_completion_guard_and_private_personal_update(tmp_path):
    client = _client(tmp_path)
    headers = _register(client, "personal@example.test")
    initial = client.get("/api/v1/marketplace/personal-profile", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["profile_complete"] is False
    assert initial.json()["missing_profile_fields"] == ["date_of_birth", "phone"]
    blocked = client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=headers,
        json={"candidate_type": "student"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == {
        "code": "profile_incomplete",
        "missing_profile_fields": ["date_of_birth", "phone"],
    }
    partial = client.patch(
        "/api/v1/marketplace/personal-profile",
        headers=headers,
        json={"date_of_birth": "1998-04-03"},
    )
    assert partial.json()["missing_profile_fields"] == ["phone"]
    completed = client.patch(
        "/api/v1/marketplace/personal-profile",
        headers=headers,
        json={"phone": "+1 (780) 555-0123"},
    )
    assert completed.status_code == 200 and completed.json()["profile_complete"] is True
    allowed = client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=headers,
        json={"candidate_type": "student"},
    )
    assert allowed.status_code == 200


def test_secure_email_change_rotates_session_and_refreshes_verification(tmp_path):
    client = _client(tmp_path)
    headers = _register(client, "change-old@example.test")
    _register(client, "already-used@example.test")
    wrong = client.post(
        "/api/v1/marketplace/personal-profile/email",
        headers=headers,
        json={"new_email": "new@example.test", "current_password": "wrong-password"},
    )
    assert wrong.status_code == 401
    duplicate = client.post(
        "/api/v1/marketplace/personal-profile/email",
        headers=headers,
        json={"new_email": "already-used@example.test", "current_password": PASSWORD},
    )
    assert duplicate.status_code == 409
    changed = client.post(
        "/api/v1/marketplace/personal-profile/email",
        headers=headers,
        json={"new_email": "CHANGE-NEW@example.test", "current_password": PASSWORD},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["email"] == "change-new@example.test"
    assert body["email_verification_method"] == "temporary_auto_approval"
    assert body["email_verified_at"] is not None and body["changed"] is True
    assert client.get("/api/v1/marketplace/personal-profile", headers=headers).status_code == 401
    new_headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert (
        client.get("/api/v1/marketplace/personal-profile", headers=new_headers).status_code == 200
    )


def test_candidate_photo_is_normalized_private_and_deletable(tmp_path):
    client = _client(tmp_path)
    first = _register(client, "photo-first@example.test")
    second = _register(client, "photo-second@example.test")
    uploaded = client.put(
        "/api/v1/marketplace/personal-profile/photo",
        headers=first,
        files={"file": ("../portrait.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    metadata = uploaded.json()
    assert metadata["content_type"] == "image/jpeg"
    assert metadata["original_filename"] == "portrait.png"
    assert metadata["created"] is True
    own = client.get("/api/v1/marketplace/personal-profile/photo", headers=first)
    assert own.status_code == 200 and own.headers["cache-control"] == "private, no-store"
    assert own.headers["content-type"].startswith("image/jpeg")
    assert (
        client.get("/api/v1/marketplace/personal-profile/photo", headers=second).status_code == 404
    )
    bad = client.put(
        "/api/v1/marketplace/personal-profile/photo",
        headers=first,
        files={"file": ("fake.png", b"not an image", "image/png")},
    )
    assert bad.status_code == 422
    removed = client.delete("/api/v1/marketplace/personal-profile/photo", headers=first)
    assert removed.status_code == 204
    assert (
        client.get("/api/v1/marketplace/personal-profile/photo", headers=first).status_code == 404
    )
