from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "ukladen",
    broker=str(settings.redis_url),
    include=["app.modules.auth.infrastructure.email_tasks"],
)
celery_app.conf.update(
    task_protocol=2,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    enable_utc=True,
    timezone="UTC",
    broker_connection_retry_on_startup=True,
    beat_schedule={},
)


@celery_app.task(name="foundation.ping")
def ping() -> str:
    """Idempotent diagnostic task with no business effects."""
    return "pong"
