from __future__ import annotations

from copy import deepcopy
from typing import Any


TASK_MODULE_LINK_VERSION = "personal-ai-os.module-task-link/v1"
TASK_MODULE_RELATIONS = {"BUILDS", "CHANGES", "USES", "VALIDATES", "BLOCKED_BY", "AFFECTS"}
TASK_MODULE_SOURCES = {"EXPLICIT", "ANALYZED", "IMPORTED"}
TASK_MODULE_STATUSES = {"PROPOSED", "CONFIRMED"}


def validate_task_module_link(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("module link must be an object")
    link = deepcopy(payload)
    module_id = str(link.get("module_id") or "").strip()
    relation = str(link.get("relation") or "").upper().strip()
    source = str(link.get("source") or "EXPLICIT").upper().strip()
    default_status = "PROPOSED" if source == "ANALYZED" else "CONFIRMED"
    status = str(link.get("status") or default_status).upper().strip()
    confidence = link.get("confidence", 1.0 if source != "ANALYZED" else 0.0)
    if not module_id:
        raise ValueError("module_id is required")
    if relation not in TASK_MODULE_RELATIONS:
        raise ValueError("unsupported task module relation")
    if source not in TASK_MODULE_SOURCES:
        raise ValueError("unsupported task module source")
    if status not in TASK_MODULE_STATUSES:
        raise ValueError("unsupported task module status")
    if source == "ANALYZED" and status != "PROPOSED":
        raise ValueError("analyzed module links must start in PROPOSED")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("module link confidence must be between 0 and 1")
    return {
        "schema_version": TASK_MODULE_LINK_VERSION,
        "module_id": module_id,
        "relation": relation,
        "source": source,
        "confidence": float(confidence),
        "status": status,
    }


def module_work_projection(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Derive current module work from confirmed task links and task truth."""

    tasks = {item["task_id"]: item for item in snapshot.get("tasks", [])}
    confirmed = [
        {
            key: deepcopy(item.get(key))
            for key in (
                "schema_version",
                "task_id",
                "module_id",
                "relation",
                "source",
                "confidence",
                "status",
            )
        }
        for item in snapshot.get("module_links", [])
        if item.get("status") == "CONFIRMED" and item.get("task_id") in tasks
    ]
    by_module: dict[str, dict[str, Any]] = {}
    linked_task_ids: set[str] = set()
    for link in confirmed:
        task = tasks[link["task_id"]]
        linked_task_ids.add(task["task_id"])
        item = by_module.setdefault(
            link["module_id"],
            {
                "module_id": link["module_id"],
                "task_ids": [],
                "relations": [],
                "status_counts": {},
            },
        )
        if task["task_id"] not in item["task_ids"]:
            item["task_ids"].append(task["task_id"])
            status = task["status"]
            item["status_counts"][status] = item["status_counts"].get(status, 0) + 1
        if link["relation"] not in item["relations"]:
            item["relations"].append(link["relation"])
    return {
        "schema_version": "personal-ai-os.module-work-projection/v1",
        "links": confirmed,
        "by_module": by_module,
        "unlinked_task_ids": [task_id for task_id in tasks if task_id not in linked_task_ids],
    }
