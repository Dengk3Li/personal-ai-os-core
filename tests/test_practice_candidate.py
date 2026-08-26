import json
import unittest
from pathlib import Path

from personal_ai_os.practice_candidate import (
    PRACTICE_CANDIDATE_VERSION,
    validate_practice_candidate,
)


ROOT = Path(__file__).resolve().parents[1]


class PracticeCandidateTests(unittest.TestCase):
    def valid_candidate(self):
        return {
            "schema_version": PRACTICE_CANDIDATE_VERSION,
            "candidate_id": "candidate-001",
            "source_refs": ["artifact:source-001", "run:source-002"],
            "scope": {
                "subject_ref": "subject-001",
                "domain_ref": "domain-001",
            },
            "review": {"status": "PROPOSED"},
        }

    def test_candidate_keeps_only_refs_scope_and_review_state(self):
        result = validate_practice_candidate(self.valid_candidate())

        self.assertEqual(PRACTICE_CANDIDATE_VERSION, result["schema_version"])
        self.assertEqual("candidate-001", result["candidate_id"])
        self.assertEqual(["artifact:source-001", "run:source-002"], result["source_refs"])
        self.assertEqual(
            {"subject_ref": "subject-001", "domain_ref": "domain-001"},
            result["scope"],
        )
        self.assertEqual({"status": "PROPOSED"}, result["review"])

    def test_reviewed_candidate_requires_a_human_reviewer_reference(self):
        for status in ("APPROVED", "REJECTED"):
            candidate = self.valid_candidate()
            candidate["review"] = {"status": status, "reviewer_ref": "reviewer-001"}
            result = validate_practice_candidate(candidate)
            self.assertEqual(status, result["review"]["status"])
            self.assertEqual("reviewer-001", result["review"]["reviewer_ref"])

        candidate = self.valid_candidate()
        candidate["review"] = {"status": "APPROVED"}
        with self.assertRaises(ValueError):
            validate_practice_candidate(candidate)

    def test_candidate_rejects_body_paths_business_labels_and_unknown_fields(self):
        candidate = self.valid_candidate()
        candidate["statement"] = "private practice body"
        with self.assertRaises(ValueError):
            validate_practice_candidate(candidate)

        candidate = self.valid_candidate()
        candidate["source_refs"] = ["/Users/private/source"]
        with self.assertRaises(ValueError):
            validate_practice_candidate(candidate)

        candidate = self.valid_candidate()
        candidate["scope"]["domain_ref"] = "行业研究"
        with self.assertRaises(ValueError):
            validate_practice_candidate(candidate)

        candidate = self.valid_candidate()
        candidate["api_key"] = "secret-value"
        with self.assertRaises(ValueError):
            validate_practice_candidate(candidate)

    def test_candidate_errors_do_not_echo_private_values_or_mutate_input(self):
        candidate = self.valid_candidate()
        candidate["scope"]["subject_ref"] = "/private/subject"
        before = json.dumps(candidate, sort_keys=True)

        with self.assertRaises(ValueError) as raised:
            validate_practice_candidate(candidate)

        self.assertNotIn("/private/subject", str(raised.exception))
        self.assertEqual(before, json.dumps(candidate, sort_keys=True))

    def test_repository_fixture_is_synthetic_and_validates_as_reference_only(self):
        fixture = json.loads(
            (ROOT / "examples" / "practice_candidate.synthetic.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(fixture, validate_practice_candidate(fixture))
        self.assertEqual({"status": "PROPOSED"}, fixture["review"])
        self.assertEqual(1, len(fixture["source_refs"]))
        self.assertEqual(
            {"subject_ref", "domain_ref"},
            set(fixture["scope"]),
        )
        self.assertNotIn(
            "statement",
            fixture,
        )
        self.assertNotIn(
            "business_label",
            json.dumps(fixture, ensure_ascii=False),
        )
        self.assertNotIn("credential", json.dumps(fixture, ensure_ascii=False))
        for reference in [
            fixture["candidate_id"],
            *fixture["source_refs"],
            *fixture["scope"].values(),
        ]:
            self.assertNotIn("/", reference)


if __name__ == "__main__":
    unittest.main()
