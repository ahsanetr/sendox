"""A Shopify store connected to a workspace (scope M3).

Tenant-scoped, so row-level security applies: one workspace can never read
another's store connection, and therefore never its access token.

The token is stored encrypted rather than hashed, because unlike a password it
has to be sent back to Shopify on every request. `crypto.py` explains the scheme;
the important part here is that the column never holds a usable token on its own.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey


class ShopifyStore(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "shopify_stores"
    __table_args__ = (
        # A store may only be connected once per workspace. Different workspaces
        # connecting the same store is allowed — that is a merchant moving, or a
        # genuine agency arrangement.
        UniqueConstraint("tenant_id", "shop_domain", name="uq_shopify_store_tenant_domain"),
    )

    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    access_token_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Shop metadata, fetched once on connect so the UI can show a real name.
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    shop_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the storefront was last crawled and indexed. Separate from last_sync_at
    # because the two read different sources: the Admin API, and the public site.
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when Shopify tells us the app was removed. The row is kept so the
    # workspace keeps its history and can reconnect without losing anything.
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.uninstalled_at is None

    def __repr__(self) -> str:
        return f"<ShopifyStore {self.shop_domain}>"
