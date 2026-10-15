"""What an agent concluded about a brand by reading its data (scope M7 FE-4/5).

`BrandProfile` is what the merchant said. This is what was inferred from the
catalogue, the storefront copy and, when Shopify allows it, the order history.
The two are composed into a single context for the writing agents, but they are
stored apart and every composed field keeps its source, because the first
question about a bad email is always "did the brand tell us that, or did we
guess it?" and a merged blob cannot answer.

Versioned per FE-5: a refresh that makes the profile worse has to be
reversible, so analyses accumulate and the newest is merely the default.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey


class BrandAnalysis(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "brand_analyses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_brand_analysis_tenant_version"),
    )

    # Monotonic per workspace. The highest version is current; nothing is
    # deleted, so an earlier one can be made current again.
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # The structured result. Shape is owned by services/brand_analysis.py and
    # deliberately not modelled as columns: the schema will change as the
    # writing agents learn what they actually need, and a migration per field
    # would make that expensive enough to discourage it.
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # What the analysis was allowed to look at, so a thin result is explicable
    # rather than mysterious. Shopify withholds customers and orders from apps
    # without protected-data approval, which is the common case.
    sources: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # The exact prompt, kept so a wrong conclusion can be traced to what the
    # model was actually given rather than what we think it was given.
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Set when a merchant restores an older version, so "current" is a decision
    # rather than always just the newest row.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<BrandAnalysis v{self.version} tenant={self.tenant_id}>"


def next_version(existing: list[int]) -> int:
    """Versions count up from 1 and never reuse a number.

    Reusing one would make "restore version 3" ambiguous the moment a fourth
    analysis is generated after a restore.
    """
    return (max(existing) + 1) if existing else 1
