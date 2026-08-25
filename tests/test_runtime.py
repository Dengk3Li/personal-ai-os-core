import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from personal_ai_os.adapters import OpenAICompatibleAdapter
from personal_ai_os.presets import get_workflow_preset
from personal_ai_os.runtime import ExecutionBroker, RuntimeStore, install_workflow_preset
from personal_ai_os.secretary import build_context_pack, build_secretary_brief


class SuccessfulAdapter:
    adapter_id = "test-adapter"

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        return {
            "ok": True,
            "external_run_id": "external-run-1",
            "status": "SUCCEEDED",
            "output_text": "A bounded result with evidence references.",
            "usage": {"input_tokens": 120, "output_tokens": 40},
        }


class MissingIdentityAdapter(SuccessfulAdapter):
    adapter_id = "missing-identity"

    def start(self, task, *, model, context_pack):
        return {"ok": True, "status": "RUNNING"}


class BlockedAdapter(SuccessfulAdapter):
    adapter_id = "blocked-adapter"

    def start(self, task, *, model, context_pack):
        return {
            "ok": True,
            "external_run_id": "external-run-blocked",
            "status": "BLOCKED",
            "error": "The next path needs a human choice.",
            "decision": {
                "question": "Which path should continue?",
                "context": "Both paths are valid but have different costs.",
                "options": [
                    {"letter": "A", "label": "Fast path"},
                    {"letter": "B", "label": "Thorough path"},
                ],
                "recommended_option": "B",
                "recommendation_reason": "It preserves stronger evidence.",
            },
        }


class SlowAdapter(SuccessfulAdapter):
    adapter_id = "slow-adapter"

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def start(self, task, *, model, context_pack):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
        return super().start(task, model=model, context_pack=context_pack)


class CaptureAdapter(SuccessfulAdapter):
    adapter_id = "capture-adapter"

    def __init__(self):
        self.context_packs = []

    def start(self, task, *, model, context_pack):
        self.context_packs.append(context_pack)
        receipt = super().start(task, model=model, context_pack=context_pack)
        receipt["external_run_id"] = f"capture-run-{len(self.context_packs)}"
        return receipt


class RaisingAdapter(SuccessfulAdapter):
    adapter_id = "raising-adapter"

    def start(self, task, *, model, context_pack):
        raise RuntimeError("token=SENSITIVE_SENTINEL https://private.invalid/run")


class RuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "runtime.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_science_preset_is_persistent_and_supports_parallel_paths(self):
        store = RuntimeStore(self.database)
        installed = install_workflow_preset(store, "science")
        reopened = RuntimeStore(self.database)
        snapshot = reopened.snapshot()

        self.assertEqual("science", installed["workflow_id"])
        self.assertEqual(7, len(snapshot["tasks"]))
        self.assertEqual(
            [
                "science:hypothesis",
                "science:protocol-a",
                "science:protocol-b",
                "science:experiment-a",
                "science:experiment-b",
                "science:analysis",
                "science:feedback",
            ],
            [task["task_id"] for task in snapshot["tasks"]],
        )
        self.assertEqual(
            {
                "科学假设角色",
                "实验方案设计角色",
                "自主实验执行角色",
                "数据分析角色",
                "反馈优化角色",
            },
            {task["agent_role"] for task in snapshot["tasks"]},
        )
        self.assertEqual("科研工作线", snapshot["workflows"][0]["name"])
        analysis = next(task for task in snapshot["tasks"] if task["task_id"] == "science:analysis")
        self.assertEqual(
            ["science:experiment-a", "science:experiment-b"],
            analysis["depends_on"],
        )
        self.assertEqual("READY", reopened.integrity()["status"])

    def test_successful_dispatch_persists_run_artifact_trace_and_resume_context(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        broker = ExecutionBroker(store, {"test-adapter": SuccessfulAdapter()})

        result = broker.dispatch(
            "science:hypothesis", adapter_id="test-adapter", model="model-a"
        )
        snapshot = RuntimeStore(self.database).snapshot()
        task = next(item for item in snapshot["tasks"] if item["task_id"] == "science:hypothesis")
        brief = build_secretary_brief(snapshot)
        context_pack = build_context_pack(
            task,
            {
                "domain_id": "science",
                "persona": "evidence-first",
                "memory_refs": ["memory://science/accepted"],
                "instruction_refs": ["instructions://science/v1"],
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual("REVIEW", task["status"])
        self.assertEqual(1, task["attempts"])
        self.assertEqual("SUCCEEDED", snapshot["runs"][0]["status"])
        self.assertEqual("model-a", snapshot["runs"][0]["model"])
        self.assertEqual(1, len(snapshot["artifacts"]))
        self.assertEqual(
            ["RUN_ASSIGNED", "ADAPTER_STARTED", "ARTIFACT_CREATED", "RUN_SUCCEEDED", "REVIEW_REQUESTED"],
            [event["event_type"] for event in snapshot["events"] if event["task_id"] == "science:hypothesis"],
        )
        self.assertEqual(1, brief["attention"]["review"])
        self.assertEqual("0 项运行中，1 项待验收，0 项待决定。", brief["summary"])
        self.assertEqual(["memory://science/accepted"], context_pack["memory_refs"])
        self.assertNotIn("memory_body", context_pack)

    def test_adapter_identity_failure_is_preserved_as_a_blocked_run(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        broker = ExecutionBroker(store, {"missing-identity": MissingIdentityAdapter()})

        result = broker.dispatch(
            "science:hypothesis", adapter_id="missing-identity", model="model-a"
        )

        self.assertFalse(result["ok"])
        self.assertEqual("ADAPTER_RUN_ID_REQUIRED", result["reason"])
        self.assertEqual("BLOCKED", store.get_task("science:hypothesis")["status"])
        self.assertEqual("REJECTED", store.snapshot()["runs"][0]["status"])

    def test_successful_run_that_cannot_enter_review_becomes_blocked(self):
        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "closure",
            "name": "Closure",
            "caption": "Git boundary",
            "layout": "milestones",
            "goal": "Keep evidence honest",
        })
        store.create_task({
            "task_id": "closure:task",
            "workflow_id": "closure",
            "title": "Produce a repository change",
            "acceptance": "A review-ready Git closure exists",
            "requires_git_closure": True,
        })
        broker = ExecutionBroker(store, {"test-adapter": SuccessfulAdapter()})

        result = broker.dispatch(
            "closure:task", adapter_id="test-adapter", model="model-a"
        )

        self.assertFalse(result["ok"])
        self.assertEqual("GIT_CLOSURE_REVIEW_REQUIRED", result["reason"])
        self.assertEqual("BLOCKED", store.get_task("closure:task")["status"])
        self.assertEqual("SUCCEEDED", store.snapshot()["runs"][0]["status"])

    def test_adapter_exception_details_do_not_cross_the_runtime_boundary(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        adapter = RaisingAdapter()
        broker = ExecutionBroker(store, {adapter.adapter_id: adapter})

        result = broker.dispatch(
            "science:hypothesis", adapter_id=adapter.adapter_id, model="model-a"
        )
        persisted = json.dumps(store.snapshot(), ensure_ascii=False)

        self.assertFalse(result["ok"])
        self.assertEqual("ADAPTER_START_FAILED", result["reason"])
        self.assertEqual("ADAPTER_START_FAILED", result["error"])
        self.assertNotIn("SENSITIVE_SENTINEL", json.dumps(result))
        self.assertNotIn("SENSITIVE_SENTINEL", persisted)
        self.assertNotIn("private.invalid", persisted)

    def test_blocked_run_creates_one_decision_and_resolution_requeues_the_task(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        broker = ExecutionBroker(store, {"blocked-adapter": BlockedAdapter()})

        result = broker.dispatch(
            "science:hypothesis", adapter_id="blocked-adapter", model="model-a"
        )
        pending = store.pending_decisions()
        resolved = store.resolve_decision(
            pending[0]["decision_id"], selected_option="B", by="owner"
        )

        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("HUMAN_DECISION_REQUIRED", result["reason"])
        self.assertEqual(1, len(pending))
        self.assertEqual("B", resolved["selected_option"])
        self.assertEqual("QUEUED", store.get_task("science:hypothesis")["status"])
        self.assertEqual([], RuntimeStore(self.database).pending_decisions())
        with self.assertRaisesRegex(ValueError, "already recorded"):
            store.resolve_decision(
                pending[0]["decision_id"], selected_option="A", by="other-owner"
            )

    def test_human_gate_dispatch_creates_a_decision_before_any_adapter_call(self):
        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "gate",
            "name": "Gate",
            "caption": "Human choice",
            "layout": "gate",
            "goal": "Confirm the next path",
        })
        store.create_task({
            "task_id": "gate:choose",
            "workflow_id": "gate",
            "title": "Choose the next path",
            "acceptance": "One option is recorded",
            "human_gate": True,
        })
        adapter = SuccessfulAdapter()
        broker = ExecutionBroker(store, {adapter.adapter_id: adapter})

        result = broker.dispatch("gate:choose", adapter_id=adapter.adapter_id, model="model-a")

        self.assertFalse(result["ok"])
        self.assertEqual("HUMAN_DECISION_REQUIRED", result["reason"])
        decision = store.pending_decisions()[0]
        self.assertEqual("是否继续“Choose the next path”？", decision["question"])
        self.assertEqual("批准并继续", decision["options"][0]["label"])
        self.assertEqual("暂停任务", decision["options"][1]["label"])
        self.assertEqual("通用执行角色", store.get_task("gate:choose")["agent_role"])
        self.assertEqual([], store.snapshot()["runs"])

    def test_separate_runtime_instances_create_one_pending_human_gate(self):
        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "gate-race",
            "name": "Gate race",
            "caption": "One decision",
            "layout": "gate",
            "goal": "Keep one pending choice",
        })
        store.create_task({
            "task_id": "gate-race:choose",
            "workflow_id": "gate-race",
            "title": "Choose one path",
            "acceptance": "One persisted decision",
            "human_gate": True,
        })
        barrier = threading.Barrier(2)
        results = []

        def dispatch_from_new_store():
            local = RuntimeStore(self.database)
            broker = ExecutionBroker(local, {"test-adapter": SuccessfulAdapter()})
            barrier.wait(timeout=2)
            results.append(broker.dispatch(
                "gate-race:choose", adapter_id="test-adapter", model="model-a"
            ))

        threads = [threading.Thread(target=dispatch_from_new_store) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        snapshot = RuntimeStore(self.database).snapshot()
        self.assertEqual(2, len(results))
        self.assertEqual({"HUMAN_DECISION_REQUIRED"}, {item["reason"] for item in results})
        self.assertEqual(1, len([item for item in snapshot["decisions"] if item["status"] == "PENDING"]))
        self.assertEqual([], snapshot["runs"])

    def test_gate_ensure_does_not_reopen_an_already_recorded_decision(self):
        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "recorded-gate",
            "name": "Recorded gate",
            "caption": "No reopen",
            "layout": "gate",
            "goal": "Keep the recorded choice",
        })
        store.create_task({
            "task_id": "recorded-gate:choose",
            "workflow_id": "recorded-gate",
            "title": "Choose",
            "acceptance": "One recorded decision",
            "human_gate": True,
        })
        packet = {
            "question": "Continue?",
            "context": "The task is ready.",
            "options": [
                {"letter": "A", "label": "Continue", "action": "continue"},
                {"letter": "B", "label": "Pause", "action": "pause"},
            ],
        }
        pending = store.ensure_pending_decision("recorded-gate:choose", packet)
        store.resolve_decision(pending["decision_id"], selected_option="A", by="owner")

        ensured = RuntimeStore(self.database).ensure_pending_decision(
            "recorded-gate:choose", packet
        )

        self.assertEqual("RECORDED", ensured["status"])
        self.assertEqual([], store.pending_decisions())
        self.assertEqual(1, len(store.snapshot()["decisions"]))

    def test_human_gate_pause_choice_keeps_task_out_of_dispatch(self):
        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "gate",
            "name": "Gate",
            "caption": "Human choice",
            "layout": "gate",
            "goal": "Confirm the next path",
        })
        store.create_task({
            "task_id": "gate:choose",
            "workflow_id": "gate",
            "title": "Choose the next path",
            "acceptance": "One option is recorded",
            "human_gate": True,
        })
        class CountingAdapter(SuccessfulAdapter):
            def __init__(self):
                self.calls = 0

            def start(self, task, *, model, context_pack):
                self.calls += 1
                return super().start(task, model=model, context_pack=context_pack)

        adapter = CountingAdapter()
        broker = ExecutionBroker(store, {adapter.adapter_id: adapter})
        broker.dispatch("gate:choose", adapter_id=adapter.adapter_id, model="model-a")
        decision = store.pending_decisions()[0]
        barrier = threading.Barrier(2)
        outcomes = {}

        def pause():
            barrier.wait(timeout=1)
            outcomes["decision"] = store.resolve_decision(
                decision["decision_id"], selected_option="B", by="owner"
            )

        def dispatch():
            barrier.wait(timeout=1)
            outcomes["dispatch"] = broker.dispatch(
                "gate:choose", adapter_id=adapter.adapter_id, model="model-a"
            )

        threads = [threading.Thread(target=pause), threading.Thread(target=dispatch)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual("PAUSED", store.get_task("gate:choose")["status"])
        self.assertEqual("B", outcomes["decision"]["selected_option"])
        self.assertFalse(outcomes["dispatch"]["ok"])
        self.assertIn(
            outcomes["dispatch"]["reason"],
            {"HUMAN_DECISION_REQUIRED", "TASK_ALREADY_DISPATCHING", "TASK_NOT_QUEUED"},
        )
        self.assertEqual(0, adapter.calls)
        self.assertEqual([], store.snapshot()["runs"])

    def test_task_dependencies_must_exist_in_the_same_workflow(self):
        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "alpha",
            "name": "Alpha",
            "caption": "First workflow",
            "layout": "sequence",
            "goal": "Produce one result",
        })
        store.create_workflow({
            "workflow_id": "beta",
            "name": "Beta",
            "caption": "Second workflow",
            "layout": "sequence",
            "goal": "Produce another result",
        })
        store.create_task({
            "task_id": "alpha:first",
            "workflow_id": "alpha",
            "title": "First task",
            "acceptance": "One bounded result",
        })

        with self.assertRaisesRegex(ValueError, "dependency not found"):
            store.create_task({
                "task_id": "alpha:unknown-dependency",
                "workflow_id": "alpha",
                "title": "Unknown dependency",
                "acceptance": "Dependency is checked",
                "depends_on": ["alpha:missing"],
            })
        with self.assertRaisesRegex(ValueError, "same workflow"):
            store.create_task({
                "task_id": "beta:cross-workflow",
                "workflow_id": "beta",
                "title": "Cross-workflow dependency",
                "acceptance": "Dependency is checked",
                "depends_on": ["alpha:first"],
            })

    def test_new_tasks_cannot_claim_a_terminal_state_or_existing_result(self):
        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "safe",
            "name": "Safe",
            "caption": "Bounded creation",
            "layout": "sequence",
            "goal": "Create tasks without forged evidence",
        })

        with self.assertRaisesRegex(ValueError, "start in QUEUED"):
            store.create_task({
                "task_id": "safe:forged-done",
                "workflow_id": "safe",
                "title": "Forged completed task",
                "acceptance": "A real result exists",
                "status": "DONE",
                "result_ref": "forged-artifact",
            })
        created = store.create_task({
            "task_id": "safe:queued",
            "workflow_id": "safe",
            "title": "Queued task",
            "acceptance": "A real result will be registered",
            "result_ref": "forged-artifact",
        })

        self.assertEqual("QUEUED", created["status"])
        self.assertIsNone(created["result_ref"])

    def test_concurrent_dispatch_calls_the_adapter_only_once(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        adapter = SlowAdapter()
        broker = ExecutionBroker(store, {adapter.adapter_id: adapter})
        first_result = {}

        thread = threading.Thread(
            target=lambda: first_result.update(
                broker.dispatch(
                    "science:hypothesis",
                    adapter_id=adapter.adapter_id,
                    model="model-a",
                )
            )
        )
        thread.start()
        self.assertTrue(adapter.started.wait(timeout=1))
        self.assertEqual("IN_PROGRESS", store.get_task("science:hypothesis")["status"])
        self.assertEqual("RUNNING", store.snapshot()["runs"][0]["status"])
        second = broker.dispatch(
            "science:hypothesis", adapter_id=adapter.adapter_id, model="model-a"
        )
        adapter.release.set()
        thread.join(timeout=2)

        self.assertEqual(1, adapter.calls)
        self.assertFalse(second["ok"])
        self.assertEqual("TASK_ALREADY_DISPATCHING", second["reason"])
        self.assertTrue(first_result["ok"])
        self.assertEqual(1, len(store.snapshot()["runs"]))

    def test_separate_store_instances_claim_the_task_before_calling_the_model(self):
        barrier = threading.Barrier(2)

        class RacingStore(RuntimeStore):
            def claim_run(self, **kwargs):
                barrier.wait(timeout=2)
                return super().claim_run(**kwargs)

        installed_by = RuntimeStore(self.database)
        install_workflow_preset(installed_by, "science")
        adapter = SlowAdapter()
        stores = [RacingStore(self.database), RacingStore(self.database)]
        brokers = [
            ExecutionBroker(store, {adapter.adapter_id: adapter}) for store in stores
        ]
        outcomes = []

        def dispatch(broker):
            outcomes.append(
                broker.dispatch(
                    "science:hypothesis",
                    adapter_id=adapter.adapter_id,
                    model="model-a",
                )
            )

        threads = [threading.Thread(target=dispatch, args=(broker,)) for broker in brokers]
        for thread in threads:
            thread.start()
        self.assertTrue(adapter.started.wait(timeout=2))
        adapter.release.set()
        for thread in threads:
            thread.join(timeout=3)

        self.assertEqual(1, adapter.calls)
        self.assertEqual(1, sum(bool(item.get("ok")) for item in outcomes))
        runs = RuntimeStore(self.database).snapshot()["runs"]
        self.assertEqual(["SUCCEEDED"], [item["status"] for item in runs])

    def test_routed_competitors_persist_only_the_winning_route(self):
        barrier = threading.Barrier(2)

        class RacingStore(RuntimeStore):
            def claim_run(self, **kwargs):
                barrier.wait(timeout=2)
                return super().claim_run(**kwargs)

        installed_by = RuntimeStore(self.database)
        install_workflow_preset(installed_by, "science")
        adapter = SlowAdapter()
        routes = [
            {
                "route": "route-a",
                "tier": "deep",
                "capabilities": ["reasoning", "evidence"],
                "max_context_tokens": 160000,
                "adapter_id": adapter.adapter_id,
                "model": "model-a",
                "enabled": True,
            },
            {
                "route": "route-b",
                "tier": "deep",
                "capabilities": ["reasoning", "evidence"],
                "max_context_tokens": 160000,
                "adapter_id": adapter.adapter_id,
                "model": "model-b",
                "enabled": True,
            },
        ]
        brokers = [
            ExecutionBroker(RacingStore(self.database), {adapter.adapter_id: adapter})
            for _ in range(2)
        ]
        outcomes = []

        def dispatch(broker, route):
            outcomes.append(
                broker.dispatch_routed(
                    "science:hypothesis",
                    routes=routes,
                    requested_route=route,
                )
            )

        threads = [
            threading.Thread(target=dispatch, args=(broker, route))
            for broker, route in zip(brokers, ("route-a", "route-b"))
        ]
        for thread in threads:
            thread.start()
        self.assertTrue(adapter.started.wait(timeout=2))
        adapter.release.set()
        for thread in threads:
            thread.join(timeout=3)

        winner = next(item for item in outcomes if item.get("ok"))
        loser = next(item for item in outcomes if not item.get("ok"))
        snapshot = RuntimeStore(self.database).snapshot()
        route_events = [
            event
            for event in snapshot["events"]
            if event["event_type"] == "AUTO_ROUTE_SELECTED"
        ]
        self.assertEqual(1, adapter.calls)
        self.assertNotIn("route", loser)
        self.assertEqual(1, len(route_events))
        self.assertTrue(route_events[0]["run_id"])
        self.assertEqual(winner["route"], route_events[0]["payload"]["route"])
        self.assertEqual(
            winner["route"],
            snapshot["assignments"]["science:hypothesis"]["route"],
        )

    def test_routed_dispatch_uses_one_adapter_availability_snapshot(self):
        class FlappingAdapter(SuccessfulAdapter):
            adapter_id = "flapping-adapter"

            def __init__(self):
                self.probe_calls = 0

            def probe(self):
                self.probe_calls += 1
                return {
                    "adapter_id": self.adapter_id,
                    "available": self.probe_calls == 1,
                }

        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        adapter = FlappingAdapter()
        broker = ExecutionBroker(store, {adapter.adapter_id: adapter})

        result = broker.dispatch_routed(
            "science:hypothesis",
            routes=[
                {
                    "route": "quick-route",
                    "tier": "quick",
                    "capabilities": ["reasoning", "evidence"],
                    "max_context_tokens": 160000,
                    "adapter_id": adapter.adapter_id,
                    "model": "quick-model",
                    "enabled": True,
                },
                {
                    "route": "research-route",
                    "tier": "deep",
                    "capabilities": ["reasoning", "evidence"],
                    "max_context_tokens": 160000,
                    "adapter_id": adapter.adapter_id,
                    "model": "research-model",
                    "enabled": True,
                }
            ],
            requested_route="research-route",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(1, adapter.probe_calls)
        self.assertEqual("research-route", result["route"])

    def test_run_claim_rolls_back_if_its_assignment_event_cannot_be_recorded(self):
        class FailingClaimStore(RuntimeStore):
            def _record_event(self, connection, **kwargs):
                if kwargs.get("event_type") == "RUN_ASSIGNED":
                    raise RuntimeError("synthetic assignment failure")
                return super()._record_event(connection, **kwargs)

        store = FailingClaimStore(self.database)
        install_workflow_preset(store, "science")

        with self.assertRaisesRegex(RuntimeError, "synthetic assignment failure"):
            store.claim_run(
                task_id="science:hypothesis",
                adapter_id="test-adapter",
                model="model-a",
                by="adapter:test-adapter",
            )

        self.assertEqual("QUEUED", store.get_task("science:hypothesis")["status"])
        self.assertEqual([], store.snapshot()["runs"])

    def test_next_task_receives_upstream_results_and_explicit_model_context(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        producer = ExecutionBroker(store, {"test-adapter": SuccessfulAdapter()})
        producer.dispatch(
            "science:hypothesis", adapter_id="test-adapter", model="model-a"
        )
        first_run = store.snapshot()["runs"][0]
        store.create_artifact(
            task_id="science:hypothesis",
            run_id=first_run["run_id"],
            content="Accepted replacement result for the next task.",
        )
        accepted = store.transition(
            "science:hypothesis", "DONE", by="owner", reason="Accepted result"
        )
        self.assertTrue(accepted["ok"])
        capture = CaptureAdapter()
        consumer = ExecutionBroker(store, {capture.adapter_id: capture})

        consumer.dispatch(
            "science:protocol-a", adapter_id=capture.adapter_id, model="model-b"
        )
        store.create_task({
            "task_id": "science:module-issue",
            "workflow_id": "science",
            "title": "Resolve a module annotation",
            "acceptance": "The annotation has an inspectable result",
            "context": {
                "workspace_path": "/private/SENSITIVE_SENTINEL",
                "model_context": {
                    "module_id": "workflow-core",
                    "annotation": "Clarify the module handoff boundary.",
                },
            },
        })
        consumer.dispatch(
            "science:module-issue", adapter_id=capture.adapter_id, model="model-b"
        )

        upstream = capture.context_packs[0]["upstream_artifacts"]
        self.assertEqual(1, len(upstream))
        self.assertEqual("science:hypothesis", upstream[0]["task_id"])
        self.assertIn("Accepted replacement result", upstream[0]["content"])
        self.assertEqual(
            "Clarify the module handoff boundary.",
            capture.context_packs[1]["model_context"]["annotation"],
        )
        self.assertNotIn(
            "SENSITIVE_SENTINEL",
            json.dumps(capture.context_packs[1], ensure_ascii=False),
        )

    def test_model_context_has_a_bounded_explicit_payload(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "science")
        task = store.get_task("science:hypothesis")
        task["context"] = {"model_context": {"body": "x" * 30_000}}

        with self.assertRaisesRegex(ValueError, "model_context exceeds"):
            build_context_pack(task)

        with self.assertRaisesRegex(ValueError, "model_context exceeds"):
            store.create_task({
                "task_id": "science:oversized-context",
                "workflow_id": "science",
                "title": "Reject an oversized model payload",
                "acceptance": "The payload remains outside the runtime",
                "context": {"model_context": {"body": "x" * 30_000}},
            })

    def test_concurrent_decision_resolution_records_only_one_choice(self):
        barrier = threading.Barrier(2)

        class RacingStore(RuntimeStore):
            def _resolve_decision(self, decision_id, *, selected_option, by):
                if getattr(self, "racing", False):
                    barrier.wait(timeout=1)
                return super()._resolve_decision(
                    decision_id,
                    selected_option=selected_option,
                    by=by,
                )

        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "gate",
            "name": "Gate",
            "caption": "One decision",
            "layout": "gate",
            "goal": "Record one choice",
        })
        store.create_task({
            "task_id": "gate:task",
            "workflow_id": "gate",
            "title": "Choose one path",
            "acceptance": "Exactly one choice is recorded",
        })
        decision = store.create_decision(
            "gate:task",
            {
                "question": "Which path should continue?",
                "context": "Only one decision can become authoritative.",
                "options": [
                    {"letter": "A", "label": "Path A"},
                    {"letter": "B", "label": "Path B"},
                ],
            },
        )
        stores = [RacingStore(self.database), RacingStore(self.database)]
        for racing_store in stores:
            racing_store.racing = True
        outcomes = []

        def resolve(racing_store, option):
            try:
                outcomes.append(
                    racing_store.resolve_decision(
                        decision["decision_id"], selected_option=option, by=option
                    )["selected_option"]
                )
            except (RuntimeError, ValueError) as exc:
                outcomes.append(str(exc))

        threads = [
            threading.Thread(target=resolve, args=(racing_store, option))
            for racing_store, option in zip(stores, ("A", "B"))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual(1, sum(item in {"A", "B"} for item in outcomes))
        self.assertEqual(1, sum("already recorded" in item for item in outcomes))
        recorded_events = [
            event
            for event in store.snapshot()["events"]
            if event["event_type"] == "DECISION_RECORDED"
        ]
        self.assertEqual(1, len(recorded_events))

    def test_concurrent_task_transitions_commit_only_one_next_state(self):
        barrier = threading.Barrier(2)

        class RacingStore(RuntimeStore):
            def get_task(self, task_id):
                task = super().get_task(task_id)
                if getattr(self, "racing", False) and task["status"] == "REVIEW":
                    barrier.wait(timeout=1)
                return task

        store = RuntimeStore(self.database)
        store.create_workflow({
            "workflow_id": "review",
            "name": "Review",
            "caption": "One authoritative transition",
            "layout": "gate",
            "goal": "Commit one review outcome",
        })
        store.create_task({
            "task_id": "review:task",
            "workflow_id": "review",
            "title": "Review one result",
            "acceptance": "One next state is authoritative",
        })
        run = store.create_run(
            task_id="review:task",
            external_run_id="review-run",
            adapter_id="test-adapter",
            model="model-a",
        )
        store.transition("review:task", "IN_PROGRESS", by="test-adapter")
        store.create_artifact(
            task_id="review:task", run_id=run["run_id"], content="Reviewable result"
        )
        store.transition("review:task", "REVIEW", by="test-adapter")
        stores = [RacingStore(self.database), RacingStore(self.database)]
        for racing_store in stores:
            racing_store.racing = True
        outcomes = []

        def move(racing_store, to, reason=""):
            outcomes.append(
                racing_store.transition("review:task", to, by="owner", reason=reason)
            )

        threads = [
            threading.Thread(target=move, args=(stores[0], "DONE")),
            threading.Thread(
                target=move,
                args=(stores[1], "QUEUED", "Revise the result"),
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual(1, sum(item["ok"] for item in outcomes))
        self.assertEqual(
            1,
            sum(item.get("reason") == "STATE_CHANGED_RETRY" for item in outcomes),
        )
        review_events = [
            event
            for event in store.snapshot()["events"]
            if event["payload"].get("from") == "REVIEW"
        ]
        self.assertEqual(1, len(review_events))


class OpenAICompatibleAdapterTests(unittest.TestCase):
    def test_adapter_calls_a_real_compatible_http_endpoint_without_persisting_secret(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                received["path"] = self.path
                received["authorization"] = self.headers.get("Authorization")
                received["body"] = json.loads(self.rfile.read(length))
                payload = json.dumps({
                    "id": "chatcmpl-local-1",
                    "choices": [{"message": {"content": "model result"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            adapter = OpenAICompatibleAdapter(
                api_base=f"http://127.0.0.1:{server.server_port}/v1",
                api_key="unit-test-placeholder",
                timeout=2,
            )
            result = adapter.start(
                {"task_id": "task-1", "title": "Bounded task"},
                model="compatible-model",
                context_pack={"goal": "Produce one result", "constraints": []},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertTrue(result["ok"])
        self.assertEqual("chatcmpl-local-1", result["external_run_id"])
        self.assertEqual("model result", result["output_text"])
        self.assertEqual("/v1/chat/completions", received["path"])
        self.assertEqual("Bearer unit-test-placeholder", received["authorization"])
        self.assertEqual("compatible-model", received["body"]["model"])
        self.assertNotIn("unit-test-placeholder", json.dumps(result))


class PresetContractTests(unittest.TestCase):
    def test_document_presets_do_not_contain_private_business_abbreviations(self):
        serialized = json.dumps(
            [get_workflow_preset("meeting-notes"), get_workflow_preset("analytical-report")],
            ensure_ascii=False,
        )
        for abbreviation in ("V" + "C", "B" + "P"):
            self.assertNotIn(abbreviation, serialized)


if __name__ == "__main__":
    unittest.main()
