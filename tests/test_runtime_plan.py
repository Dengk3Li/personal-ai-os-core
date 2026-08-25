import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_os.runtime import RuntimeStore
from personal_ai_os.runtime_plan import load_runtime_plan, sync_runtime_plan


class RuntimePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = RuntimeStore(self.root / "runtime.db")

    def tearDown(self):
        self.temp.cleanup()

    def _plan(self):
        return {
            "schema_version": "personal-ai-os.runtime-plan/v1",
            "workflows": [
                {
                    "workflow_id": "self-hosting",
                    "name": "Core self-hosting",
                    "caption": "Develop the runtime through its own task system",
                    "layout": "milestones",
                    "goal": "Ship the next verified runtime slice",
                    "tasks": [
                        {
                            "task_id": "self-hosting:intake",
                            "public_label": "Core 01",
                            "title": "Register the local workspace",
                            "acceptance": "The local source is referenced without copying its contents",
                            "context": {
                                "workspace_refs": [
                                    {
                                        "workspace_id": "public-core",
                                        "path": "/private/local/public-core",
                                        "branch": "codex/example",
                                    }
                                ]
                            },
                        },
                        {
                            "task_id": "self-hosting:pet",
                            "public_label": "Core 02",
                            "title": "Integrate the authorized pet",
                            "acceptance": "The running task renders an authorized selectable pet",
                            "depends_on": ["self-hosting:intake"],
                        },
                    ],
                }
            ],
        }

    def test_sync_plan_is_idempotent_and_preserves_runtime_state(self):
        plan = self._plan()

        first = sync_runtime_plan(self.store, plan)
        moved = self.store.transition(
            "self-hosting:intake", "IN_PROGRESS", by="local-owner"
        )
        second = sync_runtime_plan(self.store, plan)

        self.assertTrue(moved["ok"])
        self.assertEqual(
            {"created_workflows": 1, "created_tasks": 2, "existing_workflows": 0, "existing_tasks": 0},
            first,
        )
        self.assertEqual(
            {"created_workflows": 0, "created_tasks": 0, "existing_workflows": 1, "existing_tasks": 2},
            second,
        )
        self.assertEqual("IN_PROGRESS", self.store.get_task("self-hosting:intake")["status"])
        self.assertEqual(
            "/private/local/public-core",
            self.store.get_task("self-hosting:intake")["context"]["workspace_refs"][0]["path"],
        )

    def test_invalid_plan_is_rejected_before_any_runtime_write(self):
        plan = self._plan()
        plan["workflows"][0]["tasks"][1]["depends_on"] = ["missing:task"]

        with self.assertRaisesRegex(ValueError, "dependency not found in runtime plan"):
            sync_runtime_plan(self.store, plan)

        snapshot = self.store.snapshot()
        self.assertEqual([], snapshot["workflows"])
        self.assertEqual([], snapshot["tasks"])

    def test_plan_loader_requires_the_versioned_schema(self):
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps({"workflows": []}), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unsupported runtime plan schema"):
            load_runtime_plan(plan_path)

    def test_existing_task_collision_is_rejected_before_creating_a_workflow(self):
        self.store.create_workflow({
            "workflow_id": "other",
            "name": "Other",
            "caption": "Existing truth",
            "layout": "sequence",
            "goal": "Preserve the existing task owner",
        })
        self.store.create_task({
            "task_id": "self-hosting:intake",
            "workflow_id": "other",
            "title": "Existing task",
            "acceptance": "The existing workflow remains authoritative",
        })

        with self.assertRaisesRegex(ValueError, "belongs to another workflow"):
            sync_runtime_plan(self.store, self._plan())

        self.assertEqual(
            ["other"],
            [item["workflow_id"] for item in self.store.snapshot()["workflows"]],
        )

    def test_invalid_later_task_cannot_leave_a_partial_plan(self):
        plan = self._plan()
        plan["workflows"][0]["tasks"][1]["status"] = "DONE"

        with self.assertRaisesRegex(ValueError, "start in QUEUED"):
            sync_runtime_plan(self.store, plan)

        snapshot = self.store.snapshot()
        self.assertEqual([], snapshot["workflows"])
        self.assertEqual([], snapshot["tasks"])

    def test_existing_definition_drift_is_not_silently_ignored(self):
        plan = self._plan()
        sync_runtime_plan(self.store, plan)
        plan["workflows"][0]["tasks"][0]["title"] = "Changed task definition"

        with self.assertRaisesRegex(ValueError, "runtime plan definition drift"):
            sync_runtime_plan(self.store, plan)

        self.assertEqual(
            "Register the local workspace",
            self.store.get_task("self-hosting:intake")["title"],
        )

    def test_module_link_definition_is_persisted_and_drift_checked(self):
        plan = self._plan()
        plan["workflows"][0]["tasks"][0]["module_links"] = [{
            "module_id": "longtask-kernel",
            "relation": "BUILDS",
            "source": "EXPLICIT",
            "status": "CONFIRMED",
        }]
        sync_runtime_plan(self.store, plan)

        self.assertEqual(
            "longtask-kernel",
            self.store.get_task("self-hosting:intake")["module_links"][0]["module_id"],
        )
        plan["workflows"][0]["tasks"][0]["module_links"][0]["relation"] = "USES"

        with self.assertRaisesRegex(ValueError, "runtime plan definition drift"):
            sync_runtime_plan(self.store, plan)

    def test_unexpected_insert_failure_rolls_back_the_whole_plan(self):
        class FailingStore(RuntimeStore):
            def __init__(self, database):
                self.inserted = 0
                super().__init__(database)

            def _insert_task(self, connection, task):
                self.inserted += 1
                if self.inserted == 2:
                    raise RuntimeError("synthetic insert failure")
                return super()._insert_task(connection, task)

        store = FailingStore(self.root / "failing.db")
        with self.assertRaisesRegex(RuntimeError, "synthetic insert failure"):
            sync_runtime_plan(store, self._plan())

        snapshot = store.snapshot()
        self.assertEqual([], snapshot["workflows"])
        self.assertEqual([], snapshot["tasks"])
