from __future__ import annotations

from typing import Any

from .runtime import ExecutionBroker


TERMINAL_DEPENDENCY_STATES = {"DONE", "ARCHIVED"}
NON_FATAL_OUTCOMES = {
    "HUMAN_DECISION_REQUIRED",
    "STATE_CHANGED_RETRY",
    "TASK_ALREADY_DISPATCHING",
    "TASK_NOT_QUEUED",
}


class AutoAdvanceEngine:
    """Boundedly dispatch ready tasks without crossing human authority gates."""

    def __init__(
        self,
        broker: ExecutionBroker,
        *,
        adapter_id: str,
        model: str,
    ):
        self.broker = broker
        self.store = broker.store
        self.adapter_id = str(adapter_id or "").strip()
        self.model = str(model or "").strip()

    @staticmethod
    def _scoped(snapshot: dict[str, Any], workflow_id: str | None) -> dict[str, Any]:
        if workflow_id is None:
            return snapshot
        tasks = [task for task in snapshot["tasks"] if task["workflow_id"] == workflow_id]
        task_ids = {task["task_id"] for task in tasks}
        return {
            **snapshot,
            "tasks": tasks,
            "runs": [run for run in snapshot["runs"] if run["task_id"] in task_ids],
            "decisions": [
                decision for decision in snapshot["decisions"] if decision["task_id"] in task_ids
            ],
        }

    def _candidate(
        self,
        attempted: set[str],
        workflow_id: str | None,
    ) -> dict[str, Any] | None:
        snapshot = self._scoped(self.store.snapshot(), workflow_id)
        states = {task["task_id"]: task["status"] for task in snapshot["tasks"]}
        pending = {
            decision["task_id"]
            for decision in snapshot["decisions"]
            if decision["status"] == "PENDING"
        }
        for task in snapshot["tasks"]:
            if task["task_id"] in attempted or task["status"] != "QUEUED":
                continue
            if task["task_id"] in pending:
                continue
            if all(states.get(item) in TERMINAL_DEPENDENCY_STATES for item in task["depends_on"]):
                return task
        return None

    def _stop_reason(
        self,
        *,
        attempted: set[str],
        hit_limit: bool,
        actions: list[dict[str, Any]],
        failure_count: int,
        workflow_id: str | None,
    ) -> str:
        snapshot = self._scoped(self.store.snapshot(), workflow_id)
        if failure_count:
            return next(item["outcome"] for item in reversed(actions) if item["failure"])
        if hit_limit and self._candidate(attempted, workflow_id) is not None:
            return "MAX_STEPS"
        if any(item["status"] == "PENDING" for item in snapshot["decisions"]):
            return "WAITING_DECISION"
        states = {task["status"] for task in snapshot["tasks"]}
        if "REVIEW" in states:
            return "WAITING_REVIEW"
        if "IN_PROGRESS" in states:
            return "RECOVERY_REQUIRED"
        if "BLOCKED" in states:
            return "BLOCKED"
        if any(task["status"] == "QUEUED" for task in snapshot["tasks"]):
            return "WAITING_DEPENDENCY"
        if snapshot["tasks"] and states.issubset(TERMINAL_DEPENDENCY_STATES | {"PAUSED"}):
            return "COMPLETE" if states.issubset(TERMINAL_DEPENDENCY_STATES) else "PAUSED"
        return "IDLE"

    def advance(
        self,
        *,
        max_steps: int = 25,
        failure_budget: int = 1,
        workflow_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.adapter_id:
            raise ValueError("adapter_id is required")
        if not self.model:
            raise ValueError("model is required")
        if not isinstance(max_steps, int) or not 1 <= max_steps <= 100:
            raise ValueError("max_steps must be between 1 and 100")
        if not isinstance(failure_budget, int) or not 1 <= failure_budget <= 20:
            raise ValueError("failure_budget must be between 1 and 20")
        if workflow_id is not None:
            workflow_id = str(workflow_id).strip()
            if not workflow_id or workflow_id not in {
                workflow["workflow_id"] for workflow in self.store.snapshot()["workflows"]
            }:
                raise ValueError("workflow_id is not registered")

        attempted: set[str] = set()
        actions: list[dict[str, Any]] = []
        advanced_count = 0
        failure_count = 0
        for _ in range(max_steps):
            task = self._candidate(attempted, workflow_id)
            if task is None:
                break
            task_id = task["task_id"]
            attempted.add(task_id)
            self.store.record_task_event(
                task_id,
                "AUTO_ADVANCE_SELECTED",
                {"adapter_id": self.adapter_id, "model": self.model},
            )
            result = self.broker.dispatch(
                task_id,
                adapter_id=self.adapter_id,
                model=self.model,
            )
            outcome = str(result.get("reason") or result.get("status") or "UNKNOWN")
            failure = not result.get("ok") and outcome not in NON_FATAL_OUTCOMES
            self.store.record_task_event(
                task_id,
                "AUTO_ADVANCE_FINISHED",
                {"outcome": outcome},
                run_id=(result.get("run") or {}).get("run_id"),
            )
            actions.append(
                {
                    "task_id": task_id,
                    "ok": bool(result.get("ok")),
                    "outcome": outcome,
                    "failure": failure,
                }
            )
            if result.get("ok"):
                advanced_count += 1
            if failure:
                failure_count += 1
                if failure_count >= failure_budget:
                    break

        hit_limit = len(actions) == max_steps
        stop_reason = self._stop_reason(
            attempted=attempted,
            hit_limit=hit_limit,
            actions=actions,
            failure_count=failure_count,
            workflow_id=workflow_id,
        )
        return {
            "schema_version": "personal-ai-os.auto-advance/v1",
            "ok": failure_count == 0,
            "workflow_id": workflow_id,
            "advanced_count": advanced_count,
            "failure_count": failure_count,
            "actions": actions,
            "stop_reason": stop_reason,
            **({"reason": stop_reason} if failure_count else {}),
        }
