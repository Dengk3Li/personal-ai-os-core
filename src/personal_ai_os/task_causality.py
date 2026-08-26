"""Privacy-safe causal handoff contract for a task's next executor.

The contract connects opaque references in the order ``inputs -> action ->
artifacts -> downstream -> next action``.  It deliberately carries no task
body, free-text explanation, local path, business label, model payload or
credential.  Validation is pure and does not read or write runtime state.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


TASK_CAUSALITY_VERSION = "personal-ai-os.task-causality/v1"

_FIELDS = frozenset(
    {
        "schema_version",
        "task_ref",
        "inputs",
        "current_action",
        "artifacts",
        "downstream",
        "next_action",
    }
)
_REFERENCE_FIELDS = frozenset({"ref", "status"})
_ACTION_FIELDS = frozenset({"ref", "status", "run_ref"})
_DOWNSTREAM_FIELDS = frozenset({"ref", "relation", "status"})
_STATES = frozenset(
    {
        "PENDING",
        "AVAILABLE",
        "CREATED",
        "IN_PROGRESS",
        "READY",
        "BLOCKED",
        "DONE",
        "ARCHIVED",
        "MISSING",
        "REJECTED",
        "UNKNOWN",
    }
)
_RELATIONS = frozenset({"BLOCKS", "ENABLES", "INFORMS", "TRIGGERS", "FOLLOWS"})
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _supported_fields(value: Mapping[str, Any], allowed: frozenset[str], field: str) -> None:
    if not set(value).issubset(allowed):
        raise ValueError(f"{field} contains unsupported fields")


def _reference(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an opaque reference")
    normalized = value.strip()
    if not _REFERENCE.fullmatch(normalized):
        raise ValueError(f"{field} must be an opaque reference")
    return normalized


def _state(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a supported state")
    normalized = value.upper().strip()
    if normalized not in _STATES:
        raise ValueError(f"{field} must be a supported state")
    return normalized


def _reference_item(value: Any, field: str) -> dict[str, str]:
    item = _mapping(value, field)
    _supported_fields(item, _REFERENCE_FIELDS, field)
    return {
        "ref": _reference(item.get("ref"), f"{field} reference"),
        "status": _state(item.get("status", "UNKNOWN"), f"{field} status"),
    }


def _reference_list(value: Any, field: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError(f"{field} must be a bounded list")
    result = [_reference_item(item, field) for item in value]
    if len({item["ref"] for item in result}) != len(result):
        raise ValueError(f"{field} references must be unique")
    return result


def _current_action(value: Any) -> dict[str, str]:
    action = _mapping(value, "current action")
    _supported_fields(action, _ACTION_FIELDS, "current action")
    result = {
        "ref": _reference(action.get("ref"), "current action reference"),
        "status": _state(action.get("status"), "current action status"),
    }
    if "run_ref" in action:
        result["run_ref"] = _reference(action["run_ref"], "current action run reference")
    return result


def _downstream(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("downstream must be a bounded list")
    result: list[dict[str, str]] = []
    for item in value:
        downstream = _mapping(item, "downstream item")
        _supported_fields(downstream, _DOWNSTREAM_FIELDS, "downstream item")
        relation = str(downstream.get("relation") or "").upper().strip()
        if relation not in _RELATIONS:
            raise ValueError("downstream relation is unsupported")
        result.append(
            {
                "ref": _reference(downstream.get("ref"), "downstream reference"),
                "relation": relation,
                "status": _state(downstream.get("status", "UNKNOWN"), "downstream status"),
            }
        )
    if len({item["ref"] for item in result}) != len(result):
        raise ValueError("downstream references must be unique")
    return result


def _next_action(value: Any) -> dict[str, str]:
    action = _mapping(value, "next action")
    _supported_fields(action, _REFERENCE_FIELDS, "next action")
    return {
        "ref": _reference(action.get("ref"), "next action reference"),
        "status": _state(action.get("status", "PENDING"), "next action status"),
    }


def validate_task_causality(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a references-only ``TaskCausality/v1`` record.

    The returned record is safe to hand to another executor or a browser
    projection.  It has no free-text fields and validation has no side
    effects.
    """

    record = _mapping(payload, "task causality record")
    _supported_fields(record, _FIELDS, "task causality record")
    if record.get("schema_version") != TASK_CAUSALITY_VERSION:
        raise ValueError("unsupported task causality schema")
    return {
        "schema_version": TASK_CAUSALITY_VERSION,
        "task_ref": _reference(record.get("task_ref"), "task reference"),
        "inputs": _reference_list(record.get("inputs"), "inputs"),
        "current_action": _current_action(record.get("current_action")),
        "artifacts": _reference_list(record.get("artifacts"), "artifacts"),
        "downstream": _downstream(record.get("downstream")),
        "next_action": _next_action(record.get("next_action")),
    }
