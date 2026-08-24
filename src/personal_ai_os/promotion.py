from __future__ import annotations

from typing import Any


def promote_candidate(candidate: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("status") != "CANDIDATE":
        return {"status": "BLOCKED", "reason": "CANDIDATE_STATUS_REQUIRED"}
    if not candidate.get("evidence_refs"):
        return {"status": "BLOCKED", "reason": "EVIDENCE_REQUIRED"}
    if (
        decision.get("kind") != "human_final_decision"
        or decision.get("approved") is not True
        or decision.get("candidate_id") != candidate.get("candidate_id")
    ):
        return {"status": "BLOCKED", "reason": "HUMAN_DECISION_REQUIRED"}

    return {
        **candidate,
        "status": "ACCEPTED",
        "authority": "human_final_decision",
    }
