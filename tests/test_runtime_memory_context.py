import tempfile
import unittest
from pathlib import Path

from personal_ai_os.memory_context import READY
from personal_ai_os.runtime import ExecutionBroker, RuntimeStore


class CaptureAdapter:
    adapter_id = "capture-adapter"

    def __init__(self):
        self.calls = []

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        self.calls.append(context_pack)
        return {
            "ok": True,
            "external_run_id": "memory-run-1",
            "status": "SUCCEEDED",
            "output_text": "A bounded result.",
        }


def memory_task(task_id="writing:memory", **context_overrides):
    context = {
        "memory_policy": "require_read",
        "memory_refs": ["practice-1"],
        "memory_subject": {"kind": "person", "id": "writer-a"},
        "memory_domain_id": "writing",
    }
    context.update(context_overrides)
    return {
        "task_id": task_id,
        "workflow_id": "writing",
        "title": "形成初稿",
        "acceptance": "保留来源和复核入口",
        "domain_id": "writing",
        "context": context,
    }


def registered_refs(status="APPROVED", **overrides):
    reference = {
        "memory_id": "practice-1",
        "title": "写作方式",
        "status": status,
        "subject": {"kind": "person", "id": "writer-a"},
        "domain_id": "writing",
        "source_ref": "memory://writing/practice-1",
        "facts": ["先核对证据，再形成判断。"],
        "decisions": ["保留人工复核。"],
    }
    reference.update(overrides)
    return {"practice-1": reference}


class RuntimeMemoryContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RuntimeStore(Path(self.temp.name) / "runtime.db")
        self.store.create_workflow({
            "workflow_id": "writing",
            "name": "写作线",
            "caption": "受控记忆读取",
            "layout": "pipeline",
            "goal": "形成可复核文本",
            "domain_id": "writing",
        })

    def tearDown(self):
        self.temp.cleanup()

    def add_task(self, task):
        self.store.create_task(task)

    def test_required_read_without_explicit_refs_stops_before_any_runtime_side_effect(self):
        task = memory_task(**{"memory_refs": []})
        self.add_task(task)
        adapter = CaptureAdapter()

        result = ExecutionBroker(
            self.store,
            {adapter.adapter_id: adapter},
            registered_memory_refs=registered_refs(),
        ).dispatch(task["task_id"], adapter_id=adapter.adapter_id, model="model-a")

        self.assertFalse(result["ok"])
        self.assertEqual("MEMORY_REFS_REQUIRED", result["reason"])
        self.assertEqual("QUEUED", self.store.get_task(task["task_id"])["status"])
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual([], self.store.snapshot()["events"])
        self.assertEqual([], adapter.calls)

    def test_unapproved_reference_stops_before_run_claim_and_adapter_call(self):
        task = memory_task()
        self.add_task(task)
        adapter = CaptureAdapter()

        result = ExecutionBroker(
            self.store,
            {adapter.adapter_id: adapter},
            registered_memory_refs=registered_refs(status="PROPOSED"),
        ).dispatch(task["task_id"], adapter_id=adapter.adapter_id, model="model-a")

        self.assertFalse(result["ok"])
        self.assertEqual("MEMORY_REF_NOT_APPROVED", result["reason"])
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual([], self.store.snapshot()["events"])
        self.assertEqual([], adapter.calls)

    def test_successful_read_is_bound_into_context_and_only_requests_review(self):
        task = memory_task()
        self.add_task(task)
        adapter = CaptureAdapter()

        result = ExecutionBroker(
            self.store,
            {adapter.adapter_id: adapter},
            registered_memory_refs=registered_refs(),
        ).dispatch(task["task_id"], adapter_id=adapter.adapter_id, model="model-a")

        self.assertTrue(result["ok"])
        self.assertEqual(1, len(adapter.calls))
        context = adapter.calls[0]
        self.assertEqual(READY, context["memory_read_status"])
        self.assertEqual(["practice-1"], context["memory_ref_ids"])
        self.assertEqual(
            ["先核对证据，再形成判断。"],
            context["memory_context"]["entries"][0]["facts"],
        )
        events = self.store.snapshot()["events"]
        review_events = [
            event for event in events if event["event_type"] == "MEMORY_REVIEW_REQUESTED"
        ]
        self.assertEqual(1, len(review_events))
        payload = review_events[0]["payload"]
        self.assertEqual("CANDIDATE", payload["candidate"]["status"])
        self.assertFalse(payload["candidate"]["promotion"]["authorized"])
        self.assertEqual([], self.store.snapshot()["memory_candidates"])

    def test_oversized_reference_stops_before_run_claim(self):
        task = memory_task()
        self.add_task(task)
        adapter = CaptureAdapter()

        result = ExecutionBroker(
            self.store,
            {adapter.adapter_id: adapter},
            registered_memory_refs=registered_refs(facts=["x" * 8_001]),
        ).dispatch(task["task_id"], adapter_id=adapter.adapter_id, model="model-a")

        self.assertFalse(result["ok"])
        self.assertEqual("MEMORY_CONTEXT_TOO_LARGE", result["reason"])
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual([], self.store.snapshot()["events"])
        self.assertEqual([], adapter.calls)


if __name__ == "__main__":
    unittest.main()
