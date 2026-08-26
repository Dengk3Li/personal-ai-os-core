from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


RECOVERY_FIELDS = ("authority", "current_state", "next_action")
RUNTIME_CONTINUITY_SCHEMA = "personal-ai-os.continuity/v2"
MAX_RUNTIME_DEPENDENCIES = 32
MAX_RUNTIME_ARTIFACT_REFS = 32
MAX_RUNTIME_NEXT_ACTION_CHARS = 240

# Runtime continuity carries opaque identifiers, not arbitrary strings.  This
# keeps local paths, URLs, and embedded credentials out of the capsule before
# it reaches a browser projection.
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})?$"
)
_SENSITIVE = re.compile(
    r"/(?:Users|home|Volumes|private|var|tmp|opt|etc)/"
    r"|[A-Za-z]:[\\/]"
    r"|file://|~[/\\]"
    r"|(?:api[_-]?key|password|secret|token)\s*[:=]",
    re.IGNORECASE,
)


def _encoded(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _finalize(payload: dict[str, Any], schema_version: str) -> dict[str, Any]:
    encoded = _encoded(payload)
    return {
        "schema_version": schema_version,
        "payload": payload,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
    }


def build_capsule(state: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in RECOVERY_FIELDS if field not in state]
    if missing:
        raise ValueError(f"missing recovery fields: {', '.join(missing)}")
    payload = {field: state[field] for field in RECOVERY_FIELDS}
    return _finalize(payload, "personal-ai-os.continuity.v1")


def _safe_reference(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text or not _REFERENCE.fullmatch(text) or _SENSITIVE.search(text):
        raise ValueError(f"{field} must be an opaque reference")
    return text


def _safe_action(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("next_action is required")
    if len(text) > MAX_RUNTIME_NEXT_ACTION_CHARS or _SENSITIVE.search(text):
        raise ValueError("next_action contains unsafe content")
    return text


def _task_reference(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("task must be an object")
    result = {
        "task_id": _safe_reference(value.get("task_id"), field="task_id"),
        "workflow_id": _safe_reference(
            value.get("workflow_id") or value.get("line_id") or "general",
            field="workflow_id",
        ),
        "status": _safe_reference(value.get("status") or "UNKNOWN", field="status"),
    }
    return result


def _dependency_references(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("dependencies must be a list")
    if len(value) > MAX_RUNTIME_DEPENDENCIES:
        raise ValueError("dependencies exceed bounded limit")
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("dependency must be an object")
        result.append(
            {
                "task_id": _safe_reference(item.get("task_id"), field="dependency task_id"),
                "status": _safe_reference(item.get("status") or "UNKNOWN", field="dependency status"),
            }
        )
    return result


def _latest_run_reference(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("latest_run must be an object")
    result: dict[str, Any] = {
        "run_id": _safe_reference(value.get("run_id"), field="run_id"),
        "status": _safe_reference(value.get("status") or "UNKNOWN", field="run status"),
    }
    attempt = value.get("attempt")
    if attempt is not None:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or not 1 <= attempt <= 100000:
            raise ValueError("run attempt is invalid")
        result["attempt"] = attempt
    for field in ("started_at", "ended_at", "exited_at"):
        timestamp = str(value.get(field) or "").strip()
        if timestamp and _TIMESTAMP.fullmatch(timestamp):
            result[field] = timestamp
    return result


def _decision_reference(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("decision must be an object")
    return {
        "decision_id": _safe_reference(value.get("decision_id"), field="decision_id"),
        "status": _safe_reference(value.get("status") or "UNKNOWN", field="decision status"),
    }


def _artifact_references(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("artifact_refs must be a list")
    if len(value) > MAX_RUNTIME_ARTIFACT_REFS:
        raise ValueError("artifact_refs exceed bounded limit")
    result: list[str] = []
    for item in value:
        try:
            reference = _safe_reference(item, field="artifact_ref")
        except ValueError:
            # An artifact path or arbitrary body is not a valid continuity
            # reference.  Omit it rather than copying sensitive data.
            continue
        if reference not in result:
            result.append(reference)
    return result


def build_runtime_continuity_capsule(state: Mapping[str, Any]) -> dict[str, Any]:
    """Build a bounded, references-only runtime recovery capsule.

    The input may contain rich task/run records, but the returned payload keeps
    only opaque task/dependency/run/decision/artifact references and one short
    next action.  It is pure and can therefore be attached to any read-only
    runtime or memory projection without creating another persistence layer.
    """
    if not isinstance(state, Mapping):
        raise ValueError("runtime continuity state must be an object")
    payload = {
        "task": _task_reference(state.get("task")),
        "dependencies": _dependency_references(state.get("dependencies")),
        "latest_run": _latest_run_reference(state.get("latest_run")),
        "decision": _decision_reference(state.get("decision")),
        "artifact_refs": _artifact_references(state.get("artifact_refs")),
        "next_action": _safe_action(state.get("next_action")),
    }
    return _finalize(payload, RUNTIME_CONTINUITY_SCHEMA)


# Friendly public spelling for callers that do not need to distinguish the
# runtime source from the generic continuity contract.
build_continuity_capsule = build_runtime_continuity_capsule
