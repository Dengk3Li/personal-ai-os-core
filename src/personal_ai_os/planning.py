from __future__ import annotations

from collections import Counter
from typing import Any


LANES = ("QUEUED", "IN_PROGRESS", "REVIEW", "DONE", "BLOCKED", "PAUSED")


def _has_cycle(edges: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> bool:
        if task_id in visiting:
            return True
        if task_id in visited:
            return False
        visiting.add(task_id)
        if any(visit(dependency) for dependency in edges.get(task_id, [])):
            return True
        visiting.remove(task_id)
        visited.add(task_id)
        return False

    return any(visit(task_id) for task_id in edges)


def validate_plan(
    goal: str,
    tasks: list[dict[str, Any]],
    *,
    plan_id: str = "plan:long-task",
) -> dict[str, Any]:
    """Validate an AI-proposed task graph before a human accepts it."""

    normalized = [
        {
            **task,
            "task_id": str(task.get("task_id", "")).strip(),
            "title": str(task.get("title", "")).strip(),
            "acceptance": str(task.get("acceptance", "")).strip(),
            "depends_on": [str(item) for item in task.get("depends_on", [])],
            "parent_id": task.get("parent_id"),
            "human_gate": bool(task.get("human_gate", False)),
        }
        for task in tasks
    ]
    findings: list[dict[str, Any]] = []
    if not str(goal).strip():
        findings.append({"code": "GOAL_REQUIRED"})
    if not normalized:
        findings.append({"code": "TASKS_REQUIRED"})

    identifiers = [task["task_id"] for task in normalized]
    id_counts = Counter(identifiers)
    for task in normalized:
        task_id = task["task_id"]
        if not task_id or not task["title"] or not task["acceptance"]:
            findings.append({"code": "TASK_FIELDS_REQUIRED", "task_id": task_id})
        if task_id and id_counts[task_id] > 1:
            findings.append({"code": "DUPLICATE_TASK_ID", "task_id": task_id})

    known = {task_id for task_id in identifiers if task_id}
    for task in normalized:
        for dependency in task["depends_on"]:
            if dependency not in known:
                findings.append(
                    {
                        "code": "MISSING_DEPENDENCY",
                        "task_id": task["task_id"],
                        "dependency": dependency,
                    }
                )
        parent_id = task.get("parent_id")
        if parent_id is not None and parent_id not in known:
            findings.append(
                {
                    "code": "MISSING_PARENT",
                    "task_id": task["task_id"],
                    "parent_id": parent_id,
                }
            )

    if known and not any(item["code"] == "MISSING_DEPENDENCY" for item in findings):
        dependency_edges = {
            task["task_id"]: list(task.get("depends_on", [])) for task in normalized
        }
        if _has_cycle(dependency_edges):
            findings.append({"code": "DEPENDENCY_CYCLE"})
    if known and not any(item["code"] == "MISSING_PARENT" for item in findings):
        parent_edges = {
            task["task_id"]: [task["parent_id"]] if task.get("parent_id") else []
            for task in normalized
        }
        if _has_cycle(parent_edges):
            findings.append({"code": "PARENT_CYCLE"})

    blocked = bool(findings)
    return {
        "candidate_id": plan_id,
        "status": "BLOCKED" if blocked else "CANDIDATE",
        "validation_status": "BLOCKED" if blocked else "READY_FOR_HUMAN_REVIEW",
        "goal": str(goal).strip(),
        "tasks": normalized,
        "evidence_refs": [f"goal:{plan_id}"],
        "summary": {
            "task_count": len(normalized),
            "human_gate_count": sum(task["human_gate"] for task in normalized),
        },
        "findings": findings,
    }


def ready_tasks(
    plan: dict[str, Any],
    task_states: dict[str, str],
    decisions: dict[str, str],
) -> list[dict[str, Any]]:
    """Return queued tasks whose dependencies and human gates are satisfied."""

    if (
        plan.get("status") != "ACCEPTED"
        or plan.get("validation_status") != "READY_FOR_HUMAN_REVIEW"
        or plan.get("findings")
    ):
        return []
    ready = []
    for task in plan.get("tasks", []):
        task_id = task["task_id"]
        if task_states.get(task_id, "QUEUED") != "QUEUED":
            continue
        if any(task_states.get(dep) != "DONE" for dep in task.get("depends_on", [])):
            continue
        if task.get("human_gate") and decisions.get(task_id) != "APPROVED":
            continue
        ready.append(task)
    return ready


def project_plan(
    plan: dict[str, Any],
    task_states: dict[str, str],
    assignments: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project one accepted plan into hierarchy, progress, and operating lanes."""

    assignments = assignments or {}
    tasks = plan.get("tasks", [])
    by_id = {task["task_id"]: task for task in tasks}
    children: dict[str | None, list[str]] = {}
    for task in tasks:
        children.setdefault(task.get("parent_id"), []).append(task["task_id"])

    def tree(task_id: str) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "title": by_id[task_id]["title"],
            "children": [tree(child) for child in children.get(task_id, [])],
        }

    lanes = {lane: [] for lane in LANES}
    cards: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_id = task["task_id"]
        state = task_states.get(task_id, "QUEUED")
        lanes.setdefault(state, []).append(task_id)
        cards[task_id] = {
            **task,
            "status": state,
            **assignments.get(task_id, {}),
        }

    done = len(lanes["DONE"])
    total = len(tasks)
    return {
        "plan_id": plan.get("candidate_id"),
        "goal": plan.get("goal"),
        "progress": {
            "done": done,
            "total": total,
            "percent": int(done * 100 / total) if total else 0,
        },
        "hierarchy": [tree(task_id) for task_id in children.get(None, [])],
        "lanes": lanes,
        "cards": cards,
    }
