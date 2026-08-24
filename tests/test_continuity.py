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
