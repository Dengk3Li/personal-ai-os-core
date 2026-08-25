import tempfile
import unittest
from pathlib import Path

from personal_ai_os.runtime import RuntimeStore
from personal_ai_os.task_links import module_work_projection


class TaskModuleLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RuntimeStore(Path(self.temp.name) / "runtime.db")
        self.store.create_workflow({
            "workflow_id": "system",
            "name": "系统建设",
            "caption": "建设与验证模块",
            "layout": "milestones",
            "goal": "建立可复用内核",
            "domain_id": "system",
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_task_creation_persists_typed_module_links_atomically(self):
        task = self.store.create_task({
            "task_id": "system:card-runtime",
            "workflow_id": "system",
            "title": "接入任务卡",
            "acceptance": "旧卡能够形成恢复现场",
            "module_links": [
                {
                    "module_id": "longtask-kernel",
                    "relation": "BUILDS",
                    "source": "EXPLICIT",
                    "status": "CONFIRMED",
                },
                {
                    "module_id": "personal-context",
                    "relation": "USES",
                    "source": "EXPLICIT",
                    "status": "CONFIRMED",
                },
            ],
        })

        self.assertEqual(2, len(task["module_links"]))
        self.assertEqual(
            {"BUILDS", "USES"},
            {item["relation"] for item in self.store.snapshot()["module_links"]},
        )

    def test_analyzed_links_stay_proposed_until_explicitly_confirmed(self):
        self.store.create_task({
            "task_id": "system:map",
            "workflow_id": "system",
            "title": "分析模块关系",
            "acceptance": "形成可确认关系",
        })
        proposed = self.store.link_task_module(
            "system:map",
            {
                "module_id": "domain-routing",
                "relation": "AFFECTS",
                "source": "ANALYZED",
                "confidence": 0.74,
            },
        )

        self.assertEqual("PROPOSED", proposed["status"])
        confirmed = self.store.confirm_task_module_link(
            "system:map", "domain-routing", "AFFECTS", confirmed_by="owner"
        )
        self.assertEqual("CONFIRMED", confirmed["status"])

    def test_projection_derives_module_progress_and_unlinked_tasks(self):
        self.store.create_task({
            "task_id": "system:linked",
            "workflow_id": "system",
            "title": "建设内核",
            "acceptance": "关联可读",
            "module_links": [{
                "module_id": "longtask-kernel",
                "relation": "BUILDS",
                "source": "EXPLICIT",
                "status": "CONFIRMED",
            }],
        })
        self.store.create_task({
            "task_id": "system:unlinked",
            "workflow_id": "system",
            "title": "尚未定位模块",
            "acceptance": "等待建立关系",
        })

        projection = module_work_projection(self.store.snapshot())

        self.assertEqual(
            ["system:linked"],
            projection["by_module"]["longtask-kernel"]["task_ids"],
        )
        self.assertEqual(1, projection["by_module"]["longtask-kernel"]["status_counts"]["QUEUED"])
        self.assertEqual(["system:unlinked"], projection["unlinked_task_ids"])

    def test_invalid_link_rolls_back_task_creation(self):
        with self.assertRaises(ValueError):
            self.store.create_task({
                "task_id": "system:invalid",
                "workflow_id": "system",
                "title": "错误关系",
                "acceptance": "不应写入",
                "module_links": [{
                    "module_id": "longtask-kernel",
                    "relation": "MAGIC",
                    "source": "EXPLICIT",
                }],
            })

        self.assertEqual([], self.store.snapshot()["tasks"])

    def test_conflicting_link_definition_cannot_overwrite_confirmed_provenance(self):
        self.store.create_task({
            "task_id": "system:provenance",
            "workflow_id": "system",
            "title": "保留关系来源",
            "acceptance": "已确认来源不能被候选分析覆盖",
            "module_links": [{
                "module_id": "longtask-kernel",
                "relation": "BUILDS",
                "source": "EXPLICIT",
                "confidence": 1.0,
                "status": "CONFIRMED",
            }],
        })

        with self.assertRaisesRegex(ValueError, "definition drift"):
            self.store.link_task_module(
                "system:provenance",
                {
                    "module_id": "longtask-kernel",
                    "relation": "BUILDS",
                    "source": "ANALYZED",
                    "confidence": 0.5,
                    "status": "PROPOSED",
                },
            )

        link = self.store.get_task("system:provenance")["module_links"][0]
        self.assertEqual("EXPLICIT", link["source"])
        self.assertEqual("CONFIRMED", link["status"])
        self.assertEqual(1.0, link["confidence"])


if __name__ == "__main__":
    unittest.main()
