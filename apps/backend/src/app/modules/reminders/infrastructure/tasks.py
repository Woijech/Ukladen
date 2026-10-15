import logging

import httpx

from app.core.config import get_settings
from app.core.logging import log_failure
from app.db.session import create_database_engine, create_session_factory
from app.integrations.bsuir.public_api import IisPublicProvider
from app.modules.reminders.application.delivery import ReminderDispatchUnavailable
from app.modules.reminders.infrastructure.dispatch import dispatch_due
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="reminders.dispatch_due",
    ignore_result=True,
    store_errors_even_if_ignored=False,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(ReminderDispatchUnavailable,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def dispatch_reminders() -> None:
    try:
        engine = create_database_engine(get_settings())
        try:
            # Calendar target reads use stored academic context; this client makes no IIS requests.
            with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
                dispatch_due(create_session_factory(engine), IisPublicProvider(client))
        finally:
            engine.dispose()
    except Exception as error:
        log_failure(logger, "reminders.dispatch_failed", error)
        raise ReminderDispatchUnavailable("Reminder dispatch is unavailable.") from None
