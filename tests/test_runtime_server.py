import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from personal_ai_os.runtime import RuntimeStore, install_workflow_preset
from personal_ai_os.server import create_runtime_server


class SuccessfulAdapter:
    adapter_id = "test-adapter"

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        return {
            "ok": True,
            "external_run_id": "api-run-1",
            "status": "SUCCEEDED",
            "output_text": "API result",
        }


class RuntimeServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RuntimeStore(Path(self.temp.name) / "runtime.db")
        install_workflow_preset(self.store, "science")
        self.server = create_runtime_server(
            ("127.0.0.1", 0),
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="model-a",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            return response.status, json.loads(response.read())

    def test_api_reads_runtime_and_dispatches_a_real_adapter(self):
        status, initial = self.request("/api/runtime")
        run_status, dispatched = self.request(
            "/api/runs",
            {
                "task_id": "science:hypothesis",
                "adapter_id": "test-adapter",
                "model": "model-a",
            },
        )
        _, after = self.request("/api/runtime")

        self.assertEqual(200, status)
        self.assertEqual("runtime", initial["data_source"])
        self.assertEqual("READY", initial["status"])
        self.assertEqual(200, run_status)
        self.assertTrue(dispatched["ok"])
        task = next(item for item in after["state"]["tasks"] if item["task_id"] == "science:hypothesis")
        self.assertEqual("REVIEW", after["state"]["taskStates"][task["task_id"]])
        self.assertEqual(1, task["attempts"])

    def test_api_creates_tasks_and_accepts_reviewed_results(self):
        _, created = self.request(
            "/api/tasks",
            {
                "task_id": "science:extra",
                "workflow_id": "science",
                "line_id": "science",
                "title": "Additional bounded task",
                "acceptance": "One inspectable artifact",
                "depends_on": [],
                "required_capabilities": ["reasoning"],
            },
        )
        self.request(
            "/api/runs",
            {"task_id": "science:extra", "adapter_id": "test-adapter", "model": "model-a"},
        )
        _, accepted = self.request(
            "/api/tasks/science%3Aextra/transition",
            {"to": "DONE", "by": "owner", "reason": "Accepted result"},
        )

        self.assertEqual("science:extra", created["task_id"])
        self.assertTrue(accepted["ok"])
        self.assertEqual("DONE", self.store.get_task("science:extra")["status"])

    def test_runtime_projection_omits_local_task_context_and_git_closure(self):
        self.store.create_task({
            "task_id": "science:private-local-reference",
            "workflow_id": "science",
            "title": "Use a registered local workspace",
            "acceptance": "The local reference remains server-side",
            "context": {
                "workspace_path": "/private/SENSITIVE_SENTINEL",
                "model_context": {"instruction": "Use only accepted evidence."},
            },
        })

        _, projection = self.request("/api/runtime")
        serialized = json.dumps(projection, ensure_ascii=False)
        task = next(
            item
            for item in projection["state"]["tasks"]
            if item["task_id"] == "science:private-local-reference"
        )

        self.assertNotIn("context", task)
        self.assertNotIn("git_closure", task)
        self.assertNotIn("SENSITIVE_SENTINEL", serialized)

    def test_server_blocks_path_traversal_and_unknown_adapter(self):
        with self.assertRaises(urllib.error.HTTPError) as traversal:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                self.base + "/../README.md", timeout=3
            )
        with self.assertRaises(urllib.error.HTTPError) as adapter:
            self.request(
                "/api/runs",
                {"task_id": "science:hypothesis", "adapter_id": "missing", "model": "model-a"},
            )

        self.assertEqual(404, traversal.exception.code)
        self.assertEqual(422, adapter.exception.code)

    def test_write_api_rejects_cross_site_and_non_json_requests(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        non_json = urllib.request.Request(
            self.base + "/api/runs",
            data=b"{}",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        cross_site = urllib.request.Request(
            self.base + "/api/runs",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://untrusted.example",
            },
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as content_type:
            opener.open(non_json, timeout=3)
        with self.assertRaises(urllib.error.HTTPError) as origin:
            opener.open(cross_site, timeout=3)

        self.assertEqual(415, content_type.exception.code)
        self.assertEqual(403, origin.exception.code)
        self.assertEqual([], self.store.snapshot()["runs"])


if __name__ == "__main__":
    unittest.main()
