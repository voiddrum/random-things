"""FastAPI server. One WebSocket per browser tab.

Message protocol (JSON, both directions):
  client -> server:
    {"type": "user_message", "content": "..."}
    {"type": "permission_response", "request_id": "...", "decision": "allow_once|allow_always|deny_once|deny_always"}
    {"type": "permission_reset", "tool": "tool_name" | null}
  server -> client:
    {"type": "assistant_text", "content": "..."}
    {"type": "tool_call", "tool": "...", "target": "...", "summary": "...", "arguments": {...}}
    {"type": "tool_result", "tool": "...", "ok": bool, "content": "..."}
    {"type": "tool_error", "tool": "...", "error": "..."}
    {"type": "tool_denied", "tool": "...", "decision": "..."}
    {"type": "permission_request", "request_id": "...", "tool": "...", "target": "...", "summary": "...", "arguments": {...}}
    {"type": "reminder_fired", "id": "...", "text": "...", "due_ts": ...}
    {"type": "turn_done"}
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from voider.agent import Agent
from voider.config import load_config
from voider.llm import OllamaClient
from voider.permissions import Decision, PermissionLedger
from voider.tools import build_tools
from voider.tools.reminders import ReminderStore

log = logging.getLogger("voider.server")

WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(title="voider")


@app.on_event("startup")
async def _startup() -> None:
    cfg = load_config()
    app.state.cfg = cfg
    app.state.llm = OllamaClient(cfg.ollama_url, cfg.model)
    app.state.permissions = PermissionLedger(cfg.permissions_path)
    app.state.reminders = ReminderStore(path=cfg.reminders_path)
    app.state.tools = build_tools(cfg, app.state.reminders)
    app.state.agent = Agent(app.state.llm, app.state.tools, app.state.permissions)
    app.state.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
    app.state.reminder_task = asyncio.create_task(_reminder_loop(app))


async def _reminder_loop(app: FastAPI) -> None:
    store: ReminderStore = app.state.reminders
    runner = asyncio.create_task(store.run_forever())
    try:
        while True:
            r = await store.notify_queue.get()
            event = {
                "type": "reminder_fired",
                "id": r.id,
                "text": r.text,
                "due_ts": r.due_ts,
            }
            for q in list(app.state.subscribers):
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(event)
    finally:
        runner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runner


@app.on_event("shutdown")
async def _shutdown() -> None:
    task: asyncio.Task = app.state.reminder_task
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await app.state.llm.aclose()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    cfg = app.state.cfg
    try:
        models = await app.state.llm.list_models()
        ollama_up = True
    except Exception:  # noqa: BLE001
        models = []
        ollama_up = False
    return {
        "ok": True,
        "model": cfg.model,
        "ollama_up": ollama_up,
        "models_available": models,
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    pending: dict[str, asyncio.Future[Decision]] = {}
    broadcast_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    app.state.subscribers.add(broadcast_queue)

    history: list[dict[str, Any]] = []
    send_lock = asyncio.Lock()

    async def send(payload: dict[str, Any]) -> None:
        async with send_lock:
            await ws.send_text(json.dumps(payload))

    async def stream_event(event: dict[str, Any]) -> None:
        await send(event)

    async def prompt_for_permission(req: dict[str, Any]) -> Decision:
        fut: asyncio.Future[Decision] = asyncio.get_event_loop().create_future()
        pending[req["request_id"]] = fut
        await send({"type": "permission_request", **req})
        try:
            return await asyncio.wait_for(fut, timeout=300)
        except asyncio.TimeoutError:
            return "deny_once"
        finally:
            pending.pop(req["request_id"], None)

    async def pump_broadcasts() -> None:
        while True:
            event = await broadcast_queue.get()
            await send(event)

    pump_task = asyncio.create_task(pump_broadcasts())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send({"type": "error", "error": "invalid JSON"})
                continue

            mtype = msg.get("type")

            if mtype == "permission_response":
                rid = msg.get("request_id")
                decision = msg.get("decision")
                fut = pending.get(rid)
                if fut and not fut.done():
                    fut.set_result(decision)
                continue

            if mtype == "permission_reset":
                await app.state.permissions.reset(msg.get("tool"))
                await send({"type": "permission_reset_ok", "tool": msg.get("tool")})
                continue

            if mtype == "user_message":
                content = str(msg.get("content", "")).strip()
                if not content:
                    continue
                try:
                    history = await app.state.agent.respond(
                        history=history,
                        user_message=content,
                        prompt_for_permission=prompt_for_permission,
                        stream=stream_event,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.exception("agent error")
                    await send({"type": "error", "error": repr(exc)})
                await send({"type": "turn_done"})
                continue

            await send({"type": "error", "error": f"unknown type {mtype!r}"})

    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
        app.state.subscribers.discard(broadcast_queue)
        for fut in pending.values():
            if not fut.done():
                fut.set_result("deny_once")
