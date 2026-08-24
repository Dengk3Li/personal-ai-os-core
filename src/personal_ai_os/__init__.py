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
from .routing import route_task
from .truth import compile_truth
from .workflow import transition_task

__version__ = "0.5.0"

__all__ = [
    "build_capsule",
    "build_candidate_plan",
    "build_module_graph",
    "assign_task",
    "compile_truth",
    "evaluate_git_closure",
    "freeze_assets",
    "inspect_workspace",
    "module_catalog",
    "operation_spec",
    "promote_candidate",
    "project_plan",
    "ready_tasks",
    "route_task",
    "select_execution_route",
    "transition_task",
    "validate_plan",
    "verify_freeze",
]
