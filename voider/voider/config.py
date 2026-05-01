"""App config + per-user state directory.

Repo-level defaults live in `config.local.json` next to setup.ps1 (chosen model,
host, port). User state (permissions, notes, reminders) lives under
`%APPDATA%\\voider` on Windows or `~/.config/voider` elsewhere.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_PATH = REPO_ROOT / "config.local.json"


def user_state_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "voider"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "voider"
    return Path.home() / ".config" / "voider"


@dataclass
class Config:
    model: str = "qwen2.5:7b"
    ollama_url: str = "http://localhost:11434"
    host: str = "127.0.0.1"
    port: int = 8765
    web_search_provider: str = "duckduckgo"

    notes_dir: Path = field(default_factory=lambda: user_state_dir() / "notes")
    permissions_path: Path = field(default_factory=lambda: user_state_dir() / "permissions.json")
    reminders_path: Path = field(default_factory=lambda: user_state_dir() / "reminders.json")


def load_config() -> Config:
    cfg = Config()
    if LOCAL_CONFIG_PATH.exists():
        data = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
        for key in ("model", "ollama_url", "host", "port", "web_search_provider"):
            if key in data:
                setattr(cfg, key, data[key])
    cfg.notes_dir.mkdir(parents=True, exist_ok=True)
    cfg.permissions_path.parent.mkdir(parents=True, exist_ok=True)
    return cfg
