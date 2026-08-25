import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_os.codex_adapter import CodexAppServerAdapter


class _Input:
    def __init__(self):
        self.lines = []

    def write(self, value):
        self.lines.append(value)

    def flush(self):
        return None

    def close(self):
        return None


class _Process:
    def __init__(self, messages):
        self.stdin = _Input()
        self.stdout = iter(json.dumps(item) + "\n" for item in messages)
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode or 0


class CodexAppServerAdapterTests(unittest.TestCase):
    def test_supported_rpc_sequence_returns_a_bounded_result(self):
        process = _Process(
            [
                {"id": 1, "result": {"userAgent": "codex"}},
                {"id": 2, "result": {"thread": {"id": "thread-1"}}},
                {"id": 3, "result": {"turn": {"id": "turn-1"}}},
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "delta": "已完成任务",
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {
                            "id": "turn-1",
                            "status": "completed",
                            "usage": {"input_tokens": 12, "output_tokens": 4},
                        },
                    },
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            adapter = CodexAppServerAdapter(
                executable="codex",
                workspace_root=Path(temporary),
                popen=lambda *args, **kwargs: process,
                timeout=1,
            )
            result = adapter.start(
                {"task_id": "task-1"},
                model="gpt-test",
                context_pack={"task": "bounded"},
            )

        sent = [json.loads(line) for line in process.stdin.lines]
        self.assertTrue(result["ok"])
        self.assertEqual("thread-1:turn-1", result["external_run_id"])
        self.assertEqual("已完成任务", result["output_text"])
        self.assertEqual(
            ["initialize", "initialized", "thread/start", "turn/start"],
            [item["method"] for item in sent],
        )
        self.assertEqual("0.15.0", sent[0]["params"]["clientInfo"]["version"])
        self.assertEqual("never", sent[2]["params"]["approvalPolicy"])
        self.assertEqual("workspace-write", sent[2]["params"]["sandbox"])

    def test_interactive_approval_request_fails_closed(self):
        process = _Process(
            [
                {"id": 1, "result": {}},
                {"id": 2, "result": {"thread": {"id": "thread-1"}}},
                {"id": 99, "method": "item/commandExecution/requestApproval", "params": {}},
                {"id": 3, "result": {"turn": {"id": "turn-1"}}},
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            adapter = CodexAppServerAdapter(
                executable="codex",
                workspace_root=Path(temporary),
                popen=lambda *args, **kwargs: process,
                timeout=1,
            )
            result = adapter.start(
                {"task_id": "task-1"}, model="gpt-test", context_pack={}
            )

        self.assertFalse(result["ok"])
        self.assertEqual("CODEX_APP_SERVER_FAILED", result["reason"])

    def test_rpc_error_details_do_not_cross_the_adapter_boundary(self):
        process = _Process(
            [
                {
                    "id": 1,
                    "error": {"message": "token=PRIVATE_SENTINEL /Users/private"},
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            adapter = CodexAppServerAdapter(
                executable="codex",
                workspace_root=Path(temporary),
                popen=lambda *args, **kwargs: process,
                timeout=1,
            )
            result = adapter.start(
                {"task_id": "task-1"}, model="gpt-test", context_pack={}
            )

        self.assertEqual(
            {"ok": False, "reason": "CODEX_APP_SERVER_FAILED"}, result
        )
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))

    def test_only_the_final_agent_message_becomes_the_task_artifact(self):
        process = _Process(
            [
                {"id": 1, "result": {}},
                {"id": 2, "result": {"thread": {"id": "thread-1"}}},
                {"id": 3, "result": {"turn": {"id": "turn-1"}}},
                {
                    "method": "item/agentMessage/delta",
                    "params": {"itemId": "message-1", "delta": "过程说明"},
                },
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "id": "message-1",
                            "type": "agentMessage",
                            "phase": "commentary",
                            "text": "过程说明",
                        }
                    },
                },
                {
                    "method": "item/agentMessage/delta",
                    "params": {"itemId": "message-2", "delta": "最终业务结果"},
                },
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "id": "message-2",
                            "type": "agentMessage",
                            "phase": "final",
                            "text": "最终业务结果",
                        }
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-1",
                        "turn": {"id": "turn-1", "status": "completed"},
                    },
                },
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            adapter = CodexAppServerAdapter(
                executable="codex",
                workspace_root=Path(temporary),
                popen=lambda *args, **kwargs: process,
                timeout=1,
            )
            result = adapter.start(
                {"task_id": "task-1"}, model="gpt-test", context_pack={}
            )

        self.assertEqual("最终业务结果", result["output_text"])
        self.assertNotIn("过程说明", result["output_text"])
