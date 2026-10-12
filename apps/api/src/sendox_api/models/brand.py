"""What Sendox knows about a brand, and where it learned it (scope M6).

Two tables, because there are two kinds of knowledge and they fail differently.

`BrandProfile` is what the merchant *told* us: five questions answered once
during onboarding. It is short, authoritative and never guessed. When the AI and
the merchant disagree about who the audience is, this wins.

`BrandPage` is what we *read* from the public storefront. It is long, noisy and
provisional — a crawl can pick up a theme's demo text or a half-finished draft.
Keeping the extracted text in Postgres rather than only as embeddings in the
vector store is the point of the table: a merchant can be shown the actual page
we learned from and say "that one is wrong, drop it", which is impossible when
all that survives is a 400-character fragment returned by a similarity search.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey


class BrandTone(enum.StrEnum):
    """How the brand speaks, as the merchant describes it.

    A closed list rather than free text because this value is fed to a prompt:
    "warm" and "friendly but not casual" would produce different copy from the
    same intent, and the merchant cannot tell which phrasing works better. The
    free-text nuance goes in `voice_notes`, where it is read as guidance rather
    than as a switch.
    """

    WARM = "warm"
    PLAYFUL = "playful"
    DIRECT = "direct"
    LUXURY = "luxury"
    TECHNICAL = "technical"


class BrandProfile(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """The onboarding answers. Exactly one per workspace."""

    __tablename__ = "brand_profiles"
    __table_args__ = (
        # One brand per workspace is the whole premise of a workspace.
        UniqueConstraint("tenant_id", name="uq_brand_profile_tenant"),
    )

    # Q1 — what do you sell, in your own words?
    what_you_sell: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Q2 — who buys it?
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Q3 — how should Sendox sound?
    tone: Mapped[BrandTone | None] = mapped_column(
        Enum(BrandTone, name="brand_tone", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    # Q4 — anything the AI must never say, claim or promise.
    never_say: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Q5 — free-form voice notes: the nuance a dropdown cannot hold.
    voice_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Assets lifted from the storefront, as URLs rather than files. Downloading
    # and re-hosting a merchant's logo is a storage and licensing problem we do
    # not need yet; the URL is enough to show it and to put it in an email.
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    brand_colors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_complete(self) -> bool:
        """Complete means the questions that steer generation are answered.

        `never_say` and `voice_notes` are deliberately excluded: having nothing
        forbidden and no extra notes is a legitimate answer, and treating blank
        as incomplete would nag a merchant who is already done.
        """
        return all((self.what_you_sell, self.audience, self.tone))

    def __repr__(self) -> str:
        return f"<BrandProfile tenant={self.tenant_id} complete={self.is_complete}>"


class BrandPage(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """One page read from the storefront, kept so the crawl can be inspected."""

    __tablename__ = "brand_pages"
    __table_args__ = (
        # A re-crawl updates a page in place rather than stacking duplicates, so
        # the inspector shows the site as it is now, not every version we saw.
        UniqueConstraint("tenant_id", "url", name="uq_brand_page_tenant_url"),
    )

    store_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("shopify_stores.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # product | page | blog | collection | home — the crawler's classification.
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="page")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Image URLs found on the page, in document order.
    images: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Set when the merchant marks a page as not representative. Excluded pages
    # stay in the table — the merchant should be able to see what they dropped
    # and change their mind — but are skipped the next time we index.
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def is_included(self) -> bool:
        return self.excluded_at is None

    def __repr__(self) -> str:
        return f"<BrandPage {self.kind} {self.url}>"
