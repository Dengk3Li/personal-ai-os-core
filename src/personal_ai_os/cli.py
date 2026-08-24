from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from .adapters import OpenAICompatibleAdapter
from .dispatching import assign_task, select_execution_route
from .freeze import freeze_assets, verify_freeze
from .git_closure import evaluate_git_closure
from .intake import build_candidate_plan, inspect_workspace
from .modules import build_module_graph, discover_module_manifests, module_catalog
from .operations import operation_spec
from .planning import project_plan, ready_tasks, validate_plan
from .promotion import promote_candidate
from .routing import compile_domain_context, route_task
from .automation import AutoAdvanceEngine
from .runtime import ExecutionBroker, RuntimeStore, install_workflow_preset
from .runtime_plan import load_runtime_plan, sync_runtime_plan
from .secretary import build_secretary_brief
from .server import create_runtime_server
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
    context_parser = subparsers.add_parser(
        "domain-context", help="compile one references-only domain context manifest"
    )
    context_parser.add_argument("--registry", required=True)
    context_parser.add_argument("--domain", required=True)
    runtime_parser = subparsers.add_parser(
        "runtime", help="operate the persistent long-task runtime"
    )
    runtime_commands = runtime_parser.add_subparsers(dest="runtime_command", required=True)
    runtime_init = runtime_commands.add_parser("init", help="initialize a runtime store")
    runtime_init.add_argument("--store", required=True)
    runtime_init.add_argument(
        "--preset",
        choices=["science", "meeting-notes", "analytical-report"],
        default="science",
    )
    runtime_status = runtime_commands.add_parser("status", help="read runtime state")
    runtime_status.add_argument("--store", required=True)
    runtime_sync = runtime_commands.add_parser(
        "sync-plan", help="idempotently register a versioned local runtime plan"
    )
    runtime_sync.add_argument("--store", required=True)
    runtime_sync.add_argument("--plan", required=True)
    runtime_brief = runtime_commands.add_parser("brief", help="read the secretary brief")
    runtime_brief.add_argument("--store", required=True)
    runtime_run = runtime_commands.add_parser("run", help="dispatch one queued task")
    runtime_run.add_argument("--store", required=True)
    runtime_run.add_argument("--task", required=True)
    runtime_run.add_argument("--model", required=True)
    runtime_run.add_argument("--adapter", default="openai-compatible")
    runtime_advance = runtime_commands.add_parser(
        "advance", help="boundedly dispatch every currently ready task"
    )
    runtime_advance.add_argument("--store", required=True)
    runtime_advance.add_argument("--model", required=True)
    runtime_advance.add_argument("--adapter", default="openai-compatible")
    runtime_advance.add_argument("--max-steps", type=int, default=25)
    runtime_advance.add_argument("--failure-budget", type=int, default=1)
    runtime_advance.add_argument("--workflow")
    runtime_resolve = runtime_commands.add_parser("resolve", help="record a human decision")
    runtime_resolve.add_argument("--store", required=True)
    runtime_resolve.add_argument("--decision", required=True)
    runtime_resolve.add_argument("--option", required=True)
    runtime_resolve.add_argument("--by", default="owner")
    runtime_serve = runtime_commands.add_parser("serve", help="serve the workbench and runtime API")
    runtime_serve.add_argument("--store", required=True)
    runtime_serve.add_argument("--web-root", default="workbench")
    runtime_serve.add_argument("--host", default="127.0.0.1")
    runtime_serve.add_argument("--port", type=int, default=8787)
    runtime_serve.add_argument("--model", default=os.environ.get("PERSONAL_AI_OS_DEFAULT_MODEL", ""))
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
    elif args.command == "plan":
        payload = build_candidate_plan(inspect_workspace(args.path))
    elif args.command == "domain-context":
        registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        profiles = registry.get("profiles") if isinstance(registry, dict) else registry
        if not isinstance(profiles, list):
            payload = {"status": "BLOCKED", "reason": "DOMAIN_REGISTRY_INVALID"}
        else:
            payload = compile_domain_context(args.domain, profiles)
    else:
        store = RuntimeStore(args.store)
        if args.runtime_command == "init":
            installed = install_workflow_preset(store, args.preset)
            payload = {
                "status": "READY",
                "store": str(store.database),
                "workflow_id": installed["workflow_id"],
                "task_count": len(store.snapshot()["tasks"]),
            }
        elif args.runtime_command == "status":
            snapshot = store.snapshot()
            payload = {
                "status": store.integrity()["status"],
                "store": str(store.database),
                "task_count": len(snapshot["tasks"]),
                "run_count": len(snapshot["runs"]),
                "brief": build_secretary_brief(snapshot),
            }
        elif args.runtime_command == "sync-plan":
            payload = {
                "status": "READY",
                "store": str(store.database),
                **sync_runtime_plan(store, load_runtime_plan(args.plan)),
            }
        elif args.runtime_command == "brief":
            payload = {"status": store.integrity()["status"], **build_secretary_brief(store.snapshot())}
        elif args.runtime_command == "resolve":
            payload = {
                "status": "READY",
                "decision": store.resolve_decision(
                    args.decision, selected_option=args.option, by=args.by
                ),
            }
        else:
            adapter = OpenAICompatibleAdapter(
                api_base=os.environ.get("PERSONAL_AI_OS_API_BASE", ""),
                api_key=os.environ.get("PERSONAL_AI_OS_API_KEY", ""),
            )
            adapters = {adapter.adapter_id: adapter}
            if args.runtime_command == "run":
                payload = ExecutionBroker(store, adapters).dispatch(
                    args.task,
                    adapter_id=args.adapter,
                    model=args.model,
                )
                payload.setdefault("status", "READY" if payload.get("ok") else "BLOCKED")
            elif args.runtime_command == "advance":
                payload = AutoAdvanceEngine(
                    ExecutionBroker(store, adapters),
                    adapter_id=args.adapter,
                    model=args.model,
                ).advance(
                    max_steps=args.max_steps,
                    failure_budget=args.failure_budget,
                    workflow_id=args.workflow,
                )
                payload.setdefault("status", "READY" if payload.get("ok") else "BLOCKED")
            else:
                if args.host not in {"127.0.0.1", "localhost", "::1"}:
                    payload = {
                        "status": "BLOCKED",
                        "reason": "runtime server binds to loopback only",
                    }
                elif not args.model:
                    payload = {
                        "status": "BLOCKED",
                        "reason": "--model or PERSONAL_AI_OS_DEFAULT_MODEL is required",
                    }
                else:
                    server = create_runtime_server(
                        (args.host, args.port),
                        store=store,
                        adapters=adapters,
                        default_model=args.model,
                        web_root=args.web_root,
                    )
                    print(
                        json.dumps(
                            {
                                "status": "READY",
                                "url": f"http://{args.host}:{server.server_port}",
                                "store": str(store.database),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    try:
                        server.serve_forever()
                    except KeyboardInterrupt:
                        pass
                    finally:
                        server.server_close()
                    return 0
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("status") not in {"UNKNOWN", "BLOCKED"} else 2
