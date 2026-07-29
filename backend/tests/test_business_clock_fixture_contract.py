"""Keep integration fixtures on explicit business or UTC clocks."""

from __future__ import annotations

import ast
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent


def test_test_fixtures_do_not_use_the_runner_local_calendar() -> None:
    violations: list[str] = []
    for path in sorted(TEST_ROOT.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value
            if not isinstance(owner, ast.Name) or owner.id not in {"date", "datetime"}:
                continue
            if node.func.attr == "today" or (
                owner.id == "datetime"
                and node.func.attr == "now"
                and not node.args
                and not any(keyword.arg == "tz" for keyword in node.keywords)
            ):
                violations.append(f"{path.relative_to(TEST_ROOT)}:{node.lineno}")

    assert violations == [], (
        "Test fixtures must use an explicit UTC or organization/facility timezone; "
        f"runner-local clock calls found at {', '.join(violations)}"
    )
