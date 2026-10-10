"""Celery tasks.

Email goes through here rather than the request path: a slow or unreachable mail
server must not slow down a signup or leak its failure into the user's response.
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from sendox_api import email
from sendox_api.config import get_settings
from sendox_api.worker import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(name="sendox.ping")
def ping(payload: str = "pong") -> dict[str, Any]:
    """Round-trip probe: enqueued by the API, executed by a worker."""
    log.info("task.ping", payload=payload)
    return {"status": "ok", "echo": payload}


@celery_app.task(name="sendox.heartbeat")
def heartbeat() -> dict[str, str]:
    """Proves Celery Beat is alive and scheduling."""
    log.info("task.heartbeat")
    return {"status": "ok"}


@celery_app.task(
    name="sendox.send_email",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_email(to: str, subject: str, text: str) -> dict[str, str]:
    """Deliver one transactional email, retrying transient SMTP failures."""
    settings = get_settings()
    email.send(settings, email.Outgoing(to=to, subject=subject, text=text))
    return {"status": "sent", "to": to}


def queue_email(message: email.Outgoing) -> None:
    """Enqueue, and fall back to logging if the broker is unreachable.

    A signup must not fail because Redis is down; the account is already created
    and the user can request a fresh verification link.
    """
    try:
        send_email.delay(message.to, message.subject, message.text)
    except Exception as exc:  # noqa: BLE001 - never fail the caller over delivery
        log.error("email.enqueue_failed", to=message.to, error=str(exc))


@celery_app.task(name="sendox.import_shopify_store", bind=True, max_retries=3)
def import_shopify_store(self: Any, tenant_id: str, store_id: str) -> dict[str, Any]:
    """Pull a store's customers, orders and products into our tables.

    Runs in a worker because a full import can take minutes and makes hundreds of
    rate-limited calls — neither belongs in a request. The import itself is
    idempotent, so a retry after a transient failure resumes rather than
    duplicates.
    """
    import asyncio
    import uuid as _uuid

    from sendox_api.clients.shopify import ShopifyAuthError, ShopifyError
    from sendox_api.db import tenant_session
    from sendox_api.models import ShopifyStore
    from sendox_api.services import shopify_stores, shopify_sync

    settings = get_settings()
    tenant = _uuid.UUID(tenant_id)

    async def run() -> dict[str, Any]:
        with tenant_session(settings, tenant) as session:
            store = session.get(ShopifyStore, _uuid.UUID(store_id))
            if store is None or not store.is_active:
                return {"status": "skipped", "reason": "store not connected"}

            client = shopify_stores.client_for(settings, store)
            report = await shopify_sync.import_store(client, session, tenant)
            store.last_sync_at = datetime.now(UTC)
            return {"status": "ok", **report.as_dict()}

    try:
        return asyncio.run(run())
    except ShopifyAuthError as exc:
        # The merchant uninstalled, or revoked the token. Retrying cannot help.
        log.warning("shopify.import_unauthorised", store=store_id, error=str(exc))
        return {"status": "unauthorised", "detail": str(exc)}
    except ShopifyError as exc:
        log.error("shopify.import_failed", store=store_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30) from exc


@celery_app.task(name="sendox.index_brand_knowledge", bind=True, max_retries=2)
def index_brand_knowledge(self: Any, tenant_id: str, store_id: str) -> dict[str, Any]:
    """Crawl a storefront and index what it says into the workspace's knowledge base.

    In a worker because it is deliberately slow: one request per second, because
    a merchant's storefront is a shop and a crawl must never be why a real
    customer waits.
    """
    import asyncio
    import uuid as _uuid

    from sendox_api.clients import chroma
    from sendox_api.clients.storefront import StorefrontCrawler
    from sendox_api.db import tenant_session
    from sendox_api.models import ShopifyStore
    from sendox_api.services import brand_knowledge

    settings = get_settings()
    tenant = _uuid.UUID(tenant_id)

    async def run() -> dict[str, Any]:
        with tenant_session(settings, tenant) as session:
            store = session.get(ShopifyStore, _uuid.UUID(store_id))
            if store is None or not store.is_active:
                return {"status": "skipped", "reason": "store not connected"}
            domain = store.shop_domain

        crawler = StorefrontCrawler(
            domain,
            # Development only: a dev storefront hides behind a password, and a
            # brand's voice cannot be read through a login wall.
            storefront_password=settings.shopify_storefront_password,
        )
        report = await crawler.crawl()
        if not report.pages:
            return {
                "status": "empty",
                "reason": "nothing readable was found",
                "skipped": report.skipped[:5],
            }

        chunks = brand_knowledge.chunks_from_pages(tenant, report.pages)
        written = await chroma.aupsert_chunks(settings, tenant, chunks)
        stats = brand_knowledge.stats_for(report.pages, chunks)

        with tenant_session(settings, tenant) as session:
            store = session.get(ShopifyStore, _uuid.UUID(store_id))
            if store is not None:
                store.last_indexed_at = datetime.now(UTC)

        return {
            "status": "ok",
            "written": written,
            "robots_blocked": report.robots_blocked,
            **stats.as_dict(),
        }

    try:
        return asyncio.run(run())
    except Exception as exc:
        log.error("brand_knowledge.index_failed", store=store_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60) from exc
