"""Shopify OAuth — the merchant-facing install flow (scope M3 FE-1).

This is the same model Klaviyo uses: one app, many stores. A merchant is sent to
their own admin to approve the scopes, Shopify redirects back with a short-lived
code, and we trade that code for a per-store access token.

Three checks make the callback safe, and all three matter:

* **the shop domain** is validated against a strict pattern, because it is used to
  build the URL we redirect to and the URL we post the secret to. An unchecked
  `shop` parameter is an open redirect at best and credential theft at worst;
* **the HMAC** proves the query string came from Shopify and was not edited;
* **the state** proves this callback belongs to an install *we* started, which is
  what stops a CSRF-driven install against someone else's workspace.
"""

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from re import compile as re_compile
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt

from sendox_api.config import Settings
from sendox_api.security import JWT_ALGORITHM

# A Shopify store is always <handle>.myshopify.com. Anchored on both ends so
# "evil.com?x=.myshopify.com" and "shop.myshopify.com.evil.com" are both rejected.
SHOP_DOMAIN = re_compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")

STATE_TTL = timedelta(minutes=10)
TOKEN_EXCHANGE_TIMEOUT = 20.0


class ShopifyNotConfigured(RuntimeError):
    """No app credentials, or no public URL for Shopify to redirect back to."""


class InvalidShopDomain(ValueError):
    pass


class InvalidCallback(ValueError):
    """Failed HMAC, bad state, or a missing parameter."""


class TokenExchangeFailed(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class InstallGrant:
    shop_domain: str
    access_token: str
    scopes: list[str]


def normalise_shop_domain(raw: str) -> str:
    """Accept what a merchant would actually type and return the canonical domain."""
    shop = raw.strip().lower()
    for prefix in ("https://", "http://"):
        shop = shop.removeprefix(prefix)
    shop = shop.split("/")[0]
    if "." not in shop:
        shop = f"{shop}.myshopify.com"

    if not SHOP_DOMAIN.match(shop):
        raise InvalidShopDomain(f"{raw!r} is not a myshopify.com store domain")
    return shop


def require_configured(settings: Settings) -> None:
    if not settings.shopify_configured:
        raise ShopifyNotConfigured(
            "SHOPIFY_API_KEY and SHOPIFY_API_SECRET are not set. "
            "Add them from the app's Client credentials page."
        )
    if not settings.public_base_url:
        raise ShopifyNotConfigured(
            "PUBLIC_BASE_URL is not set. Shopify cannot redirect to localhost — "
            "start a tunnel (cloudflared tunnel --url http://localhost:8000) and "
            "register its URL on the app."
        )


def issue_state(settings: Settings, tenant_id: UUID) -> str:
    """A signed, expiring state parameter.

    Signed rather than stored in a table: it already has to survive a round trip
    through Shopify, and a JWT carries the workspace it belongs to without a
    lookup. The nonce makes each one distinct and the short expiry bounds replay;
    the authorization code itself is single-use at Shopify's end.
    """
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "tenant": str(tenant_id),
            "nonce": secrets.token_urlsafe(16),
            "iat": int(now.timestamp()),
            "exp": int((now + STATE_TTL).timestamp()),
            "iss": "sendox-shopify-install",
        },
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def read_state(settings: Settings, state: str) -> UUID:
    try:
        payload = jwt.decode(
            state,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer="sendox-shopify-install",
            options={"require": ["tenant", "exp"]},
        )
        return UUID(payload["tenant"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidCallback(f"install state is not valid: {exc}") from exc


def authorize_url(settings: Settings, shop_domain: str, state: str) -> str:
    """Where to send the merchant to approve the install."""
    require_configured(settings)
    query = urlencode(
        {
            "client_id": settings.shopify_api_key or "",
            "scope": ",".join(settings.shopify_scope_list),
            "redirect_uri": settings.oauth_redirect_uri,
            "state": state,
        }
    )
    return f"https://{shop_domain}/admin/oauth/authorize?{query}"


def verify_hmac(settings: Settings, params: dict[str, str]) -> bool:
    """Confirm the callback query string really came from Shopify.

    Shopify signs every parameter except `hmac` itself, sorted by key and joined
    as `key=value&...`. `signature` is excluded too: it belongs to the older
    proxy signing scheme and is not part of the digest.
    """
    secret = settings.shopify_api_secret
    received = params.get("hmac")
    if not secret or not received:
        return False

    message = "&".join(
        f"{key}={value}"
        for key, value in sorted(params.items())
        if key not in {"hmac", "signature"}
    )
    expected = hmac.new(secret.encode(), message.encode(), sha256).hexdigest()

    # Constant-time, so a wrong digest cannot be discovered byte by byte.
    return hmac.compare_digest(expected, received)


async def exchange_code(settings: Settings, shop_domain: str, code: str) -> InstallGrant:
    """Trade the one-time code for a long-lived access token for this store."""
    require_configured(settings)

    async with httpx.AsyncClient(timeout=TOKEN_EXCHANGE_TIMEOUT) as client:
        response = await client.post(
            f"https://{shop_domain}/admin/oauth/access_token",
            json={
                "client_id": settings.shopify_api_key,
                "client_secret": settings.shopify_api_secret,
                "code": code,
            },
        )

    if response.status_code >= 400:
        raise TokenExchangeFailed(f"Shopify returned {response.status_code}: {response.text[:200]}")

    body = response.json()
    token = body.get("access_token")
    if not token:
        raise TokenExchangeFailed("Shopify did not return an access token")

    return InstallGrant(
        shop_domain=shop_domain,
        access_token=token,
        scopes=[s for s in str(body.get("scope", "")).split(",") if s],
    )
