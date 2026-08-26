import tempfile
import unittest
from pathlib import Path

from personal_ai_os.runtime import ExecutionBroker, RuntimeStore
from personal_ai_os.template_selection import TEMPLATE_SELECTION_VERSION


class CountingAdapter:
    adapter_id = "counting-adapter"

    def __init__(self):
        self.probe_calls = 0
        self.start_calls = 0
        self.context_packs = []

    def probe(self):
        self.probe_calls += 1
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        self.start_calls += 1
        self.context_packs.append(context_pack)
        return {
            "ok": True,
            "external_run_id": "template-run-1",
            "status": "SUCCEEDED",
            "output_text": "template-bound result",
        }


class TemplateSelectionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "runtime.db"
        self.store = RuntimeStore(self.database)
        self.store.create_workflow(
            {
                "workflow_id": "template-work",
                "name": "Template work",
                "caption": "",
                "layout": "milestones",
                "goal": "Produce a bounded document",
                "domain_id": "writing",
            }
        )

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def valid_selection():
        return {
            "schema_version": TEMPLATE_SELECTION_VERSION,
            "template_id": "template-001",
            "version": "v3",
            "source_ref": "template-ref-001",
            "content_sha256": "A" * 64,
            "task_kind": "document-draft",
        }

    def create_task(self, context):
        return self.store.create_task(
            {
                "task_id": "template-work:draft",
                "workflow_id": "template-work",
                "title": "Produce a draft",
                "acceptance": "The draft is reviewable",
                "context": context,
            }
        )

    def test_invalid_declared_selection_keeps_task_queued_without_adapter_call(self):
        self.create_task(
            {
                "template_selection": {
                    **self.valid_selection(),
                    "content_sha256": "not-a-digest",
                }
            }
        )
        adapter = CountingAdapter()

        result = ExecutionBroker(
            self.store, {adapter.adapter_id: adapter}
        ).dispatch("template-work:draft", adapter_id=adapter.adapter_id, model="model-a")

        self.assertFalse(result["ok"])
        self.assertEqual("QUEUED", result["status"])
        self.assertEqual("TEMPLATE_SELECTION_INVALID", result["reason"])
        self.assertEqual("QUEUED", self.store.get_task("template-work:draft")["status"])
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual(0, adapter.probe_calls)
        self.assertEqual(0, adapter.start_calls)

    def test_missing_declared_selection_keeps_task_queued_without_adapter_call(self):
        self.create_task({"template_selection": None})
        adapter = CountingAdapter()

        result = ExecutionBroker(
            self.store, {adapter.adapter_id: adapter}
        ).dispatch("template-work:draft", adapter_id=adapter.adapter_id, model="model-a")

        self.assertFalse(result["ok"])
        self.assertEqual("QUEUED", result["status"])
        self.assertEqual("TEMPLATE_SELECTION_REQUIRED", result["reason"])
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual(0, adapter.probe_calls)
        self.assertEqual(0, adapter.start_calls)

    def test_valid_selection_is_the_only_template_metadata_given_to_adapter(self):
        self.create_task({"template_selection": self.valid_selection()})
        adapter = CountingAdapter()

        result = ExecutionBroker(
            self.store, {adapter.adapter_id: adapter}
        ).dispatch("template-work:draft", adapter_id=adapter.adapter_id, model="model-a")

        self.assertTrue(result["ok"])
        self.assertEqual(1, adapter.start_calls)
        selection = adapter.context_packs[0]["template_selection"]
        self.assertEqual(self.valid_selection()["source_ref"], selection["source_ref"])
        self.assertEqual("a" * 64, selection["content_sha256"])
        self.assertNotIn("content", selection)
        self.assertNotIn("path", selection)


if __name__ == "__main__":
    unittest.main()
