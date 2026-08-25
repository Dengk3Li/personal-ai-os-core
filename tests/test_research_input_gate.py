import json
import io
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

from personal_ai_os.cli import main
from personal_ai_os.research_input_gate import preview_research_input
from personal_ai_os.runtime import RuntimeStore, install_workflow_preset
from personal_ai_os.server import create_runtime_server


class ResearchInputGateTests(unittest.TestCase):
    def test_cli_preview_does_not_initialize_a_runtime_store(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "inputs.json"
            input_path.write_text(
                json.dumps(
                    {
                        "research_question": "A question",
                        "scope": {"time_boundary": "2026"},
                        "audience": "internal",
                        "format": "Markdown",
                        "source_policy": {"allowed_kinds": ["paper"]},
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["research-input-preview", "--input", str(input_path)])

            self.assertEqual(0, exit_code)
            self.assertEqual({"status": "READY_FOR_INPUT", "missing_inputs": []}, json.loads(output.getvalue()))
            self.assertEqual([input_path.name], [item.name for item in Path(directory).iterdir()])

    def test_missing_and_placeholder_inputs_return_structured_gaps(self):
        result = preview_research_input(
            {
                "research_question": "占位",
                "scope": {"time_boundary": "2026"},
                "audience": "内部",
                "format": None,
                "source_policy": {},
            }
        )

        self.assertEqual("REPORT_INPUT_REQUIRED", result["status"])
        self.assertEqual(
            [
                {"path": "research_task.research_question", "reason": "PLACEHOLDER"},
                {"path": "research_task.format", "reason": "REQUIRED"},
                {"path": "research_task.source_policy", "reason": "REQUIRED"},
            ],
            result["missing_inputs"],
        )

    def test_complete_inputs_only_return_readiness_and_never_echo_values(self):
        result = preview_research_input(
            {
                "research_question": "How does the system route work?",
                "scope": {"time_boundary": "2026", "local_path": "/private/secret"},
                "audience": "internal",
                "format": "Markdown",
                "source_policy": {"allowed_kinds": ["paper"]},
            }
        )

        self.assertEqual({"status": "READY_FOR_INPUT", "missing_inputs": []}, result)
        self.assertNotIn("/private/secret", json.dumps(result))

    def test_unknown_fields_are_rejected_without_echoing_payload(self):
        result = preview_research_input(
            {
                "research_question": "A question",
                "scope": {"time_boundary": "2026"},
                "audience": "internal",
                "format": "Markdown",
                "source_policy": {"allowed_kinds": ["paper"]},
                "/Users/zita/private/secret": "sensitive-value",
            }
        )

        self.assertEqual("REPORT_INPUT_INVALID", result["status"])
        self.assertEqual(
            [{"path": "research_task", "reason": "UNSUPPORTED_FIELD"}],
            result["invalid_inputs"],
        )
        self.assertNotIn("/private/secret", json.dumps(result))

    def test_http_preview_is_read_only_and_returns_safe_public_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            install_workflow_preset(store, "science")
            before = store.snapshot()
            server = create_runtime_server(
                ("127.0.0.1", 0),
                store=store,
                adapters={},
                default_model="model-a",
                web_root=Path(__file__).resolve().parents[1] / "workbench",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for _ in range(30):
                    try:
                        with socket.create_connection(("127.0.0.1", server.server_port), timeout=0.2):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    self.fail("loopback runtime server did not become ready")
                payload = {
                    "research_question": "占位",
                    "scope": {"local_path": "/private/secret"},
                    "audience": "internal",
                    "format": "Markdown",
                    "source_policy": {"allowed_kinds": ["paper"]},
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/research/report-input-preview",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=3) as response:
                    result = json.loads(response.read())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual("REPORT_INPUT_REQUIRED", result["status"])
            self.assertEqual(
                [{"path": "research_task.research_question", "reason": "PLACEHOLDER"}],
                result["missing_inputs"],
            )
            self.assertEqual(before, store.snapshot())
            self.assertNotIn("/private/secret", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
