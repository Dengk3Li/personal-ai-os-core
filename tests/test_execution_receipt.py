import json
import unittest

from personal_ai_os.execution_receipt import (
    EXECUTION_RECEIPT_VERSION,
    validate_execution_receipt,
)


class ExecutionReceiptTests(unittest.TestCase):
    def valid_receipt(self):
        return {
            "schema_version": EXECUTION_RECEIPT_VERSION,
            "task_ref": "task-001",
            "run_ref": "run-001",
            "binding": {
                "project_id": "project-001",
                "thread_id": "thread-001",
                "host_id": "host-001",
                "verified": True,
            },
            "receipt": {
                "receipt_id": "receipt-001",
                "status": "completed",
                "outcome": "succeeded",
                "verified": True,
                "needs_user_input": False,
                "human_gate": False,
                "final_output_ref": "artifact-001",
                "artifact_refs": ["artifact-001"],
                "observed_at": "2026-08-26T09:00:00+08:00",
            },
        }

    def test_receipt_normalizes_execution_binding_and_terminal_state(self):
        result = validate_execution_receipt(self.valid_receipt())

        self.assertEqual(EXECUTION_RECEIPT_VERSION, result["schema_version"])
        self.assertEqual(
            {
                "project_id": "project-001",
                "thread_id": "thread-001",
                "host_id": "host-001",
                "verified": True,
            },
            result["binding"],
        )
        self.assertEqual("COMPLETED", result["receipt"]["status"])
        self.assertEqual("SUCCEEDED", result["receipt"]["outcome"])
        self.assertEqual("artifact-001", result["receipt"]["final_output_ref"])

    def test_running_receipt_can_have_no_final_output_but_completed_cannot(self):
        receipt = self.valid_receipt()
        receipt["receipt"].update(
            {
                "status": "running",
                "outcome": "unknown",
                "verified": False,
            }
        )
        receipt["receipt"].pop("final_output_ref")
        receipt["receipt"].pop("artifact_refs")
        result = validate_execution_receipt(receipt)
        self.assertEqual("RUNNING", result["receipt"]["status"])
        self.assertNotIn("final_output_ref", result["receipt"])

        receipt["receipt"].update(
            {
                "status": "completed",
                "outcome": "succeeded",
                "verified": False,
            }
        )
        with self.assertRaises(ValueError):
            validate_execution_receipt(receipt)

    def test_completed_receipt_rejects_unresolved_user_input_or_human_gate(self):
        for field in ("needs_user_input", "human_gate"):
            receipt = self.valid_receipt()
            receipt["receipt"][field] = True
            with self.assertRaises(ValueError):
                validate_execution_receipt(receipt)

    def test_receipt_rejects_paths_credentials_business_fields_and_unknown_fields(self):
        for field in ("task_ref", "run_ref"):
            receipt = self.valid_receipt()
            receipt[field] = "/Users/private/task"
            with self.assertRaises(ValueError):
                validate_execution_receipt(receipt)

        receipt = self.valid_receipt()
        receipt["binding"]["project_path"] = "/private/project"
        with self.assertRaises(ValueError):
            validate_execution_receipt(receipt)

        receipt = self.valid_receipt()
        receipt["receipt"]["api_key"] = "secret-value"
        with self.assertRaises(ValueError):
            validate_execution_receipt(receipt)

        receipt = self.valid_receipt()
        receipt["receipt"]["business_label"] = "private-work"
        with self.assertRaises(ValueError):
            validate_execution_receipt(receipt)

    def test_receipt_errors_do_not_echo_private_values_or_mutate_input(self):
        receipt = self.valid_receipt()
        receipt["binding"]["thread_id"] = "/private/thread"
        before = json.dumps(receipt, sort_keys=True)

        with self.assertRaises(ValueError) as raised:
            validate_execution_receipt(receipt)

        self.assertNotIn("/private/thread", str(raised.exception))
        self.assertEqual(before, json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
