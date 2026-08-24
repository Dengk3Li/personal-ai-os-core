"""Public core primitives for an authority-aware personal AI control plane."""

from .continuity import build_capsule
from .freeze import freeze_assets, verify_freeze
from .git_closure import evaluate_git_closure
from .promotion import promote_candidate
from .routing import route_task
from .truth import compile_truth
from .workflow import transition_task

__version__ = "0.1.0"

__all__ = [
    "build_capsule",
    "compile_truth",
    "evaluate_git_closure",
    "freeze_assets",
    "promote_candidate",
    "route_task",
    "transition_task",
    "verify_freeze",
]
