"""Dependency health probes.

The readiness report is the phase 0.1 proof that every service in the compose
stack is reachable from the API. Each probe is independent, time-boxed, and
never raises — a dead dependency is reported, not propagated.
"""

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import redis.asyncio as aioredis
from sqlalchemy import create_engine, text

from sendox_api.config import Settings

PROBE_TIMEOUT_SECONDS = 3.0

# Chroma removed the v1 API in 1.x: /api/v1/* now returns 410 Gone.
CHROMA_HEARTBEAT_PATH = "/api/v2/heartbeat"

Status = Literal["ok", "error"]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    name: str
    status: Status
    latency_ms: float
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1),
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


def _truncate(message: str, limit: int = 200) -> str:
    collapsed = " ".join(message.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


async def _timed(name: str, probe: Coroutine[Any, Any, None]) -> ProbeResult:
    """Run an awaitable probe, converting any failure into an error result."""
    started = time.perf_counter()
    try:
        await asyncio.wait_for(probe, timeout=PROBE_TIMEOUT_SECONDS)
    except TimeoutError:
        return ProbeResult(name, "error", (time.perf_counter() - started) * 1000, "timed out")
    except Exception as exc:  # noqa: BLE001 - a probe must never raise
        detail = _truncate(f"{type(exc).__name__}: {exc}")
        return ProbeResult(name, "error", (time.perf_counter() - started) * 1000, detail)
    return ProbeResult(name, "ok", (time.perf_counter() - started) * 1000)


async def _check_postgres(settings: Settings) -> None:
    def query() -> None:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()

    await asyncio.to_thread(query)


async def _check_redis(settings: Settings) -> None:
    client = aioredis.from_url(settings.redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def _check_http(url: str, expect_substring: str | None = None) -> None:
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
        response = await client.get(url)
        response.raise_for_status()
        if expect_substring and expect_substring not in response.text:
            raise ValueError(f"unexpected body from {url}")


async def _check_chroma(settings: Settings) -> None:
    await _check_http(f"{settings.chroma_url.rstrip('/')}{CHROMA_HEARTBEAT_PATH}")


async def _check_mjml(settings: Settings) -> None:
    await _check_http(f"{settings.mjml_url.rstrip('/')}/health")


async def run_readiness_probes(settings: Settings) -> list[ProbeResult]:
    """Probe every backing service concurrently."""
    probes: dict[str, Coroutine[Any, Any, None]] = {
        "postgres": _check_postgres(settings),
        "redis": _check_redis(settings),
        "chromadb": _check_chroma(settings),
        "mjml": _check_mjml(settings),
    }
    return list(await asyncio.gather(*(_timed(name, p) for name, p in probes.items())))
