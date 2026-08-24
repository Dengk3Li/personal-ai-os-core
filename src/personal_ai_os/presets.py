from __future__ import annotations

from copy import deepcopy


_PRESETS = {
    "science": {
        "workflow_id": "science",
        "name": "Scientific workflow",
        "caption": "Hypothesis, protocol, parallel execution, analysis, and feedback",
        "layout": "loop",
        "goal": "Turn an open scientific question into a traceable sequence of experiments and decisions.",
        "tasks": [
            {
                "task_id": "science:hypothesis",
                "public_label": "Task A-01",
                "title": "Clarify the question and generate testable hypotheses",
                "acceptance": "The question, evidence gap, and testable hypotheses are explicit.",
                "agent_role": "Scientific Hypothesis Agent",
                "depends_on": [],
                "iteration": 1,
                "parallel_group": "main",
                "required_capabilities": ["reasoning", "evidence"],
                "complexity": "deep",
            },
            {
                "task_id": "science:protocol-a",
                "public_label": "Task A-02",
                "title": "Design protocol path A and its quality controls",
                "acceptance": "Actions, controls, stop conditions, and handoff are explicit.",
                "agent_role": "Protocol Design Agent",
                "depends_on": ["science:hypothesis"],
                "iteration": 2,
                "parallel_group": "path-a",
                "required_capabilities": ["reasoning", "tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:protocol-b",
                "public_label": "Task A-03",
                "title": "Design protocol path B and its quality controls",
                "acceptance": "The alternative path has a bounded protocol and QC plan.",
                "agent_role": "Protocol Design Agent",
                "depends_on": ["science:hypothesis"],
                "iteration": 2,
                "parallel_group": "path-b",
                "required_capabilities": ["reasoning", "tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:experiment-a",
                "public_label": "Task A-04",
                "title": "Execute path A and diagnose exceptions",
                "acceptance": "Actions, anomalies, and outputs are recorded.",
                "agent_role": "Autonomous Experiment Agent",
                "depends_on": ["science:protocol-a"],
                "iteration": 3,
                "parallel_group": "path-a",
                "required_capabilities": ["tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:experiment-b",
                "public_label": "Task A-05",
                "title": "Execute path B and diagnose exceptions",
                "acceptance": "The second path produces a comparable run record.",
                "agent_role": "Autonomous Experiment Agent",
                "depends_on": ["science:protocol-b"],
                "iteration": 3,
                "parallel_group": "path-b",
                "required_capabilities": ["tool_use"],
                "complexity": "deep",
            },
            {
                "task_id": "science:analysis",
                "public_label": "Task A-06",
                "title": "Analyze results and update the evidence state",
                "acceptance": "The result, uncertainty, and evidence update are inspectable.",
                "agent_role": "Data Analysis Agent",
                "depends_on": ["science:experiment-a", "science:experiment-b"],
                "iteration": 4,
                "parallel_group": "main",
                "required_capabilities": ["analysis", "evidence"],
                "complexity": "deep",
            },
            {
                "task_id": "science:feedback",
                "public_label": "Task A-07",
                "title": "Choose the next loop and update the path",
                "acceptance": "The next action, stop rule, and path update are decided.",
                "agent_role": "Feedback Optimization Agent",
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
        "name": "Meeting notes",
        "caption": "Source intake, extraction, draft, review, and delivery",
        "layout": "milestones",
        "goal": "Produce an attributable meeting record from provided source material.",
        "tasks": [
            {"task_id": "notes:intake", "title": "Register recordings and supplied documents", "acceptance": "Every source has an origin and availability state.", "agent_role": "Source Intake Agent", "depends_on": [], "iteration": 1, "parallel_group": "main", "required_capabilities": ["intake"], "complexity": "standard"},
            {"task_id": "notes:extract", "title": "Extract facts, statements, figures, and open questions", "acceptance": "Each extracted item points to its source.", "agent_role": "Information Extraction Agent", "depends_on": ["notes:intake"], "iteration": 2, "parallel_group": "main", "required_capabilities": ["long_context"], "complexity": "standard"},
            {"task_id": "notes:draft", "title": "Create a structured draft", "acceptance": "The draft separates facts, decisions, and follow-ups.", "agent_role": "Draft Agent", "depends_on": ["notes:extract"], "iteration": 3, "parallel_group": "main", "required_capabilities": ["writing"], "complexity": "standard"},
            {"task_id": "notes:review", "title": "Review attribution and omissions", "acceptance": "Attribution, omissions, and wording boundaries are checked.", "agent_role": "Content Review Agent", "depends_on": ["notes:draft"], "iteration": 4, "parallel_group": "gate", "required_capabilities": ["review"], "complexity": "deep", "human_gate": True},
            {"task_id": "notes:deliver", "title": "Produce the accepted delivery", "acceptance": "The accepted artifact and follow-ups are registered.", "agent_role": "Delivery Agent", "depends_on": ["notes:review"], "iteration": 5, "parallel_group": "main", "required_capabilities": ["writing"], "complexity": "standard"},
        ],
    },
    "analytical-report": {
        "workflow_id": "analytical-report",
        "name": "Analytical report",
        "caption": "Broad collection, evidence pool, argument planning, writing, and visual delivery",
        "layout": "branch",
        "goal": "Build a source-grounded analytical report through parallel evidence and production paths.",
        "tasks": [
            {"task_id": "report:collect", "title": "Collect broad source coverage", "acceptance": "The source set covers the stated scope and gaps.", "agent_role": "Collection Agent", "depends_on": [], "iteration": 1, "parallel_group": "main", "required_capabilities": ["search"], "complexity": "deep"},
            {"task_id": "report:pool", "title": "Build the evidence and data pool", "acceptance": "Claims and data point to traceable sources.", "agent_role": "Evidence Pool Agent", "depends_on": ["report:collect"], "iteration": 2, "parallel_group": "main", "required_capabilities": ["analysis", "evidence"], "complexity": "deep"},
            {"task_id": "report:argument", "title": "Plan the argument and section logic", "acceptance": "The structure, claims, and evidence needs are explicit.", "agent_role": "Report Planning Agent", "depends_on": ["report:pool"], "iteration": 3, "parallel_group": "argument", "required_capabilities": ["reasoning", "writing"], "complexity": "deep"},
            {"task_id": "report:visual", "title": "Plan charts, illustrations, and layout", "acceptance": "Each visual has a communication purpose and source boundary.", "agent_role": "Visual Planning Agent", "depends_on": ["report:pool"], "iteration": 3, "parallel_group": "visual", "required_capabilities": ["visual"], "complexity": "standard"},
            {"task_id": "report:write", "title": "Write sections with selected models", "acceptance": "Every section follows the accepted logic and evidence pool.", "agent_role": "Section Writing Agent", "depends_on": ["report:argument", "report:visual"], "iteration": 4, "parallel_group": "chapters", "required_capabilities": ["writing"], "complexity": "deep"},
            {"task_id": "report:finish", "title": "Review and prepare the final artifact", "acceptance": "Content, sources, layout, and open limits are accepted.", "agent_role": "Editorial Agent", "depends_on": ["report:write"], "iteration": 5, "parallel_group": "gate", "required_capabilities": ["review", "visual"], "complexity": "deep", "human_gate": True},
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
