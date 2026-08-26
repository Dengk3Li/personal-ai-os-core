"""Privacy-safe execution binding and receipt contract."""

from __future__ import annotations

import datetime
import re
from typing import Any


EXECUTION_RECEIPT_VERSION = "personal-ai-os.execution-receipt/v1"

_FIELDS = frozenset({"schema_version", "task_ref", "run_ref", "binding", "receipt"})
_BINDING_FIELDS = frozenset({"project_id", "thread_id", "host_id", "verified"})
_RECEIPT_FIELDS = frozenset(
    {
        "receipt_id",
        "status",
        "outcome",
        "verified",
        "needs_user_input",
        "human_gate",
        "final_output_ref",
        "artifact_refs",
        "observed_at",
    }
)
_STATUSES = frozenset({"RUNNING", "COMPLETED", "FAILED", "BLOCKED", "AWAITING_INPUT"})
_OUTCOMES = frozenset({"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED", "UNKNOWN"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


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


def _flag(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _observed_at(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("observed_at must be an ISO-8601 timestamp")
    normalized = value.strip()
    try:
        datetime.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    return normalized


def _artifact_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("artifact_refs must be a bounded list")
    normalized = [_identifier(item, "artifact reference") for item in value]
    if len(set(normalized)) != len(normalized):
        raise ValueError("artifact_refs must be unique")
    return normalized


def _validate_binding(value: Any) -> dict[str, Any]:
    binding = _mapping(value, "execution binding")
    _supported_fields(binding, _BINDING_FIELDS, "execution binding")
    if binding.get("verified") is not True:
        raise ValueError("execution binding must be verified")
    return {
        "project_id": _identifier(binding.get("project_id"), "project_id"),
        "thread_id": _identifier(binding.get("thread_id"), "thread_id"),
        "host_id": _identifier(binding.get("host_id"), "host_id"),
        "verified": True,
    }


def _validate_receipt(value: Any) -> dict[str, Any]:
    receipt = _mapping(value, "execution receipt")
    _supported_fields(receipt, _RECEIPT_FIELDS, "execution receipt")
    status = receipt.get("status")
    if not isinstance(status, str) or status.upper().strip() not in _STATUSES:
        raise ValueError("execution receipt has an unsupported status")
    status = status.upper().strip()
    outcome = receipt.get("outcome")
    if not isinstance(outcome, str) or outcome.upper().strip() not in _OUTCOMES:
        raise ValueError("execution receipt has an unsupported outcome")
    outcome = outcome.upper().strip()
    verified = _flag(receipt.get("verified"), "receipt verified")
    needs_user_input = _flag(receipt.get("needs_user_input"), "needs_user_input")
    human_gate = _flag(receipt.get("human_gate"), "human_gate")
    artifact_refs = _artifact_refs(receipt.get("artifact_refs"))
    final_output_ref = receipt.get("final_output_ref")
    if final_output_ref is not None:
        final_output_ref = _identifier(final_output_ref, "final output reference")
    if status == "COMPLETED":
        if not verified:
            raise ValueError("completed execution receipt must be verified")
        if needs_user_input or human_gate:
            raise ValueError("completed execution receipt cannot await input or a human gate")
        if outcome != "SUCCEEDED":
            raise ValueError("completed execution receipt must have a succeeded outcome")
        if final_output_ref is None:
            raise ValueError("completed execution receipt requires a final output reference")
    elif final_output_ref is not None:
        raise ValueError("final output reference is only valid for completed receipts")
    if status == "AWAITING_INPUT" and not needs_user_input:
        raise ValueError("awaiting-input receipt must request user input")
    if status != "AWAITING_INPUT" and needs_user_input:
        raise ValueError("only awaiting-input receipts may request user input")

    result: dict[str, Any] = {
        "receipt_id": _identifier(receipt.get("receipt_id"), "receipt_id"),
        "status": status,
        "outcome": outcome,
        "verified": verified,
        "needs_user_input": needs_user_input,
        "human_gate": human_gate,
        "artifact_refs": artifact_refs,
        "observed_at": _observed_at(receipt.get("observed_at")),
    }
    if final_output_ref is not None:
        result["final_output_ref"] = final_output_ref
    return result


def validate_execution_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a references-only ``ExecutionReceipt/v1`` record.

    The contract proves which project-owned execution produced a bounded
    receipt. It carries no local path, task body, model output, business label,
    or credential, and validation never writes runtime state.
    """

    record = _mapping(payload, "execution receipt record")
    _supported_fields(record, _FIELDS, "execution receipt record")
    if record.get("schema_version") != EXECUTION_RECEIPT_VERSION:
        raise ValueError("unsupported execution receipt schema")
    return {
        "schema_version": EXECUTION_RECEIPT_VERSION,
        "task_ref": _identifier(record.get("task_ref"), "task reference"),
        "run_ref": _identifier(record.get("run_ref"), "run reference"),
        "binding": _validate_binding(record.get("binding")),
        "receipt": _validate_receipt(record.get("receipt")),
    }
