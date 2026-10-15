#!/usr/bin/env bash
# Start the local AXK Network Frappe stack (web, workers, socketio, redis).
# Opens at http://axk.localhost:8000  (login: Administrator / SITE_ADMIN_PASSWORD in .env.local)
set -euo pipefail

BENCH="${AXK_BENCH:-$HOME/Documents/axk-bench}"
export PATH="$HOME/.venvs/bench/bin:/opt/homebrew/opt/python@3.11/bin:/opt/homebrew/opt/mariadb@10.11/bin:/opt/homebrew/bin:$PATH"

brew services start mariadb@10.11 >/dev/null 2>&1 || true

# Already running (e.g. started in another terminal): don't start a second copy, whose
# redis and web ports would collide and take the whole stack down.
if curl -s -m 3 -H "Host: axk.localhost" http://127.0.0.1:8000/api/method/ping | grep -q pong; then
  echo "AXK is already running at http://localhost:8000/trade"
  echo "To restart it: stop the running copy (Ctrl+C in its terminal, or: pkill -f 'honcho start'), then run make run-frappe again."
  exit 0
fi

cd "$BENCH"
exec bench start
