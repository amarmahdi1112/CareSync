from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.claim_imports import _match_claims, _name_variants


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _statement):
        return SimpleNamespace(mappings=lambda: self.rows)


def child(first: str, last: str, *, middle: str | None = None, dob: date | None = None):
    return {
        "id": uuid4(),
        "first_name": first,
        "middle_name": middle,
        "last_name": last,
        "date_of_birth": dob or date(2020, 1, 1),
    }


def claim(name: str, dob: str | None = None):
    return {
        "pdfName": name,
        "dateOfBirth": dob,
        "matchedChildId": None,
        "matchedChildName": None,
        "suggestManualReview": True,
        "reason": "",
        "confidence": "none",
        "score": 0,
    }


def test_name_variants_support_last_comma_first_and_middle_names() -> None:
    assert "aafia mahmud" in _name_variants("MAHMUD, Aafia")
    assert "aafia mahmud" in _name_variants("Aafia Noor Mahmud")
    assert _name_variants("MAHMUD Aafia") & _name_variants("Aafia Mahmud")


def test_pdf_names_receive_unique_exact_and_high_confidence_matches() -> None:
    exact_child = child("Aafia", "Mahmud", middle="Noor", dob=date(2020, 4, 3))
    fuzzy_child = child("Abdurahman", "Hadish")
    results = _match_claims(
        [claim("MAHMUD, Aafia Noor", "2020-04-03"), claim("Abdurahmn Hadish")],
        uuid4(),
        FakeSession([exact_child, fuzzy_child]),
    )

    assert results[0]["matchedChildId"] == str(exact_child["id"])
    assert results[0]["confidence"] == "exact"
    assert results[1]["matchedChildId"] == str(fuzzy_child["id"])
    assert results[1]["confidence"] == "high"


def test_ambiguous_names_stay_unmatched_without_dob_disambiguation() -> None:
    results = _match_claims(
        [claim("Ali Ali")],
        uuid4(),
        FakeSession([child("Ali", "Ali"), child("Ali", "Ali")]),
    )

    assert results[0]["matchedChildId"] is None
    assert results[0]["suggestManualReview"] is True
