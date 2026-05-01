"""Persistent reminders. A background task scans due reminders and pushes
notifications onto a queue the server consumes (and forwards to the UI).
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dateutil import parser as dateparser

from voider.tools.base import Tool, ToolResult


@dataclass
class Reminder:
    id: str
    text: str
    due_ts: float
    fired: bool = False


@dataclass
class ReminderStore:
    path: Path
    notify_queue: asyncio.Queue[Reminder] = field(default_factory=asyncio.Queue)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _items: dict[str, Reminder] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for item in data.get("reminders", []):
            r = Reminder(
                id=item["id"],
                text=item["text"],
                due_ts=item["due_ts"],
                fired=item.get("fired", False),
            )
            self._items[r.id] = r

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "reminders": [
                {"id": r.id, "text": r.text, "due_ts": r.due_ts, "fired": r.fired}
                for r in self._items.values()
            ]
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    async def add(self, text: str, due_ts: float) -> Reminder:
        async with self._lock:
            r = Reminder(id=str(uuid.uuid4())[:8], text=text, due_ts=due_ts)
            self._items[r.id] = r
            self._save_locked()
            return r

    async def all(self) -> list[Reminder]:
        async with self._lock:
            return sorted(self._items.values(), key=lambda r: r.due_ts)

    async def mark_fired(self, rid: str) -> None:
        async with self._lock:
            if rid in self._items:
                self._items[rid].fired = True
                self._save_locked()

    async def run_forever(self) -> None:
        while True:
            now = time.time()
            due: list[Reminder] = []
            async with self._lock:
                for r in self._items.values():
                    if not r.fired and r.due_ts <= now:
                        due.append(r)
            for r in due:
                await self.notify_queue.put(r)
                await self.mark_fired(r.id)
            await asyncio.sleep(5)


class ReminderSetTool(Tool):
    name = "reminder_set"
    description = (
        "Schedule a reminder. `when` accepts natural-ish strings (e.g. "
        "'2025-05-02 14:00', 'tomorrow 9am', 'in 30 minutes')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "when": {"type": "string"},
        },
        "required": ["text", "when"],
    }

    def __init__(self, store: ReminderStore) -> None:
        self.store = store

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        text = str(arguments.get("text", "")).strip()
        when = str(arguments.get("when", "")).strip()
        if not text or not when:
            return ToolResult(ok=False, content="text and when are required")

        due_ts = _parse_when(when)
        if due_ts is None:
            return ToolResult(ok=False, content=f"Could not parse time: {when!r}")
        if due_ts <= time.time():
            return ToolResult(ok=False, content="That time is in the past.")

        r = await self.store.add(text, due_ts)
        human = time.strftime("%Y-%m-%d %H:%M", time.localtime(due_ts))
        return ToolResult(
            ok=True,
            content=f"Reminder set for {human}: {text}",
            data={"id": r.id, "due_ts": due_ts},
        )


class ReminderListTool(Tool):
    name = "reminder_list"
    description = "List upcoming reminders."
    parameters = {"type": "object", "properties": {}}

    def __init__(self, store: ReminderStore) -> None:
        self.store = store

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        items = await self.store.all()
        upcoming = [r for r in items if not r.fired]
        if not upcoming:
            return ToolResult(ok=True, content="No upcoming reminders.")
        lines = [
            f"- [{r.id}] {time.strftime('%Y-%m-%d %H:%M', time.localtime(r.due_ts))} — {r.text}"
            for r in upcoming
        ]
        return ToolResult(ok=True, content="\n".join(lines))


_RELATIVE_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}


def _parse_when(s: str) -> float | None:
    s = s.strip().lower()
    if s.startswith("in "):
        parts = s[3:].split()
        if len(parts) == 2:
            try:
                qty = float(parts[0])
            except ValueError:
                return None
            unit = _RELATIVE_UNITS.get(parts[1])
            if unit:
                return time.time() + qty * unit
    try:
        dt = dateparser.parse(s, fuzzy=True)
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None
