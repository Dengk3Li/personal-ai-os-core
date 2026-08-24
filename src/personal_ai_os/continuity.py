from __future__ import annotations

import hashlib
import json
from typing import Any


RECOVERY_FIELDS = ("authority", "current_state", "next_action")


def build_capsule(state: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in RECOVERY_FIELDS if field not in state]
    if missing:
        raise ValueError(f"missing recovery fields: {', '.join(missing)}")
    payload = {field: state[field] for field in RECOVERY_FIELDS}
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return {
        "schema_version": "personal-ai-os.continuity.v1",
        "payload": payload,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
    }
