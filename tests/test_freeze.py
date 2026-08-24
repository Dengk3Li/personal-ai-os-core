import hashlib
import tempfile
import unittest
from pathlib import Path

import personal_ai_os


class AssetFreezeTests(unittest.TestCase):
    def test_freeze_detects_content_drift(self):
        freeze_assets = getattr(personal_ai_os, "freeze_assets", None)
        verify_freeze = getattr(personal_ai_os, "verify_freeze", None)
        self.assertTrue(callable(freeze_assets), "freeze_assets must be public")
        self.assertTrue(callable(verify_freeze), "verify_freeze must be public")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset.txt").write_text("version-one\n", encoding="utf-8")

            manifest = freeze_assets(root, ["asset.txt"])

            self.assertEqual(
                hashlib.sha256(b"version-one\n").hexdigest(),
                manifest["files"]["asset.txt"],
            )
            self.assertEqual("PASS", verify_freeze(root, manifest)["status"])
            (root / "asset.txt").write_text("version-two\n", encoding="utf-8")
            verification = verify_freeze(root, manifest)
            self.assertEqual("BLOCKED", verification["status"])
            self.assertEqual(["asset.txt"], verification["drifted"])

    def test_freeze_rejects_paths_outside_the_root(self):
        freeze_assets = getattr(personal_ai_os, "freeze_assets", None)
        self.assertTrue(callable(freeze_assets), "freeze_assets must be public")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "outside root"):
                freeze_assets(Path(directory), ["../secret.txt"])
