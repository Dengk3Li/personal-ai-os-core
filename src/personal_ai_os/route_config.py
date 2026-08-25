from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dispatching import TIER_RANK


RUNTIME_ROUTES_SCHEMA = "personal-ai-os.runtime-routes/v1"
CATALOG_FIELDS = {"schema_version", "routes"}
ROUTE_FIELDS = {
    "route",
    "tier",
    "capabilities",
    "max_context_tokens",
    "adapter_id",
    "model",
    "enabled",
}


def load_runtime_routes(path: str | Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime route catalog must be a JSON object")
    unknown = set(value) - CATALOG_FIELDS
    if unknown:
        raise ValueError(f"runtime route catalog field not allowed: {sorted(unknown)[0]}")
    if value.get("schema_version") != RUNTIME_ROUTES_SCHEMA:
        raise ValueError("unsupported runtime route schema")
    routes = value.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("runtime routes must be a non-empty list")
    normalized = []
    route_ids = set()
    for route in routes:
        if not isinstance(route, dict):
            raise ValueError("runtime route must be a JSON object")
        unknown = set(route) - ROUTE_FIELDS
        if unknown:
            raise ValueError(f"runtime route field not allowed: {sorted(unknown)[0]}")
        route_id = str(route.get("route") or "").strip()
        if not route_id:
            raise ValueError("runtime route id is required")
        if route_id in route_ids:
            raise ValueError(f"duplicate runtime route: {route_id}")
        adapter_id = str(route.get("adapter_id") or "").strip()
        if not adapter_id:
            raise ValueError(f"runtime route adapter_id is required: {route_id}")
        model = str(route.get("model") or "").strip()
        if not model:
            raise ValueError(f"runtime route model is required: {route_id}")
        tier = str(route.get("tier") or "").strip()
        if tier not in TIER_RANK:
            raise ValueError(f"runtime route tier is invalid: {route_id}")
        capabilities = route.get("capabilities")
        if (
            not isinstance(capabilities, list)
            or any(not isinstance(item, str) or not item.strip() for item in capabilities)
        ):
            raise ValueError(f"runtime route capabilities are invalid: {route_id}")
        context_limit = route.get("max_context_tokens")
        if type(context_limit) is not int or context_limit <= 0:
            raise ValueError(f"runtime route context limit is invalid: {route_id}")
        enabled = route.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"runtime route enabled flag is invalid: {route_id}")
        route_ids.add(route_id)
        normalized.append(
            {
                "route": route_id,
                "tier": tier,
                "capabilities": [item.strip() for item in capabilities],
                "max_context_tokens": context_limit,
                "adapter_id": adapter_id,
                "model": model,
                "enabled": enabled,
            }
        )
    return normalized
