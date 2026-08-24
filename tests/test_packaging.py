import json
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_editable_install_works_with_an_available_build_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory) / "venv"
            venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
            python = environment / "bin/python"
            install = subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-deps",
                    "--no-build-isolation",
                    "-e",
                    str(REPO_ROOT),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, install.returncode, install.stderr)
            demo = subprocess.run(
                [str(python), "-m", "personal_ai_os", "demo"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, demo.returncode, demo.stderr)
            self.assertEqual("SAFE", json.loads(demo.stdout)["status"])
