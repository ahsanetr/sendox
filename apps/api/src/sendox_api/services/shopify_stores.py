"""Persisting a connected Shopify store (scope M3 FE-2, FE-3, FE-7)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sendox_api.clients.shopify import ShopCredentials, ShopifyClient
from sendox_api.config import Settings
from sendox_api.crypto import decrypt_for_tenant, encrypt_for_tenant
from sendox_api.models import ShopifyStore
from sendox_api.services import audit
from sendox_api.services.shopify_oauth import InstallGrant


def stores_for_tenant(session: Session, tenant_id: uuid.UUID) -> list[ShopifyStore]:
    return list(
        session.execute(
            select(ShopifyStore)
            .where(ShopifyStore.tenant_id == tenant_id)
            .order_by(ShopifyStore.created_at)
        )
        .scalars()
        .all()
    )


def find_store(session: Session, tenant_id: uuid.UUID, shop_domain: str) -> ShopifyStore | None:
    return session.execute(
        select(ShopifyStore).where(
            ShopifyStore.tenant_id == tenant_id, ShopifyStore.shop_domain == shop_domain
        )
    ).scalar_one_or_none()


def save_connection(
    settings: Settings,
    session: Session,
    *,
    tenant_id: uuid.UUID,
    grant: InstallGrant,
    actor_user_id: uuid.UUID | None = None,
) -> ShopifyStore:
    """Create or refresh a store connection.

    Reconnecting an existing store updates the token in place rather than adding
    a row, so a merchant who reinstalls keeps their contacts, events and history.
    """
    store = find_store(session, tenant_id, grant.shop_domain)
    encrypted = encrypt_for_tenant(settings, tenant_id, grant.access_token)
    now = datetime.now(UTC)

    if store is None:
        store = ShopifyStore(
            tenant_id=tenant_id,
            shop_domain=grant.shop_domain,
            access_token_encrypted=encrypted,
            scopes=grant.scopes,
            installed_at=now,
        )
        session.add(store)
        action = "shopify.connected"
    else:
        store.access_token_encrypted = encrypted
        store.scopes = grant.scopes
        store.installed_at = now
        store.uninstalled_at = None
        action = "shopify.reconnected"

    audit.record(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        target=grant.shop_domain,
        meta={"scopes": grant.scopes},
    )
    session.flush()
    return store


def credentials_for(settings: Settings, store: ShopifyStore) -> ShopCredentials:
    """Decrypt the stored token for use against the Admin API."""
    return ShopCredentials(
        shop_domain=store.shop_domain,
        access_token=decrypt_for_tenant(settings, store.tenant_id, store.access_token_encrypted),
    )


def client_for(settings: Settings, store: ShopifyStore) -> ShopifyClient:
    return ShopifyClient(settings, credentials_for(settings, store))


def apply_shop_metadata(store: ShopifyStore, shop: dict[str, object]) -> ShopifyStore:
    """Record the human-readable details so the dashboard shows a real store."""
    store.shop_name = str(shop.get("name") or "") or None
    store.shop_email = str(shop.get("email") or "") or None
    store.currency = str(shop.get("currency") or "") or None
    store.shop_timezone = str(shop.get("iana_timezone") or "") or None
    return store


def mark_uninstalled(
    session: Session, store: ShopifyStore, actor_user_id: uuid.UUID | None = None
) -> ShopifyStore:
    """Keep the row, drop the token.

    The history stays so a reconnect is seamless, but the credential is gone the
    moment it stops being needed.
    """
    store.uninstalled_at = datetime.now(UTC)
    store.access_token_encrypted = ""
    audit.record(
        session,
        tenant_id=store.tenant_id,
        actor_user_id=actor_user_id,
        action="shopify.disconnected",
        target=store.shop_domain,
    )
    return store
