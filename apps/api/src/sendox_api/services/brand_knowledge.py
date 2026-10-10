"""Turn crawled pages into retrievable brand knowledge (scope M7 FE-1).

Chunking is the step people skip, and it decides how good retrieval is. Embed a
whole page and the vector is an average of everything on it — a product page
about a parka, a shipping promise and a returns policy all blur into one point
that matches nothing well. Embed single sentences and each one loses the context
that gave it meaning.

So: paragraph-aware chunks of roughly 500 tokens, never splitting mid-sentence,
with a little overlap so a statement spanning a boundary survives in one piece.
"""

import re
import uuid
from dataclasses import dataclass

import structlog

from sendox_api.clients.chroma import BrandChunk
from sendox_api.clients.storefront import Page

log = structlog.get_logger(__name__)

# ~500 tokens. Counting words rather than tokens is deliberate: it needs no
# tokenizer, and for English prose the ratio is stable enough that the chunk
# lands in the right size band either way.
TARGET_WORDS = 375
OVERLAP_WORDS = 50
MIN_CHUNK_WORDS = 30

# Requires the next sentence to open with a capital, digit or quote. That is
# what stops "Inc." and "e.g." being treated as sentence ends; the cost is that
# a sentence opening with a lowercase brand name ("iPhone cases ship free.")
# joins the one before it. For chunking that is harmless — the text stays whole.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def chunk_text(text: str) -> list[str]:
    """Group sentences into ~TARGET_WORDS chunks, never cutting one in half."""
    sentences = split_sentences(text)
    chunks: list[str] = []
    current: list[str] = []
    count = 0

    for sentence in sentences:
        words = len(sentence.split())
        if count + words > TARGET_WORDS and current:
            chunks.append(" ".join(current))
            # Carry the tail forward so a claim spanning the boundary stays whole
            # in at least one chunk.
            overlap: list[str] = []
            overlap_count = 0
            for previous in reversed(current):
                overlap.insert(0, previous)
                overlap_count += len(previous.split())
                if overlap_count >= OVERLAP_WORDS:
                    break
            current, count = overlap, overlap_count
        current.append(sentence)
        count += words

    if current and count >= MIN_CHUNK_WORDS:
        chunks.append(" ".join(current))
    elif current and chunks:
        # A short remainder belongs with the chunk before it rather than alone.
        chunks[-1] = f"{chunks[-1]} {' '.join(current)}"
    elif current:
        chunks.append(" ".join(current))

    return chunks


@dataclass(frozen=True, slots=True)
class ChunkStats:
    pages: int
    chunks: int
    words: int

    def as_dict(self) -> dict[str, int]:
        return {"pages": self.pages, "chunks": self.chunks, "words": self.words}


def chunks_from_pages(tenant_id: uuid.UUID, pages: list[Page]) -> list[BrandChunk]:
    """Build the chunks for a workspace's knowledge base.

    Ids are derived from the page URL and the chunk's position, so re-crawling
    overwrites the same rows rather than accumulating copies of the site (M7
    FE-5). A page that shrinks leaves orphans, which `prune_ids` handles.
    """
    built: list[BrandChunk] = []

    for page in pages:
        for index, text in enumerate(chunk_text(page.text)):
            built.append(
                BrandChunk(
                    id=f"{page.url}#{index}",
                    text=text,
                    metadata={
                        "source_url": page.url,
                        "title": page.title,
                        "content_type": page.kind,
                        "chunk_index": index,
                        "source": "storefront",
                    },
                )
            )

    log.info(
        "brand_knowledge.chunked",
        tenant=str(tenant_id),
        pages=len(pages),
        chunks=len(built),
    )
    return built


def stats_for(pages: list[Page], chunks: list[BrandChunk]) -> ChunkStats:
    return ChunkStats(
        pages=len(pages),
        chunks=len(chunks),
        words=sum(len(chunk.text.split()) for chunk in chunks),
    )
