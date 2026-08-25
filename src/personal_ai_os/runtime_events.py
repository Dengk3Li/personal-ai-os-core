"""Versioned runtime events shared by adapters, the runtime and SSE clients.

The runtime already persists a small legacy event record.  This module adds a
stable envelope around that record without becoming a second state store:
process evidence lives under ``action``/``observation`` and durable outcome
evidence lives under ``receipt``.  Producers remain responsible for task and
run state transitions.
"""

from __future__ import annotations

import datetime
import json
from typing import Any


SCHEMA_VERSION = "personal-ai-os.runtime-event/v1"
EVENT_TYPES = frozenset(
    {
        "requested",
        "claimed",
        "started",
        "heartbeat",
        "artifact",
        "review",
        "decision",
        "terminal",
    }
)
PROCESS_EVENT_TYPES = frozenset(
    {"requested", "claimed", "started", "heartbeat"}
)
EVENT_KIND = {
    **{event_type: "process" for event_type in PROCESS_EVENT_TYPES},
    "artifact": "artifact",
    "review": "review",
    "decision": "decision",
    "terminal": "terminal",
}


class EventValidationError(ValueError):
    """Raised when an event cannot be safely correlated or classified."""


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _mapping(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise EventValidationError("事件载荷必须是对象")
    return dict(value)


def _event_id(run_id: str, event_type: str, occurred_at: str, attempt: int) -> str:
    return f"{run_id}:{attempt}:{event_type}:{occurred_at}"


def build_envelope(
    *,
    event_type: str,
    run_id: str,
    task_id: str | None = None,
    source: str = "runtime",
    occurred_at: str | None = None,
    event_id: str | None = None,
    attempt: int = 1,
    action: dict[str, Any] | None = None,
    observation: dict[str, Any] | None = None,
    artifact: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
    terminal: dict[str, Any] | None = None,
    recovery_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one action/observation/run receipt envelope.

    The function is deliberately storage-agnostic.  It validates only the
    envelope contract and never changes a task, run or decision.
    """
    event_type = str(event_type or "").strip()
    run_id = str(run_id or "").strip()
    source = str(source or "").strip()
    if event_type not in EVENT_TYPES:
        raise EventValidationError(f"不支持的运行事件类型: {event_type!r}")
    if not run_id:
        raise EventValidationError("运行事件缺少 run_id")
    if not source:
        raise EventValidationError("运行事件缺少 source")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise EventValidationError("attempt 必须是正整数")

    occurred_at = str(occurred_at or _now())
    if not occurred_at.strip():
        raise EventValidationError("运行事件缺少 occurred_at")
    artifact = _mapping(artifact)
    review = _mapping(review)
    decision = _mapping(decision)
    terminal = _mapping(terminal)
    recovery_gate = _mapping(recovery_gate)
    required = {
        "artifact": artifact,
        "review": review,
        "decision": decision,
        "terminal": terminal,
    }
    if event_type in required and required[event_type] is None:
        raise EventValidationError(f"{event_type} 事件缺少对应回执段")
    if recovery_gate is not None and event_type not in {"decision", "terminal"}:
        raise EventValidationError("恢复门只能附着在 decision 或 terminal 事件")

    return {
        "schema_version": SCHEMA_VERSION,
        "event": {
            "id": str(event_id or _event_id(run_id, event_type, occurred_at, attempt)),
            "type": event_type,
            "kind": EVENT_KIND[event_type],
            "source": source,
            "occurred_at": occurred_at,
        },
        "run": {
            "run_id": run_id,
            "task_id": str(task_id) if task_id is not None else None,
            "attempt": attempt,
        },
        "action": _mapping(action),
        "observation": _mapping(observation),
        "receipt": {
            "artifact": artifact,
            "review": review,
            "decision": decision,
            "terminal": terminal,
            "recovery_gate": recovery_gate,
        },
    }


_LEGACY_TYPES = {
    "RUN_ASSIGNED": "claimed",
    "AUTO_ROUTE_SELECTED": "claimed",
    "ADAPTER_STARTED": "started",
    "CODEX_PROJECT_THREAD_BOUND": "started",
    "ARTIFACT_CREATED": "artifact",
    "RUN_SUCCEEDED": "terminal",
    "MEMORY_REVIEW_REQUESTED": "review",
    "REVIEW_REQUESTED": "review",
    "DECISION_REQUESTED": "decision",
    "DECISION_RECORDED": "decision",
    "DISPATCH": "claimed",
    "REWORK": "claimed",
    "UNASSIGN": "claimed",
    "UNBLOCKED": "started",
    "RESUMED": "started",
    "BLOCKED": "terminal",
    "PAUSED": "terminal",
    "DONE_SKIP_REVIEW": "terminal",
    "CLOSED": "terminal",
    "ACCEPTED": "terminal",
    "ARCHIVED": "terminal",
    "WITHDRAWN": "terminal",
    "REJECTED_RESCORE": "decision",
}


def _legacy_type(event_type: str, event: dict[str, Any] | None = None) -> str:
    upper = event_type.upper()
    if upper in _LEGACY_TYPES:
        return _LEGACY_TYPES[upper]
    if upper in {"DONE", "ERROR"}:
        return "terminal"
    if upper == "DECISION":
        return "decision"
    if upper == "STATUS":
        return {
            "starting": "claimed",
            "running": "started",
            "waiting_input": "claimed",
            "cancelled": "terminal",
        }.get(str((event or {}).get("state") or ""), "heartbeat")
    if upper == "FEEDBACK":
        kind = str(((event or {}).get("feedback") or {}).get("kind") or "")
        return {
            "accepted": "claimed",
            "progress": "heartbeat",
            "completed": "terminal",
            "failed": "terminal",
            "stale": "terminal",
            "blocked": "decision",
        }.get(kind, "heartbeat")
    return "heartbeat"


def _stable_code(value: Any) -> str | None:
    candidate = str(value or "").strip()
    if candidate and len(candidate) <= 64 and all(
        character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in candidate
    ):
        return candidate
    return None


def _legacy_receipts(
    event_type: str,
    payload: dict[str, Any],
    runtime_type: str,
    run_id: str,
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = event or {}
    feedback = event.get("feedback") or {}
    if not isinstance(feedback, dict):
        feedback = {}
    artifact = None
    if runtime_type == "artifact" or event_type == "RUN_SUCCEEDED":
        artifact_ref = str(payload.get("artifact_id") or payload.get("ref") or "").strip()
        artifact = {"ref": artifact_ref, "final": event_type == "RUN_SUCCEEDED"}
        if not artifact_ref:
            artifact["ref"] = f"run://{run_id}/artifact"

    review = None
    if runtime_type == "review":
        review = {
            "status": "requested",
            "review_type": "memory" if event_type == "MEMORY_REVIEW_REQUESTED" else "result",
        }

    decision = None
    if runtime_type == "decision":
        decision = {
            "status": "recorded" if event_type == "DECISION_RECORDED" else "pending",
        }
        decision_id = str(payload.get("decision_id") or "").strip()
        if decision_id:
            decision["decision_id"] = decision_id
        selected = str(payload.get("selected_option") or "").strip()
        if selected:
            decision["selected_option"] = selected

    terminal = None
    if runtime_type == "terminal":
        if event_type == "RUN_SUCCEEDED" or (
            event_type == "DONE" and event.get("exit_code") in (None, 0)
        ):
            outcome = "succeeded"
        elif event_type == "ERROR" or feedback.get("kind") in {"failed", "stale"}:
            outcome = str(feedback.get("kind") or "failed")
        elif event_type == "STATUS" and event.get("state") == "cancelled":
            outcome = "cancelled"
        elif event_type in {"BLOCKED", "PAUSED", "WITHDRAWN"}:
            outcome = event_type.lower()
        elif event_type in {"DONE_SKIP_REVIEW", "CLOSED", "ACCEPTED", "ARCHIVED"}:
            outcome = "completed"
        else:
            outcome = "unknown"
        terminal = {"outcome": outcome}
        error_code = _stable_code(payload.get("error_code") or payload.get("reason"))
        if error_code:
            terminal["error_code"] = error_code

    recovery_gate = None
    explicit_gate = event.get("recovery_gate")
    if isinstance(explicit_gate, dict):
        recovery_gate = dict(explicit_gate)
    elif (
        event_type in {"DECISION", "DECISION_REQUESTED"}
        or event_type in {"BLOCKED", "PAUSED"}
        or feedback.get("kind") in {"blocked", "stale", "failed"}
        or event.get("state") in {"orphaned", "unknown"}
    ):
        blocker = str(feedback.get("blocker") or "").strip()
        next_action = str(feedback.get("next_action") or "").strip()
        recovery_gate = {
            "required": True,
            "reason": blocker or (
                "等待人工决定"
                if event_type in {"DECISION", "DECISION_REQUESTED"}
                else "任务需要恢复处理"
            ),
            "next_action": next_action or (
                "记录人工决定"
                if event_type in {"DECISION", "DECISION_REQUESTED"}
                else "检查运行回执后恢复"
            ),
        }

    return {
        "artifact": artifact,
        "review": review,
        "decision": decision,
        "terminal": terminal,
        "recovery_gate": recovery_gate,
    }


def from_legacy_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep a legacy runtime event and attach its canonical envelope.

    Events without a run identity fail closed.  They remain valid in the
    legacy SQLite stream, but cannot claim to be a run receipt or be correlated
    with a model execution.
    """
    if not isinstance(event, dict):
        raise EventValidationError("旧运行事件必须是对象")
    run_id = str(event.get("run_id") or "").strip()
    if not run_id:
        raise EventValidationError("旧运行事件缺少 run_id")
    event_type = str(event.get("event_type") or event.get("type") or "").strip()
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        raise EventValidationError("旧运行事件 payload 必须是对象")
    runtime_type = _legacy_type(event_type, event)
    source = str(event.get("source") or payload.get("adapter_id") or "runtime")
    occurred_at = str(event.get("at") or event.get("ts") or _now())
    attempt = event.get("attempt", 1)
    receipts = _legacy_receipts(
        event_type.upper(), payload, runtime_type, run_id, event
    )
    event_id = event.get("event_id")
    if event_id is not None:
        event_id = f"legacy:{event_id}"
    action = {
        key: (payload if key in payload else event)[key]
        for key in ("adapter_id", "model", "route", "by", "executor", "platform")
        if key in payload or key in event
    }
    observation = {
        key: (payload if key in payload else event)[key]
        for key in ("from", "to", "status", "state", "exit_code", "result_subtype")
        if key in payload or key in event
    }
    projected = dict(event)
    projected["runtime"] = build_envelope(
        event_type=runtime_type,
        run_id=run_id,
        task_id=event.get("task_id") or event.get("card"),
        source=source,
        occurred_at=occurred_at,
        event_id=event_id,
        attempt=attempt,
        action=action or None,
        observation=observation or None,
        **receipts,
    )
    return projected


def to_sse(event: dict[str, Any]) -> str:
    """Serialize an event for an SSE data frame without changing its shape."""
    try:
        projected = from_legacy_event(event)
    except EventValidationError:
        projected = event
    return f"data: {json.dumps(projected, ensure_ascii=False, sort_keys=True)}\n\n"
