from __future__ import annotations

import posixpath
from typing import Any


TIER_RANK = {"quick": 1, "standard": 2, "deep": 3}


def _resource_locks(task: dict[str, Any]) -> list[str]:
    values = task.get("resource_locks")
    if not isinstance(values, list):
        return []
    normalized = set()
    for value in values:
        lock = str(value or "").strip()
        if lock.startswith("path:"):
            path = posixpath.normpath(lock[5:].replace("\\", "/"))
            if path in {"", ".", ".."} or path.startswith("../"):
                continue
            lock = f"path:{path}"
        if lock:
            normalized.add(lock)
    return sorted(normalized)


def _resource_conflict(left: str, right: str) -> bool:
    if left == right:
        return True
    if left.startswith("path:") and right.startswith("path:"):
        first, second = left[5:].rstrip("/"), right[5:].rstrip("/")
        return first.startswith(second + "/") or second.startswith(first + "/")
    return False


def select_dispatch_batch(
    tasks: list[dict[str, Any]],
    *,
    active_tasks: list[dict[str, Any]] | None = None,
    global_limit: int = 5,
) -> dict[str, Any]:
    """Reserve complete resource sets for a bounded concurrent dispatch batch.

    Domains define ownership and review context, not a mutex. Each selected
    task acquires its sorted resource set atomically, so it never waits while
    holding only part of its required resources.
    """

    if (not isinstance(tasks, list) or isinstance(global_limit, bool)
            or not isinstance(global_limit, int) or not 1 <= global_limit <= 32):
        return {"status": "UNKNOWN", "reason": "DISPATCH_INPUT_INVALID",
                "selected": [], "blocked_task_ids": []}
    active = [task for task in (active_tasks or []) if isinstance(task, dict)]
    occupied: list[str] = []
    unknown = []
    for task in active:
        locks = _resource_locks(task)
        if not locks:
            unknown.append(str(task.get("task_id") or "UNKNOWN"))
        occupied.extend(locks)
    if unknown:
        return {
            "status": "UNKNOWN", "reason": "ACTIVE_RESOURCE_UNKNOWN",
            "selected": [], "blocked_task_ids": [],
            "unknown_active_task_ids": unknown,
            "global_limit": global_limit,
        }

    slots = max(0, global_limit - len(active))
    selected = []
    blocked = []
    unresolved = []
    candidates = sorted(
        tasks,
        key=lambda task: (str(task.get("domain_id") or ""),
                          str(task.get("task_id") or "")),
    )
    for task in candidates:
        if len(selected) >= slots:
            break
        if task.get("status") != "QUEUED" or task.get("dispatch_ready") is not True:
            continue
        task_id = str(task.get("task_id") or "").strip()
        if not task_id or not str(task.get("domain_id") or "").strip():
            unresolved.append(task_id or "UNKNOWN")
            continue
        locks = _resource_locks(task)
        if not locks:
            unresolved.append(task_id)
            continue
        if any(_resource_conflict(lock, held) for lock in locks for held in occupied):
            blocked.append(task_id)
            continue
        occupied.extend(locks)
        selected.append({
            "task_id": task_id,
            "domain_id": str(task["domain_id"]),
            "resource_locks": locks,
            "acquisition": "ATOMIC_SORTED",
        })
    return {
        "status": "READY" if selected else "STOP",
        "reason": "DISPATCH_READY" if selected else "NO_TASK_SELECTED",
        "selected": selected,
        "blocked_task_ids": blocked,
        "unresolved_task_ids": unresolved,
        "global_limit": global_limit,
        "available_slots": max(0, slots - len(selected)),
    }


def _route_meets(task: dict[str, Any], route: dict[str, Any]) -> bool:
    required_tier = TIER_RANK.get(str(task.get("complexity", "standard")))
    route_tier = TIER_RANK.get(str(route.get("tier", "")))
    if required_tier is None or route_tier is None or route_tier < required_tier:
        return False
    required_capabilities = set(task.get("required_capabilities", []))
    if not required_capabilities.issubset(set(route.get("capabilities", []))):
        return False
    required_tokens = int(task.get("estimated_context_tokens", 0) or 0)
    return bool(route.get("available")) and int(route.get("max_context_tokens", 0)) >= required_tokens


def select_execution_route(
    task: dict[str, Any],
    routes: list[dict[str, Any]],
    *,
    requested_route: str | None = None,
) -> dict[str, Any]:
    """Choose the smallest available execution route that meets task requirements."""

    if requested_route is not None:
        matches = [route for route in routes if route.get("route") == requested_route]
        if len(matches) != 1:
            return {"status": "UNKNOWN", "reason": "ROUTE_NOT_FOUND"}
        selected = matches[0]
        if not _route_meets(task, selected):
            return {"status": "BLOCKED", "reason": "ROUTE_REQUIREMENTS_NOT_MET"}
        selection = "manual"
    else:
        candidates = [route for route in routes if _route_meets(task, route)]
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
        "task_id": task.get("task_id"),
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
