"""A public, body-free contract for proposed working-practice candidates."""

from __future__ import annotations

import re
from typing import Any


PRACTICE_CANDIDATE_VERSION = "personal-ai-os.practice-candidate/v1"

_FIELDS = frozenset({"schema_version", "candidate_id", "source_refs", "scope", "review"})
_SCOPE_FIELDS = frozenset({"subject_ref", "domain_ref"})
_REVIEW_FIELDS = frozenset({"status", "reviewer_ref"})
_REVIEW_STATUSES = frozenset({"PROPOSED", "APPROVED", "REJECTED"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _supported_fields(value: dict[str, Any], allowed: frozenset[str], field: str) -> None:
    if not set(value).issubset(allowed):
        raise ValueError(f"{field} contains unsupported fields")


def _reference(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an opaque reference")
    normalized = value.strip()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field} must be an opaque reference")
    return normalized


def validate_practice_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one review-only practice candidate without persisting it.

    The public shape carries references and review state only. It intentionally
    has no statement, category, business label, local path, or credential
    field, so an adapter must keep those details on its private side.
    """

    candidate = _mapping(payload, "practice candidate")
    _supported_fields(candidate, _FIELDS, "practice candidate")
    if candidate.get("schema_version") != PRACTICE_CANDIDATE_VERSION:
        raise ValueError("unsupported practice candidate schema")

    source_refs = candidate.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs or len(source_refs) > 32:
        raise ValueError("practice candidate source references must be a bounded list")
    normalized_sources = [_reference(item, "source reference") for item in source_refs]
    if len(set(normalized_sources)) != len(normalized_sources):
        raise ValueError("practice candidate source references must be unique")

    scope = _mapping(candidate.get("scope"), "practice candidate scope")
    _supported_fields(scope, _SCOPE_FIELDS, "practice candidate scope")
    normalized_scope = {
        "subject_ref": _reference(scope.get("subject_ref"), "subject reference"),
        "domain_ref": _reference(scope.get("domain_ref"), "domain reference"),
    }

    review = _mapping(candidate.get("review"), "practice candidate review")
    _supported_fields(review, _REVIEW_FIELDS, "practice candidate review")
    status = review.get("status")
    if not isinstance(status, str) or status.upper().strip() not in _REVIEW_STATUSES:
        raise ValueError("unsupported practice candidate review status")
    normalized_status = status.upper().strip()
    normalized_review: dict[str, str] = {"status": normalized_status}
    if normalized_status == "PROPOSED":
        if "reviewer_ref" in review:
            raise ValueError("proposed practice candidate cannot have a reviewer")
    else:
        if "reviewer_ref" not in review:
            raise ValueError("reviewed practice candidate requires a reviewer")
        normalized_review["reviewer_ref"] = _reference(
            review["reviewer_ref"], "reviewer reference"
        )

    return {
        "schema_version": PRACTICE_CANDIDATE_VERSION,
        "candidate_id": _reference(candidate.get("candidate_id"), "candidate reference"),
        "source_refs": normalized_sources,
        "scope": normalized_scope,
        "review": normalized_review,
    }
