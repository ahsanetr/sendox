#!/usr/bin/env bash
# Boot the backing services natively, without Docker.
#
# Docker Desktop is the supported path (`make up`) because it pins exact service
# versions. This script exists because the dev machine has Homebrew Postgres and
# Redis already, and waiting on a Docker install should not block development.
#
# Caveat: Homebrew Postgres is 15, docker-compose pins 16. Everything we use
# (including row-level security in phase 0.2) works on both, but production
# parity comes from the compose path.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_BIN="$(brew --prefix postgresql@15 2>/dev/null)/bin"
CHROMA_DATA="$REPO_ROOT/.chroma-data"
LOG_DIR="$REPO_ROOT/.native-logs"

mkdir -p "$CHROMA_DATA" "$LOG_DIR"

say() { printf '\033[36m==>\033[0m %s\n' "$1"; }

# --- Postgres --------------------------------------------------------------
say "Postgres"
if ! "$PG_BIN/pg_isready" -q -h 127.0.0.1 -p 5432 2>/dev/null; then
  brew services start postgresql@15 >/dev/null
  for _ in $(seq 1 30); do
    "$PG_BIN/pg_isready" -q -h 127.0.0.1 -p 5432 2>/dev/null && break
    sleep 1
  done
fi

# Idempotent: role and database are created only if absent.
#
# CREATEROLE matters: the initial migration creates the non-superuser `sendox_app`
# role that row-level security depends on, and grants it to the connecting role.
# Under Docker the connecting role is the bootstrap superuser and can do both; a
# plain Homebrew role cannot, so it is granted CREATEROLE here instead of giving
# the application superuser (which would disable RLS entirely).
"$PG_BIN/psql" -d postgres -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sendox') THEN
    CREATE ROLE sendox LOGIN PASSWORD 'sendox' CREATEROLE;
  ELSE
    ALTER ROLE sendox CREATEROLE;
  END IF;
END
$$;
SQL
if ! "$PG_BIN/psql" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='sendox'" | grep -q 1; then
  "$PG_BIN/createdb" -O sendox sendox
fi
echo "    ready on 5432 (db=sendox, user=sendox)"

# --- Redis -----------------------------------------------------------------
say "Redis"
if ! "$(brew --prefix redis)/bin/redis-cli" ping >/dev/null 2>&1; then
  brew services start redis >/dev/null
  sleep 2
fi
echo "    ready on 6379"

# --- ChromaDB --------------------------------------------------------------
say "ChromaDB"
if curl -fsS http://localhost:8001/api/v2/heartbeat >/dev/null 2>&1; then
  echo "    already running on 8001"
else
  (cd "$REPO_ROOT/apps/api" && nohup uv run chroma run --path "$CHROMA_DATA" --port 8001 \
    > "$LOG_DIR/chroma.log" 2>&1 &)
  for _ in $(seq 1 40); do
    curl -fsS http://localhost:8001/api/v2/heartbeat >/dev/null 2>&1 && break
    sleep 1
  done
  echo "    ready on 8001 (log: .native-logs/chroma.log)"
fi

# --- MJML sidecar ----------------------------------------------------------
say "MJML renderer"
if curl -fsS http://localhost:7070/health >/dev/null 2>&1; then
  echo "    already running on 7070"
else
  (cd "$REPO_ROOT/services/mjml" && nohup node server.js > "$LOG_DIR/mjml.log" 2>&1 &)
  for _ in $(seq 1 20); do
    curl -fsS http://localhost:7070/health >/dev/null 2>&1 && break
    sleep 1
  done
  echo "    ready on 7070 (log: .native-logs/mjml.log)"
fi

# --- Schema ----------------------------------------------------------------
say "Migrations"
(cd "$REPO_ROOT/apps/api" && uv run alembic upgrade head >/dev/null 2>&1) \
  && echo "    schema at head" \
  || echo "    FAILED — run: make migrate"

cat <<'NEXT'

All backing services up. Mailpit is not available natively — install Docker for
local mail capture, or point SMTP at a real sandbox when phase 1.10 needs it.

Next:
  make dev-api      # API on http://localhost:8000
  make dev-worker   # Celery worker (threads pool on macOS)
  make health       # readiness report, expect all four checks "ok"
NEXT
