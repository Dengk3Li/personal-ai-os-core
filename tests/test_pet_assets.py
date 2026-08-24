import json
import struct
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PetAssetTests(unittest.TestCase):
    def test_authorized_blue_whale_manifest_points_to_loadable_gifs(self):
        pet_root = REPO_ROOT / "workbench" / "assets" / "pets" / "blue-whale-maid"
        manifest = json.loads((pet_root / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual("personal-ai-os.pet/v1", manifest["schema_version"])
        self.assertEqual("Dengk3Li", manifest["authorized_by"])
        self.assertEqual("CC-BY-NC-4.0", manifest["license"])
        self.assertEqual(6, len(manifest["variants"]))
        for variant in manifest["variants"]:
            asset = pet_root / variant["asset"]
            header = asset.read_bytes()[:10]
            self.assertIn(header[:6], {b"GIF87a", b"GIF89a"})
            self.assertEqual((192, 208), struct.unpack("<HH", header[6:10]))


if __name__ == "__main__":
    unittest.main()
