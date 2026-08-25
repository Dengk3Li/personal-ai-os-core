from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "personal-ai-os.presentation/v1"
WORKFLOW_FIELDS = {"name", "caption", "goal"}
TASK_FIELDS = {"public_label", "title", "acceptance", "agent_role", "flow_kind"}
FLOW_KINDS = {"sequence", "branch", "join", "condition", "loop"}
MAX_TEXT_LENGTH = 2_000
MAX_IDENTIFIER_LENGTH = 512
_SENSITIVE_TEXT = re.compile(
    r"/(?:Users|home|Volumes|private|var|tmp|opt|etc)/"
    r"|[A-Za-z]:\\"
    r"|file://"
    r"|~[/\\]"
    r"|sk-[A-Za-z0-9_-]{16,}"
    r"|Bearer\s+\S+"
    r"|(?:api[_-]?key|password|token)\s*[:=]\s*\S{8,}"
    r"|https?://[^/\s:@]+:[^/\s@]+@",
    re.IGNORECASE,
)


def _reject_sensitive_identifier(value: Any, *, boundary: str) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    if len(text) > MAX_IDENTIFIER_LENGTH or _SENSITIVE_TEXT.search(text):
        raise ValueError(f"sensitive {boundary} identifier")


def validate_runtime_label(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) > MAX_IDENTIFIER_LENGTH or _SENSITIVE_TEXT.search(text):
        raise ValueError("sensitive runtime label")
    return text


def _ordered_aliases(values: list[Any], prefix: str, width: int) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for value in values:
        if value is None or str(value).strip() == "":
            continue
        item_id = str(value)
        if item_id not in aliases:
            aliases[item_id] = f"{prefix}-{len(aliases) + 1:0{width}d}"
    return aliases


def identifier_aliases(snapshot: dict[str, Any]) -> dict[str, dict[str, str]]:
    workflows = list(snapshot.get("workflows", []))
    tasks = list(snapshot.get("tasks", []))
    runs = list(snapshot.get("runs", []))
    events = list(snapshot.get("events", []))
    artifacts = list(snapshot.get("artifacts", []))
    decisions = list(snapshot.get("decisions", []))
    assignments = snapshot.get("assignments") or {}
    workflow_values = [item.get("workflow_id") for item in workflows]
    workflow_values.extend(task.get("workflow_id") for task in tasks)
    workflow_values.extend(task.get("line_id") for task in tasks)
    task_values = [task.get("task_id") for task in tasks]
    for task in tasks:
        task_values.extend(task.get("depends_on") or [])
    task_values.extend(event.get("task_id") for event in events)
    task_values.extend(decision.get("task_id") for decision in decisions)
    task_values.extend(assignments.keys())
    artifact_values = [item.get("artifact_id") for item in artifacts]
    for task in tasks:
        artifact_values.extend(task.get("artifact_refs") or [])
        artifact_values.append(task.get("result_ref"))
    return {
        "workflows": _ordered_aliases(workflow_values, "line", 2),
        "tasks": _ordered_aliases(task_values, "task", 3),
        "runs": _ordered_aliases(
            [item.get("run_id") for item in runs]
            + [item.get("run_id") for item in events]
            + [item.get("run_id") for item in artifacts],
            "run",
            3,
        ),
        "events": _ordered_aliases(
            [item.get("event_id") for item in events], "event", 3
        ),
        "artifacts": _ordered_aliases(artifact_values, "artifact", 3),
        "decisions": _ordered_aliases(
            [item.get("decision_id") for item in decisions], "decision", 3
        ),
        "domains": _ordered_aliases(
            [task.get("domain_id") for task in tasks]
            + [workflow.get("domain_id") for workflow in workflows],
            "domain",
            2,
        ),
        "groups": _ordered_aliases(
            [task.get("parallel_group") for task in tasks], "group", 2
        ),
        "capabilities": _ordered_aliases(
            [
                capability
                for task in tasks
                for capability in (task.get("required_capabilities") or [])
            ],
            "capability",
            2,
        ),
    }


def _alias(value: Any, mapping: dict[str, str]) -> Any:
    if value is None or str(value).strip() == "":
        return value
    return mapping.get(str(value), value)


def _anonymize_runtime_identifiers(
    snapshot: dict[str, Any], aliases: dict[str, dict[str, str]]
) -> None:
    for workflow in snapshot.get("workflows", []):
        workflow["workflow_id"] = _alias(
            workflow.get("workflow_id"), aliases["workflows"]
        )
        workflow["domain_id"] = _alias(
            workflow.get("domain_id"), aliases["domains"]
        )
    for task in snapshot.get("tasks", []):
        task["task_id"] = _alias(task.get("task_id"), aliases["tasks"])
        task["workflow_id"] = _alias(
            task.get("workflow_id"), aliases["workflows"]
        )
        task["line_id"] = _alias(task.get("line_id"), aliases["workflows"])
        task["depends_on"] = [
            _alias(value, aliases["tasks"]) for value in task.get("depends_on") or []
        ]
        task["domain_id"] = _alias(task.get("domain_id"), aliases["domains"])
        task["parallel_group"] = _alias(
            task.get("parallel_group"), aliases["groups"]
        )
        task["required_capabilities"] = [
            _alias(value, aliases["capabilities"])
            for value in task.get("required_capabilities") or []
        ]
        task["result_ref"] = _alias(
            task.get("result_ref"), aliases["artifacts"]
        )
        task["artifact_refs"] = [
            _alias(value, aliases["artifacts"])
            for value in task.get("artifact_refs") or []
        ]
    for run in snapshot.get("runs", []):
        run["run_id"] = _alias(run.get("run_id"), aliases["runs"])
        run["task_id"] = _alias(run.get("task_id"), aliases["tasks"])
    for event in snapshot.get("events", []):
        event["event_id"] = _alias(event.get("event_id"), aliases["events"])
        event["task_id"] = _alias(event.get("task_id"), aliases["tasks"])
        event["run_id"] = _alias(event.get("run_id"), aliases["runs"])
    for artifact in snapshot.get("artifacts", []):
        artifact["artifact_id"] = _alias(
            artifact.get("artifact_id"), aliases["artifacts"]
        )
        artifact["task_id"] = _alias(artifact.get("task_id"), aliases["tasks"])
        artifact["run_id"] = _alias(artifact.get("run_id"), aliases["runs"])
    for decision in snapshot.get("decisions", []):
        decision["decision_id"] = _alias(
            decision.get("decision_id"), aliases["decisions"]
        )
        decision["task_id"] = _alias(
            decision.get("task_id"), aliases["tasks"]
        )
    projected_assignments: dict[str, dict[str, Any]] = {}
    for task_id, assignment in (snapshot.get("assignments") or {}).items():
        for value in (assignment or {}).values():
            _reject_sensitive_identifier(value, boundary="runtime")
        projected_assignments[str(_alias(task_id, aliases["tasks"]))] = dict(
            assignment or {}
        )
    snapshot["assignments"] = projected_assignments


def _copy_map(value: Any, *, allowed: set[str], section: str) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"presentation {section} must be an object")
    result: dict[str, dict[str, str]] = {}
    for raw_id, raw_copy in value.items():
        item_id = str(raw_id).strip()
        if not item_id or not isinstance(raw_copy, dict):
            raise ValueError(f"presentation {section} entries must be named objects")
        _reject_sensitive_identifier(item_id, boundary="presentation")
        unsupported = set(raw_copy) - allowed
        if unsupported:
            raise ValueError(
                f"unsupported presentation field: {sorted(unsupported)[0]}"
            )
        display: dict[str, str] = {}
        for field, raw_text in raw_copy.items():
            if not isinstance(raw_text, str):
                raise ValueError(f"presentation field must be text: {field}")
            text = raw_text.strip()
            if not text or len(text) > MAX_TEXT_LENGTH:
                raise ValueError(f"presentation field is empty or too long: {field}")
            if field == "flow_kind" and text not in FLOW_KINDS:
                raise ValueError(f"presentation flow kind is invalid: {text}")
            if _SENSITIVE_TEXT.search(text):
                raise ValueError(f"sensitive presentation text: {field}")
            display[field] = text
        result[item_id] = display
    return result


def validate_presentation(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("presentation must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported presentation schema")
    unsupported = set(payload) - {"schema_version", "workflows", "tasks"}
    if unsupported:
        raise ValueError(f"unsupported presentation field: {sorted(unsupported)[0]}")
    return {
        "schema_version": SCHEMA_VERSION,
        "workflows": _copy_map(
            payload.get("workflows"), allowed=WORKFLOW_FIELDS, section="workflows"
        ),
        "tasks": _copy_map(
            payload.get("tasks"), allowed=TASK_FIELDS, section="tasks"
        ),
    }


def load_presentation(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return validate_presentation(payload)


def apply_presentation(
    snapshot: dict[str, Any], presentation: dict[str, Any] | None
) -> dict[str, Any]:
    projected = deepcopy(snapshot)
    if not presentation:
        return projected
    display = validate_presentation(presentation)
    aliases = identifier_aliases(projected)
    workflow_copy = display["workflows"]
    task_copy = display["tasks"]
    projected["workflows"] = [
        {
            **item,
            "name": workflow_copy.get(str(item.get("workflow_id")), {}).get(
                "name", f"工作线 {index:02d}"
            ),
            "caption": workflow_copy.get(str(item.get("workflow_id")), {}).get(
                "caption", "本地长期任务"
            ),
            "goal": workflow_copy.get(str(item.get("workflow_id")), {}).get(
                "goal", "按已登记任务持续推进"
            ),
        }
        for index, item in enumerate(projected.get("workflows", []), start=1)
    ]
    projected["tasks"] = [
        {
            **item,
            "public_label": task_copy.get(str(item.get("task_id")), {}).get(
                "public_label", f"任务 {index:02d}"
            ),
            "title": task_copy.get(str(item.get("task_id")), {}).get(
                "title", f"任务 {index:02d}"
            ),
            "acceptance": task_copy.get(str(item.get("task_id")), {}).get(
                "acceptance", "形成可检查、可继续推进的阶段结果"
            ),
            "agent_role": task_copy.get(str(item.get("task_id")), {}).get(
                "agent_role", "通用执行角色"
            ),
            "flow_kind": task_copy.get(str(item.get("task_id")), {}).get(
                "flow_kind", "sequence"
            ),
        }
        for index, item in enumerate(projected.get("tasks", []), start=1)
    ]
    _anonymize_runtime_identifiers(projected, aliases)
    return projected
