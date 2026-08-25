"""Contract tests for the public, synthetic research-report acceptance fixture."""

import json
import unittest
from pathlib import Path

from personal_ai_os.research_report_acceptance import (
    SCHEMA_VERSION,
    ResearchReportAcceptanceError,
    build_research_report_acceptance,
    synthetic_research_report_fixture,
    validate_research_report_acceptance,
)


class ResearchReportAcceptanceTests(unittest.TestCase):
    def test_fixture_is_synthetic_and_contains_only_report_stages(self):
        fixture = synthetic_research_report_fixture()

        self.assertEqual(SCHEMA_VERSION, fixture["schema_version"])
        self.assertTrue(fixture["synthetic_only"])
        self.assertEqual(
            {
                "schema_version",
                "synthetic_only",
                "brief",
                "source_manifest",
                "evidence_matrix",
                "outline",
                "chapters",
                "visual",
                "final_receipt",
                "review",
            },
            set(fixture),
        )
        self.assertEqual("IN_REVIEW", fixture["review"]["status"])

    def test_checked_in_json_fixture_obeys_the_same_contract(self):
        path = Path(__file__).parents[1] / "examples" / "research_report_acceptance.synthetic.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))

        result = validate_research_report_acceptance(fixture)

        self.assertEqual("IN_REVIEW", result["status"])
        self.assertTrue(fixture["synthetic_only"])

    def test_source_conflict_and_unknown_require_human_review(self):
        fixture = synthetic_research_report_fixture()
        fixture["source_manifest"] = [
            {"source_id": "source-a", "kind": "synthetic", "status": "KNOWN"},
            {"source_id": "source-b", "kind": "synthetic", "status": "UNKNOWN"},
            {"source_id": "source-c", "kind": "synthetic", "status": "CONFLICT"},
        ]

        result = validate_research_report_acceptance(fixture)

        self.assertEqual("IN_REVIEW", result["status"])
        self.assertEqual(
            ["SOURCE_UNKNOWN", "SOURCE_CONFLICT"],
            result["reasons"],
        )
        self.assertFalse(result["accepted"])

    def test_terminal_artifact_is_not_research_completion(self):
        fixture = synthetic_research_report_fixture()
        fixture["source_manifest"] = [
            {"source_id": "source-a", "kind": "synthetic", "status": "KNOWN"},
        ]
        fixture["final_receipt"] = {
            "artifact_terminal": True,
            "human_accepted": False,
            "receipt_ref": "receipt-synthetic",
        }

        result = validate_research_report_acceptance(fixture)

        self.assertEqual("READY_FOR_REVIEW", result["status"])
        self.assertEqual(["HUMAN_ACCEPTANCE_REQUIRED"], result["reasons"])
        self.assertFalse(result["accepted"])

    def test_only_explicit_human_acceptance_can_close_a_clean_report(self):
        fixture = synthetic_research_report_fixture()
        fixture["source_manifest"] = [
            {"source_id": "source-a", "kind": "synthetic", "status": "KNOWN"},
        ]
        fixture["final_receipt"] = {
            "artifact_terminal": True,
            "human_accepted": True,
            "receipt_ref": "receipt-synthetic",
        }

        result = validate_research_report_acceptance(fixture)

        self.assertEqual("ACCEPTED", result["status"])
        self.assertEqual([], result["reasons"])
        self.assertTrue(result["accepted"])

    def test_builder_rejects_non_synthetic_input(self):
        fixture = synthetic_research_report_fixture()
        with self.assertRaises(ResearchReportAcceptanceError):
            build_research_report_acceptance(
                synthetic_only=False,
                brief=fixture["brief"],
                source_manifest=fixture["source_manifest"],
                evidence_matrix=fixture["evidence_matrix"],
                outline=fixture["outline"],
                chapters=fixture["chapters"],
                visual=fixture["visual"],
                final_receipt=fixture["final_receipt"],
            )

    def test_schema_rejects_private_paths_and_network_sources(self):
        fixture = synthetic_research_report_fixture()
        fixture["source_manifest"][0]["reference"] = "/private/source.txt"

        with self.assertRaises(ResearchReportAcceptanceError):
            validate_research_report_acceptance(fixture)

    def test_schema_rejects_source_content_outside_the_structural_fields(self):
        fixture = synthetic_research_report_fixture()
        fixture["source_manifest"][0]["content"] = "synthetic source body"

        with self.assertRaises(ResearchReportAcceptanceError):
            validate_research_report_acceptance(fixture)


if __name__ == "__main__":
    unittest.main()
