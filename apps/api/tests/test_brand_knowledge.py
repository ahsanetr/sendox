"""Chunking decides how good retrieval is, so the boundaries get tested.

Embed a whole page and the vector averages everything on it; embed single
sentences and each loses the context that gave it meaning. These tests pin the
behaviour in between.
"""

import uuid

from sendox_api.clients.storefront import Page
from sendox_api.services.brand_knowledge import (
    MIN_CHUNK_WORDS,
    TARGET_WORDS,
    chunk_text,
    chunks_from_pages,
    split_sentences,
)

# How many words from each side of a boundary to compare when checking overlap.
OVERLAP_SAMPLE = 60


def _prose(sentences: int, words_each: int = 12) -> str:
    """Realistic prose: sentences start with a capital, as the splitter expects."""
    return " ".join(
        f"Sentence {index} {' '.join(['word'] * (words_each - 2))}." for index in range(sentences)
    )


def test_short_text_stays_one_chunk() -> None:
    text = "Northwind makes hard-wearing outdoor gear. Everything is field-tested first."

    assert chunk_text(text) == [text]


def test_long_text_is_split_near_the_target_size() -> None:
    chunks = chunk_text(_prose(200))

    assert len(chunks) > 1
    # Overlap means a chunk can exceed the target slightly; it must not run away.
    assert all(len(chunk.split()) <= TARGET_WORDS * 1.4 for chunk in chunks)


def test_sentences_are_never_cut_in_half() -> None:
    """A half-sentence embeds badly and reads worse when shown back to the user."""
    chunks = chunk_text(_prose(200))

    for chunk in chunks:
        assert chunk.rstrip().endswith("."), chunk[-60:]


def test_chunks_overlap_so_a_claim_spanning_a_boundary_survives() -> None:
    chunks = chunk_text(_prose(200))
    first_tail = set(chunks[0].split()[-OVERLAP_SAMPLE:])
    second_head = set(chunks[1].split()[:OVERLAP_SAMPLE])

    assert first_tail & second_head, "no overlap between consecutive chunks"


def test_a_short_tail_joins_the_previous_chunk_rather_than_standing_alone() -> None:
    """A six-word fragment on its own is noise in a similarity search."""
    chunks = chunk_text(_prose(120) + " A tiny tail.")

    assert all(len(chunk.split()) >= MIN_CHUNK_WORDS for chunk in chunks)


def test_sentence_splitting_handles_normal_punctuation() -> None:
    text = 'We ship fast. Do you deliver abroad? Yes! "Always," we say.'

    assert len(split_sentences(text)) == 4


def test_chunk_ids_are_stable_across_recrawls() -> None:
    """Re-crawling must overwrite the same rows, not pile up copies (M7 FE-5)."""
    tenant = uuid.uuid4()
    page = Page(
        url="https://brand.example/pages/about",
        title="About",
        text=_prose(120),
        kind="page",
    )

    first = chunks_from_pages(tenant, [page])
    second = chunks_from_pages(tenant, [page])

    assert [c.id for c in first] == [c.id for c in second]
    assert first[0].id.startswith("https://brand.example/pages/about#")


def test_each_chunk_carries_where_it_came_from() -> None:
    """Retrieval has to be able to cite a source, and the UI has to show one."""
    tenant = uuid.uuid4()
    page = Page(
        url="https://brand.example/products/parka",
        title="Ridgeline Parka",
        text=_prose(60),
        kind="product",
    )

    chunk = chunks_from_pages(tenant, [page])[0]

    assert chunk.metadata["source_url"] == page.url
    assert chunk.metadata["content_type"] == "product"
    assert chunk.metadata["title"] == "Ridgeline Parka"
