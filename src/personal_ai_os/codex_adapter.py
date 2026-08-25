from __future__ import annotations

import json
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


_MAX_OUTPUT_CHARS = 1_000_000
_MODEL_LINE = re.compile(r'^\s*model\s*=\s*"([^"]+)"\s*(?:#.*)?$')


class CodexAppServerAdapter:
    """Synchronous execution adapter for the supported Codex app-server protocol."""

    adapter_id = "codex-app-server"

    def __init__(
        self,
        *,
        executable: str,
        workspace_root: str | Path,
        available: bool = True,
        timeout: float = 1800,
        popen: Any = subprocess.Popen,
    ):
        self.executable = str(executable)
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.available = bool(available)
        self.timeout = float(timeout)
        self._popen = popen

    @classmethod
    def auto_configured(
        cls,
        *,
        workspace_root: str | Path,
        model: str = "",
        timeout: float = 1800,
    ) -> tuple["CodexAppServerAdapter", str]:
        executable = shutil.which("codex")
        if not executable:
            raise ValueError("CODEX_EXECUTABLE_NOT_FOUND")
        try:
            app_server = subprocess.run(
                [executable, "app-server", "--help"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            login = subprocess.run(
                [executable, "login", "status"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("CODEX_DISCOVERY_FAILED") from exc
        if app_server.returncode != 0:
            raise ValueError("CODEX_APP_SERVER_UNAVAILABLE")
        if login.returncode != 0:
            raise ValueError("CODEX_LOGIN_REQUIRED")
        selected_model = str(model or cls._configured_model()).strip()
        if not selected_model:
            raise ValueError("CODEX_MODEL_REQUIRED")
        return (
            cls(
                executable=executable,
                workspace_root=workspace_root,
                available=True,
                timeout=timeout,
            ),
            selected_model,
        )

    @staticmethod
    def _configured_model() -> str:
        path = Path.home() / ".codex" / "config.toml"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        for line in lines:
            match = _MODEL_LINE.match(line)
            if match:
                return match.group(1).strip()
        return ""

    def probe(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "available": self.available,
            "protocol": "codex-app-server",
        }

    def start(
        self,
        task: dict[str, Any],
        *,
        model: str,
        context_pack: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.available:
            return {"ok": False, "reason": "CODEX_APP_SERVER_UNAVAILABLE"}
        prompt = (
            "执行下面这一项有界长期任务。严格停留在任务范围内，遵守工作区中的 "
            "AGENTS.md 与人工裁决，不自行扩大权限。完成后给出结果、证据边界和下一步交接。\n\n"
            + json.dumps(context_pack, ensure_ascii=False, sort_keys=True)
        )
        process = None
        messages: queue.Queue[Any] = queue.Queue()
        eof = object()
        try:
            process = self._popen(
                [self.executable, "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                cwd=str(self.workspace_root),
            )
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("CODEX_PROCESS_STREAM_MISSING")

            def read_stdout() -> None:
                try:
                    for raw in process.stdout:
                        try:
                            messages.put(json.loads(raw))
                        except (json.JSONDecodeError, TypeError):
                            continue
                finally:
                    messages.put(eof)

            threading.Thread(target=read_stdout, daemon=True).start()
            deadline = time.monotonic() + self.timeout

            def send(message: dict[str, Any]) -> None:
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                process.stdin.flush()

            backlog: list[dict[str, Any]] = []

            def next_message() -> dict[str, Any]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                value = messages.get(timeout=remaining)
                if value is eof:
                    raise RuntimeError("CODEX_APP_SERVER_DISCONNECTED")
                return value

            def request(request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
                send({"id": request_id, "method": method, "params": params})
                while True:
                    message = next_message()
                    if message.get("id") != request_id:
                        backlog.append(message)
                        continue
                    if message.get("error") is not None:
                        raise RuntimeError(f"CODEX_RPC_FAILED:{method}")
                    result = message.get("result")
                    if not isinstance(result, dict):
                        raise RuntimeError(f"CODEX_RPC_RECEIPT_MISSING:{method}")
                    return result

            request(
                1,
                "initialize",
                {
                    "clientInfo": {
                        "name": "personal-ai-os",
                        "title": "Personal AI OS",
                        "version": "0.15.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            send({"method": "initialized", "params": {}})
            thread_result = request(
                2,
                "thread/start",
                {
                    "cwd": str(self.workspace_root),
                    "model": model,
                    "approvalPolicy": "never",
                    "sandbox": "workspace-write",
                    "ephemeral": False,
                    "serviceName": "personal-ai-os",
                },
            )
            thread_id = str((thread_result.get("thread") or {}).get("id") or "")
            if not thread_id:
                raise RuntimeError("CODEX_THREAD_ID_REQUIRED")
            turn_result = request(
                3,
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "approvalPolicy": "never",
                },
            )
            turn_id = str((turn_result.get("turn") or {}).get("id") or "")
            if not turn_id:
                raise RuntimeError("CODEX_TURN_ID_REQUIRED")

            delta_chunks: dict[str, list[str]] = {}
            completed_messages: list[str] = []
            final_messages: list[str] = []
            pending = list(backlog)
            while True:
                message = pending.pop(0) if pending else next_message()
                if message.get("id") is not None and message.get("method"):
                    raise RuntimeError("CODEX_INTERACTION_REQUIRED")
                method = message.get("method")
                params = message.get("params") or {}
                if method == "item/agentMessage/delta":
                    delta = str(params.get("delta") or "")
                    item_id = str(params.get("itemId") or "unscoped")
                    chunks = delta_chunks.setdefault(item_id, [])
                    if sum(map(len, chunks)) + len(delta) <= _MAX_OUTPUT_CHARS:
                        chunks.append(delta)
                elif method == "item/completed":
                    item = params.get("item") or {}
                    if item.get("type") == "agentMessage":
                        item_id = str(item.get("id") or "unscoped")
                        text = str(
                            item.get("text")
                            or item.get("content")
                            or "".join(delta_chunks.get(item_id, []))
                        ).strip()[:_MAX_OUTPUT_CHARS]
                        if text:
                            completed_messages.append(text)
                            if item.get("phase") == "final":
                                final_messages.append(text)
                elif method == "turn/completed":
                    turn = params.get("turn") or {}
                    if params.get("threadId") != thread_id or turn.get("id") != turn_id:
                        continue
                    if turn.get("status") != "completed":
                        return {"ok": False, "reason": "CODEX_TURN_FAILED"}
                    fallback_chunks = next(
                        reversed(delta_chunks.values()), []
                    ) if delta_chunks else []
                    output = (
                        (final_messages[-1] if final_messages else "")
                        or (completed_messages[-1] if completed_messages else "")
                        or "".join(fallback_chunks).strip()
                        or "Codex 已完成本轮任务。"
                    )
                    return {
                        "ok": True,
                        "external_run_id": f"{thread_id}:{turn_id}",
                        "status": "SUCCEEDED",
                        "output_text": output,
                        "usage": turn.get("usage") or {},
                    }
        except TimeoutError:
            return {"ok": False, "reason": "CODEX_APP_SERVER_TIMEOUT"}
        except (OSError, RuntimeError, queue.Empty):
            return {"ok": False, "reason": "CODEX_APP_SERVER_FAILED"}
        finally:
            if process is not None:
                try:
                    if process.stdin is not None:
                        process.stdin.close()
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                    except OSError:
                        pass
