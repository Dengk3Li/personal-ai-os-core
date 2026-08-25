from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "personal-ai-os.work-protocols/v1"
_PROTOCOL_FIELDS = {
    "protocol_id",
    "name",
    "domain_id",
    "workflow_ids",
    "instruction_refs",
    "template_refs",
    "rules",
    "memory_subject",
    "learning_review",
}
_LEARNING_REVIEWS = {"candidate", "off"}
_MAX_ITEMS = 64
_MAX_TEXT = 2_000
_SENSITIVE_TEXT = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}"
    r"|(?:(?:gh[pousr]|hf|npm)_[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]{20,})"
    r"|(?:glpat-|pypi-|xox[baprs]-)[A-Za-z0-9_-]{16,}"
    r"|(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"
    r"|(?:AKIA|ASIA)[A-Z0-9]{16}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|Bearer\s+\S+"
    r"|(?:api[_-]?key|client[_-]?secret|secret(?:[_-]?key)?|access[_-]?key|private[_-]?key|password|token)\s*[:=]\s*\S{8,}"
    r"|[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@",
    re.IGNORECASE,
)

_BUILTIN_PROTOCOLS = [
    {
        "protocol_id": "meeting-source-first-v1",
        "name": "完整会议记录",
        "domain_id": "writing",
        "workflow_ids": ["meeting-notes"],
        "instruction_refs": ["instruction://meeting/source-first"],
        "template_refs": ["template://meeting/full-record-v3"],
        "rules": [
            "原始逐字记录是事实来源；随附材料只补充名称与背景。",
            "保留完整会议结构，不降级为精简摘要。",
            "章节按会议自然讨论顺序组织；未讨论板块不强行补齐，模板外的重要内容单独成节。",
            "正文以完整信息单元为主，数字、金额、时间、人名和技术参数必须精确保留。",
            "问题与回答保持对应关系；明确列举不得用“等”省略。",
            "来源缺失或归因不清时停止并请求补充材料。",
        ],
        "memory_subject": {"kind": "team", "id": "meeting-notes"},
        "learning_review": "candidate",
    }
]


def _bounded_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > _MAX_TEXT:
        raise ValueError(f"work protocol {field} is required and must be bounded")
    if _SENSITIVE_TEXT.search(text):
        raise ValueError(f"work protocol {field} contains sensitive content")
    return text


def _bounded_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        raise ValueError(f"work protocol {field} must be a bounded list")
    return [_bounded_text(item, field) for item in value]


def validate_work_protocols(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"work protocol schema must be {SCHEMA_VERSION}")
    protocols = payload.get("protocols")
    if not isinstance(protocols, list) or not protocols or len(protocols) > _MAX_ITEMS:
        raise ValueError("work protocols must be a non-empty bounded list")
    normalized = []
    seen = set()
    for item in protocols:
        if not isinstance(item, dict):
            raise ValueError("work protocol must be an object")
        forbidden = set(item) - _PROTOCOL_FIELDS
        if forbidden:
            raise ValueError(f"work protocol contains forbidden fields: {sorted(forbidden)}")
        protocol_id = _bounded_text(item.get("protocol_id"), "protocol_id")
        if protocol_id in seen:
            raise ValueError(f"duplicate work protocol: {protocol_id}")
        seen.add(protocol_id)
        learning_review = str(item.get("learning_review") or "off").strip()
        if learning_review not in _LEARNING_REVIEWS:
            raise ValueError("work protocol learning_review must be candidate or off")
        memory_subject = item.get("memory_subject")
        if memory_subject is not None:
            if not isinstance(memory_subject, dict) or set(memory_subject) != {"kind", "id"}:
                raise ValueError("work protocol memory_subject must contain kind and id")
            if str(memory_subject.get("kind") or "").strip() not in {"person", "team"}:
                raise ValueError("work protocol memory_subject kind must be person or team")
            memory_subject = {
                "kind": _bounded_text(memory_subject.get("kind"), "memory_subject.kind"),
                "id": _bounded_text(memory_subject.get("id"), "memory_subject.id"),
            }
        workflow_ids = _bounded_list(item.get("workflow_ids") or [], "workflow_ids")
        if not workflow_ids:
            raise ValueError("work protocol workflow_ids must not be empty")
        rules = _bounded_list(item.get("rules") or [], "rules")
        if not rules:
            raise ValueError("work protocol rules must not be empty")
        normalized.append(
            {
                "protocol_id": protocol_id,
                "name": _bounded_text(item.get("name"), "name"),
                "domain_id": _bounded_text(item.get("domain_id"), "domain_id"),
                "workflow_ids": workflow_ids,
                "instruction_refs": _bounded_list(item.get("instruction_refs") or [], "instruction_refs"),
                "template_refs": _bounded_list(item.get("template_refs") or [], "template_refs"),
                "rules": rules,
                "memory_subject": memory_subject,
                "learning_review": learning_review,
            }
        )
    return normalized


def load_work_protocols(source: str | Path | dict[str, Any]) -> list[dict[str, Any]]:
    payload = source
    if not isinstance(source, dict):
        payload = json.loads(Path(source).expanduser().read_text(encoding="utf-8"))
    return validate_work_protocols(payload)


def work_protocol_catalog() -> list[dict[str, Any]]:
    return deepcopy(_BUILTIN_PROTOCOLS)
