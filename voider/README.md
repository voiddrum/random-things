# voider

A local AI agent. Local LLM, local OS access, web search the only thing that goes outside.
Ask-once / always-allow permissions remembered per tool + target.

> Status: v0 scaffold. Windows-first, with WSL / Linux supported via `setup.sh`.

## What it can do (v0)

- Chat with a locally-hosted LLM via [Ollama](https://ollama.com/).
- Tools the agent can call (each gated by your permission):
  - `notes_save` / `notes_list` / `notes_read` — markdown notes on disk
  - `web_search` — DuckDuckGo (no API key)
  - `web_fetch` — fetch + readable-text a URL
  - `reminder_set` / `reminder_list` — persistent reminders
- A small browser UI for chat and permission prompts.

Gmail, calendar, deeper OS automation come next — same tool/permission shape.

## Setup

### Windows (PowerShell)

Prereqs: Python 3.11+, PowerShell 5+.

```powershell
git clone <this-repo>
cd voider
./setup.ps1
./run.ps1
```

### WSL / Linux (bash)

Prereqs: Python 3.10+ (`sudo apt install python3 python3-venv python3-pip`), `curl`.

```bash
git clone <this-repo>
cd voider
./setup.sh
./run.sh
```

Then open http://localhost:8765 — from WSL, this works in your Windows browser
since WSL2 forwards localhost.

#### Where Ollama runs (WSL)

`setup.sh` auto-detects an Ollama endpoint in this order:

1. `localhost:11434` (works if Ollama runs in WSL, or on Windows with WSL2
   mirrored networking).
2. The Windows host's IP from `ip route` (works if Ollama runs on Windows
   with `OLLAMA_HOST=0.0.0.0` so it accepts non-loopback connections).
3. Offers to install Ollama inside WSL via the official installer.

If you already run Ollama on Windows and want to share it with WSL:

```powershell
# In Windows (as your user), set this env var permanently and restart Ollama:
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0", "User")
```

#### Binary compatibility note

The Python venv contains compiled extensions (`uvloop`, `httptools`,
`watchfiles`) that are platform-specific — Linux `.so` files won't run from
Windows and vice versa. Both setup scripts detect a foreign `.venv` in the
checkout and recreate it for the current platform, so you can flip between
PowerShell and WSL on the same clone safely.

What that means in practice: if you ever switch which side you run from,
the next `setup.{ps1,sh}` rebuilds the venv. State (notes, permissions,
reminders) lives in the user state dir per-platform, so they're independent
between Windows-native and WSL.

## Layout

```
voider/
  setup.ps1 / setup.sh # Installer + model picker (Windows / WSL+Linux)
  run.ps1   / run.sh   # Launch the server
  requirements.txt
  voider/              # Python package
    __main__.py        # python -m voider
    server.py          # FastAPI + WebSocket
    agent.py           # Tool-calling loop
    llm.py             # Ollama client
    permissions.py     # JSON ledger of allow/deny decisions
    config.py
    tools/             # Each tool is one file
    web/               # Chat UI (static)
```

## Permissions

Every tool call is one of:
- pre-approved (`allow_always` recorded for that tool+target)
- pre-denied (`deny_always` recorded)
- prompted in the UI: **Allow once / Allow always / Deny once / Deny always**

State lives at `%APPDATA%\voider\permissions.json` on Windows, or
`~/.config/voider/permissions.json` on Linux/WSL. Delete the file to reset.

## Roadmap

- Gmail (OAuth, read + draft)
- Calendar (Google + Outlook)
- File system browse/edit beyond notes
- Local app launchers (start/stop processes)
- Multi-step plans with explicit approval gates
- Voice in/out
