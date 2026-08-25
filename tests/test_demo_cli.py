import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DemoCliTests(unittest.TestCase):
    def test_demo_reports_a_safe_synthetic_run(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-m", "personal_ai_os", "demo"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("SAFE", payload["status"])
        self.assertEqual("synthetic", payload["data_source"])
        self.assertEqual(
            [
                "asset_freeze",
                "candidate_promotion",
                "domain_route",
                "dynamic_route",
                "git_closure",
                "long_task_plan",
                "task_assignment",
                "truth_compile",
                "workbench_projection",
                "workflow_transition",
            ],
            payload["checks"],
        )

    def test_runtime_cli_initializes_and_reads_a_persistent_science_workflow(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            store = str(Path(directory) / "runtime.db")
            initialized = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "runtime",
                    "init",
                    "--store",
                    store,
                    "--preset",
                    "science",
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            status = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "runtime",
                    "status",
                    "--store",
                    store,
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, initialized.returncode, initialized.stderr)
        self.assertEqual(7, json.loads(initialized.stdout)["task_count"])
        self.assertEqual(0, status.returncode, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual("READY", payload["status"])
        self.assertEqual("runtime-store", payload["brief"]["authority"])

    def test_runtime_cli_syncs_a_private_local_plan_without_copying_it_to_output(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = str(root / "runtime.db")
            private_path = "/private/local/workspace"
            plan = root / "private-plan.json"
            plan.write_text(json.dumps({
                "schema_version": "personal-ai-os.runtime-plan/v1",
                "workflows": [{
                    "workflow_id": "next-stage",
                    "name": "Next stage",
                    "caption": "Self-hosted work",
                    "layout": "milestones",
                    "goal": "Advance one verified slice",
                    "tasks": [{
                        "task_id": "next-stage:first",
                        "title": "Index the local workspace",
                        "acceptance": "A bounded local reference exists",
                        "context": {"workspace_path": private_path},
                    }],
                }],
            }), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "runtime",
                    "sync-plan",
                    "--store",
                    store,
                    "--plan",
                    str(plan),
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("READY", payload["status"])
        self.assertEqual(1, payload["created_workflows"])
        self.assertEqual(1, payload["created_tasks"])
        self.assertNotIn(private_path, result.stdout)

    def test_domain_context_cli_compiles_only_the_selected_profile(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "domains.json"
            registry.write_text(json.dumps({"profiles": [{
                "domain_id": "software",
                "persona": "test-first",
                "context_layers": {
                    "domain_contract": ["contract://software/v1"],
                    "current_state": ["state://software/current"],
                },
                "allowed_tools": ["tests"],
            }]}), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "domain-context",
                    "--registry",
                    str(registry),
                    "--domain",
                    "software",
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("RESOLVED", payload["status"])
        self.assertEqual("test-first", payload["persona"])

    def test_runtime_advance_exits_blocked_when_the_adapter_is_unavailable(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        env.pop("PERSONAL_AI_OS_API_BASE", None)
        env.pop("PERSONAL_AI_OS_API_KEY", None)
        with tempfile.TemporaryDirectory() as directory:
            store = str(Path(directory) / "runtime.db")
            initialized = subprocess.run(
                [sys.executable, "-m", "personal_ai_os", "runtime", "init", "--store", store, "--preset", "science"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            advanced = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "runtime",
                    "advance",
                    "--store",
                    store,
                    "--workflow",
                    "science",
                    "--model",
                    "model-a",
                    "--max-steps",
                    "10",
                    "--failure-budget",
                    "1",
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, initialized.returncode, initialized.stderr)
        self.assertEqual(2, advanced.returncode, advanced.stderr)
        payload = json.loads(advanced.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual("BLOCKED", payload["status"])
        self.assertEqual("ADAPTER_UNAVAILABLE", payload["stop_reason"])
        self.assertEqual(1, len(payload["actions"]))

    def test_runtime_advance_loads_a_versioned_route_catalog(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        env.pop("PERSONAL_AI_OS_API_BASE", None)
        env.pop("PERSONAL_AI_OS_API_KEY", None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = str(root / "runtime.db")
            routes = root / "routes.json"
            routes.write_text(
                json.dumps(
                    {
                        "schema_version": "personal-ai-os.runtime-routes/v1",
                        "routes": [
                            {
                                "route": "deep-science",
                                "tier": "deep",
                                "capabilities": ["reasoning", "evidence"],
                                "max_context_tokens": 160000,
                                "adapter_id": "openai-compatible",
                                "model": "model-routed",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            initialized = subprocess.run(
                [sys.executable, "-m", "personal_ai_os", "runtime", "init", "--store", store, "--preset", "science"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            advanced = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "runtime",
                    "advance",
                    "--store",
                    store,
                    "--workflow",
                    "science",
                    "--routes",
                    str(routes),
                    "--max-steps",
                    "10",
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, initialized.returncode, initialized.stderr)
        self.assertTrue(advanced.stdout, advanced.stderr)
        payload = json.loads(advanced.stdout)
        self.assertEqual(2, advanced.returncode, advanced.stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual("ROUTE_NOT_FOUND", payload["stop_reason"])
        self.assertEqual(1, len(payload["actions"]))

    def test_runtime_serve_rejects_an_invalid_presentation_without_a_traceback(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            presentation = root / "presentation.json"
            presentation.write_text(
                json.dumps(
                    {
                        "schema_version": "personal-ai-os.presentation/v1",
                        "tasks": {"task-a": {"context": "must stay private"}},
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "runtime",
                    "serve",
                    "--store",
                    str(root / "runtime.db"),
                    "--model",
                    "model-a",
                    "--presentation",
                    str(presentation),
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual(
            {"reason": "PRESENTATION_INVALID", "status": "BLOCKED"},
            json.loads(result.stdout),
        )

    def test_runtime_serve_rejects_sensitive_execution_labels_without_a_traceback(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            presentation = root / "presentation.json"
            presentation.write_text(
                json.dumps({"schema_version": "personal-ai-os.presentation/v1"}),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "personal_ai_os",
                    "runtime",
                    "serve",
                    "--store",
                    str(root / "runtime.db"),
                    "--model",
                    "/Users/example/private-model",
                    "--presentation",
                    str(presentation),
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual(
            {"reason": "PRESENTATION_INVALID", "status": "BLOCKED"},
            json.loads(result.stdout),
        )


if __name__ == "__main__":
    unittest.main()
