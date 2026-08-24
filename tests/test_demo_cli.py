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


if __name__ == "__main__":
    unittest.main()
