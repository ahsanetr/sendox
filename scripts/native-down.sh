#!/usr/bin/env bash
# Stop the natively-run backing services started by scripts/native-up.sh.
# Leaves Homebrew Postgres and Redis running; they are shared machine services.

set -uo pipefail

say() { printf '\033[36m==>\033[0m %s\n' "$1"; }

say "Stopping ChromaDB"
pkill -f "chroma run --path" 2>/dev/null && echo "    stopped" || echo "    not running"

say "Stopping MJML renderer"
pkill -f "node server.js" 2>/dev/null && echo "    stopped" || echo "    not running"

cat <<'NOTE'

Homebrew Postgres and Redis left running (shared machine services). Stop them with:
  brew services stop postgresql@15
  brew services stop redis
NOTE
