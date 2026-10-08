"""Celery tasks.

Phase 0.1 ships only the two tasks needed to prove the queue works end to end.
Real tasks (Shopify sync, AI generation, SES send) arrive with their phases.
"""

from typing import Any

import structlog

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
