"""Read-only task acceptance projection.

This module joins facts that already exist in the runtime store into one
display contract.  It is deliberately storage-agnostic: callers provide a
task card, the latest run, runtime events and registered artifacts.  Building
the projection never changes task state, creates an artifact, or accepts a
review.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


SCHEMA_VERSION = "personal-ai-os.acceptance/v1"

_ACTIVE_RUN_STATES = frozenset({"RUNNING", "STARTING", "IN_PROGRESS", "running", "starting"})
_FAILED_RUN_STATES = frozenset({
    "FAILED", "REJECTED", "BLOCKED", "CANCELLED", "ERROR",
    "failed", "rejected", "blocked", "cancelled", "error",
})
_TERMINAL_RUN_STATES = frozenset({"SUCCEEDED", "DONE", "TERMINAL", "exited", "terminal"})
_TIMESTAMP_KEYS = ("at", "ts", "occurred_at", "created_at")


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _first_text(value: Any, *keys: str) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        text = _text(value.get(key))
        if text:
            return text
    return None


def _task(card: dict[str, Any]) -> dict[str, Any]:
    """Keep task identity small and presentation-safe."""
    return {
        "task_id": card.get("task_id"),
        "title": str(card.get("title") or card.get("public_label") or "未命名工作"),
        "status": card.get("status"),
        "line": card.get("line") or card.get("line_id") or card.get("workflow_id"),
    }


def _causality(card: dict[str, Any]) -> dict[str, str]:
    presentation = card.get("presentation") or {}
    if not isinstance(presentation, dict):
        presentation = {}
    return {
        "background": str(presentation.get("why") or "任务背景尚未说明。"),
        "current": str(presentation.get("now") or "当前阶段尚未说明。"),
        "next": str(presentation.get("next") or "下一步尚未说明。"),
        "relationship": str(
            presentation.get("relationship") or "前后依赖尚未说明。"
        ),
    }


def _run_state(run: dict[str, Any] | None) -> str:
    return str((run or {}).get("status") or (run or {}).get("state") or "").strip()


def _execution_status(run: dict[str, Any] | None) -> str:
    if not run:
        return "NOT_DISPATCHED"
    state = _run_state(run)
    if state in _ACTIVE_RUN_STATES:
        return "RUNNING"
    if state in _FAILED_RUN_STATES:
        return "FAILED"
    if state in _TERMINAL_RUN_STATES:
        # Public RuntimeStore uses SUCCEEDED + ended_at.  A generic exited
        # record without an exit code is intentionally left uncertain.
        if state in {"exited"} and run.get("exit_code") is None:
            return "UNKNOWN"
        if state in {"SUCCEEDED", "DONE", "TERMINAL"} and not _text(
            run.get("ended_at") or run.get("exited_at")
        ):
            return "UNKNOWN"
        return "TERMINAL"
    if state == "waiting_input":
        return "AWAITING_INPUT"
    return "UNKNOWN"


def _execution(run: dict[str, Any] | None) -> dict[str, Any]:
    status = _execution_status(run)
    run = run or {}
    binding = run.get("binding") if isinstance(run.get("binding"), dict) else {}
    return {
        "status": status,
        "run_id": run.get("run_id"),
        "executor": run.get("executor") or run.get("adapter_id"),
        "adapter": run.get("adapter") or run.get("adapter_id"),
        "model_id": run.get("model_id") or run.get("model"),
        "platform": run.get("platform"),
        "thread_id": run.get("thread_id") or binding.get("conversation_id"),
        "turn_id": run.get("turn_id"),
        "started_at": run.get("started_at"),
        "exited_at": run.get("exited_at") or run.get("ended_at"),
        "exit_code": run.get("exit_code"),
    }


def _event_type(event: dict[str, Any]) -> str | None:
    return _first_text(event, "type", "event_type", "name")


def _event_at(event: dict[str, Any]) -> str | None:
    return _first_text(event, *_TIMESTAMP_KEYS)


def _timeline_item(event: dict[str, Any], *, source: str = "event") -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": _event_type(event) or "unknown",
        "source": source,
    }
    timestamp = _event_at(event)
    if timestamp:
        item["at"] = timestamp
    run_id = _first_text(event, "run_id")
    if run_id:
        item["run_id"] = run_id
    for key in ("stage", "status", "summary", "artifact_ref"):
        value = _first_text(event, key)
        if value:
            item[key] = value
    payload = event.get("payload") if isinstance(event, dict) else None
    if isinstance(payload, dict):
        for key in ("stage", "status", "summary", "artifact_ref", "artifact_id"):
            if key in item:
                continue
            value = _text(payload.get(key))
            if value:
                item["artifact_ref" if key == "artifact_id" else key] = value
    return item


def _timeline(
    run: dict[str, Any] | None,
    events: Iterable[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not run:
        return []
    run_id = _text(run.get("run_id"))
    items: list[tuple[int, dict[str, Any]]] = []
    for index, event in enumerate(events or []):
        if not isinstance(event, dict):
            continue
        event_run = _first_text(event, "run_id")
        if event_run and run_id and event_run != run_id:
            continue
        items.append((index, _timeline_item(event)))

    known_types = {item.get("type") for _, item in items}
    started_at = _first_text(run, "started_at")
    if started_at and not {"started", "STARTED", "ADAPTER_STARTED"} & known_types:
        items.append((len(items), {
            "type": "started",
            "at": started_at,
            "run_id": run_id,
            "source": "run_record",
        }))
    ended_at = _first_text(run, "ended_at", "exited_at")
    if ended_at and not {"terminal", "TERMINAL", "RUN_SUCCEEDED", "DONE"} & known_types:
        items.append((len(items), {
            "type": "terminal",
            "at": ended_at,
            "run_id": run_id,
            "status": _execution_status(run),
            "source": "run_record",
        }))

    return [
        item
        for _, item in sorted(
            items,
            key=lambda pair: (str(pair[1].get("at") or ""), pair[0]),
        )
    ]


def _artifact_item(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str) and value.strip():
        return {"artifact_ref": value.strip(), "status": "observed"}
    if not isinstance(value, dict):
        return None
    ref = _first_text(value, "artifact_ref", "artifact_id", "ref", "path")
    if not ref:
        return None
    result: dict[str, Any] = {"artifact_ref": ref}
    # Content is intentionally omitted.  This projection is usable by both
    # private-local and public-safe browser views without leaking task bodies.
    for key in ("run_id", "kind", "status", "stage", "summary", "created_at", "source"):
        text = _text(value.get(key))
        if text:
            result[key] = text
    return result


def _artifacts(
    run: dict[str, Any] | None,
    artifacts: Iterable[Any] | None,
) -> list[dict[str, Any]]:
    values: list[Any] = list(artifacts or [])
    if run:
        values.extend(run.get("artifact_refs") or [])
        values.extend((run.get("git_closure") or {}).get("artifact_refs") or [])
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values:
        item = _artifact_item(value)
        if not item:
            continue
        key = (str(item["artifact_ref"]), item.get("stage"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _review(
    card: dict[str, Any],
    run: dict[str, Any] | None,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    card_status = str(card.get("status") or "")
    execution_status = _execution_status(run)
    if card_status in {"DONE", "ARCHIVED"}:
        review_status, accepted = "ACCEPTED", True
    elif card_status == "REVIEW":
        review_status, accepted = "IN_REVIEW", False
    elif card_status in {"PAUSED", "BLOCKED"}:
        review_status, accepted = "BLOCKED", False
    elif execution_status == "FAILED":
        review_status, accepted = "FAILED", False
    elif execution_status == "TERMINAL" and artifacts:
        review_status, accepted = "READY_FOR_REVIEW", False
    else:
        review_status, accepted = "NOT_READY", False

    feedback = run.get("feedback") if isinstance(run, dict) else None
    feedback = feedback if isinstance(feedback, dict) else {}
    evidence = [str(item) for item in feedback.get("evidence") or [] if str(item).strip()]
    if not evidence:
        evidence = [str(item["artifact_ref"]) for item in artifacts]
    summary = _text(feedback.get("summary")) or ""
    if not summary and artifacts:
        summary = str(artifacts[-1].get("summary") or "")
    return {
        "status": review_status,
        "accepted": accepted,
        "summary": summary,
        "evidence": evidence,
        "next_action": str(feedback.get("next_action") or ""),
        "at": str(feedback.get("at") or ""),
    }


def build_acceptance_snapshot(
    card: dict[str, Any],
    run: dict[str, Any] | None = None,
    *,
    events: Iterable[dict[str, Any]] | None = None,
    artifacts: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Build a display snapshot from existing facts without mutating them."""
    stage_artifacts = _artifacts(run, artifacts)
    return {
        "schema_version": SCHEMA_VERSION,
        "task": _task(card),
        "causality": _causality(card),
        "execution": _execution(run),
        "timeline": _timeline(run, events),
        "stage_artifacts": stage_artifacts,
        "review": _review(card, run, stage_artifacts),
    }
