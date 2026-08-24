import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from personal_ai_os.intake import build_candidate_plan, inspect_workspace
from personal_ai_os.modules import build_module_graph, module_catalog
from personal_ai_os.operations import operation_spec


REPO_ROOT = Path(__file__).resolve().parents[1]


class ModuleContractTests(unittest.TestCase):
    def test_builtin_modules_form_a_resolved_composable_graph(self):
        catalog = module_catalog()
        graph = build_module_graph(catalog)

        self.assertEqual("READY", graph["status"])
        self.assertEqual([], graph["unresolved"])
        self.assertIn("workspace-intake", [item["module_id"] for item in graph["nodes"]])
        token_manager = next(
            item for item in graph["nodes"] if item["module_id"] == "token-manager"
        )
        self.assertEqual("PLANNED", token_manager["availability"])

    def test_missing_module_capability_blocks_composition_at_the_source(self):
        graph = build_module_graph(
            [{
                "module_id": "consumer",
                "name": "Consumer",
                "layer": "orchestration",
                "provides": ["output"],
                "requires": ["missing.input"],
                "availability": "READY",
            }]
        )

        self.assertEqual("BLOCKED", graph["status"])
        self.assertEqual(
            [{"module_id": "consumer", "capability": "missing.input"}],
            graph["unresolved"],
        )


class FirstRunIntakeTests(unittest.TestCase):
    def test_workspace_inspection_is_read_only_and_proposes_parallel_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "research").mkdir()
            (root / "drafts").mkdir()
            (root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "research" / "paper.md").write_text("notes\n", encoding="utf-8")
            (root / "drafts" / "outline.md").write_text("outline\n", encoding="utf-8")
            before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

            snapshot = inspect_workspace(root)
            plan = build_candidate_plan(snapshot)
            after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

        self.assertEqual(before, after)
        self.assertTrue(snapshot["read_only"])
        self.assertEqual("INSPECTED", snapshot["status"])
        self.assertEqual(
            ["product", "research", "writing"],
            sorted(line["line_id"] for line in snapshot["suggested_lines"]),
        )
        self.assertEqual("CANDIDATE", plan["status"])
        self.assertTrue(plan["requires_human_confirmation"])
        self.assertEqual("CONFIRM", plan["operation_chain"][3]["operation"])

    def test_dirty_git_workspace_becomes_an_explicit_human_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "README.md").write_text("uncommitted\n", encoding="utf-8")

            snapshot = inspect_workspace(root)
            plan = build_candidate_plan(snapshot)

        self.assertEqual("DIRTY", snapshot["git"]["status"])
        self.assertGreaterEqual(snapshot["git"]["dirty_count"], 1)
        self.assertEqual("workspace:dirty-boundary", plan["preflight_tasks"][0]["task_id"])
        self.assertTrue(plan["preflight_tasks"][0]["human_gate"])


class OperationCliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "personal_ai_os", *arguments],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_spec_command_exposes_the_same_operating_protocol(self):
        result = self.run_cli("spec")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(operation_spec()["operations"], payload["operations"])
        self.assertEqual("UNASSIGNED", payload["task_states"][0]["state"])

    def test_inspect_and_plan_commands_return_machine_readable_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("project\n", encoding="utf-8")
            inspected = self.run_cli("inspect", str(root))
            planned = self.run_cli("plan", str(root))

        self.assertEqual(0, inspected.returncode, inspected.stderr)
        self.assertTrue(json.loads(inspected.stdout)["read_only"])
        self.assertEqual(0, planned.returncode, planned.stderr)
        self.assertEqual("CANDIDATE", json.loads(planned.stdout)["status"])

    def test_missing_workspace_fails_closed(self):
        result = self.run_cli("inspect", "/path/that/does/not/exist")
        self.assertEqual(2, result.returncode)
        self.assertEqual("UNKNOWN", json.loads(result.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
