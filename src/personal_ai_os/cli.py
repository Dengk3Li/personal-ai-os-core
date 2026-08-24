from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .dispatching import assign_task, select_execution_route
from .freeze import freeze_assets, verify_freeze
from .git_closure import evaluate_git_closure
from .planning import project_plan, ready_tasks, validate_plan
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
    plan_candidate = validate_plan(
        "Produce a source-grounded research review",
        [
            {
                "task_id": "scope",
                "title": "Confirm scope",
                "acceptance": "One bounded question is accepted",
                "depends_on": [],
                "parent_id": None,
                "human_gate": True,
                "complexity": "standard",
                "required_capabilities": ["research"],
                "estimated_context_tokens": 24000,
            },
            {
                "task_id": "draft",
                "title": "Draft review",
                "acceptance": "Draft follows the accepted scope",
                "depends_on": ["scope"],
                "parent_id": "scope",
                "human_gate": False,
            },
        ],
        plan_id="plan:demo",
    )
    plan = promote_candidate(
        plan_candidate,
        {
            "kind": "human_final_decision",
            "candidate_id": "plan:demo",
            "approved": True,
        },
    )
    states = {"scope": "QUEUED", "draft": "QUEUED"}
    ready = ready_tasks(plan, states, {"scope": "APPROVED"})
    execution_route = select_execution_route(
        ready[0],
        [
            {
                "route": "quick",
                "tier": "quick",
                "available": True,
                "capabilities": ["writing"],
                "max_context_tokens": 64000,
            },
            {
                "route": "standard",
                "tier": "standard",
                "available": True,
                "capabilities": ["writing", "research"],
                "max_context_tokens": 160000,
            },
        ],
    )
    assignment = assign_task(
        ready[0],
        execution_route,
        [
            {
                "executor": "worker:research",
                "capabilities": ["research", "writing"],
                "supported_routes": ["standard"],
                "active_tasks": 0,
                "capacity": 1,
            }
        ],
    )
    workbench = project_plan(
        plan,
        states,
        {"scope": assignment},
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
        and plan_candidate["validation_status"] == "READY_FOR_HUMAN_REVIEW"
        and len(ready) == 1
        and execution_route["status"] == "RESOLVED"
        and assignment["status"] == "ASSIGNED"
        and workbench["progress"]["total"] == 2
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
            "dynamic_route",
            "git_closure",
            "long_task_plan",
            "task_assignment",
            "truth_compile",
            "workbench_projection",
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
