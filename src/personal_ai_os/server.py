from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .adapters import OpenAICompatibleAdapter
from .acceptance_projection import build_acceptance_snapshot
from .codex_adapter import CodexAppServerAdapter
from .codex_project import CodexProjectAdapter
from .route_config import RUNTIME_ROUTES_SCHEMA, validate_runtime_routes
from .runtime import ExecutionBroker, RuntimeStore
from .runtime_events import EventValidationError, from_legacy_event
from .automation import AutoAdvanceEngine
from .goals import GoalController
from .secretary import build_secretary_brief
from .task_links import module_work_projection
from .presentation import (
    apply_presentation,
    identifier_aliases,
    validate_presentation,
    validate_runtime_label,
)


def runtime_workbench_state(
    store: RuntimeStore,
    presentation: dict[str, Any] | None = None,
    live_task_ids: set[str] | None = None,
    codex_dispatches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot = apply_presentation(store.snapshot(), presentation)
    live_task_ids = set(live_task_ids or ())
    codex_dispatch_by_task = {
        str(item.get("task_id")): item
        for item in (codex_dispatches or [])
        if item.get("task_id")
    }
    events_by_task: dict[str, list[dict[str, Any]]] = {}
    acceptance_events_by_task: dict[str, list[dict[str, Any]]] = {}
    acceptance_artifacts_by_task: dict[str, list[dict[str, Any]]] = {}
    artifacts_by_task: dict[str, list[dict[str, Any]]] = {}
    latest_runs_by_task: dict[str, dict[str, Any]] = {}
    downstream_by_task: dict[str, list[dict[str, Any]]] = {}
    attempts_by_run = {
        str(run.get("run_id")): int(run.get("attempt") or 1)
        for run in snapshot.get("runs", [])
        if run.get("run_id")
    }
    labels = {
        "RUN_ASSIGNED": "已分配执行器",
        "ADAPTER_STARTED": "执行适配器已启动",
        "ARTIFACT_CREATED": "阶段产物已登记",
        "RUN_SUCCEEDED": "本轮运行已完成",
        "MEMORY_REVIEW_REQUESTED": "本轮经验等待复核",
        "REVIEW_REQUESTED": "结果等待验收",
        "BLOCKED": "运行需要处理",
        "DECISION_REQUESTED": "已请求人工决定",
        "DECISION_RECORDED": "人工决定已记录",
        "AUTO_ADVANCE_SELECTED": "自动推进已选中",
        "AUTO_ADVANCE_FINISHED": "自动推进步骤已结束",
    }
    for event in snapshot["events"]:
        acceptance_events_by_task.setdefault(event["task_id"], []).append(event)
        projected_event = {
            "event_id": str(event["event_id"]),
            "kind": event["event_type"].lower(),
            "label": labels.get(event["event_type"], "运行状态已更新"),
            "at": event["at"][11:16] if len(event["at"]) >= 16 else event["at"],
            "occurred_at": event["at"],
            "run_id": event.get("run_id"),
        }
        run_id = str(event.get("run_id") or "").strip()
        if run_id:
            payload = event.get("payload") or {}
            if presentation is not None:
                payload = {
                    key: payload[key]
                    for key in ("selected_option", "from", "to", "status")
                    if key in payload
                }
            try:
                projected_event["runtime"] = from_legacy_event(
                    {
                        "event_id": event["event_id"],
                        "task_id": event["task_id"],
                        "run_id": run_id,
                        "event_type": event["event_type"],
                        "payload": payload,
                        "at": event["at"],
                        "attempt": attempts_by_run.get(run_id, 1),
                    }
                )["runtime"]
            except EventValidationError:
                # Legacy events remain visible; an uncorrelatable event is not
                # upgraded into a misleading run receipt.
                pass
        events_by_task.setdefault(event["task_id"], []).append(projected_event)
    for artifact in snapshot.get("artifacts", []):
        acceptance_artifacts_by_task.setdefault(artifact["task_id"], []).append(artifact)
        result = {
            "status": "REGISTERED",
            "artifact_id": artifact.get("artifact_id"),
            "run_id": artifact.get("run_id"),
            "summary": artifact.get("summary") or "阶段产物已登记",
            "created_at": artifact.get("created_at"),
        }
        if presentation is None:
            result["preview"] = str(artifact.get("content") or "")[:1200]
        else:
            result["summary"] = "阶段产物已登记"
        artifacts_by_task.setdefault(artifact["task_id"], []).append(result)
    for run in snapshot.get("runs", []):
        task_id = str(run.get("task_id") or "")
        if not task_id:
            continue
        previous = latest_runs_by_task.get(task_id)
        if previous is None or (
            int(run.get("attempt") or 0),
            str(run.get("started_at") or ""),
        ) >= (
            int(previous.get("attempt") or 0),
            str(previous.get("started_at") or ""),
        ):
            latest_runs_by_task[task_id] = run
    for task in snapshot.get("tasks", []):
        for dependency_id in task.get("depends_on") or []:
            downstream_by_task.setdefault(str(dependency_id), []).append(task)

    def acceptance_card(task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task.get("task_id") or "")
        dependencies = [
            item for item in snapshot.get("tasks", [])
            if item.get("task_id") in (task.get("depends_on") or [])
        ]
        downstream = downstream_by_task.get(task_id, [])
        if dependencies:
            background = "承接上游任务结果：" + "、".join(
                str(item.get("public_label") or item.get("title") or "已登记任务")
                for item in dependencies
            )
        else:
            background = "当前工作线入口任务，直接承接工作线目标。"
        status = str(task.get("status") or "QUEUED")
        current = {
            "QUEUED": "等待分配执行者。",
            "IN_PROGRESS": "任务正在执行，等待运行回执。",
            "REVIEW": "阶段产物已形成，等待人工验收。",
            "DONE": "任务已通过验收。",
            "ARCHIVED": "任务已归档。",
            "BLOCKED": "任务已阻塞，需要处理阻断原因。",
            "PAUSED": "任务已暂停，等待恢复决定。",
        }.get(status, "当前阶段状态已登记。")
        if downstream:
            next_copy = "当前任务收口后影响下游：" + "、".join(
                str(item.get("public_label") or item.get("title") or "已登记任务")
                for item in downstream
            )
        else:
            next_copy = "当前没有已登记下游，由工作线继续编排下一步。"
        return {
            **task,
            "line": task.get("line_id") or task.get("workflow_id"),
            "presentation": {
                "why": background,
                "now": current,
                "next": next_copy,
                "relationship": (
                    f"已登记 {len(dependencies)} 个上游依赖，"
                    f"影响 {len(downstream)} 个下游任务。"
                ),
            },
        }

    def acceptance_run(task_id: str) -> dict[str, Any] | None:
        run = latest_runs_by_task.get(task_id)
        if run is None:
            return None
        run = dict(run)
        # Codex binding is private-local execution metadata.  It is attached
        # only when the private projection is explicitly selected.
        if presentation is None:
            dispatch = codex_dispatch_by_task.get(task_id)
            if dispatch and dispatch.get("thread_id"):
                run["thread_id"] = dispatch.get("thread_id")
                run["binding"] = {
                    "conversation_id": dispatch.get("thread_id"),
                }
        return run
    browser_task_fields = (
        "task_id",
        "workflow_id",
        "line_id",
        "public_label",
        "title",
        "acceptance",
        "agent_role",
        "status",
        "resume_to",
        "depends_on",
        "human_gate",
        "iteration",
        "parallel_group",
        "required_capabilities",
        "complexity",
        "domain_id",
        "requires_git_closure",
        "result_ref",
        "created_at",
        "updated_at",
        "attempts",
        "artifact_refs",
        "flow_kind",
        "module_links",
        "result",
    )
    tasks = [
        {
            **{field: task.get(field) for field in browser_task_fields},
            "events": events_by_task.get(task["task_id"], []),
            "result": (artifacts_by_task.get(task["task_id"]) or [None])[-1],
            "acceptance_snapshot": build_acceptance_snapshot(
                acceptance_card(task),
                acceptance_run(str(task["task_id"])),
                events=acceptance_events_by_task.get(task["task_id"], []),
                artifacts=acceptance_artifacts_by_task.get(task["task_id"], []),
            ),
            **(
                {
                    "codex_dispatch": {
                        "status": str(dispatch.get("status") or "UNKNOWN"),
                        "dispatch_id": str(dispatch.get("dispatch_id") or ""),
                        "project": {
                            "label": str((dispatch.get("project") or {}).get("label") or "Codex 项目"),
                            "environment": str((dispatch.get("project") or {}).get("environment") or ""),
                        },
                        "thread_id": str(dispatch.get("thread_id") or "") or None,
                        "project_id": str(dispatch.get("project_id") or "") or None,
                        "host_id": str(dispatch.get("host_id") or "") or None,
                        "thread_verification": dict(dispatch.get("thread_verification") or {}),
                        "completion_receipt": dict(dispatch.get("completion_receipt") or {}),
                    }
                }
                if presentation is None and (dispatch := codex_dispatch_by_task.get(task["task_id"]))
                else {}
            ),
        }
        for task in snapshot["tasks"]
    ]
    states = {task["task_id"]: task["status"] for task in tasks}
    tasks_by_id = {task["task_id"]: task for task in tasks}
    workflows = [
        {
            "line_id": item["workflow_id"],
            "name": item["name"],
            "caption": item["caption"],
            "layout": item["layout"],
            "domain_id": item["domain_id"],
            "stages": [],
        }
        for item in snapshot["workflows"]
    ]
    active = next((task for task in tasks if task["status"] == "IN_PROGRESS"), None)
    if active is None and tasks:
        active = tasks[0]
    goal = snapshot["workflows"][0]["goal"] if snapshot["workflows"] else "尚未安装工作流"
    decisions = {
        item["task_id"]: item["selected_option"] or item["status"]
        for item in snapshot["decisions"]
    }
    pending_decisions = [
        item for item in snapshot["decisions"] if item["status"] == "PENDING"
    ]
    if presentation is not None:
        projected_decisions = []
        option_labels = {
            "continue": "批准并继续",
            "pause": "暂停任务",
        }
        for item in pending_decisions:
            task = tasks_by_id.get(item["task_id"], {})
            title = task.get("title") or task.get("public_label") or "待确认任务"
            acceptance = task.get("acceptance") or "请确认任务边界后再继续"
            options = [
                {
                    "letter": option.get("letter"),
                    "label": option_labels.get(
                        str(option.get("action") or ""),
                        f"选项 {option.get('letter') or index}",
                    ),
                }
                for index, option in enumerate(item.get("options") or [], start=1)
            ]
            projected_decisions.append(
                {
                    "decision_id": item["decision_id"],
                    "task_id": item["task_id"],
                    "status": item["status"],
                    "question": f"是否继续“{title}”？",
                    "context": acceptance,
                    "options": options,
                    "recommended_option": item.get("recommended_option") or "",
                    "recommendation_reason": "任务已到达人工确认节点。",
                }
            )
        pending_decisions = projected_decisions
    module_work = module_work_projection(snapshot)
    memory_candidates = snapshot.get("memory_candidates") or []
    cognitive_learning = {
        "proposed": sum(item.get("status") == "PROPOSED" for item in memory_candidates),
        "approved": sum(item.get("status") == "APPROVED" for item in memory_candidates),
        "rejected": sum(item.get("status") == "REJECTED" for item in memory_candidates),
        "subjects": len({
            (item.get("subject", {}).get("kind"), item.get("subject", {}).get("id"))
            for item in memory_candidates
        }),
    }
    recovering_workflows = {
        task["workflow_id"]
        for task in snapshot.get("tasks", [])
        if task["status"] == "IN_PROGRESS" and task["task_id"] not in live_task_ids
    }
    recovering_task_ids = {
        run["task_id"]
        for run in snapshot.get("runs", [])
        if run["status"] == "RUNNING" and run["task_id"] not in live_task_ids
    }
    recovering_workflows.update(
        task["workflow_id"]
        for task in snapshot.get("tasks", [])
        if task["task_id"] in recovering_task_ids
    )

    def goal_recovery_required(item: dict[str, Any]) -> bool:
        live_workflow = bool(set(item["workflow_ids"]) & {
            task["workflow_id"]
            for task in snapshot.get("tasks", [])
            if task["task_id"] in live_task_ids
        })
        return (
            bool(item["active_continuation_id"]) and not live_workflow
        ) or item["status"] == "RECOVERY_REQUIRED" or (
            item["usage"].get("last_stop_reason") == "RECOVERY_REQUIRED"
        ) or bool(set(item["workflow_ids"]) & recovering_workflows)

    if presentation is None:
        durable_goals = [
            {
                "goal_id": item["goal_id"],
                "title": item["title"],
                "objective": item["objective"],
                "status": item["status"],
                "workflow_ids": item["workflow_ids"],
                "completion_criteria": item["completion_criteria"],
                "continuation_policy": item["continuation_policy"],
                "usage": item["usage"],
                "recovery_required": goal_recovery_required(item),
            }
            for item in snapshot.get("goals", [])
        ]
    else:
        durable_goals = [
            {
                "goal_id": f"goal-{index:02d}",
                "title": f"长期目标 {index:02d}",
                "status": item["status"],
                "workflow_count": len(item["workflow_ids"]),
                "usage": item["usage"],
                "recovery_required": goal_recovery_required(item),
            }
            for index, item in enumerate(snapshot.get("goals", []), start=1)
        ]
    return {
        "goal": goal,
        "activeBoard": "work",
        "activeLineId": active["line_id"] if active else (workflows[0]["line_id"] if workflows else ""),
        "activeTaskId": active["task_id"] if active else None,
        "planApproved": True,
        "tasks": tasks,
        "businessLines": workflows,
        "taskStates": states,
        "decisions": decisions,
        "pendingDecisions": pending_decisions,
        "assignments": snapshot["assignments"],
        "durableGoals": durable_goals,
        "moduleWork": module_work,
        "cognitiveLearning": cognitive_learning,
        "onboarding": {
            "status": "RUNTIME_READY",
            "readOnly": False,
            "detectedLines": [item["line_id"] for item in workflows],
        },
        "activeTemplate": None,
        "taskProposal": None,
        "runtime": True,
    }


class RuntimeApplication:
    def __init__(
        self,
        *,
        store: RuntimeStore,
        adapters: dict[str, Any],
        default_model: str,
        web_root: str | Path,
        default_adapter_id: str | None = None,
        domain_profiles: dict[str, dict[str, Any]] | None = None,
        runtime_routes: list[dict[str, Any]] | None = None,
        work_protocols: list[dict[str, Any]] | None = None,
        presentation: dict[str, Any] | None = None,
        projection_mode: str | None = None,
        execution_adapter_factories: dict[str, Any] | None = None,
        execution_root: str | Path | None = None,
    ):
        self.store = store
        self.broker = ExecutionBroker(
            store,
            adapters,
            domain_profiles=domain_profiles,
            work_protocols=work_protocols,
        )
        self.default_model = default_model
        if default_adapter_id:
            if default_adapter_id not in adapters:
                raise ValueError("default adapter is not registered")
            self.default_adapter_id = str(default_adapter_id)
        elif len(adapters) == 1:
            self.default_adapter_id = str(next(iter(adapters)))
        else:
            self.default_adapter_id = ""
        self.runtime_routes = [dict(route) for route in runtime_routes or []]
        self.execution_root = Path(execution_root or Path.cwd()).expanduser().resolve()
        self.execution_adapter_factories = dict(execution_adapter_factories or {})
        self.execution_adapter_factories.setdefault(
            "codex-app-server",
            lambda config: CodexAppServerAdapter.auto_configured(
                workspace_root=self.execution_root,
                model=str(config.get("model") or ""),
            ),
        )
        self.execution_adapter_factories.setdefault(
            "codex-project",
            lambda config: (
                CodexProjectAdapter(
                    self.store,
                    project_bindings=config.get("projects") or [],
                ),
                str(config.get("model") or CodexAppServerAdapter._configured_model()),
            ),
        )
        self.credential_source = "server-environment"
        self.projection_mode = projection_mode or (
            "public-safe" if presentation is not None else "private-local"
        )
        if self.projection_mode not in {"private-local", "public-safe"}:
            raise ValueError("projection_mode must be private-local or public-safe")
        if self.projection_mode == "public-safe" and presentation is None:
            raise ValueError("public-safe projection requires a presentation pack")
        if self.projection_mode == "private-local" and presentation is not None:
            raise ValueError("private-local projection cannot use a presentation pack")
        self.presentation = (
            validate_presentation(presentation) if presentation is not None else None
        )
        if self.projection_mode == "private-local":
            self._restore_execution_settings(self.store.load_execution_settings())
        if self.presentation is not None:
            validate_runtime_label(default_model)
            for adapter_id, adapter in adapters.items():
                validate_runtime_label(adapter_id)
                validate_runtime_label(getattr(adapter, "adapter_id", adapter_id))
            for route in self.runtime_routes:
                for field in ("route", "adapter_id", "model"):
                    validate_runtime_label(route.get(field))
                for capability in route.get("capabilities") or []:
                    validate_runtime_label(capability)
            apply_presentation(self.store.snapshot(), self.presentation)
        self.web_root = Path(web_root).expanduser().resolve()

    def _restore_execution_settings(self, settings: dict[str, Any] | None) -> None:
        """Restore safe browser configuration without restoring credentials."""
        if not settings:
            return
        self.runtime_routes = [dict(route) for route in settings.get("routes") or []]
        mode = str(settings.get("mode") or "fixed")
        saved_model = str(settings.get("default_model") or "")
        saved_adapter_id = str(settings.get("default_adapter_id") or "")
        adapter_kind = str(settings.get("adapter_kind") or "")
        if adapter_kind == "codex-project" and settings.get("codex_projects"):
            try:
                adapter = CodexProjectAdapter(
                    self.store,
                    project_bindings=settings.get("codex_projects") or [],
                )
            except (OSError, ValueError):
                self.default_adapter_id = ""
                self.default_model = ""
                self.credential_source = "recovery-required"
                return
            self.broker.adapters[adapter.adapter_id] = adapter
            saved_adapter_id = adapter.adapter_id
            self.credential_source = "codex-session"
        elif adapter_kind == "openai-compatible":
            # The adapter may be recreated from a process environment, but the
            # browser-supplied key itself is intentionally never restored.
            if saved_adapter_id not in self.broker.adapters:
                saved_adapter_id = ""
                self.credential_source = "recovery-required"
            else:
                self.credential_source = "server-environment"
        elif adapter_kind == "codex-app-server":
            factory = self.execution_adapter_factories.get("codex-app-server")
            try:
                if factory is None:
                    raise ValueError("CODEX_APP_SERVER_FACTORY_MISSING")
                adapter, configured_model = factory({"model": saved_model})
                if not adapter.probe().get("available"):
                    raise ValueError("CODEX_APP_SERVER_UNAVAILABLE")
            except (OSError, ValueError):
                self.default_adapter_id = ""
                self.default_model = ""
                self.credential_source = "recovery-required"
                return
            self.broker.adapters[adapter.adapter_id] = adapter
            saved_adapter_id = str(adapter.adapter_id)
            saved_model = str(configured_model or saved_model).strip()
            self.credential_source = "codex-session"
        else:
            saved_adapter_id = ""
            self.credential_source = "recovery-required"
        self.default_adapter_id = saved_adapter_id
        self.default_model = saved_model
        if mode == "automatic":
            self.default_adapter_id = ""
            self.default_model = ""

    def _persist_execution_settings(self, mode: str) -> None:
        """Persist routes and project bindings, never API credentials."""
        active = self.broker.adapters.get(self.default_adapter_id)
        codex_adapters = [
            adapter
            for adapter in self.broker.adapters.values()
            if isinstance(adapter, CodexProjectAdapter)
        ]
        adapter_kind = ""
        codex_projects: list[dict[str, Any]] = []
        if isinstance(active, CodexProjectAdapter):
            adapter_kind = "codex-project"
            codex_projects = [dict(item) for item in active.project_bindings]
        elif isinstance(active, OpenAICompatibleAdapter):
            adapter_kind = "openai-compatible"
        elif str(getattr(active, "adapter_id", "")) == CodexAppServerAdapter.adapter_id:
            adapter_kind = "codex-app-server"
        elif codex_adapters and any(
            str(route.get("adapter_id") or "") == CodexProjectAdapter.adapter_id
            for route in self.runtime_routes
        ):
            adapter_kind = "codex-project"
            codex_projects = [dict(item) for item in codex_adapters[0].project_bindings]
        elif any(
            str(route.get("adapter_id") or "") == CodexAppServerAdapter.adapter_id
            for route in self.runtime_routes
        ) and CodexAppServerAdapter.adapter_id in self.broker.adapters:
            adapter_kind = "codex-app-server"
        self.store.save_execution_settings(
            {
                "mode": mode,
                "default_model": self.default_model,
                "default_adapter_id": self.default_adapter_id,
                "adapter_kind": adapter_kind,
                "routes": self.runtime_routes,
                "codex_projects": codex_projects,
            }
        )

    def projection(self) -> dict[str, Any]:
        snapshot = self.store.snapshot()
        adapter_catalog = self.broker.adapter_catalog()
        brief_snapshot = (
            apply_presentation(snapshot, self.presentation)
            if self.presentation is not None
            else snapshot
        )
        codex_adapters = [
            adapter
            for adapter in self.broker.adapters.values()
            if isinstance(adapter, CodexProjectAdapter)
        ]
        state = runtime_workbench_state(
            self.store,
            self.presentation,
            live_task_ids=self.broker.active_task_ids(),
            codex_dispatches=(
                codex_adapters[0].projection_dispatches()
                if self.projection_mode == "private-local"
                and len(codex_adapters) == 1
                else []
            ),
        )
        if self.projection_mode == "public-safe":
            self._anonymize_execution_state(state, snapshot)
        return {
            "status": self.store.integrity()["status"],
            "data_source": "runtime",
            "state": state,
            "brief": build_secretary_brief(brief_snapshot),
            "adapters": self.public_adapter_catalog(adapter_catalog),
            "default_model": self._public_model(self.default_model),
            "execution": self.execution_readiness(adapter_catalog),
            "execution_settings": self.public_execution_settings(),
        }

    def configure_execution(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.projection_mode != "private-local":
            raise ValueError("execution settings require private-local projection")
        if not isinstance(payload, dict):
            raise ValueError("execution settings must be an object")
        mode = str(payload.get("mode") or "fixed")
        if mode not in {"fixed", "automatic"}:
            raise ValueError("execution mode must be fixed or automatic")

        adapters = dict(self.broker.adapters)
        default_adapter_id = self.default_adapter_id
        default_model = self.default_model
        credential_source = self.credential_source
        adapter_config = payload.get("adapter")
        if adapter_config is not None:
            if not isinstance(adapter_config, dict):
                raise ValueError("adapter settings must be an object")
            kind = str(adapter_config.get("kind") or "")
            if kind == "openai-compatible":
                api_base = str(adapter_config.get("api_base") or "").strip()
                api_key = str(adapter_config.get("api_key") or "").strip()
                model = str(adapter_config.get("model") or "").strip()
                parsed = urlsplit(api_base)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username is not None
                    or parsed.password is not None
                ):
                    raise ValueError("OpenAI-compatible endpoint is invalid")
                if not api_key or not model:
                    raise ValueError("OpenAI-compatible key and model are required")
                adapter = OpenAICompatibleAdapter(api_base=api_base, api_key=api_key)
                adapter_id = adapter.adapter_id
                adapters[adapter_id] = adapter
                default_adapter_id = adapter_id
                default_model = model
                credential_source = "browser-session"
            elif kind in self.execution_adapter_factories:
                adapter, model = self.execution_adapter_factories[kind](adapter_config)
                adapter_id = str(getattr(adapter, "adapter_id", kind))
                if not adapter.probe().get("available"):
                    raise ValueError("execution adapter is unavailable")
                adapters[adapter_id] = adapter
                default_adapter_id = adapter_id
                default_model = str(model or "").strip()
                if not default_model:
                    raise ValueError("execution model is required")
                credential_source = "codex-session"
            else:
                raise ValueError("unsupported execution adapter")

        routes = self.runtime_routes
        if "routes" in payload:
            routes = validate_runtime_routes(
                {
                    "schema_version": RUNTIME_ROUTES_SCHEMA,
                    "routes": payload.get("routes"),
                }
            )
            missing = next(
                (
                    route["adapter_id"]
                    for route in routes
                    if route["adapter_id"] not in adapters
                ),
                None,
            )
            if missing:
                raise ValueError("runtime route adapter is not registered")

        if mode == "fixed":
            if not default_adapter_id or default_adapter_id not in adapters or not default_model:
                raise ValueError("fixed execution settings are incomplete")
        else:
            if not routes:
                raise ValueError("automatic execution requires runtime routes")
            default_adapter_id = ""
            default_model = ""

        self.broker.adapters = adapters
        self.default_adapter_id = default_adapter_id
        self.default_model = default_model
        self.runtime_routes = [dict(route) for route in routes]
        self.credential_source = credential_source
        self._persist_execution_settings(mode)
        return self.projection()

    def public_execution_settings(self) -> dict[str, Any]:
        aliases = self._execution_aliases()
        capability_aliases = self._ordered_aliases(
            [capability for route in self.runtime_routes for capability in (route.get("capabilities") or [])],
            "capability",
        )
        routes = []
        for route in self.runtime_routes:
            route_id = str(route.get("route") or "")
            adapter_id = str(route.get("adapter_id") or "")
            model = str(route.get("model") or "")
            capabilities = [str(item) for item in (route.get("capabilities") or [])]
            if self.projection_mode == "public-safe":
                route_id = aliases["routes"].get(route_id, "route-unknown")
                adapter_id = aliases["adapters"].get(adapter_id, "adapter-unknown")
                model = aliases["models"].get(model, "model-unknown")
                capabilities = [capability_aliases[item] for item in capabilities]
            routes.append(
                {
                    "route": route_id,
                    "adapter_id": adapter_id,
                    "model": model,
                    "capabilities": capabilities,
                    "tier": str(route.get("tier") or ""),
                    "max_context_tokens": route.get("max_context_tokens"),
                    "enabled": bool(route.get("enabled", True)),
                }
            )
        active_adapter = self.broker.adapters.get(self.default_adapter_id)
        codex_projects = (
            [dict(item) for item in active_adapter.project_bindings]
            if self.projection_mode == "private-local"
            and isinstance(active_adapter, CodexProjectAdapter)
            else []
        )
        return {
            "routes": routes,
            "default_adapter_id": (
                aliases["adapters"].get(self.default_adapter_id, "adapter-unknown")
                if self.projection_mode == "public-safe" and self.default_adapter_id
                else self.default_adapter_id
            ),
            "credential_source": self.credential_source,
            "mode": self.execution_readiness()["advance_route_mode"],
            "writable": self.projection_mode == "private-local",
            "codex_projects": codex_projects,
        }

    def codex_project_adapter(self) -> CodexProjectAdapter:
        if self.projection_mode != "private-local":
            raise ValueError("Codex project dispatch requires private-local projection")
        adapters = [
            adapter
            for adapter in self.broker.adapters.values()
            if isinstance(adapter, CodexProjectAdapter)
        ]
        if len(adapters) != 1:
            raise ValueError("Codex project adapter is not configured")
        return adapters[0]

    @staticmethod
    def _ordered_aliases(values: list[Any], prefix: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for value in values:
            text = str(value or "").strip()
            if text and text not in aliases:
                aliases[text] = f"{prefix}-{len(aliases) + 1:02d}"
        return aliases

    def _execution_aliases(
        self, snapshot: dict[str, Any] | None = None
    ) -> dict[str, dict[str, str]]:
        assignments = (snapshot or self.store.snapshot()).get("assignments") or {}
        adapter_values = list(sorted(self.broker.adapters))
        adapter_values.extend(
            assignment.get("executor") for assignment in assignments.values()
        )
        model_values = [self.default_model]
        model_values.extend(route.get("model") for route in self.runtime_routes)
        model_values.extend(
            assignment.get("model") for assignment in assignments.values()
        )
        route_values = [route.get("route") for route in self.runtime_routes]
        route_values.extend(
            assignment.get("route") for assignment in assignments.values()
        )
        return {
            "adapters": self._ordered_aliases(adapter_values, "adapter"),
            "models": self._ordered_aliases(model_values, "model"),
            "routes": self._ordered_aliases(route_values, "route"),
        }

    def _public_model(self, model: Any) -> str:
        value = str(model or "")
        if self.projection_mode != "public-safe" or not value:
            return value
        return self._execution_aliases()["models"][value]

    def _anonymize_execution_state(
        self, state: dict[str, Any], snapshot: dict[str, Any]
    ) -> None:
        aliases = self._execution_aliases(snapshot)
        runtime_aliases = identifier_aliases(snapshot)

        def runtime_alias(kind: str, value: Any, fallback: str) -> str:
            text = str(value or "")
            mapping = runtime_aliases[kind]
            if text in mapping:
                return mapping[text]
            if text in mapping.values():
                return text
            return fallback

        for assignment in (state.get("assignments") or {}).values():
            executor = str(assignment.get("executor") or "")
            model = str(assignment.get("model") or "")
            route = str(assignment.get("route") or "")
            if executor:
                assignment["executor"] = aliases["adapters"].get(
                    executor, "adapter-unknown"
                )
            if model:
                assignment["model"] = aliases["models"].get(model, "model-unknown")
            if route:
                assignment["route"] = aliases["routes"].get(
                    route, aliases["adapters"].get(route, "route-unknown")
                )
        for task in state.get("tasks") or []:
            acceptance = task.get("acceptance_snapshot") or {}
            execution = acceptance.get("execution") or {}
            executor = str(execution.get("executor") or "")
            model = str(execution.get("model_id") or "")
            run_id = str(execution.get("run_id") or "")
            if executor:
                execution["executor"] = aliases["adapters"].get(
                    executor, "adapter-unknown"
                )
            if execution.get("adapter"):
                execution["adapter"] = aliases["adapters"].get(
                    str(execution["adapter"]), "adapter-unknown"
                )
            if model:
                execution["model_id"] = aliases["models"].get(model, "model-unknown")
            if run_id:
                execution["run_id"] = runtime_alias("runs", run_id, "run-unknown")
            # A public projection exposes that an execution occurred, but not
            # the Codex thread, turn, adapter internals, or result text.
            execution["thread_id"] = None
            execution["turn_id"] = None
            for item in acceptance.get("timeline") or []:
                if item.get("run_id"):
                    item["run_id"] = runtime_alias("runs", item["run_id"], "run-unknown")
                if item.get("artifact_ref"):
                    item["artifact_ref"] = runtime_alias(
                        "artifacts", item["artifact_ref"], "artifact-unknown"
                    )
                item.pop("summary", None)
            for item in acceptance.get("stage_artifacts") or []:
                if item.get("artifact_ref"):
                    item["artifact_ref"] = runtime_alias(
                        "artifacts", item["artifact_ref"], "artifact-unknown"
                    )
                item["summary"] = "阶段产物已登记"
                item.pop("source", None)
            review = acceptance.get("review") or {}
            review["summary"] = ""
            review["next_action"] = ""
            review["at"] = ""
            review["evidence"] = [
                runtime_alias("artifacts", value, "artifact-unknown")
                for value in review.get("evidence") or []
            ]

    def resolve_adapter_id(self, public_id: Any) -> str:
        value = str(public_id or "")
        if self.projection_mode != "public-safe":
            return value
        reverse = {
            alias: raw for raw, alias in self._execution_aliases()["adapters"].items()
        }
        if value not in reverse:
            raise ValueError("unknown public adapter")
        return reverse[value]

    def fixed_execution_binding(
        self, *, requested_adapter: Any = None, requested_model: Any = None
    ) -> tuple[str, str]:
        if not self.default_adapter_id or not self.default_model:
            raise ValueError("fixed execution settings are incomplete")
        if requested_adapter:
            adapter_id = self.resolve_adapter_id(requested_adapter)
            if adapter_id != self.default_adapter_id:
                raise ValueError("client cannot override the configured adapter")
        if requested_model:
            model = self.resolve_model(requested_model)
            if model != self.default_model:
                raise ValueError("client cannot override the configured model")
        return self.default_adapter_id, self.default_model

    def resolve_model(self, public_model: Any) -> str:
        value = str(public_model or "")
        if self.projection_mode != "public-safe":
            return value
        reverse = {
            alias: raw for raw, alias in self._execution_aliases()["models"].items()
        }
        if value not in reverse:
            raise ValueError("unknown public model")
        return reverse[value]

    def public_adapter_catalog(
        self, catalog: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        catalog = catalog if catalog is not None else self.broker.adapter_catalog()
        aliases = self._execution_aliases()["adapters"]
        projected = []
        for adapter_key, item in zip(sorted(self.broker.adapters), catalog):
            adapter_id = str(adapter_key)
            protocol = str(item.get("protocol") or "")
            if self.projection_mode == "public-safe":
                adapter_id = aliases[adapter_id]
                protocol = ""
            entry = {
                "adapter_id": adapter_id,
                "available": bool(item.get("available")),
            }
            if protocol:
                entry["protocol"] = protocol
            projected.append(entry)
        return projected

    def execution_readiness(
        self, catalog: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        catalog = catalog if catalog is not None else self.broker.adapter_catalog()
        available_adapters = {
            adapter_id
            for adapter_id, item in zip(sorted(self.broker.adapters), catalog)
            if item.get("available")
        }
        route_mode = (
            "automatic" if self.runtime_routes and not self.default_model else "fixed"
        )
        if route_mode == "automatic":
            advance_ready = any(
                route.get("enabled", True)
                and str(route.get("adapter_id") or "") in available_adapters
                for route in self.runtime_routes
            )
        else:
            advance_ready = bool(
                self.default_model
                and self.default_adapter_id
                and self.default_adapter_id in available_adapters
            )
        return {
            "task_dispatch_ready": advance_ready,
            "advance_route_mode": route_mode,
            "advance_ready": advance_ready,
        }

    def _resolve_identifier(self, kind: str, public_id: Any) -> str:
        value = str(public_id or "")
        if self.presentation is None:
            return value
        reverse = {
            alias: raw
            for raw, alias in identifier_aliases(self.store.snapshot())[kind].items()
        }
        return reverse.get(value, value)

    def resolve_task_id(self, public_id: Any) -> str:
        return self._resolve_identifier("tasks", public_id)

    def resolve_workflow_id(self, public_id: Any) -> str:
        return self._resolve_identifier("workflows", public_id)

    def resolve_decision_id(self, public_id: Any) -> str:
        return self._resolve_identifier("decisions", public_id)

    def resolve_task_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.presentation is None:
            return dict(payload)
        resolved = dict(payload)
        for field in ("workflow_id", "line_id"):
            if resolved.get(field):
                resolved[field] = self.resolve_workflow_id(resolved[field])
        if "depends_on" in resolved:
            resolved["depends_on"] = [
                self.resolve_task_id(item) for item in resolved.get("depends_on") or []
            ]
        return resolved

    def public_result(self, result: dict[str, Any]) -> dict[str, Any]:
        if self.presentation is None:
            return result
        allowed = (
            "ok",
            "status",
            "reason",
            "advanced_count",
            "failure_count",
            "stop_reason",
            "goal_id",
            "steps_used",
            "tokens_used",
            "failure_count",
        )
        projected = {key: result[key] for key in allowed if key in result}
        for key in ("reason", "stop_reason"):
            if key in projected and not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(projected[key])):
                projected[key] = "REQUEST_REJECTED"
        return projected

    def error_payload(
        self, *, status: str, safe_reason: str, detail: Any
    ) -> dict[str, Any]:
        return {"status": status, "reason": safe_reason}


class RuntimeHTTPServer(ThreadingHTTPServer):
    app: RuntimeApplication


class RuntimeRequestHandler(BaseHTTPRequestHandler):
    server: RuntimeHTTPServer

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            value = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _accept_post(self) -> bool:
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"status": "BLOCKED", "reason": "APPLICATION_JSON_REQUIRED"})
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        origin_port = parsed.port or (80 if parsed.scheme == "http" else 443)
        server_port = int(self.server.server_address[1])
        if (
            parsed.scheme != "http"
            or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}
            or origin_port != server_port
        ):
            self._json(403, {"status": "BLOCKED", "reason": "LOCAL_ORIGIN_REQUIRED"})
            return False
        return True

    def do_GET(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if path == "/api/runtime":
            try:
                projection = self.server.app.projection()
            except ValueError as exc:
                self._json(
                    422,
                    self.server.app.error_payload(
                        status="BLOCKED",
                        safe_reason="PRESENTATION_INVALID",
                        detail=exc,
                    ),
                )
                return
            self._json(200, projection)
            return
        if path == "/api/codex-project/dispatches":
            try:
                dispatches = self.server.app.codex_project_adapter().active_dispatches()
            except ValueError as exc:
                self._json(
                    422,
                    self.server.app.error_payload(
                        status="BLOCKED",
                        safe_reason="REQUEST_REJECTED",
                        detail=exc,
                    ),
                )
                return
            self._json(200, {"status": "READY", "dispatches": dispatches})
            return
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (self.server.app.web_root / relative).resolve()
        if not target.is_relative_to(self.server.app.web_root) or not target.is_file():
            self._json(404, {"status": "UNKNOWN", "reason": "NOT_FOUND"})
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if not self._accept_post():
            return
        try:
            payload = self._read_json()
            if path == "/api/tasks":
                result = self.server.app.store.create_task(
                    self.server.app.resolve_task_payload(payload)
                )
            elif path == "/api/workflows":
                result = self.server.app.store.create_workflow(payload)
            elif path == "/api/runs":
                task_id = self.server.app.resolve_task_id(payload.get("task_id"))
                if self.server.app.runtime_routes and not self.server.app.default_model:
                    result = self.server.app.broker.dispatch_routed(
                        task_id,
                        routes=self.server.app.runtime_routes,
                    )
                else:
                    adapter_id, model = self.server.app.fixed_execution_binding(
                        requested_adapter=payload.get("adapter_id"),
                        requested_model=payload.get("model"),
                    )
                    result = self.server.app.broker.dispatch(
                        task_id,
                        adapter_id=adapter_id,
                        model=model,
                    )
                if not result.get("ok"):
                    self._json(422, self.server.app.public_result(result))
                    return
            elif path == "/api/advance":
                default_route_mode = (
                    "automatic"
                    if self.server.app.runtime_routes and not self.server.app.default_model
                    else "fixed"
                )
                route_mode = str(payload.get("route_mode") or default_route_mode)
                if route_mode not in {"fixed", "automatic"}:
                    raise ValueError("route_mode must be fixed or automatic")
                if route_mode == "automatic" and not self.server.app.runtime_routes:
                    raise ValueError("runtime routes are not configured")
                if self.server.app.presentation is not None and route_mode == "fixed":
                    validate_runtime_label(payload.get("adapter_id"))
                    validate_runtime_label(
                        payload.get("model") or self.server.app.default_model
                    )
                fixed_binding = (
                    self.server.app.fixed_execution_binding(
                        requested_adapter=payload.get("adapter_id"),
                        requested_model=payload.get("model"),
                    )
                    if route_mode == "fixed"
                    else None
                )
                engine = (
                    AutoAdvanceEngine(
                        self.server.app.broker,
                        routes=self.server.app.runtime_routes,
                        requested_route=str(payload.get("requested_route") or "") or None,
                    )
                    if route_mode == "automatic"
                    else AutoAdvanceEngine(
                        self.server.app.broker,
                        adapter_id=fixed_binding[0],
                        model=fixed_binding[1],
                    )
                )
                result = engine.advance(
                    max_steps=payload.get("max_steps", 25),
                    failure_budget=payload.get("failure_budget", 1),
                    workflow_id=(
                        self.server.app.resolve_workflow_id(payload.get("workflow_id"))
                        if payload.get("workflow_id")
                        else None
                    ),
                )
                if not result.get("ok"):
                    self._json(422, self.server.app.public_result(result))
                    return
            elif path == "/api/settings/execution":
                result = self.server.app.configure_execution(payload)
            elif path == "/api/codex-project/claim":
                result = self.server.app.codex_project_adapter().claim_next(
                    worker_id=str(payload.get("worker_id") or "")
                )
                if result is None:
                    result = {"status": "IDLE", "reason": "NO_PENDING_DISPATCH"}
            elif path.startswith("/api/codex-project/dispatches/") and path.endswith("/bind"):
                dispatch_id = path[
                    len("/api/codex-project/dispatches/") : -len("/bind")
                ].strip("/")
                result = self.server.app.codex_project_adapter().bind_thread(
                    dispatch_id,
                    thread_id=str(payload.get("thread_id") or ""),
                    project_id=str(payload.get("project_id") or ""),
                    host_id=str(payload.get("host_id") or ""),
                    verification=payload.get("verification"),
                )
            elif path.startswith("/api/codex-project/dispatches/") and path.endswith("/complete"):
                dispatch_id = path[
                    len("/api/codex-project/dispatches/") : -len("/complete")
                ].strip("/")
                usage = payload.get("usage") or {}
                if not isinstance(usage, dict):
                    raise ValueError("usage must be an object")
                result = self.server.app.codex_project_adapter().complete(
                    dispatch_id,
                    output_text=str(payload.get("output_text") or ""),
                    usage=usage,
                    completion_receipt=payload.get("completion_receipt"),
                )
            elif path.startswith("/api/goals/") and path.endswith("/continue"):
                if self.server.app.presentation is not None:
                    raise ValueError("goal control requires private-local projection")
                goal_id = path[len("/api/goals/") : -len("/continue")].strip("/")
                default_route_mode = (
                    "automatic"
                    if self.server.app.runtime_routes and not self.server.app.default_model
                    else "fixed"
                )
                route_mode = str(payload.get("route_mode") or default_route_mode)
                if route_mode not in {"fixed", "automatic"}:
                    raise ValueError("route_mode must be fixed or automatic")
                fixed_binding = (
                    self.server.app.fixed_execution_binding(
                        requested_adapter=payload.get("adapter_id"),
                        requested_model=payload.get("model"),
                    )
                    if route_mode == "fixed"
                    else None
                )
                controller = (
                    GoalController(
                        self.server.app.broker,
                        routes=self.server.app.runtime_routes,
                        requested_route=str(payload.get("requested_route") or "") or None,
                    )
                    if route_mode == "automatic"
                    else GoalController(
                        self.server.app.broker,
                        adapter_id=fixed_binding[0],
                        model=fixed_binding[1],
                    )
                )
                result = controller.continue_goal(goal_id)
                if not result.get("ok"):
                    self._json(422, self.server.app.public_result(result))
                    return
            elif path.startswith("/api/goals/") and path.endswith("/complete"):
                if self.server.app.presentation is not None:
                    raise ValueError("goal control requires private-local projection")
                goal_id = path[len("/api/goals/") : -len("/complete")].strip("/")
                result = self.server.app.store.complete_goal(
                    goal_id,
                    by=str(payload.get("by") or "owner"),
                    evidence=str(payload.get("evidence") or ""),
                )
            elif path.startswith("/api/tasks/") and path.endswith("/transition"):
                task_id = path[len("/api/tasks/") : -len("/transition")].strip("/")
                result = self.server.app.store.transition(
                    self.server.app.resolve_task_id(task_id),
                    str(payload.get("to") or ""),
                    by=str(payload.get("by") or "owner"),
                    reason=str(payload.get("reason") or ""),
                    skip_review=bool(payload.get("skip_review", False)),
                )
                if not result.get("ok"):
                    self._json(422, self.server.app.public_result(result))
                    return
            elif path.startswith("/api/decisions/") and path.endswith("/resolve"):
                decision_id = path[len("/api/decisions/") : -len("/resolve")].strip("/")
                result = self.server.app.store.resolve_decision(
                    self.server.app.resolve_decision_id(decision_id),
                    selected_option=str(payload.get("selected_option") or ""),
                    by=str(payload.get("by") or "owner"),
                )
            else:
                self._json(404, {"status": "UNKNOWN", "reason": "NOT_FOUND"})
                return
        except KeyError as exc:
            self._json(
                404,
                self.server.app.error_payload(
                    status="UNKNOWN", safe_reason="NOT_FOUND", detail=exc
                ),
            )
            return
        except (ValueError, RuntimeError) as exc:
            self._json(
                422,
                self.server.app.error_payload(
                    status="BLOCKED", safe_reason="REQUEST_REJECTED", detail=exc
                ),
            )
            return
        except sqlite3.IntegrityError as exc:
            self._json(
                409,
                self.server.app.error_payload(
                    status="BLOCKED", safe_reason="CONFLICT", detail=exc
                ),
            )
            return
        self._json(200, self.server.app.public_result(result))

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def create_runtime_server(
    address: tuple[str, int],
    *,
    store: RuntimeStore,
    adapters: dict[str, Any],
    default_model: str,
    web_root: str | Path,
    default_adapter_id: str | None = None,
    domain_profiles: dict[str, dict[str, Any]] | None = None,
    runtime_routes: list[dict[str, Any]] | None = None,
    work_protocols: list[dict[str, Any]] | None = None,
    presentation: dict[str, Any] | None = None,
    projection_mode: str | None = None,
    execution_adapter_factories: dict[str, Any] | None = None,
    execution_root: str | Path | None = None,
) -> RuntimeHTTPServer:
    resolved_mode = projection_mode or (
        "public-safe" if presentation is not None else "private-local"
    )
    if resolved_mode == "private-local" and address[0].lower() not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("private-local runtime server binds to loopback only")
    application = RuntimeApplication(
        store=store,
        adapters=adapters,
        default_model=default_model,
        web_root=web_root,
        default_adapter_id=default_adapter_id,
        domain_profiles=domain_profiles,
        runtime_routes=runtime_routes,
        work_protocols=work_protocols,
        presentation=presentation,
        projection_mode=resolved_mode,
        execution_adapter_factories=execution_adapter_factories,
        execution_root=execution_root,
    )
    server = RuntimeHTTPServer(address, RuntimeRequestHandler)
    server.app = application
    return server
