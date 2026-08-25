from __future__ import annotations

import datetime
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .cognition import compile_operating_practices, validate_memory_candidate
from .dispatching import select_execution_route
from .presets import get_workflow_preset
from .secretary import build_context_pack, model_context_for_task
from .states import TASK_STATES
from .task_links import validate_task_module_link
from .workflow import transition_task
from .work_protocols import SCHEMA_VERSION as WORK_PROTOCOL_SCHEMA_VERSION
from .work_protocols import validate_work_protocols, work_protocol_catalog


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


def _goal_policy(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("continuation_policy must be an object")
    defaults = {
        "max_steps_per_continuation": 3,
        "max_total_steps": 25,
        "max_total_tokens": 200000,
        "failure_budget_per_continuation": 1,
    }
    limits = {
        "max_steps_per_continuation": (1, 100),
        "max_total_steps": (1, 100000),
        "max_total_tokens": (1, 1000000000),
        "failure_budget_per_continuation": (1, 20),
    }
    unknown = set(value) - set(defaults)
    if unknown:
        raise ValueError(f"unknown continuation policy fields: {sorted(unknown)}")
    policy = {**defaults, **value}
    for field, (minimum, maximum) in limits.items():
        item = policy[field]
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
            raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return policy


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
                    domain_id TEXT NOT NULL,
                    protocol_id TEXT NOT NULL DEFAULT '',
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
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    workflow_ids_json TEXT NOT NULL,
                    completion_criteria TEXT NOT NULL,
                    continuation_policy_json TEXT NOT NULL,
                    steps_used INTEGER NOT NULL,
                    tokens_used INTEGER NOT NULL,
                    continuation_count INTEGER NOT NULL,
                    last_stop_reason TEXT NOT NULL,
                    active_continuation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS goal_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL REFERENCES goals(goal_id),
                    continuation_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    subject_kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    domain_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    privacy_class TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reviewed_by TEXT,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS memory_candidate_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL REFERENCES memory_candidates(candidate_id),
                    event_type TEXT NOT NULL,
                    by TEXT NOT NULL,
                    at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_module_links (
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    module_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    confirmed_by TEXT,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    PRIMARY KEY (task_id, module_id, relation)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id, attempt);
                CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_goal_events_goal ON goal_events(goal_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_candidates(subject_kind, subject_id, domain_id, status);
                CREATE INDEX IF NOT EXISTS idx_memory_events_candidate ON memory_candidate_events(candidate_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_module_links_module ON task_module_links(module_id, status);
                """
            )
            workflow_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(workflows)").fetchall()
            }
            if "domain_id" not in workflow_columns:
                connection.execute(
                    "ALTER TABLE workflows ADD COLUMN domain_id TEXT NOT NULL DEFAULT 'general'"
                )
                for row in connection.execute(
                    "SELECT workflow_id FROM workflows"
                ).fetchall():
                    domain = connection.execute(
                        """
                        SELECT domain_id, COUNT(*) AS task_count
                        FROM tasks
                        WHERE workflow_id = ?
                        GROUP BY domain_id
                        ORDER BY task_count DESC, domain_id
                        LIMIT 1
                        """,
                        (row["workflow_id"],),
                    ).fetchone()
                    if domain is not None:
                        connection.execute(
                            "UPDATE workflows SET domain_id = ? WHERE workflow_id = ?",
                            (domain["domain_id"], row["workflow_id"]),
                        )
            if "protocol_id" not in workflow_columns:
                connection.execute(
                    "ALTER TABLE workflows ADD COLUMN protocol_id TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                """UPDATE workflows SET protocol_id = 'meeting-source-first-v1'
                   WHERE workflow_id = 'meeting-notes' AND protocol_id = ''"""
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
            """
            INSERT INTO workflows (
                workflow_id, name, caption, layout, goal, domain_id, protocol_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                str(workflow.get("name") or workflow_id),
                str(workflow.get("caption") or ""),
                str(workflow.get("layout") or "custom"),
                str(workflow.get("goal") or ""),
                str(workflow.get("domain_id") or workflow_id),
                str(workflow.get("protocol_id") or "").strip(),
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

    @staticmethod
    def _decode_goal(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        goal = dict(row)
        goal["workflow_ids"] = json.loads(goal.pop("workflow_ids_json"))
        goal["continuation_policy"] = json.loads(
            goal.pop("continuation_policy_json")
        )
        goal["usage"] = {
            "steps_used": goal.pop("steps_used"),
            "tokens_used": goal.pop("tokens_used"),
            "continuation_count": goal.pop("continuation_count"),
            "last_stop_reason": goal.pop("last_stop_reason"),
        }
        return goal

    @staticmethod
    def _record_goal_event(
        connection: sqlite3.Connection,
        goal_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        continuation_id: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO goal_events (
                goal_id, continuation_id, event_type, payload_json, at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (goal_id, continuation_id, event_type, _json(payload), _now()),
        )

    def create_goal(self, value: dict[str, Any]) -> dict[str, Any]:
        goal_id = str(value.get("goal_id") or "").strip()
        title = str(value.get("title") or "").strip()
        objective = str(value.get("objective") or "").strip()
        completion_criteria = str(value.get("completion_criteria") or "").strip()
        workflow_ids = value.get("workflow_ids")
        if not goal_id or not title or not objective or not completion_criteria:
            raise ValueError("goal_id, title, objective, and completion_criteria are required")
        if (
            not isinstance(workflow_ids, list)
            or not workflow_ids
            or any(not str(item).strip() for item in workflow_ids)
        ):
            raise ValueError("workflow_ids must be a non-empty list")
        normalized_workflows = [str(item).strip() for item in workflow_ids]
        if len(set(normalized_workflows)) != len(normalized_workflows):
            raise ValueError("workflow_ids must be unique")
        policy = _goal_policy(value.get("continuation_policy") or {})
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = {
                row["workflow_id"]
                for row in connection.execute(
                    "SELECT workflow_id FROM workflows WHERE workflow_id IN ({})".format(
                        ",".join("?" for _ in normalized_workflows)
                    ),
                    normalized_workflows,
                ).fetchall()
            }
            missing = [item for item in normalized_workflows if item not in existing]
            if missing:
                raise ValueError(f"workflow is not registered: {missing[0]}")
            connection.execute(
                """
                INSERT INTO goals (
                    goal_id, title, objective, status, workflow_ids_json,
                    completion_criteria, continuation_policy_json, steps_used,
                    tokens_used, continuation_count, last_stop_reason,
                    active_continuation_id, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, 'ACTIVE', ?, ?, ?, 0, 0, 0, '', '', ?, ?, NULL)
                """,
                (
                    goal_id,
                    title,
                    objective,
                    _json(normalized_workflows),
                    completion_criteria,
                    _json(policy),
                    now,
                    now,
                ),
            )
            self._record_goal_event(
                connection,
                goal_id,
                "GOAL_CREATED",
                {"workflow_count": len(normalized_workflows)},
            )
        return self.get_goal(goal_id)

    def get_goal(self, goal_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM goals WHERE goal_id = ?", (goal_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"goal not found: {goal_id}")
        return self._decode_goal(row)

    def claim_goal_continuation(self, goal_id: str) -> dict[str, Any]:
        continuation_id = _identifier("continuation")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM goals WHERE goal_id = ?", (goal_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"goal not found: {goal_id}")
            goal = self._decode_goal(row)
            if goal["active_continuation_id"]:
                return {"ok": False, "reason": "GOAL_ALREADY_CONTINUING", "goal": goal}
            if goal["status"] not in {"ACTIVE", "BUDGET_LIMITED"}:
                return {
                    "ok": False,
                    "reason": f"GOAL_{goal['status']}",
                    "goal": goal,
                }
            updated = connection.execute(
                """
                UPDATE goals
                SET active_continuation_id = ?, updated_at = ?
                WHERE goal_id = ? AND status = ? AND active_continuation_id = ''
                """,
                (continuation_id, _now(), goal_id, goal["status"]),
            )
            if updated.rowcount != 1:
                return {"ok": False, "reason": "GOAL_STATE_CHANGED", "goal": goal}
            self._record_goal_event(
                connection,
                goal_id,
                "GOAL_CONTINUATION_STARTED",
                {},
                continuation_id=continuation_id,
            )
        return {"ok": True, "continuation_id": continuation_id, "goal": goal}

    def finish_goal_continuation(
        self,
        goal_id: str,
        continuation_id: str,
        *,
        steps: int,
        tokens: int,
        stop_reason: str,
        status: str = "ACTIVE",
    ) -> dict[str, Any]:
        if status not in {
            "ACTIVE",
            "BUDGET_LIMITED",
            "AWAITING_ACCEPTANCE",
            "RECOVERY_REQUIRED",
            "ERROR",
        }:
            raise ValueError("invalid continuation goal status")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """
                UPDATE goals
                SET status = ?, steps_used = steps_used + ?,
                    tokens_used = tokens_used + ?,
                    continuation_count = continuation_count + 1,
                    last_stop_reason = ?, active_continuation_id = '', updated_at = ?
                WHERE goal_id = ? AND active_continuation_id = ?
                """,
                (status, steps, tokens, stop_reason, _now(), goal_id, continuation_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("goal continuation state changed")
            self._record_goal_event(
                connection,
                goal_id,
                "GOAL_CONTINUATION_FINISHED",
                {
                    "steps": steps,
                    "tokens": tokens,
                    "stop_reason": stop_reason,
                    "status": status,
                },
                continuation_id=continuation_id,
            )
        return self.get_goal(goal_id)

    def _change_goal_status(
        self,
        goal_id: str,
        *,
        allowed_from: set[str],
        to: str,
        by: str,
        reason: str,
        completed: bool = False,
    ) -> dict[str, Any]:
        if not str(by).strip():
            raise ValueError("by is required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, active_continuation_id FROM goals WHERE goal_id = ?",
                (goal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"goal not found: {goal_id}")
            if row["active_continuation_id"]:
                raise RuntimeError("goal continuation is active")
            if row["status"] not in allowed_from:
                raise ValueError(f"goal cannot move from {row['status']} to {to}")
            now = _now()
            connection.execute(
                """
                UPDATE goals
                SET status = ?, updated_at = ?, completed_at = ?
                WHERE goal_id = ?
                """,
                (to, now, now if completed else None, goal_id),
            )
            self._record_goal_event(
                connection,
                goal_id,
                "GOAL_STATUS_CHANGED",
                {"from": row["status"], "to": to, "by": str(by), "reason": str(reason)},
            )
        return self.get_goal(goal_id)

    def pause_goal(self, goal_id: str, *, by: str, reason: str) -> dict[str, Any]:
        return self._change_goal_status(
            goal_id,
            allowed_from={"ACTIVE"},
            to="PAUSED",
            by=by,
            reason=reason,
        )

    def resume_goal(self, goal_id: str, *, by: str) -> dict[str, Any]:
        goal = self.get_goal(goal_id)
        if goal["status"] == "BUDGET_LIMITED":
            policy = goal["continuation_policy"]
            usage = goal["usage"]
            if (
                usage["steps_used"] >= policy["max_total_steps"]
                or usage["tokens_used"] >= policy["max_total_tokens"]
            ):
                raise ValueError("goal budget must be increased before resume")
        return self._change_goal_status(
            goal_id,
            allowed_from={"PAUSED", "BUDGET_LIMITED", "ERROR"},
            to="ACTIVE",
            by=by,
            reason="Goal resumed",
        )

    def complete_goal(self, goal_id: str, *, by: str, evidence: str) -> dict[str, Any]:
        if not str(evidence).strip():
            raise ValueError("completion evidence is required")
        if not str(by).strip():
            raise ValueError("by is required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM goals WHERE goal_id = ?", (goal_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"goal not found: {goal_id}")
            goal = self._decode_goal(row)
            if goal["active_continuation_id"]:
                raise RuntimeError("goal continuation is active")
            if goal["status"] != "AWAITING_ACCEPTANCE":
                raise ValueError(
                    f"goal cannot move from {goal['status']} to COMPLETE"
                )
            placeholders = ",".join("?" for _ in goal["workflow_ids"])
            task_states = [
                item["status"]
                for item in connection.execute(
                    f"SELECT status FROM tasks WHERE workflow_id IN ({placeholders})",
                    goal["workflow_ids"],
                ).fetchall()
            ]
            if not task_states or any(
                status not in {"DONE", "ARCHIVED"} for status in task_states
            ):
                raise ValueError("goal scope changed; continuation is required")
            now = _now()
            connection.execute(
                """
                UPDATE goals
                SET status = 'COMPLETE', updated_at = ?, completed_at = ?
                WHERE goal_id = ? AND status = 'AWAITING_ACCEPTANCE'
                """,
                (now, now, goal_id),
            )
            self._record_goal_event(
                connection,
                goal_id,
                "GOAL_STATUS_CHANGED",
                {
                    "from": "AWAITING_ACCEPTANCE",
                    "to": "COMPLETE",
                    "by": str(by),
                    "reason": str(evidence),
                },
            )
        return self.get_goal(goal_id)

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
        workflow = connection.execute(
            "SELECT domain_id FROM workflows WHERE workflow_id = ?", (workflow_id,)
        ).fetchone()
        if workflow is None:
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
            str(task.get("agent_role") or "通用执行角色"),
            status,
            task.get("resume_to"),
            _json(dependencies),
            int(bool(task.get("human_gate", False))),
            int(task.get("iteration") or 1),
            str(task.get("parallel_group") or "main"),
            _json(list(task.get("required_capabilities") or [])),
            str(task.get("complexity") or "standard"),
            str(task.get("domain_id") or workflow["domain_id"] or workflow_id),
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
        for raw_link in task.get("module_links") or []:
            self._insert_task_module_link(connection, task_id, raw_link)
        return task_id

    @staticmethod
    def _decode_module_link(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        link = dict(row)
        link["schema_version"] = "personal-ai-os.module-task-link/v1"
        return link

    def _insert_task_module_link(
        self,
        connection: sqlite3.Connection,
        task_id: str,
        raw_link: dict[str, Any],
    ) -> dict[str, Any]:
        link = validate_task_module_link(raw_link)
        if connection.execute(
            "SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone() is None:
            raise KeyError(f"task not found: {task_id}")
        now = _now()
        connection.execute(
            """
            INSERT INTO task_module_links (
                task_id, module_id, relation, source, confidence, status,
                confirmed_by, created_at, confirmed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id, module_id, relation) DO NOTHING
            """,
            (
                task_id,
                link["module_id"],
                link["relation"],
                link["source"],
                link["confidence"],
                link["status"],
                None,
                now,
                now if link["status"] == "CONFIRMED" else None,
            ),
        )
        row = connection.execute(
            """SELECT * FROM task_module_links
               WHERE task_id = ? AND module_id = ? AND relation = ?""",
            (task_id, link["module_id"], link["relation"]),
        ).fetchone()
        persisted = self._decode_module_link(row)
        if any(
            persisted[field] != link[field]
            for field in ("source", "confidence", "status")
        ):
            raise ValueError("module link definition drift")
        return persisted

    def link_task_module(self, task_id: str, link: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            return self._insert_task_module_link(connection, task_id, link)

    def confirm_task_module_link(
        self,
        task_id: str,
        module_id: str,
        relation: str,
        *,
        confirmed_by: str,
    ) -> dict[str, Any]:
        confirmed_by = str(confirmed_by or "").strip()
        if not confirmed_by:
            raise ValueError("module link confirmer is required")
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE task_module_links
                   SET status = 'CONFIRMED', confirmed_by = ?, confirmed_at = ?
                   WHERE task_id = ? AND module_id = ? AND relation = ?
                     AND status = 'PROPOSED'""",
                (confirmed_by, now, task_id, module_id, relation.upper()),
            )
            if cursor.rowcount != 1:
                raise ValueError("module link is missing or already confirmed")
            row = connection.execute(
                """SELECT * FROM task_module_links
                   WHERE task_id = ? AND module_id = ? AND relation = ?""",
                (task_id, module_id, relation.upper()),
            ).fetchone()
        return self._decode_module_link(row)

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
            module_links = [
                self._decode_module_link(item)
                for item in connection.execute(
                    "SELECT * FROM task_module_links WHERE task_id = ? ORDER BY rowid",
                    (task_id,),
                )
            ]
        task = self._decode_task(row, attempts=attempts, artifacts=artifacts)
        task["module_links"] = module_links
        return task

    @staticmethod
    def _decode_memory_candidate(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        candidate = dict(row)
        candidate["schema_version"] = "personal-ai-os.memory-candidate/v1"
        candidate["subject"] = {
            "kind": candidate.pop("subject_kind"),
            "id": candidate.pop("subject_id"),
        }
        candidate["evidence_refs"] = json.loads(candidate.pop("evidence_refs_json"))
        return candidate

    def create_memory_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidate = validate_memory_candidate(payload)
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_candidates (
                    candidate_id, subject_kind, subject_id, domain_id, category,
                    statement, evidence_refs_json, sample_count, privacy_class,
                    status, reviewed_by, version, created_at, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPOSED', NULL, ?, ?, NULL)
                """,
                (
                    candidate["candidate_id"],
                    candidate["subject"]["kind"],
                    candidate["subject"]["id"],
                    candidate["domain_id"],
                    candidate["category"],
                    candidate["statement"],
                    _json(candidate["evidence_refs"]),
                    candidate["sample_count"],
                    candidate["privacy_class"],
                    candidate["version"],
                    now,
                ),
            )
            connection.execute(
                """INSERT INTO memory_candidate_events
                   (candidate_id, event_type, by, at) VALUES (?, 'PROPOSED', ?, ?)""",
                (candidate["candidate_id"], "candidate-source", now),
            )
        return self.get_memory_candidate(candidate["candidate_id"])

    def get_memory_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"memory candidate not found: {candidate_id}")
        return self._decode_memory_candidate(row)

    def review_memory_candidate(
        self,
        candidate_id: str,
        *,
        decision: str,
        reviewed_by: str,
    ) -> dict[str, Any]:
        status = decision.upper()
        if status not in {"APPROVED", "REJECTED"}:
            raise ValueError("memory decision must be APPROVED or REJECTED")
        reviewed_by = str(reviewed_by or "").strip()
        if not reviewed_by:
            raise ValueError("memory reviewer is required")
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE memory_candidates
                   SET status = ?, reviewed_by = ?, reviewed_at = ?
                   WHERE candidate_id = ? AND status = 'PROPOSED'""",
                (status, reviewed_by, now, candidate_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("memory candidate is missing or already reviewed")
            connection.execute(
                """INSERT INTO memory_candidate_events
                   (candidate_id, event_type, by, at) VALUES (?, ?, ?, ?)""",
                (candidate_id, status, reviewed_by, now),
            )
        return self.get_memory_candidate(candidate_id)

    def operating_practices(
        self,
        *,
        subject: dict[str, str],
        domain_id: str,
    ) -> dict[str, Any]:
        return compile_operating_practices(
            self.snapshot()["memory_candidates"],
            subject=subject,
            domain_id=domain_id,
        )

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
        route_binding: dict[str, Any] | None = None,
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
            if route_binding:
                self._record_event(
                    connection,
                    task_id=task_id,
                    run_id=run_id,
                    event_type="AUTO_ROUTE_SELECTED",
                    payload=route_binding,
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
            goal_rows = connection.execute("SELECT * FROM goals ORDER BY rowid").fetchall()
            goal_event_rows = connection.execute(
                "SELECT * FROM goal_events ORDER BY event_id"
            ).fetchall()
            module_link_rows = connection.execute(
                "SELECT * FROM task_module_links ORDER BY rowid"
            ).fetchall()
            memory_candidate_rows = connection.execute(
                "SELECT * FROM memory_candidates ORDER BY rowid"
            ).fetchall()
            memory_candidate_event_rows = connection.execute(
                "SELECT * FROM memory_candidate_events ORDER BY event_id"
            ).fetchall()
        route_by_run_id = {}
        for row in event_rows:
            if row["event_type"] != "AUTO_ROUTE_SELECTED" or not row["run_id"]:
                continue
            payload = json.loads(row["payload_json"])
            if payload.get("route"):
                route_by_run_id[row["run_id"]] = str(payload["route"])
        runs = []
        attempts: dict[str, int] = {}
        assignments: dict[str, dict[str, Any]] = {}
        for row in run_rows:
            run = dict(row)
            run["usage"] = json.loads(run.pop("usage_json"))
            runs.append(run)
            attempts[run["task_id"]] = max(attempts.get(run["task_id"], 0), run["attempt"])
            assignments[run["task_id"]] = {
                "route": route_by_run_id.get(run["run_id"], run["adapter_id"]),
                "model": run["model"],
                "executor": run["adapter_id"],
            }
        artifacts = [dict(row) for row in artifact_rows]
        artifacts_by_task: dict[str, list[str]] = {}
        for artifact in artifacts:
            artifacts_by_task.setdefault(artifact["task_id"], []).append(artifact["artifact_id"])
        module_links = [self._decode_module_link(row) for row in module_link_rows]
        links_by_task: dict[str, list[dict[str, Any]]] = {}
        for link in module_links:
            links_by_task.setdefault(link["task_id"], []).append(link)
        tasks = []
        for row in task_rows:
            task = self._decode_task(
                row,
                attempts=attempts.get(row["task_id"], 0),
                artifacts=artifacts_by_task.get(row["task_id"], []),
            )
            task["module_links"] = links_by_task.get(row["task_id"], [])
            tasks.append(task)
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
        goal_events = []
        for row in goal_event_rows:
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json"))
            goal_events.append(event)
        return {
            "schema_version": "personal-ai-os.runtime/v1",
            "workflows": [dict(row) for row in workflow_rows],
            "tasks": tasks,
            "runs": runs,
            "events": events,
            "artifacts": artifacts,
            "decisions": decisions,
            "assignments": assignments,
            "goals": [self._decode_goal(row) for row in goal_rows],
            "goal_events": goal_events,
            "module_links": module_links,
            "memory_candidates": [
                self._decode_memory_candidate(row) for row in memory_candidate_rows
            ],
            "memory_candidate_events": [dict(row) for row in memory_candidate_event_rows],
        }

    def integrity(self) -> dict[str, Any]:
        with self._connect() as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return {"status": "READY" if result == "ok" else "BLOCKED", "detail": result}


def install_workflow_preset(store: RuntimeStore, preset_id: str) -> dict[str, Any]:
    preset = get_workflow_preset(preset_id)
    store.create_workflow(preset)
    for task in preset["tasks"]:
        store.create_task(
            {
                **task,
                "workflow_id": preset["workflow_id"],
                "line_id": preset["workflow_id"],
                "domain_id": preset.get("domain_id") or preset["workflow_id"],
            }
        )
    return store.get_workflow(preset["workflow_id"])


class ExecutionBroker:
    """One execution boundary shared by CLI, API, and future adapters."""

    def __init__(
        self,
        store: RuntimeStore,
        adapters: dict[str, Any],
        *,
        domain_profiles: dict[str, dict[str, Any]] | None = None,
        work_protocols: list[dict[str, Any]] | None = None,
    ):
        self.store = store
        self.adapters = dict(adapters)
        self.domain_profiles = domain_profiles or {}
        protocols = work_protocol_catalog() if work_protocols is None else work_protocols
        protocols = validate_work_protocols(
            {"schema_version": WORK_PROTOCOL_SCHEMA_VERSION, "protocols": protocols}
        )
        self.work_protocols = {
            str(item["protocol_id"]): dict(item) for item in protocols
        }

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

    def dispatch_routed(
        self,
        task_id: str,
        *,
        routes: list[dict[str, Any]],
        requested_route: str | None = None,
    ) -> dict[str, Any]:
        lock = self.store.task_lock(task_id)
        if not lock.acquire(blocking=False):
            return {"ok": False, "reason": "TASK_ALREADY_DISPATCHING"}
        binding: dict[str, Any] = {}
        try:
            result = self._dispatch(
                task_id,
                adapter_id="",
                model="",
                routes=routes,
                requested_route=requested_route,
                selected_binding=binding,
            )
        finally:
            lock.release()
        return {**result, **binding}

    def _resolve_task_route(
        self,
        task: dict[str, Any],
        routes: list[dict[str, Any]],
        requested_route: str | None,
    ) -> dict[str, Any]:
        routing = (task.get("context") or {}).get("routing") or {}
        if not isinstance(routing, dict):
            return {"status": "BLOCKED", "reason": "ROUTING_CONTEXT_INVALID"}
        estimated_tokens = routing.get("estimated_context_tokens", 0)
        if type(estimated_tokens) is not int or estimated_tokens < 0:
            return {"status": "BLOCKED", "reason": "ROUTING_CONTEXT_INVALID"}
        available_routes = []
        adapter_availability: dict[str, bool] = {}
        for route in routes:
            route_adapter_id = str(route.get("adapter_id") or "")
            available = False
            if route.get("enabled", True):
                if route_adapter_id not in adapter_availability:
                    adapter = self.adapters.get(route_adapter_id)
                    try:
                        adapter_availability[route_adapter_id] = bool(
                            adapter and adapter.probe().get("available")
                        )
                    except Exception:
                        adapter_availability[route_adapter_id] = False
                available = adapter_availability[route_adapter_id]
            available_routes.append({**route, "available": available})
        return select_execution_route(
            {**task, "estimated_context_tokens": estimated_tokens},
            available_routes,
            requested_route=requested_route,
        )

    def _dispatch(
        self,
        task_id: str,
        *,
        adapter_id: str,
        model: str,
        routes: list[dict[str, Any]] | None = None,
        requested_route: str | None = None,
        selected_binding: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        workflow = self.store.get_workflow(task["workflow_id"])
        protocol_id = str(workflow.get("protocol_id") or "").strip()
        work_protocol = self.work_protocols.get(protocol_id) if protocol_id else None
        if protocol_id and work_protocol is None:
            return {"ok": False, "status": "QUEUED", "reason": "WORK_PROTOCOL_REQUIRED"}
        if work_protocol and (
            task["workflow_id"] not in work_protocol.get("workflow_ids", [])
            or task["domain_id"] != work_protocol.get("domain_id")
        ):
            return {
                "ok": False,
                "status": "QUEUED",
                "reason": "WORK_PROTOCOL_SCOPE_MISMATCH",
            }
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
                        "question": f"是否继续“{task['title']}”？",
                        "context": task["acceptance"],
                        "options": [
                            {
                                "letter": "A",
                                "label": "批准并继续",
                                "action": "continue",
                            },
                            {
                                "letter": "B",
                                "label": "暂停任务",
                                "action": "pause",
                            },
                        ],
                        "recommended_option": "A",
                        "recommendation_reason": "任务依赖已经闭合，可以进入下一步。",
                    },
                )
                if decision["status"] != "RECORDED":
                    return {"ok": False, "reason": "HUMAN_DECISION_REQUIRED"}
                task = self.store.get_task(task_id)
                if task["status"] != "QUEUED":
                    return {"ok": False, "reason": "TASK_NOT_QUEUED", "status": task["status"]}
        route_binding = None
        if routes is not None:
            selected = self._resolve_task_route(task, routes, requested_route)
            if selected.get("status") != "RESOLVED":
                return {"ok": False, "reason": selected.get("reason") or "ROUTE_NOT_FOUND"}
            adapter_id = str(selected["adapter_id"])
            model = str(selected["model"])
            route_binding = {
                "route": str(selected["route"]),
                "adapter_id": adapter_id,
                "model": model,
                "selection": str(selected["selection"]),
            }
        adapter = self.adapters.get(adapter_id)
        if adapter is None:
            return {"ok": False, "reason": "ADAPTER_NOT_FOUND"}
        if routes is None:
            probe = adapter.probe()
            if not probe.get("available"):
                return {"ok": False, "reason": "ADAPTER_UNAVAILABLE"}
        profile = dict(self.domain_profiles.get(task["domain_id"]) or {})
        task_practice_subject = (
            (task.get("context") or {}).get("model_context") or {}
        ).get("practice_subject")
        protocol_practice_subject = (
            work_protocol.get("memory_subject") if work_protocol is not None else None
        )
        if (
            protocol_practice_subject is not None
            and task_practice_subject is not None
            and task_practice_subject != protocol_practice_subject
        ):
            return {
                "ok": False,
                "status": "QUEUED",
                "reason": "WORK_PROTOCOL_MEMORY_SCOPE_MISMATCH",
            }
        practice_subject = protocol_practice_subject or task_practice_subject
        if practice_subject is not None:
            if not isinstance(practice_subject, dict):
                return {"ok": False, "reason": "PRACTICE_SCOPE_INVALID"}
            try:
                operating_practices = self.store.operating_practices(
                    subject=practice_subject,
                    domain_id=task["domain_id"],
                )
            except ValueError:
                return {"ok": False, "reason": "PRACTICE_SCOPE_INVALID"}
            profile["operating_practices"] = operating_practices["rules"]
            profile["practice_evidence_refs"] = operating_practices["evidence_refs"]
        upstream_artifacts = [
            artifact
            for artifact in self.store.snapshot()["artifacts"]
            if artifact["artifact_id"] in dependency_result_refs
        ]
        try:
            context_pack = build_context_pack(
                task,
                profile,
                upstream_artifacts=upstream_artifacts,
                work_protocol=work_protocol,
            )
        except ValueError as exc:
            message = str(exc).lower()
            reason = (
                "CONTEXT_BUDGET_EXCEEDED"
                if "exceed" in message or "budget" in message
                else "CONTEXT_PACK_INVALID"
            )
            return {"ok": False, "status": "QUEUED", "reason": reason}
        claim = self.store.claim_run(
            task_id=task_id,
            adapter_id=adapter_id,
            model=model,
            by=f"adapter:{adapter_id}",
            route_binding=route_binding,
        )
        if not claim["ok"]:
            return claim
        run = claim["run"]
        if route_binding and selected_binding is not None:
            selected_binding.update(route_binding)
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
                context_pack=context_pack,
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
                if work_protocol and work_protocol.get("learning_review") == "candidate":
                    self.store._record_event(
                        connection,
                        task_id=task_id,
                        run_id=run["run_id"],
                        event_type="MEMORY_REVIEW_REQUESTED",
                        payload={"protocol_id": work_protocol["protocol_id"]},
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
