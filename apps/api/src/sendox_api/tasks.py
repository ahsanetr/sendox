"""Celery tasks.

Email goes through here rather than the request path: a slow or unreachable mail
server must not slow down a signup or leak its failure into the user's response.
"""

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
