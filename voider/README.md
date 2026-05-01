# voider

A local AI agent. Local LLM, local OS access, web search the only thing that goes outside.
Ask-once / always-allow permissions remembered per tool + target.

> Status: v0 scaffold. Windows-first.

## What it can do (v0)

- Chat with a locally-hosted LLM via [Ollama](https://ollama.com/).
- Tools the agent can call (each gated by your permission):
  - `notes_save` / `notes_list` / `notes_read` — markdown notes on disk
  - `web_search` — DuckDuckGo (no API key)
  - `web_fetch` — fetch + readable-text a URL
  - `reminder_set` / `reminder_list` — persistent reminders
- A small browser UI for chat and permission prompts.

Gmail, calendar, deeper OS automation come next — same tool/permission shape.

## Setup (Windows)

Prereqs: Python 3.11+, PowerShell 5+.

```powershell
git clone <this-repo>
cd voider
./setup.ps1
```

`setup.ps1` will:
1. Check for [Ollama](https://ollama.com/download) (prompt to install if missing).
2. Show you a curated list of locally-hostable models with sizes.
3. Pull the model you pick.
4. Create a Python venv + install deps.
5. Write `config.local.json` with your chosen model.

Run it:

```powershell
./run.ps1
```

Then open http://localhost:8765 in your browser.

## Layout

```
voider/
  setup.ps1            # Windows installer / model picker
  run.ps1              # Launch the server
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

State lives at `%APPDATA%\voider\permissions.json`. Delete the file to reset.

## Roadmap

- Gmail (OAuth, read + draft)
- Calendar (Google + Outlook)
- File system browse/edit beyond notes
- Local app launchers (start/stop processes)
- Multi-step plans with explicit approval gates
- Voice in/out
