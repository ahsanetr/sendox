"""Development-only capability checks.

These prove the wiring the dashboard reports on: that the API can enqueue work a
worker actually executes, and that it can reach the MJML sidecar. Never mounted
when ENV is production.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from sendox_api.clients import chroma, claude
from sendox_api.clients.mjml import MjmlRenderError, render
from sendox_api.config import Settings
from sendox_api.db import global_session
from sendox_api.dependencies import SettingsDep
from sendox_api.models import Tenant

router = APIRouter(prefix="/dev", tags=["dev"])

SAMPLE_MJML = """<mjml>
  <mj-body background-color="#f4f4f5">
    <mj-section background-color="#ffffff" padding="24px">
      <mj-column>
        <mj-text font-size="20px" font-weight="700">Your cart misses you</mj-text>
        <mj-text font-size="14px" color="#52525b">
          Still thinking it over? Your items are waiting.
        </mj-text>
        <mj-button background-color="#111827" href="https://example.test/cart">
          Complete checkout
        </mj-button>
      </mj-column>
    </mj-section>
  </mj-body>
</mjml>"""


class RenderRequest(BaseModel):
    mjml: str = Field(default=SAMPLE_MJML, description="MJML source; defaults to a sample email")
    minify: bool = False


class TaskAccepted(BaseModel):
    task_id: str
    state: str


@router.post("/tasks/ping", response_model=TaskAccepted, summary="Enqueue a Celery round-trip")
async def enqueue_ping(payload: str = "pong") -> TaskAccepted:
    # Imported here so the module does not require a broker at import time.
    from sendox_api.tasks import ping

    result = ping.delay(payload)
    return TaskAccepted(task_id=result.id, state=result.state)


@router.get("/tasks/{task_id}", summary="Poll a Celery task")
async def task_result(task_id: str) -> dict[str, Any]:
    from sendox_api.worker import celery_app

    async_result = celery_app.AsyncResult(task_id)
    ready = bool(async_result.ready())

    return {
        "task_id": task_id,
        "state": str(async_result.state),
        "ready": ready,
        "result": async_result.result if ready and async_result.successful() else None,
    }


@router.post("/mjml/render", summary="Compile MJML through the sidecar")
async def render_mjml(request: RenderRequest, settings: SettingsDep) -> dict[str, Any]:
    try:
        result = await render(settings, request.mjml, minify=request.minify)
    except MjmlRenderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return {
        "ok": result.ok,
        "errors": result.errors,
        "html_bytes": len(result.html),
        "responsive": "@media" in result.html,
        "html": result.html,
    }


# --------------------------------------------------------------------- sandbox

DEV_TENANT_SLUG = "dev-sandbox"

# Stand-ins for what the crawler (phase 1.4) will extract from a real storefront.
SAMPLE_BRAND_CHUNKS: list[tuple[str, str, str]] = [
    (
        "about",
        "about-page",
        "Northwind Supply makes hard-wearing outdoor gear for people who actually use it. "
        "We started in a garage in 2016 after one too many jackets failed on a winter hike. "
        "Everything we sell is tested in the field before it reaches the shop.",
    ),
    (
        "tone",
        "brand-voice",
        "We write plainly and never oversell. No exclamation marks, no hype, no fake "
        "scarcity. If a product has a limitation we say so, because our customers are "
        "experienced and can tell when they are being handled.",
    ),
    (
        "product-parka",
        "product",
        "The Ridgeline Parka is a three-layer waterproof shell rated to -20C. Taped seams, "
        "pit zips, and a helmet-compatible hood. It weighs 820g in a medium and packs into "
        "its own chest pocket. Priced at 340 USD.",
    ),
    (
        "product-gloves",
        "product",
        "Summit Liner Gloves are merino-blend touchscreen-compatible liners meant to be worn "
        "under a shell mitt. Thin enough to handle a zip or a stove. Priced at 38 USD.",
    ),
    (
        "shipping",
        "faq",
        "Orders ship within two business days from Portland. Free shipping over 150 USD in "
        "the US. Returns accepted within 60 days, worn or unworn, because gear should be "
        "tried properly before you commit to it.",
    ),
]


async def _adev_tenant(settings: Settings) -> Tenant:
    """Async wrapper: SQLAlchemy here is synchronous, so keep it off the loop."""
    return await asyncio.to_thread(_dev_tenant, settings)


def _dev_tenant(settings: Settings) -> Tenant:
    """A stable sandbox workspace, so the vector-store checks have somewhere to live.

    Real workspaces arrive with M1 (phase 1.1); until then this gives the dashboard
    a tenant id to exercise tenant-scoped machinery against.
    """
    with global_session(settings) as session:
        tenant = session.execute(
            select(Tenant).where(Tenant.slug == DEV_TENANT_SLUG)
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name="Northwind Supply (sandbox)", slug=DEV_TENANT_SLUG)
            session.add(tenant)
            session.flush()
        return tenant


class VectorQuery(BaseModel):
    query: str = Field(min_length=1, examples=["what is your returns policy?"])
    top_k: int = Field(default=3, ge=1, le=20)


@router.get("/vectors/stats", summary="Sandbox knowledge-base size and model")
async def vector_stats(settings: SettingsDep) -> dict[str, Any]:
    tenant = await _adev_tenant(settings)
    try:
        return {"tenant_id": str(tenant.id), **(await chroma.astats(settings, tenant.id))}
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/vectors/seed", summary="Embed sample brand content into the sandbox")
async def vector_seed(settings: SettingsDep) -> dict[str, Any]:
    tenant = await _adev_tenant(settings)
    chunks = [
        chroma.BrandChunk(
            id=chunk_id,
            text=text,
            metadata={"content_type": content_type, "source": "sample"},
        )
        for chunk_id, content_type, text in SAMPLE_BRAND_CHUNKS
    ]
    try:
        written = await chroma.aupsert_chunks(settings, tenant.id, chunks)
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {
        "tenant_id": str(tenant.id),
        "chunks_written": written,
        **(await chroma.astats(settings, tenant.id)),
    }


@router.post("/vectors/query", summary="Semantic search over the sandbox knowledge base")
async def vector_query(request: VectorQuery, settings: SettingsDep) -> dict[str, Any]:
    tenant = await _adev_tenant(settings)
    try:
        matches = await chroma.aquery(settings, tenant.id, request.query, top_k=request.top_k)
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {
        "query": request.query,
        "tenant_id": str(tenant.id),
        "matches": [
            {
                "id": match.id,
                "similarity": round(match.similarity, 4),
                "distance": round(match.distance, 4),
                "content_type": match.metadata.get("content_type"),
                "text": match.text,
            }
            for match in matches
        ],
    }


@router.delete("/vectors", summary="Drop the sandbox knowledge base")
async def vector_drop(settings: SettingsDep) -> dict[str, str]:
    tenant = await _adev_tenant(settings)
    await chroma.adrop(settings, tenant.id)
    return {"dropped": chroma.collection_name(tenant.id)}


# -------------------------------------------------------------------- Claude


@router.get("/ai/status", summary="Is Claude configured?")
async def ai_status(settings: SettingsDep) -> dict[str, Any]:
    return {
        "configured": claude.is_configured(settings),
        "model": settings.anthropic_model,
        "hint": None
        if claude.is_configured(settings)
        else "Set ANTHROPIC_API_KEY in .env to enable AI generation.",
    }


@router.post("/ai/ping", summary="Smallest possible Claude round-trip")
async def ai_ping(settings: SettingsDep) -> dict[str, Any]:
    try:
        completion = await claude.complete(
            settings,
            "Reply with exactly the word: ready",
            system="You are a terse health check. Answer in one word.",
            max_tokens=16,
        )
    except claude.ClaudeNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except claude.ClaudeCallFailed as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {
        "text": completion.text.strip(),
        "model": completion.model,
        "input_tokens": completion.input_tokens,
        "output_tokens": completion.output_tokens,
    }
