from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .automation import AutoAdvanceEngine, TERMINAL_DEPENDENCY_STATES
from .runtime import ExecutionBroker


GOAL_SCHEMA = "personal-ai-os.goal/v1"


def load_goal_definition(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != GOAL_SCHEMA:
        raise ValueError("unsupported goal schema")
    allowed = {
        "schema_version",
        "goal_id",
        "title",
        "objective",
        "workflow_ids",
        "completion_criteria",
        "continuation_policy",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown goal fields: {sorted(unknown)}")
    for field, limit in (
        ("goal_id", 200),
        ("title", 300),
        ("objective", 4000),
        ("completion_criteria", 4000),
    ):
        text = str(value.get(field) or "").strip()
        if not text or len(text) > limit:
            raise ValueError(f"{field} must contain at most {limit} characters")
    workflows = value.get("workflow_ids")
    if not isinstance(workflows, list) or not 1 <= len(workflows) <= 100:
        raise ValueError("workflow_ids must contain between 1 and 100 items")
    return {key: item for key, item in value.items() if key != "schema_version"}


class GoalController:
    """Continue a durable goal through the existing bounded execution gates."""

    def __init__(
        self,
        broker: ExecutionBroker,
        *,
        adapter_id: str | None = None,
        model: str | None = None,
        routes: list[dict[str, Any]] | None = None,
        requested_route: str | None = None,
    ):
        self.broker = broker
        self.store = broker.store
        self.adapter_id = str(adapter_id or "").strip()
        self.model = str(model or "").strip()
        self.routes = [dict(route) for route in routes] if routes is not None else None
        self.requested_route = str(requested_route or "").strip() or None

    def _engine(self) -> AutoAdvanceEngine:
        return AutoAdvanceEngine(
            self.broker,
            adapter_id=self.adapter_id,
            model=self.model,
            routes=self.routes,
            requested_route=self.requested_route,
        )

    @staticmethod
    def _token_usage(runs: list[dict[str, Any]]) -> int:
        total = 0
        for run in runs:
            usage = run.get("usage") or {}
            values = []
            for primary, compatible in (
                ("input_tokens", "prompt_tokens"),
                ("output_tokens", "completion_tokens"),
            ):
                value = usage.get(primary, usage.get(compatible, 0))
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    values.append(value)
            if values:
                total += sum(values)
            else:
                value = usage.get("total_tokens", 0)
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    total += value
        return total

    def _goal_snapshot(self, goal: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.store.snapshot()
        workflow_ids = set(goal["workflow_ids"])
        tasks = [
            task for task in snapshot["tasks"] if task["workflow_id"] in workflow_ids
        ]
        task_ids = {task["task_id"] for task in tasks}
        return {
            **snapshot,
            "tasks": tasks,
            "runs": [run for run in snapshot["runs"] if run["task_id"] in task_ids],
            "decisions": [
                item for item in snapshot["decisions"] if item["task_id"] in task_ids
            ],
        }

    @staticmethod
    def _stop_reason(snapshot: dict[str, Any], actions: list[dict[str, Any]]) -> str:
        if any(item.get("failure") for item in actions):
            return next(
                str(item["outcome"])
                for item in reversed(actions)
                if item.get("failure")
            )
        if any(item["status"] == "PENDING" for item in snapshot["decisions"]):
            return "WAITING_DECISION"
        states = {task["status"] for task in snapshot["tasks"]}
        if snapshot["tasks"] and states.issubset(TERMINAL_DEPENDENCY_STATES):
            return "GOAL_AWAITING_ACCEPTANCE"
        if "REVIEW" in states:
            return "WAITING_REVIEW"
        if "IN_PROGRESS" in states:
            return "RECOVERY_REQUIRED"
        if "BLOCKED" in states:
            return "BLOCKED"
        if "PAUSED" in states:
            return "PAUSED"
        if "QUEUED" in states:
            return "WAITING_DEPENDENCY"
        return "IDLE"

    @staticmethod
    def _blocked(reason: str, goal: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "personal-ai-os.goal-continuation/v1",
            "ok": False,
            "goal_id": goal["goal_id"],
            "status": goal["status"],
            "reason": reason,
            "stop_reason": reason,
            "steps_used": 0,
            "tokens_used": 0,
            "actions": [],
        }

    def continue_goal(self, goal_id: str) -> dict[str, Any]:
        initial_goal = self.store.get_goal(goal_id)
        initial_stop = self._stop_reason(self._goal_snapshot(initial_goal), [])
        if (
            initial_stop not in {"GOAL_AWAITING_ACCEPTANCE", "RECOVERY_REQUIRED"}
            and self.routes is None
            and (not self.adapter_id or not self.model)
        ):
            return self._blocked(
                "GOAL_EXECUTION_NOT_CONFIGURED", initial_goal
            )
        claim = self.store.claim_goal_continuation(goal_id)
        goal = claim["goal"]
        if not claim["ok"]:
            reason = str(claim["reason"])
            if reason == "GOAL_ALREADY_CONTINUING":
                reason = "GOAL_RECOVERY_REQUIRED"
            return self._blocked(reason, goal)

        continuation_id = claim["continuation_id"]
        policy = goal["continuation_policy"]
        usage = goal["usage"]
        before = self._goal_snapshot(goal)
        preflight_stop = self._stop_reason(before, [])
        if preflight_stop in {"GOAL_AWAITING_ACCEPTANCE", "RECOVERY_REQUIRED"}:
            status = (
                "AWAITING_ACCEPTANCE"
                if preflight_stop == "GOAL_AWAITING_ACCEPTANCE"
                else "RECOVERY_REQUIRED"
            )
            updated = self.store.finish_goal_continuation(
                goal_id,
                continuation_id,
                steps=0,
                tokens=0,
                stop_reason=preflight_stop,
                status=status,
            )
            return {
                "schema_version": "personal-ai-os.goal-continuation/v1",
                "ok": preflight_stop == "GOAL_AWAITING_ACCEPTANCE",
                "goal_id": goal_id,
                "status": updated["status"],
                "steps_used": 0,
                "tokens_used": 0,
                "failure_count": 0,
                "actions": [],
                "stop_reason": preflight_stop,
                **(
                    {"reason": preflight_stop}
                    if preflight_stop == "RECOVERY_REQUIRED"
                    else {}
                ),
            }
        remaining_steps = policy["max_total_steps"] - usage["steps_used"]
        remaining_tokens = policy["max_total_tokens"] - usage["tokens_used"]
        if remaining_steps <= 0 or remaining_tokens <= 0:
            updated = self.store.finish_goal_continuation(
                goal_id,
                continuation_id,
                steps=0,
                tokens=0,
                stop_reason="GOAL_BUDGET_LIMITED",
                status="BUDGET_LIMITED",
            )
            return self._blocked("GOAL_BUDGET_LIMITED", updated)

        before_run_ids = {run["run_id"] for run in before["runs"]}
        max_steps = min(policy["max_steps_per_continuation"], remaining_steps)
        failure_budget = policy["failure_budget_per_continuation"]
        actions: list[dict[str, Any]] = []
        failure_count = 0
        engine = self._engine()
        for workflow_id in goal["workflow_ids"]:
            steps_left = max_steps - len(actions)
            failures_left = failure_budget - failure_count
            if steps_left <= 0 or failures_left <= 0:
                break
            result = engine.advance(
                max_steps=steps_left,
                failure_budget=failures_left,
                workflow_id=workflow_id,
            )
            actions.extend(result["actions"])
            failure_count += result["failure_count"]

        after = self._goal_snapshot(goal)
        new_runs = [run for run in after["runs"] if run["run_id"] not in before_run_ids]
        tokens = self._token_usage(new_runs)
        stop_reason = self._stop_reason(after, actions)
        total_steps = usage["steps_used"] + len(actions)
        total_tokens = usage["tokens_used"] + tokens
        if stop_reason == "GOAL_AWAITING_ACCEPTANCE":
            next_status = "AWAITING_ACCEPTANCE"
        elif stop_reason == "RECOVERY_REQUIRED":
            next_status = "RECOVERY_REQUIRED"
        elif (
            total_steps >= policy["max_total_steps"]
            or total_tokens >= policy["max_total_tokens"]
        ):
            next_status = "BUDGET_LIMITED"
        else:
            next_status = "ACTIVE"
        updated = self.store.finish_goal_continuation(
            goal_id,
            continuation_id,
            steps=len(actions),
            tokens=tokens,
            stop_reason=stop_reason,
            status=next_status,
        )
        return {
            "schema_version": "personal-ai-os.goal-continuation/v1",
            "ok": failure_count == 0,
            "goal_id": goal_id,
            "status": updated["status"],
            "steps_used": len(actions),
            "tokens_used": tokens,
            "failure_count": failure_count,
            "actions": actions,
            "stop_reason": stop_reason,
            **({"reason": stop_reason} if failure_count else {}),
        }
