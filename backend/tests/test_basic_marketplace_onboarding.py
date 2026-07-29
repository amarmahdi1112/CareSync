from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from app.api.basic.marketplace_onboarding import _certificate_proposal
from app.basic.models import BasicBase
from app.core.config import Settings
from app.main import create_app

PASSWORD = "secure-password-123"


def test_camera_viewer_label_is_not_part_of_certificate_holder_name():
    proposal, _ = _certificate_proposal(
        [
            {"text": "This confirms that", "confidence": 0.99},
            {"text": "JPEG image HIDAYA GALMO", "confidence": 0.97},
            {"text": "Certificate Number: 948472", "confidence": 0.98},
        ],
        "HIDAYA GALMO",
    )
    assert proposal["normalized_proposal"]["holder_name"] == "HIDAYA GALMO"
    assert proposal["holder_name_mismatch"] is False


def test_ocr_upeg_variant_is_removed_without_hiding_a_real_name_mismatch():
    proposal, _ = _certificate_proposal(
        [
            {"text": "Name: UPEG image Different Person", "confidence": 0.96},
            {"text": "Certificate Number: 123456", "confidence": 0.98},
        ],
        "HIDAYA GALMO",
    )
    assert proposal["normalized_proposal"]["holder_name"] == "Different Person"
    assert proposal["holder_name_mismatch"] is True


def test_ocr_pegr_text_variant_is_removed_from_certificate_holder_name():
    proposal, _ = _certificate_proposal(
        [
            {"text": "This confirms that", "confidence": 0.99},
            {"text": "PEGr text HIDAYA GALMO", "confidence": 0.97},
            {"text": "Certificate Number: 948472", "confidence": 0.98},
        ],
        "HIDAYA GALMO",
    )
    assert proposal["normalized_proposal"]["holder_name"] == "HIDAYA GALMO"
    assert proposal["holder_name_mismatch"] is False


def test_certificate_fields_can_be_reassembled_from_separate_ocr_lines():
    proposal, confidences = _certificate_proposal(
        [
            {"text": "This confirms that", "confidence": 0.99},
            {"text": "HIDAYA", "confidence": 0.98},
            {"text": "GALMO", "confidence": 0.97},
            {"text": "Certificate Number:", "confidence": 0.99},
            {"text": "948472", "confidence": 0.96},
        ],
        "HIDAYA GALMO",
    )
    assert proposal["normalized_proposal"]["holder_name"] == "HIDAYA GALMO"
    assert proposal["normalized_proposal"]["certificate_number"] == "948472"
    assert proposal["required_fields_complete"] is True
    assert confidences["holder_name"] == 0.97
    assert confidences["certificate_number"] == 0.96


def _client(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=tmp_path / "caresync.db",
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="onboarding-test-secret-with-at-least-thirty-two-bytes",
    )
    application = create_app(settings)
    BasicBase.metadata.create_all(application.state.database.engine)
    return TestClient(application), application


def _candidate(client, email="candidate@example.test"):
    response = client.post(
        "/api/v1/marketplace/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Candidate",
            "last_name": "User",
        },
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    personal = client.patch(
        "/api/v1/marketplace/personal-profile",
        headers=headers,
        json={"date_of_birth": "1994-03-15", "phone": "+1 780 555 0188"},
    )
    assert personal.status_code == 200, personal.text
    return headers


def _png():
    value = BytesIO()
    Image.new("RGB", (600, 400), "white").save(value, "PNG")
    return value.getvalue()


def _upload(client, headers, kind="certificate"):
    response = client.post(
        "/api/v1/marketplace/onboarding/documents",
        headers=headers,
        data={"document_kind": kind},
        files={"file": ("scan.png", _png(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_ocr_proposal_confirmation_manual_work_and_completion(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    headers = _candidate(client)
    me = client.get("/api/v1/marketplace/me", headers=headers).json()
    assert (me["first_name"], me["last_name"]) == ("Candidate", "User")
    client.put(
        "/api/v1/marketplace/profile",
        headers=headers,
        json={"city": "Edmonton", "headline": "Educator", "work_history": []},
    )
    selected = client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=headers,
        json={"candidate_type": "certified_educator"},
    )
    assert selected.status_code == 200 and selected.json()["current_step"] == "certificate"
    uploaded = _upload(client, headers)

    monkeypatch.setattr(
        "app.api.basic.marketplace_onboarding.run_local_ocr",
        lambda _path: {
            "model": "PP-OCRv6_tiny_det+PP-OCRv6_tiny_rec",
            "lines": [
                {"text": "Name: Different Person", "confidence": 0.98},
                {"text": "Alberta Child Care Staff Certification Level 2", "confidence": 0.95},
                {"text": "Certificate Number: AB-12345", "confidence": 0.96},
                {"text": "Expiry: 2030-01-01", "confidence": 0.94},
            ],
        },
    )
    analyzed = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/analyze", headers=headers
    )
    assert analyzed.status_code == 200, analyzed.text
    result = analyzed.json()
    assert result["proposal_is_authoritative"] is False
    assert result["raw_document_retained"] is False
    assert result["proposal"]["normalized_proposal"]["holder_name"] == "Different Person"
    assert result["proposal"]["holder_name_mismatch"] is True
    assert result["field_confidences"]["holder_name"] == 0.98

    unresolved = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/confirm-certificate",
        headers=headers,
        json={
            "certificate_type": "Alberta Level 2",
            "certificate_number": "AB-CORRECTED",
            "expiry_date": "2030-01-01",
        },
    )
    assert unresolved.status_code == 409
    arbitrary = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/confirm-certificate",
        headers=headers,
        json={
            "certificate_type": "Alberta Level 2",
            "certificate_number": "AB-CORRECTED",
            "expiry_date": "2030-01-01",
            "mismatch_resolution": "ignore_mismatch",
        },
    )
    assert arbitrary.status_code == 422
    confirmed = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/confirm-certificate",
        headers=headers,
        json={
            "certificate_type": "Alberta Level 2",
            "certificate_number": "AB-CORRECTED",
            "expiry_date": "2030-01-01",
            "mismatch_resolution": "use_certificate_name",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    me_after = client.get("/api/v1/marketplace/me", headers=headers).json()
    assert (me_after["first_name"], me_after["last_name"]) == ("Different", "Person")
    manual = client.post(
        "/api/v1/marketplace/onboarding/work-history/confirm-manual",
        headers=headers,
        json={"work_history": []},
    )
    assert manual.status_code == 200, manual.text
    assert set(manual.json()["completed_steps"]) == {"certificate", "work_experience"}
    completed = client.post("/api/v1/marketplace/onboarding/complete", headers=headers)
    assert completed.status_code == 200 and completed.json()["status"] == "complete"
    saved = client.put(
        "/api/v1/marketplace/profile",
        headers=headers,
        json={
            "city": "Edmonton",
            "headline": "Lead Educator",
            "certification_type": "Alberta Level 2",
            "certification_number": "AB-CORRECTED",
            "certification_expiry_date": "2030-01-01",
            "work_history": [],
        },
    )
    assert saved.status_code == 200
    profile = client.get("/api/v1/marketplace/profile", headers=headers).json()
    assert profile["certification_verification_status"] == "unverified"
    assert profile["certification_provenance"] == "local_ocr"
    assert profile["work_history_provenance"] == "manual"

    upgrade = _upload(client, headers)
    upgraded_analysis = client.post(
        f"/api/v1/marketplace/onboarding/documents/{upgrade['id']}/analyze", headers=headers
    )
    assert upgraded_analysis.status_code == 200, upgraded_analysis.text
    upgraded = client.post(
        f"/api/v1/marketplace/onboarding/documents/{upgrade['id']}/confirm-certificate",
        headers=headers,
        json={
            "certificate_type": "Alberta Level 3",
            "certificate_number": "AB-LEVEL-3",
            "expiry_date": "2032-01-01",
        },
    )
    assert upgraded.status_code == 200, upgraded.text
    assert upgraded.json()["status"] == "complete"
    credentials = client.get(
        "/api/v1/marketplace/onboarding/credentials", headers=headers
    ).json()
    assert [(row["version_number"], row["status"], row["is_current"]) for row in credentials] == [
        (2, "confirmed", True),
        (1, "superseded", False),
    ]
    content = client.get(credentials[0]["content_url"], headers=headers)
    assert content.status_code == 200
    assert content.content == _png()
    assert content.headers["cache-control"] == "private, no-store"


def test_reject_certificate_result_is_owned_and_does_not_persist(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    first = _candidate(client, "reject-first@example.test")
    second = _candidate(client, "reject-second@example.test")
    client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=first,
        json={"candidate_type": "certified_educator"},
    )
    uploaded = _upload(client, first)
    monkeypatch.setattr(
        "app.api.basic.marketplace_onboarding.run_local_ocr",
        lambda _path: {
            "model": "test",
            "lines": [
                {"text": "Name: Someone Else", "confidence": 0.99},
                {"text": "Certificate Number: AB-999", "confidence": 0.95},
            ],
        },
    )
    analyzed = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/analyze", headers=first
    )
    assert analyzed.status_code == 200
    hidden = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/reject-certificate-result",
        headers=second,
    )
    assert hidden.status_code == 404
    rejected = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/reject-certificate-result",
        headers=first,
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["current_step"] == "certificate" and "certificate" not in body["completed_steps"]
    row = next(item for item in body["analyses"] if item["id"] == uploaded["id"])
    assert row["status"] == "discarded" and row["failure_code"] == "candidate_rejected_result"
    profile = client.get("/api/v1/marketplace/profile", headers=first).json()
    assert profile["certification_number"] is None


def test_document_validation_and_candidate_ownership(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    first = _candidate(client, "first@example.test")
    second = _candidate(client, "second@example.test")
    client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=first,
        json={"candidate_type": "certified_educator"},
    )
    bad = client.post(
        "/api/v1/marketplace/onboarding/documents",
        headers=first,
        data={"document_kind": "certificate"},
        files={"file": ("fake.pdf", _png(), "application/pdf")},
    )
    assert bad.status_code == 415
    pdf = BytesIO()
    writer = PdfWriter()
    for _ in range(6):
        writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    too_many = client.post(
        "/api/v1/marketplace/onboarding/documents",
        headers=first,
        data={"document_kind": "resume"},
        files={"file": ("resume.pdf", pdf.getvalue(), "application/pdf")},
    )
    assert too_many.status_code == 422
    uploaded = _upload(client, first)
    monkeypatch.setattr(
        "app.api.basic.marketplace_onboarding.run_local_ocr",
        lambda _path: {"model": "test", "lines": []},
    )
    hidden = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/analyze", headers=second
    )
    assert hidden.status_code == 404
    own = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/analyze", headers=first
    )
    assert own.status_code == 422
    assert "both the certificate holder name and certificate number" in own.json()["detail"]
    retry = _upload(client, first)
    assert retry["status"] == "uploaded" and retry["id"] != uploaded["id"]


def test_alberta_certificate_layout_extracts_holder_level_and_number(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    headers = _candidate(client)
    client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=headers,
        json={"candidate_type": "certified_educator"},
    )
    uploaded = _upload(client, headers)
    observed_suffix = None

    def fake_ocr(path):
        nonlocal observed_suffix
        observed_suffix = path.suffix
        return {
            "model": (
                "fusion:PP-OCRv6_tiny_det+PP-OCRv6_tiny_rec|"
                "PP-OCRv5_mobile_det+latin_PP-OCRv5_mobile_rec"
            ),
            "vision": {"version": "4.10.0", "pipeline": "document-v2-fused"},
            "lines": [
                {"text": "Level 2_10674...", "confidence": 0.9837},
                {"text": "ALBERTA CHILDCARE", "confidence": 0.9876},
                {"text": "STAFF CERTIFICATION", "confidence": 0.9933},
                {"text": "This confirms that", "confidence": 0.9982},
                {"text": "HIDAYA GALMO", "confidence": 0.9969},
                {"text": "LEVEL 2", "confidence": 0.9810},
                {"text": "EARLY CHILDHOOD EDUCATOR", "confidence": 0.9759},
                {"text": "Certificate Number:948472", "confidence": 0.9955},
                {"text": "Jul 13,2026", "confidence": 0.9234},
                {"text": "Date Granted", "confidence": 0.9912},
            ],
        }

    monkeypatch.setattr(
        "app.api.basic.marketplace_onboarding.run_local_ocr",
        fake_ocr,
    )

    analyzed = client.post(
        f"/api/v1/marketplace/onboarding/documents/{uploaded['id']}/analyze",
        headers=headers,
    )
    assert analyzed.status_code == 200, analyzed.text
    proposal = analyzed.json()["proposal"]
    assert proposal["normalized_proposal"]["holder_name"] == "HIDAYA GALMO"
    assert proposal["normalized_proposal"]["certificate_type"] == "LEVEL 2"
    assert proposal["normalized_proposal"]["certificate_number"] == "948472"
    assert proposal["holder_name_mismatch"] is True
    assert len(analyzed.json()["ocr_model"]) <= 80
    assert observed_suffix == ".png"


def test_student_branch_and_certified_manual_bypass_are_enforced(tmp_path):
    client, _ = _client(tmp_path)
    student = _candidate(client, "student@example.test")
    initial = client.get("/api/v1/marketplace/onboarding", headers=student).json()
    assert initial["candidate_type"] is None and initial["current_step"] == "candidate_type"
    assert (
        client.post("/api/v1/marketplace/onboarding/complete", headers=student).status_code == 409
    )
    selected = client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=student,
        json={"candidate_type": "student"},
    )
    assert selected.status_code == 200 and selected.json()["current_step"] == "student_details"
    assert _certificate_upload_status(client, student) == 409
    student_certificate = client.put(
        "/api/v1/marketplace/profile",
        headers=student,
        json={
            "city": "Edmonton",
            "headline": "ELCC student",
            "certification_type": "Level 1",
            "certification_number": "NOT-ALLOWED",
            "work_history": [],
        },
    )
    assert student_certificate.status_code == 422
    invalid = client.post(
        "/api/v1/marketplace/onboarding/student-details/confirm",
        headers=student,
        json={
            "institution": "NorQuest College",
            "program": "Early Learning and Child Care",
            "expected_graduation_date": "2020-01-01",
        },
    )
    assert invalid.status_code == 422
    details = client.post(
        "/api/v1/marketplace/onboarding/student-details/confirm",
        headers=student,
        json={
            "institution": "NorQuest College",
            "program": "Early Learning and Child Care",
            "expected_graduation_date": "2028-06-30",
        },
    )
    assert details.status_code == 200 and "student_details" in details.json()["completed_steps"]
    client.put(
        "/api/v1/marketplace/profile",
        headers=student,
        json={"city": "Edmonton", "headline": "ELCC student", "work_history": []},
    )
    completed = client.post("/api/v1/marketplace/onboarding/complete", headers=student)
    assert completed.status_code == 200
    assert completed.json()["candidate_type"] == "student"

    certified = _candidate(client, "manual-cert@example.test")
    client.post(
        "/api/v1/marketplace/onboarding/candidate-type",
        headers=certified,
        json={"candidate_type": "certified_educator"},
    )
    client.put(
        "/api/v1/marketplace/profile",
        headers=certified,
        json={
            "city": "Edmonton",
            "headline": "Educator",
            "certification_type": "Level 2",
            "certification_number": "MANUAL-1",
            "work_history": [],
        },
    )
    client.post(
        "/api/v1/marketplace/onboarding/work-history/confirm-manual",
        headers=certified,
        json={"work_history": []},
    )
    bypass = client.post("/api/v1/marketplace/onboarding/complete", headers=certified)
    assert bypass.status_code == 409


def _certificate_upload_status(client, headers):
    return client.post(
        "/api/v1/marketplace/onboarding/documents",
        headers=headers,
        data={"document_kind": "certificate"},
        files={"file": ("scan.png", _png(), "image/png")},
    ).status_code
