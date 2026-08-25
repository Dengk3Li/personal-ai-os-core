from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "personal-ai-os.workflow-structure/v1"
NODE_KINDS = {"task", "sequence", "branch", "join", "if", "loop"}
TERMINAL_STATES = {"DONE", "ARCHIVED"}
_PREDICATE_REF = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"workflow structure {field} is required")
    return text


def _predicate_ref(value: Any, field: str) -> str:
    reference = _required_text(value, field)
    if not _PREDICATE_REF.fullmatch(reference):
        raise ValueError(f"{field} must reference a registered predicate")
    return reference


def _normalize_node(
    node: Any, seen: set[str], task_ids: set[str]
) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise ValueError("workflow node must be an object")
    node_id = _required_text(node.get("node_id"), "node_id")
    if node_id in seen:
        raise ValueError(f"duplicate workflow node: {node_id}")
    seen.add(node_id)
    kind = _required_text(node.get("kind"), "kind")
    if kind not in NODE_KINDS:
        raise ValueError(f"unsupported workflow node kind: {kind}")
    normalized: dict[str, Any] = {"node_id": node_id, "kind": kind}

    if kind == "task":
        task_id = _required_text(node.get("task_id"), "task_id")
        if task_id in task_ids:
            raise ValueError(f"duplicate workflow task: {task_id}")
        task_ids.add(task_id)
        normalized["task_id"] = task_id
        return normalized

    if kind in {"sequence", "branch", "join"}:
        children = node.get("children")
        if not isinstance(children, list) or not children:
            raise ValueError(f"{kind} children must be a non-empty list")
        normalized["children"] = [
            _normalize_node(child, seen, task_ids) for child in children
        ]
        if kind == "join":
            policy = str(node.get("policy") or "all").strip().lower()
            if policy not in {"all", "any"}:
                raise ValueError("join policy must be all or any")
            normalized["policy"] = policy
        return normalized

    if kind == "if":
        normalized["condition_ref"] = _predicate_ref(
            node.get("condition_ref"), "condition_ref"
        )
        branches = node.get("branches")
        if not isinstance(branches, dict) or set(branches) != {"true", "false"}:
            raise ValueError("if branches must contain true and false")
        normalized["branches"] = {
            branch: _normalize_node(branches[branch], seen, task_ids)
            for branch in ("true", "false")
        }
        return normalized

    normalized["continue_condition_ref"] = _predicate_ref(
        node.get("continue_condition_ref"), "continue_condition_ref"
    )
    max_iterations = node.get("max_iterations")
    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool) or not 1 <= max_iterations <= 100:
        raise ValueError("loop max_iterations must be an integer from 1 to 100")
    normalized["max_iterations"] = max_iterations
    normalized["body"] = _normalize_node(node.get("body"), seen, task_ids)
    return normalized


def _flatten(node: dict[str, Any], parent_id: str | None, rows: list[dict[str, Any]]) -> None:
    row = {key: deepcopy(value) for key, value in node.items() if key not in {"children", "branches", "body"}}
    row["parent_id"] = parent_id
    rows.append(row)
    if node["kind"] in {"sequence", "branch", "join"}:
        for child in node["children"]:
            _flatten(child, node["node_id"], rows)
    elif node["kind"] == "if":
        for child in node["branches"].values():
            _flatten(child, node["node_id"], rows)
    elif node["kind"] == "loop":
        _flatten(node["body"], node["node_id"], rows)


def compile_workflow_structure(structure: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(structure, dict):
        raise ValueError("workflow structure must be an object")
    if structure.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported workflow structure schema")
    root = _normalize_node(structure.get("root"), set(), set())
    nodes: list[dict[str, Any]] = []
    _flatten(root, None, nodes)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "READY",
        "root": root,
        "nodes": nodes,
    }


def _evaluate(
    node: dict[str, Any],
    task_states: dict[str, str],
    predicates: dict[str, bool],
    loop_iterations: dict[str, int],
) -> dict[str, Any]:
    kind = node["kind"]
    if kind == "task":
        state = str(task_states.get(node["task_id"], "QUEUED")).upper()
        if state in TERMINAL_STATES:
            return {"ready": [], "waiting": [], "repeat": [], "complete": True}
        if state == "QUEUED":
            return {
                "ready": [node["task_id"]],
                "waiting": [],
                "repeat": [],
                "complete": False,
            }
        return {"ready": [], "waiting": [], "repeat": [], "complete": False}

    if kind == "sequence":
        for child in node["children"]:
            result = _evaluate(child, task_states, predicates, loop_iterations)
            if not result["complete"]:
                return result
        return {"ready": [], "waiting": [], "repeat": [], "complete": True}

    if kind in {"branch", "join"}:
        results = [
            _evaluate(child, task_states, predicates, loop_iterations)
            for child in node["children"]
        ]
        policy = node.get("policy", "all")
        complete = (
            all(item["complete"] for item in results)
            if policy == "all"
            else any(item["complete"] for item in results)
        )
        if complete:
            return {"ready": [], "waiting": [], "repeat": [], "complete": True}
        return {
            "ready": [task for item in results for task in item["ready"]],
            "waiting": [decision for item in results for decision in item["waiting"]],
            "repeat": [loop for item in results for loop in item["repeat"]],
            "complete": False,
        }

    if kind == "if":
        reference = node["condition_ref"]
        if reference not in predicates or not isinstance(predicates[reference], bool):
            return {
                "ready": [],
                "waiting": [node["node_id"]],
                "repeat": [],
                "complete": False,
            }
        branch = "true" if predicates[reference] is True else "false"
        return _evaluate(node["branches"][branch], task_states, predicates, loop_iterations)

    completed_iterations = int(loop_iterations.get(node["node_id"], 0))
    if completed_iterations >= node["max_iterations"]:
        return {"ready": [], "waiting": [], "repeat": [], "complete": True}
    reference = node["continue_condition_ref"]
    if reference not in predicates or not isinstance(predicates[reference], bool):
        return {
            "ready": [],
            "waiting": [node["node_id"]],
            "repeat": [],
            "complete": False,
        }
    if predicates[reference] is not True:
        return {"ready": [], "waiting": [], "repeat": [], "complete": True}
    body = _evaluate(node["body"], task_states, predicates, loop_iterations)
    if body["complete"]:
        return {
            "ready": [],
            "waiting": [],
            "repeat": [node["node_id"]],
            "complete": False,
        }
    return body


def evaluate_workflow_structure(
    compiled: dict[str, Any],
    task_states: dict[str, str],
    *,
    predicates: dict[str, bool] | None = None,
    loop_iterations: dict[str, int] | None = None,
) -> dict[str, Any]:
    if compiled.get("schema_version") != SCHEMA_VERSION or compiled.get("status") != "READY":
        raise ValueError("workflow structure must be compiled before evaluation")
    iterations = dict(loop_iterations or {})
    loop_limits = {
        node["node_id"]: node["max_iterations"]
        for node in compiled.get("nodes", [])
        if node.get("kind") == "loop"
    }
    for node_id, value in iterations.items():
        if (
            node_id not in loop_limits
            or not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= loop_limits[node_id]
        ):
            raise ValueError(f"loop iteration is invalid: {node_id}")
    result = _evaluate(
        compiled["root"],
        dict(task_states),
        dict(predicates or {}),
        iterations,
    )
    return {
        "status": "READY",
        "ready_task_ids": result["ready"],
        "waiting_decision_ids": result["waiting"],
        "repeat_loop_ids": result["repeat"],
        "complete": result["complete"],
    }
