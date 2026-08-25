from __future__ import annotations

from copy import deepcopy


_PRESETS = {
    "science": {
        "workflow_id": "science",
        "name": "科研工作线",
        "caption": "科学假设、实验方案、并行执行、数据分析与反馈优化",
        "layout": "loop",
        "goal": "把开放科学问题转化为可追溯的实验、证据与下一轮决定。",
        "tasks": [
            {
                "task_id": "science:hypothesis",
                "public_label": "科研 01",
                "title": "澄清科学问题并提出可检验假设",
                "acceptance": "科学问题、证据缺口和可检验假设均清晰可查。",
                "agent_role": "科学假设角色",
                "depends_on": [],
                "iteration": 1,
                "parallel_group": "main",
                "required_capabilities": ["reasoning", "evidence"],
                "complexity": "deep",
            },
            {
                "task_id": "science:protocol-a",
                "public_label": "科研 02",
                "title": "设计实验路径 A 与质量控制方案",
                "acceptance": "实验动作、质量控制、停止条件和交接方式均明确。",
                "agent_role": "实验方案设计角色",
                "depends_on": ["science:hypothesis"],
                "iteration": 2,
                "parallel_group": "path-a",
                "required_capabilities": ["reasoning", "tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:protocol-b",
                "public_label": "科研 03",
                "title": "设计实验路径 B 与质量控制方案",
                "acceptance": "备选路径具有边界明确的实验方案和质量控制计划。",
                "agent_role": "实验方案设计角色",
                "depends_on": ["science:hypothesis"],
                "iteration": 2,
                "parallel_group": "path-b",
                "required_capabilities": ["reasoning", "tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:experiment-a",
                "public_label": "科研 04",
                "title": "执行路径 A 并诊断异常",
                "acceptance": "实验动作、异常和输出均有记录。",
                "agent_role": "自主实验执行角色",
                "depends_on": ["science:protocol-a"],
                "iteration": 3,
                "parallel_group": "path-a",
                "required_capabilities": ["tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:experiment-b",
                "public_label": "科研 05",
                "title": "执行路径 B 并诊断异常",
                "acceptance": "第二条路径形成可比较的运行记录。",
                "agent_role": "自主实验执行角色",
                "depends_on": ["science:protocol-b"],
                "iteration": 3,
                "parallel_group": "path-b",
                "required_capabilities": ["tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:analysis",
                "public_label": "科研 06",
                "title": "分析结果并更新证据状态",
                "acceptance": "结果、不确定性和证据变化均可检查。",
                "agent_role": "数据分析角色",
                "depends_on": ["science:experiment-a", "science:experiment-b"],
                "iteration": 4,
                "parallel_group": "main",
                "required_capabilities": ["analysis", "evidence"],
                "complexity": "deep",
            },
            {
                "task_id": "science:feedback",
                "public_label": "科研 07",
                "title": "判断是否进入下一轮并更新路径",
                "acceptance": "下一动作、停止规则和路径更新均已确认。",
                "agent_role": "反馈优化角色",
                "depends_on": ["science:analysis"],
                "iteration": 5,
                "parallel_group": "gate",
                "required_capabilities": ["reasoning"],
                "complexity": "deep",
                "human_gate": True,
            },
        ],
    },
    "meeting-notes": {
        "workflow_id": "meeting-notes",
        "name": "会议纪要工作线",
        "caption": "材料登记、信息抽取、初稿、审核与交付",
        "layout": "milestones",
        "goal": "根据提供的原始材料形成归因清楚、可核对的会议记录。",
        "tasks": [
            {"task_id": "notes:intake", "title": "登记录音与随附材料", "acceptance": "每份材料都有来源和可用状态。", "agent_role": "材料摄取角色", "depends_on": [], "iteration": 1, "parallel_group": "main", "required_capabilities": ["intake"], "complexity": "standard"},
            {"task_id": "notes:extract", "title": "提取事实、观点、数字与待确认项", "acceptance": "每项提取内容都能回到原始材料。", "agent_role": "信息抽取角色", "depends_on": ["notes:intake"], "iteration": 2, "parallel_group": "main", "required_capabilities": ["long_context"], "complexity": "standard"},
            {"task_id": "notes:draft", "title": "形成结构化初稿", "acceptance": "初稿区分事实、决定和后续事项。", "agent_role": "初稿生成角色", "depends_on": ["notes:extract"], "iteration": 3, "parallel_group": "main", "required_capabilities": ["writing"], "complexity": "standard"},
            {"task_id": "notes:review", "title": "核对归因、遗漏和表达边界", "acceptance": "归因、遗漏和措辞边界均已检查。", "agent_role": "内容审核角色", "depends_on": ["notes:draft"], "iteration": 4, "parallel_group": "gate", "required_capabilities": ["review"], "complexity": "deep", "human_gate": True},
            {"task_id": "notes:deliver", "title": "生成验收后的交付版本", "acceptance": "已验收产物和后续事项均已登记。", "agent_role": "交付角色", "depends_on": ["notes:review"], "iteration": 5, "parallel_group": "main", "required_capabilities": ["writing"], "complexity": "standard"},
        ],
    },
    "analytical-report": {
        "workflow_id": "analytical-report",
        "name": "深度分析报告工作线",
        "caption": "广域收集、证据池、论证规划、分章写作与视觉交付",
        "layout": "branch",
        "goal": "通过并行的证据与生产路径形成来源充分的深度分析报告。",
        "tasks": [
            {"task_id": "report:collect", "title": "广泛收集信息与来源", "acceptance": "来源集合覆盖既定范围并标明缺口。", "agent_role": "广域检索角色", "depends_on": [], "iteration": 1, "parallel_group": "main", "required_capabilities": ["search"], "complexity": "deep"},
            {"task_id": "report:pool", "title": "建立证据与数据池", "acceptance": "观点和数据均指向可追溯来源。", "agent_role": "证据池整理角色", "depends_on": ["report:collect"], "iteration": 2, "parallel_group": "main", "required_capabilities": ["analysis", "evidence"], "complexity": "deep"},
            {"task_id": "report:argument", "title": "规划论证与章节逻辑", "acceptance": "结构、核心判断和证据需求均明确。", "agent_role": "报告规划角色", "depends_on": ["report:pool"], "iteration": 3, "parallel_group": "argument", "required_capabilities": ["reasoning", "writing"], "complexity": "deep"},
            {"task_id": "report:visual", "title": "规划图表、配图与版式", "acceptance": "每项视觉内容都有明确用途和来源边界。", "agent_role": "视觉规划角色", "depends_on": ["report:pool"], "iteration": 3, "parallel_group": "visual", "required_capabilities": ["visual"], "complexity": "standard"},
            {"task_id": "report:write", "title": "按章节选择模型并撰写", "acceptance": "每个章节遵守已确认的论证逻辑和证据池。", "agent_role": "章节写作角色", "depends_on": ["report:argument", "report:visual"], "iteration": 4, "parallel_group": "chapters", "required_capabilities": ["writing"], "complexity": "deep"},
            {"task_id": "report:finish", "title": "审核并形成最终交付", "acceptance": "内容、来源、版式和未决边界均已验收。", "agent_role": "编辑审核角色", "depends_on": ["report:write"], "iteration": 5, "parallel_group": "gate", "required_capabilities": ["review", "visual"], "complexity": "deep", "human_gate": True},
        ],
    },
}


def get_workflow_preset(preset_id: str) -> dict:
    try:
        return deepcopy(_PRESETS[preset_id])
    except KeyError as exc:
        raise ValueError(f"unknown workflow preset: {preset_id}") from exc


def workflow_preset_catalog() -> list[dict]:
    return [
        {key: value[key] for key in ("workflow_id", "name", "caption", "layout")}
        for value in _PRESETS.values()
    ]
