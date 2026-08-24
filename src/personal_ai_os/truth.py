from __future__ import annotations

import json
from collections import defaultdict
from typing import Any


AUTHORITY_RANK = {
    "verified_evidence": 100,
    "accepted_manifest": 200,
    "acceptance_receipt": 300,
    "human_final_decision": 400,
}
VIEW_KINDS = {"graph_snapshot", "registry", "status_view"}


def _value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compile_truth(manifest: dict[str, Any]) -> dict[str, Any]:
    """Select current facts from accepted authority sources.

    Views remain projections. Missing evidence and equal-authority conflicts resolve
    to ``UNKNOWN`` so callers cannot turn an ambiguous snapshot into authority.
    """

    candidates: dict[tuple[str, str], list[tuple[int, dict[str, Any], dict[str, Any]]]]
    candidates = defaultdict(list)
    for source in manifest.get("sources", []):
        kind = source.get("kind")
        if not source.get("accepted") or kind in VIEW_KINDS or kind not in AUTHORITY_RANK:
            continue
        for claim in source.get("claims", []):
            subject = claim.get("subject")
            field = claim.get("field")
            if subject and field:
                candidates[(str(subject), str(field))].append(
                    (AUTHORITY_RANK[kind], source, claim)
                )

    required = {
        (str(item["subject"]), str(item["field"]))
        for item in manifest.get("required_claims", [])
        if item.get("subject") and item.get("field")
    }
    required.update(candidates)
    truth: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    findings: list[dict[str, Any]] = []
    for subject, field in sorted(required):
        options = candidates.get((subject, field), [])
        if not options:
            selected = {"value": "UNKNOWN", "authority": "NONE", "source_ids": []}
            findings.append({"code": "MISSING_EVIDENCE", "subject": subject, "field": field})
        else:
            highest = max(rank for rank, _, _ in options)
            top = [(source, claim) for rank, source, claim in options if rank == highest]
            values = {_value_key(claim.get("value")) for _, claim in top}
            if len(values) != 1:
                selected = {
                    "value": "UNKNOWN",
                    "authority": "CONFLICT",
                    "source_ids": sorted(str(source["id"]) for source, _ in top),
                }
                findings.append(
                    {"code": "AUTHORITY_CONFLICT", "subject": subject, "field": field}
                )
            else:
                selected = {
                    "value": top[0][1].get("value"),
                    "authority": str(top[0][0]["kind"]),
                    "source_ids": sorted(str(source["id"]) for source, _ in top),
                }
        truth[subject][field] = selected

    return {
        "safe": not findings,
        "truth": {subject: fields for subject, fields in truth.items()},
        "findings": findings,
    }
