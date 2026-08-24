import unittest

import personal_ai_os


class WorkflowStateTests(unittest.TestCase):
    def test_review_requires_a_review_ready_git_closure(self):
        transition_task = getattr(personal_ai_os, "transition_task", None)
        self.assertTrue(callable(transition_task), "transition_task must be public")
        card = {"task_id": "task-001", "status": "IN_PROGRESS"}

        blocked = transition_task(card, "REVIEW", by="agent:demo")
        ready = transition_task(
            {
                **card,
                "git_closure": {"review_ready": True, "done_ready": False},
            },
            "REVIEW",
            by="agent:demo",
            at="2026-08-24T12:00:00+08:00",
        )

        self.assertFalse(blocked["ok"])
        self.assertEqual("GIT_CLOSURE_REVIEW_REQUIRED", blocked["reason"])
        self.assertTrue(ready["ok"])
        self.assertEqual("REVIEW_REQUESTED", ready["event"]["event"])
        self.assertEqual("2026-08-24T12:00:00+08:00", ready["event"]["at"])
        self.assertEqual("IN_PROGRESS", card["status"], "transition must not mutate the card")

    def test_done_requires_a_done_ready_git_closure(self):
        transition_task = getattr(personal_ai_os, "transition_task", None)
        self.assertTrue(callable(transition_task), "transition_task must be public")

        result = transition_task(
            {
                "task_id": "task-001",
                "status": "REVIEW",
                "git_closure": {"review_ready": True, "done_ready": False},
            },
            "DONE",
            by="owner:demo",
        )

        self.assertFalse(result["ok"])
        self.assertEqual("GIT_CLOSURE_DONE_REQUIRED", result["reason"])

    def test_non_git_task_requires_a_registered_result_instead_of_git_closure(self):
        transition_task = getattr(personal_ai_os, "transition_task", None)
        missing = transition_task(
            {"task_id": "task-001", "status": "IN_PROGRESS", "requires_git_closure": False},
            "REVIEW",
            by="agent:demo",
        )
        ready = transition_task(
            {
                "task_id": "task-001",
                "status": "IN_PROGRESS",
                "requires_git_closure": False,
                "result_ref": "artifact-001",
            },
            "REVIEW",
            by="agent:demo",
        )

        self.assertEqual("RESULT_EVIDENCE_REQUIRED", missing["reason"])
        self.assertTrue(ready["ok"])

    def test_block_and_resume_are_explicit_and_reversible(self):
        transition_task = getattr(personal_ai_os, "transition_task", None)
        self.assertTrue(callable(transition_task), "transition_task must be public")
        card = {"task_id": "task-001", "status": "IN_PROGRESS"}

        missing_reason = transition_task(card, "BLOCKED", by="agent:demo")
        blocked = transition_task(
            card,
            "BLOCKED",
            by="agent:demo",
            reason="waiting for owner decision",
        )
        resumed = transition_task(
            {
                "task_id": "task-001",
                "status": "BLOCKED",
                "resume_to": "IN_PROGRESS",
            },
            "IN_PROGRESS",
            by="owner:demo",
            reason="decision recorded",
        )

        self.assertEqual("REASON_REQUIRED", missing_reason["reason"])
        self.assertEqual("IN_PROGRESS", blocked["event"]["resume_to"])
        self.assertEqual("UNBLOCKED", resumed["event"]["event"])


if __name__ == "__main__":
    unittest.main()
