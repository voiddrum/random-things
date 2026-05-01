#!/usr/bin/env bash
# voider — launch the server (Linux / WSL).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Linux venv not found. Run ./setup.sh first." >&2
    exit 1
fi

# Best-effort: if Ollama is installed locally and not running, start it.
# (If voider is configured to talk to Ollama on the Windows host, this is a no-op.)
if command -v ollama >/dev/null 2>&1; then
    if ! curl -sf --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Starting local Ollama..."
        nohup ollama serve >/tmp/voider-ollama.log 2>&1 &
        sleep 2
    fi
fi

exec .venv/bin/python -m voider
