"""One-shot orchestration between the runtime dispatch queue and Codex.

The host bridge is injected by the caller so this package does not depend on a
desktop Codex implementation.  The worker is deliberately fail-closed:
thread/project identity and a terminal receipt must be verified before any
durable bind or completion call is made.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


_VERIFICATION_SOURCES = frozenset({"task-project", "thread-project-assignments"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _same_path(left: Any, right: Any) -> bool:
    try:
        return Path(_text(left)).expanduser().resolve() == Path(_text(right)).expanduser().resolve()
    except (OSError, RuntimeError, TypeError):
        return False


def _validate_dispatch(dispatch: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Validate queue data before asking Codex to create a task.

    A project-native task cannot be created safely from a path alone.  The
    desktop bridge must receive the durable project id, path, and execution
    environment as separate fields so a missing id cannot silently become a
    projectless thread.
    """
    dispatch_id = _text(dispatch.get("dispatch_id"))
    task_id = _text(dispatch.get("task_id"))
    project = dispatch.get("project")
    if not dispatch_id or not task_id or not isinstance(project, dict):
        return False, "DISPATCH_INVALID", {}
    project_id = _text(project.get("project_id"))
    project_path = _text(project.get("path"))
    environment = _text(project.get("environment"))
    if not project_id:
        return False, "PROJECT_ID_REQUIRED", {}
    if not project_path:
        return False, "PROJECT_PATH_REQUIRED", {}
    if environment not in {"local", "worktree"}:
        return False, "PROJECT_ENVIRONMENT_INVALID", {}
    return True, "", {
        "dispatch_id": dispatch_id,
        "task_id": task_id,
        "project_id": project_id,
        "project_path": project_path,
        "environment": environment,
    }


def _verify_thread(dispatch: dict[str, Any], created: Any) -> tuple[bool, str, dict[str, Any]]:
    if not isinstance(created, dict):
        return False, "THREAD_CREATION_INVALID", {}
    project = dispatch.get("project")
    if not isinstance(project, dict):
        return False, "PROJECT_BINDING_INVALID", {}
    thread_id = _text(created.get("thread_id"))
    project_id = _text(created.get("project_id"))
    host_id = _text(created.get("host_id"))
    verification = created.get("verification")
    if not thread_id or not project_id or not host_id or not isinstance(verification, dict):
        return False, "THREAD_PROJECT_UNVERIFIED", {}
    if verification.get("verified") is not True:
        return False, "THREAD_PROJECT_UNVERIFIED", {}
    if _text(verification.get("source")) not in _VERIFICATION_SOURCES:
        return False, "THREAD_PROJECT_UNVERIFIED", {}
    if _text(verification.get("project_id")) != project_id:
        return False, "THREAD_PROJECT_MISMATCH", {}
    if project_id != _text(project.get("project_id")):
        return False, "THREAD_PROJECT_MISMATCH", {}
    if not _same_path(verification.get("project_path"), project.get("path")):
        return False, "THREAD_PROJECT_PATH_MISMATCH", {}
    if _text(verification.get("environment")) != _text(project.get("environment")):
        return False, "THREAD_PROJECT_ENVIRONMENT_MISMATCH", {}
    return True, "", {
        "thread_id": thread_id,
        "project_id": project_id,
        "host_id": host_id,
        "verification": verification,
    }


def run_once(adapter: Any, host: Any, *, worker_id: str) -> dict[str, Any]:
    """Claim and bind at most one pending dispatch."""

    try:
        dispatch = adapter.claim_next(worker_id=_text(worker_id))
    except Exception:
        return {"status": "BLOCKED", "reason": "DISPATCH_CLAIM_FAILED"}
    if dispatch is None:
        return {"status": "IDLE", "reason": "QUEUE_EMPTY"}
    if not isinstance(dispatch, dict):
        return {"status": "BLOCKED", "reason": "DISPATCH_INVALID"}
    valid, reason, metadata = _validate_dispatch(dispatch)
    if not valid:
        return {"status": "BLOCKED", "reason": reason}
    try:
        created = host.create_task(
            title=(
                f"LongTask · {metadata['task_id']} · "
                f"{metadata['dispatch_id'][-8:]}"
            ),
            task_id=metadata["task_id"],
            project_id=metadata["project_id"],
            project_path=metadata["project_path"],
            environment=metadata["environment"],
            model=_text(dispatch.get("model")),
            prompt=_text(dispatch.get("prompt")),
        )
    except Exception:
        return {"status": "BLOCKED", "reason": "THREAD_CREATION_FAILED"}
    valid, reason, binding = _verify_thread(dispatch, created)
    if not valid:
        return {"status": "BLOCKED", "reason": reason}
    try:
        result = adapter.bind_thread(metadata["dispatch_id"], **binding)
    except Exception:
        return {"status": "BLOCKED", "reason": "THREAD_BIND_FAILED"}
    if isinstance(result, dict) and (
        result.get("ok") is False or _text(result.get("status")) == "BLOCKED"
    ):
        return {
            "status": "BLOCKED",
            "reason": _text(result.get("reason")) or "THREAD_BIND_REJECTED",
            "result": result,
        }
    return {"status": "RUNNING", "dispatch_id": metadata["dispatch_id"], "result": result}


def finish_once(adapter: Any, host: Any, dispatch_id: str) -> dict[str, Any]:
    """Complete one running dispatch only after a verified terminal receipt."""

    dispatch_id = _text(dispatch_id)
    if not dispatch_id:
        return {"status": "BLOCKED", "reason": "DISPATCH_ID_REQUIRED"}
    try:
        terminal = host.read_terminal(dispatch_id=dispatch_id)
    except Exception:
        return {"status": "RUNNING", "reason": "TERMINAL_RECEIPT_PENDING"}
    if not isinstance(terminal, dict) or _text(terminal.get("status")) != "completed":
        return {"status": "RUNNING", "reason": "TERMINAL_RECEIPT_PENDING"}
    receipt = terminal.get("receipt")
    if (
        not isinstance(receipt, dict)
        or _text(receipt.get("status")) != "completed"
        or receipt.get("verified") is not True
        or receipt.get("needs_user_input") is not False
        or receipt.get("human_gate") is not False
        or not _text(terminal.get("output_text"))
    ):
        return {"status": "RUNNING", "reason": "TERMINAL_RECEIPT_UNVERIFIED"}
    try:
        result = adapter.complete(
            dispatch_id,
            output_text=_text(terminal["output_text"]),
            completion_receipt=receipt,
        )
    except Exception:
        return {"status": "BLOCKED", "reason": "TERMINAL_COMPLETE_FAILED"}
    if isinstance(result, dict) and (
        result.get("ok") is False or _text(result.get("status")) == "BLOCKED"
    ):
        return {
            "status": "BLOCKED",
            "reason": _text(result.get("reason")) or "TERMINAL_COMPLETE_REJECTED",
            "dispatch_id": dispatch_id,
            "result": result,
        }
    return {"status": "REVIEW", "dispatch_id": dispatch_id, "result": result}
