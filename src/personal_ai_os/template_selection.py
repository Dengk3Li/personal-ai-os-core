"""Privacy-safe selection metadata for adapter-owned templates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


TEMPLATE_SELECTION_VERSION = "personal-ai-os.template-selection/v1"

_FIELDS = frozenset(
    {
        "schema_version",
        "template_id",
        "version",
        "source_ref",
        "content_sha256",
        "task_kind",
    }
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an opaque identifier")
    normalized = value.strip()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field} must be an opaque identifier")
    return normalized


def validate_template_selection(payload: dict[str, Any]) -> dict[str, str]:
    """Validate and normalize a ``TemplateSelection/v1`` record.

    A selection is only a binding reference. It never reads or carries the
    template body, a local path, credentials, or other adapter metadata.
    """

    if not isinstance(payload, dict):
        raise ValueError("template selection must be an object")
    if not set(payload).issubset(_FIELDS):
        raise ValueError("template selection contains unsupported fields")
    if payload.get("schema_version") != TEMPLATE_SELECTION_VERSION:
        raise ValueError("unsupported template selection schema")

    content_sha256 = payload.get("content_sha256")
    if not isinstance(content_sha256, str) or not _SHA256.fullmatch(content_sha256.strip()):
        raise ValueError("content_sha256 must be a SHA-256 digest")
    return {
        "schema_version": TEMPLATE_SELECTION_VERSION,
        "template_id": _identifier(payload.get("template_id"), "template_id"),
        "version": _identifier(payload.get("version"), "template version"),
        "source_ref": _identifier(payload.get("source_ref"), "source_ref"),
        "content_sha256": content_sha256.strip().lower(),
        "task_kind": _identifier(payload.get("task_kind"), "task kind"),
    }


def resolve_task_template_selection(task: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve an optional task-declared template binding without side effects.

    ``context.template_selection`` is an opt-in requirement.  A missing key
    keeps the historical task shape compatible; once the key is present, the
    selection must be a valid ``TemplateSelection/v1`` record.  The result is
    deliberately limited to a stable status, reason code, and normalized
    metadata so rejected values never cross the runtime boundary.
    """

    if not isinstance(task, Mapping):
        return {"status": "BLOCKED", "reason": "TEMPLATE_SELECTION_INVALID"}
    context = task.get("context") or {}
    if not isinstance(context, Mapping) or "template_selection" not in context:
        return {"status": "NOT_REQUIRED"}
    selection = context.get("template_selection")
    if selection is None:
        return {"status": "BLOCKED", "reason": "TEMPLATE_SELECTION_REQUIRED"}
    try:
        normalized = validate_template_selection(selection)
    except (TypeError, ValueError):
        return {"status": "BLOCKED", "reason": "TEMPLATE_SELECTION_INVALID"}
    return {"status": "RESOLVED", "template_selection": normalized}
