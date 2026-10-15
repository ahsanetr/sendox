#!/usr/bin/env bash
# Start a public HTTPS tunnel to the local API and propagate its URL everywhere
# that needs it.
#
# Shopify will not redirect OAuth to localhost, so development needs a public
# origin. There are two ways to get one, and this script prefers the good one.
#
# NAMED TUNNEL (preferred). Set TUNNEL_HOSTNAME in .env, e.g.
# api.sendox.online, having run once:
#
#     cloudflared tunnel login
#     cloudflared tunnel create sendox
#     cloudflared tunnel route dns sendox api.sendox.online
#
# The hostname is then permanent. It survives restarts and reboots, which means
# `shopify app deploy` is run once and never again — the single biggest source
# of lost time on this project so far.
#
# QUICK TUNNEL (fallback). No account needed, but the hostname is random, the
# tunnel is revoked after a while, and every restart invalidates the last
# Shopify deploy. Fine for a first try, painful as a habit.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_ROOT/.native-logs"
LOG="$LOG_DIR/tunnel.log"
mkdir -p "$LOG_DIR"

say() { printf '\033[36m==>\033[0m %s\n' "$1"; }

say "Stopping any previous tunnel"
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1

# The API reads PUBLIC_BASE_URL once, at startup. An API still running from
# before this script rewrites .env therefore keeps sending the previous
# tunnel's callback URL, and Shopify answers "the redirect_uri is not
# whitelisted" — which reads like a Shopify configuration problem and is not
# one. Worse, the stale process holds port 8000, so `make dev-api` fails to
# bind and the stale one survives. Stop it here so that cannot happen.
if pkill -f "uvicorn sendox_api" 2>/dev/null; then
  say "Stopped the running API — it was holding the previous URL"
  sleep 1
fi

# A named tunnel is configured when TUNNEL_HOSTNAME is set and cloudflared has
# a tunnel of that name. Both must hold: the hostname alone would start a
# tunnel that routes nowhere.
TUNNEL_NAME="${TUNNEL_NAME:-sendox}"
HOSTNAME_FROM_ENV=$(grep -E "^TUNNEL_HOSTNAME=" "$REPO_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)

NAMED=0
if [ -n "$HOSTNAME_FROM_ENV" ] && cloudflared tunnel info "$TUNNEL_NAME" >/dev/null 2>&1; then
  NAMED=1
fi

if [ "$NAMED" = "1" ]; then
  URL="https://$HOSTNAME_FROM_ENV"
  say "Named tunnel '$TUNNEL_NAME' -> $URL"
  nohup cloudflared tunnel run --url http://localhost:8000 "$TUNNEL_NAME" > "$LOG" 2>&1 &
  # Nothing to parse: the hostname is known in advance, which is the point.
  sleep 3
else
  if [ -n "$HOSTNAME_FROM_ENV" ]; then
    say "TUNNEL_HOSTNAME is set but no cloudflared tunnel named '$TUNNEL_NAME' exists."
    say "Falling back to a quick tunnel. See the header of this script to fix that."
  fi
  # Cloudflare's quick-tunnel endpoint is a free shared service and is
  # sometimes slow enough that cloudflared's own client timeout fires first
  # ("context deadline exceeded"). Measured at ~20s from here on a bad day.
  # That is transient, so retry the launch rather than treating one slow
  # request as a failure.
  say "Starting a quick tunnel to localhost:8000"
  ATTEMPT=1

  # `api.trycloudflare.com` is cloudflared's own control endpoint and appears
  # in the log both normally and inside the error raised when the quick-tunnel
  # request times out. Matching it produced a config pointing at an address
  # that was never a tunnel, which is worse than failing: everything downstream
  # looked configured. Exclude it by name.
  URL=""
  while [ "$ATTEMPT" -le 4 ] && [ -z "$URL" ]; do
    : > "$LOG"
    nohup cloudflared tunnel --url http://localhost:8000 > "$LOG" 2>&1 &

    for _ in $(seq 1 20); do
      URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG" 2>/dev/null \
              | grep -v "^https://api\.trycloudflare\.com$" | head -1 || true)
      [ -n "$URL" ] && break
      grep -q "failed to request quick Tunnel" "$LOG" 2>/dev/null && break
      sleep 2
    done

    if [ -z "$URL" ]; then
      say "Attempt $ATTEMPT did not get a tunnel; Cloudflare was slow. Retrying."
      pkill -f "cloudflared tunnel --url" 2>/dev/null || true
      ATTEMPT=$((ATTEMPT + 1))
      sleep 3
    fi
  done

  if [ -z "$URL" ]; then
    echo >&2
    echo "Cloudflare did not issue a quick tunnel after 4 attempts:" >&2
    grep "failed to request quick Tunnel" "$LOG" 2>/dev/null | tail -1 >&2
    echo >&2
    echo "Nothing has been changed. Quick tunnels are a free shared service" >&2
    echo "and are slow or unavailable often enough that this is worth" >&2
    echo "escaping: set TUNNEL_HOSTNAME and use a named tunnel instead." >&2
    echo "See the header of this script." >&2
    exit 1
  fi
  say "Quick tunnel: $URL"
fi

# Prove the tunnel carries traffic to this machine before writing it anywhere.
# A URL that does not answer is not a configuration worth propagating, and the
# failure it causes later points at Shopify rather than at the tunnel.
say "Checking the tunnel reaches the API"
REACHED=0
for _ in $(seq 1 10); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$URL/" 2>/dev/null || true)
  if [ "$CODE" != "000" ] && [ -n "$CODE" ]; then
    REACHED=1
    break
  fi
  sleep 3
done

if [ "$REACHED" != "1" ]; then
  echo >&2
  echo "The tunnel came up at $URL but nothing answers through it." >&2
  echo "Is the API running on localhost:8000? Start it with: make dev-api" >&2
  echo "Nothing has been changed." >&2
  exit 1
fi
say "Tunnel reaches the API"

# --- propagate -------------------------------------------------------------
python3 - "$URL" "$REPO_ROOT" <<'PY'
import pathlib, re, sys

url, root = sys.argv[1], pathlib.Path(sys.argv[2])

env = root / ".env"
if env.exists():
    text = env.read_text()
    if re.search(r"^PUBLIC_BASE_URL=", text, re.M):
        text = re.sub(r"^PUBLIC_BASE_URL=.*$", f"PUBLIC_BASE_URL={url}", text, flags=re.M)
    else:
        text += f"PUBLIC_BASE_URL={url}\n"
    env.write_text(text)
    print(f"    .env               PUBLIC_BASE_URL={url}")

toml = root / "shopify.app.toml"
if toml.exists():
    text = toml.read_text()
    text = re.sub(r'^application_url = ".*"$', f'application_url = "{url}"', text, flags=re.M)
    text = re.sub(
        r'^redirect_urls = \[ ".*" \]$',
        f'redirect_urls = [ "{url}/shopify/callback" ]',
        text,
        flags=re.M,
    )
    toml.write_text(text)
    print(f"    shopify.app.toml   {url}/shopify/callback")
PY

if [ "$NAMED" = "1" ]; then
cat <<NEXT

The old API has been stopped for you. One thing left:

  make dev-api             # start the API again

No redeploy: this hostname is permanent, so Shopify already allows it. If this
is the first time you have used it, run `shopify app deploy` once.

Then connect the store at http://localhost:3000/brand

NEXT
else
cat <<NEXT

The old API has been stopped for you, because it was still holding the
previous URL. Two things left, in this order:

  1. make dev-api          # start the API again, on the new URL
  2. shopify app deploy    # push the new redirect URL to Shopify

Both are required. Skipping either gives "Oauth error invalid_request:
The redirect_uri is not whitelisted" at the Shopify authorize screen.

This hostname is random and temporary, so the deploy above is invalidated the
next time this script runs. Set TUNNEL_HOSTNAME in .env to stop that happening
at all — see the header of this script.

Then connect the store at http://localhost:3000/brand
NEXT
fi
