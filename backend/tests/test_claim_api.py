from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.config import Settings
from app.main import create_app


def test_claim_simulation_rest_endpoint_accepts_camel_case_contract(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
    )
    application = create_app(settings)
    application.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        organization_id=uuid4()
    )
    body = {
        "month": 1,
        "year": 2024,
        "capacity": 20,
        "operatingHours": 10,
        "seed": "api-parity",
        "children": [
            {
                "id": "child-1",
                "name": "Test Child",
                "birthDate": "2020-01-01",
                "familyId": "family-1",
                "ageGroup": "preschool",
            }
        ],
    }
    with TestClient(application) as client:
        response = client.post("/api/v1/claims/simulate", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["total_claims"] == 1
    assert payload["claims"][0]["child_id"] == "child-1"
    assert payload["claims"][0]["projected_hours"] > 0
    assert payload["fairness_report"]["overall_score"] >= 0
