import hashlib
import json
import unittest

import personal_ai_os


class ContinuityCapsuleTests(unittest.TestCase):
    def test_capsule_keeps_only_recovery_fields_and_has_a_stable_digest(self):
        build_capsule = getattr(personal_ai_os, "build_capsule", None)
        self.assertTrue(callable(build_capsule), "build_capsule must be public")
        state = {
            "next_action": "review candidate",
            "authority": "local_git_main",
            "private_notes": "must not enter capsule",
            "current_state": "PAUSED",
        }
        expected_payload = {
            "authority": "local_git_main",
            "current_state": "PAUSED",
            "next_action": "review candidate",
        }
        encoded = (json.dumps(expected_payload, sort_keys=True, separators=(",", ":")) + "\n").encode()

        capsule = build_capsule(state)

        self.assertEqual(expected_payload, capsule["payload"])
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), capsule["sha256"])
        self.assertEqual(len(encoded), capsule["size_bytes"])

    def test_capsule_rejects_missing_recovery_state(self):
        build_capsule = getattr(personal_ai_os, "build_capsule", None)
        self.assertTrue(callable(build_capsule), "build_capsule must be public")

        with self.assertRaisesRegex(ValueError, "missing recovery fields"):
            build_capsule({"authority": "local_git_main"})

    def test_runtime_capsule_keeps_bounded_references_without正文_or_paths(self):
        build_runtime_capsule = getattr(
            personal_ai_os, "build_runtime_continuity_capsule", None
        )
        self.assertTrue(callable(build_runtime_capsule))

        capsule = build_runtime_capsule(
            {
                "task": {
                    "task_id": "task-1",
                    "workflow_id": "line-1",
                    "status": "REVIEW",
                    "title": "private task body",
                },
                "dependencies": [
                    {"task_id": "task-0", "status": "DONE", "content": "private"}
                ],
                "latest_run": {
                    "run_id": "run-1",
                    "status": "SUCCEEDED",
                    "attempt": 2,
                    "cwd": "/Users/private/project",
                    "output_text": "private output",
                },
                "decision": {
                    "decision_id": "decision-1",
                    "status": "PENDING",
                    "question": "private question",
                    "api_token": "do-not-copy",
                },
                "artifact_refs": ["artifact-1", "artifact-1", "/private/output"],
                "next_action": "review artifact-1",
            }
        )

        self.assertEqual("personal-ai-os.continuity/v2", capsule["schema_version"])
        self.assertEqual(
            {
                "task_id": "task-1",
                "workflow_id": "line-1",
                "status": "REVIEW",
            },
            capsule["payload"]["task"],
        )
        self.assertEqual(
            [{"task_id": "task-0", "status": "DONE"}],
            capsule["payload"]["dependencies"],
        )
        self.assertEqual(
            {"run_id": "run-1", "status": "SUCCEEDED", "attempt": 2},
            capsule["payload"]["latest_run"],
        )
        self.assertEqual(
            {"decision_id": "decision-1", "status": "PENDING"},
            capsule["payload"]["decision"],
        )
        self.assertEqual(["artifact-1"], capsule["payload"]["artifact_refs"])
        serialized = json.dumps(capsule, ensure_ascii=False)
        for forbidden in ("private task body", "/Users/private/project", "private output", "do-not-copy"):
            self.assertNotIn(forbidden, serialized)

    def test_runtime_capsule_rejects_unbounded_reference_lists(self):
        build_runtime_capsule = getattr(
            personal_ai_os, "build_runtime_continuity_capsule", None
        )
        self.assertTrue(callable(build_runtime_capsule))

        with self.assertRaisesRegex(ValueError, "dependencies"):
            build_runtime_capsule(
                {
                    "task": {"task_id": "task-1", "status": "QUEUED"},
                    "dependencies": [
                        {"task_id": f"task-{index}", "status": "DONE"}
                        for index in range(33)
                    ],
                }
            )
