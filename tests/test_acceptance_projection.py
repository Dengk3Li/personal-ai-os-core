"""Read-only acceptance projection contract tests.

The projection joins existing task, run, event, artifact and review facts.  It
does not transition state, register an artifact, or infer acceptance from a
terminal executor message alone.
"""

import tempfile
import unittest
from pathlib import Path

from personal_ai_os.acceptance_projection import build_acceptance_snapshot
from personal_ai_os.runtime import RuntimeStore, install_workflow_preset
from personal_ai_os.server import runtime_workbench_state


class AcceptanceProjectionTests(unittest.TestCase):
    def test_unassigned_card_keeps_causality_without_execution_claim(self):
        card = {
            "task_id": "T-001",
            "title": "整理材料",
            "status": "QUEUED",
            "line": "research",
            "presentation": {
                "why": "上游材料已准备，需要整理为可核对事实。",
                "now": "等待安排执行者。",
                "next": "选择执行模型并开始整理。",
                "relationship": "完成后继续报告规划。",
            },
        }

        result = build_acceptance_snapshot(card)

        self.assertEqual(
            result["task"],
            {
                "task_id": "T-001",
                "title": "整理材料",
                "status": "QUEUED",
                "line": "research",
            },
        )
        self.assertEqual(result["causality"]["background"], "上游材料已准备，需要整理为可核对事实。")
        self.assertEqual(result["execution"]["status"], "NOT_DISPATCHED")
        self.assertEqual(result["timeline"], [])
        self.assertEqual(result["stage_artifacts"], [])
        self.assertEqual(result["review"]["status"], "NOT_READY")

    def test_running_execution_keeps_binding_timeline_and_stage_artifacts(self):
        card = {
            "task_id": "T-002",
            "title": "生成方案",
            "status": "IN_PROGRESS",
            "line": "research",
            "presentation": {
                "why": "假设已形成，需要转成可执行方案。",
                "now": "方案设计正在进行。",
                "next": "等待方案产物并核对。",
                "relationship": "完成后交给执行阶段。",
            },
        }
        run = {
            "run_id": "run-002",
            "task_id": "T-002",
            "status": "RUNNING",
            "adapter_id": "codex-project",
            "model": "model-test",
            "started_at": "2026-08-26T01:02:03+08:00",
            "binding": {"conversation_id": "thread-002"},
        }
        events = [
            {"event_type": "ADAPTER_STARTED", "at": "2026-08-26T01:02:04+08:00", "run_id": "run-002"},
            {"event_type": "HEARTBEAT", "at": "2026-08-26T01:02:07+08:00", "run_id": "run-002"},
        ]
        artifacts = [{
            "artifact_id": "artifact-protocol",
            "task_id": "T-002",
            "run_id": "run-002",
            "kind": "protocol",
            "summary": "方案阶段产物",
            "created_at": "2026-08-26T01:02:08+08:00",
        }]

        result = build_acceptance_snapshot(card, run, events=events, artifacts=artifacts)

        self.assertEqual(result["execution"]["status"], "RUNNING")
        self.assertEqual(result["execution"]["thread_id"], "thread-002")
        self.assertEqual(result["execution"]["model_id"], "model-test")
        self.assertEqual([item["type"] for item in result["timeline"]], [
            "ADAPTER_STARTED", "HEARTBEAT",
        ])
        self.assertEqual(result["stage_artifacts"][0]["artifact_ref"], "artifact-protocol")
        self.assertNotIn("content", result["stage_artifacts"][0])
        self.assertEqual(result["review"]["status"], "NOT_READY")

    def test_terminal_artifact_is_ready_for_review_but_not_accepted(self):
        card = {
            "task_id": "T-003",
            "title": "分析数据",
            "status": "IN_PROGRESS",
            "line": "research",
            "presentation": {},
        }
        run = {
            "run_id": "run-003",
            "task_id": "T-003",
            "status": "SUCCEEDED",
            "adapter_id": "codex-project",
            "model": "model-test",
            "started_at": "2026-08-26T01:00:00+08:00",
            "ended_at": "2026-08-26T01:03:00+08:00",
            "binding": {"conversation_id": "thread-003"},
        }
        artifacts = [{
            "artifact_id": "artifact-result",
            "task_id": "T-003",
            "run_id": "run-003",
            "summary": "结果草案",
            "created_at": "2026-08-26T01:03:00+08:00",
        }]

        result = build_acceptance_snapshot(card, run, artifacts=artifacts)

        self.assertEqual(result["execution"]["status"], "TERMINAL")
        self.assertEqual(result["review"]["status"], "READY_FOR_REVIEW")
        self.assertEqual(result["review"]["evidence"], ["artifact-result"])
        self.assertFalse(result["review"]["accepted"])

    def test_review_and_done_are_distinct_display_states(self):
        base = {
            "task_id": "T-004",
            "title": "复核报告",
            "line": "writing",
            "presentation": {},
        }
        run = {
            "run_id": "run-004",
            "status": "SUCCEEDED",
            "started_at": "2026-08-26T01:00:00+08:00",
            "ended_at": "2026-08-26T01:01:00+08:00",
        }
        review = build_acceptance_snapshot({**base, "status": "REVIEW"}, run)
        done = build_acceptance_snapshot({**base, "status": "DONE"}, run)

        self.assertEqual(review["review"]["status"], "IN_REVIEW")
        self.assertFalse(review["review"]["accepted"])
        self.assertEqual(done["review"]["status"], "ACCEPTED")
        self.assertTrue(done["review"]["accepted"])

    def test_missing_ended_at_or_failed_run_cannot_look_accepted(self):
        card = {"task_id": "T-005", "title": "未知结果", "status": "IN_PROGRESS", "line": "research"}
        run = {"run_id": "run-005", "status": "FAILED", "ended_at": None}

        result = build_acceptance_snapshot(card, run)

        self.assertEqual(result["execution"]["status"], "FAILED")
        self.assertEqual(result["review"]["status"], "FAILED")
        self.assertFalse(result["review"]["accepted"])

    def test_runtime_workbench_state_attaches_read_only_acceptance_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            install_workflow_preset(store, "science")
            state = runtime_workbench_state(store)
            task = next(item for item in state["tasks"] if item["task_id"] == "science:hypothesis")

            self.assertEqual(
                "personal-ai-os.acceptance/v1",
                task["acceptance_snapshot"]["schema_version"],
            )
            self.assertEqual("NOT_DISPATCHED", task["acceptance_snapshot"]["execution"]["status"])
            self.assertEqual("NOT_READY", task["acceptance_snapshot"]["review"]["status"])
            self.assertNotIn("context", task["acceptance_snapshot"])


if __name__ == "__main__":
    unittest.main()
