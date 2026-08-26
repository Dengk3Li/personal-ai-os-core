from __future__ import annotations

import json
from typing import Any

from .template_selection import validate_template_selection


UPSTREAM_CONTEXT_CHARACTER_LIMIT = 24_000
MODEL_CONTEXT_CHARACTER_LIMIT = 12_000


def model_context_for_task(task: dict[str, Any]) -> dict[str, Any]:
    local_context = task.get("context") or {}
    if not isinstance(local_context, dict):
        raise ValueError("task context must be an object")
    model_context = local_context.get("model_context") or {}
    if not isinstance(model_context, dict):
        raise ValueError("model_context must be an object")
    encoded = json.dumps(model_context, ensure_ascii=False, sort_keys=True)
    if len(encoded) > MODEL_CONTEXT_CHARACTER_LIMIT:
        raise ValueError(
            f"model_context exceeds {MODEL_CONTEXT_CHARACTER_LIMIT} characters"
        )
    return dict(model_context)


def build_context_pack(
    task: dict[str, Any],
    domain_profile: dict[str, Any] | None = None,
    *,
    upstream_artifacts: list[dict[str, Any]] | None = None,
    work_protocol: dict[str, Any] | None = None,
    memory_context: dict[str, Any] | None = None,
    template_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the smallest transferable task context without copying memory bodies."""
    profile = domain_profile or {}
    remaining = UPSTREAM_CONTEXT_CHARACTER_LIMIT
    bounded_upstream = []
    for artifact in upstream_artifacts or []:
        if remaining <= 0:
            break
        content = str(artifact.get("content") or "")
        excerpt = content[:remaining]
        remaining -= len(excerpt)
        bounded_upstream.append(
            {
                "artifact_id": artifact.get("artifact_id"),
                "task_id": artifact.get("task_id"),
                "summary": artifact.get("summary") or "",
                "content": excerpt,
                "truncated": len(excerpt) < len(content),
            }
        )
    model_context = model_context_for_task(task)
    operating_practices = list(profile.get("operating_practices") or [])
    practice_evidence_refs = list(profile.get("practice_evidence_refs") or [])
    approved_practice_refs = list(profile.get("approved_practice_refs") or [])
    bounded_memory_context = dict(memory_context or {})
    normalized_template_selection = None
    if template_selection is not None:
        try:
            normalized_template_selection = validate_template_selection(template_selection)
        except (TypeError, ValueError) as exc:
            raise ValueError("template selection is invalid") from exc
    bounded_context = json.dumps(
        {
            "model_context": model_context,
            "operating_practices": operating_practices,
            "practice_evidence_refs": practice_evidence_refs,
            "approved_practice_refs": approved_practice_refs,
            "work_protocol": work_protocol or {},
            "memory_context": bounded_memory_context,
            "template_selection": normalized_template_selection,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if len(bounded_context) > MODEL_CONTEXT_CHARACTER_LIMIT:
        raise ValueError(
            f"model context budget exceeds {MODEL_CONTEXT_CHARACTER_LIMIT} characters"
        )
    return {
        "schema_version": "personal-ai-os.context-pack/v1",
        "task_id": task.get("task_id"),
        "goal": task.get("title") or task.get("public_label") or task.get("task_id"),
        "acceptance": task.get("acceptance") or "",
        "current_state": task.get("status", "QUEUED"),
        "next_action": task.get("next_action") or "produce one inspectable result",
        "constraints": list(task.get("constraints") or []),
        "artifact_refs": list(task.get("artifact_refs") or []),
        "model_context": model_context,
        "upstream_artifacts": bounded_upstream,
        "domain_id": profile.get("domain_id") or task.get("domain_id") or "general",
        "persona": profile.get("persona") or "direct",
        "memory_refs": list(profile.get("memory_refs") or []),
        "instruction_refs": list(profile.get("instruction_refs") or []),
        "operating_practices": operating_practices,
        "practice_evidence_refs": practice_evidence_refs,
        "approved_practice_refs": approved_practice_refs,
        "work_protocol": dict(work_protocol or {}),
        "template_selection": normalized_template_selection,
        "memory_read_status": bounded_memory_context.get("status"),
        "memory_ref_ids": list(bounded_memory_context.get("memory_ref_ids") or []),
        "memory_context": bounded_memory_context,
    }


def build_secretary_brief(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project runtime truth into a compact attention and continuity brief."""
    tasks = snapshot.get("tasks", [])
    decisions = [item for item in snapshot.get("decisions", []) if item.get("status") == "PENDING"]
    counts = {
        state.lower(): sum(task.get("status") == state for task in tasks)
        for state in ("QUEUED", "IN_PROGRESS", "REVIEW", "BLOCKED", "PAUSED", "DONE")
    }
    next_actions = []
    if decisions:
        next_actions.append({"kind": "decision", "task_id": decisions[0]["task_id"], "decision_id": decisions[0]["decision_id"]})
    review_task = next((task for task in tasks if task.get("status") == "REVIEW"), None)
    if review_task:
        next_actions.append({"kind": "review", "task_id": review_task["task_id"]})
    queued_task = next((task for task in tasks if task.get("status") == "QUEUED"), None)
    if queued_task:
        next_actions.append({"kind": "dispatch", "task_id": queued_task["task_id"]})
    return {
        "schema_version": "personal-ai-os.secretary-brief/v1",
        "summary": (
            f"{counts['in_progress']} 项运行中，{counts['review']} 项待验收，"
            f"{len(decisions)} 项待决定。"
        ),
        "attention": {**counts, "decisions": len(decisions)},
        "next_actions": next_actions[:3],
        "authority": "runtime-store",
    }
