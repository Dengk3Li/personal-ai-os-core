from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .modules import build_module_graph, module_catalog
from .operations import operation_spec


_SKIP_DIRECTORIES = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}

_LINE_RULES = [
    {
        "line_id": "product",
        "name": "产品线",
        "layout": "milestones",
        "markers": ("src/", "app/", "workbench/", "package.json", "setup.cfg", "pyproject.toml"),
    },
    {
        "line_id": "research",
        "name": "科研线",
        "layout": "timeline",
        "markers": ("research/", "paper", "experiment", "notebook", ".ipynb"),
    },
    {
        "line_id": "writing",
        "name": "写作线",
        "layout": "pipeline",
        "markers": ("draft", "outline", "writing/", ".docx", "manuscript"),
    },
]


def _workspace_files(root: Path, max_files: int) -> tuple[list[str], bool]:
    files: list[str] = []
    truncated = False
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(item for item in directories if item not in _SKIP_DIRECTORIES)
        current_path = Path(current)
        for name in sorted(names):
            files.append((current_path / name).relative_to(root).as_posix())
            if len(files) >= max_files:
                truncated = True
                return files, truncated
    return files, truncated


def _suggest_lines(files: list[str]) -> list[dict[str, str]]:
    lowered = [path.lower() for path in files]
    suggestions = []
    for rule in _LINE_RULES:
        if any(any(marker in path for marker in rule["markers"]) for path in lowered):
            suggestions.append(
                {
                    "line_id": rule["line_id"],
                    "name": rule["name"],
                    "layout": rule["layout"],
                }
            )
    return suggestions


def _git_state(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"present": False, "status": "NOT_A_REPOSITORY", "dirty_count": 0}
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--short", "--branch"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"present": True, "status": "UNKNOWN", "dirty_count": None}
    if result.returncode != 0:
        return {"present": True, "status": "UNKNOWN", "dirty_count": None}
    lines = result.stdout.splitlines()
    change_lines = [line for line in lines if not line.startswith("##")]
    return {
        "present": True,
        "status": "DIRTY" if change_lines else "CLEAN",
        "dirty_count": len(change_lines),
        "untracked_count": sum(line.startswith("??") for line in change_lines),
        "branch_summary": lines[0][3:] if lines and lines[0].startswith("## ") else "UNKNOWN",
    }


def inspect_workspace(path: str | Path, *, max_files: int = 5000) -> dict[str, Any]:
    """Inspect local project structure without writing into the target workspace."""

    root = Path(path).expanduser()
    if not root.exists() or not root.is_dir():
        return {
            "status": "UNKNOWN",
            "reason": "WORKSPACE_NOT_FOUND",
            "read_only": True,
            "workspace_name": root.name,
            "file_count": 0,
            "files": [],
            "suggested_lines": [],
        }

    files, truncated = _workspace_files(root, max_files)
    extensions: dict[str, int] = {}
    for path_string in files:
        suffix = Path(path_string).suffix.lower() or "[no extension]"
        extensions[suffix] = extensions.get(suffix, 0) + 1

    return {
        "status": "INSPECTED",
        "read_only": True,
        "workspace_name": root.name,
        "file_count": len(files),
        "truncated": truncated,
        "extensions": dict(sorted(extensions.items(), key=lambda item: (-item[1], item[0]))),
        "signals": {
            "has_git": (root / ".git").exists(),
            "has_agent_contract": (root / "AGENTS.md").exists(),
            "has_readme": any(Path(item).name.lower().startswith("readme") for item in files),
        },
        "git": _git_state(root),
        "files": files,
        "suggested_lines": _suggest_lines(files),
        "module_graph": build_module_graph(module_catalog()),
    }


def build_candidate_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Turn a read-only workspace snapshot into a human-confirmed plan candidate."""

    if snapshot.get("status") != "INSPECTED":
        return {
            "status": "BLOCKED",
            "reason": snapshot.get("reason", "WORKSPACE_NOT_INSPECTED"),
            "requires_human_confirmation": False,
            "business_lines": [],
            "operation_chain": operation_spec()["operations"],
        }

    lines = snapshot.get("suggested_lines") or [
        {"line_id": "general", "name": "通用工作线", "layout": "pipeline"}
    ]
    git_state = snapshot.get("git") or {}
    preflight_tasks = []
    if git_state.get("status") == "DIRTY":
        preflight_tasks.append(
            {
                "task_id": "workspace:dirty-boundary",
                "title": "确认现有改动归属与保留范围",
                "status": "QUEUED",
                "human_gate": True,
                "summary": f"检测到 {git_state.get('dirty_count', 0)} 项未提交变更；确认前保持只读。",
            }
        )
    elif git_state.get("status") == "UNKNOWN":
        preflight_tasks.append(
            {
                "task_id": "workspace:git-readback",
                "title": "补充 Git 状态读回",
                "status": "BLOCKED",
                "human_gate": True,
                "summary": "无法可靠读取仓库状态，执行保持阻塞。",
            }
        )

    business_lines = []
    for line in lines:
        line_id = line["line_id"]
        business_lines.append(
            {
                **line,
                "status": "QUEUED",
                "tasks": [
                    {
                        "task_id": f"{line_id}:scope",
                        "title": f"确认{line['name']}目标与边界",
                        "status": "QUEUED",
                        "human_gate": True,
                        "depends_on": [item["task_id"] for item in preflight_tasks],
                    },
                    {
                        "task_id": f"{line_id}:first-deliverable",
                        "title": f"生成{line['name']}首个可验收结果",
                        "status": "QUEUED",
                        "depends_on": [f"{line_id}:scope"],
                        "human_gate": False,
                    },
                ],
            }
        )

    return {
        "status": "CANDIDATE",
        "workspace_name": snapshot.get("workspace_name", "workspace"),
        "requires_human_confirmation": True,
        "preflight_tasks": preflight_tasks,
        "business_lines": business_lines,
        "module_graph": snapshot.get("module_graph"),
        "operation_chain": operation_spec()["operations"],
    }
