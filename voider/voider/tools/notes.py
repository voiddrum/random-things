from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from voider.tools.base import Tool, ToolResult

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(s: str) -> str:
    s = s.strip().lower().replace(" ", "-")
    s = _SLUG_RE.sub("-", s).strip("-")
    return s[:60] or "note"


def _safe_path(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise ValueError("note path escapes notes directory")
    return candidate


class NotesSaveTool(Tool):
    name = "notes_save"
    description = "Save a markdown note to the local notes folder. Returns the file path."
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title — used for filename."},
            "body": {"type": "string", "description": "Note body in markdown."},
        },
        "required": ["title", "body"],
    }

    def __init__(self, notes_dir: Path) -> None:
        self.notes_dir = notes_dir

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        title = str(arguments.get("title", "")).strip()
        body = str(arguments.get("body", ""))
        if not title:
            return ToolResult(ok=False, content="title is required")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{stamp}-{_slugify(title)}.md"
        path = _safe_path(self.notes_dir, filename)
        path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        return ToolResult(
            ok=True,
            content=f"Saved note: {path.name}",
            data={"path": str(path)},
        )


class NotesListTool(Tool):
    name = "notes_list"
    description = "List existing notes (filenames + first line)."
    parameters = {"type": "object", "properties": {}}

    def __init__(self, notes_dir: Path) -> None:
        self.notes_dir = notes_dir

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        if not self.notes_dir.exists():
            return ToolResult(ok=True, content="No notes yet.")
        entries = []
        for p in sorted(self.notes_dir.glob("*.md"), reverse=True)[:50]:
            first_line = ""
            try:
                with p.open("r", encoding="utf-8") as fh:
                    first_line = fh.readline().strip().lstrip("# ").strip()
            except OSError:
                pass
            entries.append(f"- {p.name} — {first_line}")
        if not entries:
            return ToolResult(ok=True, content="No notes yet.")
        return ToolResult(ok=True, content="\n".join(entries))


class NotesReadTool(Tool):
    name = "notes_read"
    description = "Read the contents of a note by filename."
    parameters = {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Filename inside the notes dir, e.g. 20250501-120000-foo.md"},
        },
        "required": ["filename"],
    }

    def __init__(self, notes_dir: Path) -> None:
        self.notes_dir = notes_dir

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        name = str(arguments.get("filename", "")).strip()
        if not name:
            return ToolResult(ok=False, content="filename is required")
        try:
            path = _safe_path(self.notes_dir, name)
        except ValueError as e:
            return ToolResult(ok=False, content=str(e))
        if not path.exists():
            return ToolResult(ok=False, content=f"Not found: {name}")
        return ToolResult(ok=True, content=path.read_text(encoding="utf-8"))
