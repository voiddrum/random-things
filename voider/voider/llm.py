"""Thin Ollama chat client. Tool-calling shape matches Ollama's /api/chat."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger("voider.llm")


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_models(self) -> list[str]:
        r = await self._client.get(f"{self.base_url}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        last_role = messages[-1].get("role") if messages else "?"
        log.info(
            "chat → %s  msgs=%d  tools=%d  last=%s",
            self.model,
            len(messages),
            len(tools) if tools else 0,
            last_role,
        )
        t0 = time.monotonic()
        try:
            r = await self._client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
        except Exception as exc:
            log.error("chat ✗ failed after %.2fs: %r", time.monotonic() - t0, exc)
            raise
        dt = time.monotonic() - t0

        data = r.json()
        msg = data.get("message", {})
        content = msg.get("content", "") or ""
        raw_calls = msg.get("tool_calls") or []
        calls = [
            ToolCall(
                name=tc["function"]["name"],
                arguments=tc["function"].get("arguments") or {},
            )
            for tc in raw_calls
        ]
        log.info(
            "chat ← %.2fs  content=%d chars  tool_calls=%s",
            dt,
            len(content),
            [c.name for c in calls] or "[]",
        )
        eval_ms = (data.get("eval_count") or 0)
        eval_dur = data.get("eval_duration") or 0
        if eval_ms and eval_dur:
            tps = eval_ms / (eval_dur / 1e9)
            log.debug("ollama metrics: eval_count=%d eval_duration=%.2fs tok/s=%.1f",
                      eval_ms, eval_dur / 1e9, tps)
        return LLMResponse(content=content, tool_calls=calls)
