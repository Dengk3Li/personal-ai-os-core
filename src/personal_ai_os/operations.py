from __future__ import annotations

from copy import deepcopy

from .states import TASK_STATE_LABELS, TASK_STATES, TERMINAL_STATES

_TASK_STATES = [
    {
        "state": state,
        "label": TASK_STATE_LABELS[state],
        "terminal": state in TERMINAL_STATES,
    }
    for state in TASK_STATES
]

_OPERATIONS = [
    {
        "operation": "INSPECT",
        "purpose": "只读检查工作区结构、文件信号和已有状态",
        "writes_workspace": False,
    },
    {
        "operation": "MAP",
        "purpose": "识别模块、能力、依赖和缺口",
        "writes_workspace": False,
    },
    {
        "operation": "PLAN",
        "purpose": "提出业务线、阶段和短任务候选",
        "writes_workspace": False,
    },
    {
        "operation": "CONFIRM",
        "purpose": "由人确认计划、边界和关键裁决点",
        "writes_workspace": False,
        "human_gate": True,
    },
    {
        "operation": "ROUTE",
        "purpose": "按能力、复杂度和上下文预算选择执行层",
        "writes_workspace": False,
    },
    {
        "operation": "EXECUTE",
        "purpose": "在已确认范围内执行一个短任务",
        "writes_workspace": True,
    },
    {
        "operation": "REVIEW",
        "purpose": "核验结果并决定接受、返工或阻塞",
        "writes_workspace": False,
    },
    {
        "operation": "ARCHIVE",
        "purpose": "保存可接续状态并归档已收口工作",
        "writes_workspace": True,
    },
]


def operation_spec() -> dict[str, object]:
    """Return the stable operating protocol shared by the CLI and workbench."""

    return {
        "spec_version": "0.6.0",
        "principle": "read_only_until_confirmed",
        "operations": deepcopy(_OPERATIONS),
        "task_states": deepcopy(_TASK_STATES),
    }
