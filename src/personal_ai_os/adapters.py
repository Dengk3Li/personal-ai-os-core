from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


class OpenAICompatibleAdapter:
    """Minimal adapter for Chat Completions-compatible model endpoints."""

    adapter_id = "openai-compatible"

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        timeout: float = 120,
        opener: Any | None = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        hostname = (urlsplit(self.api_base).hostname or "").lower()
        if opener is not None:
            self.opener = opener
        elif hostname in {"127.0.0.1", "localhost", "::1"}:
            self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        else:
            self.opener = urllib.request.build_opener()

    def probe(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "available": bool(self.api_base and self.api_key),
            "protocol": "chat-completions",
        }

    def start(
        self,
        task: dict[str, Any],
        *,
        model: str,
        context_pack: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.probe()["available"]:
            return {"ok": False, "reason": "ADAPTER_NOT_CONFIGURED"}
        system = (
            "You are executing one bounded task inside a long-running workflow. "
            "Return the result, evidence limits, and the next handoff."
        )
        user = json.dumps(context_pack, ensure_ascii=False, sort_keys=True)
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.api_base}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
            content = payload["choices"][0]["message"]["content"]
            external_run_id = str(payload.get("id") or "").strip()
            if not external_run_id:
                return {"ok": False, "reason": "ADAPTER_RUN_ID_REQUIRED"}
            return {
                "ok": True,
                "external_run_id": external_run_id,
                "status": "SUCCEEDED",
                "output_text": str(content),
                "usage": payload.get("usage") or {},
            }
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as exc:
            return {"ok": False, "reason": "ADAPTER_REQUEST_FAILED", "error": str(exc)}
