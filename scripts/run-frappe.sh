#!/usr/bin/env bash
# Start the local AXK Network Frappe stack (web, workers, socketio, redis).
# Opens at http://axk.localhost:8000  (login: Administrator / SITE_ADMIN_PASSWORD in .env.local)
set -euo pipefail

BENCH="${AXK_BENCH:-$HOME/Documents/axk-bench}"
export PATH="$HOME/.venvs/bench/bin:/opt/homebrew/opt/python@3.11/bin:/opt/homebrew/opt/mariadb@10.11/bin:/opt/homebrew/bin:$PATH"

brew services start mariadb@10.11 >/dev/null 2>&1 || true

cd "$BENCH"
exec bench start
