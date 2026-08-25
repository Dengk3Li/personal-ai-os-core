"""Pure contract for one execution owner and bounded progress.

The module is an adapter-level boundary, not a runtime store or a worker.
Callers pass an authoritative snapshot in and receive a new JSON-compatible
snapshot out. ``revision`` is the compare-and-swap token: a caller that
persists the result must write it only when the expected revision still
matches. No function starts a process, calls a model, writes a database, or
accepts a review.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping


SCHEMA_VERSION = "personal-ai-os.single-owner-progression/v1"
ACTIVE_STATUSES = frozenset({"CLAIMED", "RUNNING"})
KNOWN_STATUSES = frozenset(
    {
        "READY",
        "CLAIMED",
        "RUNNING",
        "STOPPED",
        "FAILED",
        "RECOVERY_REQUIRED",
        "WAITING_REVIEW",
    }
)


class ContractViolation(ValueError):
    """A stable, machine-readable contract boundary failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _copy(value: Any) -> Any:
    return deepcopy(value)


def _text(value: Any, code: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(code, f"{label} must be a non-empty string")
    return value.strip()


def _non_negative_int(value: Any, code: str, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractViolation(code, f"{label} must be a non-negative integer")
    return value


def _positive_int(value: Any, code: str, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractViolation(code, f"{label} must be a positive integer")
    return value


def _timestamp(value: Any, code: str, label: str) -> datetime:
    text = _text(value, code, label)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractViolation(code, f"{label} must be ISO-8601") from exc


def _policy(policy: Mapping[str, Any] | None) -> dict[str, int]:
    raw = dict(policy or {})
    return {
        "max_steps": _positive_int(
            raw.get("max_steps", 3), "INVALID_POLICY", "max_steps"
        ),
        "max_tokens": _positive_int(
            raw.get("max_tokens", 100_000), "INVALID_POLICY", "max_tokens"
        ),
        "failure_budget": _non_negative_int(
            raw.get("failure_budget", 0), "INVALID_POLICY", "failure_budget"
        ),
    }


def create_execution_state(
    *, task_id: str, policy: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Create a dispatchable slot without claiming or executing it."""

    return {
        "schema_version": SCHEMA_VERSION,
        "contract": "single-owner-bounded-progression",
        "task_id": _text(task_id, "INVALID_TASK", "task_id"),
        "status": "READY",
        "revision": 0,
        "policy": _policy(policy),
        "usage": {"steps": 0, "tokens": 0, "failures": 0},
        "owner": None,
        "lease": None,
        "last_owner": None,
        "triggers": [],
        "checkpoints": [],
        "stop_reason": None,
        "last_stop": None,
        "recovery": None,
        "review": None,
    }


def _validate(state: Mapping[str, Any]) -> None:
    if not isinstance(state, Mapping) or state.get("schema_version") != SCHEMA_VERSION:
        raise ContractViolation("UNSUPPORTED_SCHEMA", "execution state schema is unsupported")
    _text(state.get("task_id"), "INVALID_STATE", "task_id")
    if state.get("status") not in KNOWN_STATUSES:
        raise ContractViolation("INVALID_STATE", "execution status is unknown")
    revision = state.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ContractViolation("INVALID_STATE", "revision must be a non-negative integer")
    _policy(state.get("policy"))
    usage = state.get("usage")
    if not isinstance(usage, Mapping):
        raise ContractViolation("INVALID_STATE", "usage is required")
    for field in ("steps", "tokens", "failures"):
        _non_negative_int(usage.get(field), "INVALID_STATE", f"usage.{field}")
    if not isinstance(state.get("triggers"), list) or not isinstance(
        state.get("checkpoints"), list
    ):
        raise ContractViolation("INVALID_STATE", "triggers and checkpoints must be arrays")


def _next(
    state: Mapping[str, Any], expected_revision: int | None = None
) -> dict[str, Any]:
    _validate(state)
    if expected_revision is not None and state.get("revision") != expected_revision:
        raise ContractViolation(
            "STALE_STATE",
            f"expected revision {expected_revision}, observed {state.get('revision')}",
        )
    result = _copy(state)
    result["revision"] += 1
    return result


def select_ready_task(
    tasks: list[Mapping[str, Any]], decisions: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Pick one task only from explicit READY decisions.

    The progression policy remains the authority for producing each decision.
    This function only chooses among explicit ``READY`` decisions, allowing
    policy and storage to remain separate without inferring dispatchability.
    """

    if not isinstance(tasks, list) or not isinstance(decisions, Mapping):
        return {
            "task": None,
            "disposition": "UNKNOWN",
            "reason_code": "READY_INPUT_UNKNOWN",
            "may_dispatch": False,
        }

    def sort_key(task: Mapping[str, Any]) -> tuple[int, str]:
        seq = task.get("seq", 0)
        try:
            seq_num = int(seq)
        except (TypeError, ValueError):
            seq_num = 2**31 - 1
        return seq_num, str(task.get("task_id") or "")

    for task in sorted(tasks, key=sort_key):
        task_id = task.get("task_id")
        decision = decisions.get(task_id) if isinstance(task_id, str) else None
        if (
            isinstance(task_id, str)
            and task.get("status") == "QUEUED"
            and isinstance(decision, Mapping)
            and decision.get("disposition") == "READY"
            and decision.get("may_dispatch") is True
        ):
            return {
                "task": _copy(dict(task)),
                "disposition": "READY",
                "may_dispatch": True,
                "reason_code": "READY_SELECTED",
            }
    return {
        "task": None,
        "disposition": "STOP",
        "may_dispatch": False,
        "reason_code": "NO_READY_TASK",
    }


def enqueue_trigger(
    state: Mapping[str, Any],
    *,
    trigger_id: str,
    dedupe_key: str,
    source: str,
    requested_at: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Add a trigger or merge it into the existing idempotency key."""

    trigger_id = _text(trigger_id, "INVALID_TRIGGER", "trigger_id")
    dedupe_key = _text(dedupe_key, "INVALID_TRIGGER", "dedupe_key")
    source = _text(source, "INVALID_TRIGGER", "source")
    _timestamp(requested_at, "INVALID_TRIGGER", "requested_at")
    if any(
        trigger_id in item.get("trigger_ids", [])
        for item in state.get("triggers", [])
    ):
        raise ContractViolation(
            "TRIGGER_ALREADY_RECORDED", f"trigger {trigger_id} is already recorded"
        )
    result = _next(state, expected_revision)
    existing = next(
        (item for item in result["triggers"] if item.get("dedupe_key") == dedupe_key),
        None,
    )
    if existing is not None:
        existing["trigger_ids"].append(trigger_id)
        existing["merged_count"] += 1
        existing["last_requested_at"] = requested_at
        return {"state": result, "disposition": "MERGED", "trigger": _copy(existing)}
    item = {
        "dedupe_key": dedupe_key,
        "source": source,
        "first_requested_at": requested_at,
        "last_requested_at": requested_at,
        "merged_count": 1,
        "trigger_ids": [trigger_id],
    }
    result["triggers"].append(item)
    return {"state": result, "disposition": "ENQUEUED", "trigger": _copy(item)}


def _assert_claim(
    state: Mapping[str, Any],
    owner_id: str,
    claim_id: str,
    observed_at: str | None = None,
) -> None:
    _text(owner_id, "INVALID_OWNER", "owner_id")
    _text(claim_id, "INVALID_CLAIM", "claim_id")
    if state.get("status") not in ACTIVE_STATUSES:
        raise ContractViolation("OWNER_NOT_ACTIVE", "the execution owner is not active")
    owner = state.get("owner") or {}
    lease = state.get("lease") or {}
    if owner.get("owner_id") != owner_id or owner.get("claim_id") != claim_id:
        raise ContractViolation("OWNER_MISMATCH", "only the current owner may mutate execution")
    if lease.get("owner_id") != owner_id or lease.get("claim_id") != claim_id:
        raise ContractViolation("LEASE_MISMATCH", "current owner lease does not match claim")
    if observed_at is not None:
        observed = _timestamp(observed_at, "INVALID_LEASE", "observed_at")
        expiry = _timestamp(lease.get("expires_at"), "INVALID_LEASE", "lease")
        if expiry <= observed:
            raise ContractViolation(
                "LEASE_EXPIRED",
                "owner lease expired; record recovery before any further side effect",
            )


def _clear_owner(result: dict[str, Any]) -> None:
    if result.get("owner") is not None:
        result["last_owner"] = _copy(result["owner"])
    result["owner"] = None
    result["lease"] = None


def claim_owner(
    state: Mapping[str, Any],
    *,
    owner_id: str,
    claim_id: str,
    claimed_at: str,
    lease_expires_at: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Atomically claim a READY slot; recovery must precede a takeover."""

    _text(owner_id, "INVALID_OWNER", "owner_id")
    _text(claim_id, "INVALID_CLAIM", "claim_id")
    start = _timestamp(claimed_at, "INVALID_CLAIM", "claimed_at")
    expiry = _timestamp(lease_expires_at, "INVALID_CLAIM", "lease_expires_at")
    if expiry <= start:
        raise ContractViolation("INVALID_CLAIM", "lease_expires_at must be after claimed_at")
    status = state.get("status")
    if status == "RECOVERY_REQUIRED":
        raise ContractViolation("RECOVERY_ACK_REQUIRED", "recovery must be acknowledged first")
    if status == "WAITING_REVIEW":
        raise ContractViolation("REVIEW_REQUIRED", "human review must decide before another claim")
    if status == "STOPPED":
        raise ContractViolation("HUMAN_RESUME_REQUIRED", "a stopped execution needs explicit resume")
    if status == "FAILED":
        raise ContractViolation("FAILED_NOT_RETRYABLE", "failed execution needs an explicit recovery path")
    if status != "READY":
        raise ContractViolation("OWNER_ALREADY_CLAIMED", "execution is already claimed or running")
    result = _next(state, expected_revision)
    result["status"] = "CLAIMED"
    result["owner"] = {"owner_id": owner_id, "claim_id": claim_id, "claimed_at": claimed_at}
    result["lease"] = {
        "owner_id": owner_id,
        "claim_id": claim_id,
        "claimed_at": claimed_at,
        "expires_at": lease_expires_at,
    }
    result["stop_reason"] = None
    result["recovery"] = None
    result["review"] = None
    return result


def renew_lease(
    state: Mapping[str, Any],
    *,
    owner_id: str,
    claim_id: str,
    lease_expires_at: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Extend only the current owner's lease; never transfer ownership."""

    expiry = _timestamp(lease_expires_at, "INVALID_LEASE", "lease_expires_at")
    _validate(state)
    if expected_revision is not None and state.get("revision") != expected_revision:
        raise ContractViolation(
            "STALE_STATE",
            f"expected revision {expected_revision}, observed {state.get('revision')}",
        )
    _assert_claim(state, owner_id, claim_id)
    current_expiry = _timestamp(state["lease"]["expires_at"], "INVALID_LEASE", "current lease")
    if expiry <= current_expiry:
        raise ContractViolation("INVALID_LEASE", "new lease must extend the current lease")
    result = _next(state, expected_revision)
    result["lease"]["expires_at"] = lease_expires_at
    return result


def expire_lease(state: Mapping[str, Any], *, observed_at: str) -> dict[str, Any]:
    """Turn an expired active claim into a recovery barrier, never a takeover."""

    observed = _timestamp(observed_at, "INVALID_RECOVERY", "observed_at")
    _validate(state)
    if state.get("status") not in ACTIVE_STATUSES or not state.get("lease"):
        return _copy(state)
    expiry = _timestamp(state["lease"]["expires_at"], "INVALID_RECOVERY", "lease")
    if expiry > observed:
        return _copy(state)
    result = _next(state)
    result["status"] = "RECOVERY_REQUIRED"
    result["stop_reason"] = "LEASE_EXPIRED"
    result["recovery"] = {
        "reason": "owner lease expired before execution closure",
        "recorded_at": observed_at,
        "acknowledged_by": None,
        "acknowledged_at": None,
    }
    _clear_owner(result)
    return result


def authorize_step(
    state: Mapping[str, Any],
    *,
    owner_id: str,
    claim_id: str,
    step_id: str,
    estimated_tokens: int,
    authorized_at: str,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Persist a pre-side-effect checkpoint and enforce budgets before work."""

    step_id = _text(step_id, "INVALID_STEP", "step_id")
    _non_negative_int(estimated_tokens, "INVALID_STEP", "estimated_tokens")
    _timestamp(authorized_at, "INVALID_STEP", "authorized_at")
    _assert_claim(state, owner_id, claim_id, observed_at=authorized_at)
    existing = next(
        (item for item in state["checkpoints"] if item.get("step_id") == step_id), None
    )
    if existing is not None:
        return {
            "state": _copy(state),
            "authorized": False,
            "disposition": "DUPLICATE_STEP",
            "checkpoint": _copy(existing),
        }
    usage = state["usage"]
    policy = state["policy"]
    if (
        usage["steps"] + 1 > policy["max_steps"]
        or usage["tokens"] + estimated_tokens > policy["max_tokens"]
    ):
        result = _next(state, expected_revision)
        result["status"] = "STOPPED"
        result["stop_reason"] = "BUDGET_LIMITED"
        result["last_stop"] = {
            "reason": "BUDGET_LIMITED",
            "at": authorized_at,
            "step_id": step_id,
        }
        _clear_owner(result)
        return {
            "state": result,
            "authorized": False,
            "disposition": "STOPPED",
            "checkpoint": None,
        }
    result = _next(state, expected_revision)
    result["status"] = "RUNNING"
    result["usage"]["steps"] += 1
    result["usage"]["tokens"] += estimated_tokens
    checkpoint = {
        "step_id": step_id,
        "status": "AUTHORIZED",
        "estimated_tokens": estimated_tokens,
        "authorized_at": authorized_at,
        "outcome": None,
        "reason": None,
        "recorded_at": None,
    }
    result["checkpoints"].append(checkpoint)
    return {
        "state": result,
        "authorized": True,
        "disposition": "AUTHORIZED",
        "checkpoint": _copy(checkpoint),
    }


def record_step_result(
    state: Mapping[str, Any],
    *,
    owner_id: str,
    claim_id: str,
    step_id: str,
    outcome: str,
    recorded_at: str,
    reason: str = "",
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Record a known result or stop at recovery when side effects are uncertain."""

    step_id = _text(step_id, "INVALID_STEP", "step_id")
    if outcome not in {"completed", "failed", "uncertain"}:
        raise ContractViolation(
            "INVALID_RESULT", "outcome must be completed, failed, or uncertain"
        )
    _timestamp(recorded_at, "INVALID_RESULT", "recorded_at")
    _assert_claim(state, owner_id, claim_id, observed_at=recorded_at)
    checkpoint = next(
        (item for item in state["checkpoints"] if item.get("step_id") == step_id), None
    )
    if checkpoint is None:
        raise ContractViolation(
            "CHECKPOINT_REQUIRED", "record a pre-side-effect checkpoint first"
        )
    if checkpoint.get("status") != "AUTHORIZED":
        return _copy(state)
    result = _next(state, expected_revision)
    target = next(item for item in result["checkpoints"] if item.get("step_id") == step_id)
    target.update(
        {
            "status": outcome.upper(),
            "outcome": outcome,
            "reason": str(reason or "").strip(),
            "recorded_at": recorded_at,
        }
    )
    if outcome == "uncertain":
        result["status"] = "RECOVERY_REQUIRED"
        result["stop_reason"] = "SIDE_EFFECT_UNCERTAIN"
        result["recovery"] = {
            "reason": str(reason or "side effect outcome is uncertain").strip(),
            "recorded_at": recorded_at,
            "acknowledged_by": None,
            "acknowledged_at": None,
        }
        _clear_owner(result)
    elif outcome == "failed":
        result["usage"]["failures"] += 1
        result["status"] = "FAILED"
        result["stop_reason"] = "EXECUTION_FAILED"
        result["last_stop"] = {
            "reason": "EXECUTION_FAILED",
            "at": recorded_at,
            "step_id": step_id,
            "detail": target["reason"],
        }
        _clear_owner(result)
    return result


def request_human_stop(
    state: Mapping[str, Any], *, actor: str, stopped_at: str, reason: str
) -> dict[str, Any]:
    """Stop active work at an explicit human boundary; no automatic resume."""

    actor = _text(actor, "INVALID_STOP", "actor")
    reason = _text(reason, "INVALID_STOP", "reason")
    _timestamp(stopped_at, "INVALID_STOP", "stopped_at")
    if state.get("status") not in ACTIVE_STATUSES:
        raise ContractViolation("STOP_NOT_ACTIVE", "only active execution can be stopped")
    result = _next(state)
    result["status"] = "STOPPED"
    result["stop_reason"] = "HUMAN_STOP"
    result["last_stop"] = {
        "reason": "HUMAN_STOP",
        "detail": reason,
        "by": actor,
        "at": stopped_at,
    }
    _clear_owner(result)
    return result


def resume_after_human_stop(
    state: Mapping[str, Any], *, resumed_by: str, resumed_at: str
) -> dict[str, Any]:
    """Return a human-stopped task to READY without claiming it."""

    resumed_by = _text(resumed_by, "INVALID_RESUME", "resumed_by")
    _timestamp(resumed_at, "INVALID_RESUME", "resumed_at")
    if state.get("status") != "STOPPED" or state.get("stop_reason") != "HUMAN_STOP":
        raise ContractViolation(
            "HUMAN_RESUME_REQUIRED",
            "only a human-stopped execution can be resumed",
        )
    result = _next(state)
    result["status"] = "READY"
    result["stop_reason"] = None
    result["last_stop"]["resumed_by"] = resumed_by
    result["last_stop"]["resumed_at"] = resumed_at
    return result


def acknowledge_recovery(
    state: Mapping[str, Any], *, acknowledged_by: str, acknowledged_at: str
) -> dict[str, Any]:
    """Clear a recovery barrier explicitly; it never replays or claims work."""

    acknowledged_by = _text(acknowledged_by, "INVALID_ACK", "acknowledged_by")
    _timestamp(acknowledged_at, "INVALID_ACK", "acknowledged_at")
    if state.get("status") != "RECOVERY_REQUIRED":
        raise ContractViolation("RECOVERY_NOT_PENDING", "recovery is not pending")
    result = _next(state)
    result["status"] = "READY"
    result["stop_reason"] = None
    result["recovery"]["acknowledged_by"] = acknowledged_by
    result["recovery"]["acknowledged_at"] = acknowledged_at
    result["recovery"]["acknowledged"] = True
    return result


def submit_for_review(
    state: Mapping[str, Any], *, owner_id: str, claim_id: str, submitted_at: str
) -> dict[str, Any]:
    """Close execution at review; acceptance remains an external human action."""

    _timestamp(submitted_at, "INVALID_REVIEW", "submitted_at")
    _assert_claim(state, owner_id, claim_id, observed_at=submitted_at)
    result = _next(state)
    result["status"] = "WAITING_REVIEW"
    result["review"] = {"status": "PENDING", "submitted_at": submitted_at}
    result["stop_reason"] = "REVIEW_REQUIRED"
    _clear_owner(result)
    return result
