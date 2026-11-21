#!/usr/bin/env bash
# Ember Council quick install for macOS / Linux. Run:  bash install.sh
# Checks Python 3.10+, optionally installs the extras (pypdf, keyring), detects Ollama, starts the server and opens the browser.
# Options: --extras (install without asking)  --no-extras  --no-start (only check)  --port 8000
set -u
cd "$(dirname "$0")"
EXTRAS=ask; START=1; PORT=8000
while [ $# -gt 0 ]; do case "$1" in --extras) EXTRAS=yes;; --no-extras) EXTRAS=no;; --no-start) START=0;; --port) PORT="${2:-8000}"; shift;; esac; shift; done

# 1. Python 3.10+ (run it and read the real version; do not trust a name on PATH)
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer was not found."
  echo "Install it (macOS: brew install python; Ubuntu/Debian: sudo apt install python3), then run this again."
  exit 1
fi
echo "Python OK: $($PY --version 2>&1)"

# 2. Optional extras. The core app needs nothing beyond Python.
if [ "$EXTRAS" = ask ] && [ -t 0 ]; then
  read -r -p "Install optional extras? pypdf lets Company Brain read PDFs; keyring keeps email passwords in your OS keychain [y/N] " a
  case "$a" in [yY]*) EXTRAS=yes;; *) EXTRAS=no;; esac
fi
if [ "$EXTRAS" = yes ]; then
  "$PY" -m pip install --user --disable-pip-version-check pypdf keyring || echo "Could not install the extras. Ember Council still works without them."
fi

# 3. Ollama (a local engine keeps company data on this machine; recommended for regulated data)
MODEL=""
if TAGS=$(curl -fsS --max-time 2 http://localhost:11434/api/tags 2>/dev/null); then
  MODEL=$(printf '%s' "$TAGS" | "$PY" -c 'import json,sys; m=[x["name"] for x in json.load(sys.stdin).get("models") or [] if "embed" not in x["name"]]; print(m[0] if m else "")' 2>/dev/null)
  if [ -n "$MODEL" ]; then echo "Ollama is running (model: $MODEL)"; else echo "Ollama is running, but no model is installed: run  ollama pull llama3.2"; fi
elif command -v ollama >/dev/null 2>&1; then echo "Ollama is installed but not running. Start it, then run  ollama pull llama3.2"
else echo "Ollama not found. For private, offline use install it from https://ollama.com and run  ollama pull llama3.2 (optional)."; fi
if [ -n "$MODEL" ] && [ -z "${OPENROUTER_API_KEY:-}" ] && [ -z "${LLM_BASE_URL:-}" ]; then
  export LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL="$MODEL" LLM_API_KEY=ollama; echo "Using your local Ollama model for this session."
elif [ -z "${OPENROUTER_API_KEY:-}" ] && [ -z "${LLM_BASE_URL:-}" ]; then
  echo "No model key found. Saved demo questions still replay for free. To ask new questions set OPENROUTER_API_KEY or use Ollama."
fi

# 4. Pick a free port, self-check, start the server, open the browser
busy() { "$PY" -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('127.0.0.1', $1)) == 0 else 1)"; }
n=0; while busy "$PORT" && [ $n -lt 20 ]; do PORT=$((PORT + 1)); n=$((n + 1)); done
export PORT
echo "Self-check..."
"$PY" server.py --selftest | tail -1 || { echo "The self-test failed. See the messages above."; exit 1; }
[ "$START" = 1 ] || { echo "Checks passed (not starting the server: --no-start)."; exit 0; }
URL="http://127.0.0.1:$PORT"; echo "Starting Ember Council at $URL  (press Ctrl+C to stop)"
( sleep 2; if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"; fi ) >/dev/null 2>&1 &
exec "$PY" server.py
