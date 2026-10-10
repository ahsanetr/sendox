"""Shopify connect endpoints (scope M3 FE-1, FE-7).

The install flow spans two requests and a redirect through the merchant's own
admin, so the two halves are deliberately asymmetric:

* `/shopify/install` is **authenticated** — it is a workspace deciding to connect
  a store, and the workspace identity is sealed into the OAuth `state`;
* `/shopify/callback` is **unauthenticated**, because the browser arriving back
  from Shopify may not carry our session cookie. Everything it needs to trust is
  proven cryptographically instead: the HMAC proves Shopify sent it, and the
  signed state proves which workspace started it.
"""

from typing import Annotated, Any
from urllib.parse import quote

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from sendox_api.clients.shopify import ShopifyAuthError, ShopifyClient, ShopifyError
from sendox_api.config import Settings
from sendox_api.db import tenant_session
from sendox_api.dependencies import SettingsDep, Workspace
from sendox_api.models import MemberRole
from sendox_api.services import shopify_oauth, shopify_stores
from sendox_api.services.errors import InsufficientRole
from sendox_api.services.shopify_oauth import (
    InvalidCallback,
    InvalidShopDomain,
    ShopifyNotConfigured,
    TokenExchangeFailed,
)

log = structlog.get_logger(__name__)

# Authenticated, workspace-scoped: a store is connected *to* a workspace, so the
# workspace is part of the path exactly as it is for members and invitations.
router = APIRouter(prefix="/workspaces/{workspace_id}/shopify", tags=["shopify"])

# The callback cannot live under that prefix: the browser arriving back from
# Shopify has no workspace in hand and may carry no session cookie. Which
# workspace it belongs to comes from the signed state instead.
public_router = APIRouter(prefix="/shopify", tags=["shopify"])


class ConnectRequest(BaseModel):
    shop: str = Field(min_length=3, examples=["your-store.myshopify.com"])


class KnowledgeQuery(BaseModel):
    query: str = Field(min_length=1, examples=["what is your returns policy?"])
    top_k: int = Field(default=5, ge=1, le=20)


class StoreOut(BaseModel):
    id: str
    shop_domain: str
    shop_name: str | None
    currency: str | None
    scopes: list[str]
    connected: bool
    installed_at: str | None
    last_sync_at: str | None
    last_indexed_at: str | None


@router.get("/status", summary="Is Shopify connect available, and what is connected?")
async def connection_status(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        stores = [
            StoreOut(
                id=str(store.id),
                shop_domain=store.shop_domain,
                shop_name=store.shop_name,
                currency=store.currency,
                scopes=list(store.scopes or []),
                connected=store.is_active,
                installed_at=store.installed_at.isoformat() if store.installed_at else None,
                last_sync_at=store.last_sync_at.isoformat() if store.last_sync_at else None,
                last_indexed_at=store.last_indexed_at.isoformat()
                if store.last_indexed_at
                else None,
            )
            for store in shopify_stores.stores_for_tenant(session, workspace.tenant_id)
        ]

    ready = settings.shopify_configured and bool(settings.public_base_url)
    return {
        "configured": settings.shopify_configured,
        "public_url_set": bool(settings.public_base_url),
        "ready": ready,
        "redirect_uri": settings.oauth_redirect_uri,
        "scopes": settings.shopify_scope_list,
        "api_version": settings.shopify_api_version,
        "stores": stores,
        "hint": None
        if ready
        else "Set SHOPIFY_API_KEY, SHOPIFY_API_SECRET and PUBLIC_BASE_URL, then "
        "register the redirect URI on the Shopify app.",
    }


@router.post("/install", summary="Begin connecting a store")
async def begin_install(
    request: ConnectRequest, workspace: Workspace, settings: SettingsDep
) -> dict[str, str]:
    """Returns the URL to send the merchant to.

    Returned as JSON rather than a redirect so the dashboard controls the
    navigation — and so an API caller can see where it is being sent.
    """
    try:
        workspace.require(MemberRole.ADMIN)
    except InsufficientRole as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"connecting a store requires the {exc.required} role; you are {exc.actual}",
        ) from exc

    try:
        shop_domain = shopify_oauth.normalise_shop_domain(request.shop)
        state = shopify_oauth.issue_state(settings, workspace.tenant_id)
        url = shopify_oauth.authorize_url(settings, shop_domain, state)
    except InvalidShopDomain as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ShopifyNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {"authorize_url": url, "shop_domain": shop_domain}


@public_router.get("/callback", summary="Where Shopify returns after the merchant approves")
async def callback(
    request: Request,
    settings: SettingsDep,
    shop: Annotated[str, Query()],
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> RedirectResponse:
    params = dict(request.query_params)

    try:
        # Order matters: validate the domain before it is used to build any URL,
        # and check the HMAC before trusting any other parameter.
        shop_domain = shopify_oauth.normalise_shop_domain(shop)
        if not shopify_oauth.verify_hmac(settings, params):
            raise InvalidCallback("the callback signature did not verify")
        tenant_id = shopify_oauth.read_state(settings, state)
        grant = await shopify_oauth.exchange_code(settings, shop_domain, code)
    except (InvalidShopDomain, InvalidCallback) as exc:
        log.warning("shopify.callback_rejected", shop=shop, error=str(exc))
        return _back_to_app(settings, error=str(exc))
    except (ShopifyNotConfigured, TokenExchangeFailed) as exc:
        log.error("shopify.callback_failed", shop=shop, error=str(exc))
        return _back_to_app(settings, error=str(exc))

    with tenant_session(settings, tenant_id) as session:
        store = shopify_stores.save_connection(settings, session, tenant_id=tenant_id, grant=grant)
        # Fetch the shop record immediately: it names the store for the UI and
        # proves the token works before the merchant is told it is connected.
        try:
            client = ShopifyClient(settings, shopify_stores.credentials_for(settings, store))
            shopify_stores.apply_shop_metadata(store, await client.shop())
        except (ShopifyError, ShopifyAuthError) as exc:
            log.warning("shopify.metadata_failed", shop=shop_domain, error=str(exc))

    log.info("shopify.connected", shop=shop_domain, tenant=str(tenant_id))
    return _back_to_app(settings, connected=shop_domain)


@router.post("/stores/{store_id}/sync", summary="Import this store's data")
async def start_sync(store_id: str, workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    """Queue a full import.

    Returns immediately with a task id: an import makes hundreds of rate-limited
    calls and can take minutes, which is not something to hold a request open for.
    """
    try:
        workspace.require(MemberRole.EDITOR)
    except InsufficientRole as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"syncing requires the {exc.required} role; you are {exc.actual}",
        ) from exc

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        stores = shopify_stores.stores_for_tenant(session, workspace.tenant_id)
        store = next((s for s in stores if str(s.id) == store_id and s.is_active), None)
        if store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="store not connected")
        domain = store.shop_domain

    from sendox_api.tasks import import_shopify_store

    task = import_shopify_store.delay(str(workspace.tenant_id), store_id)
    return {"status": "queued", "task_id": task.id, "shop_domain": domain}


@router.post("/stores/{store_id}/index", summary="Crawl the storefront and index its voice")
async def start_indexing(
    store_id: str, workspace: Workspace, settings: SettingsDep
) -> dict[str, Any]:
    """Queue a storefront crawl.

    Separate from the data import on purpose: that one reads the Admin API for
    structured records, this one reads the public site for how the brand writes.
    """
    try:
        workspace.require(MemberRole.EDITOR)
    except InsufficientRole as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"indexing requires the {exc.required} role; you are {exc.actual}",
        ) from exc

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        stores = shopify_stores.stores_for_tenant(session, workspace.tenant_id)
        store = next((s for s in stores if str(s.id) == store_id and s.is_active), None)
        if store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="store not connected")
        domain = store.shop_domain

    from sendox_api.tasks import index_brand_knowledge

    task = index_brand_knowledge.delay(str(workspace.tenant_id), store_id)
    return {"status": "queued", "task_id": task.id, "shop_domain": domain}


@router.get("/knowledge", summary="What Sendox has learned about this brand")
async def brand_knowledge_state(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    """Size of the knowledge base plus a sample, so the learning is inspectable.

    Scope M7 FE-6: a brand owner should be able to see what the AI thinks it
    knows, and say when it is wrong.
    """
    from sendox_api.clients import chroma

    try:
        stats = await chroma.astats(settings, workspace.tenant_id)
        sample = await chroma.aquery(
            settings,
            workspace.tenant_id,
            "what does this brand sell and how does it write?",
            top_k=6,
        )
    except Exception as exc:  # noqa: BLE001 - report, never 500 a status endpoint
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "available": True,
        **stats,
        "sample": [
            {
                "similarity": round(match.similarity, 4),
                "content_type": match.metadata.get("content_type"),
                "source_url": match.metadata.get("source_url"),
                "title": match.metadata.get("title"),
                "text": match.text[:400],
            }
            for match in sample
        ],
    }


@router.post("/knowledge/search", summary="Search this brand's knowledge base")
async def search_knowledge(
    request: KnowledgeQuery, workspace: Workspace, settings: SettingsDep
) -> dict[str, Any]:
    from sendox_api.clients import chroma

    matches = await chroma.aquery(settings, workspace.tenant_id, request.query, top_k=request.top_k)
    return {
        "query": request.query,
        "matches": [
            {
                "similarity": round(match.similarity, 4),
                "content_type": match.metadata.get("content_type"),
                "source_url": match.metadata.get("source_url"),
                "text": match.text[:500],
            }
            for match in matches
        ],
    }


@router.get("/data", summary="What the import has brought in")
async def imported_data(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    """Counts plus a sample, so the dashboard can show the import actually landed."""
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from sendox_api.models import Contact, Event, Product

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        counts = {
            "contacts": session.execute(sa_select(func.count()).select_from(Contact)).scalar_one(),
            "events": session.execute(sa_select(func.count()).select_from(Event)).scalar_one(),
            "products": session.execute(sa_select(func.count()).select_from(Product)).scalar_one(),
        }
        contacts = [
            {
                "email": c.email,
                "name": c.full_name,
                "consent": c.email_consent.value,
                "orders": c.orders_count,
                "spent": c.total_spent,
            }
            for c in session.execute(
                sa_select(Contact).order_by(Contact.total_spent.desc()).limit(10)
            ).scalars()
        ]
        products = [
            {"title": p.title, "price": p.price, "status": p.status}
            for p in session.execute(sa_select(Product).limit(10)).scalars()
        ]

    return {"counts": counts, "top_contacts": contacts, "products": products}


@router.delete("/stores/{store_id}", summary="Disconnect a store")
async def disconnect(store_id: str, workspace: Workspace, settings: SettingsDep) -> dict[str, str]:
    try:
        workspace.require(MemberRole.ADMIN)
    except InsufficientRole as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"disconnecting a store requires the {exc.required} role; you are {exc.actual}",
        ) from exc

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        stores = shopify_stores.stores_for_tenant(session, workspace.tenant_id)
        store = next((s for s in stores if str(s.id) == store_id), None)
        if store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="store not found")
        shopify_stores.mark_uninstalled(session, store, workspace.user_id)
        domain = store.shop_domain

    return {"status": "disconnected", "shop_domain": domain}


def _back_to_app(
    settings: Settings, *, connected: str | None = None, error: str | None = None
) -> RedirectResponse:
    """Send the merchant's browser back to the dashboard with the outcome."""
    base = settings.web_base_url.rstrip("/")
    if error:
        return RedirectResponse(f"{base}/brand?shopify_error={quote(error)}", status_code=302)
    return RedirectResponse(f"{base}/brand?shopify_connected={connected}", status_code=302)
