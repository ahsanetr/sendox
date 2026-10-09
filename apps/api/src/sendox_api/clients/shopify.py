"""Shopify Admin API client (scope M3 FE-4, FE-6).

Two things make a Shopify integration awkward, and both are handled here so no
caller has to think about them.

**Rate limits.** The REST Admin API uses a leaky bucket: 40 requests of burst,
refilling at 2/second on a standard plan. Shopify reports the current level in
`X-Shopify-Shop-Api-Call-Limit` as `used/total`. Rather than sprinting into a 429
and backing off, this client slows down as the bucket fills — a bulk import of
tens of thousands of records then runs at a steady pace instead of in bursts
punctuated by failures.

**Cursor pagination.** Results are paged through an opaque `Link` header, not a
page number. `paginate` follows it until exhausted, so callers write a for-loop.
"""

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from sendox_api.config import Settings

log = structlog.get_logger(__name__)

REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 5
# Start easing off once the leaky bucket is this full.
THROTTLE_THRESHOLD = 0.5
PAGE_SIZE = 250  # Shopify's maximum

_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


class ShopifyError(RuntimeError):
    """A request failed in a way retrying will not fix."""


class ShopifyAuthError(ShopifyError):
    """The token was rejected — usually the app was uninstalled."""


@dataclass(frozen=True, slots=True)
class ShopCredentials:
    shop_domain: str
    access_token: str


def _call_limit_usage(response: httpx.Response) -> float:
    """How full the leaky bucket is, 0.0 to 1.0."""
    header = response.headers.get("X-Shopify-Shop-Api-Call-Limit")
    if not header or "/" not in header:
        return 0.0
    used, _, total = header.partition("/")
    try:
        return int(used) / max(int(total), 1)
    except ValueError:
        return 0.0


async def _respect_rate_limit(response: httpx.Response) -> None:
    usage = _call_limit_usage(response)
    if usage < THROTTLE_THRESHOLD:
        return
    # Scale from no delay at the threshold up to half a second when full, which
    # keeps a bulk import just under the refill rate rather than tripping 429s.
    delay = (usage - THROTTLE_THRESHOLD) / (1 - THROTTLE_THRESHOLD) * 0.5
    await asyncio.sleep(delay)


class ShopifyClient:
    """Thin REST client scoped to one store's credentials."""

    def __init__(self, settings: Settings, credentials: ShopCredentials) -> None:
        self._settings = settings
        self._credentials = credentials
        self._base = f"https://{credentials.shop_domain}/admin/api/{settings.shopify_api_version}"

    @property
    def shop_domain(self) -> str:
        return self._credentials.shop_domain

    async def _request(
        self, client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        for attempt in range(MAX_RETRIES):
            response = await client.request(
                method,
                url,
                headers={
                    "X-Shopify-Access-Token": self._credentials.access_token,
                    "Accept": "application/json",
                },
                **kwargs,
            )

            if response.status_code == 429:
                # Shopify tells us exactly how long to wait; believe it.
                wait = float(response.headers.get("Retry-After", 2**attempt))
                log.warning(
                    "shopify.rate_limited", shop=self.shop_domain, wait=wait, attempt=attempt
                )
                await asyncio.sleep(wait)
                continue

            if response.status_code in (401, 403):
                raise ShopifyAuthError(
                    f"{self.shop_domain} rejected the access token "
                    f"({response.status_code}) — the app may have been uninstalled"
                )

            if response.status_code >= 500:
                await asyncio.sleep(2**attempt)
                continue

            if response.status_code >= 400:
                raise ShopifyError(
                    f"{method} {url} returned {response.status_code}: {response.text[:200]}"
                )

            await _respect_rate_limit(response)
            return response

        raise ShopifyError(f"{method} {url} still failing after {MAX_RETRIES} attempts")

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await self._request(
                client, "GET", f"{self._base}/{path.lstrip('/')}", params=params
            )
        body: dict[str, Any] = response.json()
        return body

    async def paginate(
        self, path: str, key: str, limit: int = PAGE_SIZE, **params: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield every record across every page.

        Follows the opaque cursor in the `Link` header. Note that the cursor URL
        already carries its own query string, so subsequent requests must not
        re-send the original params.
        """
        url: str | None = f"{self._base}/{path.lstrip('/')}"
        query: dict[str, Any] | None = {**params, "limit": limit}

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            while url:
                response = await self._request(client, "GET", url, params=query)
                for record in response.json().get(key, []):
                    yield record

                match = _NEXT_LINK.search(response.headers.get("Link", ""))
                url = match.group(1) if match else None
                query = None

    async def count(self, path: str, **params: Any) -> int:
        body = await self.get(path, **params)
        return int(body.get("count", 0))

    async def shop(self) -> dict[str, Any]:
        """Store metadata — also the cheapest way to verify a token works."""
        body = await self.get("shop.json")
        shop: dict[str, Any] = body.get("shop", {})
        return shop
