#!/usr/bin/env bash
# Start a public HTTPS tunnel to the local API and propagate its URL everywhere
# that needs it.
#
# Shopify will not redirect OAuth to localhost, so development needs a public
# origin. A free cloudflared quick tunnel gets a random hostname and is revoked
# after a while ("Unauthorized: Tunnel not found"), which means the URL changes
# and three places go stale at once: .env, shopify.app.toml, and the running API
# which read PUBLIC_BASE_URL at startup.
#
# Doing that by hand is how an afternoon disappears, so this does all of it.

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

say "Starting a new tunnel to localhost:8000"
nohup cloudflared tunnel --url http://localhost:8000 > "$LOG" 2>&1 &

URL=""
for _ in $(seq 1 40); do
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG" 2>/dev/null | head -1 || true)
  [ -n "$URL" ] && break
  sleep 2
done

if [ -z "$URL" ]; then
  echo "Could not get a tunnel URL. See $LOG" >&2
  exit 1
fi
say "Tunnel: $URL"

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

cat <<NEXT

The old API has been stopped for you, because it was still holding the
previous URL. Two things left, in this order:

  1. make dev-api          # start the API again, on the new URL
  2. shopify app deploy    # push the new redirect URL to Shopify

Both are required. Skipping either gives "Oauth error invalid_request:
The redirect_uri is not whitelisted" at the Shopify authorize screen.

Then connect the store at http://localhost:3000/brand

NEXT
