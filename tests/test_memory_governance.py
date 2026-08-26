import copy
import json
import unittest

from personal_ai_os.memory_governance import (
    MEMORY_READ_RECEIPT_VERSION,
    MEMORY_UPDATE_CANDIDATE_VERSION,
    validate_memory_read_receipt,
    validate_memory_update_candidate,
)


class MemoryGovernanceTests(unittest.TestCase):
    def valid_read_receipt(self):
        return {
            "schema_version": MEMORY_READ_RECEIPT_VERSION,
            "receipt_ref": "memory-read-001",
            "task_ref": "task-001",
            "memory_refs": ["memory-001", "memory-002"],
            "scope": {
                "subject_ref": "subject-001",
                "domain_ref": "domain-001",
            },
            "authority": {
                "status": "approved",
                "decision_ref": "decision-001",
            },
            "freshness": {
                "observed_at": "2026-08-26T00:00:00Z",
                "expires_at": "2026-08-27T00:00:00Z",
            },
            "read_before_run": True,
        }

    def valid_update_candidate(self):
        return {
            "schema_version": MEMORY_UPDATE_CANDIDATE_VERSION,
            "candidate_ref": "memory-update-001",
            "read_receipt_ref": "memory-read-001",
            "source_refs": ["artifact-001", "run-001"],
            "scope": {
                "subject_ref": "subject-001",
                "domain_ref": "domain-001",
            },
            "review": {"status": "proposed"},
        }

    def test_read_receipt_is_scoped_authorized_fresh_and_pre_run(self):
        result = validate_memory_read_receipt(self.valid_read_receipt())

        self.assertEqual(MEMORY_READ_RECEIPT_VERSION, result["schema_version"])
        self.assertEqual("APPROVED", result["authority"]["status"])
        self.assertTrue(result["read_before_run"])
        self.assertEqual(
            ["memory-001", "memory-002"], result["memory_refs"]
        )

    def test_read_receipt_rejects_unapproved_stale_or_post_run_reads(self):
        for field, value in (
            ("read_before_run", False),
            ("authority", {"status": "PROPOSED", "decision_ref": "decision-001"}),
            (
                "freshness",
                {
                    "observed_at": "2026-08-27T00:00:00Z",
                    "expires_at": "2026-08-26T00:00:00Z",
                },
            ),
        ):
            payload = self.valid_read_receipt()
            payload[field] = value
            with self.assertRaises(ValueError):
                validate_memory_read_receipt(payload)

    def test_update_candidate_requires_a_valid_read_receipt_reference_and_review(self):
        result = validate_memory_update_candidate(self.valid_update_candidate())

        self.assertEqual(MEMORY_UPDATE_CANDIDATE_VERSION, result["schema_version"])
        self.assertEqual("PROPOSED", result["review"]["status"])
        self.assertEqual("memory-read-001", result["read_receipt_ref"])

        candidate = self.valid_update_candidate()
        candidate["review"] = {"status": "APPROVED"}
        with self.assertRaises(ValueError):
            validate_memory_update_candidate(candidate)

        candidate = self.valid_update_candidate()
        candidate["review"] = {
            "status": "APPROVED",
            "reviewer_ref": "reviewer-001",
            "decision_ref": "decision-002",
        }
        result = validate_memory_update_candidate(candidate)
        self.assertEqual("APPROVED", result["review"]["status"])

    def test_contracts_reject_body_paths_credentials_and_unknown_fields(self):
        for key, value in (
            ("body", "private memory"),
            ("path", "/Users/private/memory"),
            ("api_key", "secret-value"),
        ):
            receipt = self.valid_read_receipt()
            receipt[key] = value
            with self.assertRaises(ValueError):
                validate_memory_read_receipt(receipt)

            candidate = self.valid_update_candidate()
            candidate[key] = value
            with self.assertRaises(ValueError):
                validate_memory_update_candidate(candidate)

        receipt = self.valid_read_receipt()
        receipt["memory_refs"] = ["/private/memory"]
        with self.assertRaises(ValueError):
            validate_memory_read_receipt(receipt)

        candidate = self.valid_update_candidate()
        candidate["scope"]["domain_ref"] = "私人领域"
        with self.assertRaises(ValueError):
            validate_memory_update_candidate(candidate)

    def test_candidate_does_not_accept_an_activation_or_mutate_input(self):
        candidate = self.valid_update_candidate()
        candidate["promotion"] = {"authorized": True}
        before = json.dumps(candidate, sort_keys=True)
        with self.assertRaises(ValueError):
            validate_memory_update_candidate(candidate)
        self.assertEqual(before, json.dumps(candidate, sort_keys=True))

        candidate = self.valid_update_candidate()
        before = copy.deepcopy(candidate)
        result = validate_memory_update_candidate(candidate)
        self.assertEqual(before, candidate)
        self.assertNotIn("body", result)
        self.assertNotIn("statement", result)


if __name__ == "__main__":
    unittest.main()
