"""Brand knowledge vector store (scope M7).

**Tenant isolation here works differently from Postgres.** Chroma has no row-level
security, so each workspace gets its own collection, `brand-<tenant_id>`, and the
collection name is the only way in. Nothing in this module accepts a collection
name from a caller — it is always derived from a tenant id — so a query cannot be
pointed at another brand's knowledge base.

Embeddings are computed locally with Chroma's default model (all-MiniLM-L6-v2 via
ONNX, 384 dimensions): no API key, no per-call cost, and no torch in the image.
The scope document allows this — M7 FE-2 reads "OpenAI text-embedding-3-small or
open-source alternative".
"""

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import DefaultEmbeddingFunction

from sendox_api.config import Settings

DEFAULT_TOP_K = 5


@dataclass(frozen=True, slots=True)
class BrandChunk:
    """One retrievable piece of brand knowledge."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Match:
    id: str
    text: str
    metadata: dict[str, Any]
    distance: float

    @property
    def similarity(self) -> float:
        """Cosine distance expressed as a 0-1 similarity, for readability."""
        return max(0.0, 1.0 - self.distance / 2.0)


@lru_cache
def _client_for(chroma_url: str) -> ClientAPI:
    parsed = urlparse(chroma_url)
    return chromadb.HttpClient(
        host=parsed.hostname or "localhost",
        port=parsed.port or (443 if parsed.scheme == "https" else 8000),
        ssl=parsed.scheme == "https",
    )


def get_client(settings: Settings) -> ClientAPI:
    return _client_for(settings.chroma_url)


def collection_name(tenant_id: UUID) -> str:
    """Derived, never supplied — this is the tenant boundary in Chroma."""
    return f"brand-{tenant_id}"


@lru_cache
def _embedding_function() -> DefaultEmbeddingFunction:
    # Downloads the ONNX model once, then runs offline.
    return DefaultEmbeddingFunction()


def get_collection(settings: Settings, tenant_id: UUID) -> Collection:
    return get_client(settings).get_or_create_collection(
        name=collection_name(tenant_id),
        # chromadb types its embedding-function protocol over text-or-image input
        # while the bundled default is text-only, so the concrete class does not
        # satisfy the declared protocol. The cast records that, rather than
        # loosening the module's own types.
        embedding_function=cast(Any, _embedding_function()),
        metadata={"hnsw:space": "cosine", "tenant_id": str(tenant_id)},
    )


def upsert_chunks(settings: Settings, tenant_id: UUID, chunks: list[BrandChunk]) -> int:
    """Add or replace chunks. Returns how many were written."""
    if not chunks:
        return 0

    collection = get_collection(settings, tenant_id)
    collection.upsert(
        ids=[chunk.id for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        # Chroma rejects empty metadata dicts, so always carry the tenant id.
        metadatas=[{**chunk.metadata, "tenant_id": str(tenant_id)} for chunk in chunks],
    )
    return len(chunks)


def query(
    settings: Settings, tenant_id: UUID, text: str, top_k: int = DEFAULT_TOP_K
) -> list[Match]:
    """Semantic search within one workspace's knowledge base."""
    collection = get_collection(settings, tenant_id)
    if collection.count() == 0:
        return []

    raw = collection.query(
        query_texts=[text],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    ids = raw["ids"][0]
    documents = cast(list[list[str | None]], raw.get("documents") or [[]])[0]
    metadatas = cast(list[list[dict[str, Any] | None]], raw.get("metadatas") or [[]])[0]
    distances = cast(list[list[float]], raw.get("distances") or [[]])[0]

    return [
        Match(
            id=chunk_id,
            text=documents[index] or "",
            metadata=metadatas[index] or {},
            distance=float(distances[index]),
        )
        for index, chunk_id in enumerate(ids)
    ]


def stats(settings: Settings, tenant_id: UUID) -> dict[str, Any]:
    collection = get_collection(settings, tenant_id)
    return {
        "collection": collection.name,
        "chunks": collection.count(),
        "embedding_model": "all-MiniLM-L6-v2 (ONNX, local)",
        "dimensions": 384,
        "distance": "cosine",
    }


def drop(settings: Settings, tenant_id: UUID) -> None:
    """Remove a workspace's knowledge base entirely (used by tests and re-crawls)."""
    try:
        get_client(settings).delete_collection(collection_name(tenant_id))
    except Exception:  # noqa: BLE001 - absent collection is not an error here
        return


def heartbeat(settings: Settings) -> int:
    value: int = get_client(settings).heartbeat()
    return value


# --------------------------------------------------------------------- async API
#
# Embedding and HTTP calls here are synchronous and can take seconds — the first
# call downloads the ONNX model. Calling them directly from an async request
# handler blocks the event loop and every other in-flight request with it, which
# is exactly how a 10-second health check ended up timing out. Request handlers
# use these wrappers; Celery tasks can use the sync functions directly.


async def aupsert_chunks(settings: Settings, tenant_id: UUID, chunks: list[BrandChunk]) -> int:
    return await asyncio.to_thread(upsert_chunks, settings, tenant_id, chunks)


async def aquery(
    settings: Settings, tenant_id: UUID, text: str, top_k: int = DEFAULT_TOP_K
) -> list[Match]:
    return await asyncio.to_thread(query, settings, tenant_id, text, top_k)


async def astats(settings: Settings, tenant_id: UUID) -> dict[str, Any]:
    return await asyncio.to_thread(stats, settings, tenant_id)


async def adrop(settings: Settings, tenant_id: UUID) -> None:
    await asyncio.to_thread(drop, settings, tenant_id)


async def awarm_embedding_model() -> None:
    """Download and load the ONNX model off the event loop.

    Called at startup so the first real request does not pay for it.
    """
    await asyncio.to_thread(lambda: _embedding_function()(["warmup"]))
