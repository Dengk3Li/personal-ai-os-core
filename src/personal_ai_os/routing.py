from __future__ import annotations

from typing import Any


DOMAIN_CONTEXT_LAYERS = (
    "domain_contract",
    "active_project",
    "current_state",
    "relevant_knowledge",
    "historical_decisions",
    "constraints",
    "excluded_context",
)


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


def compile_domain_context(
    domain_id: str,
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compile one references-only domain manifest in a fixed minimal order."""
    selected = [item for item in profiles if str(item.get("domain_id") or "") == domain_id]
    if not selected:
        return {"status": "UNKNOWN", "reason": "DOMAIN_NOT_FOUND"}
    if len(selected) > 1:
        return {"status": "UNKNOWN", "reason": "DOMAIN_AMBIGUOUS"}
    profile = selected[0]
    layers = profile.get("context_layers") or {}
    if not isinstance(layers, dict):
        return {"status": "BLOCKED", "reason": "CONTEXT_LAYERS_INVALID"}
    unknown = set(layers) - set(DOMAIN_CONTEXT_LAYERS)
    if unknown:
        return {
            "status": "BLOCKED",
            "reason": "CONTEXT_LAYER_NOT_ALLOWED",
            "layer": sorted(unknown)[0],
        }
    load_order = []
    for kind in DOMAIN_CONTEXT_LAYERS:
        if kind not in layers:
            continue
        refs = layers[kind]
        if (
            not isinstance(refs, list)
            or len(refs) > 32
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
        ):
            return {
                "status": "BLOCKED",
                "reason": "CONTEXT_REFERENCES_INVALID",
                "layer": kind,
            }
        load_order.append({"kind": kind, "refs": list(refs)})
    tools = profile.get("allowed_tools") or []
    if not isinstance(tools, list) or any(not isinstance(item, str) for item in tools):
        return {"status": "BLOCKED", "reason": "ALLOWED_TOOLS_INVALID"}
    return {
        "schema_version": "personal-ai-os.domain-context/v1",
        "status": "RESOLVED",
        "domain_id": domain_id,
        "persona": str(profile.get("persona") or "direct"),
        "load_order": load_order,
        "allowed_tools": list(tools),
    }
