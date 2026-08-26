"""A small, source-agnostic contract for scoped memory reads.

The public core does not own a memory file or a private knowledge store. Callers
provide an index of registered references and explicitly choose which references
belong in a task's context. The contract keeps that boundary observable:
malformed scope, unapproved entries, mismatched ownership, and oversized context
all fail closed; a successful run can only produce a review candidate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA_VERSION = "personal-ai-os.memory-context/v1"
REVIEW_SCHEMA_VERSION = "personal-ai-os.memory-review-request/v1"
READY = "READY"
BLOCKED = "BLOCKED"
SKIPPED = "SKIPPED"
MEMORY_REVIEW_REQUESTED = "MEMORY_REVIEW_REQUESTED"
REQUIRE_READ = "require_read"
READABLE_STATUSES = frozenset({"ACTIVE", "APPROVED"})
_SUBJECT_KINDS = frozenset({"person", "team"})
_MAX_CONTEXT_CHARS = 8_000
_MAX_OBSERVATION_CHARS = 2_000


def _base(
    status: str,
    reason: str,
    *,
    scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    public_scope: dict[str, Any] = {}
    if scope:
        public_scope = {
            "policy": scope.get("policy"),
            "subject": dict(scope["subject"]),
            "domain_id": scope.get("domain_id"),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "policy": public_scope.get("policy"),
        "scope": public_scope,
        "memory_ref_ids": [],
        "entries": [],
    }


def _context(task: Mapping[str, Any]) -> Mapping[str, Any]:
    value = task.get("context")
    return value if isinstance(value, Mapping) else {}


def _subject(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    kind = str(value.get("kind") or "").strip()
    identifier = str(value.get("id") or "").strip()
    if kind not in _SUBJECT_KINDS or not identifier:
        return None
    return {"kind": kind, "id": identifier}


def _requested_refs(value: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(value, list) or not value:
        return None, "MEMORY_REFS_REQUIRED"
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            memory_id = item.strip()
            descriptor: dict[str, Any] = {"memory_id": memory_id}
        elif isinstance(item, Mapping):
            memory_id = str(item.get("memory_id") or "").strip()
            descriptor = dict(item)
            descriptor["memory_id"] = memory_id
        else:
            return None, "MEMORY_REF_INVALID"
        if not memory_id:
            return None, "MEMORY_REF_INVALID"
        if memory_id in seen:
            return None, "MEMORY_REF_DUPLICATE"
        seen.add(memory_id)
        result.append(descriptor)
    return result, None


def _required_scope(
    task: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    context = _context(task)
    policy = context.get("memory_policy")
    if policy is None:
        return None, None
    if policy != REQUIRE_READ:
        return None, "MEMORY_POLICY_INVALID"

    subject = _subject(context.get("memory_subject"))
    domain_id = str(context.get("memory_domain_id") or "").strip()
    task_domain = str(task.get("domain_id") or "").strip()
    refs, refs_error = _requested_refs(context.get("memory_refs"))
    if subject is None or not domain_id or not task_domain or refs_error:
        return None, refs_error or "MEMORY_SCOPE_REQUIRED"
    if domain_id != task_domain:
        return None, "MEMORY_SCOPE_MISMATCH"
    return {
        "policy": REQUIRE_READ,
        "subject": subject,
        "domain_id": domain_id,
        "requested_refs": refs,
    }, None


def _registered_index(
    registered_refs: Any,
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    if registered_refs is None:
        return {}, None
    if isinstance(registered_refs, Mapping):
        raw_items = []
        for key, value in registered_refs.items():
            if not isinstance(value, Mapping):
                return None, "MEMORY_REGISTERED_REF_INVALID"
            item = dict(value)
            item.setdefault("memory_id", str(key).strip())
            raw_items.append(item)
    elif isinstance(registered_refs, Sequence) and not isinstance(
        registered_refs, (str, bytes)
    ):
        raw_items = list(registered_refs)
    else:
        return None, "MEMORY_REGISTERED_REF_INVALID"

    indexed: dict[str, dict[str, Any]] = {}
    for value in raw_items:
        if not isinstance(value, Mapping):
            return None, "MEMORY_REGISTERED_REF_INVALID"
        item = dict(value)
        memory_id = str(item.get("memory_id") or "").strip()
        if not memory_id or memory_id in indexed:
            return None, "MEMORY_REGISTERED_REF_INVALID"
        item["memory_id"] = memory_id
        indexed[memory_id] = item
    return indexed, None


def _list_text(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _same_subject(left: Any, right: Mapping[str, str]) -> bool:
    return _subject(left) == dict(right)


def _entry_from_registered(
    reference: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    subject = reference.get("subject")
    domain_id = str(reference.get("domain_id") or "").strip()
    if _subject(subject) is None or not domain_id:
        raise ValueError("MEMORY_SCOPE_METADATA_REQUIRED")
    if not _same_subject(subject, scope["subject"]) or domain_id != scope["domain_id"]:
        raise ValueError("MEMORY_SCOPE_MISMATCH")
    status = str(reference.get("status") or "").strip().upper()
    if status not in READABLE_STATUSES:
        raise ValueError("MEMORY_REF_NOT_APPROVED")
    source_ref = str(
        reference.get("source_ref") or reference.get("entry_ref") or ""
    ).strip()
    if not source_ref:
        raise ValueError("MEMORY_REF_SOURCE_REQUIRED")
    facts = _list_text(reference.get("facts"))
    decisions = _list_text(reference.get("decisions"))
    statement = str(reference.get("statement") or "").strip()
    if statement and not facts:
        facts = [statement]
    if not facts and not decisions:
        raise ValueError("MEMORY_REF_CONTENT_REQUIRED")
    return {
        "memory_id": str(reference["memory_id"]).strip(),
        "title": str(reference.get("title") or reference["memory_id"]).strip(),
        "status": status,
        "facts": facts,
        "decisions": decisions,
        "source_ref": source_ref,
        "scope": {
            "subject": dict(scope["subject"]),
            "domain_id": scope["domain_id"],
        },
    }


def read_memory_context(
    task: Mapping[str, Any],
    *,
    registered_refs: Mapping[str, Mapping[str, Any]]
    | Sequence[Mapping[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Read only explicitly requested, scope-matching registered references.

    The function is pure and source-agnostic. A caller may obtain registered
    references from any memory provider, but the resulting projection contains
    only selected facts, decisions, and their source references.
    """
    if not isinstance(task, Mapping):
        return _base(BLOCKED, "MEMORY_TASK_INVALID")
    scope, scope_error = _required_scope(task)
    if scope is None and scope_error is None:
        return _base(SKIPPED, "MEMORY_POLICY_NOT_REQUESTED")
    if scope_error:
        return _base(BLOCKED, scope_error)
    assert scope is not None

    index, index_error = _registered_index(registered_refs)
    if index_error:
        return _base(BLOCKED, index_error, scope=scope)
    assert index is not None
    if not index:
        return _base(BLOCKED, "MEMORY_SOURCE_REQUIRED", scope=scope)

    selected: list[dict[str, Any]] = []
    context_chars = 0
    for requested in scope["requested_refs"]:
        memory_id = requested["memory_id"]
        reference = index.get(memory_id)
        if reference is None:
            return _base(BLOCKED, "MEMORY_REF_NOT_FOUND", scope=scope)
        try:
            for field in ("subject", "domain_id"):
                if field in requested and requested[field] != reference.get(field):
                    raise ValueError("MEMORY_SCOPE_MISMATCH")
            entry = _entry_from_registered(reference, scope)
        except ValueError as exc:
            return _base(BLOCKED, str(exc), scope=scope)
        selected.append(entry)
        context_chars += sum(
            len(value)
            for field in ("facts", "decisions")
            for value in entry[field]
        )
        if context_chars > _MAX_CONTEXT_CHARS:
            return _base(BLOCKED, "MEMORY_CONTEXT_TOO_LARGE", scope=scope)

    memory_ref_ids = [entry["memory_id"] for entry in selected]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": READY,
        "reason": "MEMORY_READ_READY",
        "policy": scope["policy"],
        "scope": {
            "subject": dict(scope["subject"]),
            "domain_id": scope["domain_id"],
        },
        "memory_ref_ids": memory_ref_ids,
        "context_char_count": context_chars,
        "entries": selected,
        "read_receipt": {
            "source": "registered_refs",
            "memory_ref_ids": memory_ref_ids,
            "status": READY,
        },
    }


def request_memory_review(
    task: Mapping[str, Any],
    execution: Mapping[str, Any],
    *,
    observation: str,
    candidate_id: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Create a review-only memory candidate after a verified successful read."""
    scope, scope_error = _required_scope(task)
    if scope is None and scope_error is None:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": SKIPPED,
            "reason": "MEMORY_POLICY_NOT_REQUESTED",
        }
    if scope_error:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": scope_error,
        }
    assert scope is not None
    if not isinstance(execution, Mapping):
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_EXECUTION_INVALID",
        }
    run_status = str(execution.get("status") or "").strip().upper()
    if run_status not in {"SUCCEEDED", "DONE", "COMPLETED"}:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_REVIEW_REQUIRES_SUCCESS",
        }
    if execution.get("memory_read_status") != READY:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_READ_REQUIRED_BEFORE_REVIEW",
        }
    expected_ids = [item["memory_id"] for item in scope["requested_refs"]]
    if execution.get("memory_ref_ids") != expected_ids:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_READ_RECEIPT_MISMATCH",
        }
    text = str(observation or "").strip()
    if not text:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_REVIEW_INPUT_REQUIRED",
        }
    if len(text) > _MAX_OBSERVATION_CHARS:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_REVIEW_INPUT_TOO_LONG",
        }
    task_id = str(task.get("task_id") or "").strip()
    run_id = str(execution.get("run_id") or "").strip()
    if not task_id or not run_id:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_REVIEW_ID_REQUIRED",
        }
    generated_id = str(candidate_id or f"memory-review:{task_id}:{run_id}").strip()
    if not generated_id:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": BLOCKED,
            "reason": "MEMORY_REVIEW_ID_REQUIRED",
        }
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "event_type": MEMORY_REVIEW_REQUESTED,
        "status": MEMORY_REVIEW_REQUESTED,
        "observed_at": observed_at or str(execution.get("completed_at") or "UNKNOWN"),
        "task_id": task_id,
        "run_id": run_id,
        "candidate": {
            "candidate_id": generated_id,
            "status": "CANDIDATE",
            "statement": text,
            "subject": dict(scope["subject"]),
            "domain_id": scope["domain_id"],
            "source_task_id": task_id,
            "source_run_id": run_id,
            "memory_ref_ids": expected_ids,
            "promotion": {"status": "NOT_REQUESTED", "authorized": False},
            "default_context_enabled": False,
        },
    }


__all__ = [
    "BLOCKED",
    "MEMORY_REVIEW_REQUESTED",
    "READY",
    "REQUIRE_READ",
    "SCHEMA_VERSION",
    "SKIPPED",
    "read_memory_context",
    "request_memory_review",
]
