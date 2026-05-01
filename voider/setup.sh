#!/usr/bin/env bash
# voider — Linux / WSL setup
# - Detects WSL and figures out where Ollama lives (Windows host vs inside WSL)
# - Lets you pick a model from a curated list
# - Creates a Linux Python venv (separate from any Windows .venv on the same checkout)
# - Writes config.local.json
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

step() { printf "\n\033[36m==> %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32mok:\033[0m %s\n" "$*"; }
warn() { printf "  \033[33mwarn:\033[0m %s\n" "$*"; }
err()  { printf "  \033[31merr:\033[0m %s\n" "$*" >&2; }

# --- Detect WSL ------------------------------------------------------------
IS_WSL=false
if grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease 2>/dev/null \
   || [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
    IS_WSL=true
fi
$IS_WSL && step "Detected WSL (${WSL_DISTRO_NAME:-unknown})" || step "Detected Linux"

# --- Locate Ollama ---------------------------------------------------------
step "Looking for an Ollama endpoint"
OLLAMA_URL=""
candidates=("http://localhost:11434" "http://127.0.0.1:11434")

if $IS_WSL; then
    # In WSL2 NAT mode, Windows-host Ollama is reachable on the default-gateway IP.
    # (In mirrored mode, localhost works directly — the loop above covers it.)
    WIN_HOST="$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}')"
    if [[ -n "$WIN_HOST" ]]; then
        candidates+=("http://${WIN_HOST}:11434")
    fi
fi

for url in "${candidates[@]}"; do
    if curl -sf --max-time 2 "$url/api/tags" > /dev/null 2>&1; then
        OLLAMA_URL="$url"
        ok "Reached Ollama at $url"
        break
    fi
done

if [[ -z "$OLLAMA_URL" ]]; then
    echo
    if $IS_WSL; then
        cat <<EOF
Couldn't reach Ollama. Two options:

  1) Use the Ollama you already run on Windows.
       - Set OLLAMA_HOST=0.0.0.0 in Windows env vars (so WSL can reach it
         across the NAT bridge), restart Ollama, then re-run setup.sh.

  2) Install Ollama inside WSL (Linux-native binary).
       curl -fsSL https://ollama.com/install.sh | sh

EOF
        read -rp "Install Ollama inside WSL now? [y/N] " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            curl -fsSL https://ollama.com/install.sh | sh
            # systemd may not be enabled in WSL — start it manually.
            if ! pgrep -x ollama >/dev/null 2>&1; then
                nohup ollama serve >/tmp/voider-ollama.log 2>&1 &
                sleep 3
            fi
            for i in 1 2 3 4 5; do
                if curl -sf --max-time 2 http://localhost:11434/api/tags >/dev/null; then
                    OLLAMA_URL="http://localhost:11434"; break
                fi
                sleep 1
            done
        fi
    else
        cat <<EOF
Couldn't reach Ollama. Install it:
    curl -fsSL https://ollama.com/install.sh | sh
Then re-run setup.sh.
EOF
    fi
fi

if [[ -z "$OLLAMA_URL" ]]; then
    err "Ollama still not reachable. Aborting."
    exit 1
fi

# --- Model picker ----------------------------------------------------------
# Curated list. Each line: <tag>|<size>|<notes>
MODELS=(
    "qwen2.5:7b|~4.7 GB|recommended — strong tool use, balanced"
    "qwen2.5:3b|~1.9 GB|small + fast, decent tool use"
    "qwen2.5:14b|~9 GB|higher quality, needs ~16 GB RAM / decent GPU"
    "llama3.1:8b|~4.7 GB|popular general model, good tool use"
    "llama3.2:3b|~2 GB|small + fast"
    "mistral:7b|~4.1 GB|solid baseline"
    "phi3.5:3.8b|~2.2 GB|small, good reasoning for size"
)

step "Already-pulled models"
INSTALLED="$(curl -sf "$OLLAMA_URL/api/tags" | python3 -c '
import json, sys
data = json.load(sys.stdin)
for m in data.get("models", []):
    print(m["name"])
' 2>/dev/null || true)"
if [[ -n "$INSTALLED" ]]; then
    echo "$INSTALLED" | sed 's/^/  - /'
else
    echo "  (none yet)"
fi

step "Pick a model"
i=1
for line in "${MODELS[@]}"; do
    IFS='|' read -r tag size notes <<<"$line"
    flag=""
    if echo "$INSTALLED" | grep -qx "$tag"; then flag="[installed]"; fi
    printf "  %2d) %-16s %-9s %s %s\n" "$i" "$tag" "$size" "$notes" "$flag"
    i=$((i+1))
done
printf "  %2d) custom model name…\n" "$i"

read -rp "Enter number: " choice
SELECTED=""
if [[ "$choice" =~ ^[0-9]+$ ]]; then
    n="$choice"
    if (( n >= 1 && n <= ${#MODELS[@]} )); then
        IFS='|' read -r SELECTED _ _ <<<"${MODELS[$((n-1))]}"
    elif (( n == ${#MODELS[@]} + 1 )); then
        read -rp "Enter ollama model tag (e.g. mistral-nemo:12b): " SELECTED
    fi
fi
if [[ -z "$SELECTED" ]]; then
    err "Invalid choice."
    exit 1
fi

if ! echo "$INSTALLED" | grep -qx "$SELECTED"; then
    step "Pulling $SELECTED via $OLLAMA_URL (this can take a while)"
    # Use the API to pull, since `ollama` CLI may not exist if the daemon is on Windows.
    curl -fsSL -X POST "$OLLAMA_URL/api/pull" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$SELECTED\",\"stream\":false}" \
        --no-buffer
    echo
fi
ok "Model ready: $SELECTED"

# --- Python venv -----------------------------------------------------------
step "Setting up Python virtual environment"
PY="$(command -v python3 || true)"
if [[ -z "$PY" ]]; then
    err "python3 not found. On Ubuntu/Debian:  sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PY_VER="$($PY -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
PY_OK="$($PY -c 'import sys; print(int(sys.version_info >= (3,10)))')"
if [[ "$PY_OK" != "1" ]]; then
    err "Python 3.10+ required (found $PY_VER)."
    exit 1
fi
ok "Using $PY ($PY_VER)"

# Guard against a Windows .venv left in the same checkout (shared via /mnt/c).
if [[ -d ".venv" && ! -x ".venv/bin/python" ]]; then
    warn "Existing .venv has no Linux interpreter — looks like a Windows venv. Recreating."
    rm -rf .venv
fi

if [[ ! -x ".venv/bin/python" ]]; then
    "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
ok "Dependencies installed (Linux wheels)."

# --- Write config ----------------------------------------------------------
step "Writing config.local.json"
.venv/bin/python - <<PY
import json, pathlib
cfg = {
    "model": "$SELECTED",
    "ollama_url": "$OLLAMA_URL",
    "host": "127.0.0.1",
    "port": 8765,
}
pathlib.Path("config.local.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
PY
ok "Wrote config.local.json"

cat <<EOF

All set. Start voider with:
    ./run.sh
Then open http://localhost:8765 in your $($IS_WSL && echo "Windows browser" || echo "browser").
EOF
