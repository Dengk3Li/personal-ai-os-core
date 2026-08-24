from __future__ import annotations

import datetime
from typing import Any

from .states import OVERLAY_STATES, TASK_STATES

STATES = set(TASK_STATES)
STRUCTURAL_TRANSITIONS = {
    ("QUEUED", "IN_PROGRESS"),
    ("QUEUED", "DONE"),
    ("QUEUED", "ARCHIVED"),
    ("IN_PROGRESS", "REVIEW"),
    ("IN_PROGRESS", "DONE"),
    ("IN_PROGRESS", "QUEUED"),
    ("REVIEW", "DONE"),
    ("REVIEW", "IN_PROGRESS"),
    ("REVIEW", "QUEUED"),
    ("DONE", "ARCHIVED"),
}
REASON_REQUIRED = {
    ("QUEUED", "DONE"),
    ("QUEUED", "ARCHIVED"),
    ("IN_PROGRESS", "DONE"),
    ("IN_PROGRESS", "QUEUED"),
    ("REVIEW", "QUEUED"),
}
EVENT_NAMES = {
    ("QUEUED", "IN_PROGRESS"): "DISPATCH",
    ("QUEUED", "DONE"): "CLOSED",
    ("QUEUED", "ARCHIVED"): "WITHDRAWN",
    ("IN_PROGRESS", "REVIEW"): "REVIEW_REQUESTED",
    ("IN_PROGRESS", "DONE"): "DONE_SKIP_REVIEW",
    ("IN_PROGRESS", "QUEUED"): "UNASSIGN",
    ("REVIEW", "DONE"): "ACCEPTED",
    ("REVIEW", "IN_PROGRESS"): "REWORK",
    ("REVIEW", "QUEUED"): "REJECTED_RESCORE",
    ("DONE", "ARCHIVED"): "ARCHIVED",
}


def _blocked(frm: Any, to: str, reason: str) -> dict[str, Any]:
    return {"ok": False, "from": frm, "to": to, "reason": reason}


def transition_task(
    card: dict[str, Any],
    to: str,
    *,
    by: str,
    reason: str | None = None,
    skip_review: bool = False,
    at: str | None = None,
) -> dict[str, Any]:
    """Validate a task transition and return an event without mutating the card."""

    frm = card.get("status")
    if frm not in STATES or to not in STATES:
        return _blocked(frm, to, "UNKNOWN_STATE")
    if frm == "ARCHIVED":
        return _blocked(frm, to, "TERMINAL_STATE")

    resumed = frm in OVERLAY_STATES
    if resumed:
        if to != card.get("resume_to"):
            return _blocked(frm, to, "RESUME_TARGET_MISMATCH")
        if not reason or not reason.strip():
            return _blocked(frm, to, "REASON_REQUIRED")
    elif to in OVERLAY_STATES:
        if not reason or not reason.strip():
            return _blocked(frm, to, "REASON_REQUIRED")
    elif (frm, to) not in STRUCTURAL_TRANSITIONS:
        return _blocked(frm, to, "ILLEGAL_TRANSITION")

    if not resumed and (frm, to) in REASON_REQUIRED and not (reason and reason.strip()):
        return _blocked(frm, to, "REASON_REQUIRED")
    if (frm, to) == ("IN_PROGRESS", "DONE") and not skip_review:
        return _blocked(frm, to, "EXPLICIT_SKIP_REVIEW_REQUIRED")
    if (frm, to) == ("QUEUED", "IN_PROGRESS"):
        decision_ref = card.get("decision_ref")
        if decision_ref and card.get("decision_status") != "RECORDED":
            return _blocked(frm, to, "DECISION_RECORD_REQUIRED")

    if card.get("requires_git_closure", True):
        closure = card.get("git_closure") or {}
        if to == "REVIEW" and not closure.get("review_ready"):
            return _blocked(frm, to, "GIT_CLOSURE_REVIEW_REQUIRED")
        if to == "DONE" and not closure.get("done_ready"):
            return _blocked(frm, to, "GIT_CLOSURE_DONE_REQUIRED")
        if to == "ARCHIVED" and not closure.get("archive_ready"):
            return _blocked(frm, to, "GIT_CLOSURE_ARCHIVE_REQUIRED")
    elif to in {"REVIEW", "DONE"} and not card.get("result_ref"):
        return _blocked(frm, to, "RESULT_EVIDENCE_REQUIRED")

    if resumed:
        event_name = "UNBLOCKED" if frm == "BLOCKED" else "RESUMED"
    elif to in OVERLAY_STATES:
        event_name = to
    else:
        event_name = EVENT_NAMES[(frm, to)]

    event = {
        "at": at or datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "by": by,
        "task_id": card.get("task_id"),
        "from": frm,
        "to": to,
        "reason": reason or "",
        "event": event_name,
    }
    if to in OVERLAY_STATES:
        event["resume_to"] = frm
    return {"ok": True, "from": frm, "to": to, "reason": None, "event": event}
