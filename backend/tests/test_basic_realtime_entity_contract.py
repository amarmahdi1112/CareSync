"""Executable backend/frontend vocabulary contract for realtime invalidations."""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
CONTRACT_PATH = REPOSITORY_ROOT / "contracts" / "realtime_entity_contract.json"
PRODUCER_ROOTS = (
    BACKEND_ROOT / "app" / "api" / "basic",
    BACKEND_ROOT / "app" / "basic",
)


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _module_constants(tree: ast.Module) -> dict[str, str]:
    values: dict[str, str] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        value = statement.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for target in targets:
            if isinstance(target, ast.Name):
                values[target.id] = value.value
    return values


def _string_value(node: ast.expr | None, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


class _ProducerVisitor(ast.NodeVisitor):
    """Collect organization-stream entity names and reject untracked forwarding."""

    _POSITIONAL_ENTITY_ARGUMENT = {"_event": 3, "_record": 4}
    _KEYWORD_ENTITY_ARGUMENT = {
        "audit": "entity_type",
        "AuditEvent": "entity_type",
        "AtsEvent": "entity_type",
        "RealtimeEvent": "entity_type",
        "_store_event": "entity_type",
        "_realtime": "entity_type",
        "_record": "target_type",
    }
    _FORWARDERS = {
        ("AuditEvent", "audit"),
        ("audit", "_store_event"),
        ("AtsEvent", "_event"),
        ("AtsEvent", "_record"),
        ("AtsEvent", "record_hiring_event"),
        ("RealtimeEvent", "_realtime"),
        ("audit", "_record"),
    }

    def __init__(self, path: Path, constants: dict[str, str]) -> None:
        self.path = path
        self.constants = constants
        self.function_stack: list[str] = []
        self.entities: set[str] = set()
        self.unresolved: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _call_name(node)
        entity_node: ast.expr | None = None
        if name in self._POSITIONAL_ENTITY_ARGUMENT:
            index = self._POSITIONAL_ENTITY_ARGUMENT[name]
            if len(node.args) > index:
                entity_node = node.args[index]
        elif name in self._KEYWORD_ENTITY_ARGUMENT:
            argument_name = self._KEYWORD_ENTITY_ARGUMENT[name]
            entity_node = next(
                (
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == argument_name
                ),
                None,
            )
        if entity_node is not None:
            value = _string_value(entity_node, self.constants)
            parent = self.function_stack[-1] if self.function_stack else "<module>"
            if value is not None:
                self.entities.add(value)
            elif (name, parent) not in self._FORWARDERS:
                self.unresolved.append(f"{self.path}:{node.lineno} {parent} -> {name}")
        self.generic_visit(node)


def _producer_entities() -> tuple[set[str], list[str]]:
    entities: set[str] = set()
    unresolved: list[str] = []
    for root in PRODUCER_ROOTS:
        for path in sorted(root.rglob("*.py")):
            # ExFAT mirrors can materialize macOS AppleDouble metadata beside
            # source files as binary `._*.py` entries. They are not Python
            # modules and must never participate in the producer inventory.
            if path.name.startswith("._") or path.name in {"models.py", "schemas.py"}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            visitor = _ProducerVisitor(path, _module_constants(tree))
            visitor.visit(tree)
            entities.update(visitor.entities)
            unresolved.extend(visitor.unresolved)
    return entities, unresolved


def test_basic_command_entity_names_match_the_frontend_contract() -> None:
    contract = _contract()
    canonical = set(contract["organization_outbox_entity_types"])
    suppressed = set(contract["command_entity_types_suppressed_from_generic_outbox"])
    aliases = contract["bridge_input_aliases"]
    trigger_only = set(contract["database_trigger_only_entity_types"])
    forbidden = set(contract["forbidden_phantom_entity_types"])
    produced, unresolved = _producer_entities()
    normalized = {aliases.get(entity, entity) for entity in produced}

    assert unresolved == [], "New dynamic producer needs an explicit, bounded contract"
    assert produced.isdisjoint(forbidden)
    assert normalized <= canonical | suppressed, (
        "Backend command producer entity names are not represented by the canonical "
        f"frontend contract: {sorted(normalized - canonical - suppressed)}"
    )
    assert canonical - normalized == trigger_only


def test_retained_transactional_bridges_preserve_command_entity_names() -> None:
    contract = _contract()
    migration = (BACKEND_ROOT / "alembic" / "versions" / "0011_realtime_outbox.py").read_text(
        encoding="utf-8"
    )

    assert contract["retained_runtime_revision"] == "0039_admissions_decision_spine"
    assert migration.count("CREATE TRIGGER audit_events_realtime AFTER INSERT ON audit_events") == 2
    assert migration.count("CREATE TRIGGER ats_events_realtime AFTER INSERT ON ats_events") == 2
    assert "NEW.action, NEW.entity_type, NEW.entity_id" in migration
    assert "NEW.event_type, NEW.entity_type, NEW.entity_id" in migration


def test_staged_authority_revision_trigger_emits_the_canonical_head_entity() -> None:
    migration = (
        BACKEND_ROOT / "alembic" / "versions" / "0029B_release_context.py"
    ).read_text(encoding="utf-8")

    assert migration.count("'child_authority_head', NULL") == 3
    assert "'release_context', NULL" not in migration
    assert migration.count("'scope', 'release_context'") == 3


def test_batch_placement_has_no_fake_realtime_entity() -> None:
    contract = _contract()
    assert "enrollment_batch" in contract["forbidden_phantom_entity_types"]
    assert "enrollment" in contract["organization_outbox_entity_types"]
