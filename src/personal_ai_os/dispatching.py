from __future__ import annotations

from collections.abc import Mapping
from typing import Any


TIER_RANK = {"quick": 1, "standard": 2, "deep": 3}
_ROUTING_FIELDS = frozenset({"estimated_context_tokens"})
_RUNTIME_BINDING_FIELDS = frozenset({"adapter_id", "model", "route", "executor"})


def task_route_requirements(task: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the task-owned route requirements without runtime bindings.

    A task declares only the work it needs. Adapter and model identities belong
    to the server-owned route catalog and are deliberately rejected when they
    appear in a task declaration.
    """
    if not isinstance(task, Mapping):
        return {"status": "BLOCKED", "reason": "ROUTING_REQUIREMENTS_INVALID"}
    forbidden = sorted(_RUNTIME_BINDING_FIELDS.intersection(task))
    if forbidden:
        return {
            "status": "BLOCKED",
            "reason": "ROUTING_BINDING_NOT_ALLOWED",
            "field": forbidden[0],
        }

    complexity = str(task.get("complexity") or "standard").strip()
    capabilities = task.get("required_capabilities", [])
    if complexity not in TIER_RANK or not isinstance(capabilities, list):
        return {"status": "BLOCKED", "reason": "ROUTING_REQUIREMENTS_INVALID"}
    if any(not isinstance(item, str) or not item.strip() for item in capabilities):
        return {"status": "BLOCKED", "reason": "ROUTING_REQUIREMENTS_INVALID"}

    context = task.get("context") or {}
    if not isinstance(context, Mapping):
        return {"status": "BLOCKED", "reason": "ROUTING_REQUIREMENTS_INVALID"}
    routing = context.get("routing")
    if routing is not None:
        if not isinstance(routing, Mapping):
            return {"status": "BLOCKED", "reason": "ROUTING_REQUIREMENTS_INVALID"}
        unknown = sorted(set(routing) - _ROUTING_FIELDS)
        if unknown:
            return {
                "status": "BLOCKED",
                "reason": "ROUTING_FIELD_NOT_ALLOWED",
                "field": unknown[0],
            }
        estimated_tokens = routing.get("estimated_context_tokens", 0)
    else:
        # Keep the public pure function compatible with the original v0.9
        # task shape while preferring the namespaced declaration above.
        estimated_tokens = task.get("estimated_context_tokens", 0)
    if type(estimated_tokens) is not int or estimated_tokens < 0:
        return {"status": "BLOCKED", "reason": "ROUTING_REQUIREMENTS_INVALID"}

    return {
        "status": "RESOLVED",
        "task_id": task.get("task_id"),
        "complexity": complexity,
        "required_capabilities": [item.strip() for item in capabilities],
        "estimated_context_tokens": estimated_tokens,
    }


def _route_meets(requirements: Mapping[str, Any], route: dict[str, Any]) -> bool:
    required_tier = TIER_RANK.get(str(requirements.get("complexity", "standard")))
    route_tier = TIER_RANK.get(str(route.get("tier", "")))
    if required_tier is None or route_tier is None or route_tier < required_tier:
        return False
    required_capabilities = set(requirements.get("required_capabilities", []))
    if not required_capabilities.issubset(set(route.get("capabilities", []))):
        return False
    required_tokens = int(requirements.get("estimated_context_tokens", 0) or 0)
    return bool(route.get("available")) and int(route.get("max_context_tokens", 0)) >= required_tokens


def select_execution_route(
    task: dict[str, Any],
    routes: list[dict[str, Any]],
    *,
    requested_route: str | None = None,
) -> dict[str, Any]:
    """Choose the smallest available execution route that meets task requirements."""

    requirements = task_route_requirements(task)
    if requirements["status"] != "RESOLVED":
        return requirements

    if requested_route is not None:
        matches = [route for route in routes if route.get("route") == requested_route]
        if len(matches) != 1:
            return {"status": "UNKNOWN", "reason": "ROUTE_NOT_FOUND"}
        selected = matches[0]
        if not _route_meets(requirements, selected):
            return {"status": "BLOCKED", "reason": "ROUTE_REQUIREMENTS_NOT_MET"}
        selection = "manual"
    else:
        candidates = [route for route in routes if _route_meets(requirements, route)]
        if not candidates:
            return {"status": "UNKNOWN", "reason": "ROUTE_NOT_FOUND"}
        selected = min(
            candidates,
            key=lambda route: (
                TIER_RANK[str(route["tier"])],
                int(route["max_context_tokens"]),
                str(route["route"]),
            ),
        )
        selection = "automatic"

    return {
        **selected,
        "status": "RESOLVED",
        "selection": selection,
        "task_id": requirements.get("task_id"),
    }


def assign_task(
    task: dict[str, Any],
    route: dict[str, Any],
    executors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assign one routed task to a compatible executor with free capacity."""

    if route.get("status") != "RESOLVED":
        return {"status": "WAITING_ASSIGNMENT", "reason": "ROUTE_REQUIRED"}
    required = set(task.get("required_capabilities", []))
    route_id = route.get("route")
    candidates = []
    for executor in executors:
        capacity = int(executor.get("capacity", 0))
        active = int(executor.get("active_tasks", 0))
        if capacity <= active:
            continue
        if not required.issubset(set(executor.get("capabilities", []))):
            continue
        if route_id not in executor.get("supported_routes", []):
            continue
        candidates.append(executor)
    if not candidates:
        return {"status": "WAITING_ASSIGNMENT", "reason": "NO_COMPATIBLE_CAPACITY"}

    selected = min(
        candidates,
        key=lambda executor: (
            int(executor.get("active_tasks", 0)) / int(executor["capacity"]),
            int(executor.get("active_tasks", 0)),
            str(executor.get("executor", "")),
        ),
    )
    return {
        "status": "ASSIGNED",
        "task_id": task.get("task_id"),
        "executor": selected["executor"],
        "route": route_id,
    }
