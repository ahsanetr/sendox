"""Import a store's customers, orders and products (scope M3 FE-4, M5).

Shopify is treated as the source of truth: a re-sync overwrites local values
rather than merging, so a merchant correcting data in Shopify sees it corrected
here. Everything is upsert-by-external-id, which makes the whole import safely
re-runnable — important, because a 40,000-record import *will* be interrupted at
some point and must resume without duplicating anything.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from sendox_api.clients.shopify import ShopifyClient
from sendox_api.models import ConsentState, Contact, Event, EventType, Product

log = structlog.get_logger(__name__)


@dataclass
class SyncReport:
    customers: int = 0
    orders: int = 0
    products: int = 0
    abandoned_checkouts: int = 0
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "customers": self.customers,
            "orders": self.orders,
            "products": self.products,
            "abandoned_checkouts": self.abandoned_checkouts,
            "skipped": self.skipped[:20],
            "skipped_total": len(self.skipped),
        }


def _parse_time(raw: Any) -> datetime:
    """Shopify sends ISO-8601 with an offset; fall back to now rather than fail."""
    if not raw:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _consent_from(customer: dict[str, Any]) -> ConsentState:
    """Read marketing consent, preferring the modern field over the legacy flag.

    Defaulting to UNKNOWN rather than SUBSCRIBED is deliberate: emailing someone
    who never opted in is how a sending domain's reputation gets destroyed.
    """
    state = (customer.get("email_marketing_consent") or {}).get("state")
    if state == "subscribed":
        return ConsentState.SUBSCRIBED
    if state in {"unsubscribed", "not_subscribed"}:
        return ConsentState.UNSUBSCRIBED
    if customer.get("accepts_marketing") is True:
        return ConsentState.SUBSCRIBED
    return ConsentState.UNKNOWN


def upsert_contact(
    session: Session, tenant_id: uuid.UUID, customer: dict[str, Any]
) -> Contact | None:
    """Create or update one contact. Returns None when there is no usable email."""
    email = str(customer.get("email") or "").strip().lower()
    if not email:
        return None

    contact = session.execute(
        select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email)
    ).scalar_one_or_none()

    if contact is None:
        contact = Contact(tenant_id=tenant_id, email=email)
        session.add(contact)

    contact.shopify_customer_id = str(customer.get("id") or "") or None
    contact.first_name = customer.get("first_name") or None
    contact.last_name = customer.get("last_name") or None
    contact.phone = customer.get("phone") or None
    contact.email_consent = _consent_from(customer)
    contact.orders_count = int(customer.get("orders_count") or 0)
    contact.total_spent = float(customer.get("total_spent") or 0.0)
    contact.tags = [t.strip() for t in str(customer.get("tags") or "").split(",") if t.strip()]
    contact.properties = {
        "shopify_state": customer.get("state"),
        "currency": customer.get("currency"),
        "verified_email": customer.get("verified_email"),
        "default_city": (customer.get("default_address") or {}).get("city"),
        "default_country": (customer.get("default_address") or {}).get("country_code"),
    }
    return contact


def record_event(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    contact: Contact | None,
    event_type: EventType,
    occurred_at: datetime,
    external_id: str | None,
    value: float | None = None,
    meta: dict[str, Any] | None = None,
) -> Event | None:
    """Insert an event unless this exact one is already recorded.

    The uniqueness check is what makes re-running an import — or replaying a
    webhook — harmless.
    """
    if external_id is not None:
        existing = session.execute(
            select(Event).where(
                Event.tenant_id == tenant_id,
                Event.type == event_type,
                Event.external_id == external_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None

    event = Event(
        tenant_id=tenant_id,
        contact_id=contact.id if contact else None,
        type=event_type,
        occurred_at=occurred_at,
        external_id=external_id,
        value=value,
        meta=meta or {},
    )
    session.add(event)
    return event


def upsert_product(session: Session, tenant_id: uuid.UUID, raw: dict[str, Any]) -> Product:
    shopify_id = str(raw.get("id"))
    product = session.execute(
        select(Product).where(
            Product.tenant_id == tenant_id, Product.shopify_product_id == shopify_id
        )
    ).scalar_one_or_none()

    if product is None:
        product = Product(tenant_id=tenant_id, shopify_product_id=shopify_id, title="")
        session.add(product)

    variants = raw.get("variants") or []
    images = raw.get("images") or []

    product.title = str(raw.get("title") or "")[:500]
    product.handle = raw.get("handle")
    product.description = raw.get("body_html")
    product.product_type = raw.get("product_type") or None
    product.vendor = raw.get("vendor") or None
    product.status = raw.get("status") or None
    product.price = float(variants[0].get("price") or 0) if variants else None
    product.image_url = (images[0].get("src") if images else None) or (
        (raw.get("image") or {}).get("src")
    )
    product.tags = [t.strip() for t in str(raw.get("tags") or "").split(",") if t.strip()]
    return product


async def import_store(
    client: ShopifyClient,
    session: Session,
    tenant_id: uuid.UUID,
    *,
    max_records: int | None = None,
) -> SyncReport:
    """Pull the store's catalogue and customer history into our tables.

    `max_records` caps each collection, which keeps the development dashboard
    responsive against a store with tens of thousands of records.
    """
    report = SyncReport()

    # Customers first: orders and checkouts attach to them.
    async for customer in client.paginate("customers.json", "customers"):
        contact = upsert_contact(session, tenant_id, customer)
        if contact is None:
            report.skipped.append(f"customer {customer.get('id')}: no email")
            continue
        session.flush()
        record_event(
            session,
            tenant_id,
            contact=contact,
            event_type=EventType.SIGNED_UP,
            occurred_at=_parse_time(customer.get("created_at")),
            external_id=f"customer:{customer.get('id')}",
            meta={"source": "shopify"},
        )
        report.customers += 1
        if max_records and report.customers >= max_records:
            break

    by_email = {
        contact.email: contact
        for contact in session.execute(
            select(Contact).where(Contact.tenant_id == tenant_id)
        ).scalars()
    }

    async for order in client.paginate("orders.json", "orders", status="any"):
        email = str(order.get("email") or "").strip().lower()
        contact = by_email.get(email)
        occurred = _parse_time(order.get("created_at"))

        event = record_event(
            session,
            tenant_id,
            contact=contact,
            event_type=EventType.PLACED_ORDER,
            occurred_at=occurred,
            external_id=f"order:{order.get('id')}",
            value=float(order.get("total_price") or 0),
            meta={
                "order_number": order.get("order_number"),
                "currency": order.get("currency"),
                "line_items": [
                    {"title": item.get("title"), "quantity": item.get("quantity")}
                    for item in (order.get("line_items") or [])[:10]
                ],
            },
        )
        if event is not None:
            report.orders += 1
        if contact is not None and (
            contact.last_order_at is None or occurred > contact.last_order_at
        ):
            contact.last_order_at = occurred
        if max_records and report.orders >= max_records:
            break

    async for product in client.paginate("products.json", "products"):
        upsert_product(session, tenant_id, product)
        report.products += 1
        if max_records and report.products >= max_records:
            break

    log.info(
        "shopify.import_complete",
        shop=client.shop_domain,
        tenant=str(tenant_id),
        **{k: v for k, v in report.as_dict().items() if isinstance(v, int)},
    )
    return report
