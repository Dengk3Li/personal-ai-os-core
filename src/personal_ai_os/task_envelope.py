"""Small, privacy-safe contracts for passing runtime tasks between adapters.

The envelope deliberately carries opaque identifiers rather than cards, files,
business prose, or local paths. Private adapters can map their own records into
this shape before handing them to the public core.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .task_links import (
    TASK_MODULE_LINK_VERSION,
    TASK_MODULE_RELATIONS,
    TASK_MODULE_SOURCES,
    TASK_MODULE_STATUSES,
    validate_task_module_link,
)


TASK_ENVELOPE_VERSION = "personal-ai-os.task-envelope/v1"
TASK_ENVELOPE_PREVIEW_VERSION = "personal-ai-os.task-envelope-preview/v1"

_ENVELOPE_FIELDS = frozenset(
    {"schema_version", "origin", "runtime_task", "extensions", "module_refs"}
)
_ORIGIN_FIELDS = frozenset({"source_kind", "source_ref", "revision"})
_RUNTIME_FIELDS = frozenset(
    {"task_id", "workflow_id", "status", "attempt", "depends_on", "result_ref"}
)
_LINK_FIELDS = frozenset(
    {"schema_version", "module_id", "relation", "source", "confidence", "status"}
)
_RUNTIME_STATES = frozenset(
    {"QUEUED", "IN_PROGRESS", "REVIEW", "BLOCKED", "PAUSED", "DONE", "ARCHIVED"}
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EXTENSION_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,47}$")
_EXTENSION_STRING = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_PREVIEW_ITEM_FIELDS = frozenset({"envelope", "goal", "next_action"})


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _supported_fields(value: dict[str, Any], allowed: frozenset[str], field: str) -> None:
    if not set(value).issubset(allowed):
        raise ValueError(f"{field} contains unsupported fields")


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an opaque identifier")
    normalized = value.strip()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field} must be an opaque identifier")
    return normalized


def _positive_int(value: Any, field: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _extension_value(value: Any, field: str, *, depth: int = 0) -> Any:
    if depth > 3:
        raise ValueError(f"{field} is too deeply nested")
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field} must be finite")
        return value
    if isinstance(value, str):
        if not _EXTENSION_STRING.fullmatch(value):
            raise ValueError(f"{field} must be a scalar extension value")
        return value
    if isinstance(value, list):
        if len(value) > 16:
            raise ValueError(f"{field} has too many values")
        return [
            _extension_value(item, field, depth=depth + 1)
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > 16:
            raise ValueError(f"{field} has too many fields")
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not _EXTENSION_KEY.fullmatch(key):
                raise ValueError(f"{field} contains an invalid key")
            normalized[key] = _extension_value(item, field, depth=depth + 1)
        return normalized
    raise ValueError(f"{field} must contain JSON-compatible scalar data")


def validate_task_module_link_v1(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one typed module reference without accepting private metadata."""

    link = _mapping(payload, "module link")
    _supported_fields(link, _LINK_FIELDS, "module link")
    if "schema_version" in link and link["schema_version"] != TASK_MODULE_LINK_VERSION:
        raise ValueError("unsupported module link schema")
    module_id = _identifier(link.get("module_id"), "module_id")
    normalized = validate_task_module_link({**link, "module_id": module_id})
    # Keep this wrapper explicit so additions to the legacy link validator do
    # not silently widen the public envelope contract.
    if normalized["relation"] not in TASK_MODULE_RELATIONS:
        raise ValueError("unsupported task module relation")
    if normalized["source"] not in TASK_MODULE_SOURCES:
        raise ValueError("unsupported task module source")
    if normalized["status"] not in TASK_MODULE_STATUSES:
        raise ValueError("unsupported task module status")
    return normalized


def _validate_origin(payload: Any) -> dict[str, Any]:
    origin = _mapping(payload, "origin")
    _supported_fields(origin, _ORIGIN_FIELDS, "origin")
    normalized = {
        "source_kind": _identifier(origin.get("source_kind"), "origin source kind"),
        "source_ref": _identifier(origin.get("source_ref"), "origin source ref"),
        "revision": _positive_int(origin.get("revision", 1), "origin revision", allow_zero=True),
    }
    return normalized


def _validate_runtime_task(payload: Any) -> dict[str, Any]:
    runtime_task = _mapping(payload, "runtime task")
    _supported_fields(runtime_task, _RUNTIME_FIELDS, "runtime task")
    status = runtime_task.get("status")
    if not isinstance(status, str) or status.upper().strip() not in _RUNTIME_STATES:
        raise ValueError("runtime task has an unsupported status")
    normalized: dict[str, Any] = {
        "task_id": _identifier(runtime_task.get("task_id"), "runtime task id"),
        "status": status.upper().strip(),
        "attempt": _positive_int(runtime_task.get("attempt", 1), "runtime task attempt"),
    }
    if "workflow_id" in runtime_task:
        normalized["workflow_id"] = _identifier(runtime_task["workflow_id"], "workflow id")
    depends_on = runtime_task.get("depends_on", [])
    if not isinstance(depends_on, list) or len(depends_on) > 32:
        raise ValueError("runtime task dependencies must be a bounded list")
    normalized_dependencies = [
        _identifier(item, "runtime task dependency") for item in depends_on
    ]
    if len(set(normalized_dependencies)) != len(normalized_dependencies):
        raise ValueError("runtime task dependencies must be unique")
    normalized["depends_on"] = normalized_dependencies
    if "result_ref" in runtime_task:
        normalized["result_ref"] = _identifier(runtime_task["result_ref"], "result ref")
    return normalized


def validate_task_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized, bounded TaskEnvelope/v1 or raise ``ValueError``.

    This is intentionally a pure boundary check: it does not read files,
    private task cards, local paths, or invoke a model.
    """

    envelope = _mapping(payload, "task envelope")
    _supported_fields(envelope, _ENVELOPE_FIELDS, "task envelope")
    if envelope.get("schema_version") != TASK_ENVELOPE_VERSION:
        raise ValueError("unsupported task envelope schema")
    extensions = envelope.get("extensions", {})
    extensions = _mapping(extensions, "extensions")
    normalized_extensions = _extension_value(extensions, "extensions")
    module_refs = envelope.get("module_refs", [])
    if not isinstance(module_refs, list) or len(module_refs) > 32:
        raise ValueError("module references must be a bounded list")
    normalized_links = [validate_task_module_link_v1(link) for link in module_refs]
    seen_refs: set[tuple[str, str]] = set()
    for link in normalized_links:
        ref_key = (link["module_id"], link["relation"])
        if ref_key in seen_refs:
            raise ValueError("duplicate module reference")
        seen_refs.add(ref_key)
    return {
        "schema_version": TASK_ENVELOPE_VERSION,
        "origin": _validate_origin(envelope.get("origin")),
        "runtime_task": _validate_runtime_task(envelope.get("runtime_task")),
        "extensions": normalized_extensions,
        "module_refs": normalized_links,
    }


def _preview_result(
    *,
    status: str,
    reason_code: str,
    next_action_code: str,
    issues: list[dict[str, Any]],
    input_count: int,
    unique_count: int,
    duplicate_count: int,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": TASK_ENVELOPE_PREVIEW_VERSION,
        "status": status,
        "reason": {"code": reason_code},
        "next_action": {"code": next_action_code},
        "issues": issues,
        "items": items or [],
        "summary": {
            "input_count": input_count,
            "unique_count": unique_count,
            "duplicate_count": duplicate_count,
        },
        "read_only": True,
        "runtime_write": False,
    }


def _preview_metadata(value: Any, field: str) -> tuple[str | None, str | None]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, f"{field.upper()}_REQUIRED"
    try:
        return _identifier(value, field), None
    except ValueError:
        return None, f"{field.upper()}_INVALID"


def preview_task_envelopes(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Dry-run a bounded batch of task envelopes without runtime side effects.

    Each item is a wrapper containing one validated envelope plus opaque
    ``goal`` and ``next_action`` references. Identical ``origin`` + task ID
    entries collapse to one item; differing entries at that key are blocked.
    """

    if not isinstance(payloads, list):
        return _preview_result(
            status="BLOCKED",
            reason_code="TASK_ENVELOPES_INVALID",
            next_action_code="PROVIDE_TASK_ENVELOPES",
            issues=[{"index": None, "code": "TASK_ENVELOPES_LIST_REQUIRED"}],
            input_count=0,
            unique_count=0,
            duplicate_count=0,
        )
    if not payloads:
        return _preview_result(
            status="BLOCKED",
            reason_code="TASK_ENVELOPES_REQUIRED",
            next_action_code="PROVIDE_TASK_ENVELOPES",
            issues=[{"index": None, "code": "TASK_ENVELOPES_REQUIRED"}],
            input_count=0,
            unique_count=0,
            duplicate_count=0,
        )
    if len(payloads) > 128:
        return _preview_result(
            status="BLOCKED",
            reason_code="TASK_ENVELOPES_TOO_LARGE",
            next_action_code="REDUCE_TASK_ENVELOPES",
            issues=[{"index": None, "code": "TASK_ENVELOPES_TOO_LARGE"}],
            input_count=len(payloads),
            unique_count=0,
            duplicate_count=0,
        )

    unique: dict[tuple[tuple[tuple[str, Any], ...], str], dict[str, Any]] = {}
    output_items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    duplicate_count = 0
    for index, item in enumerate(payloads):
        if not isinstance(item, dict) or not set(item).issubset(_PREVIEW_ITEM_FIELDS):
            issues.append({"index": index, "code": "ITEM_INVALID"})
            continue
        if "envelope" not in item:
            issues.append({"index": index, "code": "ENVELOPE_REQUIRED"})
            continue
        try:
            envelope = validate_task_envelope(item["envelope"])
        except (TypeError, ValueError):
            issues.append({"index": index, "code": "ENVELOPE_INVALID"})
            continue
        goal, goal_issue = _preview_metadata(item.get("goal"), "goal")
        next_action, next_action_issue = _preview_metadata(item.get("next_action"), "next_action")
        if goal_issue:
            issues.append({"index": index, "code": goal_issue})
        if next_action_issue:
            issues.append({"index": index, "code": next_action_issue})
        if goal_issue or next_action_issue:
            continue

        runtime_task = envelope["runtime_task"]
        origin_key = tuple(sorted(envelope["origin"].items()))
        task_key = (origin_key, runtime_task["task_id"])
        record = {
            "envelope": envelope,
            "goal": goal,
            "next_action": next_action,
        }
        existing = unique.get(task_key)
        if existing is not None:
            if json.dumps(existing, sort_keys=True, separators=(",", ":")) == json.dumps(
                record, sort_keys=True, separators=(",", ":")
            ):
                duplicate_count += 1
            else:
                issues.append({"index": index, "code": "DUPLICATE_TASK_CONFLICT"})
            continue
        unique[task_key] = record
        output_items.append(record)

    if issues:
        if any(issue["code"] == "DUPLICATE_TASK_CONFLICT" for issue in issues):
            reason_code, next_action_code = (
                "DUPLICATE_TASK_CONFLICT",
                "RECONCILE_TASK_DUPLICATES",
            )
        elif any(issue["code"].endswith("_REQUIRED") for issue in issues):
            reason_code, next_action_code = "REQUIRED_METADATA", "PROVIDE_TASK_METADATA"
        else:
            reason_code, next_action_code = "INVALID_TASK_METADATA", "FIX_TASK_METADATA"
        return _preview_result(
            status="BLOCKED",
            reason_code=reason_code,
            next_action_code=next_action_code,
            issues=issues,
            input_count=len(payloads),
            unique_count=len(unique),
            duplicate_count=duplicate_count,
        )
    return _preview_result(
        status="READY",
        reason_code="TASK_ENVELOPES_READY",
        next_action_code="DISPATCH_TASK_ENVELOPES",
        issues=[],
        input_count=len(payloads),
        unique_count=len(unique),
        duplicate_count=duplicate_count,
        items=output_items,
    )
