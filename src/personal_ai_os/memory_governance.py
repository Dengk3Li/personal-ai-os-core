"""Privacy-safe contracts for reading and proposing memory updates.

These contracts are deliberately separate from the provider-facing memory
context.  They let an executor prove that approved, scoped memory was read
before a run and that a later change is only a review candidate.  Neither
contract carries memory content or performs persistence.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping
from typing import Any


MEMORY_READ_RECEIPT_VERSION = "personal-ai-os.memory-read-receipt/v1"
MEMORY_UPDATE_CANDIDATE_VERSION = "personal-ai-os.memory-update-candidate/v1"

_READ_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_ref",
        "task_ref",
        "memory_refs",
        "scope",
        "authority",
        "freshness",
        "read_before_run",
    }
)
_UPDATE_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_ref",
        "read_receipt_ref",
        "source_refs",
        "scope",
        "review",
    }
)
_SCOPE_FIELDS = frozenset({"subject_ref", "domain_ref"})
_AUTHORITY_FIELDS = frozenset({"status", "decision_ref"})
_FRESHNESS_FIELDS = frozenset({"observed_at", "expires_at"})
_REVIEW_FIELDS = frozenset({"status", "reviewer_ref", "decision_ref"})
_REVIEW_STATUSES = frozenset({"PROPOSED", "APPROVED", "REJECTED"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_REFS = 32


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _supported_fields(
    value: Mapping[str, Any], allowed: frozenset[str], field: str
) -> None:
    if not set(value).issubset(allowed):
        raise ValueError(f"{field} contains unsupported fields")


def _reference(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an opaque reference")
    normalized = value.strip()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field} must be an opaque reference")
    return normalized


def _references(value: Any, field: str, *, required: bool = True) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or (required and not value) or len(value) > _MAX_REFS:
        raise ValueError(f"{field} must be a bounded list")
    result = [_reference(item, f"{field} reference") for item in value]
    if len(set(result)) != len(result):
        raise ValueError(f"{field} references must be unique")
    return result


def _scope(value: Any) -> dict[str, str]:
    scope = _mapping(value, "memory scope")
    _supported_fields(scope, _SCOPE_FIELDS, "memory scope")
    return {
        "subject_ref": _reference(scope.get("subject_ref"), "scope subject"),
        "domain_ref": _reference(scope.get("domain_ref"), "scope domain"),
    }


def _timestamp(value: Any, field: str) -> tuple[str, datetime.datetime]:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    normalized = value.strip()
    try:
        parsed = datetime.datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    return normalized, parsed


def _freshness(value: Any) -> dict[str, str]:
    freshness = _mapping(value, "memory freshness")
    _supported_fields(freshness, _FRESHNESS_FIELDS, "memory freshness")
    observed_text, observed = _timestamp(
        freshness.get("observed_at"), "freshness observed_at"
    )
    result = {"observed_at": observed_text}
    if "expires_at" in freshness:
        expires_text, expires = _timestamp(
            freshness.get("expires_at"), "freshness expires_at"
        )
        try:
            is_after = expires > observed
        except TypeError as exc:
            raise ValueError("freshness timestamps must use comparable offsets") from exc
        if not is_after:
            raise ValueError("freshness expires_at must be after observed_at")
        result["expires_at"] = expires_text
    return result


def validate_memory_read_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate proof that approved scoped memory was read before execution.

    The receipt contains references only.  ``read_before_run`` and approved
    authority are intentionally mandatory so callers cannot use a post-run or
    unapproved read as execution context.
    """

    record = _mapping(payload, "memory read receipt")
    _supported_fields(record, _READ_FIELDS, "memory read receipt")
    if record.get("schema_version") != MEMORY_READ_RECEIPT_VERSION:
        raise ValueError("unsupported memory read receipt schema")
    if record.get("read_before_run") is not True:
        raise ValueError("memory read receipt must be recorded before run")

    authority = _mapping(record.get("authority"), "memory authority")
    _supported_fields(authority, _AUTHORITY_FIELDS, "memory authority")
    status = str(authority.get("status") or "").strip().upper()
    if status != "APPROVED":
        raise ValueError("memory read authority must be approved")

    return {
        "schema_version": MEMORY_READ_RECEIPT_VERSION,
        "receipt_ref": _reference(record.get("receipt_ref"), "receipt reference"),
        "task_ref": _reference(record.get("task_ref"), "task reference"),
        "memory_refs": _references(record.get("memory_refs"), "memory"),
        "scope": _scope(record.get("scope")),
        "authority": {
            "status": status,
            "decision_ref": _reference(
                authority.get("decision_ref"), "authority decision"
            ),
        },
        "freshness": _freshness(record.get("freshness")),
        "read_before_run": True,
    }


def _review(value: Any) -> dict[str, str]:
    review = _mapping(value, "memory update review")
    _supported_fields(review, _REVIEW_FIELDS, "memory update review")
    status = str(review.get("status") or "").strip().upper()
    if status not in _REVIEW_STATUSES:
        raise ValueError("unsupported memory update review status")
    result = {"status": status}
    supplied_reviewer = "reviewer_ref" in review
    supplied_decision = "decision_ref" in review
    if status == "PROPOSED":
        if supplied_reviewer or supplied_decision:
            raise ValueError("proposed memory update cannot have a review decision")
    elif not supplied_reviewer or not supplied_decision:
        raise ValueError("reviewed memory update requires reviewer and decision references")
    else:
        result["reviewer_ref"] = _reference(review["reviewer_ref"], "reviewer reference")
        result["decision_ref"] = _reference(review["decision_ref"], "review decision")
    return result


def validate_memory_update_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a review-only memory update candidate.

    A candidate must point to a valid pre-run read receipt.  Even an approved
    review here is only a human review record; this contract has no activation
    or persistence operation.
    """

    record = _mapping(payload, "memory update candidate")
    _supported_fields(record, _UPDATE_FIELDS, "memory update candidate")
    if record.get("schema_version") != MEMORY_UPDATE_CANDIDATE_VERSION:
        raise ValueError("unsupported memory update candidate schema")

    # Validate the link shape without embedding a provider receipt or memory
    # body.  The actual receipt can be resolved by a private adapter.
    read_receipt_ref = _reference(
        record.get("read_receipt_ref"), "read receipt reference"
    )
    return {
        "schema_version": MEMORY_UPDATE_CANDIDATE_VERSION,
        "candidate_ref": _reference(record.get("candidate_ref"), "candidate reference"),
        "read_receipt_ref": read_receipt_ref,
        "source_refs": _references(record.get("source_refs"), "source"),
        "scope": _scope(record.get("scope")),
        "review": _review(record.get("review")),
    }


__all__ = [
    "MEMORY_READ_RECEIPT_VERSION",
    "MEMORY_UPDATE_CANDIDATE_VERSION",
    "validate_memory_read_receipt",
    "validate_memory_update_candidate",
]
