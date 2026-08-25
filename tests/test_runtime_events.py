import json
import unittest

from personal_ai_os.runtime_events import (
    EVENT_TYPES,
    EventValidationError,
    build_envelope,
    from_legacy_event,
    to_sse,
)


class RuntimeEventEnvelopeTests(unittest.TestCase):
    def test_process_event_has_versioned_run_task_correlation(self):
        envelope = build_envelope(
            event_type="started",
            run_id="run-1",
            task_id="task-1",
            source="execution-adapter",
            occurred_at="2026-08-26T08:00:00+08:00",
            action={"adapter_id": "adapter-1"},
            observation={"state": "IN_PROGRESS"},
            attempt=2,
        )

        self.assertEqual("personal-ai-os.runtime-event/v1", envelope["schema_version"])
        self.assertEqual(
            {
                "id": "run-1:2:started:2026-08-26T08:00:00+08:00",
                "type": "started",
                "kind": "process",
                "source": "execution-adapter",
                "occurred_at": "2026-08-26T08:00:00+08:00",
            },
            envelope["event"],
        )
        self.assertEqual(
            {"run_id": "run-1", "task_id": "task-1", "attempt": 2},
            envelope["run"],
        )
        self.assertEqual("IN_PROGRESS", envelope["observation"]["state"])
        self.assertIsNone(envelope["receipt"]["terminal"])

    def test_terminal_event_separates_artifact_review_decision_and_recovery(self):
        envelope = build_envelope(
            event_type="terminal",
            run_id="run-2",
            task_id="task-2",
            source="execution-adapter",
            occurred_at="2026-08-26T08:01:00+08:00",
            artifact={"ref": "artifact-2", "final": True},
            review={"status": "requested"},
            decision={"status": "none"},
            terminal={"outcome": "failed", "error_code": "ADAPTER_FAILED"},
            recovery_gate={
                "required": True,
                "reason": "外部状态未知",
                "next_action": "重新读取执行端回执",
            },
        )

        self.assertEqual("terminal", envelope["event"]["kind"])
        self.assertTrue(envelope["receipt"]["artifact"]["final"])
        self.assertEqual("requested", envelope["receipt"]["review"]["status"])
        self.assertEqual("failed", envelope["receipt"]["terminal"]["outcome"])
        self.assertTrue(envelope["receipt"]["recovery_gate"]["required"])

    def test_invalid_event_type_or_missing_run_is_rejected(self):
        with self.assertRaises(EventValidationError):
            build_envelope(event_type="unknown", run_id="run-1")
        with self.assertRaises(EventValidationError):
            build_envelope(event_type="started", run_id="")
        with self.assertRaises(EventValidationError):
            build_envelope(event_type="artifact", run_id="run-1")

    def test_legacy_event_keeps_shape_and_adds_canonical_runtime_projection(self):
        legacy = {
            "event_id": "17",
            "task_id": "task-3",
            "run_id": "run-3",
            "event_type": "RUN_SUCCEEDED",
            "payload": {"artifact_id": "artifact-3"},
            "at": "2026-08-26T08:02:00+08:00",
        }

        projected = from_legacy_event(legacy)

        self.assertEqual(legacy["event_type"], projected["event_type"])
        self.assertEqual("run-3", projected["runtime"]["run"]["run_id"])
        self.assertEqual("terminal", projected["runtime"]["event"]["type"])
        self.assertEqual(
            "artifact-3",
            projected["runtime"]["receipt"]["artifact"]["ref"],
        )
        self.assertEqual("succeeded", projected["runtime"]["receipt"]["terminal"]["outcome"])

    def test_legacy_event_without_run_is_rejected_fail_closed(self):
        with self.assertRaises(EventValidationError):
            from_legacy_event(
                {
                    "event_id": "18",
                    "task_id": "task-4",
                    "event_type": "DECISION_REQUESTED",
                    "payload": {"decision_id": "decision-4"},
                    "at": "2026-08-26T08:03:00+08:00",
                }
            )

    def test_sse_serialization_preserves_legacy_event_and_runtime_envelope(self):
        payload = json.loads(
            to_sse(
                {
                    "event_id": "19",
                    "task_id": "task-5",
                    "run_id": "run-5",
                    "event_type": "RUN_SUCCEEDED",
                    "payload": {"artifact_id": "artifact-5"},
                    "at": "2026-08-26T08:04:00+08:00",
                }
            ).removeprefix("data: ").strip()
        )
        self.assertEqual("RUN_SUCCEEDED", payload["event_type"])
        self.assertEqual("terminal", payload["runtime"]["event"]["type"])

    def test_legacy_feedback_event_maps_stale_execution_to_recovery_terminal(self):
        projected = from_legacy_event(
            {
                "type": "feedback",
                "run_id": "run-6",
                "card": "task-6",
                "state": "running",
                "feedback_state": "stale",
                "feedback": {
                    "kind": "stale",
                    "blocker": "receipt missing",
                    "next_action": "read the executor receipt",
                },
                "ts": "2026-08-26T08:05:00+08:00",
            }
        )

        self.assertEqual("terminal", projected["runtime"]["event"]["type"])
        self.assertTrue(projected["runtime"]["receipt"]["recovery_gate"]["required"])
        self.assertEqual(
            "read the executor receipt",
            projected["runtime"]["receipt"]["recovery_gate"]["next_action"],
        )

    def test_event_types_cover_process_and_receipt_layers(self):
        self.assertEqual(
            EVENT_TYPES,
            frozenset(
                {
                    "requested",
                    "claimed",
                    "started",
                    "heartbeat",
                    "artifact",
                    "review",
                    "decision",
                    "terminal",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
