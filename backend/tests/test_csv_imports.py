import csv
from io import StringIO

from app.api.v1.csv_imports import _detect, _merge, _parse_csv


def _sample_csv() -> str:
    output = StringIO()
    fields = [
        "Child Name",
        "Start Date",
        "Birth Date",
        "Sex",
        "Address",
        "Mother Name",
        "Mother Phone",
        "Mother Email",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    common = {
        "Start Date": "Jan 2 2026",
        "Address": "123 Main St, Edmonton AB T5A 1A1",
        "Mother Name": "Sumatra Ali",
        "Mother Phone": "7805551212",
        "Mother Email": "parent@example.com",
    }
    writer.writerow(
        {**common, "Child Name": "Amal Ali", "Birth Date": "Jun 25 2021", "Sex": "Female"}
    )
    writer.writerow(
        {**common, "Child Name": "Yusuf Ali", "Birth Date": "Aug 12 2022", "Sex": "Male"}
    )
    return output.getvalue()


def test_csv_parser_and_sibling_detection_preserve_children() -> None:
    parsed = _parse_csv(_sample_csv())

    assert parsed["totalRows"] == 2
    assert parsed["families"][0]["children"][0]["dateOfBirth"] == "2021-06-25"
    matches = _detect(parsed["families"])
    assert matches[0]["familyIndices"] == [0, 1]
    assert matches[0]["confidenceScore"] == 95

    merged = _merge(parsed["families"], [[0, 1]])
    assert len(merged) == 1
    assert len(merged[0]["children"]) == 2
