"""Crawl a realistic storefront end to end.

The fixture under tests/fixtures/storefront is a small brand with an About page,
six written product descriptions and a shipping policy — roughly 900 words of
actual voice, wrapped in the same chrome a Shopify theme produces.

It exists because the two worst bugs in this crawler so far were both invisible
to canned-page tests: a sitemap whose query string defeated a suffix check, and
boilerplate that made every chunk score highly while returning the cart. Those
only appear when something crawls a whole site. This gives us that, repeatably,
without depending on a live store's contents.
"""

import http.server
import re
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from sendox_api.clients.storefront import StorefrontCrawler
from sendox_api.services.brand_knowledge import chunks_from_pages

FIXTURES = Path(__file__).parent / "fixtures" / "storefront"


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the fixture, rewriting the port the sitemaps were written with."""

    # Shopify-shaped URLs mapped onto flat fixture files, so the crawler sees
    # the paths it will see in production and classification is exercised.
    ROUTES = {
        "/": "index.html",
        "/pages/about": "pages-about.html",
        "/pages/shipping-and-returns": "pages-faq.html",
        "/products/ridgeline-parka": "products-ridgeline-parka.html",
        "/products/summit-liner-gloves": "products-summit-liner-gloves.html",
        "/products/boundary-fleece": "products-boundary-fleece.html",
        "/products/tarn-rain-pant": "products-tarn-rain-pant.html",
        "/products/field-beanie": "products-field-beanie.html",
        "/products/approach-pack-28": "products-approach-pack.html",
        "/blogs/journal/why-our-range-is-small": "blogs-journal-why-small-range.html",
    }

    def translate_path(self, path: str) -> str:
        route = path.split("?", 1)[0]
        name = self.ROUTES.get(route, route.lstrip("/"))
        return str(FIXTURES / name)

    def do_GET(self) -> None:  # name fixed by the base class
        target = Path(self.translate_path(self.path))
        if not target.is_file():
            self.send_error(404)
            return
        # The sitemaps carry an {origin} placeholder so the fixture is not tied
        # to one hostname: whatever address the crawler used to reach us is the
        # address it must see in the sitemap, or every URL looks off-origin.
        origin = f"http://{self.headers.get('Host', '127.0.0.1')}".encode()
        body = target.read_bytes().replace(b"{origin}", origin)
        kind = "application/xml" if target.suffix == ".xml" else "text/html"
        self.send_response(200)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        """Silence the default access log."""


@pytest.fixture(scope="module")
def storefront() -> Iterator[str]:
    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.fixture(scope="module")
async def crawled(storefront: str):  # type: ignore[no-untyped-def]
    # No delay: this is our own loopback server, not someone's shop.
    return await StorefrontCrawler(storefront, delay=0).crawl()


async def test_every_page_is_found_through_the_sitemap(crawled) -> None:  # type: ignore[no-untyped-def]
    """Child sitemaps carry a query string, which once defeated the suffix check."""
    assert len(crawled.pages) == 10


async def test_site_furniture_never_reaches_the_text(crawled) -> None:  # type: ignore[no-untyped-def]
    """The bug this guards: boilerplate made every chunk score highly on the cart."""
    furniture = [
        "Skip to content",
        "Your cart is empty",
        "Log in to check out faster",
        "Subscribe to our newsletter",
        "Free shipping on orders over 150 USD",  # the announcement bar, on every page
    ]
    for page in crawled.pages:
        for phrase in furniture:
            assert phrase not in page.text, f"{phrase!r} survived on {page.url}"


async def test_the_brand_voice_survives(crawled) -> None:  # type: ignore[no-untyped-def]
    """Stripping chrome must not take the content with it."""
    everything = " ".join(page.text for page in crawled.pages)

    assert "We write plainly and we do not oversell" in everything
    assert "three-layer waterproof shell" in everything
    assert "Returns are accepted within 60 days" in everything


async def test_a_claim_stated_once_is_not_mistaken_for_furniture(crawled) -> None:  # type: ignore[no-untyped-def]
    """Shipping terms appear on one page, so they must survive the repetition pass."""
    everything = " ".join(page.text for page in crawled.pages)

    assert "Repairs are free for the first three years" in everything


async def test_pages_are_classified(crawled) -> None:  # type: ignore[no-untyped-def]
    kinds = {page.kind for page in crawled.pages}

    assert "product" in kinds
    assert "page" in kinds
    assert "blog" in kinds


async def test_chunking_produces_usable_passages(crawled) -> None:  # type: ignore[no-untyped-def]
    import uuid

    chunks = chunks_from_pages(uuid.uuid4(), crawled.pages)

    assert len(chunks) >= len(crawled.pages)
    # Nothing so short it carries no meaning on its own.
    assert all(len(chunk.text.split()) >= 20 for chunk in chunks)
    assert all(chunk.metadata["source_url"] for chunk in chunks)


async def test_the_crawl_yields_enough_voice_to_learn_from(crawled) -> None:  # type: ignore[no-untyped-def]
    """A floor on signal.

    The live development store yields ~1,085 words, almost all variant labels.
    A brand with real copy clears this comfortably; the number is here so the
    difference is visible rather than argued about.
    """
    assert crawled.words >= 700


def test_the_fixture_looks_like_a_real_shopify_page() -> None:
    """If the fixture stops resembling a theme, these tests stop proving anything."""
    home = (FIXTURES / "index.html").read_text()

    assert "cart-drawer" in home
    assert "announcement-bar" in home
    assert re.search(r"<nav>.*</nav>", home, re.S)
