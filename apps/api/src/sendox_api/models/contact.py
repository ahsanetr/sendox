"""Contacts and their behavioural timeline (scope M5).

This is the heart of the data layer. Everything the AI later writes is grounded
in what is here: who a person is, what they bought, what they opened.

Both tables are tenant-scoped, so one brand's customer list is unreachable from
another workspace at the database level.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from sendox_api.models.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey


class ConsentState(enum.StrEnum):
    """Per-channel permission, tracked separately because the law treats them separately."""

    UNKNOWN = "unknown"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    # Hard bounce or spam complaint: never contact again, regardless of consent.
    SUPPRESSED = "suppressed"


class EventType(enum.StrEnum):
    """What a contact did. Kept open-ended enough for later channels."""

    SIGNED_UP = "signed_up"
    PLACED_ORDER = "placed_order"
    ABANDONED_CHECKOUT = "abandoned_checkout"
    VIEWED_PRODUCT = "viewed_product"
    EMAIL_SENT = "email_sent"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    EMAIL_BOUNCED = "email_bounced"
    UNSUBSCRIBED = "unsubscribed"


class Contact(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_contact_tenant_email"),
        # A re-sync must update the same row rather than create a duplicate.
        Index("ix_contact_tenant_shopify_id", "tenant_id", "shopify_customer_id"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    # E.164 so numbers from different countries compare and dedupe correctly.
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    shopify_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    email_consent: Mapped[ConsentState] = mapped_column(
        SAEnum(ConsentState, name="consent_state", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ConsentState.UNKNOWN,
    )
    sms_consent: Mapped[ConsentState] = mapped_column(
        SAEnum(ConsentState, name="consent_state", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ConsentState.UNKNOWN,
    )

    # Open-ended attributes from Shopify or a CSV, queryable without a migration
    # every time a brand has a field we did not anticipate.
    properties: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Denormalised order history. Recomputed on sync so segmentation and the
    # predictive models in M20 do not aggregate the event table on every query.
    orders_count: Mapped[int] = mapped_column(nullable=False, default=0)
    total_spent: Mapped[float] = mapped_column(nullable=False, default=0.0)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def full_name(self) -> str | None:
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts) or None

    @property
    def is_emailable(self) -> bool:
        return self.email_consent is ConsentState.SUBSCRIBED

    def __repr__(self) -> str:
        return f"<Contact {self.email}>"


class Event(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """One thing a contact did, at a point in time."""

    __tablename__ = "events"
    __table_args__ = (
        # Idempotency: replaying a webhook or re-running an import must not
        # duplicate history. Shopify's object id is the external id.
        UniqueConstraint("tenant_id", "type", "external_id", name="uq_event_tenant_type_external"),
        Index("ix_event_contact_time", "contact_id", "occurred_at"),
    )

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, name="event_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value: Mapped[float | None] = mapped_column(nullable=True)
    meta: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<Event {self.type} @ {self.occurred_at:%Y-%m-%d}>"


class Product(UUIDPrimaryKey, TenantScoped, Timestamps, Base):
    """A product from the connected store.

    Needed by two later modules: the Design Agent fills product blocks from it
    (M11 FE-4), and the validation layer checks AI claims against it (M12 FE-1).
    """

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "shopify_product_id", name="uq_product_tenant_shopify"),
    )

    shopify_product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(String(), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price: Mapped[float | None] = mapped_column(nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    def __repr__(self) -> str:
        return f"<Product {self.title[:40]}>"
