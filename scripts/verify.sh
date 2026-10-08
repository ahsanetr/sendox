#!/usr/bin/env bash
# End-to-end localhost verification of everything phase 0.1 claims to deliver.
#
#   ./scripts/verify.sh      (or: make verify)
#
# Runtime checks only — it exercises live services rather than reading code.
# Unit tests are `make test`. Exits non-zero if any required check fails.

set -uo pipefail

API="${API_BASE_URL:-http://localhost:8000}"
WEB="${WEB_BASE_URL:-http://localhost:3000}"
CHROMA="${CHROMA_URL:-http://localhost:8001}"
MJML="${MJML_URL:-http://localhost:7070}"
MAILPIT="${MAILPIT_URL:-http://localhost:8025}"

pass=0 fail=0 skip=0

green()  { printf '\033[32m%s\033[0m' "$1"; }
red()    { printf '\033[31m%s\033[0m' "$1"; }
yellow() { printf '\033[33m%s\033[0m' "$1"; }

ok()      { printf '  %s  %-44s %s\n' "$(green PASS)" "$1" "${2:-}"; pass=$((pass+1)); }
bad()     { printf '  %s  %-44s %s\n' "$(red FAIL)" "$1" "${2:-}"; fail=$((fail+1)); }
skipped() { printf '  %s  %-44s %s\n' "$(yellow SKIP)" "$1" "${2:-}"; skip=$((skip+1)); }

section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# jq is not assumed; python3 is already a hard requirement of this repo.
jsonq() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

printf '\033[1mSendox — localhost verification\033[0m\n'
printf 'api=%s web=%s\n' "$API" "$WEB"

# ---------------------------------------------------------------- API surface
section "API"

if root=$(curl -fsS --max-time 5 "$API/" 2>/dev/null); then
  service=$(printf '%s' "$root" | jsonq 'd["service"]')
  version=$(printf '%s' "$root" | jsonq 'd["version"]')
  [ "$service" = "sendox-api" ] \
    && ok "root endpoint identifies the service" "v$version" \
    || bad "root endpoint identifies the service" "got '$service'"
else
  bad "API reachable at $API" "start it: make dev-api (or make up)"
  printf '\n%s\n' "$(red 'API is down — remaining checks cannot run.')"
  exit 1
fi

if live=$(curl -fsS --max-time 5 "$API/health/live" 2>/dev/null); then
  [ "$(printf '%s' "$live" | jsonq 'd["status"]')" = "ok" ] \
    && ok "liveness probe" \
    || bad "liveness probe"
else
  bad "liveness probe"
fi

# 503 is a valid response body here, so do not use -f.
ready=$(curl -sS --max-time 10 -o /tmp/sendox-ready.json -w '%{http_code}' "$API/health/ready" 2>/dev/null)
overall=$(jsonq 'd["status"]' < /tmp/sendox-ready.json)
if [ "$ready" = "200" ] && [ "$overall" = "ok" ]; then
  ok "readiness: all backing services ok"
else
  bad "readiness: all backing services ok" "HTTP $ready / $overall"
fi

for svc in postgres redis chromadb mjml; do
  state=$(jsonq "d['checks']['$svc']['status']" < /tmp/sendox-ready.json)
  latency=$(jsonq "d['checks']['$svc']['latency_ms']" < /tmp/sendox-ready.json)
  if [ "$state" = "ok" ]; then
    ok "  └ $svc" "${latency} ms"
  else
    detail=$(jsonq "d['checks']['$svc'].get('detail','')" < /tmp/sendox-ready.json)
    bad "  └ $svc" "${detail:0:60}"
  fi
done

# ----------------------------------------------------------- build status API
section "Build status"

if curl -fsS --max-time 5 "$API/status/modules" -o /tmp/sendox-modules.json 2>/dev/null; then
  count=$(jsonq 'len(d["modules"])' < /tmp/sendox-modules.json)
  done_n=$(jsonq 'd["totals"].get("done",0)' < /tmp/sendox-modules.json)
  total=$(jsonq 'd["totals"]["items"]' < /tmp/sendox-modules.json)
  [ "$count" = "25" ] \
    && ok "manifest covers all 25 scope modules" "$done_n/$total items done" \
    || bad "manifest covers all 25 scope modules" "got $count"
else
  bad "manifest endpoint"
fi

# ------------------------------------------------------------ queue round-trip
section "Queue (Redis + Celery worker)"

if accepted=$(curl -fsS --max-time 10 -X POST "$API/dev/tasks/ping?payload=verify" 2>/dev/null); then
  task_id=$(printf '%s' "$accepted" | jsonq 'd["task_id"]')
  echoed=""
  for _ in $(seq 1 25); do
    result=$(curl -fsS --max-time 5 "$API/dev/tasks/$task_id" 2>/dev/null)
    if [ "$(printf '%s' "$result" | jsonq 'd["ready"]')" = "True" ]; then
      echoed=$(printf '%s' "$result" | jsonq 'd["result"]["echo"]')
      break
    fi
    sleep 1
  done
  [ "$echoed" = "verify" ] \
    && ok "task enqueued and executed by a worker" "${task_id:0:8}…" \
    || bad "task enqueued and executed by a worker" "no result; is the worker running?"
else
  bad "task enqueue"
fi

# --------------------------------------------------------------- MJML renderer
section "MJML renderer"

if curl -fsS --max-time 5 "$MJML/health" >/dev/null 2>&1; then
  ok "sidecar health endpoint"
else
  bad "sidecar health endpoint"
fi

if curl -fsS --max-time 20 -X POST "$API/dev/mjml/render" \
     -H 'content-type: application/json' -d '{}' \
     -o /tmp/sendox-render.json 2>/dev/null; then
  rendered_ok=$(jsonq 'd["ok"]' < /tmp/sendox-render.json)
  bytes=$(jsonq 'd["html_bytes"]' < /tmp/sendox-render.json)
  responsive=$(jsonq 'd["responsive"]' < /tmp/sendox-render.json)
  if [ "$rendered_ok" = "True" ] && [ "$responsive" = "True" ]; then
    ok "API compiles a sample email via the sidecar" "$bytes bytes, responsive"
  else
    bad "API compiles a sample email via the sidecar" "ok=$rendered_ok responsive=$responsive"
  fi
else
  bad "API → sidecar render path"
fi

# invalid MJML must come back as structured errors, not a 500
invalid=$(curl -sS --max-time 10 -X POST "$API/dev/mjml/render" \
  -H 'content-type: application/json' \
  -d '{"mjml":"<mjml><mj-body><mj-text>loose</mj-text></mj-body></mjml>"}' 2>/dev/null)
if [ "$(printf '%s' "$invalid" | jsonq 'd["ok"]')" = "False" ] \
   && [ "$(printf '%s' "$invalid" | jsonq 'len(d["errors"])>0')" = "True" ]; then
  ok "invalid MJML reported as errors, not a crash"
else
  bad "invalid MJML reported as errors, not a crash"
fi

# ------------------------------------------------------------- direct services
section "Services reachable directly"

curl -fsS --max-time 5 "$CHROMA/api/v2/heartbeat" >/dev/null 2>&1 \
  && ok "ChromaDB heartbeat (v2 API)" \
  || bad "ChromaDB heartbeat (v2 API)"

if curl -fsS --max-time 5 "$MAILPIT/" >/dev/null 2>&1; then
  ok "Mailpit web UI" "$MAILPIT"
else
  skipped "Mailpit web UI" "Docker-only; not available under make up-native"
fi

# ------------------------------------------------------------------------- web
section "Web dashboard"

if page=$(curl -fsS --max-time 15 "$WEB/" 2>/dev/null); then
  printf '%s' "$page" | grep -q "Internal dev dashboard" \
    && ok "dashboard renders" "$WEB" \
    || bad "dashboard renders" "page served but content unexpected"
else
  skipped "dashboard renders" "not running; start with make dev-web"
fi

# --------------------------------------------------------------------- summary
printf '\n\033[1mSummary\033[0m  %s passed, %s failed, %s skipped\n' \
  "$(green "$pass")" "$([ "$fail" -gt 0 ] && red "$fail" || echo 0)" "$(yellow "$skip")"

if [ "$fail" -gt 0 ]; then
  printf '%s\n' "$(red 'Some checks failed.')"
  exit 1
fi
printf '%s\n' "$(green 'All required checks passed.')"
