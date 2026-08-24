from __future__ import annotations

from copy import deepcopy
from typing import Any


_MODULES = [
    {
        "module_id": "workspace-intake",
        "name": "本地工作区摄取",
        "layer": "input",
        "summary": "只读识别文件结构、项目类型和已有状态。",
        "provides": ["workspace.snapshot"],
        "requires": [],
        "availability": "READY",
    },
    {
        "module_id": "cognitive-intake",
        "name": "认知摄取",
        "layer": "understanding",
        "summary": "把材料整理成可检索、可判断的知识候选。",
        "provides": ["knowledge.candidates"],
        "requires": ["workspace.snapshot"],
        "availability": "READY",
    },
    {
        "module_id": "workflow-core",
        "name": "长期工作内核",
        "layer": "orchestration",
        "summary": "建立业务线、任务依赖、状态和人工裁决点。",
        "provides": ["work.plan", "work.task"],
        "requires": ["workspace.snapshot"],
        "availability": "READY",
    },
    {
        "module_id": "dynamic-router",
        "name": "动态路由",
        "layer": "orchestration",
        "summary": "按复杂度、能力和上下文预算选择执行层。",
        "provides": ["execution.route"],
        "requires": ["work.task"],
        "availability": "READY",
    },
    {
        "module_id": "execution-adapter",
        "name": "执行适配器",
        "layer": "execution",
        "summary": "把短任务交给兼容的模型或执行者。",
        "provides": ["execution.result"],
        "requires": ["execution.route"],
        "availability": "READY",
    },
    {
        "module_id": "continuity",
        "name": "连续性与接续",
        "layer": "memory",
        "summary": "保存当前状态，让下一次对话从真实进度继续。",
        "provides": ["workspace.resume"],
        "requires": ["work.task", "execution.result"],
        "availability": "READY",
    },
    {
        "module_id": "token-manager",
        "name": "Token Manager",
        "layer": "observability",
        "summary": "规划任务预算、上下文窗口和使用量展示。",
        "provides": ["token.budget"],
        "requires": ["work.task"],
        "availability": "PLANNED",
    },
]


def module_catalog() -> list[dict[str, Any]]:
    """Return the reusable built-in module manifests."""

    return deepcopy(_MODULES)


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

    blocked = bool(unresolved or duplicate_providers)
    return {
        "status": "BLOCKED" if blocked else "READY",
        "nodes": nodes,
        "edges": edges,
        "unresolved": unresolved,
        "duplicate_providers": duplicate_providers,
    }
