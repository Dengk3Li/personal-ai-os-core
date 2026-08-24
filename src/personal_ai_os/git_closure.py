from __future__ import annotations

from typing import Any


def evaluate_git_closure(record: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether a task result has enough version evidence to advance."""

    dirty_paths = sorted({str(path) for path in record.get("dirty_paths", [])})
    if dirty_paths:
        return {
            "status": "BLOCKED",
            "reason": "UNCOMMITTED_TASK_CHANGES",
            "dirty_paths": dirty_paths,
            "review_ready": False,
            "done_ready": False,
            "archive_ready": False,
            "rollback": {"method": "unknown", "commit": None},
        }

    kind = record.get("result_kind")
    commit = record.get("result_commit")
    if kind == "result_commit":
        has_evidence = bool(commit)
        rollback = {"method": "revert", "commit": commit}
    elif kind == "no_git_change":
        has_evidence = bool(record.get("attested_by"))
        rollback = {"method": "none", "commit": None}
    elif kind == "external_delivery":
        has_evidence = bool(record.get("artifact_ref"))
        rollback = {"method": "stop_using_artifact", "commit": None}
    else:
        has_evidence = False
        rollback = {"method": "unknown", "commit": None}

    if not has_evidence:
        return {
            "status": "BLOCKED",
            "reason": "RESULT_EVIDENCE_REQUIRED",
            "dirty_paths": [],
            "review_ready": False,
            "done_ready": False,
            "archive_ready": False,
            "rollback": rollback,
        }

    accepted_candidate = bool(
        record.get("accepted_independent_candidate") or record.get("accepted_result")
    )
    done_ready = (
        kind == "no_git_change"
        or (kind == "result_commit" and record.get("integration_status") == "mainline")
        or accepted_candidate
    )
    return {
        "status": "READY" if done_ready else "REVIEW_READY",
        "reason": None if done_ready else "CANDIDATE_ACCEPTANCE_REQUIRED",
        "dirty_paths": [],
        "review_ready": True,
        "done_ready": done_ready,
        "archive_ready": done_ready,
        "rollback": rollback,
    }
