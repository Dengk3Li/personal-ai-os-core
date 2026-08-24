from __future__ import annotations

from typing import Any


def route_task(task: dict[str, Any], routes: list[dict[str, Any]]) -> dict[str, str]:
    domain = str(task.get("domain", ""))
    matches = [route for route in routes if route.get("domain") == domain]
    if len(matches) != 1:
        return {"status": "UNKNOWN", "reason": "ROUTE_NOT_FOUND"}

    route = matches[0]
    requested_inputs = {str(item) for item in task.get("inputs", [])}
    allowed_inputs = {str(item) for item in route.get("allowed_inputs", [])}
    if not requested_inputs.issubset(allowed_inputs):
        return {"status": "BLOCKED", "reason": "INPUT_SCOPE_VIOLATION"}

    requested_outputs = {str(item) for item in task.get("outputs", [])}
    allowed_outputs = {str(item) for item in route.get("allowed_outputs", [])}
    if not requested_outputs.issubset(allowed_outputs):
        return {"status": "BLOCKED", "reason": "OUTPUT_SCOPE_VIOLATION"}

    return {
        "status": "RESOLVED",
        "domain": domain,
        "executor": str(route.get("executor", "")),
    }
