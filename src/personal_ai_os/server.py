from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .runtime import ExecutionBroker, RuntimeStore
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
    store: RuntimeStore, presentation: dict[str, Any] | None = None
) -> dict[str, Any]:
    snapshot = apply_presentation(store.snapshot(), presentation)
    events_by_task: dict[str, list[dict[str, Any]]] = {}
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
        events_by_task.setdefault(event["task_id"], []).append(
            {
                "event_id": str(event["event_id"]),
                "kind": event["event_type"].lower(),
                "label": labels.get(event["event_type"], "运行状态已更新"),
                "at": event["at"][11:16] if len(event["at"]) >= 16 else event["at"],
            }
        )
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
    )
    tasks = [
        {
            **{field: task.get(field) for field in browser_task_fields},
            "events": events_by_task.get(task["task_id"], []),
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
        if task["status"] == "IN_PROGRESS"
    }
    recovering_task_ids = {
        run["task_id"]
        for run in snapshot.get("runs", [])
        if run["status"] == "RUNNING"
    }
    recovering_workflows.update(
        task["workflow_id"]
        for task in snapshot.get("tasks", [])
        if task["task_id"] in recovering_task_ids
    )

    def goal_recovery_required(item: dict[str, Any]) -> bool:
        return bool(item["active_continuation_id"]) or item["status"] == "RECOVERY_REQUIRED" or (
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

    def projection(self) -> dict[str, Any]:
        snapshot = self.store.snapshot()
        adapter_catalog = self.broker.adapter_catalog()
        brief_snapshot = (
            apply_presentation(snapshot, self.presentation)
            if self.presentation is not None
            else snapshot
        )
        state = runtime_workbench_state(self.store, self.presentation)
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
                    "enabled": bool(route.get("enabled", True)),
                }
            )
        return {
            "routes": routes,
            "default_adapter_id": (
                aliases["adapters"].get(self.default_adapter_id, "adapter-unknown")
                if self.projection_mode == "public-safe" and self.default_adapter_id
                else self.default_adapter_id
            ),
            "credential_source": "server-environment",
        }

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
    )
    server = RuntimeHTTPServer(address, RuntimeRequestHandler)
    server.app = application
    return server
