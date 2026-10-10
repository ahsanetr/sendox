"""Storefront extraction.

The boilerplate pass is the part worth testing hardest. Without it every chunk
opens with the same hundred words of cart and navigation, every embedding
crowds into the same region, and retrieval scores *highly* while returning site
furniture — which is worse than returning nothing, because it looks like it
worked.
"""

from sendox_api.clients.storefront import (
    classify,
    extract_text,
    strip_boilerplate,
)

CHROME = [
    "Skip to content",
    "Your cart is empty",
    "Log in to check out faster",
    "Subscribe to our newsletter",
]


def _page(url: str, unique: list[str]) -> tuple[str, str, list[str]]:
    return (url, "Title", [*CHROME, *unique])


def test_lines_repeating_across_the_site_are_removed() -> None:
    pages = [
        _page("/a", ["The Ridgeline Parka is a three-layer waterproof shell."]),
        _page("/b", ["Summit Liner Gloves are merino-blend touchscreen liners."]),
        _page("/c", ["We started in a garage in 2016 after a jacket failed."]),
        _page("/d", ["Returns accepted within 60 days, worn or unworn."]),
    ]

    cleaned = strip_boilerplate(pages)

    for _, _, text in cleaned:
        for chrome in CHROME:
            assert chrome not in text
    assert "Ridgeline Parka" in cleaned[0][2]
    assert "garage in 2016" in cleaned[2][2]


def test_a_small_site_is_left_alone() -> None:
    """With two pages, everything looks repeated. Better to keep too much than
    to strip a brand's only paragraph."""
    pages = [
        _page("/a", ["The Ridgeline Parka is waterproof."]),
        _page("/b", ["Summit Liner Gloves are merino."]),
    ]

    cleaned = strip_boilerplate(pages)

    assert "Skip to content" in cleaned[0][2]


def test_content_appearing_on_a_minority_of_pages_survives() -> None:
    """A line on two of six pages is a shared product claim, not furniture."""
    shared = "Free shipping over 150 USD."
    pages = [
        _page("/a", [shared]),
        _page("/b", [shared]),
        _page("/c", ["Unique one."]),
        _page("/d", ["Unique two."]),
        _page("/e", ["Unique three."]),
        _page("/f", ["Unique four."]),
    ]

    cleaned = strip_boilerplate(pages)

    assert shared in cleaned[0][2]


def test_extraction_prefers_the_main_region() -> None:
    """When a theme marks its content, that is the most reliable signal there is."""
    html = """
    <html><head><title>Ridgeline Parka</title></head><body>
      <nav>Shop All Collections</nav>
      <div class="announcement-bar">Free shipping this week</div>
      <main><p>The Ridgeline Parka is a three-layer waterproof shell.</p></main>
      <footer>Terms and conditions</footer>
    </body></html>
    """

    title, lines = extract_text(html)
    text = " ".join(lines)

    assert title == "Ridgeline Parka"
    assert "three-layer waterproof shell" in text
    assert "Shop All Collections" not in text
    assert "Terms and conditions" not in text


def test_scripts_and_styles_never_reach_the_text() -> None:
    html = """
    <html><body><main>
      <script>window.shop = {money:'$'};</script>
      <style>.cart { display: none; }</style>
      <p>We write plainly and never oversell.</p>
    </main></body></html>
    """

    _, lines = extract_text(html)
    text = " ".join(lines)

    assert "We write plainly" in text
    assert "window.shop" not in text
    assert "display: none" not in text


def test_pages_are_classified_by_their_url() -> None:
    """Content type drives retrieval filtering later, so it must be right."""
    assert classify("https://b.example/products/parka") == "product"
    assert classify("https://b.example/pages/about") == "page"
    assert classify("https://b.example/blogs/news/winter") == "blog"
    assert classify("https://b.example/collections/outerwear") == "collection"
    assert classify("https://b.example/") == "home"
