from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


MODULE_CONTRACT_VERSION = "personal-ai-os.module/v1"


_MODULES = [
    {
        "contract_version": MODULE_CONTRACT_VERSION,
        "module_id": "workspace-intake",
        "name": "本地工作区摄取",
        "layer": "input",
        "summary": "只读识别文件结构、项目类型和已有状态。",
        "provides": ["workspace.snapshot"],
        "requires": [],
        "availability": "READY",
        "optional": False,
        "entrypoint": "builtin://workspace-intake",
    },
    {
        "contract_version": MODULE_CONTRACT_VERSION,
        "module_id": "cognitive-intake",
        "name": "认知摄取",
        "layer": "understanding",
        "summary": "把材料整理成可检索、可判断的知识候选。",
        "provides": ["knowledge.candidates"],
        "requires": ["workspace.snapshot"],
        "availability": "READY",
        "optional": True,
        "entrypoint": "builtin://cognitive-intake",
    },
    {
        "contract_version": MODULE_CONTRACT_VERSION,
        "module_id": "workflow-core",
        "name": "长期工作内核",
        "layer": "orchestration",
        "summary": "建立业务线、任务依赖、状态和人工裁决点。",
        "provides": ["work.plan", "work.task"],
        "requires": ["workspace.snapshot"],
        "availability": "READY",
        "optional": False,
        "entrypoint": "builtin://workflow-core",
    },
    {
        "contract_version": MODULE_CONTRACT_VERSION,
        "module_id": "dynamic-router",
        "name": "动态路由",
        "layer": "orchestration",
        "summary": "按复杂度、能力和上下文预算选择执行层。",
        "provides": ["execution.route"],
        "requires": ["work.task"],
        "availability": "READY",
        "optional": True,
        "entrypoint": "builtin://dynamic-router",
    },
    {
        "contract_version": MODULE_CONTRACT_VERSION,
        "module_id": "execution-adapter",
        "name": "执行适配器",
        "layer": "execution",
        "summary": "把短任务交给兼容的模型或执行者。",
        "provides": ["execution.result"],
        "requires": ["execution.route"],
        "availability": "READY",
        "optional": True,
        "entrypoint": "builtin://execution-adapter",
    },
    {
        "contract_version": MODULE_CONTRACT_VERSION,
        "module_id": "continuity",
        "name": "连续性与接续",
        "layer": "memory",
        "summary": "保存当前状态，让下一次对话从真实进度继续。",
        "provides": ["workspace.resume"],
        "requires": ["work.task", "execution.result"],
        "availability": "READY",
        "optional": True,
        "entrypoint": "builtin://continuity",
    },
    {
        "contract_version": MODULE_CONTRACT_VERSION,
        "module_id": "token-manager",
        "name": "Token Manager",
        "layer": "observability",
        "summary": "规划任务预算、上下文窗口和使用量展示。",
        "provides": ["token.budget"],
        "requires": ["work.task"],
        "availability": "PLANNED",
        "optional": True,
        "entrypoint": "builtin://token-manager",
    },
]


_SYSTEM_GRAPH_MODULE_IDS = {
    "analysis-domain", "branch-node", "candidate-extract", "condition-node",
    "continuity", "conversation-learning", "delivery", "domain-routing",
    "domain-systems", "domain-template", "dynamic-route", "evidence-check",
    "execution", "experience-candidate", "goal-boundary", "human-decision",
    "human-promotion", "join-node", "learning-cycle", "longtask-kernel",
    "loop-node", "module-task-link", "owner-accept", "personal-context",
    "personal-domain", "science-domain", "secretary-entry", "sequence-node",
    "signal-capture", "task-load", "task-node", "task-state",
    "workflow-compiler", "writing-domain",
}


_REQUIRED_MANIFEST_FIELDS = {
    "contract_version",
    "module_id",
    "name",
    "layer",
    "provides",
    "requires",
    "availability",
    "optional",
    "entrypoint",
}


def module_catalog() -> list[dict[str, Any]]:
    """Return the reusable built-in module manifests."""

    return deepcopy(_MODULES)


def public_module_ids() -> set[str]:
    """Return stable IDs rendered by either built-in module-map view."""

    return _SYSTEM_GRAPH_MODULE_IDS | {
        module["module_id"] for module in _MODULES
    }


def discover_module_manifests(directory: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Read direct-child module manifests without importing or executing plug-in code."""

    root = Path(directory)
    modules: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    if not root.is_dir():
        return {"modules": modules, "rejected": rejected}

    for manifest_path in sorted(root.glob("*/module.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rejected.append({"path": str(manifest_path), "reason": "INVALID_JSON"})
            continue
        if not isinstance(manifest, dict):
            rejected.append({"path": str(manifest_path), "reason": "INVALID_MANIFEST"})
            continue
        if _REQUIRED_MANIFEST_FIELDS - manifest.keys():
            rejected.append({"path": str(manifest_path), "reason": "MISSING_FIELDS"})
            continue
        if manifest["contract_version"] != MODULE_CONTRACT_VERSION:
            rejected.append({"path": str(manifest_path), "reason": "UNSUPPORTED_CONTRACT"})
            continue
        if not isinstance(manifest["provides"], list) or not isinstance(manifest["requires"], list):
            rejected.append({"path": str(manifest_path), "reason": "INVALID_CAPABILITIES"})
            continue
        module_id = manifest["module_id"]
        if not isinstance(module_id, str) or not module_id or module_id in seen_ids:
            rejected.append({"path": str(manifest_path), "reason": "INVALID_MODULE_ID"})
            continue
        seen_ids.add(module_id)
        modules.append(deepcopy(manifest))

    return {"modules": modules, "rejected": rejected}


def build_module_graph(modules: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve module requirements to providers and expose composition failures."""

    nodes = deepcopy(modules)
    providers: dict[str, str] = {}
    duplicate_providers: list[dict[str, str]] = []
    for module in nodes:
        for capability in module.get("provides", []):
            if capability in providers:
                duplicate_providers.append(
                    {
                        "capability": capability,
                        "first": providers[capability],
                        "second": module.get("module_id", ""),
                    }
                )
            else:
                providers[capability] = module.get("module_id", "")

    edges: list[list[str]] = []
    unresolved: list[dict[str, str]] = []
    for module in nodes:
        module_id = module.get("module_id", "")
        for capability in module.get("requires", []):
            provider = providers.get(capability)
            if provider:
                edge = [provider, module_id]
                if edge not in edges:
                    edges.append(edge)
            else:
                unresolved.append({"module_id": module_id, "capability": capability})

    module_ids = {module.get("module_id", "") for module in nodes}
    direct_module_references = sum(
        requirement in module_ids
        for module in nodes
        for requirement in module.get("requires", [])
    )
    capability_edges = sum(len(module.get("requires", [])) for module in nodes) - len(unresolved)
    blocked = bool(unresolved or duplicate_providers or direct_module_references)
    return {
        "status": "BLOCKED" if blocked else "READY",
        "nodes": nodes,
        "edges": edges,
        "unresolved": unresolved,
        "duplicate_providers": duplicate_providers,
        "interfaces": providers,
        "coupling": {
            "capability_edges": capability_edges,
            "direct_module_references": direct_module_references,
            "optional_modules": sum(bool(module.get("optional")) for module in nodes),
        },
    }
