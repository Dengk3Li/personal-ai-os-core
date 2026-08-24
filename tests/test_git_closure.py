import unittest

import personal_ai_os


class GitClosureTests(unittest.TestCase):
    def test_mainline_result_commit_is_ready_for_review_done_and_rollback(self):
        evaluate_git_closure = getattr(personal_ai_os, "evaluate_git_closure", None)
        self.assertTrue(callable(evaluate_git_closure), "evaluate_git_closure must be public")

        closure = evaluate_git_closure(
            {
                "result_kind": "result_commit",
                "result_commit": "a1b2c3d4",
                "integration_status": "mainline",
                "dirty_paths": [],
            }
        )

        self.assertEqual("READY", closure["status"])
        self.assertTrue(closure["review_ready"])
        self.assertTrue(closure["done_ready"])
        self.assertTrue(closure["archive_ready"])
        self.assertEqual(
            {"method": "revert", "commit": "a1b2c3d4"},
            closure["rollback"],
        )

    def test_uncommitted_task_changes_block_review(self):
        evaluate_git_closure = getattr(personal_ai_os, "evaluate_git_closure", None)
        self.assertTrue(callable(evaluate_git_closure), "evaluate_git_closure must be public")

        closure = evaluate_git_closure(
            {
                "result_kind": "result_commit",
                "result_commit": "a1b2c3d4",
                "integration_status": "mainline",
                "dirty_paths": ["src/private.py"],
            }
        )

        self.assertEqual("BLOCKED", closure["status"])
        self.assertFalse(closure["review_ready"])
        self.assertEqual("UNCOMMITTED_TASK_CHANGES", closure["reason"])

    def test_independent_candidate_needs_explicit_acceptance_before_done(self):
        evaluate_git_closure = getattr(personal_ai_os, "evaluate_git_closure", None)
        self.assertTrue(callable(evaluate_git_closure), "evaluate_git_closure must be public")
        candidate = {
            "result_kind": "result_commit",
            "result_commit": "a1b2c3d4",
            "integration_status": "independent_candidate",
            "dirty_paths": [],
        }

        pending = evaluate_git_closure(candidate)
        accepted = evaluate_git_closure(
            {**candidate, "accepted_independent_candidate": True}
        )

        self.assertTrue(pending["review_ready"])
        self.assertFalse(pending["done_ready"])
        self.assertEqual("CANDIDATE_ACCEPTANCE_REQUIRED", pending["reason"])
        self.assertTrue(accepted["done_ready"])

    def test_no_git_change_requires_an_explicit_attestation(self):
        evaluate_git_closure = getattr(personal_ai_os, "evaluate_git_closure", None)
        self.assertTrue(callable(evaluate_git_closure), "evaluate_git_closure must be public")

        missing = evaluate_git_closure(
            {"result_kind": "no_git_change", "dirty_paths": []}
        )
        attested = evaluate_git_closure(
            {
                "result_kind": "no_git_change",
                "attested_by": "owner:demo",
                "dirty_paths": [],
            }
        )

        self.assertEqual("RESULT_EVIDENCE_REQUIRED", missing["reason"])
        self.assertTrue(attested["done_ready"])
        self.assertEqual({"method": "none", "commit": None}, attested["rollback"])


if __name__ == "__main__":
    unittest.main()
