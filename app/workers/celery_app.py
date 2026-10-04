"""Celery application configuration for asynchronous background task execution."""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "gabster_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.ai_tasks",
        "app.workers.tasks.ingestion_tasks",
        "app.workers.tasks.campaign_tasks",
    ],
)

celery_app.conf.update(
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.ai_tasks.*": {"queue": "ai"},
        "app.workers.tasks.ingestion_tasks.*": {"queue": "ingestion"},
        "app.workers.tasks.campaign_tasks.*": {"queue": "campaigns"},
    },
)
