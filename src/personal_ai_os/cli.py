from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .dispatching import assign_task, select_execution_route
from .freeze import freeze_assets, verify_freeze
from .git_closure import evaluate_git_closure
from .intake import build_candidate_plan, inspect_workspace
from .modules import build_module_graph, discover_module_manifests, module_catalog
from .operations import operation_spec
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("demo", help="run the synthetic safety demo")
    modules_parser = subparsers.add_parser(
        "modules", help="print the composable module graph"
    )
    modules_parser.add_argument(
        "--directory", help="discover direct-child module.json manifests"
    )
    subparsers.add_parser("spec", help="print the operating protocol and task states")
    inspect_parser = subparsers.add_parser(
        "inspect", help="inspect a local workspace without writing to it"
    )
    inspect_parser.add_argument("path")
    plan_parser = subparsers.add_parser(
        "plan", help="propose a work map from a read-only workspace inspection"
    )
    plan_parser.add_argument("path")
    args = parser.parse_args(argv)
    if args.command == "demo":
        payload = demo_payload()
    elif args.command == "modules":
        discovered = (
            discover_module_manifests(args.directory)
            if args.directory
            else {"modules": [], "rejected": []}
        )
        payload = build_module_graph(module_catalog() + discovered["modules"])
        payload["manifest_rejections"] = discovered["rejected"]
    elif args.command == "spec":
        payload = operation_spec()
    elif args.command == "inspect":
        payload = inspect_workspace(args.path)
    else:
        payload = build_candidate_plan(inspect_workspace(args.path))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("status") not in {"UNKNOWN", "BLOCKED"} else 2
