"""Side-effect-free input gate for a source-grounded research task.

The gate is intentionally smaller than report acceptance.  It checks only the
inputs needed to start a research line and returns a public-safe status.  It
does not create a task, touch ``RuntimeStore``, invoke an adapter, or echo the
submitted values.  Keeping the gate pure lets the CLI and loopback API share
the same contract without coupling intake to execution.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "personal-ai-os.research-input-gate/v1"
READY_FOR_INPUT_STATUS = "READY_FOR_INPUT"
REPORT_INPUT_REQUIRED_STATUS = "REPORT_INPUT_REQUIRED"
REPORT_INPUT_INVALID_STATUS = "REPORT_INPUT_INVALID"
REQUIRED_RESEARCH_TASK_INPUTS = (
    "research_question",
    "scope",
    "audience",
    "format",
    "source_policy",
)

_PLACEHOLDER_VALUES = frozenset(
    {
        "todo",
        "tbd",
        "tba",
        "placeholder",
        "pending",
        "占位",
        "未定",
        "待定",
        "待填写",
        "待补充",
        "source-pending",
        "evidence-pending",
        "artifact-pending",
    }
)


class ResearchInputGateValidationError(ValueError):
    """Raised when a research input set cannot enter the input gate."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        missing_inputs: list[dict[str, str]] | None = None,
        invalid_inputs: list[dict[str, str]] | None = None,
    ):
        self.code = code
        self.missing_inputs = deepcopy(missing_inputs or [])
        self.invalid_inputs = deepcopy(invalid_inputs or [])
        super().__init__(message or code)


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().casefold()
    return normalized in _PLACEHOLDER_VALUES or normalized.startswith(("待填写", "待补充"))


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or _is_placeholder(value)
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        return not value
    return False


def validate_research_task_inputs(
    *,
    research_question: Any = None,
    scope: Any = None,
    audience: Any = None,
    format: Any = None,
    source_policy: Any = None,
) -> dict[str, Any]:
    """Validate the five explicit inputs without creating runtime state.

    The returned mapping is intended for trusted local callers.  HTTP and CLI
    preview boundaries deliberately discard it and return status only, so a
    private path nested in caller input cannot be reflected to a browser.
    """

    values = {
        "research_question": research_question,
        "scope": scope,
        "audience": audience,
        "format": format,
        "source_policy": source_policy,
    }
    missing: list[dict[str, str]] = []
    for key in REQUIRED_RESEARCH_TASK_INPUTS:
        value = values[key]
        if _is_missing(value):
            missing.append(
                {
                    "path": f"research_task.{key}",
                    "reason": "PLACEHOLDER" if _is_placeholder(value) else "REQUIRED",
                }
            )
    if missing:
        raise ResearchInputGateValidationError(
            REPORT_INPUT_REQUIRED_STATUS,
            "research task inputs are required",
            missing_inputs=missing,
        )
    return deepcopy(values)


def preview_research_input(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a public-safe readiness result for a research task input set.

    This function is pure: no task/report is created, no model is called and
    no submitted value is included in its result.
    """

    if not isinstance(payload, Mapping):
        return {
            "status": REPORT_INPUT_INVALID_STATUS,
            "invalid_inputs": [{"path": "request", "reason": "OBJECT_REQUIRED"}],
            "missing_inputs": [],
        }

    unknown = sorted(set(payload) - set(REQUIRED_RESEARCH_TASK_INPUTS))
    if unknown:
        return {
            "status": REPORT_INPUT_INVALID_STATUS,
            # Do not echo arbitrary field names: callers may use a local path
            # as an accidental key, and this boundary must remain public-safe.
            "invalid_inputs": [{"path": "research_task", "reason": "UNSUPPORTED_FIELD"}],
            "missing_inputs": [],
        }

    try:
        validate_research_task_inputs(
            **{
                key: payload.get(key)
                for key in REQUIRED_RESEARCH_TASK_INPUTS
            }
        )
    except ResearchInputGateValidationError as exc:
        return {
            "status": REPORT_INPUT_REQUIRED_STATUS,
            "missing_inputs": deepcopy(exc.missing_inputs),
            "invalid_inputs": [],
        }
    return {"status": READY_FOR_INPUT_STATUS, "missing_inputs": []}


def preview_research_task_inputs(**inputs: Any) -> dict[str, Any]:
    """Compatibility-shaped keyword wrapper for local callers."""

    return preview_research_input(inputs)
