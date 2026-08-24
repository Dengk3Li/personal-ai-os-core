from __future__ import annotations

import datetime
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .presets import get_workflow_preset
from .secretary import build_context_pack, model_context_for_task
from .states import TASK_STATES
from .workflow import transition_task


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _stable_error_code(value: Any, default: str) -> str:
    candidate = str(value or "").strip()
    if (
        candidate
        and len(candidate) <= 64
        and all(character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in candidate)
    ):
        return candidate
    return default


class RuntimeStore:
    """SQLite authority for tasks, runs, events, artifacts, and decisions."""

    def __init__(self, database: str | Path):
        self.database = Path(database).expanduser().resolve()
        self._task_locks: dict[str, threading.RLock] = {}
        self._task_locks_guard = threading.Lock()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def task_lock(self, task_id: str) -> threading.RLock:
        with self._task_locks_guard:
            return self._task_locks.setdefault(task_id, threading.RLock())

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    layout TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
                    line_id TEXT NOT NULL,
                    public_label TEXT NOT NULL,
                    title TEXT NOT NULL,
                    acceptance TEXT NOT NULL,
                    agent_role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resume_to TEXT,
                    depends_on TEXT NOT NULL,
                    human_gate INTEGER NOT NULL,
                    iteration INTEGER NOT NULL,
                    parallel_group TEXT NOT NULL,
                    required_capabilities TEXT NOT NULL,
                    complexity TEXT NOT NULL,
                    domain_id TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    requires_git_closure INTEGER NOT NULL,
                    git_closure TEXT NOT NULL,
                    result_ref TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    external_run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    adapter_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    usage_json TEXT NOT NULL,
                    error TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    run_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    status TEXT NOT NULL,
                    question TEXT NOT NULL,
                    context TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    recommended_option TEXT NOT NULL,
                    recommendation_reason TEXT NOT NULL,
                    selected_option TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id, attempt);
                CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status, created_at);
                """
            )

    def create_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            workflow_id = self._insert_workflow(connection, workflow)
        return self.get_workflow(workflow_id)

    def _insert_workflow(
        self,
        connection: sqlite3.Connection,
        workflow: dict[str, Any],
    ) -> str:
        workflow_id = str(workflow.get("workflow_id") or "").strip()
        if not workflow_id:
            raise ValueError("workflow_id is required")
        now = _now()
        connection.execute(
            "INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?)",
            (
                workflow_id,
                str(workflow.get("name") or workflow_id),
                str(workflow.get("caption") or ""),
                str(workflow.get("layout") or "custom"),
                str(workflow.get("goal") or ""),
                now,
            ),
        )
        return workflow_id

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"workflow not found: {workflow_id}")
        return dict(row)

    def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            task_id = self._insert_task(connection, task)
        return self.get_task(task_id)

    def _insert_task(
        self,
        connection: sqlite3.Connection,
        task: dict[str, Any],
    ) -> str:
        task_id = str(task.get("task_id") or "").strip()
        workflow_id = str(task.get("workflow_id") or task.get("line_id") or "").strip()
        title = str(task.get("title") or "").strip()
        acceptance = str(task.get("acceptance") or "").strip()
        status = str(task.get("status") or "QUEUED").upper()
        if not task_id or not workflow_id or not title or not acceptance:
            raise ValueError("task_id, workflow_id, title, and acceptance are required")
        if status not in TASK_STATES:
            raise ValueError(f"unknown task status: {status}")
        if status != "QUEUED":
            raise ValueError("new tasks must start in QUEUED")
        context = task.get("context") or {}
        if not isinstance(context, dict):
            raise ValueError("task context must be an object")
        model_context_for_task({"context": context})
        if connection.execute(
            "SELECT 1 FROM workflows WHERE workflow_id = ?", (workflow_id,)
        ).fetchone() is None:
            raise KeyError(f"workflow not found: {workflow_id}")
        dependencies = [str(item).strip() for item in task.get("depends_on") or []]
        if any(not item for item in dependencies):
            raise ValueError("task dependencies cannot be empty")
        if task_id in dependencies:
            raise ValueError("task cannot depend on itself")
        for dependency_id in dependencies:
            dependency = connection.execute(
                "SELECT workflow_id FROM tasks WHERE task_id = ?", (dependency_id,)
            ).fetchone()
            if dependency is None:
                raise ValueError(f"dependency not found: {dependency_id}")
            if dependency["workflow_id"] != workflow_id:
                raise ValueError(
                    f"dependency must belong to the same workflow: {dependency_id}"
                )
        now = _now()
        values = (
            task_id,
            workflow_id,
            str(task.get("line_id") or workflow_id),
            str(task.get("public_label") or task_id),
            title,
            acceptance,
            str(task.get("agent_role") or "General Agent"),
            status,
            task.get("resume_to"),
            _json(dependencies),
            int(bool(task.get("human_gate", False))),
            int(task.get("iteration") or 1),
            str(task.get("parallel_group") or "main"),
            _json(list(task.get("required_capabilities") or [])),
            str(task.get("complexity") or "standard"),
            str(task.get("domain_id") or workflow_id),
            _json(dict(context)),
            int(bool(task.get("requires_git_closure", False))),
            _json({}),
            None,
            now,
            now,
        )
        connection.execute(
            """
            INSERT INTO tasks (
                task_id, workflow_id, line_id, public_label, title, acceptance,
                agent_role, status, resume_to, depends_on, human_gate, iteration,
                parallel_group, required_capabilities, complexity, domain_id,
                context_json, requires_git_closure, git_closure, result_ref,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return task_id

    @staticmethod
    def _decode_task(row: sqlite3.Row, *, attempts: int = 0, artifacts: list[str] | None = None) -> dict[str, Any]:
        task = dict(row)
        for key in ("depends_on", "required_capabilities", "context_json", "git_closure"):
            task[key] = json.loads(task[key])
        task["context"] = task.pop("context_json")
        task["human_gate"] = bool(task["human_gate"])
        task["requires_git_closure"] = bool(task["requires_git_closure"])
        task["attempts"] = attempts
        task["artifact_refs"] = artifacts or []
        return task

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(f"task not found: {task_id}")
            attempts = connection.execute(
                "SELECT COUNT(*) FROM runs WHERE task_id = ?", (task_id,)
            ).fetchone()[0]
            artifacts = [item[0] for item in connection.execute(
                "SELECT artifact_id FROM artifacts WHERE task_id = ? ORDER BY created_at", (task_id,)
            )]
        return self._decode_task(row, attempts=attempts, artifacts=artifacts)

    def _record_event(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        run_id: str | None = None,
        at: str | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO events (task_id, run_id, event_type, payload_json, at) VALUES (?, ?, ?, ?, ?)",
            (task_id, run_id, event_type, _json(payload or {}), at or _now()),
        )

    def record_task_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
    ) -> None:
        """Append a bounded runtime event without changing task state."""
        self.get_task(task_id)
        if not event_type or len(event_type) > 64:
            raise ValueError("event_type is required and must be at most 64 characters")
        with self._connect() as connection:
            self._record_event(
                connection,
                task_id=task_id,
                event_type=event_type,
                payload=payload,
                run_id=run_id,
            )

    def transition(
        self,
        task_id: str,
        to: str,
        *,
        by: str,
        reason: str = "",
        skip_review: bool = False,
        run_id: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        lock = self.task_lock(task_id)
        if not lock.acquire(blocking=False):
            return {
                "ok": False,
                "from": None,
                "to": to,
                "reason": "TASK_ALREADY_DISPATCHING",
            }
        try:
            return self._transition(
                task_id,
                to,
                by=by,
                reason=reason,
                skip_review=skip_review,
                run_id=run_id,
                event_type=event_type,
            )
        finally:
            lock.release()

    def _transition(
        self,
        task_id: str,
        to: str,
        *,
        by: str,
        reason: str = "",
        skip_review: bool = False,
        run_id: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        result = transition_task(
            task,
            to,
            by=by,
            reason=reason,
            skip_review=skip_review,
        )
        if not result["ok"]:
            return result
        event = result["event"]
        resume_to = event.get("resume_to") if to in {"BLOCKED", "PAUSED"} else None
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE tasks SET status = ?, resume_to = ?, updated_at = ?
                    WHERE task_id = ? AND status = ?""",
                (to, resume_to, event["at"], task_id, task["status"]),
            )
            if cursor.rowcount != 1:
                return {
                    "ok": False,
                    "from": task["status"],
                    "to": to,
                    "reason": "STATE_CHANGED_RETRY",
                }
            self._record_event(
                connection,
                task_id=task_id,
                run_id=run_id,
                event_type=event_type or event["event"],
                payload={"from": event["from"], "to": event["to"], "by": by, "reason": reason},
                at=event["at"],
            )
        return result

    def create_run(
        self,
        *,
        task_id: str,
        external_run_id: str,
        adapter_id: str,
        model: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            attempt = connection.execute(
                "SELECT COUNT(*) + 1 FROM runs WHERE task_id = ?", (task_id,)
            ).fetchone()[0]
            run_id = _identifier("run")
            now = _now()
            connection.execute(
                """INSERT INTO runs (
                    run_id, external_run_id, task_id, adapter_id, model, status,
                    attempt, usage_json, error, started_at, ended_at
                ) VALUES (?, ?, ?, ?, ?, 'RUNNING', ?, '{}', '', ?, NULL)""",
                (run_id, external_run_id, task_id, adapter_id, model, attempt, now),
            )
        return self.get_run(run_id)

    def claim_run(
        self,
        *,
        task_id: str,
        adapter_id: str,
        model: str,
        by: str,
    ) -> dict[str, Any]:
        """Atomically claim a queued task and create its local run."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"task not found: {task_id}")
            task = self._decode_task(row)
            if task["status"] != "QUEUED":
                return {
                    "ok": False,
                    "reason": "TASK_NOT_QUEUED",
                    "status": task["status"],
                }
            transition = transition_task(task, "IN_PROGRESS", by=by)
            if not transition["ok"]:
                return transition

            event = transition["event"]
            cursor = connection.execute(
                """UPDATE tasks SET status = 'IN_PROGRESS', resume_to = NULL, updated_at = ?
                    WHERE task_id = ? AND status = 'QUEUED'""",
                (event["at"], task_id),
            )
            if cursor.rowcount != 1:
                return {
                    "ok": False,
                    "reason": "STATE_CHANGED_RETRY",
                    "status": "QUEUED",
                }

            attempt = connection.execute(
                "SELECT COUNT(*) + 1 FROM runs WHERE task_id = ?", (task_id,)
            ).fetchone()[0]
            run_id = _identifier("run")
            connection.execute(
                """INSERT INTO runs (
                    run_id, external_run_id, task_id, adapter_id, model, status,
                    attempt, usage_json, error, started_at, ended_at
                ) VALUES (?, '', ?, ?, ?, 'RUNNING', ?, '{}', '', ?, NULL)""",
                (run_id, task_id, adapter_id, model, attempt, event["at"]),
            )
            self._record_event(
                connection,
                task_id=task_id,
                run_id=run_id,
                event_type="RUN_ASSIGNED",
                payload={
                    "from": event["from"],
                    "to": event["to"],
                    "by": by,
                    "reason": "",
                },
                at=event["at"],
            )
        return {"ok": True, "run": self.get_run(run_id)}

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        result = dict(row)
        result["usage"] = json.loads(result.pop("usage_json"))
        return result

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        usage: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, usage_json = ?, error = ?, ended_at = ? WHERE run_id = ?",
                (status, _json(usage or {}), error, _now(), run_id),
            )
        return self.get_run(run_id)

    def set_run_external_id(self, run_id: str, external_run_id: str) -> dict[str, Any]:
        external_run_id = str(external_run_id or "").strip()
        if not external_run_id:
            raise ValueError("external_run_id is required")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET external_run_id = ? WHERE run_id = ?",
                (external_run_id, run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"run not found: {run_id}")
        return self.get_run(run_id)

    def create_artifact(self, *, task_id: str, run_id: str, content: str) -> dict[str, Any]:
        artifact_id = _identifier("artifact")
        summary = content.strip().replace("\n", " ")[:180]
        now = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?, 'model-output', ?, ?, ?)",
                (artifact_id, task_id, run_id, content, summary, now),
            )
            connection.execute(
                "UPDATE tasks SET result_ref = ?, updated_at = ? WHERE task_id = ?",
                (artifact_id, now, task_id),
            )
            self._record_event(
                connection,
                task_id=task_id,
                run_id=run_id,
                event_type="ARTIFACT_CREATED",
                payload={"artifact_id": artifact_id, "summary": summary},
                at=now,
            )
        return {"artifact_id": artifact_id, "task_id": task_id, "run_id": run_id, "summary": summary}

    def create_decision(self, task_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        options = decision.get("options") or []
        if not decision.get("question") or not decision.get("context") or len(options) < 2:
            raise ValueError("decision requires question, context, and at least two options")
        decision_id = _identifier("decision")
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO decisions (
                    decision_id, task_id, status, question, context, options_json,
                    recommended_option, recommendation_reason, selected_option,
                    created_at, resolved_at, resolved_by
                ) VALUES (?, ?, 'PENDING', ?, ?, ?, ?, ?, NULL, ?, NULL, NULL)""",
                (
                    decision_id,
                    task_id,
                    str(decision["question"]),
                    str(decision["context"]),
                    _json(options),
                    str(decision.get("recommended_option") or ""),
                    str(decision.get("recommendation_reason") or ""),
                    now,
                ),
            )
            self._record_event(
                connection,
                task_id=task_id,
                event_type="DECISION_REQUESTED",
                payload={"decision_id": decision_id},
                at=now,
            )
        return self._get_decision(decision_id)

    def ensure_pending_decision(self, task_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        """Return the task's single pending decision, creating it atomically if needed."""
        options = decision.get("options") or []
        if not decision.get("question") or not decision.get("context") or len(options) < 2:
            raise ValueError("decision requires question, context, and at least two options")
        self.get_task(task_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT decision_id FROM decisions
                    WHERE task_id = ? AND status IN ('RECORDED', 'PENDING')
                    ORDER BY CASE status WHEN 'RECORDED' THEN 0 ELSE 1 END, created_at DESC
                    LIMIT 1""",
                (task_id,),
            ).fetchone()
            if row is not None:
                decision_id = row["decision_id"]
            else:
                decision_id = _identifier("decision")
                now = _now()
                connection.execute(
                    """INSERT INTO decisions (
                        decision_id, task_id, status, question, context, options_json,
                        recommended_option, recommendation_reason, selected_option,
                        created_at, resolved_at, resolved_by
                    ) VALUES (?, ?, 'PENDING', ?, ?, ?, ?, ?, NULL, ?, NULL, NULL)""",
                    (
                        decision_id,
                        task_id,
                        str(decision["question"]),
                        str(decision["context"]),
                        _json(options),
                        str(decision.get("recommended_option") or ""),
                        str(decision.get("recommendation_reason") or ""),
                        now,
                    ),
                )
                self._record_event(
                    connection,
                    task_id=task_id,
                    event_type="DECISION_REQUESTED",
                    payload={"decision_id": decision_id},
                    at=now,
                )
        return self._get_decision(decision_id)

    def _get_decision(self, decision_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"decision not found: {decision_id}")
        item = dict(row)
        item["options"] = json.loads(item.pop("options_json"))
        return item

    def pending_decisions(self) -> list[dict[str, Any]]:
        return [item for item in self.snapshot()["decisions"] if item["status"] == "PENDING"]

    def resolve_decision(self, decision_id: str, *, selected_option: str, by: str) -> dict[str, Any]:
        decision = self._get_decision(decision_id)
        lock = self.task_lock(decision["task_id"])
        with lock:
            return self._resolve_decision(
                decision_id,
                selected_option=selected_option,
                by=by,
            )

    def _resolve_decision(self, decision_id: str, *, selected_option: str, by: str) -> dict[str, Any]:
        decision = self._get_decision(decision_id)
        if decision["status"] != "PENDING":
            raise ValueError("decision is already recorded")
        valid = {str(item.get("letter") or "").upper() for item in decision["options"]}
        selected = selected_option.upper()
        if selected not in valid:
            raise ValueError("selected option is not part of this decision")
        selected_item = next(
            item
            for item in decision["options"]
            if str(item.get("letter") or "").upper() == selected
        )
        task = self.get_task(decision["task_id"])
        pause_result = None
        if selected_item.get("action") == "pause":
            if task["status"] != "QUEUED":
                raise RuntimeError("task is no longer available to pause")
            pause_result = transition_task(
                task,
                "PAUSED",
                by=by,
                reason="Human decision paused this task",
            )
            if not pause_result["ok"]:
                raise RuntimeError(pause_result["reason"])
        now = _now()
        with self._connect() as connection:
            if pause_result:
                pause_event = pause_result["event"]
                task_cursor = connection.execute(
                    """UPDATE tasks SET status = 'PAUSED', resume_to = 'QUEUED', updated_at = ?
                        WHERE task_id = ? AND status = 'QUEUED'""",
                    (pause_event["at"], task["task_id"]),
                )
                if task_cursor.rowcount != 1:
                    raise RuntimeError("task state changed before the decision was recorded")
            cursor = connection.execute(
                """UPDATE decisions SET status = 'RECORDED', selected_option = ?,
                    resolved_at = ?, resolved_by = ?
                    WHERE decision_id = ? AND status = 'PENDING'""",
                (selected, now, by, decision_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("decision is already recorded")
            self._record_event(
                connection,
                task_id=decision["task_id"],
                event_type="DECISION_RECORDED",
                payload={"decision_id": decision_id, "selected_option": selected, "by": by},
                at=now,
            )
            if pause_result:
                self._record_event(
                    connection,
                    task_id=task["task_id"],
                    event_type=pause_result["event"]["event"],
                    payload={
                        "from": pause_result["event"]["from"],
                        "to": pause_result["event"]["to"],
                        "by": by,
                        "reason": pause_result["event"]["reason"],
                    },
                    at=pause_result["event"]["at"],
                )
        if pause_result:
            return self._get_decision(decision_id)
        if task["status"] in {"BLOCKED", "PAUSED"}:
            resume_to = task.get("resume_to") or "QUEUED"
            resumed = self.transition(task["task_id"], resume_to, by=by, reason="Decision recorded")
            if not resumed["ok"]:
                raise RuntimeError(resumed["reason"])
            if resume_to == "IN_PROGRESS" and not self._has_running_run(task["task_id"]):
                queued = self.transition(task["task_id"], "QUEUED", by=by, reason="Ready for redispatch")
                if not queued["ok"]:
                    raise RuntimeError(queued["reason"])
        return self._get_decision(decision_id)

    def _has_running_run(self, task_id: str) -> bool:
        with self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM runs WHERE task_id = ? AND status = 'RUNNING'", (task_id,)
            ).fetchone()[0]
        return bool(count)

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as connection:
            workflow_rows = connection.execute("SELECT * FROM workflows ORDER BY rowid").fetchall()
            task_rows = connection.execute("SELECT * FROM tasks ORDER BY rowid").fetchall()
            run_rows = connection.execute("SELECT * FROM runs ORDER BY rowid").fetchall()
            event_rows = connection.execute("SELECT * FROM events ORDER BY event_id").fetchall()
            artifact_rows = connection.execute("SELECT * FROM artifacts ORDER BY rowid").fetchall()
            decision_rows = connection.execute("SELECT * FROM decisions ORDER BY rowid").fetchall()
        runs = []
        attempts: dict[str, int] = {}
        assignments: dict[str, dict[str, Any]] = {}
        for row in run_rows:
            run = dict(row)
            run["usage"] = json.loads(run.pop("usage_json"))
            runs.append(run)
            attempts[run["task_id"]] = max(attempts.get(run["task_id"], 0), run["attempt"])
            assignments[run["task_id"]] = {
                "route": run["adapter_id"],
                "model": run["model"],
                "executor": run["adapter_id"],
            }
        artifacts = [dict(row) for row in artifact_rows]
        artifacts_by_task: dict[str, list[str]] = {}
        for artifact in artifacts:
            artifacts_by_task.setdefault(artifact["task_id"], []).append(artifact["artifact_id"])
        tasks = [
            self._decode_task(
                row,
                attempts=attempts.get(row["task_id"], 0),
                artifacts=artifacts_by_task.get(row["task_id"], []),
            )
            for row in task_rows
        ]
        events = []
        for row in event_rows:
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json"))
            events.append(event)
        decisions = []
        for row in decision_rows:
            decision = dict(row)
            decision["options"] = json.loads(decision.pop("options_json"))
            decisions.append(decision)
        return {
            "schema_version": "personal-ai-os.runtime/v1",
            "workflows": [dict(row) for row in workflow_rows],
            "tasks": tasks,
            "runs": runs,
            "events": events,
            "artifacts": artifacts,
            "decisions": decisions,
            "assignments": assignments,
        }

    def integrity(self) -> dict[str, Any]:
        with self._connect() as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return {"status": "READY" if result == "ok" else "BLOCKED", "detail": result}


def install_workflow_preset(store: RuntimeStore, preset_id: str) -> dict[str, Any]:
    preset = get_workflow_preset(preset_id)
    store.create_workflow(preset)
    for task in preset["tasks"]:
        store.create_task({**task, "workflow_id": preset["workflow_id"], "line_id": preset["workflow_id"]})
    return store.get_workflow(preset["workflow_id"])


class ExecutionBroker:
    """One execution boundary shared by CLI, API, and future adapters."""

    def __init__(
        self,
        store: RuntimeStore,
        adapters: dict[str, Any],
        *,
        domain_profiles: dict[str, dict[str, Any]] | None = None,
    ):
        self.store = store
        self.adapters = dict(adapters)
        self.domain_profiles = domain_profiles or {}

    def adapter_catalog(self) -> list[dict[str, Any]]:
        return [self.adapters[key].probe() for key in sorted(self.adapters)]

    def dispatch(self, task_id: str, *, adapter_id: str, model: str) -> dict[str, Any]:
        lock = self.store.task_lock(task_id)
        if not lock.acquire(blocking=False):
            return {"ok": False, "reason": "TASK_ALREADY_DISPATCHING"}
        try:
            return self._dispatch(task_id, adapter_id=adapter_id, model=model)
        finally:
            lock.release()

    def _dispatch(self, task_id: str, *, adapter_id: str, model: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if task["status"] != "QUEUED":
            return {"ok": False, "reason": "TASK_NOT_QUEUED", "status": task["status"]}
        dependency_result_refs = set()
        for dependency in task["depends_on"]:
            dependency_task = self.store.get_task(dependency)
            if dependency_task["status"] not in {"DONE", "ARCHIVED"}:
                return {"ok": False, "reason": "DEPENDENCY_NOT_DONE", "dependency": dependency}
            if dependency_task.get("result_ref"):
                dependency_result_refs.add(dependency_task["result_ref"])
        if task["human_gate"]:
            task_decisions = [
                item
                for item in self.store.snapshot()["decisions"]
                if item["task_id"] == task_id
            ]
            if not any(item["status"] == "RECORDED" for item in task_decisions):
                decision = self.store.ensure_pending_decision(
                    task_id,
                    {
                        "question": f"Should {task['title']} continue?",
                        "context": task["acceptance"],
                        "options": [
                            {
                                "letter": "A",
                                "label": "Approve and continue",
                                "action": "continue",
                            },
                            {
                                "letter": "B",
                                "label": "Pause this task",
                                "action": "pause",
                            },
                        ],
                        "recommended_option": "A",
                        "recommendation_reason": "The task is ready and its dependencies are closed.",
                    },
                )
                if decision["status"] != "RECORDED":
                    return {"ok": False, "reason": "HUMAN_DECISION_REQUIRED"}
                task = self.store.get_task(task_id)
                if task["status"] != "QUEUED":
                    return {"ok": False, "reason": "TASK_NOT_QUEUED", "status": task["status"]}
        adapter = self.adapters.get(adapter_id)
        if adapter is None:
            return {"ok": False, "reason": "ADAPTER_NOT_FOUND"}
        probe = adapter.probe()
        if not probe.get("available"):
            return {"ok": False, "reason": "ADAPTER_UNAVAILABLE"}
        profile = self.domain_profiles.get(task["domain_id"])
        upstream_artifacts = [
            artifact
            for artifact in self.store.snapshot()["artifacts"]
            if artifact["artifact_id"] in dependency_result_refs
        ]
        claim = self.store.claim_run(
            task_id=task_id,
            adapter_id=adapter_id,
            model=model,
            by=f"adapter:{adapter_id}",
        )
        if not claim["ok"]:
            return claim
        run = claim["run"]
        with self.store._connect() as connection:
            self.store._record_event(
                connection,
                task_id=task_id,
                run_id=run["run_id"],
                event_type="ADAPTER_STARTED",
                payload={"adapter_id": adapter_id, "model": model},
            )
        try:
            receipt = adapter.start(
                task,
                model=model,
                context_pack=build_context_pack(
                    task,
                    profile,
                    upstream_artifacts=upstream_artifacts,
                ),
            )
        except Exception:
            receipt = {
                "ok": False,
                "reason": "ADAPTER_START_FAILED",
            }
        if not receipt.get("ok"):
            reason = _stable_error_code(
                receipt.get("reason"), "ADAPTER_START_FAILED"
            )
            error = reason
            self.store.finish_run(run["run_id"], status="REJECTED", error=error)
            self.store.transition(
                task_id,
                "BLOCKED",
                by=f"adapter:{adapter_id}",
                reason=error,
                run_id=run["run_id"],
            )
            return {"ok": False, "status": "BLOCKED", "reason": reason, "error": error}
        external_run_id = str(receipt.get("external_run_id") or "").strip()
        if not external_run_id:
            reason = "ADAPTER_RUN_ID_REQUIRED"
            self.store.finish_run(run["run_id"], status="REJECTED", error=reason)
            self.store.transition(
                task_id,
                "BLOCKED",
                by=f"adapter:{adapter_id}",
                reason=reason,
                run_id=run["run_id"],
            )
            return {"ok": False, "status": "BLOCKED", "reason": reason}
        self.store.set_run_external_id(run["run_id"], external_run_id)
        status = str(receipt.get("status") or "RUNNING").upper()
        if status not in {"RUNNING", "SUCCEEDED", "BLOCKED", "FAILED", "CANCELLED"}:
            status = "FAILED"
        if status == "RUNNING":
            return {"ok": True, "status": "IN_PROGRESS", "run": self.store.get_run(run["run_id"])}
        if status == "SUCCEEDED":
            artifact = self.store.create_artifact(
                task_id=task_id,
                run_id=run["run_id"],
                content=str(receipt.get("output_text") or ""),
            )
            self.store.finish_run(
                run["run_id"], status="SUCCEEDED", usage=receipt.get("usage") or {}
            )
            with self.store._connect() as connection:
                self.store._record_event(
                    connection,
                    task_id=task_id,
                    run_id=run["run_id"],
                    event_type="RUN_SUCCEEDED",
                    payload={"artifact_id": artifact["artifact_id"]},
                )
            review = self.store.transition(
                task_id,
                "REVIEW",
                by=f"adapter:{adapter_id}",
                reason="Model output registered",
                run_id=run["run_id"],
            )
            if not review["ok"]:
                blocked = self.store.transition(
                    task_id,
                    "BLOCKED",
                    by=f"adapter:{adapter_id}",
                    reason=review["reason"],
                    run_id=run["run_id"],
                )
                return {
                    "ok": False,
                    "status": "BLOCKED" if blocked["ok"] else "RECOVERY_REQUIRED",
                    "reason": review["reason"],
                    "run": self.store.get_run(run["run_id"]),
                }
            return {
                "ok": True,
                "status": "REVIEW",
                "run": self.store.get_run(run["run_id"]),
                "artifact": artifact,
            }
        error = _stable_error_code(
            receipt.get("reason"), f"ADAPTER_{status}"
        )
        self.store.finish_run(run["run_id"], status=status, usage=receipt.get("usage") or {}, error=error)
        blocked = self.store.transition(
            task_id,
            "BLOCKED",
            by=f"adapter:{adapter_id}",
            reason=error,
            run_id=run["run_id"],
        )
        decision = None
        if receipt.get("decision"):
            decision = self.store.create_decision(task_id, receipt["decision"])
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "HUMAN_DECISION_REQUIRED" if decision else error,
            "run": self.store.get_run(run["run_id"]),
            **({"decision": decision} if decision else {}),
        }
