"""Reading and writing a workspace's brand profile and extracted pages (M6).

Every function here takes a session that is already tenant-scoped, so none of
them filter by `tenant_id` themselves — row-level security does that, and a
hand-written filter would only create a second place for the rule to be wrong.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sendox_api.clients.storefront import Page
from sendox_api.models import BrandPage, BrandProfile, BrandTone


def get_profile(session: Session, tenant_id: uuid.UUID) -> BrandProfile | None:
    return session.scalars(select(BrandProfile)).one_or_none()


def ensure_profile(session: Session, tenant_id: uuid.UUID) -> BrandProfile:
    """The profile row for this workspace, created empty if it does not exist.

    An empty row rather than None means the rest of the code never has to ask
    "has onboarding started?" before reading a field.
    """
    profile = get_profile(session, tenant_id)
    if profile is None:
        profile = BrandProfile(tenant_id=tenant_id, brand_colors=[])
        session.add(profile)
        session.flush()
    return profile


def update_profile(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    what_you_sell: str | None = None,
    audience: str | None = None,
    tone: BrandTone | None = None,
    never_say: str | None = None,
    voice_notes: str | None = None,
    logo_url: str | None = None,
    brand_colors: list[str] | None = None,
) -> BrandProfile:
    """Apply the answers given, leaving the rest alone.

    The wizard saves one step at a time, so a partial payload is the normal
    case rather than an error: `None` means "not answered in this request", not
    "clear this field". Clearing an answer is done by sending an empty string,
    which is why the blanks are normalised to NULL here rather than rejected.
    """
    profile = ensure_profile(session, tenant_id)

    if what_you_sell is not None:
        profile.what_you_sell = what_you_sell.strip() or None
    if audience is not None:
        profile.audience = audience.strip() or None
    if tone is not None:
        profile.tone = tone
    if never_say is not None:
        profile.never_say = never_say.strip() or None
    if voice_notes is not None:
        profile.voice_notes = voice_notes.strip() or None
    if logo_url is not None:
        profile.logo_url = logo_url.strip() or None
    if brand_colors is not None:
        profile.brand_colors = brand_colors

    # Stamped the first time the answers that steer generation are all present,
    # and never cleared afterwards: `completed_at` records that onboarding
    # happened, which stays true even if the merchant later blanks a field.
    if profile.completed_at is None and profile.is_complete:
        profile.completed_at = datetime.now(UTC)

    session.flush()
    return profile


def pages_for(
    session: Session, tenant_id: uuid.UUID, *, included_only: bool = False
) -> Sequence[BrandPage]:
    """Extracted pages, largest first — the ones with the most voice in them."""
    statement = select(BrandPage)
    if included_only:
        statement = statement.where(BrandPage.excluded_at.is_(None))
    return session.scalars(statement.order_by(BrandPage.word_count.desc())).all()


def record_pages(
    session: Session,
    tenant_id: uuid.UUID,
    store_id: uuid.UUID | None,
    pages: Sequence[Page],
) -> int:
    """Persist a crawl's pages, updating any URL already seen.

    Updating in place rather than deleting and reinserting keeps two things a
    merchant would notice: the `excluded_at` decision they made about a page
    survives a re-crawl, and the row's identity stays stable so a link to it
    does not rot.
    """
    crawled_at = datetime.now(UTC)
    existing = {page.url: page for page in session.scalars(select(BrandPage)).all()}

    for page in pages:
        row = existing.get(page.url)
        if row is None:
            row = BrandPage(tenant_id=tenant_id, url=page.url, crawled_at=crawled_at)
            session.add(row)
        row.store_id = store_id
        row.title = page.title[:512]
        row.kind = page.kind
        row.text = page.text
        row.word_count = page.word_count
        row.images = list(page.images)
        row.crawled_at = crawled_at

    session.flush()
    return len(pages)


def set_page_excluded(
    session: Session, tenant_id: uuid.UUID, page_id: uuid.UUID, excluded: bool
) -> BrandPage | None:
    page = session.get(BrandPage, page_id)
    if page is None:
        return None
    page.excluded_at = datetime.now(UTC) if excluded else None
    session.flush()
    return page


def guess_assets(pages: Sequence[Page]) -> str | None:
    """The brand's logo, guessed from the home page's first image.

    A guess, and labelled as one everywhere it surfaces: themes put a promo
    banner above the logo often enough that this is wrong perhaps a third of the
    time. It exists so the merchant has something to correct rather than a blank
    field to fill, which is a much harder thing to ask for.
    """
    home = next((page for page in pages if page.kind == "home"), None)
    if home is None or not home.images:
        return None
    return home.images[0]
