from __future__ import annotations

from voider.config import Config
from voider.tools.base import Tool
from voider.tools.notes import NotesListTool, NotesReadTool, NotesSaveTool
from voider.tools.reminders import ReminderListTool, ReminderSetTool, ReminderStore
from voider.tools.web_fetch import WebFetchTool
from voider.tools.web_search import WebSearchTool


def build_tools(cfg: Config, reminders: ReminderStore) -> list[Tool]:
    return [
        NotesSaveTool(cfg.notes_dir),
        NotesListTool(cfg.notes_dir),
        NotesReadTool(cfg.notes_dir),
        WebSearchTool(),
        WebFetchTool(),
        ReminderSetTool(reminders),
        ReminderListTool(reminders),
    ]


__all__ = ["Tool", "build_tools", "ReminderStore"]
