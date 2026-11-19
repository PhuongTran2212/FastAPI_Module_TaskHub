from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "taskhub",
    broker=str(settings.celery_broker_url),
    include=["app.jobs"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=settings.job_connection_timeout_seconds,
    broker_transport_options={
        "socket_connect_timeout": settings.job_connection_timeout_seconds,
        "socket_timeout": settings.job_connection_timeout_seconds,
    },
    task_publish_retry=False,
    beat_schedule={
        "cleanup-expired-refresh-tokens": {
            "task": "taskhub.cleanup_expired_refresh_tokens",
            "schedule": settings.refresh_cleanup_interval_seconds,
            "options": {"expires": settings.refresh_cleanup_interval_seconds},
        },
    },
)
