"""Public, synthetic-only contract for source-grounded report acceptance.

The contract describes the shape of a report handoff without carrying source
content, local paths, URLs, model prompts, or private task identifiers.  It is
an acceptance boundary, not a report generator: a terminal artifact proves
that an executor stopped, while only an explicit human acceptance can close a
clean report.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "personal-ai-os.research-report-acceptance/v1"
_BLOCKS = (
    "brief",
    "source_manifest",
    "evidence_matrix",
    "outline",
    "chapters",
    "visual",
    "final_receipt",
)
_SOURCE_STATUSES = frozenset({"KNOWN", "UNKNOWN", "CONFLICT"})
_EVIDENCE_STATUSES = frozenset({"SUPPORTED", "UNKNOWN", "CONFLICT"})
_TOP_FIELDS = frozenset({"schema_version", "synthetic_only", *_BLOCKS, "review"})
_BLOCK_FIELDS = {
    "brief": frozenset({"brief_id", "question", "scope"}),
    "source_manifest": frozenset({"source_id", "kind", "status"}),
    "evidence_matrix": frozenset({"evidence_id", "claim_ref", "source_ids", "status"}),
    "outline": frozenset({"section_id", "title"}),
    "chapters": frozenset({"chapter_id", "outline_id", "status"}),
    "visual": frozenset({"visual_id", "kind", "status"}),
    "final_receipt": frozenset({"artifact_terminal", "human_accepted", "receipt_ref"}),
}
_FORBIDDEN_KEYS = frozenset(
    {
        "absolute_path",
        "command",
        "file",
        "filename",
        "local_path",
        "path",
        "prompt",
        "reference",
        "uri",
        "url",
    }
)


class ResearchReportAcceptanceError(ValueError):
    """Raised when a report acceptance payload violates the public contract."""


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ResearchReportAcceptanceError(f"{field} is required")
    return text


def _reject_private_fields(value: Any, *, location: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in _FORBIDDEN_KEYS:
                raise ResearchReportAcceptanceError(
                    f"{location}.{key} is not allowed in a public synthetic contract"
                )
            _reject_private_fields(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private_fields(child, location=f"{location}[{index}]")


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchReportAcceptanceError(f"{field} must be an object")
    return value


def _rows(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ResearchReportAcceptanceError(f"{field} must be a non-empty list")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        rows.append(_object(row, f"{field}[{index}]"))
    return rows


def _check_fields(value: dict[str, Any], field: str) -> None:
    allowed = _BLOCK_FIELDS[field]
    unexpected = set(value) - allowed
    if unexpected:
        raise ResearchReportAcceptanceError(
            f"{field} contains unsupported fields: {sorted(unexpected)}"
        )


def _row_ids(rows: list[dict[str, Any]], field: str, key: str) -> set[str]:
    identifiers: set[str] = set()
    for index, row in enumerate(rows):
        identifier = _text(row.get(key), f"{field}[{index}].{key}")
        if identifier in identifiers:
            raise ResearchReportAcceptanceError(f"duplicate {field} identifier: {identifier}")
        identifiers.add(identifier)
    return identifiers


def _validate_structure(contract: dict[str, Any]) -> None:
    unexpected = set(contract) - _TOP_FIELDS
    if unexpected:
        raise ResearchReportAcceptanceError(
            f"research report acceptance contains unsupported fields: {sorted(unexpected)}"
        )
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise ResearchReportAcceptanceError("unsupported research report acceptance schema")
    if contract.get("synthetic_only") is not True:
        raise ResearchReportAcceptanceError("research report acceptance must be synthetic_only")
    _reject_private_fields(contract)

    brief = _object(contract.get("brief"), "brief")
    _check_fields(brief, "brief")
    for key in ("brief_id", "question", "scope"):
        _text(brief.get(key), f"brief.{key}")

    sources = _rows(contract.get("source_manifest"), "source_manifest")
    source_ids = _row_ids(sources, "source_manifest", "source_id")
    for index, source in enumerate(sources):
        _check_fields(source, "source_manifest")
        kind = _text(source.get("kind"), f"source_manifest[{index}].kind")
        if kind != "synthetic":
            raise ResearchReportAcceptanceError(
                "source_manifest entries must use kind=synthetic"
            )
        status = _text(source.get("status"), f"source_manifest[{index}].status").upper()
        if status not in _SOURCE_STATUSES:
            raise ResearchReportAcceptanceError(
                f"unsupported source status: {status}"
            )

    evidence = _rows(contract.get("evidence_matrix"), "evidence_matrix")
    _row_ids(evidence, "evidence_matrix", "evidence_id")
    for index, row in enumerate(evidence):
        _check_fields(row, "evidence_matrix")
        status = _text(row.get("status"), f"evidence_matrix[{index}].status").upper()
        if status not in _EVIDENCE_STATUSES:
            raise ResearchReportAcceptanceError(
                f"unsupported evidence status: {status}"
            )
        references = row.get("source_ids")
        if not isinstance(references, list) or not references:
            raise ResearchReportAcceptanceError(
                f"evidence_matrix[{index}].source_ids must be a non-empty list"
            )
        unknown_sources = set(references) - source_ids
        if unknown_sources:
            raise ResearchReportAcceptanceError(
                f"evidence references unknown sources: {sorted(unknown_sources)}"
            )
        _text(row.get("claim_ref"), f"evidence_matrix[{index}].claim_ref")

    outline = _rows(contract.get("outline"), "outline")
    _row_ids(outline, "outline", "section_id")
    for index, row in enumerate(outline):
        _check_fields(row, "outline")
        _text(row.get("title"), f"outline[{index}].title")

    chapters = _rows(contract.get("chapters"), "chapters")
    outline_ids = _row_ids(outline, "outline", "section_id")
    _row_ids(chapters, "chapters", "chapter_id")
    for index, row in enumerate(chapters):
        _check_fields(row, "chapters")
        outline_id = _text(row.get("outline_id"), f"chapters[{index}].outline_id")
        if outline_id not in outline_ids:
            raise ResearchReportAcceptanceError(
                f"chapter references unknown outline section: {outline_id}"
            )

    visual = _rows(contract.get("visual"), "visual")
    _row_ids(visual, "visual", "visual_id")
    for index, row in enumerate(visual):
        _check_fields(row, "visual")
        _text(row.get("kind"), f"visual[{index}].kind")

    final_receipt = _object(contract.get("final_receipt"), "final_receipt")
    _check_fields(final_receipt, "final_receipt")
    for key in ("artifact_terminal", "human_accepted"):
        if not isinstance(final_receipt.get(key), bool):
            raise ResearchReportAcceptanceError(
                f"final_receipt.{key} must be boolean"
            )
    _text(final_receipt.get("receipt_ref"), "final_receipt.receipt_ref")


def _review(contract: dict[str, Any]) -> dict[str, Any]:
    sources = contract["source_manifest"]
    evidence = contract["evidence_matrix"]
    reasons: list[str] = []
    source_statuses = [str(row["status"]).upper() for row in sources]
    evidence_statuses = [str(row["status"]).upper() for row in evidence]
    if "UNKNOWN" in source_statuses:
        reasons.append("SOURCE_UNKNOWN")
    if "CONFLICT" in source_statuses:
        reasons.append("SOURCE_CONFLICT")
    if "UNKNOWN" in evidence_statuses:
        reasons.append("EVIDENCE_UNKNOWN")
    if "CONFLICT" in evidence_statuses:
        reasons.append("EVIDENCE_CONFLICT")

    final_receipt = contract["final_receipt"]
    if reasons:
        status = "IN_REVIEW"
    elif not final_receipt["artifact_terminal"]:
        status = "NOT_READY"
        reasons.append("ARTIFACT_TERMINAL_REQUIRED")
    elif not final_receipt["human_accepted"]:
        status = "READY_FOR_REVIEW"
        reasons.append("HUMAN_ACCEPTANCE_REQUIRED")
    else:
        status = "ACCEPTED"
    return {
        "status": status,
        "accepted": status == "ACCEPTED",
        "reasons": reasons,
    }


def validate_research_report_acceptance(
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Validate a contract and return its derived human-review status.

    The returned status is derived from the source/evidence rows and final
    receipt.  A caller must persist or display an explicit human acceptance;
    this function never mutates the payload or accepts a report.
    """

    if not isinstance(contract, dict):
        raise ResearchReportAcceptanceError("research report acceptance must be an object")
    _validate_structure(contract)
    return _review(contract)


def build_research_report_acceptance(
    *,
    synthetic_only: bool,
    brief: dict[str, Any],
    source_manifest: list[dict[str, Any]],
    evidence_matrix: list[dict[str, Any]],
    outline: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
    visual: list[dict[str, Any]],
    final_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Build a normalized public contract from seven report-stage blocks."""

    contract = {
        "schema_version": SCHEMA_VERSION,
        "synthetic_only": synthetic_only,
        "brief": deepcopy(brief),
        "source_manifest": deepcopy(source_manifest),
        "evidence_matrix": deepcopy(evidence_matrix),
        "outline": deepcopy(outline),
        "chapters": deepcopy(chapters),
        "visual": deepcopy(visual),
        "final_receipt": deepcopy(final_receipt),
    }
    review = validate_research_report_acceptance(contract)
    contract["review"] = review
    return contract


def synthetic_research_report_fixture() -> dict[str, Any]:
    """Return a stable fixture containing no real source or task material."""

    return build_research_report_acceptance(
        synthetic_only=True,
        brief={
            "brief_id": "brief-example",
            "question": "Example question for a bounded report",
            "scope": "Example scope with synthetic records only",
        },
        source_manifest=[
            {"source_id": "source-a", "kind": "synthetic", "status": "KNOWN"},
            {"source_id": "source-b", "kind": "synthetic", "status": "UNKNOWN"},
            {"source_id": "source-c", "kind": "synthetic", "status": "CONFLICT"},
        ],
        evidence_matrix=[
            {
                "evidence_id": "evidence-example",
                "claim_ref": "claim-example",
                "source_ids": ["source-a"],
                "status": "SUPPORTED",
            }
        ],
        outline=[
            {
                "section_id": "section-example",
                "title": "Example section",
            }
        ],
        chapters=[
            {
                "chapter_id": "chapter-example",
                "outline_id": "section-example",
                "status": "DRAFT",
            }
        ],
        visual=[
            {
                "visual_id": "visual-example",
                "kind": "synthetic-figure",
                "status": "DRAFT",
            }
        ],
        final_receipt={
            "artifact_terminal": True,
            "human_accepted": False,
            "receipt_ref": "receipt-example",
        },
    )
