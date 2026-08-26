import tempfile
import unittest
from pathlib import Path

from personal_ai_os.codex_project import CodexProjectAdapter
from personal_ai_os.presets import get_workflow_preset
from personal_ai_os.runtime import ExecutionBroker, RuntimeStore, install_workflow_preset


class CodexProjectAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = self.root / "workspace"
        self.project.mkdir()
        self.store = RuntimeStore(self.root / "runtime.db")
        install_workflow_preset(self.store, "science")
        self.adapter = CodexProjectAdapter(
            self.store,
            project_bindings=[
                {
                    "project_key": "science-workspace",
                    "project_id": "codex-project-expected",
                    "label": "科研项目",
                    "path": str(self.project),
                    "workflow_ids": ["science"],
                    "environment": "worktree",
                }
            ],
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_dispatch_creates_one_persistent_project_request_instead_of_a_projectless_thread(self):
        broker = ExecutionBroker(
            self.store,
            {self.adapter.adapter_id: self.adapter},
        )

        result = broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )

        self.assertTrue(result["ok"])
        self.assertEqual("IN_PROGRESS", result["status"])
        pending = self.adapter.pending_dispatches()
        self.assertEqual(1, len(pending))
        self.assertEqual("science:hypothesis", pending[0]["task_id"])
        self.assertEqual("科研项目", pending[0]["project"]["label"])
        self.assertEqual(str(self.project.resolve()), pending[0]["project"]["path"])
        self.assertEqual("worktree", pending[0]["project"]["environment"])
        self.assertIn("澄清科学问题并提出可检验假设", pending[0]["prompt"])
        snapshot = self.store.snapshot()
        self.assertEqual("RUNNING", snapshot["runs"][0]["status"])
        self.assertEqual(pending[0]["dispatch_id"], snapshot["runs"][0]["external_run_id"])

    def test_each_task_attempt_gets_a_unique_project_dispatch_id(self):
        broker = ExecutionBroker(
            self.store,
            {self.adapter.adapter_id: self.adapter},
        )

        first = broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )
        self.store.create_task({
            "task_id": "science:protocol",
            "workflow_id": "science",
            "title": "设计实验协议",
            "acceptance": "形成可核对协议",
            "domain_id": "science",
            "depends_on": [],
        })
        second = broker.dispatch(
            "science:protocol",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        dispatches = self.adapter.pending_dispatches()
        self.assertEqual(2, len(dispatches))
        self.assertEqual(2, len({item["dispatch_id"] for item in dispatches}))
        self.assertEqual(
            {item["dispatch_id"] for item in dispatches},
            {run["external_run_id"] for run in self.store.snapshot()["runs"]},
        )

    def test_claim_bind_and_complete_returns_the_project_thread_result_to_review(self):
        broker = ExecutionBroker(
            self.store,
            {self.adapter.adapter_id: self.adapter},
        )
        broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )

        claimed = self.adapter.claim_next(worker_id="manager-thread")
        self.assertEqual("CLAIMED", claimed["status"])
        self.assertIsNone(self.adapter.claim_next(worker_id="other-manager"))
        bound = self.adapter.bind_thread(
            claimed["dispatch_id"],
            thread_id="codex-thread-1",
            project_id="codex-project-expected",
            host_id="local",
            verification={
                "source": "task-project", "verified": True,
                "project_id": "codex-project-expected", "project_path": str(self.project),
                "environment": "worktree",
            },
        )
        self.assertEqual("RUNNING", bound["status"])
        self.assertEqual("local", bound["host_id"])
        completed = self.adapter.complete(
            claimed["dispatch_id"],
            output_text="已形成可核对的科学假设。",
            usage={"input_tokens": 120, "output_tokens": 30},
            completion_receipt={
                "status": "completed", "verified": True,
                "needs_user_input": False, "human_gate": False,
            },
        )

        self.assertTrue(completed["ok"])
        self.assertEqual("REVIEW", completed["status"])
        self.assertEqual("REVIEW", self.store.get_task("science:hypothesis")["status"])
        snapshot = self.store.snapshot()
        self.assertEqual("SUCCEEDED", snapshot["runs"][0]["status"])
        self.assertEqual(1, len(snapshot["artifacts"]))
        self.assertEqual("已形成可核对的科学假设。", snapshot["artifacts"][0]["content"])
        self.assertEqual("SUCCEEDED", self.adapter.get_dispatch(claimed["dispatch_id"])["status"])

    def test_bind_rejects_a_thread_from_a_different_codex_project(self):
        broker = ExecutionBroker(self.store, {self.adapter.adapter_id: self.adapter})
        broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )
        claimed = self.adapter.claim_next(worker_id="manager-thread")

        with self.assertRaisesRegex(ValueError, "does not match configured Codex project"):
            self.adapter.bind_thread(
                claimed["dispatch_id"],
                thread_id="codex-thread-1",
                project_id="codex-project-wrong",
                host_id="local",
                verification={
                    "source": "thread-project-assignments", "verified": True,
                    "project_id": "codex-project-wrong", "project_path": str(self.project),
                    "environment": "worktree",
                },
            )

        self.assertEqual("CLAIMED", self.adapter.get_dispatch(claimed["dispatch_id"])["status"])

    def test_completion_requires_a_nonempty_final_output_and_terminal_receipt(self):
        broker = ExecutionBroker(self.store, {self.adapter.adapter_id: self.adapter})
        broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )
        claimed = self.adapter.claim_next(worker_id="manager-thread")
        self.adapter.bind_thread(
            claimed["dispatch_id"],
            thread_id="codex-thread-1",
            project_id="codex-project-expected",
            host_id="local",
            verification={
                "source": "task-project", "verified": True,
                "project_id": "codex-project-expected", "project_path": str(self.project),
                "environment": "worktree",
            },
        )

        with self.assertRaisesRegex(ValueError, "final output"):
            self.adapter.complete(
                claimed["dispatch_id"],
                output_text="",
            )
        with self.assertRaisesRegex(ValueError, "terminal receipt"):
            self.adapter.complete(
                claimed["dispatch_id"],
                output_text="结果",
            )
        self.assertEqual("RUNNING", self.adapter.get_dispatch(claimed["dispatch_id"])["status"])

    def test_completion_keeps_a_human_gate_or_user_question_open(self):
        broker = ExecutionBroker(self.store, {self.adapter.adapter_id: self.adapter})
        broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )
        claimed = self.adapter.claim_next(worker_id="manager-thread")
        self.adapter.bind_thread(
            claimed["dispatch_id"],
            thread_id="codex-thread-1",
            project_id="codex-project-expected",
            host_id="local",
            verification={
                "source": "thread-project-assignments", "verified": True,
                "project_id": "codex-project-expected", "project_path": str(self.project),
                "environment": "worktree",
            },
        )

        with self.assertRaisesRegex(ValueError, "human gate"):
            self.adapter.complete(
                claimed["dispatch_id"],
                output_text="阶段结果",
                completion_receipt={
                    "status": "completed", "verified": True,
                    "needs_user_input": False, "human_gate": True,
                },
            )
        with self.assertRaisesRegex(ValueError, "user input"):
            self.adapter.complete(
                claimed["dispatch_id"],
                output_text="阶段结果",
                completion_receipt={
                    "status": "completed", "verified": True,
                    "needs_user_input": True, "human_gate": False,
                },
            )
        self.assertEqual("RUNNING", self.adapter.get_dispatch(claimed["dispatch_id"])["status"])

    def test_expired_claim_is_recovered_without_creating_a_second_dispatch(self):
        broker = ExecutionBroker(self.store, {self.adapter.adapter_id: self.adapter})
        broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )
        first = self.adapter.claim_next(worker_id="lost-manager")
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE codex_project_dispatches SET lease_until = ? WHERE dispatch_id = ?",
                ("2000-01-01T00:00:00+00:00", first["dispatch_id"]),
            )

        recovered = self.adapter.claim_next(worker_id="replacement-manager")

        self.assertEqual(first["dispatch_id"], recovered["dispatch_id"])
        self.assertEqual("replacement-manager", recovered["worker_id"])
        self.assertEqual(1, len(self.adapter.active_dispatches()))

    def test_completion_is_single_owner_and_cannot_duplicate_the_artifact(self):
        broker = ExecutionBroker(self.store, {self.adapter.adapter_id: self.adapter})
        broker.dispatch(
            "science:hypothesis",
            adapter_id=self.adapter.adapter_id,
            model="gpt-5.6-sol",
        )
        claimed = self.adapter.claim_next(worker_id="manager-thread")
        self.adapter.bind_thread(
            claimed["dispatch_id"],
            thread_id="codex-thread-1",
            project_id="codex-project-expected",
            host_id="local",
            verification={
                "source": "task-project", "verified": True,
                "project_id": "codex-project-expected", "project_path": str(self.project),
                "environment": "worktree",
            },
        )
        self.adapter.complete(
            claimed["dispatch_id"],
            output_text="唯一结果",
            completion_receipt={
                "status": "completed", "verified": True,
                "needs_user_input": False, "human_gate": False,
            },
        )

        with self.assertRaisesRegex(ValueError, "not running"):
            self.adapter.complete(claimed["dispatch_id"], output_text="重复结果")

        self.assertEqual(1, len(self.store.snapshot()["artifacts"]))


if __name__ == "__main__":
    unittest.main()
