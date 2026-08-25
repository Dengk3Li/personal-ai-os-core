import tempfile
import unittest
from pathlib import Path

from personal_ai_os.automation import AutoAdvanceEngine
from personal_ai_os.runtime import ExecutionBroker, RuntimeStore


class SuccessfulAdapter:
    adapter_id = "test-adapter"

    def __init__(self):
        self.calls = []

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        self.calls.append(task["task_id"])
        return {
            "ok": True,
            "external_run_id": f"external-{task['task_id']}",
            "status": "SUCCEEDED",
            "output_text": f"Result for {task['task_id']}",
        }


class AvailabilityDropsAdapter(SuccessfulAdapter):
    adapter_id = "availability-drops"

    def __init__(self):
        super().__init__()
        self.probes = 0

    def probe(self):
        self.probes += 1
        return {"adapter_id": self.adapter_id, "available": self.probes == 1}


class FailedRunAdapter(SuccessfulAdapter):
    adapter_id = "failed-run"

    def start(self, task, *, model, context_pack):
        self.calls.append(task["task_id"])
        return {
            "ok": True,
            "external_run_id": f"failed-{task['task_id']}",
            "status": "FAILED",
            "reason": "MODEL_FAILED",
        }


class DecisionAdapter(SuccessfulAdapter):
    adapter_id = "decision-adapter"

    def start(self, task, *, model, context_pack):
        self.calls.append(task["task_id"])
        return {
            "ok": True,
            "external_run_id": f"decision-{task['task_id']}",
            "status": "BLOCKED",
            "reason": "PATH_SELECTION_REQUIRED",
            "decision": {
                "question": "Which path should continue?",
                "context": "Both paths are valid.",
                "options": [
                    {"letter": "A", "label": "Fast path"},
                    {"letter": "B", "label": "Thorough path"},
                ],
                "recommended_option": "B",
                "recommendation_reason": "It preserves stronger evidence.",
            },
        }


class NamedAdapter:
    def __init__(self, adapter_id, *, available=True):
        self.adapter_id = adapter_id
        self.available = available
        self.calls = []

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": self.available}

    def start(self, task, *, model, context_pack):
        self.calls.append((task["task_id"], model))
        return {
            "ok": True,
            "external_run_id": f"{self.adapter_id}-{task['task_id']}",
            "status": "SUCCEEDED",
            "output_text": f"Result for {task['task_id']}",
        }


class AutoAdvanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RuntimeStore(Path(self.temp.name) / "runtime.db")
        self.store.create_workflow({
            "workflow_id": "delivery",
            "name": "Delivery",
            "caption": "Parallel work",
            "layout": "branch",
            "goal": "Produce an accepted result",
        })
        self.adapter = SuccessfulAdapter()
        self.engine = AutoAdvanceEngine(
            ExecutionBroker(self.store, {self.adapter.adapter_id: self.adapter}),
            adapter_id=self.adapter.adapter_id,
            model="model-a",
        )

    def tearDown(self):
        self.temp.cleanup()

    def add_task(self, task_id, *, depends_on=None, human_gate=False, **overrides):
        self.store.create_task({
            "task_id": task_id,
            "workflow_id": "delivery",
            "title": task_id,
            "acceptance": "One inspectable result",
            "depends_on": depends_on or [],
            "human_gate": human_gate,
            **overrides,
        })

    @staticmethod
    def runtime_routes():
        return [
            {
                "route": "quick-writing",
                "tier": "quick",
                "capabilities": ["writing"],
                "max_context_tokens": 64000,
                "adapter_id": "quick-adapter",
                "model": "model-quick",
                "enabled": True,
            },
            {
                "route": "standard-research",
                "tier": "standard",
                "capabilities": ["writing", "research"],
                "max_context_tokens": 160000,
                "adapter_id": "standard-adapter",
                "model": "model-standard",
                "enabled": True,
            },
            {
                "route": "deep-research",
                "tier": "deep",
                "capabilities": ["research", "code"],
                "max_context_tokens": 240000,
                "adapter_id": "deep-adapter",
                "model": "model-deep",
                "enabled": True,
            },
        ]

    def routed_engine(self, broker, routes):
        try:
            return AutoAdvanceEngine(broker, routes=routes)
        except TypeError as exc:
            self.fail(f"AutoAdvanceEngine must accept runtime routes: {exc}")

    def test_drain_runs_each_ready_parallel_task_once_and_waits_for_review(self):
        self.add_task("delivery:a")
        self.add_task("delivery:b")
        self.add_task("delivery:join", depends_on=["delivery:a", "delivery:b"])

        result = self.engine.advance(max_steps=10)

        self.assertTrue(result["ok"])
        self.assertEqual("WAITING_REVIEW", result["stop_reason"])
        self.assertEqual(["delivery:a", "delivery:b"], self.adapter.calls)
        self.assertEqual(2, result["advanced_count"])
        self.assertEqual("REVIEW", self.store.get_task("delivery:a")["status"])
        self.assertEqual("REVIEW", self.store.get_task("delivery:b")["status"])
        self.assertEqual("QUEUED", self.store.get_task("delivery:join")["status"])

    def test_routed_drain_selects_a_binding_for_each_task(self):
        self.add_task(
            "delivery:quick",
            complexity="quick",
            required_capabilities=["writing"],
            context={"routing": {"estimated_context_tokens": 12000}},
        )
        self.add_task(
            "delivery:large",
            complexity="quick",
            required_capabilities=["writing"],
            context={"routing": {"estimated_context_tokens": 80000}},
        )
        self.add_task(
            "delivery:deep",
            complexity="deep",
            required_capabilities=["research"],
        )
        adapters = {
            adapter.adapter_id: adapter
            for adapter in (
                NamedAdapter("quick-adapter"),
                NamedAdapter("standard-adapter"),
                NamedAdapter("deep-adapter"),
            )
        }
        engine = self.routed_engine(
            ExecutionBroker(self.store, adapters), self.runtime_routes()
        )

        result = engine.advance(max_steps=10, workflow_id="delivery")

        self.assertTrue(result["ok"])
        self.assertEqual("WAITING_REVIEW", result["stop_reason"])
        self.assertEqual(
            ["quick-writing", "standard-research", "deep-research"],
            [item["route"] for item in result["actions"]],
        )
        self.assertEqual(
            [("delivery:quick", "model-quick")],
            adapters["quick-adapter"].calls,
        )
        self.assertEqual(
            [("delivery:large", "model-standard")],
            adapters["standard-adapter"].calls,
        )
        self.assertEqual(
            [("delivery:deep", "model-deep")],
            adapters["deep-adapter"].calls,
        )
        assignments = self.store.snapshot()["assignments"]
        self.assertEqual("model-standard", assignments["delivery:large"]["model"])
        self.assertEqual(
            "standard-research", assignments["delivery:large"]["route"]
        )
        selected_events = [
            event
            for event in self.store.snapshot()["events"]
            if event["event_type"] == "AUTO_ROUTE_SELECTED"
        ]
        self.assertEqual(3, len(selected_events))

    def test_route_failure_stops_before_claim_and_consumes_the_failure_budget(self):
        self.add_task(
            "delivery:unsupported",
            complexity="deep",
            required_capabilities=["vision"],
        )
        self.add_task("delivery:later")
        adapter = NamedAdapter("quick-adapter")
        engine = self.routed_engine(
            ExecutionBroker(self.store, {adapter.adapter_id: adapter}),
            [self.runtime_routes()[0]],
        )

        result = engine.advance(max_steps=10, failure_budget=1, workflow_id="delivery")

        self.assertFalse(result["ok"])
        self.assertEqual("ROUTE_NOT_FOUND", result["stop_reason"])
        self.assertEqual(1, result["failure_count"])
        self.assertEqual(["delivery:unsupported"], [item["task_id"] for item in result["actions"]])
        self.assertEqual("QUEUED", self.store.get_task("delivery:unsupported")["status"])
        self.assertEqual("QUEUED", self.store.get_task("delivery:later")["status"])
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual([], adapter.calls)

    def test_routed_human_gate_keeps_authority_and_allows_other_ready_work(self):
        self.add_task("delivery:gate", human_gate=True)
        self.add_task("delivery:independent")
        adapter = NamedAdapter("standard-adapter")
        engine = self.routed_engine(
            ExecutionBroker(self.store, {adapter.adapter_id: adapter}),
            [self.runtime_routes()[1]],
        )

        result = engine.advance(max_steps=10, workflow_id="delivery")

        self.assertTrue(result["ok"])
        self.assertEqual("WAITING_DECISION", result["stop_reason"])
        self.assertEqual(0, result["failure_count"])
        self.assertEqual(1, len(self.store.pending_decisions()))
        self.assertEqual([("delivery:independent", "model-standard")], adapter.calls)

    def test_routed_human_gate_precedes_route_availability(self):
        self.add_task("delivery:gate", human_gate=True)
        adapter = NamedAdapter("standard-adapter", available=False)
        engine = self.routed_engine(
            ExecutionBroker(self.store, {adapter.adapter_id: adapter}),
            [self.runtime_routes()[1]],
        )

        result = engine.advance(max_steps=10, workflow_id="delivery")

        self.assertTrue(result["ok"])
        self.assertEqual("WAITING_DECISION", result["stop_reason"])
        self.assertEqual(0, result["failure_count"])
        self.assertEqual(1, len(self.store.pending_decisions()))
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual([], adapter.calls)

    def test_human_gate_creates_one_decision_while_other_ready_work_continues(self):
        self.add_task("delivery:gate", human_gate=True)
        self.add_task("delivery:independent")

        result = self.engine.advance(max_steps=10)

        self.assertEqual("WAITING_DECISION", result["stop_reason"])
        self.assertEqual(["delivery:independent"], self.adapter.calls)
        self.assertEqual(1, len(self.store.pending_decisions()))
        self.assertTrue(result["ok"])
        self.assertEqual(0, result["failure_count"])
        self.assertEqual(
            ["delivery:gate", "delivery:independent"],
            [item["task_id"] for item in result["actions"]],
        )

        again = self.engine.advance(max_steps=10)
        self.assertEqual([], again["actions"])
        self.assertEqual(1, len(self.store.pending_decisions()))

    def test_max_steps_is_a_hard_boundary(self):
        self.add_task("delivery:a")
        self.add_task("delivery:b")

        result = self.engine.advance(max_steps=1)

        self.assertEqual("MAX_STEPS", result["stop_reason"])
        self.assertEqual(1, result["advanced_count"])
        self.assertEqual(1, len(self.adapter.calls))

    def test_workflow_scope_does_not_dispatch_another_line(self):
        self.add_task("delivery:a")
        self.store.create_workflow({
            "workflow_id": "other",
            "name": "Other",
            "caption": "Separate line",
            "layout": "milestones",
            "goal": "Stay isolated",
        })
        self.store.create_task({
            "task_id": "other:a",
            "workflow_id": "other",
            "title": "Other task",
            "acceptance": "One result",
        })

        result = self.engine.advance(max_steps=10, workflow_id="delivery")

        self.assertEqual("delivery", result["workflow_id"])
        self.assertEqual(["delivery:a"], self.adapter.calls)
        self.assertEqual("QUEUED", self.store.get_task("other:a")["status"])

    def test_adapter_failure_is_an_overall_failure_and_respects_the_budget(self):
        self.add_task("delivery:a")
        self.add_task("delivery:b")
        engine = AutoAdvanceEngine(
            ExecutionBroker(self.store, {}),
            adapter_id="missing-adapter",
            model="model-a",
        )

        result = engine.advance(max_steps=10, failure_budget=1)

        self.assertFalse(result["ok"])
        self.assertEqual("ADAPTER_NOT_FOUND", result["stop_reason"])
        self.assertEqual(1, result["failure_count"])
        self.assertEqual(1, len(result["actions"]))
        self.assertEqual("QUEUED", self.store.get_task("delivery:b")["status"])

    def test_a_late_adapter_failure_is_not_hidden_by_an_earlier_review(self):
        self.add_task("delivery:a")
        self.add_task("delivery:b")
        adapter = AvailabilityDropsAdapter()
        engine = AutoAdvanceEngine(
            ExecutionBroker(self.store, {adapter.adapter_id: adapter}),
            adapter_id=adapter.adapter_id,
            model="model-a",
        )

        result = engine.advance(max_steps=10, failure_budget=1)

        self.assertFalse(result["ok"])
        self.assertEqual("ADAPTER_UNAVAILABLE", result["stop_reason"])
        self.assertEqual(1, result["advanced_count"])
        self.assertEqual(1, result["failure_count"])

    def test_failed_external_run_consumes_the_failure_budget(self):
        self.add_task("delivery:a")
        self.add_task("delivery:b")
        self.add_task("delivery:c")
        adapter = FailedRunAdapter()
        engine = AutoAdvanceEngine(
            ExecutionBroker(self.store, {adapter.adapter_id: adapter}),
            adapter_id=adapter.adapter_id,
            model="model-a",
        )

        result = engine.advance(max_steps=10, failure_budget=1)

        self.assertFalse(result["ok"])
        self.assertEqual("MODEL_FAILED", result["stop_reason"])
        self.assertEqual(0, result["advanced_count"])
        self.assertEqual(1, result["failure_count"])
        self.assertEqual(["delivery:a"], adapter.calls)
        self.assertEqual("QUEUED", self.store.get_task("delivery:b")["status"])

    def test_adapter_decision_stops_at_the_human_gate_without_spending_failure_budget(self):
        self.add_task("delivery:a")
        adapter = DecisionAdapter()
        engine = AutoAdvanceEngine(
            ExecutionBroker(self.store, {adapter.adapter_id: adapter}),
            adapter_id=adapter.adapter_id,
            model="model-a",
        )

        result = engine.advance(max_steps=10, failure_budget=1)

        self.assertTrue(result["ok"])
        self.assertEqual("WAITING_DECISION", result["stop_reason"])
        self.assertEqual(0, result["failure_count"])
        self.assertEqual("HUMAN_DECISION_REQUIRED", result["actions"][0]["outcome"])
        self.assertEqual(1, len(self.store.pending_decisions()))

    def test_empty_runtime_is_idle(self):
        result = self.engine.advance(max_steps=3)

        self.assertTrue(result["ok"])
        self.assertEqual("IDLE", result["stop_reason"])
        self.assertEqual([], result["actions"])

    def test_persisted_running_run_after_restart_requires_recovery(self):
        self.add_task("delivery:interrupted")
        self.store.claim_run(
            task_id="delivery:interrupted",
            adapter_id=self.adapter.adapter_id,
            model="model-a",
            by="adapter:test-adapter",
        )
        reopened_store = RuntimeStore(self.store.database)
        reopened_adapter = SuccessfulAdapter()
        reopened_engine = AutoAdvanceEngine(
            ExecutionBroker(reopened_store, {reopened_adapter.adapter_id: reopened_adapter}),
            adapter_id=reopened_adapter.adapter_id,
            model="model-a",
        )

        result = reopened_engine.advance(max_steps=3)

        self.assertEqual("RECOVERY_REQUIRED", result["stop_reason"])
        self.assertEqual([], result["actions"])
        self.assertEqual([], reopened_adapter.calls)


if __name__ == "__main__":
    unittest.main()
