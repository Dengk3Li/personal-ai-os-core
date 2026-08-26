"""Small, privacy-safe contracts for passing runtime tasks between adapters.

The envelope deliberately carries opaque identifiers rather than cards, files,
business prose, or local paths. Private adapters can map their own records into
this shape before handing them to the public core.
"""

from __future__ import annotations

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
