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

# ------------------------------------------------- database + tenant isolation
section "Database & tenant isolation"

if curl -fsS --max-time 10 "$API/status/database" -o /tmp/sendox-db.json 2>/dev/null; then
  reachable=$(jsonq 'd["reachable"]' < /tmp/sendox-db.json)
  if [ "$reachable" = "True" ]; then
    revision=$(jsonq 'd["migration_revision"]' < /tmp/sendox-db.json)
    role=$(jsonq 'd["session_role"]' < /tmp/sendox-db.json)
    is_super=$(jsonq 'd["session_is_superuser"]' < /tmp/sendox-db.json)
    enforced=$(jsonq 'd["enforced"]' < /tmp/sendox-db.json)
    scoped=$(jsonq '",".join(d["tenant_scoped_tables"])' < /tmp/sendox-db.json)
    unprotected=$(jsonq '",".join(d["unprotected_tables"])' < /tmp/sendox-db.json)

    [ -n "$revision" ] && [ "$revision" != "None" ] \
      && ok "migrations applied" "revision $revision" \
      || bad "migrations applied" "run make migrate"

    [ "$is_super" = "False" ] \
      && ok "app session is not a superuser" "role=$role" \
      || bad "app session is not a superuser" "RLS is bypassed for superusers!"

    [ -z "$unprotected" ] \
      && ok "every tenant-scoped table has an RLS policy" "$scoped" \
      || bad "every tenant-scoped table has an RLS policy" "unprotected: $unprotected"

    [ "$enforced" = "True" ] \
      && ok "tenant isolation enforced" \
      || bad "tenant isolation enforced"
  else
    bad "database reachable" "$(jsonq 'd["error"]' < /tmp/sendox-db.json)"
  fi
else
  bad "database status endpoint"
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

# ------------------------------------------------ accounts, workspaces, roles
section "Accounts & workspaces (M1)"

STAMP=$(date +%s)
OWNER_EMAIL="verify-owner-$STAMP@example.com"
GUEST_EMAIL="verify-guest-$STAMP@example.com"
PASSWORD="VerifyRun2026"
JAR="/tmp/sendox-verify-jar.txt"
rm -f "$JAR"

reg=$(curl -fsS --max-time 15 -X POST "$API/auth/register" \
  -H 'content-type: application/json' \
  -d "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$PASSWORD\",\"workspace_name\":\"Verify Brand\"}" 2>/dev/null)

if [ -n "$reg" ]; then
  verified=$(printf '%s' "$reg" | jsonq 'd["user"]["email_verified"]')
  vtoken=$(printf '%s' "$reg" | jsonq 'd["dev_verification_token"] or ""')
  [ "$verified" = "False" ] \
    && ok "registration creates an unconfirmed account" \
    || bad "registration creates an unconfirmed account"
else
  bad "registration" "endpoint failed"
  vtoken=""
fi

# The credentials are right but the address is unconfirmed: 403, not 401.
code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -X POST "$API/auth/login" \
  -H 'content-type: application/json' \
  -d "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$PASSWORD\"}" 2>/dev/null)
[ "$code" = "403" ] \
  && ok "sign-in refused until the email is confirmed" \
  || bad "sign-in refused until the email is confirmed" "got HTTP $code"

if [ -n "$vtoken" ]; then
  headers=$(curl -sS --max-time 15 -D - -o /tmp/sendox-verify.json -c "$JAR" \
    -X POST "$API/auth/verify-email" -H 'content-type: application/json' \
    -d "{\"token\":\"$vtoken\"}" 2>/dev/null)

  printf '%s' "$headers" | grep -qi 'set-cookie:.*httponly' \
    && ok "session cookie is httpOnly" \
    || bad "session cookie is httpOnly" "an XSS bug could steal the session"

  # Replaying a consumed link must fail.
  code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -X POST "$API/auth/verify-email" \
    -H 'content-type: application/json' -d "{\"token\":\"$vtoken\"}" 2>/dev/null)
  [ "$code" = "400" ] \
    && ok "a confirmation link works only once" \
    || bad "a confirmation link works only once" "got HTTP $code"

  OWNER_TOKEN=$(jsonq 'd["access_token"]' < /tmp/sendox-verify.json)
else
  bad "email confirmation" "no token returned"
  OWNER_TOKEN=""
fi

if [ -n "$OWNER_TOKEN" ]; then
  auth="Authorization: Bearer $OWNER_TOKEN"
  curl -fsS --max-time 10 "$API/auth/me" -H "$auth" -o /tmp/sendox-me.json 2>/dev/null
  role=$(jsonq 'd["workspaces"][0]["role"] if d["workspaces"] else ""' < /tmp/sendox-me.json)
  WS=$(jsonq 'd["workspaces"][0]["id"] if d["workspaces"] else ""' < /tmp/sendox-me.json)
  [ "$role" = "owner" ] \
    && ok "the creator of a workspace is its owner" \
    || bad "the creator of a workspace is its owner" "role=$role"

  # The cookie alone must authenticate, with no bearer header at all.
  code=$(curl -sS --max-time 10 -b "$JAR" -o /dev/null -w '%{http_code}' "$API/auth/me" 2>/dev/null)
  [ "$code" = "200" ] \
    && ok "the session cookie alone authenticates" \
    || bad "the session cookie alone authenticates" "got HTTP $code"

  # A second account that is not a member must not even learn it exists.
  greg=$(curl -fsS --max-time 15 -X POST "$API/auth/register" \
    -H 'content-type: application/json' \
    -d "{\"email\":\"$GUEST_EMAIL\",\"password\":\"$PASSWORD\"}" 2>/dev/null)
  gtoken=$(printf '%s' "$greg" | jsonq 'd["dev_verification_token"] or ""')
  GUEST_TOKEN=$(curl -fsS --max-time 15 -X POST "$API/auth/verify-email" \
    -H 'content-type: application/json' -d "{\"token\":\"$gtoken\"}" 2>/dev/null | jsonq 'd["access_token"]')

  code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "$API/workspaces/$WS" \
    -H "Authorization: Bearer $GUEST_TOKEN" 2>/dev/null)
  [ "$code" = "404" ] \
    && ok "a non-member cannot see a workspace exists" \
    || bad "a non-member cannot see a workspace exists" "got HTTP $code"

  # Invite the guest as a viewer, then confirm the role is actually enforced.
  itoken=$(curl -fsS --max-time 15 -X POST "$API/workspaces/$WS/invitations" -H "$auth" \
    -H 'content-type: application/json' \
    -d "{\"email\":\"$GUEST_EMAIL\",\"role\":\"viewer\"}" 2>/dev/null \
    | jsonq 'd["dev_invitation_token"] or ""')
  curl -fsS --max-time 10 -X POST "$API/invitations/accept" \
    -H "Authorization: Bearer $GUEST_TOKEN" -H 'content-type: application/json' \
    -d "{\"token\":\"$itoken\"}" >/dev/null 2>&1 \
    && ok "an invitation grants access" \
    || bad "an invitation grants access"

  code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -X PATCH "$API/workspaces/$WS" \
    -H "Authorization: Bearer $GUEST_TOKEN" -H 'content-type: application/json' \
    -d '{"name":"Hijacked"}' 2>/dev/null)
  [ "$code" = "403" ] \
    && ok "a viewer cannot change workspace settings" \
    || bad "a viewer cannot change workspace settings" "got HTTP $code"

  # A workspace must never be left without an owner.
  OWNER_ID=$(jsonq 'd["user"]["id"]' < /tmp/sendox-me.json)
  code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' \
    -X PATCH "$API/workspaces/$WS/members/$OWNER_ID" -H "$auth" \
    -H 'content-type: application/json' -d '{"role":"admin"}' 2>/dev/null)
  [ "$code" = "409" ] \
    && ok "a workspace cannot lose its last owner" \
    || bad "a workspace cannot lose its last owner" "got HTTP $code"

  entries=$(curl -fsS --max-time 10 "$API/workspaces/$WS/audit" -H "$auth" 2>/dev/null \
    | jsonq 'len(d)')
  [ "${entries:-0}" -ge 3 ] \
    && ok "workspace activity is recorded" "$entries entries" \
    || bad "workspace activity is recorded" "only ${entries:-0} entries"

  # Leave the database as it was found.
  curl -sS --max-time 15 -X DELETE "$API/auth/me" -H "Authorization: Bearer $GUEST_TOKEN" >/dev/null 2>&1
  curl -sS --max-time 15 -X DELETE "$API/auth/me" -H "$auth" >/dev/null 2>&1
  code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "$API/auth/me" -H "$auth" 2>/dev/null)
  [ "$code" = "401" ] \
    && ok "a deleted account can no longer be used" \
    || bad "a deleted account can no longer be used" "got HTTP $code"
fi
rm -f "$JAR"

# ------------------------------------------------- vector store (brand knowledge)
section "Brand knowledge vector store"

# First run in a fresh container downloads the ~80MB ONNX embedding model.
if curl -fsS --max-time 180 -X POST "$API/dev/vectors/seed" -o /tmp/sendox-seed.json 2>/dev/null; then
  written=$(jsonq 'd["chunks_written"]' < /tmp/sendox-seed.json)
  dims=$(jsonq 'd["dimensions"]' < /tmp/sendox-seed.json)
  ok "sample brand content embedded" "$written chunks, ${dims}d"
else
  bad "sample brand content embedded"
fi

# Shares no words with the source text, so a keyword match cannot explain a hit.
if curl -fsS --max-time 30 -X POST "$API/dev/vectors/query" \
     -H 'content-type: application/json' \
     -d '{"query":"can I send something back if it does not fit","top_k":1}' \
     -o /tmp/sendox-query.json 2>/dev/null; then
  top_id=$(jsonq 'd["matches"][0]["id"] if d["matches"] else ""' < /tmp/sendox-query.json)
  sim=$(jsonq 'd["matches"][0]["similarity"] if d["matches"] else 0' < /tmp/sendox-query.json)
  [ "$top_id" = "shipping" ] \
    && ok "semantic search retrieves by meaning" "top hit '$top_id' @ $sim" \
    || bad "semantic search retrieves by meaning" "expected 'shipping', got '$top_id'"
else
  bad "semantic search"
fi

# ------------------------------------------------------------------------- AI
section "Claude API"

if curl -fsS --max-time 10 "$API/dev/ai/status" -o /tmp/sendox-ai.json 2>/dev/null; then
  configured=$(jsonq 'd["configured"]' < /tmp/sendox-ai.json)
  model=$(jsonq 'd["model"]' < /tmp/sendox-ai.json)
  if [ "$configured" = "True" ]; then
    if reply=$(curl -fsS --max-time 60 -X POST "$API/dev/ai/ping" 2>/dev/null); then
      ok "Claude round-trip" "$(printf '%s' "$reply" | jsonq 'd["model"]')"
    else
      bad "Claude round-trip" "key present but the call failed"
    fi
  else
    skipped "Claude round-trip" "ANTHROPIC_API_KEY not set (model would be $model)"
  fi
else
  bad "Claude status endpoint"
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
