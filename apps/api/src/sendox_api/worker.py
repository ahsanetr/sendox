"""Celery application.

Shares the API's codebase on purpose: workers need the same models, settings and
service clients, and a second package would mean duplicating all of it.
"""

from celery import Celery
from celery.schedules import crontab

from sendox_api.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sendox",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["sendox_api.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    # Periodic jobs land here as phases need them (e.g. the 15-minute Shopify
    # incremental sync in phase 2.1).
    beat_schedule={
        "heartbeat": {
            "task": "sendox.heartbeat",
            "schedule": crontab(minute="*/15"),
        },
    },
)
