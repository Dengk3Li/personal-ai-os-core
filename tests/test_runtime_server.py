import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from personal_ai_os.runtime import RuntimeStore, install_workflow_preset
from personal_ai_os.presentation import validate_presentation
from personal_ai_os.server import RuntimeApplication, create_runtime_server, runtime_workbench_state


class SuccessfulAdapter:
    adapter_id = "test-adapter"

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        return {
            "ok": True,
            "external_run_id": "api-run-1",
            "status": "SUCCEEDED",
            "output_text": "API result",
        }


class NoisyProbeAdapter(SuccessfulAdapter):
    def probe(self):
        return {
            "adapter_id": self.adapter_id,
            "available": True,
            "protocol": "test",
            "debug": "token=PRIVATE_SENTINEL",
        }


class ClientNamedAdapter(SuccessfulAdapter):
    adapter_id = "client-alpha-adapter"

    def probe(self):
        return {
            "adapter_id": self.adapter_id,
            "available": True,
            "protocol": "client-alpha-protocol",
        }


class CountingAdapter(SuccessfulAdapter):
    def __init__(self, adapter_id):
        self.adapter_id = adapter_id
        self.calls = 0

    def start(self, task, *, model, context_pack):
        self.calls += 1
        return super().start(task, model=model, context_pack=context_pack)


class BlockingAdapter(SuccessfulAdapter):
    adapter_id = "blocking-adapter"

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def start(self, task, *, model, context_pack):
        self.started.set()
        self.release.wait(timeout=3)
        return super().start(task, model=model, context_pack=context_pack)


class RuntimeServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RuntimeStore(Path(self.temp.name) / "runtime.db")
        install_workflow_preset(self.store, "science")
        self.server = create_runtime_server(
            ("127.0.0.1", 0),
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="model-a",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            return response.status, json.loads(response.read())

    def test_runtime_projection_marks_succeeded_dispatch_without_terminal_receipt_as_legacy(self):
        projection = runtime_workbench_state(
            self.store,
            codex_dispatches=[
                {
                    "task_id": "science:hypothesis",
                    "status": "SUCCEEDED",
                    "dispatch_id": "dispatch-legacy",
                    "project": {"label": "科研项目", "environment": "worktree"},
                    "thread_id": "thread-legacy",
                    "project_id": "project-1",
                    "completion_receipt": {},
                }
            ],
        )

        task = next(item for item in projection["tasks"] if item["task_id"] == "science:hypothesis")
        self.assertEqual("LEGACY_MISSING", task["codex_dispatch"]["receipt_state"])

    def test_api_reads_runtime_and_dispatches_a_real_adapter(self):
        status, initial = self.request("/api/runtime")
        run_status, dispatched = self.request(
            "/api/runs",
            {
                "task_id": "science:hypothesis",
                "adapter_id": "test-adapter",
                "model": "model-a",
            },
        )
        _, after = self.request("/api/runtime")

        self.assertEqual(200, status)
        self.assertEqual("runtime", initial["data_source"])
        self.assertEqual("READY", initial["status"])
        self.assertEqual(200, run_status)
        self.assertTrue(dispatched["ok"])
        task = next(item for item in after["state"]["tasks"] if item["task_id"] == "science:hypothesis")
        self.assertEqual("REVIEW", after["state"]["taskStates"][task["task_id"]])
        self.assertEqual(1, task["attempts"])

    def test_get_execution_settings_is_read_only_and_reports_readiness(self):
        before = self.store.load_execution_settings()
        status, settings = self.request("/api/settings/execution")
        after = self.store.load_execution_settings()

        self.assertEqual(200, status)
        self.assertEqual("personal-ai-os.execution-settings/v1", settings["schema_version"])
        self.assertEqual("READY", settings["status"])
        self.assertEqual("runtime", settings["data_source"])
        self.assertEqual(
            {"task_dispatch_ready": True, "advance_route_mode": "fixed", "advance_ready": True},
            settings["execution"],
        )
        self.assertIn("execution_settings", settings)
        self.assertIn("adapters", settings)
        self.assertIsNone(before)
        self.assertIsNone(after)
        self.assertNotIn("api_key", json.dumps(settings, ensure_ascii=False))

    def test_public_safe_execution_settings_get_preserves_alias_boundary(self):
        app = RuntimeApplication(
            store=self.store,
            adapters={"client-alpha-adapter": ClientNamedAdapter()},
            default_model="client-alpha-model",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            runtime_routes=[
                {
                    "route": "client-alpha-route",
                    "adapter_id": "client-alpha-adapter",
                    "model": "client-alpha-model",
                    "capabilities": ["client-alpha-writing"],
                    "enabled": True,
                }
            ],
            presentation={
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {},
                "tasks": {},
            },
            projection_mode="public-safe",
        )

        settings = app.execution_settings_projection()
        serialized = json.dumps(settings, ensure_ascii=False)

        self.assertEqual("READY", settings["status"])
        self.assertEqual("model-01", settings["default_model"])
        self.assertEqual("adapter-01", settings["adapters"][0]["adapter_id"])
        self.assertNotIn("client-alpha", serialized)
        self.assertNotIn("protocol", settings["adapters"][0])

    def test_runtime_projection_returns_result_feedback_and_real_timeline(self):
        run_status, dispatched = self.request(
            "/api/runs",
            {
                "task_id": "science:hypothesis",
                "adapter_id": "test-adapter",
                "model": "model-a",
            },
        )

        _, after = self.request("/api/runtime")
        task = next(
            item
            for item in after["state"]["tasks"]
            if item["task_id"] == "science:hypothesis"
        )

        self.assertEqual(200, run_status)
        self.assertTrue(dispatched["ok"])
        self.assertEqual("REVIEW", task["status"])
        self.assertEqual("REGISTERED", task["result"]["status"])
        self.assertEqual("API result", task["result"]["summary"])
        self.assertEqual("API result", task["result"]["preview"])
        self.assertRegex(task["result"]["created_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertTrue(task["events"])
        self.assertRegex(task["events"][0]["occurred_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertIn("run_id", task["events"][0])
        self.assertEqual("process", task["events"][0]["runtime"]["event"]["kind"])
        self.assertEqual(
            task["task_id"], task["events"][0]["runtime"]["run"]["task_id"]
        )

    def test_public_safe_result_feedback_omits_private_preview(self):
        app = RuntimeApplication(
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="model-a",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            presentation={
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {},
                "tasks": {},
            },
            projection_mode="public-safe",
        )

        dispatched = app.broker.dispatch(
            "science:hypothesis",
            adapter_id="test-adapter",
            model="model-a",
        )
        projection = app.projection()
        task = next(item for item in projection["state"]["tasks"] if item["result"])
        serialized = json.dumps(projection, ensure_ascii=False)

        self.assertTrue(dispatched["ok"])
        self.assertEqual("REGISTERED", task["result"]["status"])
        self.assertNotIn("preview", task["result"])
        self.assertNotIn("API result", serialized)

    def test_empty_workflow_keeps_its_domain_in_the_runtime_projection(self):
        created_status, created = self.request(
            "/api/workflows",
            {
                "workflow_id": "empty-product-line",
                "name": "空工作线",
                "caption": "等待添加任务",
                "layout": "custom",
                "goal": "保留所属领域",
                "domain_id": "product",
            },
        )

        read_status, projection = self.request("/api/runtime")
        line = next(
            item
            for item in projection["state"]["businessLines"]
            if item["line_id"] == "empty-product-line"
        )

        self.assertEqual(200, created_status)
        self.assertEqual("product", created["domain_id"])
        self.assertEqual(200, read_status)
        self.assertEqual("product", line["domain_id"])

    def test_runtime_projection_links_module_work_to_task_truth(self):
        self.store.create_task({
            "task_id": "science:module-link",
            "workflow_id": "science",
            "title": "建设长期任务内核",
            "acceptance": "模块与任务能够互相定位",
            "module_links": [{
                "module_id": "longtask-kernel",
                "relation": "BUILDS",
                "source": "EXPLICIT",
                "status": "CONFIRMED",
            }],
        })

        _, projection = self.request("/api/runtime")

        module_work = projection["state"]["moduleWork"]
        self.assertEqual(
            ["science:module-link"],
            module_work["by_module"]["longtask-kernel"]["task_ids"],
        )
        task = next(
            item for item in projection["state"]["tasks"]
            if item["task_id"] == "science:module-link"
        )
        self.assertEqual("longtask-kernel", task["module_links"][0]["module_id"])

    def test_runtime_projection_exposes_only_cognitive_counts(self):
        self.store.create_memory_candidate({
            "schema_version": "personal-ai-os.memory-candidate/v1",
            "candidate_id": "private-habit",
            "subject": {"kind": "person", "id": "writer-a"},
            "domain_id": "science",
            "category": "warning",
            "statement": "PRIVATE_STYLE_SENTINEL",
            "evidence_refs": ["artifact:accepted"],
            "sample_count": 2,
            "privacy_class": "private",
        })

        _, projection = self.request("/api/runtime")
        serialized = json.dumps(projection["state"], ensure_ascii=False)

        self.assertEqual(1, projection["state"]["cognitiveLearning"]["proposed"])
        self.assertEqual(0, projection["state"]["cognitiveLearning"]["approved"])
        self.assertNotIn("PRIVATE_STYLE_SENTINEL", serialized)

    def test_private_local_projection_keeps_private_task_copy_but_whitelists_adapter_probe(self):
        self.store.create_task(
            {
                "task_id": "science:private",
                "workflow_id": "science",
                "line_id": "science",
                "title": "私人任务原文",
                "acceptance": "保留完整材料",
                "depends_on": [],
            }
        )
        self.server.app.broker.adapters = {"test-adapter": NoisyProbeAdapter()}

        _, payload = self.request("/api/runtime")

        self.assertIn("私人任务原文", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(payload, ensure_ascii=False))
        self.assertEqual("private-local", self.server.app.projection_mode)

    def test_private_local_server_rejects_non_loopback_binding(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            create_runtime_server(
                ("0.0.0.0", 0),
                store=self.store,
                adapters={"test-adapter": SuccessfulAdapter()},
                default_model="model-a",
                web_root=Path(__file__).resolve().parents[1] / "workbench",
                projection_mode="private-local",
            )

    def test_public_safe_projection_aliases_execution_labels_and_resolves_them(self):
        app = RuntimeApplication(
            store=self.store,
            adapters={"client-alpha-adapter": ClientNamedAdapter()},
            default_model="client-alpha-model",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            runtime_routes=[
                {
                    "route": "client-alpha-route",
                    "adapter_id": "client-alpha-adapter",
                    "model": "client-alpha-model",
                    "capabilities": ["client-alpha-writing"],
                    "enabled": True,
                }
            ],
            presentation={
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {},
                "tasks": {},
            },
            projection_mode="public-safe",
        )

        projection = app.projection()
        dispatched = app.broker.dispatch(
            "science:hypothesis",
            adapter_id="client-alpha-adapter",
            model="client-alpha-model",
        )
        after_dispatch = app.projection()
        serialized = json.dumps(projection, ensure_ascii=False)
        after_serialized = json.dumps(after_dispatch, ensure_ascii=False)

        self.assertTrue(dispatched["ok"])
        self.assertNotIn("client-alpha", serialized)
        self.assertNotIn("client-alpha", after_serialized)
        self.assertEqual("model-01", projection["default_model"])
        self.assertEqual("adapter-01", projection["adapters"][0]["adapter_id"])
        self.assertNotIn("protocol", projection["adapters"][0])
        self.assertEqual("route-01", projection["execution_settings"]["routes"][0]["route"])
        self.assertEqual("capability-01", projection["execution_settings"]["routes"][0]["capabilities"][0])
        assignment = next(iter(after_dispatch["state"]["assignments"].values()))
        self.assertEqual("model-01", assignment["model"])
        self.assertEqual("adapter-01", assignment["executor"])
        self.assertEqual(
            "client-alpha-adapter", app.resolve_adapter_id("adapter-01")
        )
        self.assertEqual("client-alpha-model", app.resolve_model("model-01"))

    def test_routes_only_projection_reports_automatic_advance_readiness(self):
        app = RuntimeApplication(
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            runtime_routes=[
                {
                    "route": "deep-science",
                    "adapter_id": "test-adapter",
                    "model": "model-routed",
                    "enabled": True,
                }
            ],
        )

        projection = app.projection()

        self.assertEqual(
            {
                "task_dispatch_ready": True,
                "advance_route_mode": "automatic",
                "advance_ready": True,
            },
            projection["execution"],
        )
        self.assertEqual("server-environment", projection["execution_settings"]["credential_source"])
        self.assertEqual("deep-science", projection["execution_settings"]["routes"][0]["route"])

    def test_api_advances_ready_work_with_a_bounded_request(self):
        status, advanced = self.request(
            "/api/advance",
            {"adapter_id": "test-adapter", "model": "model-a", "max_steps": 2, "workflow_id": "science"},
        )

        self.assertEqual(200, status)
        self.assertTrue(advanced["ok"])
        self.assertEqual(1, advanced["advanced_count"])
        self.assertEqual("science:hypothesis", advanced["actions"][0]["task_id"])
        self.assertEqual("WAITING_REVIEW", advanced["stop_reason"])

    def test_advance_api_uses_the_server_route_catalog_not_client_injection(self):
        self.server.app.runtime_routes = [
            {
                "route": "deep-science",
                "tier": "deep",
                "capabilities": ["reasoning", "evidence"],
                "max_context_tokens": 160000,
                "adapter_id": "test-adapter",
                "model": "model-routed",
                "enabled": True,
            }
        ]
        try:
            status, advanced = self.request(
                "/api/advance",
                {
                    "route_mode": "automatic",
                    "workflow_id": "science",
                    "max_steps": 1,
                    "routes": [
                        {
                            "route": "client-injected",
                            "adapter_id": "missing",
                            "model": "untrusted-model",
                        }
                    ],
                },
            )
        except urllib.error.HTTPError as exc:
            self.fail(f"automatic route request must use the server catalog: HTTP {exc.code}")

        self.assertEqual(200, status)
        self.assertTrue(advanced["ok"])
        self.assertEqual("deep-science", advanced["actions"][0]["route"])
        self.assertEqual("model-routed", advanced["actions"][0]["model"])
        self.assertEqual(
            "model-routed",
            self.store.snapshot()["assignments"]["science:hypothesis"]["model"],
        )

    def test_routes_only_server_advances_the_workbench_request_automatically(self):
        self.server.app.default_model = ""
        self.server.app.runtime_routes = [
            {
                "route": "deep-science",
                "tier": "deep",
                "capabilities": ["reasoning", "evidence"],
                "max_context_tokens": 160000,
                "adapter_id": "test-adapter",
                "model": "model-routed",
                "enabled": True,
            }
        ]

        status, advanced = self.request(
            "/api/advance",
            {"workflow_id": "science", "max_steps": 1},
        )

        self.assertEqual(200, status)
        self.assertTrue(advanced["ok"])
        self.assertEqual("deep-science", advanced["actions"][0]["route"])

    def test_routes_only_server_dispatches_one_task_from_saved_settings(self):
        self.server.app.default_model = ""
        self.server.app.runtime_routes = [
            {
                "route": "deep-science",
                "tier": "deep",
                "capabilities": ["reasoning", "evidence"],
                "max_context_tokens": 160000,
                "adapter_id": "test-adapter",
                "model": "model-routed",
                "enabled": True,
            }
        ]

        status, result = self.request(
            "/api/runs",
            {"task_id": "science:hypothesis"},
        )

        self.assertEqual(200, status)
        self.assertTrue(result["ok"])
        self.assertEqual(
            "model-routed",
            self.store.snapshot()["assignments"]["science:hypothesis"]["model"],
        )

    def test_fixed_server_dispatches_only_through_its_saved_default_adapter(self):
        unrelated = CountingAdapter("a-unrelated")
        configured = CountingAdapter("z-configured")
        server = create_runtime_server(
            ("127.0.0.1", 0),
            store=self.store,
            adapters={unrelated.adapter_id: unrelated, configured.adapter_id: configured},
            default_model="model-a",
            default_adapter_id=configured.adapter_id,
            web_root=Path(__file__).resolve().parents[1] / "workbench",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                urllib.request.Request(
                    base + "/api/runs",
                    data=json.dumps(
                        {
                            "task_id": "science:hypothesis",
                        }
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=3,
            ) as response:
                result = json.loads(response.read())
            projection = server.app.projection()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertTrue(result["ok"])
        self.assertEqual(0, unrelated.calls)
        self.assertEqual(1, configured.calls)
        self.assertEqual("z-configured", projection["execution_settings"]["default_adapter_id"])
        self.assertTrue(projection["execution"]["task_dispatch_ready"])

    def test_private_browser_binds_api_credentials_without_projecting_them(self):
        secret = "sk-browser-session-private-sentinel"
        status, configured = self.request(
            "/api/settings/execution",
            {
                "mode": "fixed",
                "adapter": {
                    "kind": "openai-compatible",
                    "api_base": "https://example.invalid/v1",
                    "api_key": secret,
                    "model": "model-browser",
                },
            },
        )
        _, projection = self.request("/api/runtime")
        serialized = json.dumps(projection, ensure_ascii=False)

        self.assertEqual(200, status)
        self.assertTrue(configured["execution"]["task_dispatch_ready"])
        self.assertEqual("model-browser", projection["default_model"])
        self.assertEqual("browser-session", projection["execution_settings"]["credential_source"])
        self.assertNotIn(secret, serialized)
        self.assertNotIn("example.invalid", serialized)
        self.assertNotIn("api_key", serialized)

    def test_private_browser_binds_workflow_to_a_codex_project(self):
        project = Path(self.temp.name) / "science-project"
        project.mkdir()

        status, configured = self.request(
            "/api/settings/execution",
            {
                "mode": "fixed",
                "adapter": {
                    "kind": "codex-project",
                    "model": "gpt-5.6-sol",
                    "projects": [
                        {
                            "project_key": "science-workspace",
                            "label": "科研项目",
                            "path": str(project),
                            "workflow_ids": ["science"],
                            "environment": "worktree",
                        }
                    ],
                },
            },
        )

        self.assertEqual(200, status)
        self.assertTrue(configured["execution"]["task_dispatch_ready"])
        self.assertEqual(
            [
                {
                    "project_key": "science-workspace",
                    "label": "科研项目",
                    "path": str(project.resolve()),
                    "workflow_ids": ["science"],
                    "domain_ids": [],
                    "environment": "worktree",
                }
            ],
            configured["execution_settings"]["codex_projects"],
        )

    def test_private_execution_settings_restore_codex_binding_after_application_restart(self):
        project = Path(self.temp.name) / "science-project"
        project.mkdir()
        _, configured = self.request(
            "/api/settings/execution",
            {
                "mode": "fixed",
                "adapter": {
                    "kind": "codex-project",
                    "model": "gpt-5.6-sol",
                    "projects": [
                        {
                            "project_key": "science-workspace",
                            "label": "科研项目",
                            "path": str(project),
                            "workflow_ids": ["science"],
                            "environment": "worktree",
                        }
                    ],
                },
            },
        )

        restarted_store = RuntimeStore(self.store.database)
        restarted = RuntimeApplication(
            store=restarted_store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="fallback-model",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
        )
        projection = restarted.projection()

        self.assertTrue(configured["execution"]["task_dispatch_ready"])
        self.assertEqual("gpt-5.6-sol", projection["default_model"])
        self.assertEqual("codex-project", projection["execution_settings"]["default_adapter_id"])
        self.assertEqual("科研项目", projection["execution_settings"]["codex_projects"][0]["label"])
        self.assertTrue(projection["execution"]["task_dispatch_ready"])

    def test_private_api_key_never_enters_persisted_execution_settings(self):
        secret = "sk-persisted-settings-must-not-contain-me"
        self.request(
            "/api/settings/execution",
            {
                "mode": "fixed",
                "adapter": {
                    "kind": "openai-compatible",
                    "api_base": "https://example.invalid/v1",
                    "api_key": secret,
                    "model": "model-browser",
                },
            },
        )

        with sqlite3.connect(self.store.database) as connection:
            rows = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'execution_settings'"
            ).fetchall()
            persisted = " ".join(str(row[0]) for row in rows)
            values = connection.execute("SELECT * FROM execution_settings").fetchall()
            persisted += " " + json.dumps(values, ensure_ascii=False)

        self.assertNotIn("api_key", persisted)
        self.assertNotIn(secret, persisted)

    def test_private_task_routes_restore_after_application_restart(self):
        routes = [
            {
                "route": "research-deep",
                "tier": "deep",
                "capabilities": ["research", "evidence"],
                "max_context_tokens": 160000,
                "adapter_id": "test-adapter",
                "model": "research-model",
                "enabled": True,
            }
        ]
        status, configured = self.request(
            "/api/settings/execution",
            {"mode": "automatic", "routes": routes},
        )

        restarted = RuntimeApplication(
            store=RuntimeStore(self.store.database),
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="fallback-model",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
        )
        projection = restarted.projection()

        self.assertEqual(200, status)
        self.assertTrue(configured["execution"]["advance_ready"])
        self.assertEqual("automatic", projection["execution_settings"]["mode"])
        self.assertEqual(routes, projection["execution_settings"]["routes"])
        self.assertTrue(projection["execution"]["advance_ready"])

    def test_private_codex_app_server_binding_restores_from_factory_after_restart(self):
        configured = CountingAdapter("codex-app-server")
        factory = lambda _config: (configured, "codex-model")
        app = RuntimeApplication(
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="fallback-model",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            execution_adapter_factories={"codex-app-server": factory},
        )
        configured_projection = app.configure_execution(
            {
                "mode": "fixed",
                "adapter": {"kind": "codex-app-server", "model": "codex-model"},
            }
        )

        restarted = RuntimeApplication(
            store=RuntimeStore(self.store.database),
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="fallback-model",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            execution_adapter_factories={"codex-app-server": factory},
        )
        projection = restarted.projection()

        self.assertTrue(configured_projection["execution"]["task_dispatch_ready"])
        self.assertEqual("codex-app-server", projection["execution_settings"]["default_adapter_id"])
        self.assertEqual("codex-model", projection["default_model"])
        self.assertTrue(projection["execution"]["task_dispatch_ready"])

    def test_codex_project_bridge_claims_binds_and_completes_a_browser_dispatch(self):
        project = Path(self.temp.name) / "science-project"
        project.mkdir()
        self.request(
            "/api/settings/execution",
            {
                "mode": "fixed",
                "adapter": {
                    "kind": "codex-project",
                    "model": "gpt-5.6-sol",
                    "projects": [
                        {
                            "project_key": "science-workspace",
                            "label": "科研项目",
                            "path": str(project),
                            "workflow_ids": ["science"],
                            "environment": "worktree",
                        }
                    ],
                },
            },
        )

        advanced_status, advanced = self.request(
            "/api/advance", {"workflow_id": "science", "max_steps": 1}
        )
        pending_status, pending = self.request("/api/codex-project/dispatches")
        claim_status, claimed = self.request(
            "/api/codex-project/claim", {"worker_id": "manager-thread"}
        )
        dispatch_id = claimed["dispatch_id"]
        bind_status, bound = self.request(
            f"/api/codex-project/dispatches/{dispatch_id}/bind",
            {
                "thread_id": "codex-thread-1", "project_id": "codex-project-1", "host_id": "local",
                "verification": {
                    "source": "task-project", "verified": True,
                    "project_id": "codex-project-1", "project_path": str(project),
                    "environment": "worktree",
                },
            },
        )
        complete_status, completed = self.request(
            f"/api/codex-project/dispatches/{dispatch_id}/complete",
            {
                "output_text": "项目线程已完成任务。", "usage": {"input_tokens": 10},
                "completion_receipt": {
                    "status": "completed", "verified": True,
                    "needs_user_input": False, "human_gate": False,
                },
            },
        )

        self.assertEqual(200, advanced_status)
        self.assertEqual("RECOVERY_REQUIRED", advanced["stop_reason"])
        self.assertEqual(200, pending_status)
        self.assertEqual(1, len(pending["dispatches"]))
        self.assertEqual(200, claim_status)
        self.assertEqual("CLAIMED", claimed["status"])
        self.assertEqual("科研项目", claimed["project"]["label"])
        self.assertEqual(200, bind_status)
        self.assertEqual("RUNNING", bound["status"])
        self.assertEqual(200, complete_status)
        self.assertTrue(completed["ok"])
        self.assertEqual("REVIEW", completed["status"])
        self.assertEqual("REVIEW", self.store.get_task("science:hypothesis")["status"])
        _, reviewed_projection = self.request("/api/runtime")
        reviewed_task = next(
            item
            for item in reviewed_projection["state"]["tasks"]
            if item["task_id"] == "science:hypothesis"
        )
        self.assertEqual("SUCCEEDED", reviewed_task["codex_dispatch"]["status"])
        self.assertEqual("codex-thread-1", reviewed_task["codex_dispatch"]["thread_id"])
        self.assertEqual("codex-project-1", reviewed_task["codex_dispatch"]["project_id"])
        self.assertEqual(
            "task-project",
            reviewed_task["codex_dispatch"]["thread_verification"]["source"],
        )
        self.assertFalse(reviewed_task["codex_dispatch"]["completion_receipt"]["human_gate"])

    def test_runtime_projection_surfaces_codex_project_queue_and_bound_thread(self):
        project = Path(self.temp.name) / "science-project"
        project.mkdir()
        self.request(
            "/api/settings/execution",
            {
                "mode": "fixed",
                "adapter": {
                    "kind": "codex-project",
                    "model": "model-a",
                    "projects": [
                        {
                            "project_key": "science-workspace",
                            "label": "科研项目",
                            "path": str(project),
                            "workflow_ids": ["science"],
                            "environment": "worktree",
                        }
                    ],
                },
            },
        )

        run_status, dispatched = self.request(
            "/api/runs",
            {"task_id": "science:hypothesis", "adapter_id": "codex-project", "model": "model-a"},
        )
        _, queued = self.request("/api/runtime")
        queued_task = next(
            item for item in queued["state"]["tasks"] if item["task_id"] == "science:hypothesis"
        )
        dispatch = queued_task["codex_dispatch"]
        claim_status, claimed = self.request(
            "/api/codex-project/claim", {"worker_id": "runtime-projection-test"}
        )
        _, claimed_projection = self.request("/api/runtime")
        claimed_task = next(
            item
            for item in claimed_projection["state"]["tasks"]
            if item["task_id"] == "science:hypothesis"
        )
        bind_status, bound = self.request(
            f"/api/codex-project/dispatches/{claimed['dispatch_id']}/bind",
            {
                "thread_id": "codex-thread-projection", "project_id": "codex-project-1", "host_id": "local",
                "verification": {
                    "source": "thread-project-assignments", "verified": True,
                    "project_id": "codex-project-1", "project_path": str(project),
                    "environment": "worktree",
                },
            },
        )
        _, bound_projection = self.request("/api/runtime")
        bound_task = next(
            item
            for item in bound_projection["state"]["tasks"]
            if item["task_id"] == "science:hypothesis"
        )

        self.assertEqual(200, run_status)
        self.assertTrue(dispatched["ok"])
        self.assertEqual("PENDING", dispatch["status"])
        self.assertEqual("科研项目", dispatch["project"]["label"])
        self.assertIsNone(dispatch["thread_id"])
        self.assertEqual(200, claim_status)
        self.assertEqual("CLAIMED", claimed_task["codex_dispatch"]["status"])
        self.assertEqual(200, bind_status)
        self.assertEqual("RUNNING", bound["status"])
        self.assertEqual("RUNNING", bound_task["codex_dispatch"]["status"])
        self.assertEqual("codex-thread-projection", bound_task["codex_dispatch"]["thread_id"])

    def test_live_broker_run_is_not_misreported_as_restart_recovery(self):
        self.store.create_goal(
            {
                "goal_id": "goal:live",
                "title": "实时推进",
                "objective": "区分当前运行与重启遗留运行",
                "workflow_ids": ["science"],
                "completion_criteria": "任务完成",
                "continuation_policy": {
                    "max_steps_per_continuation": 1,
                    "max_total_steps": 10,
                    "max_total_tokens": 10000,
                    "failure_budget_per_continuation": 1,
                },
            }
        )
        adapter = BlockingAdapter()
        app = RuntimeApplication(
            store=self.store,
            adapters={adapter.adapter_id: adapter},
            default_model="model-a",
            default_adapter_id=adapter.adapter_id,
            web_root=Path(__file__).resolve().parents[1] / "workbench",
        )
        worker = threading.Thread(
            target=lambda: app.broker.dispatch(
                "science:hypothesis",
                adapter_id=adapter.adapter_id,
                model="model-a",
            ),
            daemon=True,
        )
        worker.start()
        self.assertTrue(adapter.started.wait(timeout=1))

        live_goal = app.projection()["state"]["durableGoals"][0]
        reopened = RuntimeApplication(
            store=RuntimeStore(self.store.database),
            adapters={adapter.adapter_id: adapter},
            default_model="model-a",
            default_adapter_id=adapter.adapter_id,
            web_root=Path(__file__).resolve().parents[1] / "workbench",
        )
        reopened_goal = reopened.projection()["state"]["durableGoals"][0]
        adapter.release.set()
        worker.join(timeout=3)

        self.assertFalse(live_goal["recovery_required"])
        self.assertTrue(reopened_goal["recovery_required"])

    def test_private_browser_auto_configures_codex_and_saves_automatic_routes(self):
        codex = CountingAdapter("codex-app-server")

        def codex_factory(config):
            self.assertEqual("", config.get("model", ""))
            return codex, "gpt-codex-detected"

        server = create_runtime_server(
            ("127.0.0.1", 0),
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="model-a",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            execution_adapter_factories={"codex-app-server": codex_factory},
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(payload):
            request = urllib.request.Request(
                base + "/api/settings/execution",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                request, timeout=3
            ) as response:
                return json.loads(response.read())

        try:
            fixed = post(
                {
                    "mode": "fixed",
                    "adapter": {"kind": "codex-app-server", "model": ""},
                }
            )
            automatic = post(
                {
                    "mode": "automatic",
                    "routes": [
                        {
                            "route": "research-deep",
                            "tier": "deep",
                            "capabilities": ["research", "writing"],
                            "max_context_tokens": 120000,
                            "adapter_id": "codex-app-server",
                            "model": "gpt-codex-detected",
                            "enabled": True,
                        }
                    ],
                }
            )
            projection = server.app.projection()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual("gpt-codex-detected", fixed["default_model"])
        self.assertTrue(fixed["execution"]["task_dispatch_ready"])
        self.assertEqual("automatic", automatic["execution"]["advance_route_mode"])
        self.assertTrue(automatic["execution"]["advance_ready"])
        self.assertEqual("research-deep", projection["execution_settings"]["routes"][0]["route"])

    def test_execution_settings_reject_invalid_routes_without_partial_mutation(self):
        _, before = self.request("/api/runtime")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request(
                "/api/settings/execution",
                {
                    "mode": "automatic",
                    "routes": [
                        {
                            "route": "broken",
                            "tier": "deep",
                            "capabilities": ["research"],
                            "max_context_tokens": 120000,
                            "adapter_id": "missing-adapter",
                            "model": "model-b",
                            "enabled": True,
                        }
                    ],
                },
            )
        _, after = self.request("/api/runtime")

        self.assertEqual(422, caught.exception.code)
        self.assertEqual(before["default_model"], after["default_model"])
        self.assertEqual(before["execution_settings"], after["execution_settings"])

    def test_public_safe_runtime_rejects_browser_execution_configuration(self):
        app = RuntimeApplication(
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="model-a",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            presentation={
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {},
                "tasks": {},
            },
            projection_mode="public-safe",
        )

        with self.assertRaisesRegex(ValueError, "private-local"):
            app.configure_execution({"mode": "fixed"})

    def test_private_runtime_projects_and_continues_a_durable_goal(self):
        self.store.create_goal(
            {
                "goal_id": "goal:science-release",
                "title": "完成本轮科研验证",
                "objective": "推进已登记科研任务，并把结论交回人工验收。",
                "workflow_ids": ["science"],
                "completion_criteria": "全部任务经过人工验收",
                "continuation_policy": {
                    "max_steps_per_continuation": 1,
                    "max_total_steps": 10,
                    "max_total_tokens": 10000,
                    "failure_budget_per_continuation": 1,
                },
            }
        )

        _, initial = self.request("/api/runtime")
        continued_status, continued = self.request(
            "/api/goals/goal%3Ascience-release/continue",
            {"adapter_id": "test-adapter", "model": "model-a"},
        )
        _, after = self.request("/api/runtime")

        self.assertEqual("完成本轮科研验证", initial["state"]["durableGoals"][0]["title"])
        self.assertEqual(200, continued_status)
        self.assertEqual(1, continued["steps_used"])
        self.assertEqual("WAITING_REVIEW", continued["stop_reason"])
        self.assertEqual(1, after["state"]["durableGoals"][0]["usage"]["continuation_count"])

    def test_public_safe_goal_projection_never_exposes_private_goal_copy(self):
        self.store.create_goal(
            {
                "goal_id": "goal:private-client-release",
                "title": "PRIVATE_GOAL_TITLE_SENTINEL",
                "objective": "PRIVATE_OBJECTIVE_SENTINEL",
                "workflow_ids": ["science"],
                "completion_criteria": "PRIVATE_CRITERIA_SENTINEL",
                "continuation_policy": {},
            }
        )
        app = RuntimeApplication(
            store=self.store,
            adapters={"test-adapter": SuccessfulAdapter()},
            default_model="model-a",
            web_root=Path(__file__).resolve().parents[1] / "workbench",
            presentation={
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {},
                "tasks": {},
            },
            projection_mode="public-safe",
        )

        serialized = json.dumps(app.projection(), ensure_ascii=False)

        self.assertNotIn("private-client", serialized)
        self.assertNotIn("PRIVATE_GOAL", serialized)
        self.assertNotIn("PRIVATE_OBJECTIVE", serialized)
        self.assertNotIn("PRIVATE_CRITERIA", serialized)
        self.assertIn("长期目标 01", serialized)

    def test_running_goal_is_projected_as_recovery_required(self):
        self.store.create_goal(
            {
                "goal_id": "goal:science-release",
                "title": "完成本轮科研验证",
                "objective": "推进后等待外部运行回执。",
                "workflow_ids": ["science"],
                "completion_criteria": "全部任务经过人工验收",
                "continuation_policy": {},
            }
        )
        run = self.store.claim_run(
            task_id="science:hypothesis",
            adapter_id="test-adapter",
            model="model-a",
            by="adapter:test-adapter",
        )
        self.assertTrue(run["ok"])

        projection = self.server.app.projection()

        self.assertTrue(
            projection["state"]["durableGoals"][0]["recovery_required"]
        )

    def test_advance_api_rejects_non_integer_limits_without_dropping_the_connection(self):
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            self.request(
                "/api/advance",
                {"adapter_id": "test-adapter", "model": "model-a", "max_steps": [1]},
            )

        self.assertEqual(422, invalid.exception.code)
        self.assertEqual([], self.store.snapshot()["runs"])

    def test_api_creates_tasks_and_accepts_reviewed_results(self):
        _, created = self.request(
            "/api/tasks",
            {
                "task_id": "science:extra",
                "workflow_id": "science",
                "line_id": "science",
                "title": "Additional bounded task",
                "acceptance": "One inspectable artifact",
                "depends_on": [],
                "required_capabilities": ["reasoning"],
            },
        )
        self.request(
            "/api/runs",
            {"task_id": "science:extra", "adapter_id": "test-adapter", "model": "model-a"},
        )
        _, accepted = self.request(
            "/api/tasks/science%3Aextra/transition",
            {"to": "DONE", "by": "owner", "reason": "Accepted result"},
        )

        self.assertEqual("science:extra", created["task_id"])
        self.assertTrue(accepted["ok"])
        self.assertEqual("DONE", self.store.get_task("science:extra")["status"])

    def test_runtime_projection_omits_local_task_context_and_git_closure(self):
        self.store.create_task({
            "task_id": "science:private-local-reference",
            "workflow_id": "science",
            "title": "Use a registered local workspace",
            "acceptance": "The local reference remains server-side",
            "context": {
                "workspace_path": "/private/SENSITIVE_SENTINEL",
                "model_context": {"instruction": "Use only accepted evidence."},
            },
        })

        _, projection = self.request("/api/runtime")
        serialized = json.dumps(projection, ensure_ascii=False)
        task = next(
            item
            for item in projection["state"]["tasks"]
            if item["task_id"] == "science:private-local-reference"
        )

        self.assertNotIn("context", task)
        self.assertNotIn("git_closure", task)
        self.assertNotIn("SENSITIVE_SENTINEL", serialized)

    def test_presentation_aliases_round_trip_without_exposing_runtime_ids(self):
        self.store.create_workflow(
            {
                "workflow_id": "/Users/example/private-second-line",
                "name": "Private second line",
                "caption": "Private",
                "layout": "branch",
                "goal": "Private",
            }
        )
        self.server.app.presentation = validate_presentation(
            {
                "schema_version": "personal-ai-os.presentation/v1",
                "workflows": {"science": {"name": "科研工作线"}},
                "tasks": {
                    "science:hypothesis": {
                        "title": "提出可检验假设",
                        "acceptance": "假设边界清晰",
                    }
                },
            }
        )
        self.server.app.projection_mode = "public-safe"

        _, initial = self.request("/api/runtime")
        task = initial["state"]["tasks"][0]
        with self.assertRaises(urllib.error.HTTPError) as private_model:
            self.request(
                "/api/runs",
                {
                    "task_id": task["task_id"],
                    "adapter_id": "test-adapter",
                    "model": "/Users/example/private-model",
                },
            )
        private_model_payload = json.loads(private_model.exception.read())
        self.assertEqual([], self.store.snapshot()["runs"])
        run_status, dispatched = self.request(
            "/api/runs",
            {
                "task_id": task["task_id"],
                "adapter_id": initial["adapters"][0]["adapter_id"],
                "model": initial["default_model"],
            },
        )
        transition_status, accepted = self.request(
            f"/api/tasks/{task['task_id']}/transition",
            {"to": "DONE", "by": "owner", "reason": "Accepted result"},
        )
        with self.assertRaises(urllib.error.HTTPError) as invalid_dependency:
            self.request(
                "/api/tasks",
                {
                    "task_id": "public-new-task",
                    "workflow_id": "line-02",
                    "line_id": "line-02",
                    "title": "公开任务",
                    "acceptance": "形成阶段结果",
                    "depends_on": ["task-001"],
                },
            )
        error_payload = json.loads(invalid_dependency.exception.read())
        serialized = json.dumps(
            {
                "initial": initial,
                "dispatched": dispatched,
                "accepted": accepted,
                "error": error_payload,
                "private_model": private_model_payload,
            },
            ensure_ascii=False,
        )

        self.assertEqual("line-01", initial["state"]["activeLineId"])
        self.assertEqual("task-001", task["task_id"])
        self.assertEqual(200, run_status)
        self.assertEqual(200, transition_status)
        self.assertEqual(422, invalid_dependency.exception.code)
        self.assertEqual("REQUEST_REJECTED", error_payload["reason"])
        self.assertEqual("REQUEST_REJECTED", private_model_payload["reason"])
        self.assertNotIn("science:hypothesis", serialized)
        self.assertNotIn('"science"', serialized)
        self.assertNotIn("/Users/", serialized)
        self.assertEqual("DONE", self.store.get_task("science:hypothesis")["status"])

    def test_server_blocks_path_traversal_and_client_adapter_override(self):
        with self.assertRaises(urllib.error.HTTPError) as traversal:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                self.base + "/../README.md", timeout=3
            )
        with self.assertRaises(urllib.error.HTTPError) as adapter:
            self.request(
                "/api/runs",
                {"task_id": "science:hypothesis", "adapter_id": "missing", "model": "model-a"},
            )

        self.assertEqual(404, traversal.exception.code)
        self.assertEqual(422, adapter.exception.code)
        self.assertEqual([], self.store.snapshot()["runs"])

    def test_write_api_rejects_cross_site_and_non_json_requests(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        non_json = urllib.request.Request(
            self.base + "/api/runs",
            data=b"{}",
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        cross_site = urllib.request.Request(
            self.base + "/api/runs",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://untrusted.example",
            },
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as content_type:
            opener.open(non_json, timeout=3)
        with self.assertRaises(urllib.error.HTTPError) as origin:
            opener.open(cross_site, timeout=3)

        self.assertEqual(415, content_type.exception.code)
        self.assertEqual(403, origin.exception.code)
        self.assertEqual([], self.store.snapshot()["runs"])


if __name__ == "__main__":
    unittest.main()
