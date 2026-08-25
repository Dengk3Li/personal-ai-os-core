from __future__ import annotations

from copy import deepcopy
from typing import Any


MEMORY_CANDIDATE_VERSION = "personal-ai-os.memory-candidate/v1"
MEMORY_CATEGORIES = {"style", "workflow", "preference", "warning"}
MEMORY_SUBJECT_KINDS = {"person", "team"}
MEMORY_PRIVACY_CLASSES = {"private", "team"}
MEMORY_STATUSES = {"PROPOSED", "APPROVED", "REJECTED"}
MAX_MEMORY_STATEMENT_CHARACTERS = 2_000
MAX_OPERATING_PRACTICE_RULES = 32


def validate_memory_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one evidence-backed practice candidate before persistence."""

    if not isinstance(payload, dict):
        raise ValueError("memory candidate must be an object")
    candidate = deepcopy(payload)
    if candidate.get("schema_version") != MEMORY_CANDIDATE_VERSION:
        raise ValueError("unsupported memory candidate schema")
    candidate_id = str(candidate.get("candidate_id") or "").strip()
    subject = candidate.get("subject") or {}
    domain_id = str(candidate.get("domain_id") or "").strip()
    category = str(candidate.get("category") or "").strip()
    statement = str(candidate.get("statement") or "").strip()
    evidence_refs = candidate.get("evidence_refs") or []
    sample_count = candidate.get("sample_count")
    privacy_class = str(candidate.get("privacy_class") or "").strip()
    status = str(candidate.get("status") or "PROPOSED").upper()
    if not candidate_id or not domain_id or not statement:
        raise ValueError("candidate_id, domain_id, and statement are required")
    if len(statement) > MAX_MEMORY_STATEMENT_CHARACTERS:
        raise ValueError(
            f"memory statement exceeds {MAX_MEMORY_STATEMENT_CHARACTERS} characters"
        )
    if not isinstance(subject, dict):
        raise ValueError("memory subject must be an object")
    subject_kind = str(subject.get("kind") or "").strip()
    subject_id = str(subject.get("id") or "").strip()
    if subject_kind not in MEMORY_SUBJECT_KINDS or not subject_id:
        raise ValueError("memory subject must identify one person or team")
    if category not in MEMORY_CATEGORIES:
        raise ValueError("unsupported memory category")
    if not isinstance(evidence_refs, list) or not evidence_refs or any(
        not isinstance(item, str) or not item.strip() for item in evidence_refs
    ):
        raise ValueError("memory candidate requires evidence references")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 1:
        raise ValueError("sample_count must be a positive integer")
    if privacy_class not in MEMORY_PRIVACY_CLASSES:
        raise ValueError("unsupported memory privacy class")
    if status != "PROPOSED":
        raise ValueError("new memory candidates must start in PROPOSED")
    candidate.update(
        {
            "candidate_id": candidate_id,
            "subject": {"kind": subject_kind, "id": subject_id},
            "domain_id": domain_id,
            "category": category,
            "statement": statement,
            "evidence_refs": [item.strip() for item in evidence_refs],
            "sample_count": sample_count,
            "privacy_class": privacy_class,
            "status": status,
            "version": int(candidate.get("version") or 1),
        }
    )
    return candidate


def compile_operating_practices(
    candidates: list[dict[str, Any]],
    *,
    subject: dict[str, str],
    domain_id: str,
) -> dict[str, Any]:
    """Compile only approved, subject-scoped practices for one task domain."""

    subject_kind = str(subject.get("kind") or "").strip()
    subject_id = str(subject.get("id") or "").strip()
    if subject_kind not in MEMORY_SUBJECT_KINDS or not subject_id:
        raise ValueError("practice subject must identify one person or team")
    selected = [
        item
        for item in candidates
        if item.get("status") == "APPROVED"
        and item.get("subject", {}).get("kind") == subject_kind
        and item.get("subject", {}).get("id") == subject_id
        and item.get("domain_id") == domain_id
    ]
    if len(selected) > MAX_OPERATING_PRACTICE_RULES:
        raise ValueError(
            f"operating practice rule limit is {MAX_OPERATING_PRACTICE_RULES}"
        )
    evidence_refs: list[str] = []
    for item in selected:
        for reference in item.get("evidence_refs") or []:
            if reference not in evidence_refs:
                evidence_refs.append(reference)
    return {
        "schema_version": "personal-ai-os.operating-practices/v1",
        "subject": {"kind": subject_kind, "id": subject_id},
        "domain_id": domain_id,
        "rules": [str(item["statement"]) for item in selected],
        "candidate_ids": [str(item["candidate_id"]) for item in selected],
        "evidence_refs": evidence_refs,
    }
