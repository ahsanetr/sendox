"""Importing a store's data.

Driven by a fake client rather than a live store, so the logic that matters —
idempotency, consent defaults, missing emails — is testable without network,
credentials, or a particular store's contents.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import sqlalchemy

from sendox_api.config import Settings
from sendox_api.db import get_sessionmaker, global_session, tenant_session
from sendox_api.models import ConsentState, Contact, Event, EventType, Product, Tenant
from sendox_api.services import shopify_sync

pytestmark = pytest.mark.integration


class FakeShopifyClient:
    """Stands in for ShopifyClient, returning canned pages."""

    shop_domain = "fake-store.myshopify.com"

    def __init__(self, **collections: list[dict[str, Any]]) -> None:
        self._collections = collections
        self.calls: list[str] = []

    async def paginate(self, path: str, key: str, **_: Any) -> AsyncIterator[dict[str, Any]]:
        self.calls.append(path)
        for record in self._collections.get(key, []):
            yield record


CUSTOMER = {
    "id": 1001,
    "email": "Buyer@Example.com",
    "first_name": "Sam",
    "last_name": "Rivers",
    "orders_count": 2,
    "total_spent": "340.00",
    "tags": "vip, winter",
    "created_at": "2026-02-01T10:00:00-05:00",
    "email_marketing_consent": {"state": "subscribed"},
    "default_address": {"city": "Portland", "country_code": "US"},
}

ORDER = {
    "id": 5001,
    "email": "buyer@example.com",
    "created_at": "2026-03-04T12:00:00-05:00",
    "total_price": "340.00",
    "currency": "USD",
    "order_number": 1042,
    "line_items": [{"title": "Ridgeline Parka", "quantity": 1}],
}

PRODUCT = {
    "id": 9001,
    "title": "Ridgeline Parka",
    "handle": "ridgeline-parka",
    "body_html": "<p>Three-layer waterproof shell.</p>",
    "vendor": "Northwind",
    "status": "active",
    "tags": "outerwear, winter",
    "variants": [{"price": "340.00"}],
    "images": [{"src": "https://cdn.example.com/parka.jpg"}],
}


def _database_up(settings: Settings) -> bool:
    try:
        with get_sessionmaker(settings)() as session:
            session.execute(sqlalchemy.text("SELECT 1"))
        return True
    except sqlalchemy.exc.SQLAlchemyError:
        return False


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", log_level="WARNING")


@pytest.fixture
def tenant(settings: Settings) -> uuid.UUID:
    if not _database_up(settings):
        pytest.skip("Postgres not running — start it with `make up` or `make up-native`")
    with global_session(settings) as session:
        workspace = Tenant(name="Sync Test", slug=f"sync-{uuid.uuid4().hex[:10]}")
        session.add(workspace)
        session.flush()
        tenant_id = workspace.id
    yield tenant_id
    with global_session(settings) as session:
        found = session.get(Tenant, tenant_id)
        if found:
            session.delete(found)


async def test_an_import_creates_contacts_events_and_products(
    settings: Settings, tenant: uuid.UUID
) -> None:
    client = FakeShopifyClient(customers=[CUSTOMER], orders=[ORDER], products=[PRODUCT])

    with tenant_session(settings, tenant) as session:
        report = await shopify_sync.import_store(client, session, tenant)  # type: ignore[arg-type]

    assert (report.customers, report.orders, report.products) == (1, 1, 1)

    with tenant_session(settings, tenant) as session:
        contact = session.execute(sqlalchemy.select(Contact)).scalar_one()
        product = session.execute(sqlalchemy.select(Product)).scalar_one()
        events = session.execute(sqlalchemy.select(Event)).scalars().all()

        # The address is lower-cased, so "Buyer@Example.com" and "buyer@..." are
        # the same person rather than two contacts.
        assert contact.email == "buyer@example.com"
        assert contact.full_name == "Sam Rivers"
        assert contact.tags == ["vip", "winter"]
        assert contact.email_consent is ConsentState.SUBSCRIBED
        assert contact.is_emailable

        assert product.title == "Ridgeline Parka"
        assert product.price == 340.0

        assert {e.type for e in events} == {EventType.SIGNED_UP, EventType.PLACED_ORDER}
        order_event = next(e for e in events if e.type is EventType.PLACED_ORDER)
        assert order_event.value == 340.0
        assert order_event.contact_id == contact.id


async def test_running_the_import_twice_changes_nothing(
    settings: Settings, tenant: uuid.UUID
) -> None:
    """A 40,000-record import will be interrupted; resuming must not duplicate."""
    client = FakeShopifyClient(customers=[CUSTOMER], orders=[ORDER], products=[PRODUCT])

    with tenant_session(settings, tenant) as session:
        await shopify_sync.import_store(client, session, tenant)  # type: ignore[arg-type]
    with tenant_session(settings, tenant) as session:
        second = await shopify_sync.import_store(client, session, tenant)  # type: ignore[arg-type]

    # The second pass sees the same records, but writes no new events.
    assert second.orders == 0

    with tenant_session(settings, tenant) as session:
        assert len(session.execute(sqlalchemy.select(Contact)).scalars().all()) == 1
        assert len(session.execute(sqlalchemy.select(Product)).scalars().all()) == 1
        assert len(session.execute(sqlalchemy.select(Event)).scalars().all()) == 2


async def test_a_customer_without_an_email_is_skipped_not_fatal(
    settings: Settings, tenant: uuid.UUID
) -> None:
    client = FakeShopifyClient(customers=[{"id": 7, "first_name": "Anon"}, CUSTOMER])

    with tenant_session(settings, tenant) as session:
        report = await shopify_sync.import_store(client, session, tenant)  # type: ignore[arg-type]

    assert report.customers == 1
    assert len(report.skipped) == 1
    assert "no email" in report.skipped[0]


@pytest.mark.parametrize(
    ("customer", "expected"),
    [
        (
            {"email": "a@example.com", "email_marketing_consent": {"state": "subscribed"}},
            ConsentState.SUBSCRIBED,
        ),
        (
            {"email": "b@example.com", "email_marketing_consent": {"state": "unsubscribed"}},
            ConsentState.UNSUBSCRIBED,
        ),
        ({"email": "c@example.com", "accepts_marketing": True}, ConsentState.SUBSCRIBED),
        ({"email": "d@example.com"}, ConsentState.UNKNOWN),
    ],
)
async def test_consent_defaults_to_unknown_rather_than_subscribed(
    settings: Settings, tenant: uuid.UUID, customer: dict[str, Any], expected: ConsentState
) -> None:
    """Emailing someone who never opted in is how a sending domain is ruined."""
    with tenant_session(settings, tenant) as session:
        contact = shopify_sync.upsert_contact(session, tenant, customer)

    assert contact is not None
    assert contact.email_consent is expected


async def test_shopify_values_overwrite_local_ones(settings: Settings, tenant: uuid.UUID) -> None:
    """Shopify is the source of truth, so a correction there lands here."""
    with tenant_session(settings, tenant) as session:
        shopify_sync.upsert_contact(session, tenant, CUSTOMER)

    with tenant_session(settings, tenant) as session:
        shopify_sync.upsert_contact(
            session, tenant, {**CUSTOMER, "first_name": "Samantha", "total_spent": "999.00"}
        )

    with tenant_session(settings, tenant) as session:
        contact = session.execute(sqlalchemy.select(Contact)).scalar_one()
        assert contact.first_name == "Samantha"
        assert contact.total_spent == 999.0
