"""Permission ledger.

Each tool call is identified by (tool_name, target). `target` is whatever the
tool decides scopes a decision — a domain for `web_fetch`, the literal `"*"`
for tools the user has blanket-approved, etc.

Decisions:
  - allow_always — auto-approve forever
  - deny_always  — auto-deny forever
  - allow_once   — one-shot grant, not stored
  - deny_once    — one-shot deny, not stored
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

log = logging.getLogger("voider.permissions")

Decision = Literal["allow_once", "allow_always", "deny_once", "deny_always"]

PromptFn = Callable[[dict[str, Any]], Awaitable[Decision]]


@dataclass
class PermissionRequest:
    request_id: str
    tool: str
    target: str
    summary: str
    arguments: dict[str, Any]


class PermissionLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {"decisions": {}}
        self._lock = asyncio.Lock()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {"decisions": {}}
        self._data.setdefault("decisions", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _key(tool: str, target: str) -> str:
        return f"{tool}::{target}"

    def stored_decision(self, tool: str, target: str) -> Decision | None:
        entry = self._data["decisions"].get(self._key(tool, target))
        if not entry:
            entry = self._data["decisions"].get(self._key(tool, "*"))
        if not entry:
            return None
        return entry.get("decision")

    async def record(self, tool: str, target: str, decision: Decision) -> None:
        if decision not in ("allow_always", "deny_always"):
            return
        async with self._lock:
            self._data["decisions"][self._key(tool, target)] = {
                "decision": decision,
                "ts": int(time.time()),
            }
            self._save()

    async def reset(self, tool: str | None = None) -> None:
        async with self._lock:
            if tool is None:
                self._data["decisions"] = {}
            else:
                prefix = f"{tool}::"
                self._data["decisions"] = {
                    k: v for k, v in self._data["decisions"].items() if not k.startswith(prefix)
                }
            self._save()

    async def check(
        self,
        tool: str,
        target: str,
        summary: str,
        arguments: dict[str, Any],
        prompt: PromptFn,
    ) -> tuple[bool, Decision]:
        stored = self.stored_decision(tool, target)
        if stored == "allow_always":
            log.info("auto-allow %s::%s (stored)", tool, target)
            return True, stored
        if stored == "deny_always":
            log.info("auto-deny %s::%s (stored)", tool, target)
            return False, stored

        req = PermissionRequest(
            request_id=str(uuid.uuid4()),
            tool=tool,
            target=target,
            summary=summary,
            arguments=arguments,
        )
        log.info("prompt %s::%s → user (waiting)", tool, target)
        t0 = time.monotonic()
        decision = await prompt(
            {
                "request_id": req.request_id,
                "tool": req.tool,
                "target": req.target,
                "summary": req.summary,
                "arguments": req.arguments,
            }
        )
        log.info("decision %s::%s = %s  (%.1fs)", tool, target, decision, time.monotonic() - t0)
        await self.record(tool, target, decision)
        return decision in ("allow_once", "allow_always"), decision
