from __future__ import annotations

import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .runtime import ExecutionBroker, RuntimeStore
from .secretary import build_secretary_brief


def runtime_workbench_state(store: RuntimeStore) -> dict[str, Any]:
    snapshot = store.snapshot()
    events_by_task: dict[str, list[dict[str, Any]]] = {}
    labels = {
        "RUN_ASSIGNED": "Executor assigned",
        "ADAPTER_STARTED": "Adapter started",
        "ARTIFACT_CREATED": "Artifact registered",
        "RUN_SUCCEEDED": "Run completed",
        "REVIEW_REQUESTED": "Result awaiting review",
        "BLOCKED": "Run needs a decision",
        "DECISION_REQUESTED": "Decision requested",
        "DECISION_RECORDED": "Decision recorded",
    }
    for event in snapshot["events"]:
        events_by_task.setdefault(event["task_id"], []).append(
            {
                "event_id": str(event["event_id"]),
                "kind": event["event_type"].lower(),
                "label": labels.get(event["event_type"], event["event_type"].replace("_", " ").title()),
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
    )
    tasks = [
        {
            **{field: task[field] for field in browser_task_fields},
            "events": events_by_task.get(task["task_id"], []),
        }
        for task in snapshot["tasks"]
    ]
    states = {task["task_id"]: task["status"] for task in tasks}
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
    goal = snapshot["workflows"][0]["goal"] if snapshot["workflows"] else "No workflow installed"
    decisions = {
        item["task_id"]: item["selected_option"] or item["status"]
        for item in snapshot["decisions"]
    }
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
        "pendingDecisions": [item for item in snapshot["decisions"] if item["status"] == "PENDING"],
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
    ):
        self.store = store
        self.broker = ExecutionBroker(store, adapters, domain_profiles=domain_profiles)
        self.default_model = default_model
        self.web_root = Path(web_root).expanduser().resolve()

    def projection(self) -> dict[str, Any]:
        snapshot = self.store.snapshot()
        return {
            "status": self.store.integrity()["status"],
            "data_source": "runtime",
            "state": runtime_workbench_state(self.store),
            "brief": build_secretary_brief(snapshot),
            "adapters": self.broker.adapter_catalog(),
            "default_model": self.default_model,
        }


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
            self._json(200, self.server.app.projection())
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
                result = self.server.app.store.create_task(payload)
            elif path == "/api/workflows":
                result = self.server.app.store.create_workflow(payload)
            elif path == "/api/runs":
                result = self.server.app.broker.dispatch(
                    str(payload.get("task_id") or ""),
                    adapter_id=str(payload.get("adapter_id") or ""),
                    model=str(payload.get("model") or self.server.app.default_model),
                )
                if not result.get("ok"):
                    self._json(422, result)
                    return
            elif path.startswith("/api/tasks/") and path.endswith("/transition"):
                task_id = path[len("/api/tasks/") : -len("/transition")].strip("/")
                result = self.server.app.store.transition(
                    task_id,
                    str(payload.get("to") or ""),
                    by=str(payload.get("by") or "owner"),
                    reason=str(payload.get("reason") or ""),
                    skip_review=bool(payload.get("skip_review", False)),
                )
                if not result.get("ok"):
                    self._json(422, result)
                    return
            elif path.startswith("/api/decisions/") and path.endswith("/resolve"):
                decision_id = path[len("/api/decisions/") : -len("/resolve")].strip("/")
                result = self.server.app.store.resolve_decision(
                    decision_id,
                    selected_option=str(payload.get("selected_option") or ""),
                    by=str(payload.get("by") or "owner"),
                )
            else:
                self._json(404, {"status": "UNKNOWN", "reason": "NOT_FOUND"})
                return
        except KeyError as exc:
            self._json(404, {"status": "UNKNOWN", "reason": str(exc)})
            return
        except (ValueError, RuntimeError) as exc:
            self._json(422, {"status": "BLOCKED", "reason": str(exc)})
            return
        except sqlite3.IntegrityError as exc:
            self._json(409, {"status": "BLOCKED", "reason": str(exc)})
            return
        self._json(200, result)

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
) -> RuntimeHTTPServer:
    server = RuntimeHTTPServer(address, RuntimeRequestHandler)
    server.app = RuntimeApplication(
        store=store,
        adapters=adapters,
        default_model=default_model,
        web_root=web_root,
        domain_profiles=domain_profiles,
    )
    return server
