from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .freeze import freeze_assets, verify_freeze
from .git_closure import evaluate_git_closure
from .promotion import promote_candidate
from .routing import route_task
from .truth import compile_truth
from .workflow import transition_task


def demo_payload() -> dict[str, object]:
    truth = compile_truth(
        {
            "required_claims": [{"subject": "project:demo", "field": "status"}],
            "sources": [
                {
                    "id": "demo-receipt",
                    "kind": "acceptance_receipt",
                    "accepted": True,
                    "claims": [
                        {"subject": "project:demo", "field": "status", "value": "ACTIVE"}
                    ],
                }
            ],
        }
    )
    route = route_task(
        {"domain": "engineering", "inputs": ["source"], "outputs": ["candidate"]},
        [
            {
                "domain": "engineering",
                "executor": "local-agent",
                "allowed_inputs": ["source"],
                "allowed_outputs": ["candidate"],
            }
        ],
    )
    promotion = promote_candidate(
        {"candidate_id": "demo", "status": "CANDIDATE", "evidence_refs": ["demo"]},
        {"kind": "human_final_decision", "candidate_id": "demo", "approved": True},
    )
    closure = evaluate_git_closure(
        {
            "result_kind": "no_git_change",
            "attested_by": "owner:synthetic",
            "dirty_paths": [],
        }
    )
    transition = transition_task(
        {
            "task_id": "demo",
            "status": "IN_PROGRESS",
            "git_closure": closure,
        },
        "REVIEW",
        by="agent:synthetic",
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "asset.txt").write_text("synthetic\n", encoding="utf-8")
        freeze = freeze_assets(root, ["asset.txt"])
        freeze_status = verify_freeze(root, freeze)["status"]

    safe = (
        truth["safe"]
        and route["status"] == "RESOLVED"
        and promotion["status"] == "ACCEPTED"
        and closure["done_ready"]
        and transition["ok"]
        and freeze_status == "PASS"
    )
    return {
        "status": "SAFE" if safe else "BLOCKED",
        "data_source": "synthetic",
        "checks": [
            "asset_freeze",
            "candidate_promotion",
            "domain_route",
            "git_closure",
            "truth_compile",
            "workflow_transition",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="personal-ai-os")
    parser.add_argument("command", choices=("demo",))
    args = parser.parse_args(argv)
    if args.command == "demo":
        print(json.dumps(demo_payload(), ensure_ascii=False, sort_keys=True))
    return 0
