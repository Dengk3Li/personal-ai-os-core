import json
import unittest
from pathlib import Path

from personal_ai_os.task_causality import (
    TASK_CAUSALITY_VERSION,
    validate_task_causality,
)


class TaskCausalityTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def valid_record(self):
        return {
            "schema_version": TASK_CAUSALITY_VERSION,
            "task_ref": "task-001",
            "inputs": [
                {"ref": "artifact-input", "status": "available"},
            ],
            "current_action": {
                "ref": "action-001",
                "status": "in_progress",
                "run_ref": "run-001",
            },
            "artifacts": [
                {"ref": "artifact-output", "status": "created"},
            ],
            "downstream": [
                {"ref": "task-002", "relation": "enables", "status": "pending"},
            ],
            "next_action": {"ref": "action-002", "status": "ready"},
        }

    def test_normalizes_the_causal_handoff_chain(self):
        result = validate_task_causality(self.valid_record())

        self.assertEqual(TASK_CAUSALITY_VERSION, result["schema_version"])
        self.assertEqual("AVAILABLE", result["inputs"][0]["status"])
        self.assertEqual("IN_PROGRESS", result["current_action"]["status"])
        self.assertEqual("CREATED", result["artifacts"][0]["status"])
        self.assertEqual("ENABLES", result["downstream"][0]["relation"])
        self.assertEqual("READY", result["next_action"]["status"])

    def test_empty_collections_are_normalized_without_free_text(self):
        record = self.valid_record()
        record.pop("inputs")
        record.pop("artifacts")
        record.pop("downstream")

        result = validate_task_causality(record)

        self.assertEqual([], result["inputs"])
        self.assertEqual([], result["artifacts"])
        self.assertEqual([], result["downstream"])

    def test_rejects_paths_credentials_business_fields_and_free_text(self):
        for field, value in (
            ("task_ref", "/Users/private/task"),
            ("task_ref", "task title"),
        ):
            record = self.valid_record()
            record[field] = value
            with self.assertRaises(ValueError):
                validate_task_causality(record)

        record = self.valid_record()
        record["current_action"]["summary"] = "private task body"
        with self.assertRaises(ValueError):
            validate_task_causality(record)

        record = self.valid_record()
        record["artifacts"][0]["path"] = "/private/output"
        with self.assertRaises(ValueError):
            validate_task_causality(record)

        record = self.valid_record()
        record["next_action"]["api_key"] = "secret-value"
        with self.assertRaises(ValueError):
            validate_task_causality(record)

        record = self.valid_record()
        record["business_label"] = "private-work"
        with self.assertRaises(ValueError):
            validate_task_causality(record)

    def test_rejects_invalid_relations_statuses_duplicates_and_unbounded_lists(self):
        record = self.valid_record()
        record["downstream"][0]["relation"] = "describes"
        with self.assertRaises(ValueError):
            validate_task_causality(record)

        record = self.valid_record()
        record["current_action"]["status"] = "unknown-status"
        with self.assertRaises(ValueError):
            validate_task_causality(record)

        record = self.valid_record()
        record["inputs"].append(dict(record["inputs"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_task_causality(record)

        record = self.valid_record()
        record["artifacts"] = [
            {"ref": f"artifact-{index:02d}", "status": "created"}
            for index in range(33)
        ]
        with self.assertRaises(ValueError):
            validate_task_causality(record)

    def test_validation_does_not_mutate_input_or_echo_sensitive_values(self):
        record = self.valid_record()
        record["task_ref"] = "/private/opaque-value"
        before = json.dumps(record, sort_keys=True)

        with self.assertRaises(ValueError) as raised:
            validate_task_causality(record)

        self.assertNotIn("/private/opaque-value", str(raised.exception))
        self.assertEqual(before, json.dumps(record, sort_keys=True))

    def test_repository_fixture_is_synthetic_and_validates_as_reference_only(self):
        fixture = json.loads(
            (self.ROOT / "examples" / "task_causality.synthetic.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(fixture, validate_task_causality(fixture))
        self.assertNotIn("summary", json.dumps(fixture))
        self.assertNotIn("path", json.dumps(fixture))


if __name__ == "__main__":
    unittest.main()
