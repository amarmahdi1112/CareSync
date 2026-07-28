"""Authentication compatibility tests."""

from datetime import datetime
from uuid import uuid4

import bcrypt
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import Base, Permission, Role, User


def _build_client(tmp_path) -> TestClient:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        jwt_secret="test-only-secret-with-at-least-32-bytes",
    )
    application = create_app(settings)
    Base.metadata.create_all(application.state.database.engine)
    with application.state.database.session_factory() as session:
        permission = Permission(name="users:read", description="Read users")
        role = Role(name="Administrator", description="Test role", permissions=[permission])
        user = User(
            id=uuid4(),
            email="admin@example.com",
            password=bcrypt.hashpw(b"correct-password", bcrypt.gensalt(rounds=4)).decode(),
            first_name="Test",
            last_name="Admin",
            provider="local",
            role=role,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(user)
        session.commit()
    return TestClient(application)


def test_login_and_current_user(tmp_path) -> None:
    with _build_client(tmp_path) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "ADMIN@example.com", "password": "correct-password"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        current_user = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert current_user.status_code == 200
    assert current_user.json()["email"] == "admin@example.com"
    assert current_user.json()["role"]["permissions"][0]["name"] == "users:read"


def test_login_rejects_invalid_password(tmp_path) -> None:
    with _build_client(tmp_path) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "wrong"},
        )

    assert response.status_code == 401


def test_register_profile_and_password_workflow(tmp_path) -> None:
    with _build_client(tmp_path) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "password": "initial-password",
                "first_name": "New",
                "last_name": "User",
            },
        )
        assert registered.status_code == 201
        token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        updated = client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"first_name": "Updated"},
        )
        assert updated.status_code == 200
        assert updated.json()["first_name"] == "Updated"

        changed = client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={
                "current_password": "initial-password",
                "new_password": "replacement-password",
            },
        )
        assert changed.status_code == 204
        relogin = client.post(
            "/api/v1/auth/login",
            json={"email": "new@example.com", "password": "replacement-password"},
        )
        assert relogin.status_code == 200


def test_change_password_rejects_wrong_current_password(tmp_path) -> None:
    with _build_client(tmp_path) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "correct-password"},
        )
        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
            json={"current_password": "wrong-password", "new_password": "replacement-password"},
        )

    assert response.status_code == 401
