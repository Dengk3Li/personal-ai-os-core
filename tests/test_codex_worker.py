import unittest

from personal_ai_os.codex_worker import run_once, finish_once


class FakeAdapter:
    def __init__(self, dispatch=None):
        self.dispatch = dispatch
        self.bound = []
        self.completed = []

    def claim_next(self, *, worker_id):
        return self.dispatch

    def bind_thread(self, dispatch_id, **payload):
        self.bound.append((dispatch_id, payload))
        return {"status": "RUNNING"}

    def complete(self, dispatch_id, **payload):
        self.completed.append((dispatch_id, payload))
        return {"status": "REVIEW"}


class FakeHost:
    def __init__(self, creation=None, terminal=None):
        self.creation = creation
        self.terminal = terminal

    def create_task(self, **_kwargs):
        return self.creation

    def read_terminal(self, **_kwargs):
        return self.terminal


def pending_dispatch():
    return {
        "dispatch_id": "dispatch-1",
        "task_id": "task-1",
        "model": "model-a",
        "prompt": "do bounded work",
        "project": {
            "project_id": "project-1",
            "path": "/tmp/project-1",
            "environment": "worktree",
        },
    }


class CodexWorkerTests(unittest.TestCase):
    def test_empty_queue_is_idle(self):
        result = run_once(FakeAdapter(), FakeHost(), worker_id="worker-1")
        self.assertEqual({"status": "IDLE", "reason": "QUEUE_EMPTY"}, result)

    def test_unverified_thread_is_not_bound(self):
        adapter = FakeAdapter(pending_dispatch())
        host = FakeHost(
            creation={
                "thread_id": "thread-1",
                "project_id": "project-1",
                "host_id": "local",
                "verification": {"verified": False},
            }
        )
        result = run_once(adapter, host, worker_id="worker-1")
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("THREAD_PROJECT_UNVERIFIED", result["reason"])
        self.assertEqual([], adapter.bound)

    def test_verified_thread_is_bound_to_the_claimed_project(self):
        adapter = FakeAdapter(pending_dispatch())
        host = FakeHost(
            creation={
                "thread_id": "thread-1",
                "project_id": "project-1",
                "host_id": "local",
                "verification": {
                    "verified": True,
                    "source": "thread-project-assignments",
                    "project_id": "project-1",
                    "project_path": "/tmp/project-1",
                    "environment": "worktree",
                },
            }
        )
        result = run_once(adapter, host, worker_id="worker-1")
        self.assertEqual("RUNNING", result["status"])
        self.assertEqual("thread-1", adapter.bound[0][1]["thread_id"])

    def test_non_terminal_host_result_stays_running(self):
        adapter = FakeAdapter()
        host = FakeHost(terminal={"status": "running"})
        result = finish_once(adapter, host, "dispatch-1")
        self.assertEqual({"status": "RUNNING", "reason": "TERMINAL_RECEIPT_PENDING"}, result)
        self.assertEqual([], adapter.completed)

    def test_verified_terminal_receipt_can_complete(self):
        adapter = FakeAdapter()
        host = FakeHost(
            terminal={
                "status": "completed",
                "output_text": "bounded result",
                "receipt": {
                    "status": "completed",
                    "verified": True,
                    "needs_user_input": False,
                    "human_gate": False,
                },
            }
        )
        result = finish_once(adapter, host, "dispatch-1")
        self.assertEqual("REVIEW", result["status"])
        self.assertEqual(1, len(adapter.completed))


if __name__ == "__main__":
    unittest.main()
