from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runtime import RuntimeStore


RUNTIME_PLAN_SCHEMA = "personal-ai-os.runtime-plan/v1"


def load_runtime_plan(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime plan must be a JSON object")
    _validated_plan(value)
    return value


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"runtime plan {field} is required")
    return text


def _validated_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if plan.get("schema_version") != RUNTIME_PLAN_SCHEMA:
        raise ValueError("unsupported runtime plan schema")
    workflows = plan.get("workflows")
    if not isinstance(workflows, list):
        raise ValueError("runtime plan workflows must be a list")

    normalized: list[dict[str, Any]] = []
    workflow_ids: set[str] = set()
    task_ids: set[str] = set()
    for workflow in workflows:
        if not isinstance(workflow, dict):
            raise ValueError("runtime plan workflow must be an object")
        workflow_id = _required_text(workflow.get("workflow_id"), "workflow_id")
        if workflow_id in workflow_ids:
            raise ValueError(f"duplicate runtime plan workflow: {workflow_id}")
        workflow_ids.add(workflow_id)
        tasks = workflow.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError(f"runtime plan tasks must be a list: {workflow_id}")

        normalized_tasks: list[dict[str, Any]] = []
        workflow_task_ids: set[str] = set()
        for task in tasks:
            if not isinstance(task, dict):
                raise ValueError("runtime plan task must be an object")
            task_id = _required_text(task.get("task_id"), "task_id")
            title = _required_text(task.get("title"), f"task title: {task_id}")
            acceptance = _required_text(task.get("acceptance"), f"task acceptance: {task_id}")
            status = str(task.get("status") or "QUEUED").upper()
            if status != "QUEUED":
                raise ValueError(f"runtime plan tasks must start in QUEUED: {task_id}")
            if task.get("result_ref") or task.get("git_closure"):
                raise ValueError(f"runtime plan cannot provide runtime evidence: {task_id}")
            context = task.get("context") or {}
            if not isinstance(context, dict):
                raise ValueError(f"task context must be an object: {task_id}")
            capabilities = task.get("required_capabilities") or []
            if not isinstance(capabilities, list):
                raise ValueError(f"task required_capabilities must be a list: {task_id}")
            if task_id in task_ids:
                raise ValueError(f"duplicate runtime plan task: {task_id}")
            task_ids.add(task_id)
            workflow_task_ids.add(task_id)
            normalized_tasks.append(
                {
                    **task,
                    "task_id": task_id,
                    "title": title,
                    "acceptance": acceptance,
                    "status": "QUEUED",
                    "context": dict(context),
                    "required_capabilities": list(capabilities),
                }
            )

        for task in normalized_tasks:
            task_id = str(task["task_id"]).strip()
            dependencies = task.get("depends_on") or []
            if not isinstance(dependencies, list):
                raise ValueError(f"task dependencies must be a list: {task_id}")
            for dependency in dependencies:
                dependency_id = str(dependency or "").strip()
                if dependency_id not in workflow_task_ids:
                    raise ValueError(
                        f"dependency not found in runtime plan: {dependency_id or '<empty>'}"
                    )
            task["depends_on"] = [str(item).strip() for item in dependencies]

        pending = {str(task["task_id"]).strip(): task for task in normalized_tasks}
        ordered: list[dict[str, Any]] = []
        installed: set[str] = set()
        while pending:
            ready = [
                task_id
                for task_id, task in pending.items()
                if set(str(item).strip() for item in task.get("depends_on") or []) <= installed
            ]
            if not ready:
                raise ValueError(f"runtime plan contains a dependency cycle: {workflow_id}")
            for task_id in ready:
                ordered.append(pending.pop(task_id))
                installed.add(task_id)

        normalized.append({**workflow, "workflow_id": workflow_id, "tasks": ordered})
    return normalized


def _workflow_definition(workflow: dict[str, Any]) -> dict[str, Any]:
    workflow_id = str(workflow["workflow_id"]).strip()
    return {
        "workflow_id": workflow_id,
        "name": str(workflow.get("name") or workflow_id),
        "caption": str(workflow.get("caption") or ""),
        "layout": str(workflow.get("layout") or "custom"),
        "goal": str(workflow.get("goal") or ""),
    }


def _task_definition(workflow_id: str, task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task["task_id"]).strip()
    return {
        "task_id": task_id,
        "workflow_id": workflow_id,
        "line_id": str(task.get("line_id") or workflow_id),
        "public_label": str(task.get("public_label") or task_id),
        "title": str(task["title"]).strip(),
        "acceptance": str(task["acceptance"]).strip(),
        "agent_role": str(task.get("agent_role") or "General Agent"),
        "depends_on": list(task.get("depends_on") or []),
        "human_gate": bool(task.get("human_gate", False)),
        "iteration": int(task.get("iteration") or 1),
        "parallel_group": str(task.get("parallel_group") or "main"),
        "required_capabilities": list(task.get("required_capabilities") or []),
        "complexity": str(task.get("complexity") or "standard"),
        "domain_id": str(task.get("domain_id") or workflow_id),
        "context": dict(task.get("context") or {}),
        "requires_git_closure": bool(task.get("requires_git_closure", False)),
    }


def _existing_task_definition(task: dict[str, Any]) -> dict[str, Any]:
    keys = _task_definition(task["workflow_id"], task).keys()
    return {key: task[key] for key in keys}


def sync_runtime_plan(store: RuntimeStore, plan: dict[str, Any]) -> dict[str, int]:
    workflows = _validated_plan(plan)
    snapshot = store.snapshot()
    existing_workflows = {item["workflow_id"]: item for item in snapshot["workflows"]}
    existing_tasks = {item["task_id"]: item for item in snapshot["tasks"]}
    counts = {
        "created_workflows": 0,
        "created_tasks": 0,
        "existing_workflows": 0,
        "existing_tasks": 0,
    }

    for workflow in workflows:
        workflow_id = workflow["workflow_id"]
        workflow_definition = _workflow_definition(workflow)
        existing_workflow = existing_workflows.get(workflow_id)
        if existing_workflow is not None:
            existing_definition = {
                key: existing_workflow[key] for key in workflow_definition
            }
            if existing_definition != workflow_definition:
                raise ValueError(
                    f"runtime plan definition drift: workflow {workflow_id}"
                )
        for task in workflow["tasks"]:
            task_id = str(task["task_id"]).strip()
            existing = existing_tasks.get(task_id)
            if existing is not None and existing["workflow_id"] != workflow_id:
                raise ValueError(f"existing task belongs to another workflow: {task_id}")
            if existing is not None:
                definition = _task_definition(workflow_id, task)
                if _existing_task_definition(existing) != definition:
                    raise ValueError(f"runtime plan definition drift: task {task_id}")

    with store._connect() as connection:
        for workflow in workflows:
            workflow_id = workflow["workflow_id"]
            if workflow_id in existing_workflows:
                counts["existing_workflows"] += 1
            else:
                store._insert_workflow(connection, workflow)
                counts["created_workflows"] += 1

            for task in workflow["tasks"]:
                task_id = str(task["task_id"]).strip()
                existing = existing_tasks.get(task_id)
                if existing is not None:
                    counts["existing_tasks"] += 1
                    continue
                store._insert_task(
                    connection,
                    {
                        **task,
                        "workflow_id": workflow_id,
                        "line_id": str(task.get("line_id") or workflow_id),
                    },
                )
                counts["created_tasks"] += 1
    return counts
