from __future__ import annotations

import datetime
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .runtime import RuntimeStore, _identifier, _now


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["project"] = json.loads(result.pop("project_json"))
    result["context_pack"] = json.loads(result.pop("context_json"))
    for raw_key, public_key in (
        ("thread_verification_json", "thread_verification"),
        ("completion_receipt_json", "completion_receipt"),
    ):
        raw = result.pop(raw_key, "{}")
        try:
            result[public_key] = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            result[public_key] = {}
    return result


class CodexProjectAdapter:
    """Queue Codex work for an app-native project dispatcher."""

    adapter_id = "codex-project"

    def __init__(
        self,
        store: RuntimeStore,
        *,
        project_bindings: list[dict[str, Any]],
    ):
        self.store = store
        self.project_bindings = [self._binding(item) for item in project_bindings]
        if not self.project_bindings:
            raise ValueError("at least one Codex project binding is required")
        with self.store._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS codex_project_dispatches (
                    dispatch_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    run_id TEXT,
                    model TEXT NOT NULL,
                    project_json TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    lease_until TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    host_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_codex_project_dispatch
                ON codex_project_dispatches(task_id)
                WHERE status IN ('PENDING', 'CLAIMED', 'RUNNING');
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(codex_project_dispatches)"
                ).fetchall()
            }
            if "thread_verification_json" not in columns:
                connection.execute(
                    "ALTER TABLE codex_project_dispatches "
                    "ADD COLUMN thread_verification_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "completion_receipt_json" not in columns:
                connection.execute(
                    "ALTER TABLE codex_project_dispatches "
                    "ADD COLUMN completion_receipt_json TEXT NOT NULL DEFAULT '{}'"
                )

    @staticmethod
    def _binding(value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("Codex project binding must be an object")
        project_key = str(value.get("project_key") or "").strip()
        configured_project_id = str(value.get("project_id") or "").strip()
        label = str(value.get("label") or "").strip()
        path = Path(str(value.get("path") or "")).expanduser().resolve()
        workflow_ids = [str(item).strip() for item in value.get("workflow_ids") or []]
        domain_ids = [str(item).strip() for item in value.get("domain_ids") or []]
        environment = str(value.get("environment") or "worktree").strip()
        if not project_key or not label:
            raise ValueError("Codex project key and label are required")
        if not path.is_dir():
            raise ValueError("Codex project path must be an existing directory")
        if not workflow_ids and not domain_ids:
            raise ValueError("Codex project binding requires a workflow or domain")
        if environment not in {"local", "worktree"}:
            raise ValueError("Codex project environment must be local or worktree")
        return {
            "project_key": project_key,
            **({"project_id": configured_project_id} if configured_project_id else {}),
            "label": label,
            "path": str(path),
            "workflow_ids": workflow_ids,
            "domain_ids": domain_ids,
            "environment": environment,
        }

    def probe(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "available": bool(self.project_bindings),
            "protocol": "codex-project-bridge",
        }

    def _project_for(self, task: dict[str, Any]) -> dict[str, Any]:
        workflow_id = str(task.get("workflow_id") or "")
        domain_id = str(task.get("domain_id") or "")
        workflow_matches = [
            item for item in self.project_bindings if workflow_id in item["workflow_ids"]
        ]
        matches = workflow_matches or [
            item for item in self.project_bindings if domain_id in item["domain_ids"]
        ]
        if len(matches) != 1:
            raise ValueError("Codex project binding is missing or ambiguous")
        return dict(matches[0])

    @staticmethod
    def _prompt(task: dict[str, Any], context_pack: dict[str, Any]) -> str:
        return (
            "执行下面这一项有界长期任务。严格停留在任务范围内，遵守工作区中的 "
            "AGENTS.md 与人工裁决，不自行扩大权限。完成后给出结果、证据边界和下一步交接。\n\n"
            f"任务：{task.get('title') or task.get('task_id')}\n"
            + json.dumps(context_pack, ensure_ascii=False, sort_keys=True)
        )

    def start(
        self,
        task: dict[str, Any],
        *,
        model: str,
        context_pack: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            project = self._project_for(task)
            # A project queue can contain more than one task attempt.  The
            # dispatch id is the external run identity, so a constant would
            # collide on the second task and make the adapter appear flaky.
            dispatch_id = _identifier(f"project-dispatch-{uuid.uuid4().hex}")
            now = _now()
            with self.store._connect() as connection:
                connection.execute(
                    """INSERT INTO codex_project_dispatches (
                        dispatch_id, task_id, run_id, model, project_json,
                        context_json, prompt, status, worker_id, lease_until,
                        thread_id, project_id, host_id, created_at, updated_at
                    ) VALUES (?, ?, '', ?, ?, ?, ?, 'PENDING', '', '', '', '', '', ?, ?)""",
                    (
                        dispatch_id,
                        task["task_id"],
                        str(model),
                        json.dumps(project, ensure_ascii=False, sort_keys=True),
                        json.dumps(context_pack, ensure_ascii=False, sort_keys=True),
                        self._prompt(task, context_pack),
                        now,
                        now,
                    ),
                )
        except (ValueError, sqlite3.IntegrityError):
            return {"ok": False, "reason": "CODEX_PROJECT_DISPATCH_INVALID"}
        return {
            "ok": True,
            "external_run_id": dispatch_id,
            "status": "RUNNING",
        }

    def get_dispatch(self, dispatch_id: str) -> dict[str, Any]:
        with self.store._connect() as connection:
            row = connection.execute(
                "SELECT * FROM codex_project_dispatches WHERE dispatch_id = ?",
                (dispatch_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Codex project dispatch not found: {dispatch_id}")
        return _decode(row)

    def pending_dispatches(self) -> list[dict[str, Any]]:
        with self.store._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM codex_project_dispatches
                   WHERE status = 'PENDING' ORDER BY created_at, dispatch_id"""
            ).fetchall()
        return [_decode(row) for row in rows]

    def active_dispatches(self) -> list[dict[str, Any]]:
        with self.store._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM codex_project_dispatches
                   WHERE status IN ('PENDING', 'CLAIMED', 'RUNNING', 'COMPLETING')
                   ORDER BY created_at, dispatch_id"""
            ).fetchall()
        return [_decode(row) for row in rows]

    def projection_dispatches(self) -> list[dict[str, Any]]:
        """Return durable execution receipts for task projection.

        The queue endpoint intentionally exposes only live work. The workbench
        needs the durable Codex receipt as well after a run moves to REVIEW, so
        a completed dispatch remains traceable without reopening the queue. The
        projection selects the newest row per task from this creation-ordered
        list.
        """
        with self.store._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM codex_project_dispatches
                   ORDER BY created_at, dispatch_id"""
            ).fetchall()
        return [_decode(row) for row in rows]

    def claim_next(self, *, worker_id: str) -> dict[str, Any] | None:
        worker_id = str(worker_id or "").strip()
        if not worker_id:
            raise ValueError("worker_id is required")
        now = datetime.datetime.now().astimezone()
        lease_until = (now + datetime.timedelta(minutes=15)).isoformat(timespec="seconds")
        now_text = now.isoformat(timespec="seconds")
        with self.store._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT dispatch_id FROM codex_project_dispatches
                   WHERE status = 'PENDING'
                      OR (status = 'CLAIMED' AND lease_until < ?)
                   ORDER BY created_at, dispatch_id LIMIT 1""",
                (now_text,),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """UPDATE codex_project_dispatches
                   SET status = 'CLAIMED', worker_id = ?, lease_until = ?, updated_at = ?
                   WHERE dispatch_id = ?
                     AND (status = 'PENDING' OR (status = 'CLAIMED' AND lease_until < ?))""",
                (worker_id, lease_until, now_text, row["dispatch_id"], now_text),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_dispatch(row["dispatch_id"])

    def bind_thread(
        self,
        dispatch_id: str,
        *,
        thread_id: str,
        project_id: str,
        host_id: str,
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        thread_id = str(thread_id or "").strip()
        project_id = str(project_id or "").strip()
        host_id = str(host_id or "").strip()
        if not thread_id or not project_id or not host_id:
            raise ValueError("Codex thread, project, and host ids are required")
        if not isinstance(verification, dict):
            raise ValueError("Codex thread/project verification is required")
        source = str(verification.get("source") or "").strip()
        if source not in {"task-project", "thread-project-assignments"}:
            raise ValueError("Codex thread/project verification source is invalid")
        if verification.get("verified") is not True:
            raise ValueError("Codex thread/project verification is not confirmed")
        if str(verification.get("project_id") or "").strip() != project_id:
            raise ValueError("Codex thread/project verification does not match project id")
        project_path = str(verification.get("project_path") or "").strip()
        environment = str(verification.get("environment") or "").strip()
        if not project_path or not environment:
            raise ValueError("Codex thread/project verification lacks project path or environment")
        now = _now()
        with self.store._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            dispatch = connection.execute(
                "SELECT * FROM codex_project_dispatches WHERE dispatch_id = ?",
                (dispatch_id,),
            ).fetchone()
            if dispatch is None or dispatch["status"] != "CLAIMED":
                raise ValueError("Codex project dispatch is not claimed")
            run = connection.execute(
                """SELECT * FROM runs
                   WHERE external_run_id = ? AND status = 'RUNNING'""",
                (dispatch_id,),
            ).fetchone()
            if run is None:
                raise ValueError("Codex project dispatch run is unavailable")
            project = json.loads(dispatch["project_json"])
            configured_project_id = str(project.get("project_id") or "").strip()
            if configured_project_id and configured_project_id != project_id:
                raise ValueError("Codex thread project id does not match configured Codex project")
            if str(Path(project_path).expanduser().resolve()) != str(Path(project["path"]).resolve()):
                raise ValueError("Codex thread project path does not match configured Codex project")
            if environment != project["environment"]:
                raise ValueError("Codex thread project environment does not match configured Codex project")
            cursor = connection.execute(
                """UPDATE codex_project_dispatches
                   SET status = 'RUNNING', run_id = ?, thread_id = ?, project_id = ?,
                       host_id = ?, lease_until = '', thread_verification_json = ?, updated_at = ?
                   WHERE dispatch_id = ? AND status = 'CLAIMED'""",
                (
                    run["run_id"], thread_id, project_id, host_id,
                    json.dumps(verification, ensure_ascii=False, sort_keys=True),
                    now, dispatch_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Codex project dispatch claim changed")
            connection.execute(
                "UPDATE runs SET external_run_id = ? WHERE run_id = ? AND status = 'RUNNING'",
                (thread_id, run["run_id"]),
            )
            self.store._record_event(
                connection,
                task_id=dispatch["task_id"],
                run_id=run["run_id"],
                event_type="CODEX_PROJECT_THREAD_BOUND",
                payload={"project_key": json.loads(dispatch["project_json"])["project_key"]},
                at=now,
            )
        return self.get_dispatch(dispatch_id)

    def complete(
        self,
        dispatch_id: str,
        *,
        output_text: str,
        usage: dict[str, Any] | None = None,
        completion_receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dispatch = self.get_dispatch(dispatch_id)
        if dispatch["status"] != "RUNNING":
            raise ValueError("Codex project dispatch is not running")
        if not str(output_text or "").strip():
            raise ValueError("Codex final output is required")
        if not isinstance(completion_receipt, dict):
            raise ValueError("Codex terminal receipt is required")
        if str(completion_receipt.get("status") or "").strip() != "completed":
            raise ValueError("Codex terminal receipt is not completed")
        if completion_receipt.get("verified") is not True:
            raise ValueError("Codex terminal receipt is not confirmed")
        if completion_receipt.get("needs_user_input") is not False:
            raise ValueError("Codex terminal receipt still needs user input")
        if completion_receipt.get("human_gate") is not False:
            raise ValueError("Codex terminal receipt is waiting at a human gate")
        with self.store._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE codex_project_dispatches
                   SET status = 'COMPLETING', completion_receipt_json = ?, updated_at = ?
                   WHERE dispatch_id = ? AND status = 'RUNNING'""",
                (
                    json.dumps(completion_receipt, ensure_ascii=False, sort_keys=True),
                    _now(), dispatch_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Codex project dispatch is not running")
        run = self.store.get_run(dispatch["run_id"])
        if run["status"] != "RUNNING":
            raise ValueError("Codex project run is not running")
        artifact = self.store.create_artifact(
            task_id=dispatch["task_id"],
            run_id=run["run_id"],
            content=str(output_text or ""),
        )
        self.store.finish_run(run["run_id"], status="SUCCEEDED", usage=usage or {})
        with self.store._connect() as connection:
            self.store._record_event(
                connection,
                task_id=dispatch["task_id"],
                run_id=run["run_id"],
                event_type="RUN_SUCCEEDED",
                payload={"artifact_id": artifact["artifact_id"]},
            )
        review = self.store.transition(
            dispatch["task_id"],
            "REVIEW",
            by="adapter:codex-project",
            reason="Codex project result registered",
            run_id=run["run_id"],
        )
        status = "SUCCEEDED" if review["ok"] else "BLOCKED"
        with self.store._connect() as connection:
            connection.execute(
                """UPDATE codex_project_dispatches SET status = ?, updated_at = ?
                   WHERE dispatch_id = ? AND status = 'COMPLETING'""",
                (status, _now(), dispatch_id),
            )
        if not review["ok"]:
            return {"ok": False, "status": "BLOCKED", "reason": review["reason"]}
        return {"ok": True, "status": "REVIEW", "artifact": artifact}
