"""Explicit organization selection for identities with multiple staff memberships."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.basic.models import BasicBase, Organization, OrganizationMembership, Role, User
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
        jwt_secret="multi-org-context-secret-with-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _register(client, email, organization_name):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Multi",
            "last_name": "Tenant",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_multi_membership_discovery_login_and_header_selection(tmp_path) -> None:
    client, application = _client(tmp_path)
    first = _register(client, "multi@example.test", "First Centre")
    second = _register(client, "second-owner@example.test", "Second Centre")
    first_org = first["user"]["organization_id"]
    second_org = second["user"]["organization_id"]
    with application.state.database.session_factory() as session:
        user = session.scalar(select(User).where(User.email == "multi@example.test"))
        organization = session.get(Organization, UUID(second_org))
        role = session.scalar(
            select(Role).where(Role.organization_id == organization.id, Role.key == "educator")
        )
        session.add(
            OrganizationMembership(
                id=uuid4(),
                organization_id=organization.id,
                user_id=user.id,
                role_id=role.id,
                status="active",
            )
        )
        session.commit()

    headers = {"Authorization": f"Bearer {first['access_token']}"}
    choices = client.get("/api/v1/auth/organizations", headers=headers)
    assert choices.status_code == 200, choices.text
    assert choices.json()["selection_required"] is True
    assert {item["organization_id"] for item in choices.json()["organizations"]} == {
        first_org,
        second_org,
    }
    assert all(
        item["request_header"] == {
            "name": "X-Organization-ID",
            "value": item["organization_id"],
        }
        for item in choices.json()["organizations"]
    )

    ambiguous = client.get("/api/v1/auth/me", headers=headers)
    assert ambiguous.status_code == 409
    for organization_id in (first_org, second_org):
        selected = client.get(
            "/api/v1/auth/me",
            headers={**headers, "X-Organization-ID": organization_id},
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["organization_id"] == organization_id

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "multi@example.test", "password": PASSWORD},
    )
    assert login.status_code == 409
    assert login.json()["detail"]["code"] == "organization_selection_required"
    selected_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "multi@example.test",
            "password": PASSWORD,
            "organization_id": second_org,
        },
    )
    assert selected_login.status_code == 200, selected_login.text
    assert selected_login.json()["user"]["organization_id"] == second_org
