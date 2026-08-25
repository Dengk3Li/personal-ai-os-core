from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_os import apply_presentation, load_presentation
from personal_ai_os.modules import module_catalog
from personal_ai_os.runtime import RuntimeStore
from personal_ai_os.server import RuntimeApplication, runtime_workbench_state


class PresentationTests(unittest.TestCase):
    def test_local_presentation_pack_changes_display_copy_without_changing_truth(self) -> None:
        snapshot = {
            "workflows": [
                {
                    "workflow_id": "line-a",
                    "name": "Internal line",
                    "caption": "Internal caption",
                    "goal": "Internal goal",
                }
            ],
            "tasks": [
                {
                    "task_id": "task-a",
                    "workflow_id": "line-a",
                    "title": "Internal task",
                    "acceptance": "Internal acceptance",
                    "agent_role": "General Agent",
                }
            ],
        }
        presentation = {
            "schema_version": "personal-ai-os.presentation/v1",
            "workflows": {
                "line-a": {
                    "name": "中文工作线",
                    "caption": "不看背景也能理解的说明",
                    "goal": "形成可验收结果",
                }
            },
            "tasks": {
                "task-a": {
                    "public_label": "任务 01",
                    "title": "核对系统结构",
                    "acceptance": "输入、处理和输出关系清晰",
                    "agent_role": "系统梳理角色",
                    "flow_kind": "join",
                }
            },
        }

        projected = apply_presentation(snapshot, presentation)

        self.assertEqual("中文工作线", projected["workflows"][0]["name"])
        self.assertEqual("核对系统结构", projected["tasks"][0]["title"])
        self.assertEqual("join", projected["tasks"][0]["flow_kind"])
        self.assertEqual("Internal line", snapshot["workflows"][0]["name"])
        self.assertEqual("Internal task", snapshot["tasks"][0]["title"])

    def test_loader_rejects_private_runtime_fields_and_unknown_copy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presentation.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "personal-ai-os.presentation/v1",
                        "workflows": {},
                        "tasks": {"task-a": {"title": "安全标题", "context": {"path": "/private"}}},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unsupported presentation field"):
                load_presentation(path)

    def test_loader_accepts_only_bounded_text_maps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presentation.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "personal-ai-os.presentation/v1",
                        "workflows": {"line-a": {"name": "科研工作线"}},
                        "tasks": {"task-a": {"title": "提出可检验假设"}},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            loaded = load_presentation(path)
            self.assertEqual("科研工作线", loaded["workflows"]["line-a"]["name"])

    def test_loader_rejects_paths_and_obvious_secrets_inside_display_copy(self) -> None:
        unsafe_values = (
            "/Users/example/private/project",
            "文件在/Users/example/private/project",
            "路径：/home/example/project",
            r"C:\Users\example\secret",
            r"本地：C:\Users\example\secret",
            "file:///private/source",
            "sk-1234567890abcdefghijklmnop",
            "Bearer local-token-value",
            "api_key=abcdefghijklmnop",
            "https://user:password@example.invalid/path",
        )
        for value in unsafe_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "sensitive presentation text"):
                    apply_presentation(
                        {"workflows": [], "tasks": []},
                        {
                            "schema_version": "personal-ai-os.presentation/v1",
                            "tasks": {"task-a": {"title": value}},
                        },
                    )

    def test_loader_rejects_sensitive_runtime_ids_used_as_mapping_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "sensitive presentation identifier"):
            apply_presentation(
                {"workflows": [], "tasks": []},
                {
                    "schema_version": "personal-ai-os.presentation/v1",
                    "workflows": {
                        "file:///Users/example/private-workflow": {"name": "公开工作线"}
                    },
                    "tasks": {},
                },
            )

    def test_presentation_mode_anonymizes_runtime_relationship_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            store.create_workflow(
                {
                    "workflow_id": "safe-workflow",
                    "name": "Private line",
                    "caption": "Private caption",
                    "layout": "branch",
                    "goal": "Private goal",
                }
            )
            store.create_task(
                {
                    "task_id": "safe-task",
                    "workflow_id": "safe-workflow",
                    "title": "Private task",
                    "acceptance": "Private acceptance",
                    "domain_id": "/Users/example/private-domain",
                    "parallel_group": "CONFIDENTIAL_GROUP",
                    "required_capabilities": ["CONFIDENTIAL_CAPABILITY"],
                }
            )
            presentation = {
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {"safe-workflow": {"name": "公开工作线"}},
                "tasks": {"safe-task": {"title": "公开任务"}},
            }

            application = RuntimeApplication(
                store=store,
                adapters={},
                default_model="model-a",
                web_root=Path(__file__).resolve().parents[1] / "workbench",
                presentation=presentation,
            )
            projected = application.projection()["state"]
            serialized = json.dumps(projected, ensure_ascii=False)

            self.assertNotIn("/Users/", serialized)
            self.assertNotIn("CONFIDENTIAL_", serialized)
            self.assertEqual("line-01", projected["tasks"][0]["line_id"])
            self.assertEqual("task-001", projected["tasks"][0]["task_id"])
            self.assertEqual("domain-01", projected["tasks"][0]["domain_id"])
            self.assertEqual("group-01", projected["tasks"][0]["parallel_group"])
            self.assertEqual(
                ["capability-01"], projected["tasks"][0]["required_capabilities"]
            )
            self.assertEqual("safe-task", application.resolve_task_id("task-001"))
            self.assertEqual(
                "safe-workflow", application.resolve_workflow_id("line-01")
            )

    def test_presentation_mode_anonymizes_module_link_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            store.create_workflow({
                "workflow_id": "private-line",
                "name": "Private",
                "caption": "Private",
                "layout": "custom",
                "goal": "Private",
            })
            store.create_task({
                "task_id": "private-task",
                "workflow_id": "private-line",
                "title": "Private",
                "acceptance": "Private",
                "module_links": [{
                    "module_id": "/Users/example/private-module",
                    "relation": "USES",
                    "source": "EXPLICIT",
                    "status": "CONFIRMED",
                }],
            })
            projected = runtime_workbench_state(
                store,
                {
                    "schema_version": "personal-ai-os.presentation/v1",
                    "workflows": {"private-line": {"name": "公开线"}},
                    "tasks": {"private-task": {"title": "公开任务"}},
                },
            )
            serialized = json.dumps(projected, ensure_ascii=False)

            self.assertNotIn("/Users", serialized)
            self.assertIn("module-01", serialized)

    def test_public_system_module_links_keep_their_graph_identity(self) -> None:
        snapshot = {
            "workflows": [{"workflow_id": "private-line", "name": "Private"}],
            "tasks": [{
                "task_id": "private-task",
                "workflow_id": "private-line",
                "title": "Private",
                "module_links": [{
                    "task_id": "private-task",
                    "module_id": "longtask-kernel",
                    "relation": "BUILDS",
                    "source": "EXPLICIT",
                    "status": "CONFIRMED",
                }],
            }],
            "module_links": [{
                "task_id": "private-task",
                "module_id": "longtask-kernel",
                "relation": "BUILDS",
                "source": "EXPLICIT",
                "status": "CONFIRMED",
            }],
        }

        projected = apply_presentation(
            snapshot,
            {"schema_version": "personal-ai-os.presentation/v1"},
        )

        self.assertEqual(
            "longtask-kernel", projected["tasks"][0]["module_links"][0]["module_id"]
        )
        self.assertEqual(
            "longtask-kernel", projected["module_links"][0]["module_id"]
        )

    def test_builtin_runtime_module_links_keep_their_catalog_identity(self) -> None:
        for module in module_catalog():
            module_id = module["module_id"]
            projected = apply_presentation(
                {
                    "workflows": [{"workflow_id": "private-line", "name": "Private"}],
                    "tasks": [{
                        "task_id": "private-task",
                        "workflow_id": "private-line",
                        "title": "Private",
                        "module_links": [{
                            "task_id": "private-task",
                            "module_id": module_id,
                            "relation": "BUILDS",
                            "source": "EXPLICIT",
                            "status": "CONFIRMED",
                        }],
                    }],
                    "module_links": [{
                        "task_id": "private-task",
                        "module_id": module_id,
                        "relation": "BUILDS",
                        "source": "EXPLICIT",
                        "status": "CONFIRMED",
                    }],
                },
                {"schema_version": "personal-ai-os.presentation/v1"},
            )

            self.assertEqual(
                module_id, projected["module_links"][0]["module_id"]
            )

    def test_unmapped_items_use_safe_display_copy_when_a_pack_is_active(self) -> None:
        snapshot = {
            "workflows": [
                {
                    "workflow_id": "line-private",
                    "name": "PRIVATE_WORKFLOW_SENTINEL",
                    "caption": "PRIVATE_CAPTION_SENTINEL",
                    "goal": "PRIVATE_GOAL_SENTINEL",
                }
            ],
            "tasks": [
                {
                    "task_id": "task-private",
                    "title": "PRIVATE_TITLE_SENTINEL",
                    "acceptance": "PRIVATE_ACCEPTANCE_SENTINEL",
                    "agent_role": "PRIVATE_ROLE_SENTINEL",
                }
            ],
        }
        presentation = {
            "schema_version": "personal-ai-os.presentation/v1",
            "workflows": {},
            "tasks": {},
        }

        projected = apply_presentation(snapshot, presentation)
        serialized = json.dumps(projected, ensure_ascii=False)

        self.assertNotIn("PRIVATE_", serialized)
        self.assertEqual("工作线 01", projected["workflows"][0]["name"])
        self.assertEqual("任务 01", projected["tasks"][0]["public_label"])

    def test_runtime_identifier_aliases_preserve_graph_relationships(self) -> None:
        snapshot = {
            "workflows": [{"workflow_id": "private-line", "name": "Private"}],
            "tasks": [
                {
                    "task_id": "private-first",
                    "workflow_id": "private-line",
                    "line_id": "private-line",
                    "depends_on": [],
                    "parallel_group": "private-group",
                    "required_capabilities": ["private-capability"],
                },
                {
                    "task_id": "private-second",
                    "workflow_id": "private-line",
                    "line_id": "private-line",
                    "depends_on": ["private-first"],
                    "parallel_group": "private-group",
                    "required_capabilities": ["private-capability"],
                },
            ],
            "events": [
                {
                    "event_id": "private-event",
                    "task_id": "private-first",
                    "run_id": "private-run",
                }
            ],
            "decisions": [
                {
                    "decision_id": "private-decision",
                    "task_id": "private-second",
                }
            ],
            "assignments": {
                "private-first": {
                    "route": "standard",
                    "model": "model-a",
                    "executor": "adapter-a",
                }
            },
        }

        projected = apply_presentation(
            snapshot,
            {"schema_version": "personal-ai-os.presentation/v1"},
        )
        serialized = json.dumps(projected, ensure_ascii=False)

        self.assertNotIn("private-line", serialized)
        self.assertNotIn("private-first", serialized)
        self.assertNotIn("private-group", serialized)
        self.assertNotIn("private-capability", serialized)
        self.assertEqual("line-01", projected["workflows"][0]["workflow_id"])
        self.assertEqual(["task-001"], projected["tasks"][1]["depends_on"])
        self.assertEqual(["task-001"], list(projected["assignments"]))
        self.assertEqual("task-002", projected["decisions"][0]["task_id"])

    def test_runtime_projection_uses_local_copy_without_mutating_the_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            store.create_workflow(
                {
                    "workflow_id": "line-a",
                    "name": "Internal line",
                    "caption": "Internal caption",
                    "layout": "branch",
                    "goal": "Internal goal",
                }
            )
            store.create_task(
                {
                    "task_id": "task-a",
                    "workflow_id": "line-a",
                    "title": "Internal task",
                    "acceptance": "Internal acceptance",
                }
            )
            presentation = {
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {"line-a": {"name": "中文工作线"}},
                "tasks": {"task-a": {"title": "核对系统结构"}},
            }

            projected = runtime_workbench_state(store, presentation)

            self.assertEqual("中文工作线", projected["businessLines"][0]["name"])
            self.assertEqual("核对系统结构", projected["tasks"][0]["title"])
            self.assertEqual("Internal line", store.snapshot()["workflows"][0]["name"])
            self.assertEqual("Internal task", store.get_task("task-a")["title"])

    def test_presentation_mode_projects_pending_decisions_without_private_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            store.create_workflow(
                {
                    "workflow_id": "line-a",
                    "name": "Private line",
                    "caption": "Private caption",
                    "layout": "branch",
                    "goal": "Private goal",
                }
            )
            store.create_task(
                {
                    "task_id": "task-a",
                    "workflow_id": "line-a",
                    "title": "PRIVATE_TITLE_SENTINEL",
                    "acceptance": "/Users/private/ACCEPTANCE_SENTINEL",
                    "human_gate": True,
                }
            )
            store.ensure_pending_decision(
                "task-a",
                {
                    "question": "Should PRIVATE_TITLE_SENTINEL continue?",
                    "context": "/Users/private/ACCEPTANCE_SENTINEL",
                    "options": [
                        {"letter": "A", "label": "Approve and continue", "action": "continue"},
                        {"letter": "B", "label": "Pause this task", "action": "pause"},
                    ],
                    "recommended_option": "A",
                    "recommendation_reason": "PRIVATE_REASON_SENTINEL",
                },
            )
            projected = runtime_workbench_state(
                store,
                {
                    "schema_version": "personal-ai-os.presentation/v1",
                    "workflows": {"line-a": {"name": "科研工作线"}},
                    "tasks": {
                        "task-a": {
                            "title": "确认实验边界",
                            "acceptance": "实验范围和停止条件均已确认",
                        }
                    },
                },
            )
            serialized = json.dumps(projected, ensure_ascii=False)

            self.assertNotIn("PRIVATE_", serialized)
            self.assertNotIn("/Users/", serialized)
            decision = projected["pendingDecisions"][0]
            self.assertEqual("是否继续“确认实验边界”？", decision["question"])
            self.assertEqual("批准并继续", decision["options"][0]["label"])

    def test_public_example_is_a_valid_generic_presentation_pack(self) -> None:
        example = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "presentation.zh-CN.json"
        )

        loaded = load_presentation(example)

        self.assertEqual("科研工作线", loaded["workflows"]["science"]["name"])
        self.assertEqual(
            "提出可检验的科学假设",
            loaded["tasks"]["science:hypothesis"]["title"],
        )

    def test_runtime_application_rejects_an_invalid_pack_before_serving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            with self.assertRaisesRegex(ValueError, "unsupported presentation schema"):
                RuntimeApplication(
                    store=store,
                    adapters={},
                    default_model="model-a",
                    web_root=Path(__file__).resolve().parents[1] / "workbench",
                    presentation={"schema_version": "invalid"},
                )

    def test_presentation_server_rejects_sensitive_execution_labels_before_serving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory) / "runtime.db")
            presentation = {"schema_version": "personal-ai-os.presentation/v1"}
            common = {
                "store": store,
                "web_root": Path(__file__).resolve().parents[1] / "workbench",
                "presentation": presentation,
            }
            with self.assertRaisesRegex(ValueError, "sensitive runtime label"):
                RuntimeApplication(
                    **common,
                    adapters={},
                    default_model="/Users/example/private-model",
                )
            with self.assertRaisesRegex(ValueError, "sensitive runtime label"):
                RuntimeApplication(
                    **common,
                    adapters={"/Users/example/private-adapter": object()},
                    default_model="model-a",
                )
            with self.assertRaisesRegex(ValueError, "sensitive runtime label"):
                RuntimeApplication(
                    **common,
                    adapters={},
                    default_model="model-a",
                    runtime_routes=[
                        {
                            "route": "deep",
                            "adapter_id": "adapter-a",
                            "model": "/Users/example/private-model",
                        }
                    ],
                )


if __name__ == "__main__":
    unittest.main()
