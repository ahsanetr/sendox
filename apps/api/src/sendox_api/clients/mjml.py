"""Client for the MJML render sidecar.

Used by the dev capability check now and by the Design Agent in phase 1.8 — the
agent will build MJML and call exactly this function to compile it.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from sendox_api.config import Settings

RENDER_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class RenderResult:
    html: str
    errors: list[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return not self.errors


class MjmlRenderError(RuntimeError):
    """The sidecar rejected the request outright (bad payload, strict validation)."""


async def render(settings: Settings, mjml: str, *, minify: bool = False) -> RenderResult:
    url = f"{settings.mjml_url.rstrip('/')}/render"
    payload = {"mjml": mjml, "minify": minify}

    async with httpx.AsyncClient(timeout=RENDER_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=payload)

    if response.status_code >= 400:
        detail = response.json().get("error", response.text)
        raise MjmlRenderError(detail)

    body = response.json()
    return RenderResult(html=body["html"], errors=body["errors"])
