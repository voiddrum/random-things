"""Agent loop: chat -> LLM -> (tool calls?) -> permission check -> execute -> repeat."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from voider.llm import LLMResponse, OllamaClient
from voider.permissions import Decision, PermissionLedger
from voider.tools.base import Tool, ToolResult

log = logging.getLogger("voider.agent")


def _short(s: Any, n: int = 120) -> str:
    s = str(s).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


SYSTEM_PROMPT = """You are voider, a local assistant running on the user's machine.

You have tools for: saving/listing/reading notes, web search, fetching URLs, and \
setting/listing reminders. Use a tool when it would actually help — otherwise reply \
directly. When a tool's result is shown to you, summarize it for the user in plain \
language. Be concise.

Every tool call may prompt the user for permission. If a call is denied, do not retry \
the same call; either pick a different approach or tell the user."""


PromptFn = Callable[[dict[str, Any]], Awaitable[Decision]]
StreamFn = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class Agent:
    llm: OllamaClient
    tools: list[Tool]
    permissions: PermissionLedger
    max_turns: int = 8

    def __post_init__(self) -> None:
        self._tool_by_name = {t.name: t for t in self.tools}
        self._tool_schemas = [t.schema() for t in self.tools]

    async def respond(
        self,
        history: list[dict[str, Any]],
        user_message: str,
        prompt_for_permission: PromptFn,
        stream: StreamFn,
    ) -> list[dict[str, Any]]:
        if not history or history[0].get("role") != "system":
            history = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

        history.append({"role": "user", "content": user_message})
        turn_t0 = time.monotonic()
        log.info("turn start | user=%r", _short(user_message, 100))

        for turn_idx in range(self.max_turns):
            log.info("loop %d/%d | history=%d msgs", turn_idx + 1, self.max_turns, len(history))
            resp: LLMResponse = await self.llm.chat(history, tools=self._tool_schemas)

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": resp.content}
            if resp.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"function": {"name": tc.name, "arguments": tc.arguments}}
                    for tc in resp.tool_calls
                ]
            history.append(assistant_msg)

            if resp.content:
                await stream({"type": "assistant_text", "content": resp.content})

            if not resp.tool_calls:
                log.info(
                    "turn done | %.2fs total | content=%d chars",
                    time.monotonic() - turn_t0,
                    len(resp.content),
                )
                return history

            log.info("plan: %d tool call(s) → %s",
                     len(resp.tool_calls), [c.name for c in resp.tool_calls])

            for call in resp.tool_calls:
                tool = self._tool_by_name.get(call.name)
                if tool is None:
                    log.warning("unknown tool requested: %s", call.name)
                    history.append(
                        {
                            "role": "tool",
                            "name": call.name,
                            "content": f"Unknown tool: {call.name}",
                        }
                    )
                    await stream({"type": "tool_error", "tool": call.name, "error": "unknown tool"})
                    continue

                target = tool.permission_target(call.arguments)
                summary = tool.permission_summary(call.arguments)
                log.info(
                    "→ %s  target=%s  args=%s",
                    call.name,
                    target,
                    _short(json.dumps(call.arguments, default=str), 200),
                )
                await stream(
                    {
                        "type": "tool_call",
                        "tool": call.name,
                        "target": target,
                        "summary": summary,
                        "arguments": call.arguments,
                    }
                )

                allowed, decision = await self.permissions.check(
                    tool=call.name,
                    target=target,
                    summary=summary,
                    arguments=call.arguments,
                    prompt=prompt_for_permission,
                )

                if not allowed:
                    log.info("✗ %s denied (%s)", call.name, decision)
                    msg = f"User denied this tool call ({decision})."
                    history.append({"role": "tool", "name": call.name, "content": msg})
                    await stream({"type": "tool_denied", "tool": call.name, "decision": decision})
                    continue

                t0 = time.monotonic()
                try:
                    result: ToolResult = await tool.run(call.arguments)
                    dt = time.monotonic() - t0
                    log.info(
                        "← %s  ok=%s  %.2fs  content=%d chars",
                        call.name,
                        result.ok,
                        dt,
                        len(result.content),
                    )
                    payload = result.content if result.ok else f"ERROR: {result.content}"
                    history.append({"role": "tool", "name": call.name, "content": payload})
                    await stream(
                        {
                            "type": "tool_result",
                            "tool": call.name,
                            "ok": result.ok,
                            "content": result.content,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    dt = time.monotonic() - t0
                    log.exception("✗ %s raised after %.2fs", call.name, dt)
                    history.append(
                        {
                            "role": "tool",
                            "name": call.name,
                            "content": f"ERROR: {exc!r}",
                        }
                    )
                    await stream({"type": "tool_error", "tool": call.name, "error": repr(exc)})

        log.warning("hit max_turns=%d, stopping", self.max_turns)
        history.append(
            {
                "role": "assistant",
                "content": "(stopped: hit max tool-call turns)",
            }
        )
        await stream({"type": "assistant_text", "content": "(stopped: hit max tool-call turns)"})
        return history


def safe_json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(obj))
