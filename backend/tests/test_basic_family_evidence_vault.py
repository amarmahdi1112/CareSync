"""Focused acceptance coverage for the 0029A1 private evidence vault."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject
from sqlalchemy import func, select
from starlette.datastructures import Headers

import app.api.basic.family_authority as authority_api
import app.basic.family_evidence_vault as vault
from app.basic.family_evidence_vault import (
    MalwareScanResult,
    ScannerUnavailable,
    read_private_object,
    scan_private_object,
    store_private_upload,
)
from app.basic.models import (
    ChildcareCommandReceipt,
    FamilyAuthorityEvidence,
    FamilyAuthorityEvidenceObject,
)
from app.core.config import BACKEND_ROOT, Settings
from app.core.evidence_upload_limit import EvidenceUploadLimitMiddleware
from tests.test_basic_family_authority_api import (
    _client,
    _family,
    _register,
    _role_headers,
)


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (3, 2), (28, 111, 176)).save(output, format="PNG")
    return output.getvalue()


def _active_pdf_bytes() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.root_object[NameObject("/OpenAction")] = DictionaryObject(
        {
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject("app.alert('active')"),
        }
    )
    writer.write(output)
    return output.getvalue()


def _safe_pdf_bytes() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


def _outline_active_pdf_bytes() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    outline = writer.add_outline_item("Hidden action", 0).get_object()
    outline.pop("/Dest", None)
    outline[NameObject("/A")] = DictionaryObject(
        {
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject("app.alert('outline')"),
        }
    )
    writer.write(output)
    return output.getvalue()


def _vault_client(tmp_path, monkeypatch):
    root = tmp_path / "private-vault"
    monkeypatch.setenv("FAMILY_EVIDENCE_VAULT_PATH", str(root))
    client, application = _client(tmp_path, monkeypatch)
    return client, application, root


def _upload(
    client,
    headers: dict[str, str],
    family_id: str,
    *,
    operation_id: str | None = None,
    evidence_kind: str = "custody_document",
    content: bytes | None = None,
    media_type: str = "image/png",
    filename: str = "custody.png",
    extra: dict[str, str] | None = None,
):
    payload = {
        "client_operation_id": operation_id or str(uuid4()),
        "evidence_kind": evidence_kind,
        **(extra or {}),
    }
    return client.post(
        f"/api/v1/families/{family_id}/authority/evidence-objects",
        headers=headers,
        data=payload,
        files={"file": (filename, _png_bytes() if content is None else content, media_type)},
    )


def _scan(client, headers, family_id: str, object_id: str, operation_id: str | None = None):
    return client.post(
        f"/api/v1/families/{family_id}/authority/evidence-objects/{object_id}/scan",
        headers=headers,
        json={
            "client_operation_id": operation_id or str(uuid4()),
            "expected_version": 1,
        },
    )


def _clean_scan(_: Path, __: Settings) -> MalwareScanResult:
    return MalwareScanResult(
        decision="clean",
        scanner_engine="clamdscan",
        scanner_version="ClamAV 1.4.3",
        scanner_signature=None,
        reason_code=None,
    )


def test_full_vault_flow_exact_replay_private_download_and_maker_checker(
    tmp_path, monkeypatch
) -> None:
    client, application, root = _vault_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", _clean_scan)
    with client:
        auth, owner_headers = _register(client, "VaultFlow")
        family = _family(client, owner_headers, "Vault Flow Family")
        operation_id = str(uuid4())
        content = _png_bytes()
        rejected_claims = _upload(
            client,
            owner_headers,
            family["id"],
            operation_id=operation_id,
            content=content,
            filename="../../Custody\u202e.png",
            extra={
                "storage_reference": "client/owned/key",
                "content_sha256": "0" * 64,
                "byte_size": "999999",
                "status": "clean",
            },
        )
        assert rejected_claims.status_code == 422
        assert rejected_claims.json()["detail"]["code"] == ("unexpected_evidence_upload_fields")
        assert not root.exists()

        uploaded = _upload(
            client,
            owner_headers,
            family["id"],
            operation_id=operation_id,
            content=content,
            filename="../../Custody\u202e.png",
        )
        assert uploaded.status_code == 201, uploaded.text
        first = uploaded.json()
        object_id = first["resource"]["id"]
        assert first["replayed"] is False
        assert first["resource"]["lifecycle_status"] == "quarantined"
        assert first["resource"]["version"] == 1
        assert first["resource"]["byte_size"] == len(content)
        assert first["resource"]["content_sha256"] == hashlib.sha256(content).hexdigest()
        assert first["resource"]["original_filename"] == "Custody_.png"
        assert "storage_reference" not in first["resource"]
        assert first["receipt"]["command_type"] == ("family.authority.evidence_object.upload")
        assert first["receipt"]["committed_version"] == 1

        files = list(root.rglob("v1.png"))
        assert len(files) == 1
        assert files[0].read_bytes() == content
        assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
        assert stat.S_IMODE(root.stat().st_mode) == 0o700

        replay = _upload(
            client,
            owner_headers,
            family["id"],
            operation_id=operation_id,
            content=content,
            filename="../../Custody\u202e.png",
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["resource"]["id"] == object_id
        assert replay.json()["receipt"] == first["receipt"]
        assert len(list(root.rglob("v1.png"))) == 1

        changed_retry = _upload(
            client,
            owner_headers,
            family["id"],
            operation_id=operation_id,
            content=_png_bytes() + b"changed",
            filename="../../Custody\u202e.png",
        )
        assert changed_retry.status_code == 409
        assert changed_retry.json()["detail"]["code"] == "operation_reused"
        assert len(list(root.rglob("v1.png"))) == 1

        quarantined_download = client.get(
            f"/api/v1/families/{family['id']}/authority/evidence-objects/{object_id}/download",
            headers=owner_headers,
        )
        assert quarantined_download.status_code == 409

        scan_operation = str(uuid4())
        scanned = _scan(client, owner_headers, family["id"], object_id, scan_operation)
        assert scanned.status_code == 200, scanned.text
        assert scanned.json()["resource"]["lifecycle_status"] == "clean"
        assert scanned.json()["resource"]["version"] == 2
        assert scanned.json()["receipt"]["command_type"] == (
            "family.authority.evidence_object.scan"
        )
        scan_replay = _scan(client, owner_headers, family["id"], object_id, scan_operation)
        assert scan_replay.status_code == 200, scan_replay.text
        assert scan_replay.json()["replayed"] is True
        assert scan_replay.json()["resource"] == scanned.json()["resource"]
        assert scan_replay.json()["receipt"] == scanned.json()["receipt"]

        downloaded = client.get(
            f"/api/v1/families/{family['id']}/authority/evidence-objects/{object_id}/download",
            headers=owner_headers,
        )
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == content
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert downloaded.headers["content-disposition"].startswith("attachment;")
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert "Custody" not in downloaded.headers["content-disposition"]

        recorded = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "evidence_kind": "custody_document",
                "source_label": "Observed custody document",
                "captured_at": "2026-07-17T00:00:00Z",
                "evidence_object_id": object_id,
            },
        )
        assert recorded.status_code == 201, recorded.text
        evidence_id = recorded.json()["resource"]["id"]
        assert recorded.json()["resource"]["evidence_object_id"] == object_id

        same_maker_review = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence_id}/review",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "assessed_epistemic_status": "document_observed",
            },
        )
        assert same_maker_review.status_code == 409
        assert same_maker_review.json()["detail"]["code"] == "maker_checker_required"

        _, administrator_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        reviewed = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence_id}/review",
            headers=administrator_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "assessed_epistemic_status": "document_observed",
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["resource"]["valid_now"] is True

        second_record = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "evidence_kind": "custody_document",
                "source_label": "Object cannot be consumed twice",
                "evidence_object_id": object_id,
            },
        )
        assert second_record.status_code == 409

        workspace = client.get(f"/api/v1/families/{family['id']}/authority", headers=owner_headers)
        assert workspace.status_code == 200, workspace.text
        assert [row["id"] for row in workspace.json()["evidence_objects"]] == [object_id]


@pytest.mark.parametrize(
    ("content", "media_type", "filename"),
    [
        (b"\x89PNG\r\n\x1a\nnot-a-real-image", "image/png", "bad.png"),
        (b"%PDF-1.4\nnot-a-real-pdf", "application/pdf", "bad.pdf"),
    ],
)
def test_scanner_runs_before_parser_and_malformed_documents_are_terminal_rejections(
    tmp_path, monkeypatch, content: bytes, media_type: str, filename: str
) -> None:
    client, _, root = _vault_client(tmp_path, monkeypatch)
    scanner_called = False

    def clean_after_observing_file(path, settings: Settings):
        nonlocal scanner_called
        assert read_private_object(path, settings.family_evidence_max_bytes) == content
        scanner_called = True
        return _clean_scan(path, settings)

    monkeypatch.setattr(
        "app.basic.family_evidence_objects.scan_private_object",
        clean_after_observing_file,
    )
    with client:
        _, headers = _register(client, "Malformed")
        family = _family(client, headers)
        uploaded = _upload(
            client,
            headers,
            family["id"],
            content=content,
            media_type=media_type,
            filename=filename,
        )
        assert uploaded.status_code == 201, uploaded.text
        scanned = _scan(client, headers, family["id"], uploaded.json()["resource"]["id"])
        assert scanner_called is True
        assert scanned.status_code == 200, scanned.text
        resource = scanned.json()["resource"]
        assert resource["lifecycle_status"] == "rejected"
        assert resource["current_assessment"]["reason_code"] == "invalid_document"
        assert len(list(root.rglob("v1.*"))) == 1


@pytest.mark.parametrize("content", [_active_pdf_bytes(), _outline_active_pdf_bytes()])
def test_active_pdf_structures_are_rejected_after_clean_scan(
    tmp_path, monkeypatch, content: bytes
) -> None:
    client, _, _ = _vault_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", _clean_scan)
    with client:
        _, headers = _register(client, "ActivePdf")
        family = _family(client, headers)
        uploaded = _upload(
            client,
            headers,
            family["id"],
            content=content,
            media_type="application/pdf",
            filename="active.pdf",
        )
        assert uploaded.status_code == 201, uploaded.text
        scanned = _scan(client, headers, family["id"], uploaded.json()["resource"]["id"])
        assert scanned.status_code == 200, scanned.text
        assert scanned.json()["resource"]["lifecycle_status"] == "rejected"
        assert scanned.json()["resource"]["current_assessment"]["reason_code"] == (
            "invalid_document"
        )


def test_isolated_parser_accepts_valid_png_and_pdf_and_timeout_fails_closed(
    tmp_path, monkeypatch
) -> None:
    png = tmp_path / "valid.png"
    pdf = tmp_path / "valid.pdf"
    png.write_bytes(_png_bytes())
    pdf.write_bytes(_safe_pdf_bytes())
    settings = Settings(_env_file=None, environment="test")
    vault.validate_scanned_document(png, "image/png", settings)
    vault.validate_scanned_document(pdf, "application/pdf", settings)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr(vault.subprocess, "run", timeout)
    with pytest.raises(HTTPException) as raised:
        vault.validate_scanned_document(png, "image/png", settings)
    assert raised.value.status_code == 422
    assert raised.value.detail == {"code": "invalid_evidence_document"}


def test_empty_archive_and_receive_level_oversize_are_rejected_before_private_storage(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FAMILY_EVIDENCE_MAX_BYTES", str(64 * 1024))
    client, _, root = _vault_client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client, "Bounded")
        family = _family(client, headers)
        empty = _upload(client, headers, family["id"], content=b"")
        assert empty.status_code == 422
        archive = _upload(
            client,
            headers,
            family["id"],
            content=b"PK\x03\x04" + b"x" * 100,
            media_type="application/zip",
            filename="archive.zip",
        )
        assert archive.status_code == 422
        oversized = _upload(
            client,
            headers,
            family["id"],
            content=b"\x89PNG\r\n\x1a\n" + b"x" * (400 * 1024),
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"]["code"] == "evidence_upload_body_too_large"
        boundary = "caresync-chunked-boundary"
        chunked_body = (
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="client_operation_id"\r\n\r\n'
                f"{uuid4()}\r\n"
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="evidence_kind"\r\n\r\n'
                "custody_document\r\n"
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="huge.png"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode()
            + b"x" * (400 * 1024)
            + f"\r\n--{boundary}--\r\n".encode()
        )
        chunked = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence-objects",
            headers={
                **headers,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            content=(
                chunked_body[index : index + 32 * 1024]
                for index in range(0, len(chunked_body), 32 * 1024)
            ),
        )
        assert chunked.status_code == 413, chunked.text
        assert chunked.json()["detail"]["code"] == "evidence_upload_body_too_large"
        assert list(root.rglob("v1.*")) == []


def test_chunked_receive_overflow_returns_typed_413_without_content_length() -> None:
    consumed = 0

    async def inner(scope, receive, send):
        nonlocal consumed
        while True:
            message = await receive()
            consumed += len(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = EvidenceUploadLimitMiddleware(inner, api_prefix="/api/v1", file_limit=1)
    messages = iter(
        [
            {
                "type": "http.request",
                "body": b"x" * (128 * 1024),
                "more_body": True,
            },
            {
                "type": "http.request",
                "body": b"x" * (129 * 1024),
                "more_body": False,
            },
        ]
    )
    sent: list[dict] = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/families/00000000/authority/evidence-objects",
                "headers": [],
            },
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 413
    assert consumed == 128 * 1024


def test_scanner_unavailable_rolls_back_scan_and_non_documents_never_reach_disk(
    tmp_path, monkeypatch
) -> None:
    client, application, root = _vault_client(tmp_path, monkeypatch)

    def unavailable(*_):
        raise ScannerUnavailable("malware_scanner_unavailable")

    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", unavailable)
    with client:
        _, headers = _register(client, "FailClosed")
        family = _family(client, headers)
        refused = _upload(
            client,
            headers,
            family["id"],
            evidence_kind="guardian_attestation",
        )
        assert refused.status_code == 422
        assert not root.exists()

        uploaded = _upload(client, headers, family["id"])
        assert uploaded.status_code == 201, uploaded.text
        object_id = uploaded.json()["resource"]["id"]
        scan_operation = str(uuid4())
        scanned = _scan(client, headers, family["id"], object_id, scan_operation)
        assert scanned.status_code == 503
        assert scanned.json()["detail"]["code"] == "malware_scanner_unavailable"
        with application.state.database.session_factory() as session:
            value = session.get(FamilyAuthorityEvidenceObject, UUID(object_id))
            assert value is not None and value.status == "quarantined"
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ChildcareCommandReceipt)
                    .where(ChildcareCommandReceipt.client_operation_id == UUID(scan_operation))
                )
                == 0
            )


def test_malware_rejection_retains_isolated_bytes_but_forbids_download(
    tmp_path, monkeypatch
) -> None:
    client, _, root = _vault_client(tmp_path, monkeypatch)

    def infected(_: Path, __: Settings) -> MalwareScanResult:
        return MalwareScanResult(
            decision="rejected",
            scanner_engine="clamdscan",
            scanner_version="ClamAV 1.4.3/28001/Fri Jul 17 11:00:00 2026",
            scanner_signature="Eicar-Signature",
            reason_code="malware_detected",
        )

    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", infected)
    with client:
        _, headers = _register(client, "Infected")
        family = _family(client, headers)
        uploaded = _upload(client, headers, family["id"])
        object_id = uploaded.json()["resource"]["id"]
        scanned = _scan(client, headers, family["id"], object_id)
        assert scanned.status_code == 200, scanned.text
        assert scanned.json()["resource"]["lifecycle_status"] == "rejected"
        assert scanned.json()["resource"]["current_assessment"]["reason_code"] == (
            "malware_detected"
        )
        assert len(list(root.rglob("v1.png"))) == 1
        download = client.get(
            f"/api/v1/families/{family['id']}/authority/evidence-objects/{object_id}/download",
            headers=headers,
        )
        assert download.status_code == 409


def test_tampered_clean_bytes_block_record_and_review(tmp_path, monkeypatch) -> None:
    client, application, root = _vault_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", _clean_scan)
    with client:
        auth, headers = _register(client, "Tamper")
        family = _family(client, headers)
        uploaded = _upload(client, headers, family["id"])
        object_id = uploaded.json()["resource"]["id"]
        assert _scan(client, headers, family["id"], object_id).status_code == 200
        stored_path = next(root.rglob("v1.png"))
        original = stored_path.read_bytes()
        stored_path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        payload = {
            "client_operation_id": str(uuid4()),
            "evidence_kind": "custody_document",
            "source_label": "Integrity checked",
            "evidence_object_id": object_id,
        }
        blocked_record = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=headers,
            json=payload,
        )
        assert blocked_record.status_code == 409
        assert blocked_record.json()["detail"]["code"] == ("evidence_object_integrity_failed")
        stored_path.write_bytes(original)
        payload["client_operation_id"] = str(uuid4())
        recorded = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=headers,
            json=payload,
        )
        assert recorded.status_code == 201, recorded.text
        _, reviewer_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        stored_path.write_bytes(original + b"tampered")
        blocked_review = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/"
            f"{recorded.json()['resource']['id']}/review",
            headers=reviewer_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "assessed_epistemic_status": "document_observed",
            },
        )
        assert blocked_review.status_code == 409
        assert blocked_review.json()["detail"]["code"] == ("evidence_object_integrity_failed")


@pytest.mark.parametrize("anomaly", ["missing", "symlink", "public_mode", "hardlink"])
def test_private_download_normalizes_storage_integrity_failures(
    tmp_path, monkeypatch, anomaly: str
) -> None:
    client, _, root = _vault_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", _clean_scan)
    with client:
        _, headers = _register(client, f"Integrity-{anomaly}")
        family = _family(client, headers)
        uploaded = _upload(client, headers, family["id"])
        object_id = uploaded.json()["resource"]["id"]
        assert _scan(client, headers, family["id"], object_id).status_code == 200
        stored_path = next(root.rglob("v1.png"))
        if anomaly == "missing":
            stored_path.unlink()
        elif anomaly == "symlink":
            external = tmp_path / "external.png"
            external.write_bytes(_png_bytes())
            external.chmod(0o600)
            stored_path.unlink()
            stored_path.symlink_to(external)
        elif anomaly == "public_mode":
            stored_path.chmod(0o644)
        else:
            os.link(stored_path, tmp_path / "second-link.png")

        response = client.get(
            f"/api/v1/families/{family['id']}/authority/evidence-objects/{object_id}/download",
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == ("evidence_object_integrity_failed")


def test_scan_pins_one_inode_and_rejects_a_concurrent_directory_entry_swap(
    tmp_path, monkeypatch
) -> None:
    client, application, root = _vault_client(tmp_path, monkeypatch)
    with client:
        _, headers = _register(client, "PinnedInode")
        family = _family(client, headers)
        uploaded = _upload(client, headers, family["id"])
        object_id = uploaded.json()["resource"]["id"]
        stored_path = next(root.rglob("v1.png"))
        original = stored_path.read_bytes()

        def swap_while_scanning(handle, _: Settings) -> MalwareScanResult:
            replacement = stored_path.with_name("replacement.png")
            replacement.write_bytes(_png_bytes() + b"replacement")
            replacement.chmod(0o600)
            os.replace(replacement, stored_path)
            assert os.pread(handle.descriptor, len(original), 0) == original
            return _clean_scan(handle, application.state.settings)

        monkeypatch.setattr(
            "app.basic.family_evidence_objects.scan_private_object",
            swap_while_scanning,
        )
        response = _scan(client, headers, family["id"], object_id)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == ("evidence_object_integrity_failed")
        with application.state.database.session_factory() as session:
            stored = session.get(FamilyAuthorityEvidenceObject, UUID(object_id))
            assert stored is not None and stored.status == "quarantined"


def test_vault_root_rejects_a_symlinked_ancestor_before_writing(tmp_path) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_vault_path=linked_parent / "vault",
    )
    upload = UploadFile(
        file=io.BytesIO(_png_bytes()),
        filename="proof.png",
        headers=Headers({"content-type": "image/png"}),
    )
    with pytest.raises(RuntimeError, match="unsafe path component"):
        asyncio.run(
            store_private_upload(
                upload,
                settings=settings,
                organization_id=uuid4(),
                family_id=uuid4(),
                object_id=uuid4(),
            )
        )
    assert not (real_parent / "vault").exists()


def test_admin_tenant_boundary_and_typed_precommit_cleanup(tmp_path, monkeypatch) -> None:
    client, application, root = _vault_client(tmp_path, monkeypatch)
    with client:
        first_auth, first_headers = _register(client, "FirstTenant")
        family = _family(client, first_headers)
        _, educator_headers = _role_headers(
            application,
            client,
            organization_id=first_auth["user"]["organization_id"],
            role_key="educator",
        )
        denied = _upload(client, educator_headers, family["id"])
        assert denied.status_code == 403
        assert not root.exists()

        _, second_headers = _register(client, "SecondTenant")
        hidden = _upload(client, second_headers, family["id"])
        assert hidden.status_code == 404
        assert list(root.rglob("v1.*")) == []


def test_attestation_review_also_requires_separate_recorder_and_reviewer(
    tmp_path, monkeypatch
) -> None:
    client, application, _ = _vault_client(tmp_path, monkeypatch)
    with client:
        auth, headers = _register(client, "Attestation")
        family = _family(client, headers)
        recorded = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "evidence_kind": "guardian_attestation",
                "source_label": "Guardian statement",
            },
        )
        assert recorded.status_code == 201, recorded.text
        evidence_id = recorded.json()["resource"]["id"]
        review_payload = {
            "client_operation_id": str(uuid4()),
            "expected_version": 1,
            "assessed_epistemic_status": "reported",
        }
        self_review = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence_id}/review",
            headers=headers,
            json=review_payload,
        )
        assert self_review.status_code == 409
        assert self_review.json()["detail"]["code"] == "maker_checker_required"
        _, reviewer_headers = _role_headers(
            application,
            client,
            organization_id=auth["user"]["organization_id"],
            role_key="administrator",
        )
        review_payload["client_operation_id"] = str(uuid4())
        reviewed = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence_id}/review",
            headers=reviewer_headers,
            json=review_payload,
        )
        assert reviewed.status_code == 200, reviewed.text


def test_wrong_advisory_media_and_cross_family_binding_are_rejected(tmp_path, monkeypatch) -> None:
    client, _, root = _vault_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", _clean_scan)
    with client:
        _, headers = _register(client, "Isolation")
        first_family = _family(client, headers, "First Family")
        second_family = _family(client, headers, "Second Family")
        mismatch = _upload(
            client,
            headers,
            first_family["id"],
            media_type="application/pdf",
        )
        assert mismatch.status_code == 422
        assert list(root.rglob("v1.*")) == []

        uploaded = _upload(client, headers, first_family["id"])
        assert uploaded.status_code == 201, uploaded.text
        object_id = uploaded.json()["resource"]["id"]
        scanned = _scan(client, headers, first_family["id"], object_id)
        assert scanned.status_code == 200, scanned.text
        cross_family = client.post(
            f"/api/v1/families/{second_family['id']}/authority/evidence",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "evidence_kind": "custody_document",
                "source_label": "Wrong family",
                "evidence_object_id": object_id,
            },
        )
        assert cross_family.status_code == 404


def test_ambiguous_post_commit_failure_keeps_adopted_private_object(tmp_path, monkeypatch) -> None:
    client, application, root = _vault_client(tmp_path, monkeypatch)
    original = authority_api.record_evidence_object_upload

    def committed_then_failed(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated response-path failure after commit")

    monkeypatch.setattr(authority_api, "record_evidence_object_upload", committed_then_failed)
    with client:
        _, headers = _register(client, "Adopted")
        family = _family(client, headers)
        with pytest.raises(RuntimeError, match="after commit"):
            _upload(client, headers, family["id"])
        files = list(root.rglob("v1.png"))
        assert len(files) == 1
        with application.state.database.session_factory() as session:
            assert (
                session.scalar(select(func.count()).select_from(FamilyAuthorityEvidenceObject)) == 1
            )


def test_private_publication_is_no_clobber_and_fsyncs_directories(tmp_path, monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_vault_path=tmp_path / "vault",
    )
    organization_id = uuid4()
    family_id = uuid4()
    object_id = uuid4()
    observed_directory_fsyncs = 0
    original_fsync = vault.os.fsync

    def recording_fsync(descriptor: int) -> None:
        nonlocal observed_directory_fsyncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            observed_directory_fsyncs += 1
        original_fsync(descriptor)

    monkeypatch.setattr(vault.os, "fsync", recording_fsync)
    first = UploadFile(
        file=io.BytesIO(_png_bytes()),
        filename="first.png",
        headers=Headers({"content-type": "image/png"}),
    )
    stored = asyncio.run(
        store_private_upload(
            first,
            settings=settings,
            organization_id=organization_id,
            family_id=family_id,
            object_id=object_id,
        )
    )
    final = settings.resolved_family_evidence_vault_path / stored.storage_reference
    original_bytes = final.read_bytes()
    second = UploadFile(
        file=io.BytesIO(b"\x89PNG\r\n\x1a\nreplacement"),
        filename="second.png",
        headers=Headers({"content-type": "image/png"}),
    )
    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            store_private_upload(
                second,
                settings=settings,
                organization_id=organization_id,
                family_id=family_id,
                object_id=object_id,
            )
        )
    assert raised.value.status_code == 409
    assert final.read_bytes() == original_bytes
    assert observed_directory_fsyncs >= 2


def test_post_link_failure_removes_unadopted_final_object(tmp_path, monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_vault_path=tmp_path / "vault",
    )
    organization_id = uuid4()
    family_id = uuid4()
    object_id = uuid4()
    original_fsync = vault.os.fsync
    failed_once = False
    object_directory = (
        settings.resolved_family_evidence_vault_path
        / organization_id.hex
        / family_id.hex
        / object_id.hex
    )

    def fail_final_publication_once(descriptor: int) -> None:
        nonlocal failed_once
        measured = os.fstat(descriptor)
        is_object_directory = (
            stat.S_ISDIR(measured.st_mode)
            and object_directory.exists()
            and measured.st_ino == object_directory.stat().st_ino
        )
        if is_object_directory and not failed_once:
            failed_once = True
            raise OSError("injected directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(vault.os, "fsync", fail_final_publication_once)
    upload = UploadFile(
        file=io.BytesIO(_png_bytes()),
        filename="failure.png",
        headers=Headers({"content-type": "image/png"}),
    )
    with pytest.raises(OSError, match="injected"):
        asyncio.run(
            store_private_upload(
                upload,
                settings=settings,
                organization_id=organization_id,
                family_id=family_id,
                object_id=object_id,
            )
        )
    assert list(object_directory.glob("v1.*")) == []
    assert list(object_directory.glob("*.uploading")) == []


@pytest.mark.parametrize(("returncode", "output"), [(1, "failed"), (0, "")])
def test_scanner_version_probe_fails_closed(
    tmp_path, monkeypatch, returncode: int, output: str
) -> None:
    binary = tmp_path / "clamscan"
    binary.touch(mode=0o700)
    target = tmp_path / "object.png"
    target.write_bytes(_png_bytes())
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_scanner_path=binary,
    )
    calls: list[list[str]] = []

    def fake_run(args, **_):
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode, stdout=output, stderr="")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    with pytest.raises(ScannerUnavailable, match="malware_scanner_failed"):
        scan_private_object(target, settings)
    assert calls == [[str(binary), "--version"]]


def test_clamdscan_fails_closed_without_daemon_limit_policy_attestation(
    tmp_path, monkeypatch
) -> None:
    binary = tmp_path / "clamdscan"
    binary.touch(mode=0o700)
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_scanner_path=binary,
    )
    monkeypatch.setattr(
        vault.subprocess,
        "run",
        lambda *_args, **_options: pytest.fail("clamdscan must not be executed"),
    )

    with pytest.raises(ScannerUnavailable, match="limit_policy_unverified"):
        scan_private_object(tmp_path / "object.png", settings)


def test_scanner_auto_discovery_prefers_enforceable_clamscan(tmp_path, monkeypatch) -> None:
    clamscan = tmp_path / "clamscan"
    clamdscan = tmp_path / "clamdscan"
    clamscan.touch(mode=0o700)
    clamdscan.touch(mode=0o700)
    discovered: list[str] = []

    def fake_which(name: str) -> str | None:
        discovered.append(name)
        return os.fspath(clamscan if name == "clamscan" else clamdscan)

    monkeypatch.setattr(vault.shutil, "which", fake_which)
    settings = Settings(_env_file=None, environment="test")

    assert vault._scanner_binary(settings) == clamscan.resolve()
    assert discovered == ["clamscan"]


def test_clamscan_streams_a_pinned_inode_through_stdin(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "clamscan"
    binary.touch(mode=0o700)
    target = tmp_path / "object.png"
    target.write_bytes(_png_bytes())
    target.chmod(0o600)
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_scanner_path=binary,
    )
    calls: list[tuple[list[str], dict]] = []
    monkeypatch.setattr(vault, "_now_utc", lambda: datetime(2026, 7, 17, 12, tzinfo=UTC))

    def fake_run(args, **options):
        calls.append((args, options))
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=("ClamAV 1.4.3/28001/Fri Jul 17 11:00:00 2026 /private/operator/path"),
                stderr="",
            )
        return subprocess.CompletedProcess(args, 0, stdout="stdin: OK", stderr="")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    descriptor = os.open(target, os.O_RDONLY)
    with vault.PrivateObjectHandle(descriptor, "synthetic/object.png") as handle:
        result = scan_private_object(handle, settings)
        scan_descriptor = handle.descriptor

    assert result.decision == "clean"
    assert calls[0][0] == [str(binary), "--version"]
    assert calls[1][0] == [
        str(binary),
        "--no-summary",
        "--alert-exceeds-max=yes",
        "-",
    ]
    assert calls[1][1]["stdin"] == scan_descriptor
    assert "pass_fds" not in calls[1][1]
    assert result.scanner_version == ("ClamAV 1.4.3/28001/Fri Jul 17 11:00:00 2026")


def test_scanner_rejects_stale_signature_database(tmp_path, monkeypatch) -> None:
    binary = tmp_path / "clamscan"
    binary.touch(mode=0o700)
    target = tmp_path / "object.png"
    target.write_bytes(_png_bytes())
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_scanner_path=binary,
        family_evidence_scanner_max_definition_age_hours=24,
    )
    monkeypatch.setattr(vault, "_now_utc", lambda: datetime(2026, 7, 17, 12, tzinfo=UTC))

    def fake_run(args, **_):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="ClamAV 1.4.3/27900/Wed Jul 15 11:00:00 2026",
            stderr="",
        )

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    with pytest.raises(ScannerUnavailable, match="definitions_stale"):
        scan_private_object(target, settings)


def test_scanner_rejects_unsafe_version_token_instead_of_persisting_it(
    tmp_path, monkeypatch
) -> None:
    binary = tmp_path / "clamscan"
    binary.touch(mode=0o700)
    target = tmp_path / "object.png"
    target.write_bytes(_png_bytes())
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_scanner_path=binary,
    )
    monkeypatch.setattr(
        vault.subprocess,
        "run",
        lambda args, **_options: subprocess.CompletedProcess(
            args,
            0,
            stdout=("ClamAV 1.4.3\x1b[31m/28001/Fri Jul 17 11:00:00 2026"),
            stderr="",
        ),
    )

    with pytest.raises(ScannerUnavailable, match="definitions_unverified"):
        scan_private_object(target, settings)


@pytest.mark.parametrize("outcome", ["timeout", "nonzero"])
def test_scanner_timeout_and_nonzero_scan_fail_closed(tmp_path, monkeypatch, outcome: str) -> None:
    binary = tmp_path / "clamscan"
    binary.touch(mode=0o700)
    target = tmp_path / "object.png"
    target.write_bytes(_png_bytes())
    settings = Settings(
        _env_file=None,
        environment="test",
        family_evidence_scanner_path=binary,
    )
    monkeypatch.setattr(vault, "_now_utc", lambda: datetime(2026, 7, 17, 12, tzinfo=UTC))
    calls = 0

    def fake_run(args, **_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout="ClamAV 1.4.3/28001/Fri Jul 17 11:00:00 2026",
                stderr="",
            )
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        return subprocess.CompletedProcess(args, 2, stdout="error", stderr="")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    with pytest.raises(ScannerUnavailable, match="malware_scanner_failed"):
        scan_private_object(target, settings)


def test_vault_root_cannot_be_inside_backend_source_tree(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        family_evidence_vault_path=BACKEND_ROOT / "storage" / "unsafe-vault",
    )
    with pytest.raises(ValueError, match="outside the backend source tree"):
        _ = settings.resolved_family_evidence_vault_path


def test_document_object_is_bound_to_only_one_evidence_row(tmp_path, monkeypatch) -> None:
    """Keep the partial unique index visible in portable ORM acceptance coverage."""

    client, application, _ = _vault_client(tmp_path, monkeypatch)
    monkeypatch.setattr("app.basic.family_evidence_objects.scan_private_object", _clean_scan)
    with client:
        _, headers = _register(client, "SingleUse")
        family = _family(client, headers)
        uploaded = _upload(client, headers, family["id"])
        object_id = uploaded.json()["resource"]["id"]
        assert _scan(client, headers, family["id"], object_id).status_code == 200
        payload = {
            "client_operation_id": str(uuid4()),
            "evidence_kind": "custody_document",
            "source_label": "Bound object",
            "evidence_object_id": object_id,
        }
        first = client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=headers,
            json=payload,
        )
        assert first.status_code == 201, first.text
        with application.state.database.session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(FamilyAuthorityEvidence)
                    .where(FamilyAuthorityEvidence.evidence_object_id == UUID(object_id))
                )
                == 1
            )
