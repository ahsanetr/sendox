"""The API must stay responsive while slow work runs.

Embedding a batch of chunks takes seconds. When those synchronous Chroma calls
were invoked directly from an async handler they blocked the event loop, and a
concurrent 10-second health check timed out — which is how the bug was found.
This pins the fix: a health check must answer promptly while a seed is in flight.
"""

import asyncio
import time

import httpx
import pytest

from sendox_api.clients import chroma
from sendox_api.config import Settings
from sendox_api.main import create_app

pytestmark = pytest.mark.integration

HEALTH_BUDGET_SECONDS = 3.0


def _chroma_up(settings: Settings) -> bool:
    try:
        chroma.heartbeat(settings)
        return True
    except Exception:  # noqa: BLE001
        return False


async def test_health_check_answers_while_embedding_runs(settings: Settings) -> None:
    if not _chroma_up(settings):
        pytest.skip("ChromaDB not running — start it with `make up`")

    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        seed = asyncio.create_task(client.post("/dev/vectors/seed", timeout=120))

        # Give the seed a moment to actually start before timing the health check.
        await asyncio.sleep(0.2)

        started = time.perf_counter()
        health = await client.get("/health/live", timeout=HEALTH_BUDGET_SECONDS * 2)
        elapsed = time.perf_counter() - started

        seed_response = await seed

    assert health.status_code == 200
    assert seed_response.status_code == 200
    assert elapsed < HEALTH_BUDGET_SECONDS, (
        f"health check took {elapsed:.2f}s while embedding ran — "
        "the event loop is being blocked again"
    )
