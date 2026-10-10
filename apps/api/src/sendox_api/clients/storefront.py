"""Storefront crawler (scope M6 FE-3, FE-4, FE-6).

Reads a brand's own website — product pages, the About page, policies — because
that is where its voice actually lives. The Admin API gives us structured data;
only the storefront shows how the brand *writes*.

Three rules this crawler keeps, and they are not optional:

* **robots.txt is obeyed.** We are a guest on a merchant's site.
* **one request per second, serialised.** A storefront is a shop, not a test
  target; a crawl must never be the reason a real customer sees a slow page.
* **only the merchant's own origin** is followed. A link out is not ours to crawl.
"""

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog

# selectolax 1.0 deprecated the modest backend; lexbor follows HTML5 properly.
from selectolax.lexbor import LexborHTMLParser

log = structlog.get_logger(__name__)

USER_AGENT = "SendoxBot/0.1 (+https://sendox.app/bot; brand voice indexing)"
REQUEST_TIMEOUT = 20.0
CRAWL_DELAY_SECONDS = 1.0
MAX_PAGES = 120

# Chrome, navigation, legal boilerplate — present on every page and therefore
# useless for telling one brand's voice from another's.
STRIP_SELECTORS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "svg",
    "form",
    "iframe",
    "[aria-hidden='true']",
)


@dataclass(frozen=True, slots=True)
class Page:
    url: str
    title: str
    text: str
    kind: str  # product | page | blog | collection | home

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class CrawlReport:
    pages: list[Page] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    robots_blocked: int = 0

    @property
    def words(self) -> int:
        return sum(page.word_count for page in self.pages)


def classify(url: str) -> str:
    path = urlparse(url).path
    for marker, kind in (
        ("/products/", "product"),
        ("/pages/", "page"),
        ("/blogs/", "blog"),
        ("/collections/", "collection"),
    ):
        if marker in path:
            return kind
    return "home"


def extract_text(html: str) -> tuple[str, str]:
    """Return (title, readable text) with chrome removed."""
    tree = LexborHTMLParser(html)
    for selector in STRIP_SELECTORS:
        for node in tree.css(selector):
            node.decompose()

    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else ""

    body = tree.body
    text = body.text(separator=" ", strip=True) if body else ""
    # Collapse the whitespace a template leaves behind, so chunking later sees
    # sentences rather than indentation.
    return title, re.sub(r"\s+", " ", text).strip()


class StorefrontCrawler:
    """Polite, single-origin crawler for one storefront."""

    def __init__(
        self,
        base_url: str,
        *,
        storefront_password: str | None = None,
        max_pages: int = MAX_PAGES,
        delay: float = CRAWL_DELAY_SECONDS,
    ) -> None:
        parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.storefront_password = storefront_password
        self.max_pages = max_pages
        self.delay = delay
        self._robots: RobotFileParser | None = None

    def _same_origin(self, url: str) -> bool:
        return urlparse(url).netloc == urlparse(self.origin).netloc

    async def _load_robots(self, client: httpx.AsyncClient) -> None:
        parser = RobotFileParser()
        try:
            response = await client.get(f"{self.origin}/robots.txt")
            parser.parse(response.text.splitlines() if response.status_code == 200 else [])
        except httpx.HTTPError:
            # Unreadable robots.txt is not permission to ignore it, but it is also
            # not a reason to refuse to crawl a site that may simply not have one.
            parser.parse([])
        self._robots = parser

    def _allowed(self, url: str) -> bool:
        return self._robots.can_fetch(USER_AGENT, url) if self._robots else True

    async def _unlock(self, client: httpx.AsyncClient) -> bool:
        """Get past a development store's storefront password.

        Only ever used in development: a real merchant's storefront is public, and
        a password wall is the signal that this is a dev store.
        """
        if not self.storefront_password:
            return False
        response = await client.post(
            f"{self.origin}/password",
            data={
                "form_type": "storefront_password",
                "utf8": "✓",
                "password": self.storefront_password,
            },
        )
        # Confirm by asking the storefront, not by inspecting cookie names: the
        # proof that the password worked is that the home page stops redirecting
        # to /password.
        probe = await client.get(self.origin, follow_redirects=False)
        unlocked = probe.status_code == 200 or "/password" not in probe.headers.get("location", "")
        log.info(
            "storefront.unlock",
            origin=self.origin,
            unlocked=unlocked,
            status=response.status_code,
        )
        return unlocked

    async def discover(self, client: httpx.AsyncClient) -> list[str]:
        """Find pages through sitemap.xml, which Shopify keeps current for us.

        Preferred over following links: it is complete, it is authoritative, and
        it costs a handful of requests instead of a spider.
        """
        urls: list[str] = []
        queue = [f"{self.origin}/sitemap.xml"]
        seen_sitemaps: set[str] = set()

        while queue and len(urls) < self.max_pages:
            sitemap = queue.pop(0)
            if sitemap in seen_sitemaps:
                continue
            seen_sitemaps.add(sitemap)

            try:
                response = await client.get(sitemap)
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue

            locations = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", response.text)
            for raw in locations:
                location = raw.replace("&amp;", "&").strip()
                if not self._same_origin(location):
                    continue
                # Shopify's child sitemaps look like
                # sitemap_products_1.xml?from=…&to=…, so the suffix has to be
                # tested on the path, not the whole URL. Testing the whole URL
                # made every child sitemap look like a content page, and the
                # crawler parsed raw XML as HTML instead of finding products.
                if urlparse(location).path.endswith(".xml"):
                    queue.append(location)
                elif location not in urls:
                    urls.append(location)
            await asyncio.sleep(self.delay)

        return urls[: self.max_pages]

    async def crawl(self) -> CrawlReport:
        report = CrawlReport()

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            await self._load_robots(client)
            await self._unlock(client)

            urls = await self.discover(client)
            if not urls:
                report.skipped.append(
                    "no sitemap found — the storefront may be password-protected "
                    "or not yet published"
                )
                return report

            for url in urls:
                if not self._allowed(url):
                    report.robots_blocked += 1
                    continue
                try:
                    response = await client.get(url)
                except httpx.HTTPError as exc:
                    report.skipped.append(f"{url}: {type(exc).__name__}")
                    continue

                if response.status_code != 200:
                    report.skipped.append(f"{url}: HTTP {response.status_code}")
                    continue

                title, text = extract_text(response.text)
                if len(text.split()) < 25:
                    # Too little to carry a voice; keeping it would dilute search.
                    report.skipped.append(f"{url}: too little text")
                else:
                    report.pages.append(Page(url=url, title=title, text=text, kind=classify(url)))

                # Serialised and spaced: a storefront is a shop, not a test target.
                await asyncio.sleep(self.delay)

        log.info(
            "storefront.crawled",
            origin=self.origin,
            pages=len(report.pages),
            words=report.words,
            blocked=report.robots_blocked,
        )
        return report
