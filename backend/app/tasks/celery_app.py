from celery import Celery
from app.config import settings

celery_app = Celery(
    "cloud_transfer",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.transfer"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    result_expires=604800,
    worker_prefetch_multiplier=1,
)
