import json
import unittest

from personal_ai_os.task_envelope import (
    TASK_ENVELOPE_VERSION,
    TASK_MODULE_LINK_VERSION,
    preview_task_envelopes,
    validate_task_envelope,
    validate_task_module_link_v1,
)


class TaskEnvelopeTests(unittest.TestCase):
    def valid_envelope(self):
        return {
            "schema_version": TASK_ENVELOPE_VERSION,
            "origin": {
                "source_kind": "local-adapter",
                "source_ref": "origin-001",
                "revision": 1,
            },
            "runtime_task": {
                "task_id": "task-001",
                "workflow_id": "workflow-001",
                "status": "QUEUED",
                "attempt": 1,
                "depends_on": [],
                "result_ref": "artifact-001",
            },
            "extensions": {"resume_hint": {"ready": True}},
            "module_refs": [
                {
                    "module_id": "workflow-core",
                    "relation": "BUILDS",
                    "source": "IMPORTED",
                    "status": "CONFIRMED",
                }
            ],
        }

    def test_task_envelope_normalizes_runtime_task_and_typed_module_refs(self):
        result = validate_task_envelope(self.valid_envelope())

        self.assertEqual(TASK_ENVELOPE_VERSION, result["schema_version"])
        self.assertEqual("origin-001", result["origin"]["source_ref"])
        self.assertEqual("QUEUED", result["runtime_task"]["status"])
        self.assertEqual(TASK_MODULE_LINK_VERSION, result["module_refs"][0]["schema_version"])
        self.assertEqual("workflow-core", result["module_refs"][0]["module_id"])

    def test_task_envelope_rejects_private_paths_business_copy_and_unknown_fields(self):
        envelope = self.valid_envelope()
        envelope["runtime_task"]["title"] = "专业分析工作"
        with self.assertRaises(ValueError):
            validate_task_envelope(envelope)

        for location, value in (
            ("origin", "/Users/private/card"),
            ("extensions", "行业研究"),
        ):
            envelope = self.valid_envelope()
            if location == "origin":
                envelope["origin"]["source_ref"] = value
            else:
                envelope["extensions"] = {"label": value}
            with self.assertRaises(ValueError):
                validate_task_envelope(envelope)

    def test_task_envelope_rejects_private_module_refs_and_duplicate_refs(self):
        envelope = self.valid_envelope()
        envelope["module_refs"][0]["module_id"] = "/private/module"
        with self.assertRaises(ValueError):
            validate_task_envelope(envelope)

        envelope = self.valid_envelope()
        envelope["module_refs"].append(dict(envelope["module_refs"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate module reference"):
            validate_task_envelope(envelope)

    def test_task_module_link_v1_is_strict_and_uses_existing_typed_relations(self):
        link = validate_task_module_link_v1(
            {
                "module_id": "execution-adapter",
                "relation": "USES",
                "source": "EXPLICIT",
            }
        )

        self.assertEqual(TASK_MODULE_LINK_VERSION, link["schema_version"])
        self.assertEqual("USES", link["relation"])
        with self.assertRaises(ValueError):
            validate_task_module_link_v1({**link, "unexpected": True})
        with self.assertRaises(ValueError):
            validate_task_module_link_v1({**link, "module_id": "/Users/private/module"})

    def test_task_envelope_never_echoes_rejected_values(self):
        envelope = self.valid_envelope()
        envelope["origin"]["source_ref"] = "/private/sensitive-source"

        with self.assertRaises(ValueError) as raised:
            validate_task_envelope(envelope)

        self.assertNotIn("/private/sensitive-source", str(raised.exception))
        self.assertNotIn("/private/sensitive-source", json.dumps(self.valid_envelope()))

    def test_batch_preview_deduplicates_identical_origin_and_task(self):
        item = {
            "envelope": self.valid_envelope(),
            "goal": "goal-001",
            "next_action": "action-001",
        }

        result = preview_task_envelopes([item, dict(item)])

        self.assertEqual("READY", result["status"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["runtime_write"])
        self.assertEqual(2, result["summary"]["input_count"])
        self.assertEqual(1, result["summary"]["unique_count"])
        self.assertEqual(1, result["summary"]["duplicate_count"])
        self.assertEqual(1, len(result["items"]))
        self.assertEqual("goal-001", result["items"][0]["goal"])

    def test_batch_preview_blocks_conflicting_origin_and_task(self):
        first = {
            "envelope": self.valid_envelope(),
            "goal": "goal-001",
            "next_action": "action-001",
        }
        second = {
            "envelope": self.valid_envelope(),
            "goal": "goal-002",
            "next_action": "action-001",
        }

        result = preview_task_envelopes([first, second])

        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("DUPLICATE_TASK_CONFLICT", result["reason"]["code"])
        self.assertEqual("RECONCILE_TASK_DUPLICATES", result["next_action"]["code"])
        self.assertEqual([{"index": 1, "code": "DUPLICATE_TASK_CONFLICT"}], result["issues"])
        self.assertNotIn("goal-002", json.dumps(result))

    def test_batch_preview_blocks_missing_goal_or_next_action(self):
        item = {"envelope": self.valid_envelope(), "goal": "goal-001"}

        result = preview_task_envelopes([item])

        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("REQUIRED_METADATA", result["reason"]["code"])
        self.assertEqual("PROVIDE_TASK_METADATA", result["next_action"]["code"])
        self.assertEqual(
            [{"index": 0, "code": "NEXT_ACTION_REQUIRED"}],
            result["issues"],
        )
        self.assertNotIn("goal-001", json.dumps(result))

    def test_batch_preview_rejects_private_input_without_echoing_it(self):
        item = {
            "envelope": self.valid_envelope(),
            "goal": "goal-001",
            "next_action": "/private/template-body",
        }

        result = preview_task_envelopes([item])

        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("INVALID_TASK_METADATA", result["reason"]["code"])
        self.assertEqual([{"index": 0, "code": "NEXT_ACTION_INVALID"}], result["issues"])
        self.assertNotIn("/private/template-body", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
