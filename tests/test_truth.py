import unittest

import personal_ai_os


class TruthCompilerTests(unittest.TestCase):
    def test_views_cannot_override_an_accepted_receipt(self):
        compile_truth = getattr(personal_ai_os, "compile_truth", None)
        self.assertTrue(callable(compile_truth), "compile_truth must be public")
        manifest = {
            "required_claims": [{"subject": "project:demo", "field": "status"}],
            "sources": [
                {
                    "id": "receipt-1",
                    "kind": "acceptance_receipt",
                    "accepted": True,
                    "claims": [
                        {"subject": "project:demo", "field": "status", "value": "ACTIVE"}
                    ],
                },
                {
                    "id": "dashboard-1",
                    "kind": "status_view",
                    "accepted": True,
                    "claims": [
                        {"subject": "project:demo", "field": "status", "value": "BLOCKED"}
                    ],
                },
            ],
        }

        result = compile_truth(manifest)

        selected = result["truth"]["project:demo"]["status"]
        self.assertEqual("ACTIVE", selected["value"])
        self.assertEqual("acceptance_receipt", selected["authority"])
        self.assertTrue(result["safe"])

    def test_equal_authority_conflict_fails_closed(self):
        compile_truth = getattr(personal_ai_os, "compile_truth", None)
        self.assertTrue(callable(compile_truth), "compile_truth must be public")
        manifest = {
            "required_claims": [{"subject": "project:demo", "field": "status"}],
            "sources": [
                {
                    "id": "receipt-a",
                    "kind": "acceptance_receipt",
                    "accepted": True,
                    "claims": [
                        {"subject": "project:demo", "field": "status", "value": "ACTIVE"}
                    ],
                },
                {
                    "id": "receipt-b",
                    "kind": "acceptance_receipt",
                    "accepted": True,
                    "claims": [
                        {"subject": "project:demo", "field": "status", "value": "PAUSED"}
                    ],
                },
            ],
        }

        result = compile_truth(manifest)

        selected = result["truth"]["project:demo"]["status"]
        self.assertEqual("UNKNOWN", selected["value"])
        self.assertEqual("CONFLICT", selected["authority"])
        self.assertFalse(result["safe"])
