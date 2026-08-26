"""Public core primitives for an authority-aware personal AI control plane."""

from .acceptance_projection import build_acceptance_snapshot
from .continuity import (
    build_capsule,
    build_continuity_capsule,
    build_runtime_continuity_capsule,
)
from .cognition import compile_operating_practices, validate_memory_candidate
from .memory_context import read_memory_context, request_memory_review
from .dispatching import assign_task, select_execution_route, task_route_requirements
from .freeze import freeze_assets, verify_freeze
from .git_closure import evaluate_git_closure
from .goals import GoalController, load_goal_definition
from .intake import build_candidate_plan, inspect_workspace
from .modules import build_module_graph, module_catalog
from .operations import operation_spec
from .promotion import promote_candidate
from .planning import project_plan, ready_tasks, validate_plan
from .presentation import apply_presentation, load_presentation
from .presets import get_workflow_preset, workflow_preset_catalog
from .routing import compile_domain_context, route_task
from .research_report_acceptance import (
    ResearchReportAcceptanceError,
    build_research_report_acceptance,
    synthetic_research_report_fixture,
    validate_research_report_acceptance,
)
from .research_input_gate import (
    ResearchInputGateValidationError,
    preview_research_input,
    preview_research_task_inputs,
    project_research_report_input,
    validate_research_task_inputs,
)
from .automation import AutoAdvanceEngine
from .runtime import ExecutionBroker, RuntimeStore, install_workflow_preset
from .runtime_plan import load_runtime_plan, sync_runtime_plan
from .route_config import load_runtime_routes
from .single_owner_progression import (
    ContractViolation,
    acknowledge_recovery,
    authorize_step,
    claim_owner,
    create_execution_state,
    enqueue_trigger,
    expire_lease,
    record_step_result,
    renew_lease,
    request_human_stop,
    resume_after_human_stop,
    select_ready_task,
    submit_for_review,
)
from .codex_adapter import CodexAppServerAdapter
from .codex_project import CodexProjectAdapter
from .codex_worker import finish_once as finish_codex_dispatch, run_once as run_codex_dispatch_once
from .secretary import build_context_pack, build_secretary_brief
from .task_links import module_work_projection, validate_task_module_link
from .task_envelope import (
    TASK_ENVELOPE_VERSION,
    TASK_ENVELOPE_PREVIEW_VERSION,
    TASK_MODULE_LINK_VERSION,
    preview_task_envelopes,
    validate_task_envelope,
    validate_task_module_link_v1,
)
from .template_selection import TEMPLATE_SELECTION_VERSION, validate_template_selection
from .practice_candidate import PRACTICE_CANDIDATE_VERSION, validate_practice_candidate
from .execution_receipt import EXECUTION_RECEIPT_VERSION, validate_execution_receipt
from .truth import compile_truth
from .workflow import transition_task
from .workflow_structure import compile_workflow_structure, evaluate_workflow_structure
from .work_protocols import load_work_protocols, work_protocol_catalog

__version__ = "0.15.0"

__all__ = [
    "build_capsule",
    "build_continuity_capsule",
    "build_runtime_continuity_capsule",
    "build_acceptance_snapshot",
    "build_research_report_acceptance",
    "AutoAdvanceEngine",
    "build_candidate_plan",
    "build_module_graph",
    "build_context_pack",
    "build_secretary_brief",
    "assign_task",
    "apply_presentation",
    "compile_truth",
    "compile_domain_context",
    "compile_operating_practices",
    "compile_workflow_structure",
    "CodexAppServerAdapter",
    "CodexProjectAdapter",
    "finish_codex_dispatch",
    "ContractViolation",
    "acknowledge_recovery",
    "authorize_step",
    "claim_owner",
    "create_execution_state",
    "enqueue_trigger",
    "evaluate_git_closure",
    "evaluate_workflow_structure",
    "ExecutionBroker",
    "GoalController",
    "freeze_assets",
    "inspect_workspace",
    "install_workflow_preset",
    "load_runtime_plan",
    "load_runtime_routes",
    "load_work_protocols",
    "read_memory_context",
    "request_memory_review",
    "load_goal_definition",
    "load_presentation",
    "module_catalog",
    "module_work_projection",
    "operation_spec",
    "promote_candidate",
    "project_plan",
    "ready_tasks",
    "route_task",
    "record_step_result",
    "renew_lease",
    "request_human_stop",
    "resume_after_human_stop",
    "RuntimeStore",
    "run_codex_dispatch_once",
    "ResearchReportAcceptanceError",
    "ResearchInputGateValidationError",
    "preview_research_input",
    "preview_research_task_inputs",
    "project_research_report_input",
    "select_ready_task",
    "select_execution_route",
    "task_route_requirements",
    "TASK_ENVELOPE_VERSION",
    "TASK_ENVELOPE_PREVIEW_VERSION",
    "TASK_MODULE_LINK_VERSION",
    "TEMPLATE_SELECTION_VERSION",
    "PRACTICE_CANDIDATE_VERSION",
    "EXECUTION_RECEIPT_VERSION",
    "submit_for_review",
    "sync_runtime_plan",
    "synthetic_research_report_fixture",
    "transition_task",
    "validate_plan",
    "validate_memory_candidate",
    "validate_research_report_acceptance",
    "validate_research_task_inputs",
    "validate_task_module_link",
    "validate_task_envelope",
    "validate_task_module_link_v1",
    "preview_task_envelopes",
    "validate_template_selection",
    "validate_practice_candidate",
    "validate_execution_receipt",
    "verify_freeze",
    "expire_lease",
    "get_workflow_preset",
    "workflow_preset_catalog",
    "work_protocol_catalog",
]
