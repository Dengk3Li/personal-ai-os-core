import unittest

import personal_ai_os


class CandidatePromotionTests(unittest.TestCase):
    def test_human_decision_and_evidence_are_both_required(self):
        promote_candidate = getattr(personal_ai_os, "promote_candidate", None)
        self.assertTrue(callable(promote_candidate), "promote_candidate must be public")
        candidate = {
            "candidate_id": "candidate-001",
            "status": "CANDIDATE",
            "evidence_refs": ["evidence/demo.json"],
        }
        decision = {
            "kind": "human_final_decision",
            "candidate_id": "candidate-001",
            "approved": True,
        }

        accepted = promote_candidate(candidate, decision)
        blocked = promote_candidate({**candidate, "evidence_refs": []}, decision)

        self.assertEqual("ACCEPTED", accepted["status"])
        self.assertEqual("human_final_decision", accepted["authority"])
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertEqual("EVIDENCE_REQUIRED", blocked["reason"])
