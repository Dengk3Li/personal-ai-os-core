"""Public core primitives for an authority-aware personal AI control plane."""

from .continuity import build_capsule
from .dispatching import assign_task, select_execution_route
from .freeze import freeze_assets, verify_freeze
from .git_closure import evaluate_git_closure
from .intake import build_candidate_plan, inspect_workspace
from .modules import build_module_graph, module_catalog
from .operations import operation_spec
from .promotion import promote_candidate
from .planning import project_plan, ready_tasks, validate_plan
from .presentation import apply_presentation, load_presentation
from .presets import get_workflow_preset, workflow_preset_catalog
from .routing import compile_domain_context, route_task
from .automation import AutoAdvanceEngine
from .runtime import ExecutionBroker, RuntimeStore, install_workflow_preset
from .runtime_plan import load_runtime_plan, sync_runtime_plan
from .route_config import load_runtime_routes
from .secretary import build_context_pack, build_secretary_brief
from .truth import compile_truth
from .workflow import transition_task
from .workflow_structure import compile_workflow_structure, evaluate_workflow_structure

__version__ = "0.11.0"

__all__ = [
    "build_capsule",
    "AutoAdvanceEngine",
    "build_candidate_plan",
    "build_module_graph",
    "build_context_pack",
    "build_secretary_brief",
    "assign_task",
    "apply_presentation",
    "compile_truth",
    "compile_domain_context",
    "compile_workflow_structure",
    "evaluate_git_closure",
    "evaluate_workflow_structure",
    "ExecutionBroker",
    "freeze_assets",
    "inspect_workspace",
    "install_workflow_preset",
    "load_runtime_plan",
    "load_runtime_routes",
    "load_presentation",
    "module_catalog",
    "operation_spec",
    "promote_candidate",
    "project_plan",
    "ready_tasks",
    "route_task",
    "RuntimeStore",
    "select_execution_route",
    "sync_runtime_plan",
    "transition_task",
    "validate_plan",
    "verify_freeze",
    "get_workflow_preset",
    "workflow_preset_catalog",
]
