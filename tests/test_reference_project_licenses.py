import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReferenceProjectLicenseDocsTest(unittest.TestCase):
    def test_current_taskbook_exposes_integration_boundary(self):
        text = (ROOT / "docs" / "DEVELOPMENT_TASKBOOK_V0.20.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("参考项目与引入边界", text)
        self.assertIn("REFERENCE_PROJECT_LICENSES_V0.13.md", text)
        self.assertIn("不复制源码、界面、文案、商标或品牌素材", text)
        self.assertIn("直接引入第三方代码或文件", text)
        self.assertIn("原始许可证、版权声明和 NOTICE", text)

    def test_canonical_reference_record_keeps_required_projects_and_obligations(self):
        text = (ROOT / "docs" / "REFERENCE_PROJECT_LICENSES_V0.13.md").read_text(
            encoding="utf-8"
        )

        for project in ("Prime Agent", "LangGraph", "OpenHands"):
            self.assertIn(project, text)
        self.assertIn("MIT", text)
        self.assertIn("保留原版权声明与 MIT 许可", text)
        self.assertIn("NOTICE", text)
        self.assertIn("逐文件核对", text)


if __name__ == "__main__":
    unittest.main()
