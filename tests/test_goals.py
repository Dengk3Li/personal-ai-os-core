import tempfile
import threading
import unittest
from pathlib import Path

from personal_ai_os.goals import GoalController, load_goal_definition
from personal_ai_os.runtime import ExecutionBroker, RuntimeStore


class SuccessfulAdapter:
    adapter_id = "goal-adapter"

    def __init__(self):
        self.calls = []

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        self.calls.append(task["task_id"])
        return {
            "ok": True,
            "external_run_id": f"goal-run-{len(self.calls)}",
            "status": "SUCCEEDED",
            "output_text": f"Result for {task['task_id']}",
            "usage": {"input_tokens": 80, "output_tokens": 20},
        }


class SlowAdapter(SuccessfulAdapter):
    adapter_id = "slow-goal-adapter"

    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def start(self, task, *, model, context_pack):
        self.started.set()
        self.release.wait(timeout=2)
        return super().start(task, model=model, context_pack=context_pack)


class ChatUsageAdapter(SuccessfulAdapter):
    def start(self, task, *, model, context_pack):
        receipt = super().start(task, model=model, context_pack=context_pack)
        receipt["usage"] = {"prompt_tokens": 80, "completion_tokens": 20}
        return receipt


class RunningAdapter(SuccessfulAdapter):
    def start(self, task, *, model, context_pack):
        self.calls.append(task["task_id"])
        return {
            "ok": True,
            "external_run_id": "still-running",
            "status": "RUNNING",
        }


class DurableGoalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "runtime.db"
        self.store = RuntimeStore(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def add_workflow(self, workflow_id, task_ids):
        self.store.create_workflow(
            {
                "workflow_id": workflow_id,
                "name": workflow_id,
                "goal": f"Workline goal for {workflow_id}",
                "domain_id": "engineering",
            }
        )
        for task_id in task_ids:
            self.store.create_task(
                {
                    "task_id": task_id,
                    "workflow_id": workflow_id,
                    "line_id": workflow_id,
                    "title": task_id,
                    "acceptance": "One inspectable result",
                    "depends_on": [],
                }
            )

    def create_goal(self, workflow_ids, **policy):
        return self.store.create_goal(
            {
                "goal_id": "goal:release",
                "title": "Ship one accepted release",
                "objective": "Advance the registered work without confusing budget limits with success.",
                "workflow_ids": workflow_ids,
                "completion_criteria": "Every scoped task is accepted by the owner.",
                "continuation_policy": {
                    "max_steps_per_continuation": 2,
                    "max_total_steps": 4,
                    "max_total_tokens": 500,
                    "failure_budget_per_continuation": 1,
                    **policy,
                },
            }
        )

    def controller(self, adapter=None, store=None):
        adapter = adapter or SuccessfulAdapter()
        store = store or self.store
        return GoalController(
            ExecutionBroker(store, {adapter.adapter_id: adapter}),
            adapter_id=adapter.adapter_id,
            model="model-a",
        ), adapter

    def test_goal_is_persisted_separately_from_workline_copy(self):
        self.add_workflow("line-a", ["line-a:one"])
        created = self.create_goal(["line-a"])

        reopened = RuntimeStore(self.database)
        snapshot = reopened.snapshot()

        self.assertEqual("ACTIVE", created["status"])
        self.assertEqual(["line-a"], created["workflow_ids"])
        self.assertEqual(0, created["usage"]["steps_used"])
        self.assertEqual("Workline goal for line-a", snapshot["workflows"][0]["goal"])
        self.assertEqual("Ship one accepted release", snapshot["goals"][0]["title"])
        self.assertEqual("GOAL_CREATED", snapshot["goal_events"][0]["event_type"])

    def test_goal_rejects_unknown_workflows_without_partial_state(self):
        with self.assertRaisesRegex(ValueError, "workflow"):
            self.create_goal(["missing-line"])

        self.assertEqual([], self.store.snapshot()["goals"])
        self.assertEqual([], self.store.snapshot()["goal_events"])

    def test_continuation_spans_registered_worklines_and_persists_usage(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.add_workflow("line-b", ["line-b:one"])
        self.create_goal(["line-a", "line-b"])
        controller, adapter = self.controller()

        result = controller.continue_goal("goal:release")
        reopened = RuntimeStore(self.database)
        goal = reopened.get_goal("goal:release")

        self.assertTrue(result["ok"])
        self.assertEqual(["line-a:one", "line-b:one"], adapter.calls)
        self.assertEqual(2, result["steps_used"])
        self.assertEqual(200, result["tokens_used"])
        self.assertEqual("ACTIVE", goal["status"])
        self.assertEqual(1, goal["usage"]["continuation_count"])
        self.assertEqual(2, goal["usage"]["steps_used"])
        self.assertEqual(200, goal["usage"]["tokens_used"])
        self.assertEqual("WAITING_REVIEW", goal["usage"]["last_stop_reason"])

    def test_budget_exhaustion_is_budget_limited_not_complete(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"], max_total_steps=1)
        controller, _ = self.controller()

        first = controller.continue_goal("goal:release")
        second = controller.continue_goal("goal:release")
        goal = self.store.get_goal("goal:release")

        self.assertEqual("WAITING_REVIEW", first["stop_reason"])
        self.assertFalse(second["ok"])
        self.assertEqual("GOAL_BUDGET_LIMITED", second["reason"])
        self.assertEqual("BUDGET_LIMITED", goal["status"])
        self.assertIsNone(goal["completed_at"])

    def test_chat_completions_usage_is_counted_and_overrun_limits_immediately(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"], max_total_tokens=50)
        controller, _ = self.controller(ChatUsageAdapter())

        result = controller.continue_goal("goal:release")
        goal = self.store.get_goal("goal:release")

        self.assertEqual(100, result["tokens_used"])
        self.assertEqual(100, goal["usage"]["tokens_used"])
        self.assertEqual("BUDGET_LIMITED", goal["status"])

    def test_terminal_scope_reaches_acceptance_even_when_budget_is_exhausted(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"], max_total_steps=1)
        controller, _ = self.controller()

        controller.continue_goal("goal:release")
        self.store.transition("line-a:one", "DONE", by="owner", reason="Accepted")
        verification_only = GoalController(
            ExecutionBroker(self.store, {}), adapter_id="", model=""
        )
        waiting = verification_only.continue_goal("goal:release")

        self.assertEqual("GOAL_AWAITING_ACCEPTANCE", waiting["stop_reason"])
        self.assertEqual(
            "AWAITING_ACCEPTANCE", self.store.get_goal("goal:release")["status"]
        )

    def test_terminal_tasks_wait_for_explicit_goal_acceptance(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"])
        controller, _ = self.controller()

        controller.continue_goal("goal:release")
        self.store.transition("line-a:one", "DONE", by="owner", reason="Accepted")
        waiting = controller.continue_goal("goal:release")
        before = self.store.get_goal("goal:release")
        completed = self.store.complete_goal(
            "goal:release", by="owner", evidence="All scoped results were reviewed."
        )

        self.assertEqual("GOAL_AWAITING_ACCEPTANCE", waiting["stop_reason"])
        self.assertEqual("AWAITING_ACCEPTANCE", before["status"])
        self.assertEqual("COMPLETE", completed["status"])
        self.assertIsNotNone(completed["completed_at"])

    def test_completion_rechecks_the_scope_after_acceptance_was_requested(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"])
        controller, _ = self.controller()
        controller.continue_goal("goal:release")
        self.store.transition("line-a:one", "DONE", by="owner", reason="Accepted")
        controller.continue_goal("goal:release")
        self.store.create_task(
            {
                "task_id": "line-a:new",
                "workflow_id": "line-a",
                "title": "New scoped task",
                "acceptance": "One accepted output",
            }
        )

        with self.assertRaisesRegex(ValueError, "scope changed"):
            self.store.complete_goal(
                "goal:release", by="owner", evidence="Earlier work was reviewed."
            )

        self.assertEqual(
            "AWAITING_ACCEPTANCE", self.store.get_goal("goal:release")["status"]
        )

    def test_paused_goal_never_dispatches_until_resumed(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"])
        self.store.pause_goal("goal:release", by="owner", reason="Wait for input")
        controller, adapter = self.controller()

        paused = controller.continue_goal("goal:release")
        self.store.resume_goal("goal:release", by="owner")
        resumed = controller.continue_goal("goal:release")

        self.assertEqual("GOAL_PAUSED", paused["reason"])
        self.assertEqual([], paused["actions"])
        self.assertEqual(["line-a:one"], adapter.calls)
        self.assertTrue(resumed["ok"])

    def test_two_runtime_instances_claim_one_goal_continuation(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"])
        slow = SlowAdapter()
        first_store = RuntimeStore(self.database)
        second_store = RuntimeStore(self.database)
        first, _ = self.controller(slow, first_store)
        second, _ = self.controller(slow, second_store)
        results = []

        thread = threading.Thread(
            target=lambda: results.append(first.continue_goal("goal:release"))
        )
        thread.start()
        self.assertTrue(slow.started.wait(timeout=1))
        competing = second.continue_goal("goal:release")
        slow.release.set()
        thread.join(timeout=2)

        self.assertEqual("GOAL_RECOVERY_REQUIRED", competing["reason"])
        self.assertEqual(1, len(slow.calls))
        self.assertEqual(1, len(results))

    def test_goal_definition_loader_requires_a_versioned_bounded_contract(self):
        goal_file = Path(self.temp.name) / "goal.json"
        goal_file.write_text(
            '{"schema_version":"personal-ai-os.goal/v1","goal_id":"goal:release",'
            '"title":"Release","objective":"Produce one accepted release",'
            '"workflow_ids":["line-a"],"completion_criteria":"Owner accepts all results",'
            '"continuation_policy":{"max_total_steps":10}}',
            encoding="utf-8",
        )

        loaded = load_goal_definition(goal_file)

        self.assertNotIn("schema_version", loaded)
        self.assertEqual("goal:release", loaded["goal_id"])
        self.assertEqual(10, loaded["continuation_policy"]["max_total_steps"])

    def test_reopened_store_fails_closed_on_an_unfinished_continuation(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"])
        claim = self.store.claim_goal_continuation("goal:release")
        reopened = RuntimeStore(self.database)
        controller, adapter = self.controller(store=reopened)

        result = controller.continue_goal("goal:release")

        self.assertTrue(claim["ok"])
        self.assertEqual("GOAL_RECOVERY_REQUIRED", result["reason"])
        self.assertEqual([], adapter.calls)

    def test_invalid_execution_configuration_does_not_claim_the_goal(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"])
        adapter = SuccessfulAdapter()
        controller = GoalController(
            ExecutionBroker(self.store, {adapter.adapter_id: adapter}),
            adapter_id=adapter.adapter_id,
            model="",
        )

        result = controller.continue_goal("goal:release")
        goal = self.store.get_goal("goal:release")

        self.assertEqual("GOAL_EXECUTION_NOT_CONFIGURED", result["reason"])
        self.assertEqual("", goal["active_continuation_id"])
        self.assertEqual([], adapter.calls)

    def test_external_running_receipt_persists_a_recovery_gate(self):
        self.add_workflow("line-a", ["line-a:one"])
        self.create_goal(["line-a"])
        controller, adapter = self.controller(RunningAdapter())

        result = controller.continue_goal("goal:release")
        goal = self.store.get_goal("goal:release")

        self.assertEqual(["line-a:one"], adapter.calls)
        self.assertEqual("RECOVERY_REQUIRED", result["stop_reason"])
        self.assertEqual("RECOVERY_REQUIRED", goal["status"])
        self.assertEqual("", goal["active_continuation_id"])


if __name__ == "__main__":
    unittest.main()
