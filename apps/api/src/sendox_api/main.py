"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sendox_api import __version__
from sendox_api.clients import chroma
from sendox_api.config import Settings, get_settings
from sendox_api.logging_setup import configure_logging
from sendox_api.routers import dev, health, status


async def _warm_embeddings(log: structlog.stdlib.BoundLogger) -> None:
    try:
        await chroma.awarm_embedding_model()
        log.info("api.embedding_model_ready")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - never take the app down for this
        log.warning("api.embedding_model_unavailable", error=str(exc))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    log = structlog.get_logger(__name__)

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            release=f"sendox-api@{__version__}",
            traces_sample_rate=0.1,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log.info("api.startup", env=settings.env, version=__version__)
        # Warm the local embedding model in the background. Deliberately not
        # awaited: if the model is not already cached it downloads ~79MB, and
        # blocking startup on that makes the container healthcheck fail before the
        # app ever serves a request. The image bakes the model in, so this is
        # normally instant.
        warmup = asyncio.create_task(_warm_embeddings(log))
        yield
        warmup.cancel()
        log.info("api.shutdown")

    app = FastAPI(
        title="Sendox API",
        version=__version__,
        summary="AI-native multi-channel marketing platform for Shopify brands",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Read back by `get_request_settings`, so routers always see the settings
    # this app was constructed with.
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(status.router)

    # Capability checks are a development aid; they expose internals and must not
    # ship to production.
    if not settings.is_production:
        app.include_router(dev.router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "sendox-api", "version": __version__, "docs": "/docs"}

    return app


app = create_app()
