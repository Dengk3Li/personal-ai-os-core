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
from .secretary import build_secretary_brief
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
        domain_profiles: dict[str, dict[str, Any]] | None = None,
        runtime_routes: list[dict[str, Any]] | None = None,
        presentation: dict[str, Any] | None = None,
    ):
        self.store = store
        self.broker = ExecutionBroker(store, adapters, domain_profiles=domain_profiles)
        self.default_model = default_model
        self.runtime_routes = [dict(route) for route in runtime_routes or []]
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
        brief_snapshot = (
            apply_presentation(snapshot, self.presentation)
            if self.presentation is not None
            else snapshot
        )
        return {
            "status": self.store.integrity()["status"],
            "data_source": "runtime",
            "state": runtime_workbench_state(self.store, self.presentation),
            "brief": build_secretary_brief(brief_snapshot),
            "adapters": self.public_adapter_catalog(),
            "default_model": self.default_model,
        }

    def public_adapter_catalog(self) -> list[dict[str, Any]]:
        catalog = self.broker.adapter_catalog()
        if self.presentation is None:
            return catalog
        projected = []
        for adapter_key, item in zip(sorted(self.broker.adapters), catalog):
            adapter_id = validate_runtime_label(adapter_key)
            protocol = validate_runtime_label(item.get("protocol"))
            entry = {
                "adapter_id": adapter_id,
                "available": bool(item.get("available")),
            }
            if protocol:
                entry["protocol"] = protocol
            projected.append(entry)
        return projected

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
        )
        projected = {key: result[key] for key in allowed if key in result}
        for key in ("reason", "stop_reason"):
            if key in projected and not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(projected[key])):
                projected[key] = "REQUEST_REJECTED"
        return projected

    def error_payload(
        self, *, status: str, safe_reason: str, detail: Any
    ) -> dict[str, Any]:
        if self.presentation is not None:
            return {"status": status, "reason": safe_reason}
        return {"status": status, "reason": str(detail)}


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
                if self.server.app.presentation is not None:
                    validate_runtime_label(payload.get("adapter_id"))
                    validate_runtime_label(
                        payload.get("model") or self.server.app.default_model
                    )
                result = self.server.app.broker.dispatch(
                    self.server.app.resolve_task_id(payload.get("task_id")),
                    adapter_id=str(payload.get("adapter_id") or ""),
                    model=str(payload.get("model") or self.server.app.default_model),
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
                engine = (
                    AutoAdvanceEngine(
                        self.server.app.broker,
                        routes=self.server.app.runtime_routes,
                        requested_route=str(payload.get("requested_route") or "") or None,
                    )
                    if route_mode == "automatic"
                    else AutoAdvanceEngine(
                        self.server.app.broker,
                        adapter_id=str(payload.get("adapter_id") or ""),
                        model=str(payload.get("model") or self.server.app.default_model),
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
    domain_profiles: dict[str, dict[str, Any]] | None = None,
    runtime_routes: list[dict[str, Any]] | None = None,
    presentation: dict[str, Any] | None = None,
) -> RuntimeHTTPServer:
    application = RuntimeApplication(
        store=store,
        adapters=adapters,
        default_model=default_model,
        web_root=web_root,
        domain_profiles=domain_profiles,
        runtime_routes=runtime_routes,
        presentation=presentation,
    )
    server = RuntimeHTTPServer(address, RuntimeRequestHandler)
    server.app = application
    return server
