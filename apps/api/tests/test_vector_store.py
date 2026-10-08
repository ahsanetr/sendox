"""Brand knowledge vector store.

Isolation in Chroma is a different mechanism from Postgres: there is no row-level
security, so each workspace gets its own collection and the name is derived from
the tenant id rather than supplied. These tests cover both that the retrieval is
useful and that the boundary holds.

Marked `integration` — a real Chroma is needed.
"""

import uuid
from collections.abc import Iterator

import pytest

from sendox_api.clients import chroma
from sendox_api.config import Settings

pytestmark = pytest.mark.integration


def _chroma_up(settings: Settings) -> bool:
    try:
        chroma.heartbeat(settings)
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


@pytest.fixture
def store(settings: Settings) -> Settings:
    if not _chroma_up(settings):
        pytest.skip("ChromaDB not running — start it with `make up`")
    return settings


@pytest.fixture
def tenant_a(store: Settings) -> Iterator[uuid.UUID]:
    tenant_id = uuid.uuid4()
    yield tenant_id
    chroma.drop(store, tenant_id)


@pytest.fixture
def tenant_b(store: Settings) -> Iterator[uuid.UUID]:
    tenant_id = uuid.uuid4()
    yield tenant_id
    chroma.drop(store, tenant_id)


def test_collection_name_is_derived_from_the_tenant(tenant_a: uuid.UUID) -> None:
    assert chroma.collection_name(tenant_a) == f"brand-{tenant_a}"


def test_chunks_are_retrievable_by_meaning_not_keyword(
    store: Settings, tenant_a: uuid.UUID
) -> None:
    """The point of embeddings: a query that shares no words still matches."""
    chroma.upsert_chunks(
        store,
        tenant_a,
        [
            chroma.BrandChunk(
                id="returns",
                text="Returns accepted within 60 days, worn or unworn.",
                metadata={"content_type": "faq"},
            ),
            chroma.BrandChunk(
                id="parka",
                text="The Ridgeline Parka is a three-layer waterproof shell rated to -20C.",
                metadata={"content_type": "product"},
            ),
        ],
    )

    matches = chroma.query(store, tenant_a, "can I send it back if it does not fit?", top_k=1)

    assert len(matches) == 1
    assert matches[0].id == "returns"
    assert matches[0].metadata["content_type"] == "faq"
    assert 0.0 <= matches[0].similarity <= 1.0


def test_one_workspace_cannot_retrieve_anothers_knowledge(
    store: Settings, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    chroma.upsert_chunks(
        store,
        tenant_a,
        [chroma.BrandChunk(id="secret", text="Alpha's confidential brand playbook.")],
    )
    chroma.upsert_chunks(
        store,
        tenant_b,
        [chroma.BrandChunk(id="other", text="Beta sells artisanal coffee beans.")],
    )

    from_b = chroma.query(store, tenant_b, "confidential brand playbook", top_k=5)

    assert [match.id for match in from_b] == ["other"]
    assert all("Alpha" not in match.text for match in from_b)


def test_querying_an_empty_knowledge_base_returns_nothing(
    store: Settings, tenant_a: uuid.UUID
) -> None:
    """Must not raise: phase 1.4 queries before the crawler has run."""
    assert chroma.query(store, tenant_a, "anything at all") == []


def test_upsert_replaces_rather_than_duplicates(store: Settings, tenant_a: uuid.UUID) -> None:
    """Re-crawling a storefront must not multiply the knowledge base (M7 FE-5)."""
    chunk = chroma.BrandChunk(id="about", text="First version of the about page.")
    chroma.upsert_chunks(store, tenant_a, [chunk])
    chroma.upsert_chunks(
        store, tenant_a, [chroma.BrandChunk(id="about", text="Revised about page.")]
    )

    assert chroma.stats(store, tenant_a)["chunks"] == 1
    assert chroma.query(store, tenant_a, "about page", top_k=1)[0].text == "Revised about page."


def test_upserting_nothing_is_a_no_op(store: Settings, tenant_a: uuid.UUID) -> None:
    assert chroma.upsert_chunks(store, tenant_a, []) == 0


def test_stats_report_the_local_embedding_model(store: Settings, tenant_a: uuid.UUID) -> None:
    stats = chroma.stats(store, tenant_a)
    assert stats["dimensions"] == 384
    assert stats["distance"] == "cosine"
    assert "local" in stats["embedding_model"]
